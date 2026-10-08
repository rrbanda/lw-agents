"""Production entry point — runs ADK with uvicorn workers for reliability.

The default `adk web` command runs a single uvicorn process. During long-running
tool operations (mvn compile, git push), the single process can't serve health
checks or SSE keepalives, causing proxy/browser disconnects.

This entry point uses `get_fast_api_app()` (the production API recommended by
ADK's GKE deployment docs) and runs it with multiple uvicorn workers.
"""

from __future__ import annotations

import os
import pathlib

import uvicorn
from google.adk.cli.api_server import get_fast_api_app

AGENT_DIR = str(pathlib.Path(__file__).resolve().parent)

app = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri="memory://",
    web=True,
    allow_origins=["*"],
)

if __name__ == "__main__":
    workers = int(os.environ.get("WEB_WORKERS", "3"))
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        timeout_keep_alive=300,
        log_level="info",
    )
