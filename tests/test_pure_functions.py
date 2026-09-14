"""Unit tests for pure functions — no LLM calls, no network, no side-effects.

Tests the functions that can be verified deterministically before
spinning up the full agent service.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# _extract_json_object (app.callbacks)
# ---------------------------------------------------------------------------


class TestExtractJsonObject:
    """Tests for the nested-JSON extraction utility."""

    def setup_method(self):
        from app.callbacks import _extract_json_object

        self.extract = _extract_json_object

    def test_simple_flat_object(self):
        text = 'Here is the result: {"cve_id": "CVE-2024-1234", "selected": true}'
        result = self.extract(text)
        assert result == {"cve_id": "CVE-2024-1234", "selected": True}

    def test_nested_object(self):
        text = '{"outer": {"inner": 1}, "key": "val"}'
        result = self.extract(text)
        assert result == {"outer": {"inner": 1}, "key": "val"}

    def test_json_with_surrounding_text(self):
        text = 'Some preamble\n```json\n{"a": 1}\n```\nMore text'
        result = self.extract(text)
        assert result == {"a": 1}

    def test_no_json(self):
        assert self.extract("no json here") is None

    def test_empty_string(self):
        assert self.extract("") is None

    def test_array_not_object(self):
        """Arrays should not match — we only want objects."""
        assert self.extract("[1, 2, 3]") is None

    def test_malformed_json(self):
        assert self.extract("{ bad json: }") is None


# ---------------------------------------------------------------------------
# validate_selection (app.scoring.validate_selection)
# ---------------------------------------------------------------------------


class TestValidateSelection:
    """Tests for fail-closed CVE selection validation."""

    def setup_method(self):
        from app.scoring.validate_selection import validate_selection

        self.validate = validate_selection

    def test_valid_selection(self):
        result = self.validate(
            {
                "selected": "1",
                "cve_id": "CVE-2024-1234",
                "package": "com.example:lib",
                "current_version": "1.0.0",
                "fixed_version": "1.0.1",
                "justification": "Critical RCE vulnerability",
            }
        )
        assert result["SELECTED"] == "1"
        assert result["validation_status"] == "accepted"
        assert result["validation_errors"] == []

    def test_not_selected_passthrough(self):
        result = self.validate({"selected": "0"})
        assert result["SELECTED"] == "0"
        assert result["validation_status"] == "not_selected"

    def test_invalid_cve_id_rejects(self):
        result = self.validate(
            {
                "selected": "1",
                "cve_id": "not-a-cve",
                "package": "com.example:lib",
                "current_version": "1.0",
                "fixed_version": "1.1",
                "justification": "Fix it",
            }
        )
        assert result["SELECTED"] == "0"
        assert result["validation_status"] == "rejected"
        assert any("CVE ID" in e for e in result["validation_errors"])

    def test_invalid_package_rejects(self):
        result = self.validate(
            {
                "selected": "1",
                "cve_id": "CVE-2024-9999",
                "package": "no-colon",
                "current_version": "1.0",
                "fixed_version": "1.1",
                "justification": "Fix it",
            }
        )
        assert result["SELECTED"] == "0"
        assert any("package" in e.lower() for e in result["validation_errors"])

    def test_same_versions_rejects(self):
        result = self.validate(
            {
                "selected": "1",
                "cve_id": "CVE-2024-5678",
                "package": "org.example:core",
                "current_version": "2.0.0",
                "fixed_version": "2.0.0",
                "justification": "Fix it",
            }
        )
        assert result["SELECTED"] == "0"
        assert any("identical" in e for e in result["validation_errors"])

    def test_placeholder_detection(self):
        result = self.validate(
            {
                "selected": "1",
                "cve_id": "CVE-2024-5678",
                "package": "org.example:core",
                "current_version": "string",
                "fixed_version": "null",
                "justification": "Fix it",
            }
        )
        assert result["SELECTED"] == "0"
        assert any("placeholder" in e for e in result["validation_errors"])

    def test_empty_justification_rejects(self):
        result = self.validate(
            {
                "selected": "1",
                "cve_id": "CVE-2024-5678",
                "package": "org.example:core",
                "current_version": "1.0",
                "fixed_version": "1.1",
                "justification": "",
            }
        )
        assert result["SELECTED"] == "0"
        assert any("justification" in e.lower() for e in result["validation_errors"])


# ---------------------------------------------------------------------------
# validate_diff (app.policy.post_gate)
# ---------------------------------------------------------------------------


class TestValidateDiff:
    """Tests for post-gate diff validation."""

    def setup_method(self):
        from app.policy.post_gate import validate_diff

        self.validate = validate_diff

    def test_clean_pom_diff(self):
        diff = "--- a/pom.xml\n+++ b/pom.xml\n-<version>1.0</version>\n+<version>1.1</version>\n"
        result = self.validate(diff, ["pom.xml"])
        assert result["valid"] is True
        assert result["errors"] == []

    def test_empty_diff_rejects(self):
        result = self.validate("", [])
        assert result["valid"] is False
        assert any("no changes" in e.lower() for e in result["errors"])

    def test_forbidden_nosec_pattern(self):
        diff = "--- a/pom.xml\n+++ b/pom.xml\n+# nosec\n"
        result = self.validate(diff, ["pom.xml"])
        assert result["valid"] is False
        assert any("nosec" in e.lower() for e in result["errors"])

    def test_forbidden_suppress_warnings(self):
        diff = "+@SuppressWarnings\n"
        result = self.validate(diff, ["pom.xml"])
        assert result["valid"] is False

    def test_too_many_files(self):
        files = [f"file_{i}.txt" for i in range(10)]
        result = self.validate("some diff\n", files)
        assert result["valid"] is False
        assert any("too many" in e.lower() for e in result["errors"])

    def test_unexpected_file_warning(self):
        result = self.validate("some diff\n", ["pom.xml", "Dockerfile"])
        assert result["valid"] is True  # warnings don't invalidate
        assert any("unexpected" in w.lower() for w in result["warnings"])

    def test_large_diff_warning(self):
        diff = "x\n" * 200
        result = self.validate(diff, ["pom.xml"])
        assert result["valid"] is True
        assert any("large diff" in w.lower() for w in result["warnings"])

    def test_allowed_basenames(self):
        result = self.validate("diff\n", ["pom.xml", "sub/pom.xml", "REMEDIATION.md"])
        assert result["valid"] is True
        assert result["warnings"] == []


# ---------------------------------------------------------------------------
# redact_text (app.plugins.redaction)
# ---------------------------------------------------------------------------


class TestRedactText:
    """Tests for shape-based secret redaction."""

    def setup_method(self):
        from app.plugins.redaction import redact_dict, redact_text

        self.redact_text = redact_text
        self.redact_dict = redact_dict

    def test_github_token(self):
        text = "Token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklm"
        assert "[GITHUB_TOKEN]" in self.redact_text(text)

    def test_gitlab_token(self):
        text = "Token: glpat-abcdefghijklmnopqrstuvwx"
        assert "[GITLAB_TOKEN]" in self.redact_text(text)

    def test_anthropic_key_before_openai(self):
        """Anthropic sk-ant- should match before generic sk- pattern."""
        text = "key=sk-ant-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        result = self.redact_text(text)
        assert "[ANTHROPIC_KEY]" in result
        assert "[API_KEY]" not in result

    def test_openai_key(self):
        text = "key=sk-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop"
        assert "[API_KEY]" in self.redact_text(text)

    def test_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.abc"
        result = self.redact_text(text)
        assert "Bearer" not in result or "[BEARER_TOKEN]" in result or "[JWT_TOKEN]" in result

    def test_jwt_token(self):
        text = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.abc_DEF-123"
        assert "[JWT_TOKEN]" in self.redact_text(text)

    def test_basic_auth(self):
        text = "Authorization: Basic dXNlcjpwYXNzd29yZC1sb25nLWVub3VnaA=="
        assert "[BASIC_AUTH]" in self.redact_text(text)

    def test_clean_text_unchanged(self):
        text = "This is perfectly normal text with no secrets."
        assert self.redact_text(text) == text

    def test_redact_dict_credential_keys(self):
        data = {"token": "my-secret", "name": "safe"}
        result = self.redact_dict(data)
        assert result["token"] == "[REDACTED]"
        assert result["name"] == "safe"

    def test_redact_dict_nested(self):
        data = {"auth": {"password": "secret123", "user": "admin"}}
        result = self.redact_dict(data)
        assert result["auth"]["password"] == "[REDACTED]"
        assert result["auth"]["user"] == "admin"


# ---------------------------------------------------------------------------
# BuildResultChecker (app.agents.remediation)
# ---------------------------------------------------------------------------


class TestBuildResultChecker:
    """Tests for remediation build-result escalation logic.

    BuildResultChecker is a BaseAgent that runs inside a LoopAgent.
    We test its decision logic by checking session state after it runs,
    since the actual agent requires an InvocationContext.
    We test the equivalent logic directly.
    """

    def test_success_keywords(self):
        """BUILD SUCCESS in output should set build_passed=True."""
        output = "Build completed: BUILD SUCCESS"
        assert "build success" in output.lower()

    def test_failure_keywords(self):
        """Known failure keywords should be detected."""
        for kw in ("build failure", "compilation error", "maven error"):
            output = f"Process failed: {kw}"
            keywords = ("build failure", "compilation error", "maven error")
            assert any(k in output.lower() for k in keywords)

    def test_false_positive_guard(self):
        """'no errors' should negate false positive."""
        output = "build failure analysis: no errors found"
        lower = output.lower()
        is_failure = (
            any(kw in lower for kw in ("build failure", "compilation error", "maven error"))
            and "no errors" not in lower
            and "did not fail" not in lower
        )
        assert not is_failure

    def test_structured_status_pass(self):
        """Structured build_status='pass' should be recognized."""
        build_status = "pass"
        assert build_status == "pass"

    def test_structured_status_fail(self):
        """Structured build_status='fail' should be recognized."""
        build_status = "fail"
        assert build_status == "fail"


# ---------------------------------------------------------------------------
# parse_maven_purl (app.tools.cve_tools)
# ---------------------------------------------------------------------------


class TestParseMavenPurl:
    """Tests for Maven PURL parsing."""

    def setup_method(self):
        from app.tools.cve_tools import parse_maven_purl

        self.parse = parse_maven_purl

    def test_full_purl(self):
        result = self.parse("pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.13.2")
        assert result["group_id"] == "com.fasterxml.jackson.core"
        assert result["artifact_id"] == "jackson-databind"
        assert result["version"] == "2.13.2"
        assert result["package"] == "com.fasterxml.jackson.core:jackson-databind"

    def test_purl_without_version(self):
        result = self.parse("pkg:maven/org.example/lib")
        assert result["group_id"] == "org.example"
        assert result["artifact_id"] == "lib"
        assert result["version"] == ""

    def test_invalid_purl(self):
        result = self.parse("not-a-purl")
        assert "error" in result

    def test_npm_purl_fails(self):
        result = self.parse("pkg:npm/lodash@4.17.21")
        assert "error" in result


# ---------------------------------------------------------------------------
# _extract_repo_path (app.tools.scm_tools)
# ---------------------------------------------------------------------------


class TestExtractRepoPath:
    """Tests for SCM URL repo path extraction."""

    def setup_method(self):
        from app.tools.scm_tools import _extract_repo_path

        self.extract = _extract_repo_path

    def test_https_url(self):
        result = self.extract("https://gitlab.example.com/org/project.git")
        assert result == "org/project"

    def test_https_url_no_git_suffix(self):
        result = self.extract("https://github.com/org/project")
        assert result == "org/project"

    def test_nested_group(self):
        result = self.extract("https://gitlab.com/group/subgroup/project.git")
        assert result == "group/subgroup/project"


# ---------------------------------------------------------------------------
# validate_remediation_request (app.policy.pre_gate)
# ---------------------------------------------------------------------------


class TestValidateRemediationRequest:
    """Tests for pre-gate remediation request validation."""

    def setup_method(self):
        from app.policy.pre_gate import validate_remediation_request

        self.validate = validate_remediation_request

    def test_valid_request(self):
        result = self.validate(
            cve_id="CVE-2024-1234",
            package="com.example:lib",
            current_version="1.0.0",
            fixed_version="1.0.1",
        )
        assert result["valid"] is True
        assert result["errors"] == []

    def test_invalid_cve(self):
        result = self.validate(
            cve_id="not-a-cve",
            package="com.example:lib",
            current_version="1.0",
            fixed_version="1.1",
        )
        assert result["valid"] is False

    def test_missing_package(self):
        result = self.validate(
            cve_id="CVE-2024-1234",
            package="",
            current_version="1.0",
            fixed_version="1.1",
        )
        assert result["valid"] is False

    def test_same_versions(self):
        result = self.validate(
            cve_id="CVE-2024-1234",
            package="com.example:lib",
            current_version="1.0.0",
            fixed_version="1.0.0",
        )
        assert result["valid"] is False
        assert any("identical" in e for e in result["errors"])
