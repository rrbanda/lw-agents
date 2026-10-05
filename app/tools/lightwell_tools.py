"""Lightwell integration tools — read the Lightwell OSV feed, verify
.rhlw versions exist, and check catalog coverage.

These tools give agents access to the Lightwell advisory feed and
repository so they can find the fixed coordinate for a Lightwell pin
instead of relying on Maven Central or OSV.dev.

Authentication: The Lightwell production repositories require a registry
service account. Set LIGHTWELL_USERNAME and LIGHTWELL_TOKEN as env vars.
When both are set, requests include HTTP Basic auth. When unset, only the
public demo feed is accessible.

The LIGHTWELL_OSV_BASE_URL defaults to the production Java OSV endpoint.
Override with LIGHTWELL_OSV_BASE_URL for the public demo or a mirror.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from app.cache import cache_get, cache_put
from app.http import fetch_json, fetch_text, head_check

logger = logging.getLogger(__name__)

# --- Lightwell endpoints ---
_DEFAULT_OSV_BASE = "https://packages.redhat.com/lightwell/osv/java/remediated"
_DEFAULT_REPO_BASE = "https://packages.redhat.com/lightwell/java/remediated"
_DEMO_OSV_BASE = (
    "https://packages.redhat.com/api/pulp-content/"
    "public-lightwell-demo/osv/java/remediated"
)


def _osv_base() -> str:
    return os.environ.get("LIGHTWELL_OSV_BASE_URL", _DEFAULT_OSV_BASE)


def _repo_base() -> str:
    return os.environ.get("LIGHTWELL_REPO_BASE_URL", _DEFAULT_REPO_BASE)


def _auth_headers() -> dict[str, str]:
    """Build HTTP Basic auth header from env if credentials are available."""
    username = os.environ.get("LIGHTWELL_USERNAME", "")
    token = os.environ.get("LIGHTWELL_TOKEN", "")
    if username and token:
        import base64

        credentials = base64.b64encode(f"{username}:{token}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}
    return {}


def _is_lightwell_version(version: str) -> bool:
    """Return True if the version string looks like a Lightwell build."""
    return ".rhlw-" in version or "+rhlw." in version


def _is_lightwell_advisory_id(advisory_id: str) -> bool:
    """Return True if the advisory ID matches Lightwell patterns."""
    return bool(
        re.match(r"^RHLW-\d{4}-\d+$", advisory_id)
        or re.match(r"^LW-DEMO-\d+$", advisory_id)
    )


# ============================================================================
# L1 — Lightwell OSV feed
# ============================================================================


def lookup_lightwell_osv(advisory_id: str) -> dict[str, Any]:
    """Fetch a Lightwell advisory from the Lightwell OSV feed.

    Returns the fixed coordinate, affected ranges, and advisory metadata.
    This is the version authority for a Lightwell pin — not Maven Central,
    not OSV.dev, not NVD.

    Args:
        advisory_id: The Lightwell advisory identifier
            (e.g. RHLW-2024-0001 or LW-DEMO-0002).
    """
    if not advisory_id or not advisory_id.strip():
        return {"status": "error", "error": "advisory_id is required"}

    advisory_id = advisory_id.strip()
    cache_key = advisory_id
    cached = cache_get("lightwell_osv", cache_key)
    if cached:
        try:
            return json.loads(cached)
        except (json.JSONDecodeError, TypeError):
            pass

    base = _osv_base()
    url = f"{base}/{advisory_id}.json"
    headers = _auth_headers()
    headers["Accept"] = "application/json"

    status, data = fetch_json(url, headers=headers)

    if status == 401:
        return {
            "status": "auth_required",
            "error": (
                "Lightwell OSV feed returned 401. Set LIGHTWELL_USERNAME and "
                "LIGHTWELL_TOKEN env vars with registry service account credentials."
            ),
            "advisory_id": advisory_id,
            "checked_url": url,
        }

    if status == 404 or data is None:
        return {
            "status": "not_found",
            "advisory_id": advisory_id,
            "checked_url": url,
            "error": f"Advisory {advisory_id} not found in the Lightwell OSV feed.",
        }

    if not isinstance(data, dict):
        return {
            "status": "error",
            "advisory_id": advisory_id,
            "error": "Unexpected response format from Lightwell OSV feed.",
        }

    result = _parse_lightwell_osv(advisory_id, data)
    cache_put("lightwell_osv", advisory_id, json.dumps(result))
    return result


def _parse_lightwell_osv(advisory_id: str, data: dict) -> dict[str, Any]:
    """Extract the fixed coordinate and affected ranges from a Lightwell OSV document."""
    result: dict[str, Any] = {
        "status": "ok",
        "advisory_id": advisory_id,
        "source": "lightwell-osv",
    }

    result["id"] = data.get("id", advisory_id)
    result["summary"] = data.get("summary", "")
    result["details"] = data.get("details", "")
    result["modified"] = data.get("modified", "")

    fixed_versions: list[dict[str, str]] = []
    affected_packages: list[dict[str, Any]] = []

    for affected in data.get("affected", []):
        pkg = affected.get("package", {})
        ecosystem = pkg.get("ecosystem", "")
        name = pkg.get("name", "")

        pkg_info: dict[str, Any] = {
            "ecosystem": ecosystem,
            "name": name,
        }

        ranges_data = affected.get("ranges", [])
        for rng in ranges_data:
            for event in rng.get("events", []):
                if "fixed" in event:
                    fixed_version = event["fixed"]
                    fixed_versions.append(
                        {
                            "package": name,
                            "version": fixed_version,
                            "ecosystem": ecosystem,
                        }
                    )

        versions = affected.get("versions", [])
        pkg_info["affected_versions"] = versions
        affected_packages.append(pkg_info)

    result["fixed_versions"] = fixed_versions
    result["affected_packages"] = affected_packages

    if fixed_versions:
        primary = fixed_versions[0]
        result["fixed_coordinate"] = f"{primary['package']}:{primary['version']}"
        result["fixed_version"] = primary["version"]
        result["fixed_package"] = primary["package"]

    return result


def list_lightwell_advisories() -> dict[str, Any]:
    """List available advisories by reading the PULP_MANIFEST index.

    The PULP_MANIFEST file at the OSV feed root lists all advisory JSON
    files with their checksums. A changed checksum means new data.

    Returns a list of advisory IDs and their checksums.
    """
    cache_key = "manifest"
    cached = cache_get("lightwell_osv", cache_key)
    if cached:
        try:
            return json.loads(cached)
        except (json.JSONDecodeError, TypeError):
            pass

    base = _osv_base()
    url = f"{base}/PULP_MANIFEST"
    headers = _auth_headers()

    status, text = fetch_text(url, headers=headers)

    if status == 401:
        return {
            "status": "auth_required",
            "error": (
                "Lightwell OSV manifest returned 401. Set LIGHTWELL_USERNAME "
                "and LIGHTWELL_TOKEN env vars."
            ),
        }

    if status == 404 or text is None:
        return {
            "status": "not_found",
            "error": "PULP_MANIFEST not found at the Lightwell OSV feed.",
            "checked_url": url,
        }

    advisories: list[dict[str, str]] = []
    for line in (text or "").splitlines():
        parts = line.strip().split(",")
        if len(parts) >= 2:
            filename = parts[0].strip()
            checksum = parts[1].strip()
            if filename.endswith(".json") and filename != "PULP_MANIFEST":
                adv_id = filename.replace(".json", "")
                advisories.append({"advisory_id": adv_id, "checksum": checksum})

    result = {
        "status": "ok",
        "count": len(advisories),
        "advisories": advisories,
    }
    cache_put("lightwell_osv", cache_key, json.dumps(result))
    return result


# ============================================================================
# L2 — Lightwell repository version check
# ============================================================================


def check_lightwell_version_exists(
    group_id: str,
    artifact_id: str,
    version: str,
) -> dict[str, Any]:
    """Verify a version exists in the Lightwell Java repository.

    Use this instead of check_version_exists when the version has a
    .rhlw suffix. Those versions are not on Maven Central.

    Args:
        group_id: Maven groupId, e.g. org.apache.commons.
        artifact_id: Maven artifactId, e.g. commons-lang3.
        version: Version string with .rhlw suffix, e.g. 3.14.0.rhlw-00001.
    """
    repo_base = _repo_base()
    group_path = group_id.replace(".", "/")
    url = (
        f"{repo_base}/{group_path}/{artifact_id}/{version}/"
        f"{artifact_id}-{version}.pom"
    )

    headers = _auth_headers()
    if headers:
        import httpx

        client = httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "lw-agents/1.0", **headers},
        )
        try:
            resp = client.head(url)
            status_code = resp.status_code
            exists = status_code == 200
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning("lightwell_head_check url=%s error=%s", url, exc)
            status_code = 0
            exists = False
        finally:
            client.close()
    else:
        status_code, exists = head_check(url)

    return {
        "group_id": group_id,
        "artifact_id": artifact_id,
        "version": version,
        "exists": exists,
        "status": (
            "checked"
            if status_code > 0
            else "auth_required"
            if status_code == 0
            else "error"
        ),
        "repository": "lightwell",
        "checked_url": url,
        "note": (
            "Lightwell versions are not on Maven Central. "
            "This check uses the Lightwell repository directly."
        ),
    }


# ============================================================================
# L3 — Smart version check (auto-routes Central vs Lightwell)
# ============================================================================


def check_version_exists_smart(
    group_id: str,
    artifact_id: str,
    version: str,
) -> dict[str, Any]:
    """Check if a version exists, routing to the right repository.

    If the version contains a .rhlw or +rhlw suffix, checks the Lightwell
    repository. Otherwise checks Maven Central.

    This is intended to replace or wrap the existing check_version_exists
    so skills do not need to decide which repository to check.

    Args:
        group_id: Maven groupId.
        artifact_id: Maven artifactId.
        version: Version string. Lightwell versions are auto-detected.
    """
    if _is_lightwell_version(version):
        return check_lightwell_version_exists(group_id, artifact_id, version)

    from app.tools.cve_tools import check_version_exists

    return check_version_exists(group_id, artifact_id, version)
