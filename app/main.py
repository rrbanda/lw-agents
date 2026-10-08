"""Production FastAPI entry point — matches the official ADK samples pattern.

Uses get_fast_api_app() from google.adk.cli.fast_api (the public API) instead
of the `adk web` CLI command. This gives us control over uvicorn settings
(timeout_keep_alive for long SSE streams) while serving the same Web UI.

Reference: adk-samples/core/python/ambient-expense-agent/expense_agent/fast_api_app.py
"""

from __future__ import annotations

import os

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))

app = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    web=True,
    allow_origins=["*"],
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        timeout_keep_alive=300,
        log_level="info",
    )
