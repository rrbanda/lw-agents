"""Upstream discovery tools — find repos, commits, and diffs.

Gives agents the ability to discover where upstream fixes live:
- Find the GitHub repo for any Maven component
- Search for fix commits by CVE ID
- Fetch commit diffs to analyze what changed
- Extract commit URLs directly from advisory references
- Resolve version strings to git tags
"""

from __future__ import annotations

import logging
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

from app.cache import cache_get, cache_put
from app.http import fetch_json, fetch_text, github_headers
from app.validation import canonicalize_github_commit_url, parse_github_commit_url

logger = logging.getLogger(__name__)

_GH_COMMIT_RE = re.compile(
    r"github\.com/([^/]+)/([^/]+)/commit/([0-9a-fA-F]{7,40})",
    re.IGNORECASE,
)
_GH_SCM_RE = re.compile(r"github\.com[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")

_known_repos: dict[str, str] | None = None


# ============================================================================
# L2.1 — Known-repos mapping
# ============================================================================


def _load_known_repos() -> dict[str, str]:
    """Load the known-repos.yaml mapping file."""
    global _known_repos
    if _known_repos is not None:
        return _known_repos

    for base in (
        Path(__file__).resolve().parent.parent / "data",
        Path.cwd(),
    ):
        yaml_path = base / "known-repos.yaml"
        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and data:
                _known_repos = {k.lower(): v for k, v in data.items()}
                return _known_repos
        except FileNotFoundError:
            continue

    _known_repos = {}
    return _known_repos


def lookup_known_repo(component: str) -> dict[str, Any]:
    """Look up a component in the known-repos mapping.

    Tries the full name, then the artifact-only name (after last colon),
    then a version-stripped name.

    Args:
        component: Component name (e.g. "jackson-databind" or
            "com.fasterxml.jackson.core:jackson-databind").
    """
    repos = _load_known_repos()
    key = component.lower().strip()

    candidates = [key]
    if ":" in key:
        candidates.append(key.rsplit(":", 1)[1])
    stripped = re.sub(r"-\d+(?:\.\d+)*$", "", key)
    if stripped != key:
        candidates.append(stripped)
    if key.count(".") >= 2:
        candidates.append(key.rsplit(".", 1)[-1])

    for candidate in candidates:
        if candidate in repos:
            entry = repos[candidate]
            parts = entry.split("/")
            if len(parts) >= 2:
                return {
                    "status": "found",
                    "owner": parts[0],
                    "repo": parts[1],
                    "full_name": entry,
                    "source": "known-repos",
                    "url": f"https://github.com/{entry}",
                }

    return {"status": "not_found", "component": component}


# ============================================================================
# L2.2 — Maven POM SCM discovery
# ============================================================================


def discover_repo_from_maven_pom(
    group_id: str,
    artifact_id: str,
    version: str,
) -> dict[str, Any]:
    """Fetch Maven POM and extract upstream repo from <scm><url>.

    Args:
        group_id: Maven groupId (e.g. "com.fasterxml.jackson.core").
        artifact_id: Maven artifactId (e.g. "jackson-databind").
        version: Version to fetch (e.g. "2.13.4.2").
    """
    cache_key = f"{group_id}:{artifact_id}:{version}"
    cached = cache_get("maven_pom_scm", cache_key)
    if cached:
        import json

        return json.loads(cached)

    maven_repo = os.environ.get("MAVEN_REPO_URL", "https://repo1.maven.org/maven2")
    group_path = group_id.replace(".", "/")
    url = f"{maven_repo}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.pom"

    status, pom_text = fetch_text(url)
    if status == 404 or pom_text is None:
        return {"status": "not_found", "error": f"POM not found at {url}"}

    # Strip XML namespaces for simpler parsing
    pom_stripped = re.sub(r'\s+xmlns(?::[^=]+)?="[^"]*"', "", pom_text)
    try:
        root = ET.fromstring(pom_stripped)
    except ET.ParseError as exc:
        return {"status": "error", "error": f"POM parse error: {exc}"}

    for tag in ("scm/url", "scm/connection", "scm/developerConnection"):
        el = root.find(tag)
        if el is not None and el.text:
            m = _GH_SCM_RE.search(el.text)
            if m:
                result = {
                    "status": "found",
                    "owner": m.group(1),
                    "repo": m.group(2),
                    "full_name": f"{m.group(1)}/{m.group(2)}",
                    "source": "maven-pom",
                    "url": f"https://github.com/{m.group(1)}/{m.group(2)}",
                    "scm_tag": tag,
                }
                import json

                cache_put("maven_pom_scm", cache_key, json.dumps(result))
                return result

    return {"status": "not_found", "error": "No GitHub URL in POM SCM metadata"}


