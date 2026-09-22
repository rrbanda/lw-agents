---
name: scm-conventions
description: >
  SCM conventions for branch naming, commit messages, PR body templates,
  issue body templates, selective git staging, and label standards used
  across all CVE remediation and test generation workflows.
---

# SCM Conventions

## Branch Naming

| Task | Pattern | Example |
|------|---------|---------|
| CVE remediation | `rhtpa/remediate-{cve_id}-{ts}` | `rhtpa/remediate-CVE-2024-1234-1726300000` |
| Test generation | `ai-tests/generated-{ts}` | `ai-tests/generated-1726300000` |

## Commit Messages

| Task | Format |
|------|--------|
| CVE remediation | `fix({cve_id}): bump {package} to {fixed_version}` |
| Test generation | `test: add AI-generated unit tests` |

## Selective Git Staging

PRs must NEVER include agent artifacts. Stage only:

| Task | Allowed pathspecs |
|------|-------------------|
| CVE remediation (Maven) | `pom.xml`, `*/pom.xml`, `REMEDIATION.md` |
| CVE remediation (Gradle) | `build.gradle`, `build.gradle.kts`, `gradle/libs.versions.toml`, `gradle.properties` |
| Test generation | `src/test/`, `*/src/test/` |

## Issue Body Template

See `references/issue-template.md` in the `cve-analysis` skill.

## PR Body Templates

### CVE Remediation
```
Automated remediation from the agentic-cve-remediation pipeline.
- CVE: {cve_id}
- Dependency: {package} {current_version} -> {fixed_version}
- Build system: Maven|Gradle
- Upstream fix analyzed: yes|no
- Fix type: version_bump|source_patch|config_change
- Rationale: {justification}
```

### Test Generation
```
Automated unit-test generation.
Includes AI-generated JUnit tests under src/test.
Please review before merging.
```

## Labels

| Context | Labels |
|---------|--------|
| CVE issues | `security`, `cve`, `{severity}` |
| Remediation PRs | `security`, `remediation`, `automated` |
| Test PRs | `testing`, `automated` |
