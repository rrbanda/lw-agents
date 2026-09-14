"""CVE exploration tools — agents call these to investigate vulnerabilities
one at a time, never loading the entire report into a single prompt."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

def list_must_fix_cves(workspace_path: str) -> dict[str, Any]:
    """List all CVEs in the Conforma policy-gated must-fix set.

    Returns a dict with status, count, and cves list. The status field
    distinguishes success from degraded (file unreadable) so the agent
    can reason about data quality.

    Args:
        workspace_path: Path to the pipeline workspace containing rhtpa/ directory.
    """
    ws = workspace_path or os.environ.get("WORKSPACE_PATH", "")
    must_fix_path = Path(ws) / "rhtpa" / "must-fix-cves.json"

    if not must_fix_path.exists():
        return {"status": "not_found", "count": 0, "cves": [],
                "error": f"must-fix-cves.json not found at {must_fix_path}"}

    try:
        raw = json.loads(must_fix_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"status": "degraded", "count": 0, "cves": [],
                "error": f"Failed to read must-fix-cves.json: {e}"}

    if not isinstance(raw, list):
        return {"status": "degraded", "count": 0, "cves": [],
                "error": "must-fix-cves.json is not a JSON array"}

    results = []
    for item in raw:
        if isinstance(item, str):
            results.append({"cve_id": item, "severity": "unknown",
                            "affected_purls": [], "fixed_version_hints": []})
        elif isinstance(item, dict):
            results.append({
                "cve_id": item.get("cve_id", ""),
                "severity": item.get("severity", "unknown"),
                "affected_purls": item.get("affected_purls", []),
                "fixed_version_hints": item.get("fixed_version_hints", []),
            })
    return {"status": "ok", "count": len(results), "cves": results}


def lookup_cve_detail(cve_id: str, workspace_path: str) -> dict[str, Any]:
    """Look up full details for a single CVE from the RHTPA vulnerability report.

    Returns title, description, severity, affected_purls, fixed_version_hints,
    and the full advisory_text. Call this per-CVE after list_must_fix_cves.

    Args:
        cve_id: The CVE identifier, e.g. CVE-2024-1234.
        workspace_path: Path to the pipeline workspace containing rhtpa/ directory.
    """
    ws = workspace_path or os.environ.get("WORKSPACE_PATH", "")
    vuln_path = Path(ws) / "rhtpa" / "vulnerabilities.json"
    if not vuln_path.exists():
        return {"error": f"Vulnerability report not found at {vuln_path}"}

    report = json.loads(vuln_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        return {"error": "Vulnerability report is not a valid JSON object"}

    cve_upper = cve_id.upper()

    finding = next(
        (f for f in report.get("findings", [])
         if isinstance(f, dict) and (f.get("cve_id") or "").upper() == cve_upper),
        None,
    )
    detail = next(
        (d for d in report.get("details", [])
         if isinstance(d, dict)
         and (d.get("identifier") or d.get("id") or "").upper() == cve_upper),
        None,
    )

    if finding is None and detail is None:
        return {"status": "not_found",
                "error": f"CVE {cve_id} not found in vulnerability report"}

    result: dict[str, Any] = {"cve_id": cve_id}
    if finding:
        result["severity"] = finding.get("severity", "unknown")
        result["affected_purls"] = finding.get("affected_purls", [])
        result["fixed_version_hints"] = finding.get("fixed_version_hints", [])
    if detail:
        result["title"] = detail.get("title", "")
        result["description"] = detail.get("description", "")
        result["advisory_text"] = (
            f"{detail.get('title', '')} {detail.get('description', '')}"
        )
    return result


def parse_maven_purl(purl: str) -> dict[str, str]:
    """Extract Maven coordinates from a Package URL.

    Args:
        purl: A Package URL like pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.13.2.

    Returns:
        Dict with group_id, artifact_id, version, and the Maven package
        string as groupId:artifactId.
    """
    match = re.match(r"pkg:maven/([^/]+)/([^@]+)(?:@(.+))?", purl)
    if not match:
        return {"error": f"Cannot parse PURL: {purl}"}

    group_id = match.group(1).replace("/", ".")
    artifact_id = match.group(2)
    version = match.group(3) or ""

    return {
        "group_id": group_id,
        "artifact_id": artifact_id,
        "version": version,
        "package": f"{group_id}:{artifact_id}",
    }


def check_version_exists(
    group_id: str,
    artifact_id: str,
    version: str,
) -> dict[str, Any]:
    """Verify a Maven version exists in Maven Central.

    Prevents hallucinated version numbers. Returns whether the version
    is a real published artifact.

    Args:
        group_id: Maven groupId, e.g. com.fasterxml.jackson.core.
        artifact_id: Maven artifactId, e.g. jackson-databind.
        version: Version string to verify, e.g. 2.13.4.2.
    """
    import httpx

    maven_repo = os.environ.get(
        "MAVEN_REPO_URL", "https://repo1.maven.org/maven2"
    )
    group_path = group_id.replace(".", "/")
    url = (
        f"{maven_repo}/{group_path}/{artifact_id}"
        f"/{version}/{artifact_id}-{version}.pom"
    )

    try:
        resp = httpx.head(url, follow_redirects=True, timeout=10.0)
        return {
            "group_id": group_id,
            "artifact_id": artifact_id,
            "version": version,
            "exists": resp.status_code == 200,
            "status": "checked",
            "checked_url": url,
        }
    except httpx.TimeoutException:
        return {
            "group_id": group_id,
            "artifact_id": artifact_id,
            "version": version,
            "exists": False,
            "status": "timeout",
            "error": "Maven Central check timed out — version unverified",
            "checked_url": url,
        }
    except httpx.HTTPError as e:
        return {
            "group_id": group_id,
            "artifact_id": artifact_id,
            "version": version,
            "exists": False,
            "status": "error",
            "error": f"Network error checking version: {e}",
            "checked_url": url,
        }
