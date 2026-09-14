"""Smoke test — verifies that the agent module imports and root_agent is defined.

Following the adk-samples convention (every recipe has test_runnability.py).
"""

from unittest.mock import patch


def test_root_agent_is_defined():
    with patch("google.auth.default", return_value=(None, "test-project")):
        from app.agent import app, root_agent

        assert root_agent is not None
        assert root_agent.name == "ssc_coordinator"
        assert app is not None
        assert app.name == "app"
