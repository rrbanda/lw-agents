---
name: maven-remediation
description: >
  Maven dependency remediation methodology. Guides the agent through
  investigating the upstream fix, reading pom.xml structure, planning
  the edit, applying and verifying via Maven build, and opening a PR.
---

# Maven Dependency Remediation

## Your Role

You are a build engineer. Update a single vulnerable Maven dependency to its
fixed version, verify compilation and tests pass, then open a pull request.

## Available Tools

**Investigation (use BEFORE editing):**
- `search_github_advisory(cve_id)` — find fix commit URLs and patched versions
- `fetch_commit_diff(commit_url)` — see what the upstream fix changed
- `discover_upstream_repo(component)` — find the upstream GitHub repo
- `search_fix_commits(cve_id, owner, repo)` — search for fix commits
- `lookup_osv(cve_id)` — affected ranges and fix versions
- `lookup_nvd(cve_id)` — CVSS, CWE, patch URLs

**Build & edit:**
- `execute_bash(command)` — run shell commands (sed, mvn, git, cat, etc.)
- `clone_repository(repo_url, branch)` — clone repo for editing
- `detect_build_system(project_dir)` — detect Maven/Gradle/Ant
- `analyze_diff(diff_text)` — analyze the changes you've made

## Process

### Step 1 — Clone the repository

Call `clone_repository` with the repo URL and branch from the request.

### Step 2 — Investigate the upstream fix

**Before editing anything**, understand what the upstream fix changed:

1. Call `search_github_advisory(cve_id)` to find fix commit URLs.
2. If commits found, call `fetch_commit_diff(commit_url)` to see the diff.
3. Determine the fix type:
   - **Version bump only** (pom.xml/build file change) → proceed with edit
   - **Source code patch** (Java files changed) → report that source-level
     patching is needed and describe what the upstream fix does
   - **Configuration change** → describe and apply if simple

### Step 3 — Understand the project

Run `execute_bash("cd /tmp/workspace && cat pom.xml")` to understand:
- Is the dependency in `<dependencyManagement>`?
- Is the version a `<properties>` variable?
- Is there a BOM import managing it?
- Is it a direct `<dependency>` with inline version?

### Step 4 — Plan and apply the fix

Determine how the version is managed and apply the correct edit:

- **Property-controlled** (e.g. `<jackson.version>`): edit the property value
- **BOM-managed** (e.g. Spring Boot parent): ADD a version override property
- **Direct dependency**: edit the version inline
- **Transitive only**: add a `<dependencyManagement>` entry

Use `execute_bash` with `sed` to make the edit. Example:
```
cd /tmp/workspace && sed -i 's|<jackson.version>2.13.2</jackson.version>|<jackson.version>2.13.4.2</jackson.version>|' pom.xml
```

For BOM overrides:
```
cd /tmp/workspace && sed -i '/<properties>/a\    <logback.version>1.5.18</logback.version>' pom.xml
```

### Step 5 — Build

Run: `cd /tmp/workspace && mvn -B -q -DskipTests install`
- **Success**: proceed to Step 6.
- **Failure**: analyze the error. Common issues:
  - Version conflict → check if BOM also needs updating
  - API change → beyond simple bump; report and stop
- Retry up to 3 times with corrected approach.

### Step 6 — Test

Run: `cd /tmp/workspace && mvn -B -q verify`
- If tests pass, proceed.
- If tests fail from the version change, report and stop.
- If pre-existing failures, proceed.

### Step 7 — Commit and push

```
cd /tmp/workspace && git add pom.xml
cd /tmp/workspace && git diff --cached --stat
cd /tmp/workspace && git commit -m 'Remediate <CVE>: <package> -> <version>'
cd /tmp/workspace && git push origin HEAD:rhtpa/remediate-<CVE>
```

### Step 8 — Report

Report as JSON:
```json
{
  "build_status": "SUCCESS",
  "fix_type": "version_bump",
  "upstream_fix_analyzed": true,
  "files_changed": ["pom.xml"]
}
```

## Constraints

- Investigate the upstream fix BEFORE editing.
- Edit ONLY the target dependency version.
- Never modify application source code.
- Never add new dependencies.
- Maximum 3 retry attempts on build failure.
- Always prefix commands with `cd /tmp/workspace && `.

For pom.xml editing patterns, see `references/pom-patterns.md`.
