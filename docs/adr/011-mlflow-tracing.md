# ADR 011: MLflow Tracing via OpenTelemetry

## Status

Accepted

## Context

The lw-agents system runs multi-agent workflows involving LLM calls, tool executions, and agent delegations. Without observability, it is difficult to:

- Debug why an agent made a particular decision
- Identify latency bottlenecks across the agent pipeline
- Track token usage and cost per run
- Correlate agent behaviour changes with model updates

RHOAI 3.5 provides an MLflow instance with an OTLP `/v1/traces` endpoint that accepts OpenTelemetry spans. Google ADK natively emits OTel spans for agent runs and tool calls. LiteLLM (used by ADK for inference) can auto-log LLM call details via `mlflow.litellm.autolog()`.

## Decision

Implement MLflow tracing using two complementary layers:

1. **OpenTelemetry TracerProvider** with an OTLP HTTP exporter targeting the MLflow `/v1/traces` endpoint — captures ADK's native agent/tool spans
2. **`mlflow.litellm.autolog()`** — captures LLM request/response spans with token counts and latencies

Tracing is:
- **Opt-in**: activated only when `MLFLOW_TRACKING_URI` is set
- **Gracefully degrading**: if the server is unreachable or dependencies are missing, the agent starts normally without tracing
- **Zero-impact on agent code**: existing agents get full tracing without any modifications

Bootstrap happens in `app/__init__.py` before any ADK imports, ensuring the TracerProvider is set before ADK starts emitting spans.

## Consequences

### Positive

- Full-stack visibility: every LLM call, tool execution, and agent delegation is captured
- Cost tracking via token count spans
- Latency profiling for pipeline optimization
- No changes required to any existing agent module
- Compatible with RHOAI 3.5 MLflow's workspace-scoped experiment tracking

### Negative

- Additional optional dependencies (`mlflow`, `opentelemetry-*`)
- Small latency overhead for span export (mitigated by async logging)
- Health check adds up to 5 seconds to startup when MLflow is configured but slow

### Risks

- RHOAI MLflow workspace API may change between releases
- `SimpleSpanProcessor` (synchronous) is still in use as of this writing and
  should be replaced with `BatchSpanProcessor` before high-throughput production
  deployment to avoid blocking the agent on span export

## References

- [agentic-starter-kits tracing.md](https://github.com/red-hat-data-services/agentic-starter-kits/blob/main/tracing.md)
- [mortgage repo tracing.py](https://github.com/rrbanda/mortgage/blob/main/small_business_loan_agent/tracing.py)
- [MLflow OTel Traces](https://mlflow.org/docs/latest/tracing/index.html)