# ============================================================================
# L2.3 — Upstream repo discovery cascade
# ============================================================================


def discover_upstream_repo(
    component: str,
    version: str = "",
    group_id: str = "",
    artifact_id: str = "",
) -> dict[str, Any]:
    """Discover the upstream GitHub repo using a cascade of strategies.

    Strategy order (stops at first success):
    1. Known-repos.yaml lookup (instant, no API call)
    2. Maven POM SCM discovery (requires version)
    3. ecosyste.ms Packages API
    4. GitHub repository search API

    Args:
        component: Component name or Maven coordinate.
        version: Package version (for POM SCM lookup).
        group_id: Maven groupId (optional, parsed from component if absent).
        artifact_id: Maven artifactId (optional).
    """
    # Parse Maven coordinates if not provided
    if not group_id and ":" in component:
        parts = component.split(":")
        group_id = parts[0]
        artifact_id = parts[1] if len(parts) > 1 else ""
    if not artifact_id:
        artifact_id = component.rsplit(":", 1)[-1] if ":" in component else component

    # 1. Known-repos lookup
    result = lookup_known_repo(component)
    if result["status"] == "found":
        return result
    if artifact_id and artifact_id != component:
        result = lookup_known_repo(artifact_id)
        if result["status"] == "found":
            return result

    # 2. Maven POM SCM
    if group_id and artifact_id and version:
        result = discover_repo_from_maven_pom(group_id, artifact_id, version)
        if result["status"] == "found":
            return result

    # 3. ecosyste.ms
    try:
        from app.tools.live_cve_tools import lookup_ecosystems_package

        pkg_name = f"{group_id}:{artifact_id}" if group_id else component
        eco_result = lookup_ecosystems_package("maven", pkg_name)
        if eco_result.get("status") == "ok" and eco_result.get("repository_url"):
            repo_url = eco_result["repository_url"]
            m = _GH_SCM_RE.search(repo_url)
            if m:
                return {
                    "status": "found",
                    "owner": m.group(1),
                    "repo": m.group(2),
                    "full_name": f"{m.group(1)}/{m.group(2)}",
                    "source": "ecosystems",
                    "url": f"https://github.com/{m.group(1)}/{m.group(2)}",
                }
    except Exception as exc:
        logger.debug("ecosystems_discovery_error component=%s error=%s", component, exc)

    # 4. GitHub search
    token = os.environ.get("GITHUB_TOKEN", "")
    search_term = artifact_id or component
    search_url = (
        f"https://api.github.com/search/repositories"
        f"?q={urllib.parse.quote(search_term)}&sort=stars&per_page=5"
    )
    status, data = fetch_json(search_url, headers=github_headers(token or None))

    if status == 200 and isinstance(data, dict):
        search_lower = search_term.lower()
        for item in data.get("items", []):
            full_name = item.get("full_name", "")
            if search_lower in full_name.lower():
                owner, repo = full_name.split("/", 1)
                return {
                    "status": "found",
                    "owner": owner,
                    "repo": repo,
                    "full_name": full_name,
                    "source": "github-search",
                    "url": f"https://github.com/{full_name}",
                }

    return {
        "status": "not_found",
        "component": component,
        "strategies_tried": ["known-repos", "maven-pom", "ecosystems", "github-search"],
    }


# ============================================================================
# L2.4 — GitHub commit search
# ============================================================================


