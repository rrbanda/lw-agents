"""Production FastAPI entry point with SSE keepalive fix.

ADK 2.11.0's /run_sse uses StreamingResponse without keepalive pings.
During long tool execution (mvn compile, 60+ seconds), no SSE events
flow, causing proxies and browsers to drop the connection (adk-web #307).

This entry point wraps the SSE event generator with periodic `: ping`
SSE comment keepalives (every 10s), which proxies and browsers treat as
activity. The SSE spec says clients MUST ignore comment lines.

Reference: https://github.com/google/adk-web/issues/307
Reference: https://html.spec.whatwg.org/multipage/server-sent-events.html
"""

from __future__ import annotations

import asyncio
import os

import uvicorn
from fastapi.responses import StreamingResponse
from google.adk.cli.fast_api import get_fast_api_app
from starlette.requests import Request

AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))

app = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    web=True,
    allow_origins=["*"],
)


def _wrap_sse_with_keepalive(original_route):
    """Wrap an SSE endpoint to inject `: ping` keepalives every 10 seconds."""

    async def keepalive_wrapper(request: Request):
        response = await original_route(request)

        if not isinstance(response, StreamingResponse):
            return response
        if response.media_type != "text/event-stream":
            return response

        original_body = response.body_iterator

        async def keepalive_generator():
            ping_task = None
            queue: asyncio.Queue = asyncio.Queue()
            stop = asyncio.Event()

            async def ping_loop():
                while not stop.is_set():
                    await asyncio.sleep(10)
                    if not stop.is_set():
                        await queue.put(": ping\n\n")

            async def data_loop():
                try:
                    async for chunk in original_body:
                        await queue.put(chunk)
                finally:
                    stop.set()
                    await queue.put(None)

            ping_task = asyncio.create_task(ping_loop())
            data_task = asyncio.create_task(data_loop())

            try:
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    yield item
            finally:
                stop.set()
                ping_task.cancel()
                data_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass
                try:
                    await data_task
                except asyncio.CancelledError:
                    pass

        return StreamingResponse(
            keepalive_generator(),
            media_type="text/event-stream",
            headers=dict(response.headers),
        )

    return keepalive_wrapper


# Patch the /run_sse route to add keepalive pings
for route in app.routes:
    if hasattr(route, "path") and route.path == "/run_sse":
        route.endpoint = _wrap_sse_with_keepalive(route.endpoint)
        break


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        timeout_keep_alive=300,
        log_level="info",
    )
