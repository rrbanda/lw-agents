"""Build verification tools — structured build execution and diagnostics.

Replaces the bare `mvn -B -q install` pattern with production-grade build
infrastructure: build system detection, Surefire/JUnit XML parsing,
error classification, Gradle support, deterministic fixers, build recipe
persistence, and per-attempt log writing.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.tools.diff_tools import classify_build_failure

logger = logging.getLogger(__name__)


# ============================================================================
# L4.4 — BuildVerificationResult model
# ============================================================================


class BuildOutcome(StrEnum):
    PASSED = "PASSED"
    TEST_FAILURE = "TEST_FAILURE"
    BUILD_FAILURE = "BUILD_FAILURE"
    TIMEOUT = "TIMEOUT"
    NO_TESTS = "NO_TESTS"


@dataclass
class SurefireResult:
    """Parsed JUnit/Surefire XML test results."""
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_errored: int = 0
    tests_skipped: int = 0
    failure_names: list[str] = field(default_factory=list)


@dataclass
class BuildVerificationResult:
    """Typed result from a build verification run."""
    success: bool = False
    build_system: str = ""
    compile_status: str = ""
    compile_output: str = ""
    test_status: str | None = None
    test_output: str | None = None
    test_results: SurefireResult | None = None
    outcome: BuildOutcome = BuildOutcome.BUILD_FAILURE
    error: str | None = None
    project_dir: str = ""
    classification: dict | None = None
    env_fix_attempts: list[dict] = field(default_factory=list)
    recipe: "BuildRecipe | None" = None

    def __post_init__(self):
        if self.compile_status == "timeout" or self.test_status == "timeout":
            self.outcome = BuildOutcome.TIMEOUT
        elif self.compile_status != "passed":
            self.outcome = BuildOutcome.BUILD_FAILURE
        elif self.test_status == "skipped" or self.test_results is None:
            self.outcome = BuildOutcome.NO_TESTS
        elif self.test_results and (
            self.test_results.tests_failed or self.test_results.tests_errored
        ):
            self.outcome = BuildOutcome.TEST_FAILURE
        elif self.test_results and self.test_results.tests_run == 0:
            self.outcome = BuildOutcome.NO_TESTS
        elif self.compile_status == "passed":
            self.outcome = BuildOutcome.PASSED
        self.success = self.outcome == BuildOutcome.PASSED

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "success": self.success,
            "outcome": self.outcome.value,
            "build_system": self.build_system,
            "compile_status": self.compile_status,
        }
        if self.test_status:
            d["test_status"] = self.test_status
        if self.test_results:
            d["test_results"] = {
                "run": self.test_results.tests_run,
                "passed": self.test_results.tests_passed,
                "failed": self.test_results.tests_failed,
                "errored": self.test_results.tests_errored,
                "skipped": self.test_results.tests_skipped,
                "failure_names": self.test_results.failure_names[:20],
            }
        if self.error:
            d["error"] = self.error
        if self.classification:
            d["classification"] = self.classification
        return d


# ============================================================================
# L4.6 — Build recipe persistence
# ============================================================================


@dataclass
class BuildRecipeEntry:
    """A single fix applied during the build-fix process."""
    source: str  # "deterministic:<name>" or "agent"
    description: str
    files_modified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "description": self.description,
            "files_modified": self.files_modified,
        }


@dataclass
class BuildRecipe:
    """Accumulated build-configuration fixes for auditability and replay."""
    entries: list[BuildRecipeEntry] = field(default_factory=list)
    build_args: list[str] | None = None
    file_snapshot: dict[str, str] = field(default_factory=dict)
    build_system: str = ""

    def add_entry(self, entry: BuildRecipeEntry) -> None:
        self.entries.append(entry)

    def snapshot_files(self, project_dir: str, rel_paths: list[str]) -> None:
        for rel in rel_paths:
            abs_path = os.path.join(project_dir, rel)
            try:
                with open(abs_path) as f:
                    self.file_snapshot[rel] = f.read()
            except OSError:
                pass

    def to_dict(self) -> dict:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "build_args": self.build_args,
            "file_snapshot": dict(self.file_snapshot),
            "build_system": self.build_system,
        }


# ============================================================================
# L4.1 — Build system detection
# ============================================================================


def detect_build_system(project_dir: str) -> dict[str, Any]:
    """Detect build system and project structure.

    Args:
        project_dir: Path to the project root.
    """
    p = Path(project_dir)
    has_maven = (p / "pom.xml").exists()
    has_gradle = (p / "build.gradle").exists() or (p / "build.gradle.kts").exists()
    has_ant = (p / "build.xml").exists()
    has_gradle_wrapper = (p / "gradlew").exists()
    modules = [d.parent.name for d in p.glob("*/pom.xml")]
    is_multi_module = len(modules) > 1

    build_system = "unknown"
    if has_maven:
        build_system = "maven"
    elif has_gradle:
        build_system = "gradle"
    elif has_ant:
        build_system = "ant"

    return {
        "build_system": build_system,
        "maven": has_maven,
        "gradle": has_gradle,
        "gradle_wrapper": has_gradle_wrapper,
        "ant": has_ant,
        "is_multi_module": is_multi_module,
        "modules": modules,
    }


# ============================================================================
# L4.2 — Structured Maven build
# ============================================================================


def run_maven_build(
    project_dir: str,
    skip_tests: bool = False,
    timeout: int = 600,
    extra_args: list[str] | None = None,
) -> BuildVerificationResult:
    """Run a Maven build with structured result reporting.

    Args:
        project_dir: Path to the Maven project.
        skip_tests: If True, skip test execution.
        timeout: Build timeout in seconds.
        extra_args: Additional Maven arguments.
    """
    cmd = ["mvn", "-B", "-q"]
    if skip_tests:
        cmd.append("-DskipTests")
    if extra_args:
        cmd.extend(extra_args)
    cmd.append("install" if skip_tests else "verify")

    try:
        result = subprocess.run(
            cmd, cwd=project_dir, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or b""
        partial = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else (raw or "")
        return BuildVerificationResult(
            build_system="maven",
            compile_status="timeout",
            compile_output=partial[-5000:],
            error=f"Build timed out after {timeout}s",
            project_dir=project_dir,
        )

    combined = result.stdout + (
        "\n" + result.stderr if result.stderr else ""
    )

    if result.returncode != 0:
        classification = classify_build_failure(combined)
        upper = combined.upper()
        is_compile_err = "COMPILATION ERROR" in upper or "BUILD FAILURE" in upper
        return BuildVerificationResult(
            build_system="maven",
            compile_status="failed" if is_compile_err else "failed",
            compile_output=combined[-5000:],
            error=f"Maven failed with exit code {result.returncode}",
            project_dir=project_dir,
            classification=classification,
        )

    # Compile passed — parse test results
    test_results = _parse_surefire_reports(project_dir)
    if skip_tests:
        test_status = "skipped"
    elif not test_results:
        test_status = "passed"
    elif test_results.tests_failed == 0 and test_results.tests_errored == 0:
        test_status = "passed"
    else:
        test_status = "failed"

    return BuildVerificationResult(
        build_system="maven",
        compile_status="passed",
        compile_output=combined[-2000:],
        test_status=test_status,
        test_output=combined[-3000:] if not skip_tests else None,
        test_results=test_results if not skip_tests else None,
        project_dir=project_dir,
    )


def _parse_surefire_reports(project_dir: str) -> SurefireResult | None:
    """Parse JUnit XML from surefire-reports directories."""
    result = SurefireResult()
    found = False

    for reports_dir in Path(project_dir).rglob("surefire-reports"):
        for xml_file in reports_dir.glob("TEST-*.xml"):
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                result.tests_run += int(root.get("tests", 0))
                result.tests_failed += int(root.get("failures", 0))
                result.tests_errored += int(root.get("errors", 0))
                result.tests_skipped += int(root.get("skipped", 0))
                failures = root.findall(".//testcase[failure]")
                errors = root.findall(".//testcase[error]")
                for tc in list(failures) + list(errors):
                    name = f"{tc.get('classname', '')}.{tc.get('name', '')}"
                    result.failure_names.append(name)
                found = True
            except ET.ParseError:
                continue

    if not found:
        return None

    result.tests_passed = (
        result.tests_run - result.tests_failed
        - result.tests_errored - result.tests_skipped
    )
    return result


# ============================================================================
# L4.3 — Gradle build support
# ============================================================================


def run_gradle_build(
    project_dir: str,
    skip_tests: bool = False,
    timeout: int = 600,
    extra_args: list[str] | None = None,
) -> BuildVerificationResult:
    """Run a Gradle build with structured result reporting.

    Auto-detects and uses the Gradle wrapper (gradlew) when available.

    Args:
        project_dir: Path to the Gradle project.
        skip_tests: If True, skip test execution.
        timeout: Build timeout in seconds.
        extra_args: Additional Gradle arguments.
    """
    wrapper = os.path.join(project_dir, "gradlew")
    gradle_cmd = wrapper if os.path.isfile(wrapper) else "gradle"

    cmd = [gradle_cmd, "--no-daemon", "-q"]
    if skip_tests:
        cmd.extend(["build", "-x", "test"])
    else:
        cmd.append("build")
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd, cwd=project_dir, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or b""
        partial = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else (raw or "")
        return BuildVerificationResult(
            build_system="gradle",
            compile_status="timeout",
            compile_output=partial[-5000:],
            error=f"Build timed out after {timeout}s",
            project_dir=project_dir,
        )

    combined = result.stdout + (
        "\n" + result.stderr if result.stderr else ""
    )

    if result.returncode != 0:
        classification = classify_build_failure(combined)
        return BuildVerificationResult(
            build_system="gradle", compile_status="failed",
            compile_output=combined[-5000:],
            error=f"Gradle failed with exit code {result.returncode}",
            project_dir=project_dir, classification=classification,
        )

    return BuildVerificationResult(
        build_system="gradle", compile_status="passed",
        compile_output=combined[-2000:],
        test_status="skipped" if skip_tests else "passed",
        project_dir=project_dir,
    )


# ============================================================================
# L4.5 — Deterministic build fixers
# ============================================================================


def _fix_unsupported_class_version(build_output: str, project_dir: str) -> str | None:
    """Fix JDK version mismatch by setting JAVA_HOME."""
    if "Unsupported class file major version" not in build_output:
        return None
    java_homes = {
        "8": os.environ.get("JAVA_8_HOME", ""),
        "11": os.environ.get("JAVA_11_HOME", ""),
        "17": os.environ.get("JAVA_17_HOME", ""),
        "21": os.environ.get("JAVA_21_HOME", ""),
    }
    for ver, home in java_homes.items():
        if home and os.path.isdir(home):
            os.environ["JAVA_HOME"] = home
            return f"Set JAVA_HOME to JDK {ver}: {home}"
    return None


def _fix_spring_format(build_output: str, project_dir: str) -> str | None:
    """Disable Spring Java Format plugin that fails on generated patches."""
    has_plugin = "spring-javaformat-maven-plugin" in build_output
    has_violations = "Formatting violations" in build_output
    if not has_plugin or not has_violations:
        return None
    pom_path = os.path.join(project_dir, "pom.xml")
    if not os.path.exists(pom_path):
        return None
    try:
        content = Path(pom_path).read_text()
        if "spring-javaformat-maven-plugin" in content:
            content = re.sub(
                r"<plugin>\s*<groupId>io\.spring\.javaformat"
                r"</groupId>.*?</plugin>",
                "<!-- spring-javaformat disabled -->",
                content, flags=re.DOTALL
            )
            Path(pom_path).write_text(content)
            return "Disabled spring-javaformat-maven-plugin (formatting check)"
    except OSError:
        pass
    return None


def _fix_missing_toolchains(build_output: str, project_dir: str) -> str | None:
    """Skip maven-toolchains-plugin when no matching JDK toolchain available."""
    if "No toolchain found for type jdk" not in build_output:
        return None
    pom_path = os.path.join(project_dir, "pom.xml")
    if not os.path.exists(pom_path):
        return None
    try:
        content = Path(pom_path).read_text()
        if "maven-toolchains-plugin" in content:
            content = re.sub(
                r"<plugin>\s*<groupId>org\.apache\.maven\.plugins</groupId>\s*"
                r"<artifactId>maven-toolchains-plugin</artifactId>.*?</plugin>",
                "<!-- toolchains plugin disabled by build fixer -->", content, flags=re.DOTALL
            )
            Path(pom_path).write_text(content)
            return "Disabled maven-toolchains-plugin (no matching JDK)"
    except OSError:
        pass
    return None


DETERMINISTIC_FIXERS = [
    _fix_unsupported_class_version,
    _fix_spring_format,
    _fix_missing_toolchains,
]


def apply_deterministic_fixes(
    build_output: str,
    project_dir: str,
) -> list[BuildRecipeEntry]:
    """Try each deterministic fixer and return entries for those that succeeded."""
    entries: list[BuildRecipeEntry] = []
    for fixer in DETERMINISTIC_FIXERS:
        result = fixer(build_output, project_dir)
        if result:
            entries.append(BuildRecipeEntry(
                source=f"deterministic:{fixer.__name__}",
                description=result,
            ))
    return entries


# ============================================================================
# L4.7 — Build log persistence
# ============================================================================


def write_build_logs(
    run_dir: str,
    prefix: str,
    build_result: BuildVerificationResult,
) -> None:
    """Write build logs to the run directory for debugging.

    Args:
        run_dir: Directory to write logs into.
        prefix: Filename prefix (e.g. "baseline", "patched").
        build_result: The build result containing outputs.
    """
    try:
        os.makedirs(run_dir, exist_ok=True)
        if build_result.compile_output:
            Path(run_dir, f"{prefix}_compile.log").write_text(
                build_result.compile_output, encoding="utf-8"
            )
        if build_result.test_output:
            Path(run_dir, f"{prefix}_test.log").write_text(
                build_result.test_output, encoding="utf-8"
            )
        for i, attempt in enumerate(build_result.env_fix_attempts):
            output = attempt.get("full_output", "")
            if output:
                Path(run_dir, f"{prefix}_fix_{i}.log").write_text(output, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write %s build logs: %s", prefix, exc)
