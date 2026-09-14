"""LW-Agents: ADK-based CVE remediation and test generation agents.

Tracing is enabled BEFORE any agent-related imports so that the
OpenTelemetry TracerProvider is set before ADK emits spans.
"""

from dotenv import load_dotenv

load_dotenv()

# Enable MLflow tracing before agent imports — if MLFLOW_TRACKING_URI is
# set, this configures OTel + LiteLLM autolog.  If not set or the server
# is unreachable, the call is a harmless no-op.
from app.tracing import enable_tracing  # noqa: E402

enable_tracing()
