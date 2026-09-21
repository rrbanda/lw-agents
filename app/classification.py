"""Advanced classification and analysis patterns — Layer 12.

Provides complexity classification, JDK version constraint awareness,
component-to-path matching, and version-window commit scanning.
"""

from __future__ import annotations

import os
import re
from typing import Any

from app.http import fetch_json, github_headers

# ============================================================================
# L12.1 — Complexity classification (P0-P4)
# ============================================================================

PATTERN_NAMES: dict[int, str] = {
    0: "already_patched",
    1: "clean_cherry_pick",
    2: "api_divergence",
    3: "refactoring_noise",
    4: "fix_interdependency",
}


def classify_diff_complexity(diff_text: str) -> dict[str, Any]:
    """Classify a diff by size complexity (S/M/L) and hunk count.

    Returns complexity rating and dimensional detail.
    """
    if not diff_text:
        return {"complexity": "S", "byte_size": 0, "files_touched": 0, "hunks": 0}

    byte_size = len(diff_text.encode("utf-8"))
    files = len(re.findall(r"^diff --git", diff_text, re.MULTILINE))
    hunks = len(re.findall(r"^@@", diff_text, re.MULTILINE))

    if byte_size < 2000 and files <= 3 and hunks <= 5:
        complexity = "S"
    elif byte_size < 10000 and files <= 10 and hunks <= 20:
        complexity = "M"
    else:
        complexity = "L"

    return {
        "complexity": complexity,
        "byte_size": byte_size,
        "files_touched": files,
        "hunks": hunks,
    }


def classify_complexity_tier(
    pattern: int | None,
    diff_complexity: str,
    cross_major: bool = False,
) -> int:
    """Derive a complexity tier (1-3) from classification outputs.

    Tier 1 (fast-track): already-patched or clean cherry-pick with S/M diff.
    Tier 2 (standard): clean cherry-pick with L diff, or api-divergence.
    Tier 3 (complex): refactoring noise, fix interdependency, or cross-major.
    """
    if cross_major:
        return 3
    if pattern is None:
        return 2
    if pattern == 0:
        return 1
    if pattern == 1:
        return 1 if diff_complexity in ("S", "M") else 2
    if pattern == 2:
        return 2
    return 3


TIER_LABELS = {1: "fast-track", 2: "standard", 3: "complex"}


# ============================================================================
# L12.2 — JDK version constraint awareness
# ============================================================================

_JAVA_FEATURES_BY_VERSION: list[tuple[int, str]] = [
    (7, "try-with-resources"),
    (7, "diamond operator"),
    (8, "lambdas"),
    (8, "method references"),
    (8, "streams API"),
    (8, "default methods in interfaces"),
    (10, "var keyword for local variables"),
    (11, "var in lambda parameters"),
    (14, "switch expressions"),
    (15, "text blocks"),
    (16, "records"),
    (16, "pattern matching for instanceof"),
    (17, "sealed classes"),
]


def java_version_constraint(required_jdk: int) -> str:
    """Build a prompt section listing Java features unavailable at the target level.

    Args:
        required_jdk: Target Java version (e.g. 8, 11, 17).

    Returns:
        Constraint text for inclusion in agent prompts. Empty if no restrictions.
    """
    unavailable = [
        f"{name} (requires {ver}+)"
        for ver, name in _JAVA_FEATURES_BY_VERSION
        if ver > required_jdk
    ]
    if not unavailable:
        return ""
    return (
        f"The project targets Java {required_jdk}. Do NOT use language features "
        f"unavailable at this level: {', '.join(unavailable)}."
    )


