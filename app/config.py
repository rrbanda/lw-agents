"""Shared configuration — single source of truth for settings used across agents.

Avoids duplicating os.environ.get() calls for MODEL, WORKSPACE_PATH, etc.
in every agent module. All values are read at import time from env vars.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

from google.adk.tools import FunctionTool

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


def build_bash_tool(workspace: str | None = None) -> FunctionTool:
    """Build a bash execution tool WITHOUT confirmation prompts.

    ADK's ExecuteBashTool always requires user confirmation for every command.
    In CI/CD pipelines there is no human to approve. We use BashToolPolicy
    (allowed command prefixes, timeout, memory limit) as the safety guardrail
    instead of per-command confirmation.
    """
    ws = workspace or WORKSPACE_PATH
    # Use /tmp/workspace as fallback if default workspace doesn't exist
    if not os.path.isdir(ws):
        ws = "/tmp/workspace" if os.path.isdir("/tmp/workspace") else "/tmp"
    allowed = BASH_ALLOWED_PREFIXES
    timeout = BASH_TIMEOUT_SECONDS

    def execute_bash(command: str) -> dict:
        """Execute a bash command in the workspace.

        Only commands starting with allowed prefixes are permitted.
        Commands are subject to timeout and memory limits.

        Args:
            command: The bash command to execute.
        """
        if not command or not command.strip():
            return {"error": "Command is required."}

        cmd = command.strip()
        if not any(cmd.startswith(prefix) for prefix in allowed):
            return {"error": f"Command not allowed. Must start with one of: {', '.join(allowed)}"}

        try:
            # Use the command's target directory if it references an absolute path
            run_cwd = ws
            if "/tmp/workspace" in cmd and os.path.isdir("/tmp/workspace"):
                run_cwd = "/tmp/workspace"

            result = subprocess.run(
                ["bash", "-c", cmd],
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.returncode != 0:
                output += f"\nSTDERR: {result.stderr}" if result.stderr else ""
                output += f"\nExit code: {result.returncode}"
            return {"output": output[:50000]}
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    return FunctionTool(execute_bash, require_confirmation=False)
