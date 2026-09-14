"""Typed Pydantic contracts for data flowing between agents.

These replace the raw dict[str, Any] / regex extraction approach.
Every agent produces one of these models, and downstream consumers
can validate the data structurally.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class CVEDecision(BaseModel):
    """Output of the CVE selection or analysis agent."""

    selected: bool = False
    cve_id: str = ""
    package: str = Field(default="", description="Maven groupId:artifactId")
    current_version: str = ""
    fixed_version: str = ""
    justification: str = ""
    validation_errors: list[str] = Field(default_factory=list)
    validation_status: str = "pending"

    @field_validator("cve_id")
    @classmethod
    def cve_id_format(cls, v: str) -> str:
        if v and not re.match(r"^CVE-\d{4}-\d{4,}$", v, re.I):
            raise ValueError(f"Invalid CVE ID format: {v}")
        return v

    @field_validator("package")
    @classmethod
    def maven_coordinates(cls, v: str) -> str:
        if v and ":" not in v:
            raise ValueError(f"Package must be groupId:artifactId, got: {v}")
        return v

    @field_validator("fixed_version", "current_version")
    @classmethod
    def version_has_digit(cls, v: str) -> str:
        if v and not re.search(r"\d", v):
            raise ValueError(f"Version must contain a digit, got: {v}")
        return v

    def to_tekton_results(self) -> dict[str, str]:
        """Convert to the 6-field Tekton result contract."""
        return {
            "SELECTED": "1" if self.selected else "0",
            "CVE_ID": self.cve_id,
            "PACKAGE": self.package,
            "CURRENT_VERSION": self.current_version,
            "FIXED_VERSION": self.fixed_version,
            "JUSTIFICATION": self.justification,
        }


class RemediationResult(BaseModel):
    """Output of the remediation agent."""

    success: bool = False
    changed_files: list[str] = Field(default_factory=list)
    diff_content: str = ""
    diff_lines: int = 0
    pr_url: str = ""
    error: str | None = None
    pre_gate_denied: bool = False
    post_gate_rejected: bool = False
    validation_verdict: str | None = None


class ValidationVerdict(BaseModel):
    """Output of the validation agent (deterministic scoring)."""

    decision: str = Field(default="NOT_FIXED", description="FIXED / PARTIALLY_FIXED / NOT_FIXED")
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    gates: dict[str, dict] = Field(default_factory=dict)
    personas_consulted: list[str] = Field(default_factory=list)

    def is_acceptable(self) -> bool:
        """Whether the fix meets the minimum bar for PR submission."""
        return self.decision in ("FIXED", "PARTIALLY_FIXED")
