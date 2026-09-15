"""Shared configuration — single source of truth for settings used across agents.

Avoids duplicating os.environ.get() calls for MODEL, WORKSPACE_PATH, etc.
in every agent module. All values are read at import time from env vars.
"""

from __future__ import annotations

import os
import pathlib

from google.adk.tools.bash_tool import BashToolPolicy, ExecuteBashTool

MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-2.5-flash")
SAFETY_JUDGE_MODEL_NAME = os.environ.get("SAFETY_JUDGE_MODEL", "gemini-2.5-flash")


def _build_model(model_name: str):
    """Build a model instance — MaaSLiteLlm if MAAS_BASE_URL is set, else plain string.

    Plain string works with Gemini API (GEMINI_API_KEY) and Vertex AI.
    MaaSLiteLlm works with Red Hat MaaS (OpenAI-compatible Gemini proxy).
    """
    if os.environ.get("MAAS_BASE_URL"):
        try:
            import rh_maas_litellm

            if not getattr(_build_model, "_bootstrapped", False):
                rh_maas_litellm.bootstrap()
                _build_model._bootstrapped = True
            return rh_maas_litellm.get_maas_model(model_name)
        except ImportError:
            raise ImportError(
                "MAAS_BASE_URL is set but rh-maas-litellm is not installed. "
                "Install with: pip install rh-maas-litellm"
            )
    return model_name


MODEL = _build_model(MODEL_NAME)
SAFETY_JUDGE_MODEL = _build_model(SAFETY_JUDGE_MODEL_NAME)
WORKSPACE_PATH = os.environ.get("WORKSPACE_PATH", "/workspace/source")
BASE_BRANCH = os.environ.get("SCM_BASE_BRANCH", "main")
SKILLS_DIR = pathlib.Path(__file__).resolve().parent.parent / "skills"

# --- EvalHub settings ---
EVALHUB_URL = os.environ.get("EVALHUB_URL", "")
EVALHUB_TENANT = os.environ.get("EVALHUB_TENANT", "redhat-ods-applications")
EVALHUB_TOKEN = os.environ.get("EVALHUB_TOKEN", "")
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "")
MLFLOW_EXPERIMENT_NAME = os.environ.get("MLFLOW_EXPERIMENT_NAME", "lw-agents")
MLFLOW_WORKSPACE = os.environ.get(
    "MLFLOW_WORKSPACE", os.environ.get("MLFLOW_TRACKING_WORKSPACE", "")
)
MLFLOW_TRACKING_TOKEN = os.environ.get("MLFLOW_TRACKING_TOKEN", "")

BASH_ALLOWED_PREFIXES = (
    "opencode ",
    "mvn ",
    "git ",
    "cat ",
    "ls ",
    "head ",
    "grep ",
    "find ",
)
BASH_TIMEOUT_SECONDS = 300
BASH_MAX_MEMORY_BYTES = 1024 * 1024 * 1024


def build_bash_tool(workspace: str | None = None) -> ExecuteBashTool:
    """Build an ExecuteBashTool with the standard policy.

    Args:
        workspace: Override workspace path. Falls back to WORKSPACE_PATH.
    """
    return ExecuteBashTool(
        workspace=workspace or WORKSPACE_PATH,
        policy=BashToolPolicy(
            allowed_command_prefixes=BASH_ALLOWED_PREFIXES,
            timeout_seconds=BASH_TIMEOUT_SECONDS,
            max_memory_bytes=BASH_MAX_MEMORY_BYTES,
        ),
    )
