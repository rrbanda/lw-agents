# Agent Fixes Required for Tekton Pipeline Integration

## Problem

The lw-agents service runs in its OWN pod. Tekton tasks run in SEPARATE pods
with a shared workspace PVC. The agent cannot read files from the Tekton
workspace directly. There are 4 gaps between what the Tekton tasks send and
what the agent currently does.

## Architecture

```
Tekton Pod (has /workspace/source/)          Agent Pod (has /sandbox/)
┌──────────────────────────────┐             ┌──────────────────────────────┐
│ rhtpa/must-fix-cves.json     │──── HTTP ──>│ ADK Agent Service            │
│ rhtpa/vulnerabilities.json   │   (prompt   │ ├── CVE tools (read files)   │
│ source/pom.xml               │    with     │ ├── OpenCode (edit files)    │
│ source/src/main/java/...     │    data)    │ ├── Maven (build/test)       │
│                              │<── SSE ─────│ └── git/glab/gh (push/PR)   │
│ Writes Tekton results        │  (results)  │                              │
└──────────────────────────────┘             └──────────────────────────────┘
```

## Gap 1: CVE tools read from filesystem -- Tekton sends data inline

### What Tekton sends

The `ai-select-cve` and `ai-analyze-cves` tasks read `must-fix-cves.json`
and `vulnerabilities.json` from the workspace, then embed the FULL CONTENTS
in the prompt:

```
Select the best CVE to remediate from the must-fix set below.

MUST-FIX CVEs (from Conforma policy gate):
[{"cve_id":"CVE-2024-29025","severity":"critical","affected_purls":["pkg:maven/io.netty/netty-codec-http@4.1.100.Final"],"fixed_version_hints":["4.1.108.Final"]}]

VULNERABILITY REPORT (RHTPA analysis):
{"findings":[...],"details":[...]}
```

### What the agent does now

The `cve_selection` agent calls `list_must_fix_cves(workspace_path)` which
tries to read `/workspace/source/rhtpa/must-fix-cves.json` from the AGENT
POD's filesystem. File doesn't exist. Tool returns `{"status":"not_found"}`.

The LLM has the data in its context (Tekton put it there), but the agent's
instruction tells it to "follow the skill process step by step using tools."
The skill says "call list_must_fix_cves." When that fails, the agent may
not realize it should use the inline data.

### What to fix

**File: `app/agents/cve_selection.py`** line 37 -- update instruction:

```python
instruction=(
    "You are a CVE triage specialist. When asked to select a CVE, "
    "first call load_skill to read the cve-triage skill, then follow "
    "its process step by step using the available tools.\n\n"
    "IMPORTANT: If the workspace files are not found when you call "
    "list_must_fix_cves or lookup_cve_detail (tool returns 'not_found' "
    "or 'error'), use the CVE data provided directly in the user's "
    "message instead. The Tekton pipeline embeds file contents in the "
    "prompt when the agent runs as a remote service.\n\n"
    "Report your selection as a structured summary with: selected (true/false), "
    "cve_id, package (groupId:artifactId), current_version, "
    "fixed_version, and justification."
),
```

**File: `app/agents/cve_analysis.py`** line 31 -- same pattern, plus request
JSON array output (see Gap 2).

### How to test

```bash
# Simulate what Tekton sends (inline data, no workspace):
curl -sk -X POST "$BASE/run_sse" \
  -H "Content-Type: application/json" \
  -d '{"app_name":"app","user_id":"test","session_id":"'$SID'",
    "new_message":{"role":"user","parts":[{"text":"Select the best CVE:\n\nMUST-FIX CVEs:\n[{\"cve_id\":\"CVE-2024-29025\",\"severity\":\"critical\",\"affected_purls\":[\"pkg:maven/io.netty/netty-codec-http@4.1.100.Final\"],\"fixed_version_hints\":[\"4.1.108.Final\"]}]\n\nVULNERABILITY REPORT:\n{\"findings\":[{\"cve_id\":\"CVE-2024-29025\",\"severity\":\"critical\",\"affected_purls\":[\"pkg:maven/io.netty/netty-codec-http@4.1.100.Final\"],\"fixed_version_hints\":[\"4.1.108.Final\"]}],\"details\":[{\"identifier\":\"CVE-2024-29025\",\"title\":\"Netty HttpPostRequestDecoder OOM\",\"description\":\"Fix in 4.1.108.Final\"}]}"}]}}'
```

