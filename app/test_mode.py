"""Test mode infrastructure — Layer 10.1.

Enables safe end-to-end testing against staging infrastructure without
touching production state.

Usage:
    export LW_TEST_MODE=true
    # Routes to staging SCM, uses test CVE data, prevents real PRs.

Individual settings can be overridden via their specific env vars.
"""

from __future__ import annotations

import os

TEST_MODE = os.environ.get("LW_TEST_MODE", "").lower() in ("true", "1", "yes")

TEST_SCM_HOST = "gitlab.example.com"
TEST_WORKSPACE = "/tmp/lw-test-workspace"
PROD_SCM_HOST = ""


def configure_test_mode() -> None:
    """Apply test mode configuration if LW_TEST_MODE is set.

    Sets default values for test infrastructure, but respects any explicit
    overrides already present in the environment.
    """
    if not TEST_MODE:
        return

    os.environ.setdefault("WORKSPACE_PATH", TEST_WORKSPACE)
    os.environ.setdefault("LW_CACHE_TTL_SECONDS", "0")


def get_test_mode_variables() -> dict[str, str]:
    """Return variables to pass test mode to downstream pipelines."""
    if TEST_MODE:
        return {"LW_TEST_MODE": "true"}
    return {}


def is_test_mode() -> bool:
    """Return True if test mode is enabled."""
    return TEST_MODE


configure_test_mode()
