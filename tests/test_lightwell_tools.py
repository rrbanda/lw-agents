"""Unit tests for lightwell_tools — no network calls, all HTTP mocked."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers: sample OSV data matching real Lightwell OSV format
# ---------------------------------------------------------------------------

SAMPLE_OSV = {
    "id": "LW-DEMO-0002",
    "summary": "CVE-2023-51074 fix for commons-lang3",
    "details": "Security-only backport of CVE-2023-51074 fix.",
    "modified": "2026-07-27T00:00:00Z",
    "affected": [
        {
            "package": {
                "ecosystem": "Maven",
                "name": "org.apache.commons:commons-lang3",
            },
            "ranges": [
                {
                    "type": "ECOSYSTEM",
                    "events": [
                        {"introduced": "3.14.0"},
                        {"fixed": "3.14.0.rhlw-00001"},
                    ],
                }
            ],
            "versions": ["3.14.0"],
        }
    ],
}

SAMPLE_MANIFEST = (
    "LW-DEMO-0001.json,sha256:abc123,1234\n"
    "LW-DEMO-0002.json,sha256:def456,5678\n"
    "PULP_MANIFEST,sha256:000,0\n"
)


# ---------------------------------------------------------------------------
# Pure function tests — no mocking needed
# ---------------------------------------------------------------------------


class TestIsLightwellVersion:
    def test_java_rhlw(self):
        from app.tools.lightwell_tools import _is_lightwell_version

        assert _is_lightwell_version("3.14.0.rhlw-00001") is True

    def test_python_rhlw(self):
        from app.tools.lightwell_tools import _is_lightwell_version

        assert _is_lightwell_version("1.0.0+rhlw.00001") is True

    def test_upstream_version(self):
        from app.tools.lightwell_tools import _is_lightwell_version

        assert _is_lightwell_version("3.18.0") is False

    def test_empty(self):
        from app.tools.lightwell_tools import _is_lightwell_version

        assert _is_lightwell_version("") is False

    def test_predisclosure(self):
        from app.tools.lightwell_tools import _is_lightwell_version

        assert _is_lightwell_version("5.3.17.rhlw-00001-n0001") is True


class TestIsLightwellAdvisoryId:
    def test_production_id(self):
        from app.tools.lightwell_tools import _is_lightwell_advisory_id

        assert _is_lightwell_advisory_id("RHLW-2024-0001") is True

    def test_demo_id(self):
        from app.tools.lightwell_tools import _is_lightwell_advisory_id

        assert _is_lightwell_advisory_id("LW-DEMO-0002") is True

    def test_cve_id(self):
        from app.tools.lightwell_tools import _is_lightwell_advisory_id

        assert _is_lightwell_advisory_id("CVE-2024-1234") is False

    def test_empty(self):
        from app.tools.lightwell_tools import _is_lightwell_advisory_id

        assert _is_lightwell_advisory_id("") is False

    def test_ghsa(self):
        from app.tools.lightwell_tools import _is_lightwell_advisory_id

        assert _is_lightwell_advisory_id("GHSA-abcd-1234-wxyz") is False


class TestParseLightwellOsv:
    def test_extracts_fixed_version(self):
        from app.tools.lightwell_tools import _parse_lightwell_osv

        result = _parse_lightwell_osv("LW-DEMO-0002", SAMPLE_OSV)
        assert result["status"] == "ok"
        assert result["fixed_version"] == "3.14.0.rhlw-00001"
        assert result["fixed_package"] == "org.apache.commons:commons-lang3"
        assert result["fixed_coordinate"] == "org.apache.commons:commons-lang3:3.14.0.rhlw-00001"

    def test_extracts_advisory_id(self):
        from app.tools.lightwell_tools import _parse_lightwell_osv

        result = _parse_lightwell_osv("LW-DEMO-0002", SAMPLE_OSV)
        assert result["advisory_id"] == "LW-DEMO-0002"
        assert result["source"] == "lightwell-osv"

    def test_extracts_affected_packages(self):
        from app.tools.lightwell_tools import _parse_lightwell_osv

        result = _parse_lightwell_osv("LW-DEMO-0002", SAMPLE_OSV)
        assert len(result["affected_packages"]) == 1
        assert result["affected_packages"][0]["name"] == "org.apache.commons:commons-lang3"
        assert result["affected_packages"][0]["ecosystem"] == "Maven"

    def test_extracts_metadata(self):
        from app.tools.lightwell_tools import _parse_lightwell_osv

        result = _parse_lightwell_osv("LW-DEMO-0002", SAMPLE_OSV)
        assert result["summary"] == "CVE-2023-51074 fix for commons-lang3"
        assert result["modified"] == "2026-07-27T00:00:00Z"

    def test_empty_affected(self):
        from app.tools.lightwell_tools import _parse_lightwell_osv

        data = {"id": "LW-DEMO-9999", "affected": []}
        result = _parse_lightwell_osv("LW-DEMO-9999", data)
        assert result["status"] == "ok"
        assert result["fixed_versions"] == []
        assert "fixed_coordinate" not in result

    def test_no_fixed_event(self):
        from app.tools.lightwell_tools import _parse_lightwell_osv

        data = {
            "id": "LW-DEMO-9999",
            "affected": [
                {
                    "package": {"ecosystem": "Maven", "name": "com.example:lib"},
                    "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "1.0.0"}]}],
                }
            ],
        }
        result = _parse_lightwell_osv("LW-DEMO-9999", data)
        assert result["fixed_versions"] == []

    def test_multiple_fixed_events(self):
        from app.tools.lightwell_tools import _parse_lightwell_osv

        data = {
            "id": "RHLW-2024-0001",
            "affected": [
                {
                    "package": {"ecosystem": "Maven", "name": "com.example:a"},
                    "ranges": [{"type": "ECOSYSTEM", "events": [{"fixed": "1.0.0.rhlw-00001"}]}],
                },
                {
                    "package": {"ecosystem": "Maven", "name": "com.example:b"},
                    "ranges": [{"type": "ECOSYSTEM", "events": [{"fixed": "2.0.0.rhlw-00001"}]}],
                },
            ],
        }
        result = _parse_lightwell_osv("RHLW-2024-0001", data)
        assert len(result["fixed_versions"]) == 2
        assert result["fixed_version"] == "1.0.0.rhlw-00001"


# ---------------------------------------------------------------------------
# lookup_lightwell_osv — mocked HTTP
# ---------------------------------------------------------------------------


class TestLookupLightwellOsv:
    def test_empty_advisory_id(self):
        from app.tools.lightwell_tools import lookup_lightwell_osv

        result = lookup_lightwell_osv("")
        assert result["status"] == "error"

    def test_whitespace_advisory_id(self):
        from app.tools.lightwell_tools import lookup_lightwell_osv

        result = lookup_lightwell_osv("   ")
        assert result["status"] == "error"

    @patch("app.tools.lightwell_tools.cache_get", return_value=None)
    @patch("app.tools.lightwell_tools.cache_put")
    @patch("app.tools.lightwell_tools.fetch_json")
    def test_successful_lookup(self, mock_fetch, mock_cache_put, mock_cache_get):
        from app.tools.lightwell_tools import lookup_lightwell_osv

        mock_fetch.return_value = (200, SAMPLE_OSV)
        result = lookup_lightwell_osv("LW-DEMO-0002")

        assert result["status"] == "ok"
        assert result["fixed_version"] == "3.14.0.rhlw-00001"
        assert result["source"] == "lightwell-osv"
        mock_cache_put.assert_called_once()

    @patch("app.tools.lightwell_tools.cache_get", return_value=None)
    @patch("app.tools.lightwell_tools.fetch_json")
    def test_404_not_found(self, mock_fetch, mock_cache_get):
        from app.tools.lightwell_tools import lookup_lightwell_osv

        mock_fetch.return_value = (404, None)
        result = lookup_lightwell_osv("LW-DEMO-9999")

        assert result["status"] == "not_found"
        assert "LW-DEMO-9999" in result["error"]

    @patch("app.tools.lightwell_tools.cache_get", return_value=None)
    @patch("app.tools.lightwell_tools.fetch_json")
    def test_401_auth_required(self, mock_fetch, mock_cache_get):
        from app.tools.lightwell_tools import lookup_lightwell_osv

        mock_fetch.return_value = (401, None)
        result = lookup_lightwell_osv("RHLW-2024-0001")

        assert result["status"] == "auth_required"
        assert "LIGHTWELL_USERNAME" in result["error"]

    @patch("app.tools.lightwell_tools.cache_get")
    def test_cache_hit(self, mock_cache_get):
        from app.tools.lightwell_tools import lookup_lightwell_osv

        cached_result = {
            "status": "ok",
            "advisory_id": "LW-DEMO-0002",
            "fixed_version": "3.14.0.rhlw-00001",
        }
        mock_cache_get.return_value = json.dumps(cached_result)
        result = lookup_lightwell_osv("LW-DEMO-0002")

        assert result["status"] == "ok"
        assert result["fixed_version"] == "3.14.0.rhlw-00001"

    @patch("app.tools.lightwell_tools.cache_get", return_value=None)
    @patch("app.tools.lightwell_tools.fetch_json")
    def test_non_dict_response(self, mock_fetch, mock_cache_get):
        from app.tools.lightwell_tools import lookup_lightwell_osv

        mock_fetch.return_value = (200, [1, 2, 3])
        result = lookup_lightwell_osv("LW-DEMO-0002")

        assert result["status"] == "error"
        assert "Unexpected" in result["error"]


# ---------------------------------------------------------------------------
# list_lightwell_advisories — mocked HTTP
# ---------------------------------------------------------------------------


class TestListLightwellAdvisories:
    @patch("app.tools.lightwell_tools.cache_get", return_value=None)
    @patch("app.tools.lightwell_tools.cache_put")
    @patch("app.tools.lightwell_tools.fetch_text")
    def test_successful_manifest(self, mock_fetch, mock_cache_put, mock_cache_get):
        from app.tools.lightwell_tools import list_lightwell_advisories

        mock_fetch.return_value = (200, SAMPLE_MANIFEST)
        result = list_lightwell_advisories()

        assert result["status"] == "ok"
        assert result["count"] == 2
        ids = [a["advisory_id"] for a in result["advisories"]]
        assert "LW-DEMO-0001" in ids
        assert "LW-DEMO-0002" in ids
        assert "PULP_MANIFEST" not in ids

    @patch("app.tools.lightwell_tools.cache_get", return_value=None)
    @patch("app.tools.lightwell_tools.fetch_text")
    def test_401_auth_required(self, mock_fetch, mock_cache_get):
        from app.tools.lightwell_tools import list_lightwell_advisories

        mock_fetch.return_value = (401, None)
        result = list_lightwell_advisories()

        assert result["status"] == "auth_required"

    @patch("app.tools.lightwell_tools.cache_get", return_value=None)
    @patch("app.tools.lightwell_tools.fetch_text")
    def test_404_not_found(self, mock_fetch, mock_cache_get):
        from app.tools.lightwell_tools import list_lightwell_advisories

        mock_fetch.return_value = (404, None)
        result = list_lightwell_advisories()

        assert result["status"] == "not_found"

    @patch("app.tools.lightwell_tools.cache_get", return_value=None)
    @patch("app.tools.lightwell_tools.cache_put")
    @patch("app.tools.lightwell_tools.fetch_text")
    def test_empty_manifest(self, mock_fetch, mock_cache_put, mock_cache_get):
        from app.tools.lightwell_tools import list_lightwell_advisories

        mock_fetch.return_value = (200, "")
        result = list_lightwell_advisories()

        assert result["status"] == "ok"
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# check_lightwell_version_exists — mocked HTTP
# ---------------------------------------------------------------------------


class TestCheckLightwellVersionExists:
    @patch("app.tools.lightwell_tools._auth_headers", return_value={})
    @patch("app.tools.lightwell_tools.head_check")
    def test_version_exists_no_auth(self, mock_head, mock_auth):
        from app.tools.lightwell_tools import check_lightwell_version_exists

        mock_head.return_value = (200, True)
        result = check_lightwell_version_exists(
            "org.apache.commons", "commons-lang3", "3.14.0.rhlw-00001"
        )

        assert result["exists"] is True
        assert result["repository"] == "lightwell"
        assert result["status"] == "checked"
        assert "commons-lang3" in result["checked_url"]
        assert "3.14.0.rhlw-00001" in result["checked_url"]

    @patch("app.tools.lightwell_tools._auth_headers", return_value={})
    @patch("app.tools.lightwell_tools.head_check")
    def test_version_not_found(self, mock_head, mock_auth):
        from app.tools.lightwell_tools import check_lightwell_version_exists

        mock_head.return_value = (404, False)
        result = check_lightwell_version_exists(
            "org.apache.commons", "commons-lang3", "3.14.0.rhlw-99999"
        )

        assert result["exists"] is False
        assert result["status"] == "checked"

    @patch(
        "app.tools.lightwell_tools._auth_headers",
        return_value={"Authorization": "Basic dGVzdDp0b2tlbg=="},
    )
    def test_version_exists_with_auth(self, mock_auth):
        """When auth headers are present, uses httpx.Client directly."""
        from unittest.mock import MagicMock

        from app.tools.lightwell_tools import check_lightwell_version_exists

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.head.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client):
            result = check_lightwell_version_exists(
                "org.apache.commons", "commons-lang3", "3.14.0.rhlw-00001"
            )

            assert result["exists"] is True
            assert result["repository"] == "lightwell"
            mock_client.close.assert_called_once()

    def test_url_construction(self):
        from app.tools.lightwell_tools import check_lightwell_version_exists

        with patch("app.tools.lightwell_tools._auth_headers", return_value={}), \
             patch("app.tools.lightwell_tools.head_check", return_value=(404, False)):
            result = check_lightwell_version_exists(
                "org.apache.commons", "commons-lang3", "3.14.0.rhlw-00001"
            )
            assert "org/apache/commons/commons-lang3/3.14.0.rhlw-00001" in result["checked_url"]


# ---------------------------------------------------------------------------
# check_version_exists_smart — routing logic
# ---------------------------------------------------------------------------


class TestCheckVersionExistsSmart:
    @patch("app.tools.lightwell_tools.check_lightwell_version_exists")
    def test_routes_rhlw_to_lightwell(self, mock_lw_check):
        from app.tools.lightwell_tools import check_version_exists_smart

        mock_lw_check.return_value = {"exists": True, "repository": "lightwell"}
        result = check_version_exists_smart(
            "org.apache.commons", "commons-lang3", "3.14.0.rhlw-00001"
        )

        mock_lw_check.assert_called_once_with(
            "org.apache.commons", "commons-lang3", "3.14.0.rhlw-00001"
        )
        assert result["repository"] == "lightwell"

    @patch("app.tools.lightwell_tools.check_lightwell_version_exists")
    def test_routes_python_rhlw_to_lightwell(self, mock_lw_check):
        from app.tools.lightwell_tools import check_version_exists_smart

        mock_lw_check.return_value = {"exists": True, "repository": "lightwell"}
        check_version_exists_smart("some.pkg", "lib", "1.0.0+rhlw.00001")

        mock_lw_check.assert_called_once()

    @patch("app.tools.cve_tools.head_check")
    def test_routes_upstream_to_central(self, mock_head):
        from app.tools.lightwell_tools import check_version_exists_smart

        mock_head.return_value = (200, True)
        result = check_version_exists_smart(
            "org.apache.commons", "commons-lang3", "3.18.0"
        )

        assert result["exists"] is True
        assert "repo1.maven.org" in result.get("checked_url", "")


# ---------------------------------------------------------------------------
# Auth headers
# ---------------------------------------------------------------------------


class TestAuthHeaders:
    def test_no_env_vars(self):
        from app.tools.lightwell_tools import _auth_headers

        with patch.dict(os.environ, {}, clear=True):
            headers = _auth_headers()
            assert headers == {}

    def test_with_env_vars(self):
        from app.tools.lightwell_tools import _auth_headers

        env = {"LIGHTWELL_USERNAME": "12345|sa", "LIGHTWELL_TOKEN": "secret"}
        with patch.dict(os.environ, env):
            headers = _auth_headers()
            assert "Authorization" in headers
            assert headers["Authorization"].startswith("Basic ")

    def test_partial_env_vars(self):
        from app.tools.lightwell_tools import _auth_headers

        with patch.dict(os.environ, {"LIGHTWELL_USERNAME": "12345|sa", "LIGHTWELL_TOKEN": ""}):
            headers = _auth_headers()
            assert headers == {}
