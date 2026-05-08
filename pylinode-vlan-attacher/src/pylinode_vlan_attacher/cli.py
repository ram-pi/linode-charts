"""CLI entrypoint."""

from __future__ import annotations

import logging
import signal
import threading

from .config import Config
from .controller import VLANAttacherController


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    stop_event = threading.Event()

    def _handle_signal(signum: int, _frame: object) -> None:
        LOGGER = logging.getLogger(__name__)
        LOGGER.info("received signal %s, shutting down gracefully", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    cfg = Config.from_env()
    try:
        VLANAttacherController(cfg, stop_event=stop_event).run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("keyboard interrupt received, exiting")
