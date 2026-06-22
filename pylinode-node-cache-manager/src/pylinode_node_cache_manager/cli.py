"""
Main CLI entry point for node cache manager daemon.
Handles signal handling, logging setup, and daemon lifecycle.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

from prometheus_client import start_http_server

from .config import AppConfig, load_cache_manifest
from .cache_manager import CacheManager


# Setup logging
def setup_logging(log_level: str) -> logging.Logger:
    """Configure structured logging."""
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger(__name__)


logger = logging.getLogger(__name__)


class DaemonApp:
    """Main daemon application."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.cache_manager: Optional[CacheManager] = None
        self._logger = logging.getLogger(self.__class__.__name__)

    async def startup(self) -> None:
        """Initialize daemon on startup."""
        self._logger.info(f"Starting node cache manager (cache_path={self.config.cache_path})")

        # Validate configuration
        try:
            self.config.validate()
        except ValueError as e:
            self._logger.error(f"Configuration validation failed: {e}")
            raise

        # Load cache manifest
        manifest = load_cache_manifest()

        # Initialize cache manager
        self.cache_manager = CacheManager(
            cache_root=Path(self.config.cache_path),
            manifest=manifest,
            download_timeout=self.config.download_timeout_seconds,
            min_free_disk_percent=self.config.min_free_disk_percent,
            hf_token=self.config.hf_token,
            aws_access_key_id=self.config.aws_access_key_id,
            aws_secret_access_key=self.config.aws_secret_access_key,
        )

        # Start metrics server
        try:
            start_http_server(self.config.metrics_port)
            self._logger.info(f"Metrics server started on port {self.config.metrics_port}")
        except Exception as e:
            self._logger.error(f"Failed to start metrics server: {e}")
            raise

        self._logger.info("Daemon startup complete")

    async def run(self, stop: asyncio.Event) -> None:
        """Main daemon loop. Exits as soon as `stop` is set."""
        if not self.cache_manager:
            raise RuntimeError("Daemon not initialized; call startup() first")

        self._logger.info("Entering main loop")

        # Perform initial reconciliation
        try:
            await self.cache_manager.reconcile()
        except Exception as e:
            self._logger.error(f"Initial reconciliation failed: {e}")

        # Main reconcile loop: sleep until interval elapses OR stop is requested.
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=self.config.reconcile_interval_seconds,
                )
                # stop was set during the wait — exit cleanly
                break
            except asyncio.TimeoutError:
                # Normal: interval elapsed, run next reconcile
                pass

            if stop.is_set():
                break

            try:
                await self.cache_manager.reconcile()
            except Exception as e:
                self._logger.error(f"Reconciliation error: {e}", exc_info=True)

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self._logger.info("Shutdown signal received")

        if self.cache_manager:
            try:
                await self.cache_manager.cleanup()
            except Exception as e:
                self._logger.error(f"Error during cleanup: {e}")

        self._logger.info("Daemon shutdown complete")


async def main_async(app: DaemonApp) -> None:
    """Async main entry point."""
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    # Use loop.add_signal_handler (asyncio-native) so signals are delivered on
    # the event loop thread and immediately wake any awaiting coroutine.
    def _on_signal(signum: int) -> None:
        logger.info(f"Received signal {signum}, shutting down…")
        stop.set()

    loop.add_signal_handler(signal.SIGTERM, _on_signal, signal.SIGTERM)
    loop.add_signal_handler(signal.SIGINT, _on_signal, signal.SIGINT)

    try:
        await app.startup()
        await app.run(stop)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await app.shutdown()


def main() -> None:
    """Main entry point."""
    try:
        config = AppConfig.from_env()
        setup_logging(config.log_level)

        app = DaemonApp(config)
        asyncio.run(main_async(app))
    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
