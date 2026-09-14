"""Diff proof tools — snapshot before, verify after.

Inspired by VVAH's harness_amend() pattern: replace the agent's
self-report with what git diff actually shows. Evidence over claims.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any


def snapshot_workspace(repo_path: str) -> dict[str, str]:
    """Capture file hashes before the coding agent edits.

    Returns a dict of {relative_path: sha256_hash} for all tracked files.
    Call this BEFORE invoke_coding_agent, store in session state.

    Args:
        repo_path: Path to the repository root.
    """
    result: dict[str, str] = {}
    repo = Path(repo_path)

    try:
        ls_output = subprocess.run(
            ["git", "ls-files"], cwd=repo_path,
            capture_output=True, text=True, timeout=10,
        )
        if ls_output.returncode == 0:
            for rel_path in ls_output.stdout.strip().splitlines():
                full_path = repo / rel_path
                if full_path.is_file():
                    content = full_path.read_bytes()
                    result[rel_path] = hashlib.sha256(content).hexdigest()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return result


def verify_changes(repo_path: str, snapshot: dict[str, str]) -> dict[str, Any]:
    """Compare current state against pre-edit snapshot.

    Returns evidence-based proof of what changed — NOT the agent's
    self-report. This is the diff proof that policy gates validate.

    Args:
        repo_path: Path to the repository root.
        snapshot: The dict returned by snapshot_workspace before edits.
    """
    repo = Path(repo_path)
    changed_files: list[str] = []
    new_files: list[str] = []

    # Compare hashes
    for rel_path, old_hash in snapshot.items():
        full_path = repo / rel_path
        if full_path.is_file():
            new_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
            if new_hash != old_hash:
                changed_files.append(rel_path)
        else:
            changed_files.append(rel_path)  # deleted

    # Check for new untracked files
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        if status.returncode == 0:
            for line in status.stdout.strip().splitlines():
                if line.startswith("?? "):
                    new_files.append(line[3:].strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Get actual diff content
    diff_content = ""
    try:
        diff = subprocess.run(
            ["git", "diff", "--no-color"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        if diff.returncode == 0:
            diff_content = diff.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    all_changed = changed_files + new_files
    return {
        "changed_files": all_changed,
        "new_files": new_files,
        "diff_content": diff_content[:10000],  # cap for session state
        "diff_lines": diff_content.count("\n"),
        "has_changes": len(all_changed) > 0,
    }