def detect_java_version(project_dir: str) -> int | None:
    """Detect the target Java version from POM or Gradle config.

    Returns the Java major version (e.g. 8, 11, 17) or None if not detected.
    """
    pom_path = os.path.join(project_dir, "pom.xml")
    if os.path.exists(pom_path):
        try:
            content = open(pom_path).read()
            # <maven.compiler.source>1.8</maven.compiler.source>
            m = re.search(
                r"<maven\.compiler\.source>\s*(\d[\d.]*)"
                r"\s*</maven\.compiler\.source>", content,
            )
            if m:
                ver = m.group(1)
                if ver.startswith("1."):
                    return int(ver.replace("1.", ""))
                return int(ver.split(".")[0])
            # <java.version>17</java.version>
            m = re.search(r"<java\.version>\s*(\d+)\s*</java\.version>", content)
            if m:
                return int(m.group(1))
        except (OSError, ValueError):
            pass

    for gradle_file in ("build.gradle", "build.gradle.kts"):
        gpath = os.path.join(project_dir, gradle_file)
        if os.path.exists(gpath):
            try:
                content = open(gpath).read()
                m = re.search(r"sourceCompatibility\s*=\s*['\"]?(\d+)", content)
                if m:
                    return int(m.group(1))
                m = re.search(r"JavaVersion\.VERSION_(\d+)", content)
                if m:
                    return int(m.group(1))
            except (OSError, ValueError):
                pass

    return None


# ============================================================================
# L12.3 — Component-to-path matching
# ============================================================================


def component_matches_path(component: str, file_path: str) -> bool:
    """Check if a file path belongs to a component in a monorepo.

    Matches both hyphenated names (spring-web) and their slash equivalents
    (spring/web) against path segments.

    Args:
        component: Component name (e.g. "jackson-databind").
        file_path: File path from a diff (e.g. "databind/src/main/java/...").
    """
    if not component:
        return True

    comp_lower = component.lower()
    path_lower = file_path.lower()
    slash_variant = comp_lower.replace("-", "/")

    return (
        f"/{comp_lower}/" in path_lower
        or path_lower.startswith(f"{comp_lower}/")
        or path_lower.startswith(f"{slash_variant}/")
        or f"/{slash_variant}/" in path_lower
    )


def classify_file_relevance(
    files: list[str],
    component: str,
) -> dict[str, list[str]]:
    """Classify files by relevance to a target component.

    Returns dict with 'relevant', 'other', and 'boilerplate' lists.
    """
    relevant, other, boilerplate = [], [], []
    boilerplate_patterns = (".gitignore", ".editorconfig", "LICENSE", "NOTICE")

    for f in files:
        basename = f.split("/")[-1] if "/" in f else f
        if any(basename == bp for bp in boilerplate_patterns):
            boilerplate.append(f)
        elif component_matches_path(component, f):
            relevant.append(f)
        else:
            other.append(f)

    return {
        "relevant": relevant,
        "other": other,
        "boilerplate": boilerplate,
    }


# ============================================================================
# L12.4 — Version-window commit scanning
# ============================================================================


def scan_version_window(
    owner: str,
    repo: str,
    prior_tag: str,
    fixed_tag: str,
) -> dict[str, Any]:
    """Fetch commits between two version tags and scan for security-related subjects.

    Uses GitHub Compare API to enumerate inter-tag commits.

    Args:
        owner: GitHub repo owner.
        repo: GitHub repo name.
        prior_tag: Tag for the version before the fix.
        fixed_tag: Tag for the fixed version.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = github_headers(token or None)
    url = f"https://api.github.com/repos/{owner}/{repo}/compare/{prior_tag}...{fixed_tag}"

    status, data = fetch_json(url, headers=headers)

    if status != 200 or not isinstance(data, dict):
        return {"status": "error", "error": f"Compare API returned {status}"}

    commits = data.get("commits", [])
    total = data.get("total_commits", len(commits))

    security_keywords = re.compile(
        r"(?:fix|patch|secur|vuln|cve|sanitiz|escap|inject|overflow|bypass|xss|rce"
        r"|dos|csrf|ssrf|deserializ|authenticat|authori[sz]|permiss|validat)",
        re.IGNORECASE,
    )

    all_commits = []
    security_related = []
    for c in commits:
        sha = c.get("sha", "")
        message = c.get("commit", {}).get("message", "")
        subject = message.split("\n")[0][:120]
        entry = {"sha": sha, "subject": subject}
        all_commits.append(entry)
        if security_keywords.search(subject):
            security_related.append(entry)

    return {
        "status": "ok",
        "owner": owner,
        "repo": repo,
        "prior_tag": prior_tag,
        "fixed_tag": fixed_tag,
        "total_commits": total,
        "commits_in_page": len(commits),
        "security_related": security_related,
        "all_commits": all_commits[:50],
    }
