"""Validation Agent — multi-persona adversarial review of remediation fixes.

Inspired by VVAH's S11 validation system: three read-only personas
independently evaluate fixes against weighted gates, with deterministic
consensus synthesis. No persona can write files or run commands.

Architecture: SequentialAgent runs two personas in sequence, then a
deterministic scoring function produces the final verdict.
"""

from __future__ import annotations

import os
import pathlib

from google.adk.agents import BaseAgent, LlmAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from typing import AsyncGenerator

from app.tools.cve_tools import (
    lookup_cve_detail,
    parse_maven_purl,
)

MODEL = os.environ.get("MODEL_NAME", "gemini-2.5-flash")
SKILLS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "skills"

# Gate weights (from VVAH scoring engine)
GATE_WEIGHTS = {
    "root_cause": 0.43,
    "instance_coverage": 0.2467,
    "no_new_vulnerabilities": 0.1867,
    "security_best_practices": 0.1366,
}

DECISION_THRESHOLDS = {
    "fixed": 0.80,
    "partially_fixed": 0.50,
}


def _create_security_architect() -> LlmAgent:
    """Read-only persona: evaluates fix design, data flow, and controls."""
    skills = [load_skill_from_dir(SKILLS_DIR / "validation-architect")]
    skill_toolset = SkillToolset(skills=skills)

    return LlmAgent(
        name="security_architect",
        model=MODEL,
        instruction=(
            "You are a security architect reviewing a vulnerability fix. "
            "Load the validation-architect skill and follow its process. "
            "Evaluate the fix against all four gates: root_cause, "
            "instance_coverage, no_new_vulnerabilities, security_best_practices. "
            "For each gate, report: status (pass/partial/fail), summary, and evidence."
        ),
        description="Evaluates fix design, data flow paths, and security controls.",
        tools=[skill_toolset, lookup_cve_detail, parse_maven_purl],
        output_key="architect_report",
    )


def _create_penetration_tester() -> LlmAgent:
    """Read-only persona: evaluates exploitability after the fix."""
    skills = [load_skill_from_dir(SKILLS_DIR / "validation-pentester")]
    skill_toolset = SkillToolset(skills=skills)

    return LlmAgent(
        name="penetration_tester",
        model=MODEL,
        instruction=(
            "You are a penetration tester reviewing a vulnerability fix. "
            "Load the validation-pentester skill and follow its process. "
            "Try to find ways the fix can be bypassed. Evaluate the fix "
            "against all four gates: root_cause, instance_coverage, "
            "no_new_vulnerabilities, security_best_practices. "
            "For each gate, report: status (pass/partial/fail), summary, and evidence."
        ),
        description="Evaluates real-world exploitability of the fix.",
        tools=[skill_toolset, lookup_cve_detail, parse_maven_purl],
        output_key="pentester_report",
    )


class DeterministicScoring(BaseAgent):
    """Deterministic consensus scoring — no LLM, pure computation.

    Reads architect_report and pentester_report from session state,
    applies VVAH-style weighted scoring with conservative consensus.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        architect = ctx.session.state.get("architect_report", "")
        pentester = ctx.session.state.get("pentester_report", "")

        # Parse gate statuses from persona reports
        gates = {}
        for gate_name in GATE_WEIGHTS:
            statuses = []
            for report in [architect, pentester]:
                report_lower = str(report).lower()
                if f"{gate_name}: pass" in report_lower or f"{gate_name}:pass" in report_lower:
                    statuses.append("pass")
                elif f"{gate_name}: partial" in report_lower:
                    statuses.append("partial")
                elif f"{gate_name}: fail" in report_lower:
                    statuses.append("fail")
                else:
                    statuses.append("inconclusive")

            # Conservative consensus (VVAH pattern)
            if len(set(statuses)) == 1 and len(statuses) >= 2:
                gates[gate_name] = {"status": statuses[0], "confidence": "HIGH"}
            else:
                most_conservative = min(statuses, key=lambda s: {"fail": 0, "partial": 1, "inconclusive": 2, "pass": 3}.get(s, 2))
                gates[gate_name] = {"status": most_conservative, "confidence": "FLAGGED"}

        # Compute weighted score
        score_map = {"pass": 1.0, "partial": 0.5, "fail": 0.0, "inconclusive": 0.0}
        total_score = sum(
            GATE_WEIGHTS[gate] * score_map.get(gates[gate]["status"], 0.0)
            for gate in GATE_WEIGHTS
        )

        # Decision thresholds
        if total_score >= DECISION_THRESHOLDS["fixed"]:
            decision = "FIXED"
        elif total_score >= DECISION_THRESHOLDS["partially_fixed"]:
            decision = "PARTIALLY_FIXED"
        else:
            decision = "NOT_FIXED"

        # Critical gate cap (VVAH pattern): if root_cause is not PASS,
        # cap the decision down one level
        if gates.get("root_cause", {}).get("status") != "pass":
            if decision == "FIXED":
                decision = "PARTIALLY_FIXED"

        result = {
            "decision": decision,
            "score": round(total_score, 3),
            "gates": gates,
            "personas_consulted": ["security_architect", "penetration_tester"],
        }

        ctx.session.state["validation_result"] = result

        yield Event(
            author=self.name,
            content=None,
        )


def create_validation_agent() -> SequentialAgent:
    """Factory: builds the validation pipeline with two personas + scoring."""
    return SequentialAgent(
        name="fix_validation",
        description=(
            "Validates remediation fixes using two adversarial personas "
            "(security architect + penetration tester) with deterministic "
            "weighted scoring. Read-only — no write tools."
        ),
        sub_agents=[
            _create_security_architect(),
            _create_penetration_tester(),
            DeterministicScoring(name="deterministic_scoring"),
        ],
    )