Expected: Agent calls `list_must_fix_cves`, gets "not_found", then reasons
from the inline data, calls `parse_maven_purl` and `check_version_exists`,
returns SELECTED=1.

---

## Gap 2: Analyze agent needs to return a decisions array

### What Tekton expects

The `ai-analyze-cves` task parses the agent's TEXT response for a JSON array:

```python
json_match = re.search(r'\[[\s\S]*\]', agent_text)
decisions = [d for d in arr if d.get("selected")]
```

Each decision needs:
```json
{
  "cve_id": "CVE-2024-29025",
  "package": "io.netty:netty-codec-http",
  "current_version": "4.1.100.Final",
  "fixed_version": "4.1.108.Final",
  "severity": "critical",
  "justification": "...",
  "selected": true
}
```

Then it writes `.title`/`.body`/`.labels` files to the workspace for
the `open-cve-issues` task to create GitLab/GitHub issues.

### What the agent does now

The `cve_analysis` agent returns natural language and a COUNT. It tries to
call `create_scm_issue` directly (which fails without SCM credentials).
It does NOT output a JSON array.

### What to fix

**File: `app/agents/cve_analysis.py`** -- update instruction to request
JSON array output AND remove `create_scm_issue_tool` (Tekton handles issues):

```python
instruction=(
    "You are a CVE analysis specialist. When asked to analyze CVEs, "
    "first call load_skill to read the cve-analysis skill, then follow "
    "its process step by step.\n\n"
    "IMPORTANT: If workspace files are not found, use the CVE data "
    "provided in the user's message.\n\n"
    "For EACH fixable CVE, verify the fixed version exists using "
    "check_version_exists. Then output your complete analysis as a "
    "JSON array:\n"
    "[{\"cve_id\":\"CVE-...\",\"package\":\"groupId:artifactId\","
    "\"current_version\":\"...\",\"fixed_version\":\"...\","
    "\"severity\":\"...\",\"justification\":\"...\","
    "\"selected\":true}, ...]\n\n"
    "Include ONLY CVEs where you verified a concrete fixed version exists."
),
```

Remove `create_scm_issue_tool` from the tools list. Issue creation is handled
by the Tekton `open-cve-issues` task, not the agent.

### How to test

Same curl as Gap 1 but with the analyze prompt. Expected: agent text response
contains a JSON array like `[{"cve_id":"CVE-2024-29025",...,"selected":true}]`.

---

## Gap 3: Remediation agent needs to clone repo, edit, push

### What Tekton sends

```
Remediate CVE-2024-29025 in package io.netty:netty-codec-http.
Current version: 4.1.100.Final
Fixed version: 4.1.108.Final
Workspace path: /workspace/source/source
```

The workspace path is on the TEKTON pod. The agent cannot access it.

### What Tekton expects back

```yaml
results:
  - name: CHANGED  # "1" if agent modified build files
```

After the agent returns CHANGED=1, the Tekton pipeline's `open-pr-cve`
task commits and pushes from the Tekton workspace.

### The architecture problem

The agent runs OpenCode + Maven on its own filesystem. It CAN'T edit files
on the Tekton workspace. Two clean solutions:

**Solution A: Agent clones, edits, pushes a branch (recommended)**

The Tekton task passes the git repo URL and branch. The agent clones the
repo into a temp dir, applies the fix, verifies the build, pushes a new
branch. Tekton creates the PR from that branch.

Requires: Tekton task sends `REPO_URL` and `SOURCE_BRANCH` in the prompt.
The agent needs SCM env vars (SCM_HOST, SCM_TOKEN) which it already has.

**Solution B: Agent returns a diff, Tekton applies it**

The Tekton task sends the pom.xml content. The agent returns a unified diff.
Tekton applies the diff to the workspace.

Requires: Tekton task reads pom.xml and sends it in prompt. Agent returns
patch format. Build verification moves to Tekton.

### What to fix (Solution A)

**File: `app/tools/scm_tools.py`** -- add new tool:

