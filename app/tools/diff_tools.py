"""Diff analysis and classification tools — deterministic intelligence.

No LLM tokens burned. These tools give agents and policy gates objective,
evidence-based analysis of code changes, diffs, and commit subjects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

# ============================================================================
# L3.1 — Diff analysis
# ============================================================================

FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"#\s*nosec", "nosec comment (suppresses security linter)"),
    (r"//\s*noqa", "noqa comment (suppresses linter)"),
    (r"@SuppressWarnings", "SuppressWarnings annotation"),
    (r"verify\s*=\s*False", "TLS verification disabled"),
    (r"rejectUnauthorized:\s*false", "TLS rejection disabled"),
    (r"try:\s*\n\s*.*\n\s*except.*:\s*pass", "bare except-pass (swallows errors)"),
    (r"@PermitAll", "PermitAll annotation (removes auth)"),
    (r"FIXME.*security", "FIXME security comment left in"),
]

_DOC_EXTENSIONS = frozenset({".md", ".txt", ".rst", ".adoc", ".html"})
_DOC_PATHS = ("CHANGELOG", "RELEASE-NOTES", "README", "docs/", "src/site/")
_SOURCE_EXTENSIONS = frozenset({
    ".java", ".py", ".go", ".c", ".cpp", ".rs", ".kt", ".scala", ".groovy",
})
_CONFIG_EXTENSIONS = frozenset({
    ".xml", ".yaml", ".yml", ".properties", ".json", ".toml",
    ".gradle", ".gradle.kts",
})
_TEST_INDICATORS = ("test/", "tests/", "Test.java", "Tests.java", "IT.java", "_test.py", "test_")


def analyze_diff(diff_text: str) -> dict[str, Any]:
    """Analyze a unified diff deterministically.

    Returns file classification, line counts, forbidden pattern violations,
    doc-only flag, pom-only flag, and file lists.

    Args:
        diff_text: Unified diff text.
    """
    if not diff_text:
        return {
            "total_files": 0, "files": [], "lines_added": 0, "lines_removed": 0,
            "forbidden_patterns": [], "is_doc_only": False, "is_pom_only": False,
            "source_files": [], "test_files": [], "config_files": [], "doc_files": [],
        }

    files = re.findall(r"^diff --git a/.+ b/(.+)$", diff_text, re.MULTILINE)
    added = len(re.findall(r"^\+[^+]", diff_text, re.MULTILINE))
    removed = len(re.findall(r"^-[^-]", diff_text, re.MULTILINE))

    violations = []
    for pattern, desc in FORBIDDEN_PATTERNS:
        if re.search(pattern, diff_text, re.MULTILINE):
            violations.append(desc)

    source_files, test_files, config_files, doc_files = [], [], [], []
    for f in files:
        basename = f.split("/")[-1] if "/" in f else f
        ext = "." + basename.rsplit(".", 1)[1] if "." in basename else ""

        if any(ind in f for ind in _TEST_INDICATORS):
            test_files.append(f)
        elif ext in _SOURCE_EXTENSIONS:
            source_files.append(f)
        elif ext in _DOC_EXTENSIONS or any(p in f for p in _DOC_PATHS):
            doc_files.append(f)
        elif ext in _CONFIG_EXTENSIONS:
            config_files.append(f)
        else:
            config_files.append(f)

    is_doc_only = bool(files) and all(
        any(f.endswith(ext) for ext in _DOC_EXTENSIONS) or any(p in f for p in _DOC_PATHS)
        for f in files
    )
    is_pom_only = bool(files) and all(f.endswith("pom.xml") for f in files)

    return {
        "total_files": len(files),
        "files": files,
        "lines_added": added,
        "lines_removed": removed,
        "forbidden_patterns": violations,
        "is_doc_only": is_doc_only,
        "is_pom_only": is_pom_only,
        "source_files": source_files,
        "test_files": test_files,
        "config_files": config_files,
        "doc_files": doc_files,
    }


# ============================================================================
# L3.2 — ReDoS / regex safety scanner
# ============================================================================

_UNBOUNDED_RANGE = re.compile(r"\{\d*,\}")
_SINK_BEFORE = re.compile(
    r"(?:Pattern\.compile|\.matches|\.split|\.replaceAll|\.replaceFirst)\s*\(\s*$"
    r"|\bPattern\s+\w+\s*=\s*$"
    r"|\b\w*(?:PATTERN|REGEX|_RE)\w*\s*=\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RegexSmell:
    """A quantified alternation group flagged as a ReDoS/StackOverflow risk."""
    group: str
    quantifier: str
    line: int = 0


def _find_alternation_groups(pattern: str) -> list[RegexSmell]:
    """Find quantified alternation groups like (a|b)* in a regex pattern."""
    smells: list[RegexSmell] = []
    stack: list[list] = []
    in_class = False
    i, n = 0, len(pattern)

    while i < n:
        c = pattern[i]
        if c == "\\":
            i += 2
            continue
        if in_class:
            in_class = c != "]"
        elif c == "[":
            in_class = True
        elif c == "(":
            stack.append([i, False])
        elif c == "|" and stack:
            stack[-1][1] = True
        elif c == ")" and stack:
            start, has_alt = stack.pop()
            if has_alt and i + 1 < n and pattern[i + 1] in ("*", "+"):
                quant = pattern[i + 1]
                if i + 2 >= n or pattern[i + 2] != "+":
                    smells.append(RegexSmell(
                        group=pattern[start:i + 2],
                        quantifier=quant,
                    ))
            if has_alt and stack:
                stack[-1][1] = True
        i += 1
    return smells


def check_regex_safety(diff_text: str) -> dict[str, Any]:
    """Detect ReDoS-prone regex patterns in added lines of a diff.

    Scans only added lines in .java files for quantified alternation groups.

    Args:
        diff_text: Unified diff text.
    """
    if not diff_text:
        return {"safe": True, "smells": []}

    smells: list[dict] = []
    current_file = ""
    line_num = 0

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ "):
            current_file = raw_line[4:].strip().removeprefix("b/")
            continue
        if raw_line.startswith("@@ "):
            m = re.search(r"\+(\d+)", raw_line)
            line_num = int(m.group(1)) if m else 0
            continue
        if not current_file.endswith(".java"):
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            line_num += 1
            line = raw_line[1:]
            if line.strip().startswith("//"):
                continue
            for string_match in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"', line):
                literal = string_match.group(1)
                for smell in _find_alternation_groups(literal):
                    smells.append({
                        "file": current_file,
                        "line": line_num,
                        "group": smell.group,
                        "quantifier": smell.quantifier,
                        "risk": "Quantified alternation group — potential ReDoS/StackOverflow",
                    })
        elif not raw_line.startswith("-"):
            line_num += 1

    return {"safe": len(smells) == 0, "smells": smells}


# ============================================================================
# L3.3 — Build failure classifier
# ============================================================================

_NETWORK_ERROR_RE = re.compile(
    r"Received status code (?:429|5\d\d) from server"
    r"|Could not GET 'https?://"
    r"|Could not get resource 'https?://"
    r"|Connection (?:refused|reset|timed out)"
    r"|UnknownHostException"
    r"|Read timed out",
    re.IGNORECASE,
)
_COMPILATION_ERROR_RE = re.compile(r"error: cannot find symbol")
_SOURCE_LEVEL_ERROR_RE = re.compile(r"(?:is|are) not supported in -source (\d[\d.]*)")
_PLUGIN_NOT_FOUND_RE = re.compile(
    r"Plugin (?:with id '([^']+)'|\[id: '([^']+)'[^\]]*\])"
    r" (?:not found|was not found)"
)
_DEP_RESOLUTION_RE = re.compile(
    r"Could not (?:resolve|find) (?:dependenc(?:y|ies)"
    r"|all (?:artifacts|files)|io\.|org\.|com\.|me\.)",
    re.IGNORECASE,
)
_UNSUPPORTED_CLASS_RE = re.compile(r"Unsupported class file major version")
_MAVEN_PLUGIN_RE = re.compile(
    r"Plugin ([\w.\-:]+) or one of its dependencies"
    r" could not be resolved"
)
_CONTAINER_PULL_RE = re.compile(r"(?:manifest unknown|unable to copy from source docker://)")


def classify_build_failure(build_output: str) -> dict[str, Any]:
    """Classify a build failure into actionable categories.

    Categories:
    - PATCH_ERROR: Compilation error from the applied patch
    - ENVIRONMENT_ERROR: Build config, plugin, dependency issues
    - PRE_EXISTING: Failures unrelated to the patch
    - NETWORK_ERROR: Unreachable repos, rate limiting

    Args:
        build_output: Combined stdout+stderr from the build.
    """
    if not build_output:
        return {"category": "UNKNOWN", "description": "No build output"}

    # Network errors first (highest priority)
    if _NETWORK_ERROR_RE.search(build_output):
        return {
            "category": "NETWORK_ERROR",
            "description": "Repository unreachable or rate-limited",
            "retryable": False,
        }

    # Source level errors (patch error)
    m = _SOURCE_LEVEL_ERROR_RE.search(build_output)
    if m:
        return {
            "category": "PATCH_ERROR",
            "description": f"Java feature not supported in -source {m.group(1)}",
            "retryable": True,
        }

    # Container pull failure
    if _CONTAINER_PULL_RE.search(build_output):
        return {
            "category": "ENVIRONMENT_ERROR",
            "description": "Container image pull failed",
            "retryable": False,
        }

    # Plugin not found
    m = _PLUGIN_NOT_FOUND_RE.search(build_output) or _MAVEN_PLUGIN_RE.search(build_output)
    if m:
        plugin = m.group(1) or m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
        return {
            "category": "ENVIRONMENT_ERROR",
            "description": f"Plugin not found: {plugin}",
            "retryable": True,
        }

    # Dependency resolution
    if _DEP_RESOLUTION_RE.search(build_output):
        return {
            "category": "ENVIRONMENT_ERROR",
            "description": "Could not resolve dependency",
            "retryable": True,
        }

    # JDK mismatch
    if _UNSUPPORTED_CLASS_RE.search(build_output):
        return {
            "category": "ENVIRONMENT_ERROR",
            "description": "Unsupported class file major version (JDK mismatch)",
            "retryable": True,
        }

    # Compilation error (likely patch-related)
    if _COMPILATION_ERROR_RE.search(build_output):
        return {
            "category": "PATCH_ERROR",
            "description": "Compilation error: cannot find symbol",
            "retryable": True,
        }

    # Generic test failure
    if "test failure" in build_output.lower() or "tests run:" in build_output.lower():
        return {
            "category": "PATCH_ERROR",
            "description": "Test failure",
            "retryable": True,
        }

    return {"category": "UNKNOWN", "description": "Unclassified build failure", "retryable": True}


# ============================================================================
# L3.4 — Non-security commit filter
# ============================================================================

_NON_SECURITY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("release-prep", re.compile(
        r"prepare for next development iteration"
        r"|prepare release\b"
        r"|\[maven-release-plugin\]"
        r"|^\[release\] "
    )),
    ("build-config", re.compile(
        r"maven plugin configuration"
        r"|gpg[\s/]signing config"
        r"|javadoc plugin"
        r"|updated? build (?:config|script)"
    )),
    ("dependency-upgrade", re.compile(
        r"general dependency version upgrade"
        r"|general maven plugin version upgrade"
        r"|bump(?:ed)? \S+ from \S+ to \S+"
    )),
    ("housekeeping", re.compile(
        r"\.gitignore"
        r"|^updated headers$"
        r"|^fix(?:ed)? typos?$"
        r"|^updated? copyright"
    )),
    ("version-bump", re.compile(
        r"^(?:set |bump(?:ed)? )?version to \S+$"
        r"|^\d+\.\d+[\d.]*(?:[._-](?:release|final|ga|snapshot))?$"
    )),
]


def filter_non_security_commits(
    commits: list[dict[str, Any]],
) -> dict[str, Any]:
    """Filter out commits unlikely to be security fixes by subject pattern.

    Returns kept and excluded lists. If ALL would be excluded, returns
    the original list unchanged (fail-safe).

    Args:
        commits: List of dicts with "subject" key.
    """
    kept, excluded = [], []

    for c in commits:
        subject = (c.get("subject") or "").lower().strip()
        if not subject:
            kept.append(c)
            continue

        matched = None
        for category, pattern in _NON_SECURITY_PATTERNS:
            if pattern.search(subject):
                matched = category
                break

        if matched:
            excluded.append({**c, "excluded_reason": matched})
        else:
            kept.append(c)

    if not kept and excluded:
        return {"kept": commits, "excluded": [], "note": "All excluded — returning original list"}

    return {"kept": kept, "excluded": excluded}


# ============================================================================
# L3.5 — Intelligent diff filtering
# ============================================================================

class _Priority(IntEnum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


def filter_diff_by_priority(
    diff_text: str,
    target_component: str = "",
    max_chars: int = 8000,
) -> str:
    """Filter a diff by priority when it exceeds the context window limit.

    Priority order:
    - CRITICAL: Target component main source (always full)
    - HIGH: Other main source files (full if space)
    - MEDIUM: Test files (filename + stats only)
    - LOW: Docs, configs (filename only)

    Args:
        diff_text: Full unified diff text.
        target_component: Component name to prioritize.
        max_chars: Maximum output size.
    """
    if len(diff_text) <= max_chars:
        return diff_text

    sections: list[tuple[str, str, int]] = []
    current_file = ""
    current_lines: list[str] = []

    def flush():
        if current_file and current_lines:
            content = "\n".join(current_lines)
            sections.append((current_file, content, len(content)))

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            flush()
            m = re.search(r" b/(.+)$", line)
            current_file = m.group(1) if m else line
            current_lines = [line]
        else:
            current_lines.append(line)
    flush()

    def priority(filename: str) -> _Priority:
        if any(ind in filename for ind in _TEST_INDICATORS):
            return _Priority.MEDIUM
        is_doc = any(filename.endswith(ext) for ext in _DOC_EXTENSIONS)
        is_doc = is_doc or any(p in filename for p in _DOC_PATHS)
        if is_doc:
            return _Priority.LOW
        if target_component and target_component.lower() in filename.lower():
            return _Priority.CRITICAL
        if any(filename.endswith(ext) for ext in _SOURCE_EXTENSIONS):
            return _Priority.HIGH
        return _Priority.LOW

    prioritized = sorted(sections, key=lambda s: priority(s[0]))

    output_parts: list[str] = []
    remaining = max_chars
    for filename, content, size in prioritized:
        p = priority(filename)
        if p <= _Priority.HIGH and size <= remaining:
            output_parts.append(content)
            remaining -= size
        elif p == _Priority.MEDIUM:
            summary = f"# {filename} (test file, {size} chars — omitted for space)"
            output_parts.append(summary)
            remaining -= len(summary)
        else:
            summary = f"# {filename} ({size} chars — omitted)"
            output_parts.append(summary)
            remaining -= len(summary)

        if remaining <= 0:
            break

    return "\n".join(output_parts)


# ============================================================================
# L3.6 — Prompt injection detection
# ============================================================================

_INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r"\bignore\s+(?:all\s+)?(?:previous|prior)"
     r"\s+(?:instructions?|directives?|commands?)", "instruction_override"),
    (r"\bignore\s+all\s+(?:instructions?|directives?|commands?)", "instruction_override"),
    (r"\bdisregard\s+(?:all\s+)?(?:previous|prior)", "instruction_override"),
    (r"\bforget\s+(?:everything|all|previous)", "instruction_override"),
    (r"\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(admin|system|root|god)", "role_confusion"),
    (r"^(system|assistant|user|admin):\s*", "role_marker"),
    (r"\balways\s+(return|respond|say|output)", "output_manipulation"),
    (r"\b(skip|bypass|disable)\s+(all\s+)?(security|safety|validation)\b", "security_bypass"),
    (r"\bsend\s+(all|the|this|data|results?|code|output)\s+.+?\s+to\s+https?://", "exfiltration"),
    (r"\bpost\s+.+?\s+to\s+https?://", "exfiltration"),
    (r"\n{5,}", "context_break"),
    (r"={20,}", "context_break"),
]

_DESCRIPTIVE_MODAL_RE = re.compile(
    r"\b(?:can|could|may|might|allows?|able\s+to|used\s+to|attempt(?:s|ed)?\s+to)\b",
    re.IGNORECASE,
)


def detect_prompt_injection(text: str) -> dict[str, Any]:
    """Scan text for prompt injection attempts.

    Uses regex patterns with descriptive-context exemption for CVE language.

    Args:
        text: Text to scan (CVE description, commit messages, etc.).
    """
    if not text or len(text.strip()) < 10:
        return {"is_safe": True, "threats": [], "risk_level": "low"}

    threats: list[str] = []
    for pattern, threat_type in _INJECTION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            descriptive_types = ("security_bypass", "instruction_override", "role_confusion")
            if threat_type in descriptive_types:
                window = text[max(0, match.start() - 60):match.start()]
                last_break = max(window.rfind("."), window.rfind("!"), window.rfind("\n"))
                clause = window[last_break + 1:] if last_break >= 0 else window
                if _DESCRIPTIVE_MODAL_RE.search(clause):
                    continue
            threats.append(threat_type)

    if not threats:
        return {"is_safe": True, "threats": [], "risk_level": "low"}

    critical = any(t in threats for t in ["instruction_override", "role_confusion", "exfiltration"])
    return {
        "is_safe": False,
        "threats": list(set(threats)),
        "risk_level": "critical" if critical else "medium",
    }


def sanitize_text(text: str, threats: list[str]) -> str:
    """Remove detected injection patterns from text.

    Args:
        text: Original text.
        threats: List of threat types detected.
    """
    sanitized = text

    if "role_marker" in threats or "role_confusion" in threats:
        sanitized = re.sub(
            r"^(system|assistant|user|admin|root):\s*", "",
            sanitized, flags=re.IGNORECASE | re.MULTILINE
        )
    if "instruction_override" in threats:
        for p in [
            r"ignore\s+(previous|all|prior)\s+(instructions?|directives?|commands?)[^\n]*",
            r"disregard\s+(previous|all|prior)[^\n]*",
            r"forget\s+(everything|all|previous)[^\n]*",
        ]:
            sanitized = re.sub(p, "[REMOVED]", sanitized, flags=re.IGNORECASE)
    if "security_bypass" in threats:
        sanitized = re.sub(
            r"(skip|bypass|disable)\s+(all|security|safety|validation)[^\n]*",
            "[REMOVED]", sanitized, flags=re.IGNORECASE
        )
    if "exfiltration" in threats:
        sanitized = re.sub(
            r"(send|post)\s+.+?\s+to\s+(https?://[^\s]+)",
            r"\1 [URL REMOVED]", sanitized, flags=re.IGNORECASE
        )
    if "context_break" in threats:
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        sanitized = re.sub(r"={10,}", "=" * 10, sanitized)

    return sanitized.strip()


# ============================================================================
# L3.7 — Exploit source trust scoring
# ============================================================================

TRUSTED_ORGS = frozenset({
    "spring-projects", "apache", "eclipse", "kubernetes", "docker",
    "nodejs", "microsoft", "google", "netty", "FasterXML", "qos-ch",
})
SAFE_ORGS = frozenset({"projectdiscovery", "offensive-security"})
SAFE_DOMAINS = frozenset({"www.exploit-db.com", "exploit-db.com"})
ADVISORY_DOMAINS = frozenset({
    "www.herodevs.com", "herodevs.com", "security.snyk.io", "snyk.io",
    "nvd.nist.gov", "cve.mitre.org", "spring.io",
})


def score_exploit_source(url: str) -> dict[str, Any]:
    """Score the trustworthiness of an exploit/PoC source URL.

    Tiers: TRUSTED (80-100), SAFE (60-79), ADVISORY (50-59),
    COMMUNITY (40-49), UNTRUSTED (0-39).

    Args:
        url: URL of the exploit source.
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()

    if any(domain == d or domain.endswith("." + d) for d in ADVISORY_DOMAINS):
        return {"url": url, "tier": "ADVISORY", "score": 55.0, "can_download": False}
    if any(domain == d or domain.endswith("." + d) for d in SAFE_DOMAINS):
        return {"url": url, "tier": "SAFE", "score": 70.0, "can_download": True}

    if domain == "github.com":
        m = re.search(r"^/([^/]+)", path)
        if m:
            org = m.group(1)
            if org.lower() in {o.lower() for o in TRUSTED_ORGS}:
                return {"url": url, "tier": "TRUSTED", "score": 95.0, "can_download": True}
            if org.lower() in {o.lower() for o in SAFE_ORGS}:
                return {"url": url, "tier": "SAFE", "score": 70.0, "can_download": True}
            return {"url": url, "tier": "COMMUNITY", "score": 35.0, "can_download": True,
                    "warning": "Unknown GitHub org — verify before use"}

    return {"url": url, "tier": "UNTRUSTED", "score": 10.0, "can_download": False,
            "warning": "Unknown domain — manual review required"}
