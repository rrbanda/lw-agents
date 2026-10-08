"""Production FastAPI entry point with SSE keepalive middleware.

ADK's /run_sse sends no data during long tool execution (mvn, 60s+).
Proxies and browsers drop idle SSE connections (adk-web #307).

This adds ASGI middleware that intercepts SSE responses and injects
`: ping` comment keepalives every 10 seconds. Unlike route patching,
middleware wraps the actual response bytes at the ASGI protocol level.

ADK pinned to 2.10.0 — 2.11.0 cancels the agent on SSE disconnect.
"""

from __future__ import annotations

import asyncio
import os
import time

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))

app = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    web=True,
    allow_origins=["*"],
)


class SSEKeepaliveMiddleware:
    """ASGI middleware that injects `: ping` keepalives into SSE streams."""

    PING = b": ping\n\n"
    INTERVAL = 10  # seconds

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check if this is the /run_sse endpoint
        path = scope.get("path", "")
        if path != "/run_sse":
            await self.app(scope, receive, send)
            return

        # Wrap the send callable to inject keepalives between body chunks
        is_sse = False
        last_send = time.monotonic()
        ping_task = None
        send_lock = asyncio.Lock()

        async def ping_loop():
            nonlocal last_send
            while True:
                await asyncio.sleep(self.INTERVAL)
                elapsed = time.monotonic() - last_send
                if elapsed >= self.INTERVAL and is_sse:
                    async with send_lock:
                        try:
                            await send(
                                {
                                    "type": "http.response.body",
                                    "body": self.PING,
                                    "more_body": True,
                                }
                            )
                            last_send = time.monotonic()
                        except Exception:
                            return

        async def send_wrapper(message):
            nonlocal is_sse, last_send, ping_task

            if message["type"] == "http.response.start":
                headers = dict((k.lower(), v) for k, v in (message.get("headers") or []))
                if b"text/event-stream" in headers.get(b"content-type", b""):
                    is_sse = True
                    ping_task = asyncio.create_task(ping_loop())

            if message["type"] == "http.response.body" and is_sse:
                async with send_lock:
                    last_send = time.monotonic()
                    await send(message)
                return

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if ping_task:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass


# Wrap at ASGI level — more reliable than app.add_middleware()
_inner_app = app
app = SSEKeepaliveMiddleware(_inner_app)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        timeout_keep_alive=300,
        log_level="info",
    )