```python
def clone_repository(
    repo_url: str,
    branch: str = "main",
    target_dir: str = "/tmp/workspace",
) -> dict[str, Any]:
    """Clone a git repository for editing.

    Args:
        repo_url: HTTPS URL of the repository.
        branch: Branch to clone.
        target_dir: Local directory to clone into.
    """
    provider = os.environ.get("SCM_PROVIDER", "gitlab")
    host = os.environ.get("SCM_HOST", "")
    token = os.environ.get("SCM_TOKEN", "")
    username = os.environ.get("SCM_USERNAME", "oauth2")

    auth_url = f"https://{username}:{token}@{host}/{_extract_repo_path(repo_url)}.git"

    try:
        result = subprocess.run(
            ["git", "clone", "--branch", branch, "--depth", "1", auth_url, target_dir],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {"cloned": False, "error": result.stderr.strip()}
        return {"cloned": True, "path": target_dir}
    except Exception as e:
        return {"cloned": False, "error": str(e)}

clone_repository_tool = FunctionTool(clone_repository, require_confirmation=False)
```

**File: `app/agents/remediation.py`** -- update instruction:

```python
instruction=(
    "You are a Maven remediation engineer. Follow these steps:\n"
    "1. Clone the repository using clone_repository tool\n"
    "2. Load the maven-remediation skill\n"
    "3. Read pom.xml to understand the project\n"
    "4. Apply the fix using opencode run\n"
    "5. Verify with mvn -B -q -DskipTests install\n"
    "6. If build passes, push changes using create_pull_request\n"
    "7. Report BUILD SUCCESS or BUILD FAILURE\n\n"
    "The repo URL and branch will be in the user's request or session state."
),
```

Add `clone_repository_tool` to the tools list.

**File: `app/config.py`** -- add `git` to bash allowed prefixes:

```python
BASH_ALLOWED_PREFIXES = (
    "opencode ", "mvn ", "cat ", "ls ", "head ", "grep ", "find ", "git ",
)
```

**Tekton task change needed** (in ssc-demo, not here):

The `ai-remediate-dependency` task needs to pass the git repo URL and branch:

```python
prompt = f"""Remediate {CVE_ID} in package {PACKAGE}.
Current version: {CURRENT_VERSION}
Fixed version: {FIXED_VERSION}
Repository: {REPO_URL}
Branch: {SOURCE_BRANCH}"""
```

The `REPO_URL` is available from the `git-clone` task earlier in the pipeline.

### How to test

```bash
# Requires SCM_PROVIDER, SCM_HOST, SCM_TOKEN env vars on the agent pod
curl -sk -X POST "$BASE/run_sse" ... \
  -d '{"text":"Remediate CVE-2024-29025 in io.netty:netty-codec-http. Current: 4.1.100.Final, Fixed: 4.1.108.Final. Repository: https://gitlab.example.com/app.git Branch: main"}'
```

Expected: Agent clones repo, runs opencode to edit pom.xml, runs mvn build,
pushes branch, returns BUILD SUCCESS + PR_URL.

---

## Gap 4: Test-gen agent -- same as Gap 3

Same solution: clone repo, generate tests, push branch.

**File: `app/agents/test_generation.py`** -- update instruction to include
clone step. Add `clone_repository_tool` to writer tools.

**Tekton task change needed**: `ai-generate-tests` passes REPO_URL + branch.

---

## Summary of changes

### In lw-agents (this repo):

| File | Change |
|---|---|
| `app/agents/cve_selection.py` | Add "use inline data if tools return not_found" to instruction |
| `app/agents/cve_analysis.py` | Same + request JSON array output + remove create_scm_issue_tool |
| `app/agents/remediation.py` | Add "clone repo first" to instruction + add clone_repository_tool |
| `app/agents/test_generation.py` | Same as remediation -- clone first |
| `app/tools/scm_tools.py` | Add `clone_repository` tool |
| `app/config.py` | Add `"git "` to BASH_ALLOWED_PREFIXES |
| `app/callbacks.py` | Add CHANGED field to structured_result defaults |

### In ssc-demo (other repo -- tell other Cursor window):

| File | Change |
|---|---|
| `ai-select-cve.yaml` | No change needed (already sends inline data) |
| `ai-analyze-cves.yaml` | No change needed (already parses JSON array from text) |
| `ai-remediate-dependency.yaml` | Add REPO_URL and SOURCE_BRANCH to prompt |
| `ai-generate-tests.yaml` | Add REPO_URL and SOURCE_BRANCH to prompt |

### Environment variables needed on agent pod:

```
SCM_PROVIDER=gitlab     # or github
SCM_HOST=gitlab.example.com
SCM_TOKEN=<token>
SCM_USERNAME=oauth2     # default for GitLab
SCM_BASE_BRANCH=main
```

These are already in the Kustomize secret template.
