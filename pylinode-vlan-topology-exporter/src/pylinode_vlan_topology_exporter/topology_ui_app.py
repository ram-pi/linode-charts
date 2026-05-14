"""FastAPI app for live VLAN topology UI."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .topology_ui_model import parse_topology_metrics


LOGGER = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent


class TopologyReader:
    """Reads current topology snapshot from exporter metrics endpoint."""

    def __init__(self, metrics_url: str, timeout_seconds: float) -> None:
        self.metrics_url = metrics_url
        self.timeout_seconds = timeout_seconds

    def fetch(self) -> dict[str, Any]:
        started = datetime.now(UTC)
        try:
            response = httpx.get(self.metrics_url, timeout=self.timeout_seconds)
            response.raise_for_status()
            snapshot = parse_topology_metrics(response.text)
            snapshot["ui"] = {
                "status": "ok",
                "error": "",
                "exporter_metrics_url": self.metrics_url,
                "fetched_at": started.isoformat(),
            }
            return snapshot
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("failed to read metrics from %s: %s", self.metrics_url, exc)
            return {
                "generated_at": datetime.now(UTC).isoformat(),
                "scrape": {
                    "success": 0,
                    "duration_seconds": 0.0,
                    "api_rate_limit_hits_total": 0.0,
                },
                "summary": {
                    "vlan_count": 0,
                    "attachment_count": 0,
                    "unique_linode_count": 0,
                },
                "vlans": [],
                "attachments": [],
                "ui": {
                    "status": "error",
                    "error": str(exc),
                    "exporter_metrics_url": self.metrics_url,
                    "fetched_at": started.isoformat(),
                },
            }


def create_app() -> FastAPI:
    """Create and configure the topology UI app."""
    metrics_url = os.getenv("TOPOLOGY_METRICS_URL", "http://exporter:9108/metrics")
    timeout_seconds = float(os.getenv("TOPOLOGY_HTTP_TIMEOUT_SECONDS", "5"))
    reader = TopologyReader(metrics_url=metrics_url, timeout_seconds=timeout_seconds)

    app = FastAPI(title="Linode VLAN Topology UI", version="0.1.0")
    templates = Jinja2Templates(directory=str(BASE_DIR / "topology_ui_templates"))
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "topology_ui_static")), name="static")

    @app.api_route("/healthz", methods=["GET", "HEAD"])
    def healthz() -> dict[str, str]:
        """Health check endpoint. Supports both GET and HEAD for NodeBalancer probes."""
        return {"status": "ok"}

    @app.get("/api/topology")
    def api_topology() -> JSONResponse:
        return JSONResponse(reader.fetch())

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "metrics_url": metrics_url,
                "refresh_seconds": int(os.getenv("TOPOLOGY_REFRESH_SECONDS", "60")),
            },
        )

    return app
