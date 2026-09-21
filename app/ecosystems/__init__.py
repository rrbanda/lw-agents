"""Ecosystem handler abstraction — Layers 11.1-11.3.

Provides a plugin architecture for supporting multiple language ecosystems
(Java/Maven, Python/PyPI, Gradle) with auto-detection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.http import fetch_json, head_check

# ============================================================================
# L11.1 — Ecosystem handler abstraction
# ============================================================================


class EcosystemHandler(ABC):
    """Abstract base class for ecosystem-specific operations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Ecosystem name (e.g. 'java', 'python')."""
        ...

    @abstractmethod
    def check_version_exists(self, package: str, version: str) -> dict[str, Any]:
        """Verify a version exists in the package registry."""
        ...

    @abstractmethod
    def detect_build_system(self, project_dir: Path) -> str:
        """Detect the build system from project files."""
        ...

    @abstractmethod
    def test_file_pattern(self, path: str) -> bool:
        """Return True if path is a test file in this ecosystem."""
        ...


class UnsupportedEcosystemError(Exception):
    pass


# ============================================================================
# L11.2 — Ecosystem registry with auto-detection
# ============================================================================


class EcosystemRegistry:
    """Registry for ecosystem handlers with auto-detection."""

    def __init__(self) -> None:
        self._handlers: dict[str, EcosystemHandler] = {}

    def register(self, handler: EcosystemHandler) -> None:
        self._handlers[handler.name] = handler

    def get(self, name: str) -> EcosystemHandler:
        try:
            return self._handlers[name]
        except KeyError:
            raise UnsupportedEcosystemError(
                f"Unsupported ecosystem: {name!r}. "
                f"Registered: {', '.join(sorted(self._handlers)) or '(none)'}"
            )

    def detect(self, component: str, *, group_id: str = "") -> str:
        """Auto-detect ecosystem from component name.

        ':' in component or non-empty group_id → Java.
        Otherwise → Python.
        """
        name = "java" if (group_id or ":" in component) else "python"
        if name not in self._handlers:
            raise UnsupportedEcosystemError(
                f"Detected {name!r} for {component!r} but no handler registered"
            )
        return name

    def supported(self) -> list[str]:
        return sorted(self._handlers)


# ============================================================================
# Java ecosystem handler
# ============================================================================


class JavaEcosystemHandler(EcosystemHandler):
    """Java/Maven ecosystem handler."""

    @property
    def name(self) -> str:
        return "java"

    def check_version_exists(self, package: str, version: str) -> dict[str, Any]:
        """Check Maven Central for a version."""
        import os
        parts = package.split(":")
        if len(parts) != 2:
            return {"exists": False, "error": f"Invalid Maven coordinate: {package}"}
        group_id, artifact_id = parts
        maven_repo = os.environ.get("MAVEN_REPO_URL", "https://repo1.maven.org/maven2")
        group_path = group_id.replace(".", "/")
        url = f"{maven_repo}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.pom"
        status, exists = head_check(url)
        return {
            "package": package, "version": version,
            "exists": exists, "status": "checked", "checked_url": url,
        }

    def detect_build_system(self, project_dir: Path) -> str:
        if (project_dir / "pom.xml").exists():
            return "maven"
        if (project_dir / "build.gradle").exists() or (project_dir / "build.gradle.kts").exists():
            return "gradle"
        if (project_dir / "build.xml").exists():
            return "ant"
        return "unknown"

    def test_file_pattern(self, path: str) -> bool:
        return (
            "src/test/" in path
            or path.endswith("Test.java")
            or path.endswith("Tests.java")
            or path.endswith("IT.java")
        )


# ============================================================================
# L11.3 — Python ecosystem handler
# ============================================================================


class PythonEcosystemHandler(EcosystemHandler):
    """Python/PyPI ecosystem handler."""

    @property
    def name(self) -> str:
        return "python"

    def check_version_exists(self, package: str, version: str) -> dict[str, Any]:
        """Check PyPI for a version."""
        url = f"https://pypi.org/pypi/{package}/{version}/json"
        status, data = fetch_json(url, max_retries=2)
        return {
            "package": package, "version": version,
            "exists": status == 200, "status": "checked",
        }

    def detect_build_system(self, project_dir: Path) -> str:
        if (project_dir / "pyproject.toml").exists():
            return "pyproject"
        if (project_dir / "setup.py").exists():
            return "setuptools"
        if (project_dir / "Pipfile").exists():
            return "pipenv"
        if (project_dir / "poetry.lock").exists():
            return "poetry"
        return "unknown"

    def test_file_pattern(self, path: str) -> bool:
        basename = path.split("/")[-1] if "/" in path else path
        return (
            "test/" in path
            or "tests/" in path
            or basename.startswith("test_")
            or basename.endswith("_test.py")
        )


# ============================================================================
# Default registry
# ============================================================================

default_registry = EcosystemRegistry()
default_registry.register(JavaEcosystemHandler())
default_registry.register(PythonEcosystemHandler())
