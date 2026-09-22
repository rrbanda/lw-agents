"""SCM tools — create issues and pull requests on GitLab / GitHub.

These are ADK FunctionTools that agents call. SCM credentials come from
environment variables (SCM_PROVIDER, SCM_HOST, SCM_TOKEN, SCM_USERNAME).
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any

from google.adk.tools import FunctionTool


def create_scm_issue(
    repo_url: str,
    title: str,
    body: str,
    labels: str,
    deduplicate: bool,
) -> dict[str, Any]:
    """Create a GitLab or GitHub issue for a vulnerability.

    Args:
        repo_url: HTTPS URL of the repository.
        title: Issue title.
        body: Issue body in markdown format.
        labels: Comma-separated labels to apply, e.g. security,cve,critical.
        deduplicate: If true, skip creation if an open issue with matching CVE exists.
    """
    provider = os.environ.get("SCM_PROVIDER", "gitlab")
    host = os.environ.get("SCM_HOST", "")
    token = os.environ.get("SCM_TOKEN", "")
    repo_path = _extract_repo_path(repo_url)
    env = _scm_env(provider, host, token)

    if deduplicate:
        cve_id = _extract_cve_from_title(title)
        if cve_id and _issue_exists(provider, repo_path, cve_id, env):
            return {"created": False, "skipped_reason": f"Open issue for {cve_id} already exists"}

    label_args = _label_args(provider, labels)

    if provider == "gitlab":
        cmd = [
            "glab",
            "issue",
            "create",
            "-R",
            repo_path,
            "--title",
            title,
            "--description",
            body,
            "--yes",
        ] + label_args
    elif provider == "github":
        cmd = [
            "gh",
            "issue",
            "create",
            "-R",
            repo_path,
            "--title",
            title,
            "--body",
            body,
        ] + label_args
    else:
        return {"created": False, "error": f"Unsupported SCM_PROVIDER: {provider}"}

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    except FileNotFoundError:
        return {"created": False, "error": f"SCM CLI not found: {cmd[0]}"}
    except subprocess.TimeoutExpired:
        return {"created": False, "error": "SCM CLI timed out after 30s"}
    return {
        "created": result.returncode == 0,
        "issue_url": _extract_url(result.stdout + result.stderr),
        "error": result.stderr.strip() if result.returncode != 0 else None,
    }


create_scm_issue_tool = FunctionTool(create_scm_issue, require_confirmation=False)


def clone_repository(
    repo_url: str,
    branch: str = "main",
    target_dir: str = "/tmp/workspace",
) -> dict[str, Any]:
    """Clone a git repository for editing.

    Used by the remediation and test-generation agents to get source code
    when running as a remote service (no shared Tekton workspace).

    Args:
        repo_url: HTTPS URL of the repository.
        branch: Branch to clone.
        target_dir: Local directory to clone into.
    """
    host = os.environ.get("SCM_HOST", "")
    token = os.environ.get("SCM_TOKEN", "")
    username = os.environ.get("SCM_USERNAME", "oauth2")
    repo_path = _extract_repo_path(repo_url)

    # Clean target dir if it exists
    if os.path.exists(target_dir):
        import shutil

        shutil.rmtree(target_dir)

    # Build authenticated URL — only inject credentials if repo is on SCM_HOST
    from urllib.parse import urlparse

    parsed = urlparse(repo_url)
    repo_host = parsed.hostname or ""

    if host and token and (repo_host == host or not repo_host):
        clone_url = f"https://{username}:{token}@{host}/{repo_path}.git"
    elif host and token and "github.com" not in repo_host:
        # Different private host — try with token anyway
        clone_url = f"https://{username}:{token}@{repo_host}/{repo_path}.git"
    else:
        # Public repo or unknown host — clone without credentials
        clone_url = repo_url

    try:
        result = subprocess.run(
            ["git", "clone", "--branch", branch, "--depth", "1", clone_url, target_dir],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return {"cloned": False, "error": result.stderr.strip()}
        return {"cloned": True, "path": target_dir}
    except FileNotFoundError:
        return {"cloned": False, "error": "git CLI not found"}
    except subprocess.TimeoutExpired:
        return {"cloned": False, "error": "git clone timed out after 120s"}
    except Exception as e:
        return {"cloned": False, "error": str(e)}


clone_repository_tool = FunctionTool(clone_repository, require_confirmation=False)


def create_pull_request(
    repo_url: str,
    local_repo_path: str,
    branch: str,
    base: str,
    title: str,
    body: str,
    files_to_stage: str,
) -> dict[str, Any]:
    """Stage files, commit, push, and create a PR/MR.

    Args:
        repo_url: HTTPS URL of the repository.
        local_repo_path: Local filesystem path to the cloned repository.
        branch: Branch name to create and push.
        base: Base branch to merge into, e.g. main.
        title: PR/MR title.
        body: PR/MR description in markdown.
        files_to_stage: Space-separated pathspecs to stage, e.g. pom.xml REMEDIATION.md.
    """
    provider = os.environ.get("SCM_PROVIDER", "gitlab")
    host = os.environ.get("SCM_HOST", "")
    token = os.environ.get("SCM_TOKEN", "")
    username = os.environ.get("SCM_USERNAME", "oauth2")
    env = _scm_env(provider, host, token)

    try:
        _git(local_repo_path, ["config", "safe.directory", local_repo_path])
        _git(local_repo_path, ["config", "user.email", f"tekton-bot@{host}"])
        _git(local_repo_path, ["config", "user.name", "TSSC Remediation Bot"])

        for pathspec in files_to_stage.split():
            _git(local_repo_path, ["add", "-A", "--", pathspec])

        diff = _git(local_repo_path, ["diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return {"created": False, "pr_url": "", "reason": "No changes to submit"}

        _git(local_repo_path, ["checkout", "-b", branch], check=True)
        _git(local_repo_path, ["commit", "-m", title], check=True)

        scm_path = _extract_repo_path(repo_url)
        push_remote = f"https://{host}/{scm_path}.git"
        askpass_path, push_env = _setup_git_credential_helper(
            local_repo_path,
            host,
            username,
            token,
        )
        try:
            _git(local_repo_path, ["push", push_remote, branch], check=True, env=push_env)
        finally:
            if askpass_path:
                os.unlink(askpass_path)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        err = getattr(exc, "stderr", str(exc))
        return {"created": False, "error": f"git {exc.cmd} failed: {err}"}
    except FileNotFoundError:
        return {"created": False, "error": "git CLI not found"}

    if provider == "gitlab":
        cmd = [
            "glab",
            "mr",
            "create",
            "--source-branch",
            branch,
            "--target-branch",
            base,
            "--title",
            title,
            "--description",
            body,
            "--yes",
        ]
    elif provider == "github":
        cmd = [
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ]
    else:
        return {"created": False, "error": f"Unsupported provider: {provider}"}

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    except FileNotFoundError:
        return {"created": False, "error": f"SCM CLI not found: {cmd[0]}"}
    except subprocess.TimeoutExpired:
        return {"created": False, "error": "SCM CLI timed out creating PR"}
    return {
        "created": result.returncode == 0,
        "pr_url": _extract_url(result.stdout + result.stderr),
        "branch": branch,
    }


create_pull_request_tool = FunctionTool(create_pull_request, require_confirmation=False)


def _scm_env(provider: str, host: str, token: str) -> dict[str, str]:
    env = dict(os.environ)
    if provider == "gitlab":
        env.update(GITLAB_HOST=host, GITLAB_TOKEN=token)
    elif provider == "github":
        env.update(GH_HOST=host, GH_TOKEN=token)
    return env


def _git(
    repo: str,
    args: list[str],
    *,
    check: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git"] + args,
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            ["git"] + args,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def _setup_git_credential_helper(
    repo: str,
    host: str,
    username: str,
    token: str,
) -> tuple[str, dict[str, str]]:
    """Configure git to authenticate via GIT_ASKPASS instead of URL-embedded tokens.

    Returns (askpass_path, env_dict). The caller MUST delete askpass_path
    after the git operation completes to avoid leaving tokens on disk.
    """
    import shlex
    import stat
    import tempfile

    askpass = tempfile.NamedTemporaryFile(
        mode="w",
        prefix="git-askpass-",
        suffix=".sh",
        delete=False,
    )
    askpass.write(f"#!/bin/sh\necho {shlex.quote(token)}\n")
    askpass.close()
    os.chmod(askpass.name, stat.S_IRWXU)

    env = dict(os.environ)
    env["GIT_ASKPASS"] = askpass.name
    env["GIT_TERMINAL_PROMPT"] = "0"
    return askpass.name, env


def _extract_repo_path(url: str) -> str:
    path = re.sub(r"^https?://", "", url)
    path = re.sub(r"^[^/]+/", "", path)
    return re.sub(r"\.git$", "", path)


def _extract_url(text: str) -> str:
    m = re.search(r"https?://\S+", text)
    return m.group(0) if m else ""


def _extract_cve_from_title(title: str) -> str:
    m = re.search(r"CVE-\d{4}-\d+", title, re.I)
    return m.group(0) if m else ""


def _label_args(provider: str, labels: str) -> list[str]:
    if not labels.strip():
        return []
    if provider == "gitlab":
        return ["--label", labels]
    return [arg for lbl in labels.split(",") for arg in ("--label", lbl.strip())]


def _issue_exists(
    provider: str,
    repo: str,
    cve_id: str,
    env: dict[str, str],
) -> bool:
    try:
        if provider == "gitlab":
            r = subprocess.run(
                ["glab", "issue", "list", "-R", repo, "--search", cve_id],
                capture_output=True,
                text=True,
                env=env,
                timeout=15,
            )
        elif provider == "github":
            r = subprocess.run(
                [
                    "gh",
                    "issue",
                    "list",
                    "-R",
                    repo,
                    "--state",
                    "open",
                    "--search",
                    f"{cve_id} in:title",
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=15,
            )
        else:
            return False
        return cve_id.upper() in (r.stdout + r.stderr).upper()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
