"""MLflow tracing setup for lw-agents.

Follows the agentic-starter-kits ADK template pattern:
https://github.com/red-hat-data-services/agentic-starter-kits/blob/main/tracing.md

Google ADK is Level A (OpenTelemetry variant): ADK natively emits OTel spans
for agent runs, tool calls, and model requests. We configure an OTLP exporter
to forward those spans to the MLflow tracking server.

Enable by setting MLFLOW_TRACKING_URI in the environment.
If the env var is absent or the server is unreachable, the agent starts
normally without tracing.
"""

from __future__ import annotations

import logging
import time
from os import getenv
from typing import Callable, Literal, Optional

logger = logging.getLogger(__name__)

_TRACING_ENABLED: bool = False


def _safe_uri(uri: str) -> str:
    """Strip credentials and query params from a URI for safe logging."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(uri)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _check_mlflow_health(
    tracking_uri: str,
    max_wait: int = 5,
    retry_interval: int = 1,
) -> None:
    """Poll MLflow until reachable or timeout.

    RHOAI MLflow does not expose /health. Instead we probe the
    /v1/traces OTLP endpoint (returns 422 with a validation error
    when alive) or fall back to a root GET (any non-connection-error).
    """
    import httpx

    insecure = getenv("MLFLOW_TRACKING_INSECURE_TLS", "").lower() in (
        "true",
        "1",
        "yes",
    )
    safe = _safe_uri(tracking_uri)
    deadline = time.time() + max_wait

    probe_urls = [
        f"{tracking_uri.rstrip('/')}/health",
        f"{tracking_uri.rstrip('/')}/v1/traces",
    ]

    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise RuntimeError(f"MLflow unreachable after {max_wait}s at {safe}")

        for url in probe_urls:
            try:
                resp = httpx.get(
                    url,
                    timeout=min(5.0, remaining),
                    verify=not insecure,
                    follow_redirects=True,
                )
                if resp.status_code < 500:
                    logger.info(
                        "[Tracing] MLflow reachable at %s (status %d)",
                        safe,
                        resp.status_code,
                    )
                    return
            except httpx.HTTPError:
                pass

        if time.time() + retry_interval > deadline:
            raise RuntimeError(f"MLflow unreachable after {max_wait}s at {safe}")
        time.sleep(retry_interval)


def wrap_func_with_mlflow_trace(
    func: Callable,
    span_type: Literal["tool", "agent"],
    name: Optional[str] = None,
) -> Callable:
    """Wrap a function with an MLflow span. No-op if tracing is disabled.

    Use for custom FunctionTool wrappers that ADK may not auto-trace.
    Most ADK tools and agents are traced automatically via OTel.
    """
    if not _TRACING_ENABLED:
        return func

    import mlflow
    from mlflow.entities import SpanType

    st = SpanType.TOOL if span_type == "tool" else SpanType.AGENT
    return mlflow.trace(span_type=st, name=name)(func)


def is_tracing_enabled() -> bool:
    """Check if tracing is currently active."""
    return _TRACING_ENABLED


def enable_tracing() -> None:
    """Enable MLflow tracing if MLFLOW_TRACKING_URI is set and reachable.

    Behaviour:
    - MLFLOW_TRACKING_URI absent -> tracing skipped, agent starts normally.
    - URI set but server unreachable -> warning logged, agent starts normally.
    - URI set and server healthy -> OTel TracerProvider configured, all ADK
      spans forwarded to MLflow via OTLP.

    This function MUST be called before any ADK components are created
    (i.e. before importing app.agent) so the TracerProvider is set
    before ADK starts emitting spans.
    """
    global _TRACING_ENABLED

    tracking_uri: Optional[str] = getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        logger.info("[Tracing] MLFLOW_TRACKING_URI not set — tracing disabled")
        return

    # --- Fail-fast on missing packages ---
    try:
        import mlflow
        import mlflow.litellm
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "MLFLOW_TRACKING_URI is set but mlflow is not installed. "
            "Install with: uv sync --extra tracing"
        ) from exc

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "MLFLOW_TRACKING_URI is set but opentelemetry-exporter-otlp "
            "is not installed. Install with: uv sync --extra tracing"
        ) from exc

    # --- Health check ---
    try:
        timeout = int(getenv("MLFLOW_HEALTH_CHECK_TIMEOUT", "5"))
    except ValueError:
        timeout = 5

    try:
        _check_mlflow_health(tracking_uri, max_wait=timeout)
    except RuntimeError as exc:
        logger.warning("[Tracing] %s — continuing without tracing", exc)
        return

    safe = _safe_uri(tracking_uri)
    insecure = getenv("MLFLOW_TRACKING_INSECURE_TLS", "").lower() in (
        "true",
        "1",
        "yes",
    )

    try:
        # --- Configure MLflow tracking (for litellm autolog + experiment) ---
        mlflow.set_tracking_uri(tracking_uri)
        experiment_name = getenv("MLFLOW_EXPERIMENT_NAME", "lw-agents")

        # Set experiment — creates it if it doesn't exist
        experiment = mlflow.set_experiment(experiment_name)
        experiment_id = experiment.experiment_id

        mlflow.config.enable_async_logging()

        # --- Layer 1: LiteLLM autolog for LLM call spans ---
        # ADK routes all inference through LiteLLM, so this captures
        # prompts, responses, and token counts as CHAT_MODEL spans.
        mlflow.litellm.autolog()

        # --- Layer 2+3: OTel TracerProvider for ADK agent/tool spans ---
        # ADK natively emits OpenTelemetry spans. We configure an OTLP
        # exporter to forward them to MLflow's /v1/traces endpoint.
        otlp_endpoint = f"{tracking_uri.rstrip('/')}/v1/traces"

        # Build headers for RHOAI MLflow
        headers: dict[str, str] = {}
        if experiment_id:
            headers["x-mlflow-experiment-id"] = experiment_id

        workspace = getenv(
            "MLFLOW_WORKSPACE",
            getenv("MLFLOW_TRACKING_WORKSPACE", ""),
        )
        if workspace:
            headers["X-MLflow-Workspace"] = workspace

        # Auth token for RHOAI
        token = getenv("MLFLOW_TRACKING_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers=headers,
            certificate_file=None,
        )

        # If insecure TLS, patch the exporter session
        if insecure:
            try:
                import urllib3

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except ImportError:
                pass

        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        _TRACING_ENABLED = True
        logger.info(
            "[Tracing] Enabled — MLflow: %s  experiment: %s (id=%s)",
            safe,
            experiment_name,
            experiment_id,
        )

    except Exception as exc:
        logger.warning(
            "[Tracing] Setup failed at %s, continuing without tracing: %s",
            safe,
            exc,
        )
