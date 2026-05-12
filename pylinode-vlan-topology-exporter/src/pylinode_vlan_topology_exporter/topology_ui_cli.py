"""CLI entrypoint for topology UI service."""

from __future__ import annotations

import logging
import os

import uvicorn

from .topology_ui_app import create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app()
    host = os.getenv("TOPOLOGY_UI_HOST", "0.0.0.0")
    port = int(os.getenv("TOPOLOGY_UI_PORT", "9200"))
    uvicorn.run(app, host=host, port=port, log_level="info")