def search_fix_commits(
    cve_id: str,
    owner: str = "",
    repo: str = "",
) -> dict[str, Any]:
    """Search GitHub commits for CVE ID mentions.

    If owner/repo provided, scopes search to that repo.
    Otherwise searches globally.

    Args:
        cve_id: The CVE identifier to search for.
        owner: GitHub repo owner (optional).
        repo: GitHub repo name (optional).
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = github_headers(token or None)

    if owner and repo:
        query = urllib.parse.urlencode({"q": f"{cve_id} repo:{owner}/{repo}"})
    else:
        query = urllib.parse.urlencode({"q": cve_id})

    url = f"https://api.github.com/search/commits?{query}"
    status, data = fetch_json(url, headers=headers)

    if status != 200 or not isinstance(data, dict):
        return {"status": "error", "error": f"GitHub search returned {status}", "candidates": []}

    candidates = []
    for item in data.get("items", []):
        try:
            sha = item["sha"]
            html_url = item["html_url"]
            subject = item["commit"]["message"].split("\n")[0]
            item_repo = item.get("repository", {}).get("full_name", f"{owner}/{repo}")
            candidates.append(
                {
                    "sha": sha,
                    "url": canonicalize_github_commit_url(html_url),
                    "repo": item_repo,
                    "subject": subject,
                }
            )
        except (KeyError, IndexError):
            continue

    return {
        "status": "ok",
        "cve_id": cve_id,
        "repo": f"{owner}/{repo}" if owner else "global",
        "total_count": data.get("total_count", 0),
        "candidates": candidates,
    }


# ============================================================================
# L2.5 — Commit diff fetcher
# ============================================================================


def fetch_commit_diff(commit_url: str) -> dict[str, Any]:
    """Fetch the unified diff and metadata for a GitHub commit.

    Args:
        commit_url: GitHub commit URL (canonical or PR-scoped).
    """
    canonical = canonicalize_github_commit_url(commit_url)
    try:
        owner, repo, sha = parse_github_commit_url(canonical)
    except ValueError:
        return {"status": "error", "error": f"Cannot parse commit URL: {commit_url}"}

    token = os.environ.get("GITHUB_TOKEN", "")
    api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"

    # Fetch metadata
    headers = github_headers(token or None)
    meta_status, meta_data = fetch_json(api_url, headers=headers)

    if meta_status != 200 or not isinstance(meta_data, dict):
        return {"status": "error", "error": f"GitHub API returned {meta_status}"}

    # Fetch diff
    diff_headers = dict(headers)
    diff_headers["Accept"] = "application/vnd.github.diff"
    diff_status, diff_text = fetch_text(api_url, headers=diff_headers)

    commit_meta = meta_data.get("commit", {})
    author = commit_meta.get("author", {})
    stats = meta_data.get("stats", {})
    files = [f.get("filename", "") for f in meta_data.get("files", [])]

    return {
        "status": "ok",
        "sha": meta_data.get("sha", sha),
        "url": canonical,
        "repo": f"{owner}/{repo}",
        "subject": commit_meta.get("message", "").split("\n")[0],
        "message": commit_meta.get("message", ""),
        "author": author.get("name", ""),
        "date": author.get("date", ""),
        "additions": stats.get("additions", 0),
        "deletions": stats.get("deletions", 0),
        "files_changed": len(files),
        "files": files,
        "diff": (diff_text or "")[:100000],
    }


# ============================================================================
# L2.6 — Direct commit extraction from references
# ============================================================================


def extract_commit_urls(references: list[dict | str]) -> list[dict[str, str]]:
    """Extract GitHub commit URLs from CVE reference arrays.

    Works on OSV, GHSA, and NVD reference formats. No API calls needed.

    Args:
        references: List of reference objects (with "url" key) or bare URL strings.
    """
    commits = []
    seen_shas: set[str] = set()

    for ref in references:
        url = ref.get("url", ref) if isinstance(ref, dict) else str(ref)
        m = _GH_COMMIT_RE.search(url)
        if m:
            owner, repo_name, sha = m.groups()
            if sha not in seen_shas:
                seen_shas.add(sha)
                commits.append(
                    {
                        "sha": sha,
                        "url": f"https://github.com/{owner}/{repo_name}/commit/{sha}",
                        "repo": f"{owner}/{repo_name}",
                    }
                )

    return commits


# ============================================================================
# L2.7 — Version tag resolution
# ============================================================================


def resolve_version_tag(
    owner: str,
    repo: str,
    version: str,
) -> dict[str, Any]:
    """Resolve a version string to its git tag in a GitHub repo.

    Tries common tag naming conventions: {ver}, v{ver}, rel/{ver}.

    Args:
        owner: GitHub repo owner.
        repo: GitHub repo name.
        version: Version string to resolve (e.g. "2.13.4.2").
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = github_headers(token or None)

    tag_candidates = [
        version,
        f"v{version}",
        f"rel/{version}",
    ]
    if "-" in repo:
        suffix = repo.split("-", 1)[-1]
        tag_candidates.append(f"rel/commons-{suffix}-{version}")
        tag_candidates.append(f"rel/{repo}-{version}")

    for tag in tag_candidates:
        url = f"https://api.github.com/repos/{owner}/{repo}/commits?sha={tag}&per_page=1"
        status, data = fetch_json(url, headers=headers, max_retries=1)
        if status == 200 and isinstance(data, list) and data:
            return {
                "status": "found",
                "tag": tag,
                "owner": owner,
                "repo": repo,
                "version": version,
                "head_sha": data[0].get("sha", ""),
            }

    return {
        "status": "not_found",
        "owner": owner,
        "repo": repo,
        "version": version,
        "tried": tag_candidates,
    }
