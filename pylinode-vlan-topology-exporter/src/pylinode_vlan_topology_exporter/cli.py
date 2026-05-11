"""CLI entrypoint for VLAN topology exporter."""

from __future__ import annotations

import logging
import signal

from prometheus_client import start_http_server

from .config import Config
from .exporter import VlanTopologyExporter


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config.from_env()
    exporter = VlanTopologyExporter(cfg)

    def _handle_signal(signum: int, _frame: object) -> None:
        logging.getLogger(__name__).info("received signal %s, shutting down", signum)
        exporter.stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    start_http_server(cfg.listen_port)
    logging.getLogger(__name__).info(
        "exporter listening on :%s interval=%ss workers=%s vlan_filter=%s",
        cfg.listen_port,
        cfg.scrape_interval_seconds,
        cfg.max_workers,
        cfg.vlan_label_filter or "<none>",
    )
    exporter.run_forever()
