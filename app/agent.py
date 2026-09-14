"""Root agent + App definition — the entry point ADK expects.

ADK's built-in server (adk api_server) and the scaffolded fast_api_app.py
look for root_agent and app in app/agent.py. This module wires the four
specialist agents under a coordinator, with safety plugin at the Runner level.

Architecture follows the adk-samples patterns:
- Coordinator with sub_agents (from deep-search)
- Safety BasePlugin at Runner (from safety-plugins)
- App with ResumabilityConfig (from long-horizon-harness)
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig

from app.agents.cve_analysis import create_cve_analysis_agent
from app.agents.cve_selection import create_cve_selection_agent
from app.agents.remediation import create_remediation_agent
from app.agents.test_generation import create_test_generation_agent
from app.plugins.safety import SafetyPlugin

MODEL = os.environ.get("MODEL_NAME", "gemini-2.5-flash")


def _build_app() -> App:
    root_agent = LlmAgent(
        name="ssc_coordinator",
        model=MODEL,
        instruction=(
            "You are the Software Supply Chain security agent coordinator. "
            "Based on the user's request, delegate to the appropriate specialist:\n\n"
            "- For CVE **selection** (pick ONE CVE to fix): delegate to cve_selection\n"
            "- For CVE **analysis** (analyze ALL CVEs, open issues): delegate to cve_analysis\n"
            "- For dependency **remediation** (apply a fix, open PR): delegate to remediation\n"
            "- For **test generation** (generate JUnit tests, open PR): delegate to test_generation\n\n"
            "Always delegate — never attempt the task yourself. Pass the full "
            "request context (workspace path, CVE details, etc.) to the specialist."
        ),
        description="Routes software supply chain security tasks to specialist agents.",
        sub_agents=[
            create_cve_selection_agent(),
            create_cve_analysis_agent(),
            create_remediation_agent(),
            create_test_generation_agent(),
        ],
    )

    return App(
        name="app",
        root_agent=root_agent,
        plugins=[SafetyPlugin()],
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


app = _build_app()
root_agent = app.root_agent
