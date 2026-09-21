"""Input validation utilities for CVE IDs, Maven coordinates, and versions.

Centralizes validation patterns used across tools, agents, and policy gates.
Every validation function returns a normalized value on success or raises
ValueError with a descriptive message on failure.
"""

from __future__ import annotations

import re
from typing import NewType

# --- Type aliases ---

CveId = NewType("CveId", str)
MavenCoordinate = NewType("MavenCoordinate", str)

# --- Compiled patterns ---

_CVE_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_MAVEN_COORD_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]+:[a-zA-Z][a-zA-Z0-9._-]+$")
_VERSION_HAS_DIGIT = re.compile(r"\d")
_PURL_MAVEN_PATTERN = re.compile(r"^pkg:maven/([^/]+)/([^@]+)(?:@(.+))?$")
_GITHUB_COMMIT_URL = re.compile(
    r"github\.com/([^/]+)/([^/]+)/commit/([0-9a-fA-F]{7,40})",
)
_GITHUB_PR_COMMIT_URL = re.compile(
    r"github\.com/([^/]+)/([^/]+)/pull/\d+/commits/([0-9a-fA-F]{7,40})",
)

# Placeholder values LLMs sometimes hallucinate
_PLACEHOLDER_VALUES = frozenset({"string", "null", "none", "n/a", "unknown", "tbd", ""})


def validate_cve_id(raw: str) -> CveId:
    """Validate and normalize a CVE ID string.

    Accepts CVE-YYYY-NNNNN (case-insensitive), returns uppercase form.

    Raises:
        ValueError: If the input is not a valid CVE ID.
    """
    stripped = raw.strip()
    if not _CVE_PATTERN.match(stripped):
        raise ValueError(f"Invalid CVE ID format: {stripped!r}. Expected CVE-YYYY-NNNNN.")
    return CveId(stripped.upper())


def validate_maven_coordinate(raw: str) -> MavenCoordinate:
    """Validate a Maven groupId:artifactId coordinate.

    Raises:
        ValueError: If the input is not a valid Maven coordinate.
    """
    stripped = raw.strip()
    if not _MAVEN_COORD_PATTERN.match(stripped):
        raise ValueError(f"Invalid Maven coordinates: {stripped!r}. Expected groupId:artifactId.")
    return MavenCoordinate(stripped)


def validate_version(raw: str, field_name: str = "version") -> str:
    """Validate that a version string contains at least one digit.

    Raises:
        ValueError: If the version has no digits or is a placeholder.
    """
    stripped = raw.strip()
    if stripped.lower() in _PLACEHOLDER_VALUES:
        raise ValueError(f"{field_name} is a placeholder: {stripped!r}")
    if not _VERSION_HAS_DIGIT.search(stripped):
        raise ValueError(f"{field_name} must contain a digit, got: {stripped!r}")
    return stripped


def is_valid_cve_id(raw: str) -> bool:
    """Return True if *raw* is a valid CVE ID (no exception)."""
    try:
        validate_cve_id(raw)
        return True
    except ValueError:
        return False


def is_placeholder(value: str) -> bool:
    """Return True if *value* is a known placeholder/hallucination."""
    return value.strip().lower() in _PLACEHOLDER_VALUES


def parse_maven_purl(purl: str) -> dict[str, str]:
    """Extract Maven coordinates from a Package URL.

    Args:
        purl: A Package URL like pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.13.2.

    Returns:
        Dict with group_id, artifact_id, version, package (groupId:artifactId).

    Raises:
        ValueError: If the PURL cannot be parsed.
    """
    match = _PURL_MAVEN_PATTERN.match(purl.strip())
    if not match:
        raise ValueError(f"Cannot parse Maven PURL: {purl!r}")

    group_id = match.group(1).replace("/", ".")
    artifact_id = match.group(2)
    version = match.group(3) or ""

    return {
        "group_id": group_id,
        "artifact_id": artifact_id,
        "version": version,
        "package": f"{group_id}:{artifact_id}",
    }


def parse_github_commit_url(url: str) -> tuple[str, str, str]:
    """Extract (owner, repo, sha) from a GitHub commit URL.

    Handles both canonical (/commit/{sha}) and PR-scoped
    (/pull/{n}/commits/{sha}) URLs.

    Raises:
        ValueError: If the URL is not a recognized GitHub commit URL.
    """
    for pattern in (_GITHUB_PR_COMMIT_URL, _GITHUB_COMMIT_URL):
        match = pattern.search(url)
        if match:
            return match.group(1), match.group(2), match.group(3)
    raise ValueError(f"Not a GitHub commit URL: {url!r}")


def canonicalize_github_commit_url(url: str) -> str:
    """Rewrite PR-scoped GitHub commit URL to canonical form.

    github.com/{owner}/{repo}/pull/{n}/commits/{sha}
        -> https://github.com/{owner}/{repo}/commit/{sha}

    Non-matching URLs are returned unchanged.
    """
    match = _GITHUB_PR_COMMIT_URL.search(url)
    if match:
        owner, repo, sha = match.group(1), match.group(2), match.group(3)
        return f"https://github.com/{owner}/{repo}/commit/{sha}"
    return url


def extract_cve_year(cve_id: str) -> str:
    """Extract the year component from a CVE ID.

    Args:
        cve_id: A validated CVE ID (e.g. CVE-2024-1234).

    Returns:
        The year string (e.g. "2024").
    """
    parts = cve_id.split("-")
    if len(parts) >= 2:
        return parts[1]
    raise ValueError(f"Cannot extract year from CVE ID: {cve_id!r}")


def split_nvr(nvr: str) -> tuple[str, str]:
    """Split an NVR (name-version-release) into (component, version).

    Handles Maven GAV (group:artifact:version), Maven-like
    (group:artifact-version), and RPM NVR (name-version).
    """
    tail = nvr
    if ":" in tail:
        tail = tail.rsplit(":", 1)[1]

    idx = tail.rfind("-")
    if idx <= 0:
        return tail, tail

    comp, ver = tail[:idx], tail[idx + 1 :]
    if ver[:1].isdigit():
        return comp, ver

    # Rescan for version start
    parts = tail.split("-")
    version_start_re = re.compile(r"^\d[\d.]*$")
    for i in range(1, len(parts)):
        if version_start_re.match(parts[i]):
            return "-".join(parts[:i]), "-".join(parts[i:])

    return comp, ver
