"""Production entry point — runs ADK with uvicorn workers for reliability.

The default `adk web` command runs a single uvicorn process. During long-running
tool operations (mvn compile, git push), the single process can't serve health
checks or SSE keepalives, causing proxy/browser disconnects (adk-web #307).

This wraps the same ADK CLI setup but runs with multiple workers.
"""

from __future__ import annotations

import os

import uvicorn


def create_app():
    """Create the FastAPI app the same way `adk web` does internally."""
    from google.adk.cli.cli import _setup_services_and_start_api_server

    agents_dir = os.environ.get("AGENTS_DIR", "/sandbox")
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8080"))

    # This returns the FastAPI app without running uvicorn
    app = _setup_services_and_start_api_server(
        agents_dir=agents_dir,
        host=host,
        port=port,
        session_service_uri="memory://",
        web=True,
        start_server=False,
    )
    return app


# Try the internal setup; fall back to manual ApiServer if signature differs
try:
    app = create_app()
except (ImportError, TypeError, AttributeError):
    # Fallback: construct ApiServer manually

    from google.adk.agents.in_memory_session_service import InMemorySessionService
    from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
    from google.adk.cli.agent_loader import AgentLoader
    from google.adk.cli.api_server import ApiServer
    from google.adk.memory.in_memory_memory_service import InMemoryMemoryService

    agents_dir = os.environ.get("AGENTS_DIR", "/sandbox")

    try:
        from google.adk.auth.credential_service.in_memory_credential_service import (
            InMemoryCredentialService,
        )
    except ImportError:
        InMemoryCredentialService = None

    try:
        from google.adk.evaluation.local_eval_set_results_manager import (
            LocalEvalSetResultsManager,
        )
        from google.adk.evaluation.local_eval_sets_manager import LocalEvalSetsManager

        eval_mgr = LocalEvalSetsManager(agents_dir=agents_dir)
        eval_res_mgr = LocalEvalSetResultsManager(agents_dir=agents_dir)
    except ImportError:
        eval_mgr = None
        eval_res_mgr = None

    kwargs = dict(
        agent_loader=AgentLoader(agents_dir),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
        artifact_service=InMemoryArtifactService(),
        agents_dir=agents_dir,
    )
    if InMemoryCredentialService:
        kwargs["credential_service"] = InMemoryCredentialService()
    if eval_mgr:
        kwargs["eval_sets_manager"] = eval_mgr
        kwargs["eval_set_results_manager"] = eval_res_mgr

    server = ApiServer(**kwargs)
    app = server.get_fast_api_app(allow_origins=["*"], with_ui=True)


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
