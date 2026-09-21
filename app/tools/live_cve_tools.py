"""Live CVE data tools — fetch real-time vulnerability data from authoritative sources.

These tools give agents access to 7 data sources beyond the local RHTPA report:
OSV.dev, NVD, EPSS, GitHub Advisories, Red Hat VEX, Spring.io, and ecosyste.ms.

All tools use the shared HTTP retry layer (app/http.py) and response cache
(app/cache.py) for resilience and efficiency.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
from typing import Any

from app.cache import cache_get, cache_put
from app.http import fetch_json, fetch_text, github_headers
from app.validation import extract_cve_year, is_valid_cve_id

logger = logging.getLogger(__name__)

# --- Public API endpoints ---
OSV_API_BASE = "https://api.osv.dev/v1/vulns"
NVD_API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
EPSS_API_BASE = "https://api.first.org/data/v1/epss"
GITHUB_ADVISORY_API = "https://api.github.com/advisories"
VEX_BASE = "https://security.access.redhat.com/data/csaf/v2/vex"
SPRING_SECURITY_BASE = "https://spring.io/security"
ECOSYSTEMS_PACKAGES_BASE = "https://packages.ecosyste.ms/api/v1"
ECOSYSTEMS_ADVISORIES_BASE = "https://advisories.ecosyste.ms/api/v1"


# ============================================================================
# L1.1 — OSV/GHSA fetcher
# ============================================================================


def lookup_osv(cve_id: str) -> dict[str, Any]:
    """Fetch vulnerability data from OSV.dev API.

    Returns affected version ranges, fixed versions, GHSA aliases,
    and package data. Auto-enriches with GHSA data when the CVE record
    lacks package information.

    Args:
        cve_id: The CVE identifier (e.g. CVE-2024-1234).
    """
    if not is_valid_cve_id(cve_id):
        return {"status": "error", "error": f"Invalid CVE ID: {cve_id}"}

    cve_upper = cve_id.upper()
    cached = cache_get("osv", cve_upper)
    if cached:
        return json.loads(cached)

    url = f"{OSV_API_BASE}/{cve_upper}"
    status, data = fetch_json(url)

    if status == 404 or data is None:
        return {"status": "not_found", "cve_id": cve_id}

    if isinstance(data, dict) and "error" in data:
        return {"status": "error", "error": data["error"]}

    # Enrich with GHSA alias if CVE record lacks package data
    enriched = _enrich_from_alias(data)

    # Extract structured fields
    result = _parse_osv_response(cve_upper, enriched)
    cache_put("osv", cve_upper, json.dumps(result))
    return result


def _has_package_data(osv_data: dict) -> bool:
    """True if any affected entry has a non-empty package name."""
    for affected in osv_data.get("affected", []):
        pkg = affected.get("package", {})
        if pkg.get("name"):
            return True
    return False


def _enrich_from_alias(osv_data: dict) -> dict:
    """If CVE record lacks package data, fetch GHSA alias instead."""
    if _has_package_data(osv_data):
        return osv_data

    for alias in osv_data.get("aliases", []):
        if alias.startswith("GHSA-"):
            try:
                url = f"{OSV_API_BASE}/{alias}"
                status, ghsa_data = fetch_json(url)
                if status == 200 and isinstance(ghsa_data, dict) and _has_package_data(ghsa_data):
                    logger.info(
                        "osv_enriched_from_alias cve_id=%s alias=%s",
                        osv_data.get("id"), alias,
                    )
                    return ghsa_data
            except Exception as exc:
                logger.debug("osv_alias_fetch_error alias=%s error=%s", alias, exc)
    return osv_data


def _parse_osv_response(cve_id: str, data: dict) -> dict[str, Any]:
    """Extract structured fields from an OSV response."""
    result: dict[str, Any] = {
        "status": "ok",
        "cve_id": cve_id,
        "summary": data.get("summary", ""),
        "details": data.get("details", ""),
        "aliases": data.get("aliases", []),
        "references": [],
        "affected_packages": [],
        "fixed_versions": [],
    }

    for ref in data.get("references", []):
        result["references"].append({
            "type": ref.get("type", ""),
            "url": ref.get("url", ""),
        })

    for affected in data.get("affected", []):
        pkg = affected.get("package", {})
        entry = {
            "ecosystem": pkg.get("ecosystem", ""),
            "name": pkg.get("name", ""),
            "ranges": [],
            "fixed_versions": [],
        }
        for rng in affected.get("ranges", []):
            for event in rng.get("events", []):
                if "fixed" in event:
                    entry["fixed_versions"].append(event["fixed"])
                    result["fixed_versions"].append(event["fixed"])
            entry["ranges"].append({
                "type": rng.get("type", ""),
                "events": rng.get("events", []),
            })
        result["affected_packages"].append(entry)

    return result


# ============================================================================
# L1.2 — NVD 2.0 fetcher
# ============================================================================


def lookup_nvd(cve_id: str) -> dict[str, Any]:
    """Fetch CVE record from NVD 2.0 API.

    Returns CVSS v3 vector/score, CWE classification, patch-tagged URLs,
    and CPE fix versions (versionEndExcluding).

    Args:
        cve_id: The CVE identifier (e.g. CVE-2024-1234).
    """
    if not is_valid_cve_id(cve_id):
        return {"status": "error", "error": f"Invalid CVE ID: {cve_id}"}

    cve_upper = cve_id.upper()
    cached = cache_get("nvd", cve_upper)
    if cached:
        return json.loads(cached)

    headers: dict[str, str] = {"Accept": "application/json"}
    api_key = os.environ.get("NVD_API_KEY", "")
    if api_key:
        headers["apiKey"] = api_key

    url = f"{NVD_API_BASE}?cveId={cve_upper}"
    status, data = fetch_json(url, headers=headers)

    if status == 404 or data is None:
        return {"status": "not_found", "cve_id": cve_id}

    if isinstance(data, dict) and "error" in data:
        return {"status": "error", "error": data["error"]}

    result = _parse_nvd_response(cve_upper, data)
    cache_put("nvd", cve_upper, json.dumps(result))
    return result


def _parse_nvd_response(cve_id: str, data: dict) -> dict[str, Any]:
    """Extract structured fields from an NVD 2.0 response."""
    result: dict[str, Any] = {
        "status": "ok",
        "cve_id": cve_id,
        "cvss_v3_score": None,
        "cvss_v3_vector": "",
        "cvss_severity": "",
        "cwe_id": "",
        "cwe_name": "",
        "description": "",
        "patch_urls": [],
        "reference_urls": [],
        "fix_versions": [],
    }

    vulns = data.get("vulnerabilities", [])
    if not vulns:
        result["status"] = "not_found"
        return result

    cve_data = vulns[0].get("cve", {})

    # Description
    for desc in cve_data.get("descriptions", []):
        if desc.get("lang") == "en":
            result["description"] = desc.get("value", "")
            break

    # CVSS v3
    metrics = cve_data.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30"):
        metric_list = metrics.get(key, [])
        if metric_list:
            cvss = metric_list[0].get("cvssData", {})
            result["cvss_v3_score"] = cvss.get("baseScore")
            result["cvss_v3_vector"] = cvss.get("vectorString", "")
            result["cvss_severity"] = cvss.get("baseSeverity", "")
            break

    # CWE
    for weakness in cve_data.get("weaknesses", []):
        for desc in weakness.get("description", []):
            val = desc.get("value", "")
            if val.startswith("CWE-"):
                result["cwe_id"] = val
                break
        if result["cwe_id"]:
            break

    # References — separate patch URLs from general references
    for ref in cve_data.get("references", []):
        url = ref.get("url", "")
        tags = ref.get("tags", [])
        if "Patch" in tags:
            result["patch_urls"].append(url)
        result["reference_urls"].append({"url": url, "tags": tags})

    # Fix versions from CPE match data (versionEndExcluding)
    for config in cve_data.get("configurations", []):
        for node in config.get("nodes", []):
            for match in node.get("cpeMatch", []):
                ver = match.get("versionEndExcluding")
                if ver and ver not in result["fix_versions"]:
                    result["fix_versions"].append(ver)

    return result


# ============================================================================
# L1.3 — EPSS score fetcher
# ============================================================================


def lookup_epss(cve_id: str) -> dict[str, Any]:
    """Fetch exploit prediction score from FIRST EPSS API.

    EPSS (Exploit Prediction Scoring System) predicts the probability
    that a CVE will be exploited in the wild within 30 days.

    Args:
        cve_id: The CVE identifier (e.g. CVE-2024-1234).
    """
    if not is_valid_cve_id(cve_id):
        return {"status": "error", "error": f"Invalid CVE ID: {cve_id}"}

    cve_upper = cve_id.upper()
    cached = cache_get("epss", cve_upper)
    if cached:
        return json.loads(cached)

    url = f"{EPSS_API_BASE}?cve={cve_upper}"
    status, data = fetch_json(url)

    if status != 200 or not isinstance(data, dict):
        return {"status": "error", "cve_id": cve_id, "error": f"EPSS API returned {status}"}

    epss_data = data.get("data", [])
    if not epss_data:
        return {"status": "not_found", "cve_id": cve_id}

    entry = epss_data[0]
    result = {
        "status": "ok",
        "cve_id": cve_upper,
        "epss_score": float(entry.get("epss", 0.0)),
        "epss_percentile": float(entry.get("percentile", 0.0)),
    }
    cache_put("epss", cve_upper, json.dumps(result))
    return result


# ============================================================================
# L1.4 — GitHub Advisory search
# ============================================================================


def search_github_advisory(cve_id: str) -> dict[str, Any]:
    """Search GitHub Advisory Database for a CVE.

    Returns advisory details, affected/patched versions, fix commit URLs,
    and source_code_location (upstream repo).

    Args:
        cve_id: The CVE identifier (e.g. CVE-2024-1234).
    """
    if not is_valid_cve_id(cve_id):
        return {"status": "error", "error": f"Invalid CVE ID: {cve_id}"}

    cve_upper = cve_id.upper()
    cached = cache_get("github_advisory", cve_upper)
    if cached:
        return json.loads(cached)

    token = os.environ.get("GITHUB_TOKEN", "")
    headers = github_headers(token or None)
    url = f"{GITHUB_ADVISORY_API}?cve_id={cve_upper}"
    status, data = fetch_json(url, headers=headers)

    if status != 200 or not isinstance(data, list):
        return {"status": "error", "cve_id": cve_id, "error": f"GitHub API returned {status}"}

    if not data:
        return {"status": "not_found", "cve_id": cve_id}

    result: dict[str, Any] = {
        "status": "ok",
        "cve_id": cve_upper,
        "advisories": [],
        "fix_commit_urls": [],
        "patched_versions": [],
        "source_code_location": "",
    }

    for adv in data:
        advisory = {
            "ghsa_id": adv.get("ghsa_id", ""),
            "summary": adv.get("summary", ""),
            "severity": adv.get("severity", ""),
            "cvss_score": (adv.get("cvss") or {}).get("score"),
            "source_code_location": adv.get("source_code_location", ""),
            "vulnerabilities": [],
        }

        if advisory["source_code_location"] and not result["source_code_location"]:
            result["source_code_location"] = advisory["source_code_location"]

        for vuln in adv.get("vulnerabilities", []):
            v = {
                "package": vuln.get("package", {}).get("name", ""),
                "ecosystem": vuln.get("package", {}).get("ecosystem", ""),
                "first_patched_version": vuln.get("first_patched_version", ""),
                "vulnerable_version_range": vuln.get("vulnerable_version_range", ""),
            }
            advisory["vulnerabilities"].append(v)
            if v["first_patched_version"]:
                result["patched_versions"].append(v["first_patched_version"])

        # Extract fix commit URLs from references
        for ref in adv.get("references", []):
            url_str = ref if isinstance(ref, str) else ""
            if "/commit/" in url_str and "github.com" in url_str:
                result["fix_commit_urls"].append(url_str)

        result["advisories"].append(advisory)

    cache_put("github_advisory", cve_upper, json.dumps(result))
    return result


# ============================================================================
# L1.5 — Red Hat VEX fetcher
# ============================================================================


def lookup_vex(cve_id: str) -> dict[str, Any]:
    """Fetch Red Hat CSAF 2.0 VEX document for a CVE.

    Returns component name, severity, Bugzilla IDs, upstream references,
    description, and fixed versions from the official Red Hat advisory.

    Args:
        cve_id: The CVE identifier (e.g. CVE-2024-1234).
    """
    if not is_valid_cve_id(cve_id):
        return {"status": "error", "error": f"Invalid CVE ID: {cve_id}"}

    cve_lower = cve_id.lower()
    cve_upper = cve_id.upper()
    cached = cache_get("vex", cve_upper)
    if cached:
        return json.loads(cached)

    year = extract_cve_year(cve_upper)
    url = f"{VEX_BASE}/{year}/{cve_lower}.json"
    status, data = fetch_json(url)

    if status == 404 or data is None:
        return {"status": "not_found", "cve_id": cve_id}

    if isinstance(data, dict) and "error" in data:
        return {"status": "error", "error": data["error"]}

    result = _parse_vex_response(cve_upper, data)
    cache_put("vex", cve_upper, json.dumps(result))
    return result


_RHBZ_URL_RE = re.compile(r"https?://bugzilla\.redhat\.com/show_bug\.cgi\?id=(\d+)")
_EXCLUDED_DOMAINS = (
    "access.redhat.com",
    "bugzilla.redhat.com",
    "cve.org",
    "nvd.nist.gov",
    "security.access.redhat.com",
)


def _parse_vex_response(cve_id: str, data: dict) -> dict[str, Any]:
    """Parse a CSAF 2.0 VEX document into structured fields."""
    result: dict[str, Any] = {
        "status": "ok",
        "cve_id": cve_id,
        "component": "",
        "description": "",
        "rhbz_ids": [],
        "upstream_refs": [],
        "fixed_versions": [],
    }

    # Component from title
    title = data.get("document", {}).get("title", "")
    if ":" in title:
        result["component"] = title.split(":")[0].strip().lower()
    elif title:
        result["component"] = title.strip().lower()

    # Vulnerability data
    vulns = data.get("vulnerabilities", [])
    if not vulns:
        return result

    vuln = vulns[0]

    # Description
    notes = vuln.get("notes", [])
    result["description"] = "\n\n".join(
        n.get("text", "") for n in notes if n.get("category") == "description"
    )

    # References
    for ref in vuln.get("references", []):
        url = ref.get("url", "")
        m = _RHBZ_URL_RE.search(url)
        if m:
            result["rhbz_ids"].append(m.group(1))
        elif not any(domain in url for domain in _EXCLUDED_DOMAINS):
            result["upstream_refs"].append(url)

    # Fixed versions
    result["fixed_versions"] = vuln.get("product_status", {}).get("fixed", [])

    return result


# ============================================================================
# L1.6 — Spring.io advisory fetcher
# ============================================================================


def lookup_spring_advisory(cve_id: str) -> dict[str, Any]:
    """Fetch Spring.io security advisory for a CVE.

    Returns the advisory text as markdown (converted from HTML).
    Only relevant for Spring Framework components.

    Args:
        cve_id: The CVE identifier (e.g. CVE-2024-1234).
    """
    if not is_valid_cve_id(cve_id):
        return {"status": "error", "error": f"Invalid CVE ID: {cve_id}"}

    cve_lower = cve_id.lower()
    cached = cache_get("spring", cve_lower)
    if cached:
        return json.loads(cached)

    url = f"{SPRING_SECURITY_BASE}/{cve_lower}"
    status, html = fetch_text(url, headers={"Accept": "text/html"})

    if status == 404 or html is None:
        return {"status": "not_found", "cve_id": cve_id}

    # Basic HTML to text extraction (strip tags)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    # Extract main content area if possible
    main_start = html.find('id="main"')
    if main_start >= 0:
        tag_start = html.rfind("<div", 0, main_start)
        footer = html.find("<footer", tag_start if tag_start >= 0 else 0)
        if footer > 0 and tag_start >= 0:
            section = html[tag_start:footer]
            text = re.sub(r"<[^>]+>", " ", section)
            text = re.sub(r"\s+", " ", text).strip()

    result = {
        "status": "ok",
        "cve_id": cve_id,
        "advisory_text": text[:10000],
    }
    cache_put("spring", cve_lower, json.dumps(result))
    return result


# ============================================================================
# L1.7 — ecosyste.ms package lookup
# ============================================================================


def lookup_ecosystems_package(
    ecosystem: str,
    name: str,
) -> dict[str, Any]:
    """Look up a package on ecosyste.ms Packages API.

    Returns repository_url, dependent count, latest version, and other metadata.

    Args:
        ecosystem: Package ecosystem (e.g. "maven", "pypi").
        name: Package name (e.g. "com.fasterxml.jackson.core:jackson-databind").
    """
    cache_key = f"{ecosystem}:{name}"
    cached = cache_get("ecosystems_pkg", cache_key)
    if cached:
        return json.loads(cached)

    url = (
        f"{ECOSYSTEMS_PACKAGES_BASE}/packages/lookup"
        f"?ecosystem={urllib.parse.quote(ecosystem)}"
        f"&name={urllib.parse.quote(name)}"
    )
    status, data = fetch_json(url)

    if status == 404 or data is None:
        return {"status": "not_found", "ecosystem": ecosystem, "name": name}

    # API returns a list; take first match
    pkg = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else None
    if not pkg:
        return {"status": "not_found", "ecosystem": ecosystem, "name": name}

    result = {
        "status": "ok",
        "ecosystem": ecosystem,
        "name": name,
        "repository_url": pkg.get("repository_url", ""),
        "latest_version": pkg.get("latest_release_number", ""),
        "dependent_repos_count": pkg.get("dependent_repos_count", 0),
        "dependent_packages_count": pkg.get("dependent_packages_count", 0),
        "homepage": pkg.get("homepage", ""),
        "description": pkg.get("description", "")[:500],
    }
    cache_put("ecosystems_pkg", cache_key, json.dumps(result))
    return result


def lookup_ecosystems_advisory(cve_id: str) -> dict[str, Any]:
    """Look up a CVE on ecosyste.ms Advisories API.

    Returns EPSS score/percentile and additional advisory metadata.

    Args:
        cve_id: The CVE identifier.
    """
    if not is_valid_cve_id(cve_id):
        return {"status": "error", "error": f"Invalid CVE ID: {cve_id}"}

    cve_upper = cve_id.upper()
    cached = cache_get("ecosystems_adv", cve_upper)
    if cached:
        return json.loads(cached)

    url = f"{ECOSYSTEMS_ADVISORIES_BASE}/advisories/{urllib.parse.quote(cve_upper, safe='')}"
    status, data = fetch_json(url)

    if status == 404 or data is None:
        return {"status": "not_found", "cve_id": cve_id}

    pkg = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else {}

    result = {
        "status": "ok",
        "cve_id": cve_upper,
        "epss_percentage": pkg.get("epss_percentage"),
        "epss_percentile": pkg.get("epss_percentile"),
        "severity": pkg.get("severity", ""),
        "summary": pkg.get("summary", "")[:1000],
    }
    cache_put("ecosystems_adv", cve_upper, json.dumps(result))
    return result
