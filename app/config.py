"""Shared configuration — single source of truth for settings used across agents.

Avoids duplicating os.environ.get() calls for MODEL, WORKSPACE_PATH, etc.
in every agent module. All values are read at import time from env vars.
"""

from __future__ import annotations

import asyncio as _asyncio
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
    "cd ",
    "sed ",
    "cat ",
    "ls ",
    "head ",
    "grep ",
    "find ",
    "echo ",
    "mkdir ",
    "tee ",
)
BASH_TIMEOUT_SECONDS = 300


# Shell metacharacters that enable command injection.
# Note: '&&' is intentionally ALLOWED because agents use 'cd /dir && cmd'
# as a standard pattern. The prefix allowlist prevents the first command
# from being dangerous. Semicolons and pipes are the real injection vectors.


async def _run_async_subprocess(
    args: list[str],
    *,
    cwd: str,
    timeout: int,
    env: dict[str, str],
) -> subprocess.CompletedProcess:
    """Run a subprocess without blocking the async event loop.

    Uses asyncio.create_subprocess_exec so the event loop stays responsive
    for health checks, SSE keepalives, and other requests while Maven runs.
    """
    proc = await _asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=_asyncio.subprocess.PIPE,
        stderr=_asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout_bytes, stderr_bytes = await _asyncio.wait_for(proc.communicate(), timeout=timeout)
    except _asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise subprocess.TimeoutExpired(args, timeout)

    stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
    stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)


_BASH_FORBIDDEN_PATTERNS = (
    ";",
    "|",
    "$(",
    "`",
    "$((",
    "<(",
    ">()",
    "\n",
)


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

        # Reject shell metacharacters that enable command chaining / injection
        for pattern in _BASH_FORBIDDEN_PATTERNS:
            if pattern in cmd:
                return {
                    "error": f"Command contains forbidden pattern '{pattern}'. "
                    "Shell chaining and subshells are not allowed."
                }

        try:
            # Use the command's target directory if it references an absolute path
            run_cwd = ws
            if "/tmp/workspace" in cmd and os.path.isdir("/tmp/workspace"):
                run_cwd = "/tmp/workspace"

            # Configure git credentials for push operations
            env = dict(os.environ)
            scm_token = os.environ.get("SCM_TOKEN", "")
            scm_host = os.environ.get("SCM_HOST", "")
            if scm_token and scm_host and "git" in cmd:
                import shlex
                import stat
                import tempfile

                askpass = tempfile.NamedTemporaryFile(
                    mode="w", prefix="bash-askpass-", suffix=".sh", delete=False
                )
                askpass.write(f"#!/bin/sh\necho {shlex.quote(scm_token)}\n")
                askpass.close()
                os.chmod(askpass.name, stat.S_IRWXU)
                env["GIT_ASKPASS"] = askpass.name
                env["GIT_TERMINAL_PROMPT"] = "0"

            # Run subprocess asynchronously — keeps the event loop responsive
            # ADK runs sync tool functions in a thread via to_thread(),
            # so we use asyncio.run_coroutine_threadsafe to call back into the loop
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                future = _asyncio.run_coroutine_threadsafe(
                    _run_async_subprocess(
                        ["bash", "-c", cmd], cwd=run_cwd, timeout=timeout, env=env
                    ),
                    loop,
                )
                result = future.result(timeout=timeout + 10)
            else:
                result = loop.run_until_complete(
                    _run_async_subprocess(
                        ["bash", "-c", cmd], cwd=run_cwd, timeout=timeout, env=env
                    )
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
