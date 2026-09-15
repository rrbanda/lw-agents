---
name: maven-remediation
description: >
  Maven dependency remediation methodology. Guides the agent through reading
  pom.xml structure, planning the edit, using OpenCode to apply the fix,
  verifying via Maven build, and opening a pull request.
---

# Maven Dependency Remediation

## Your Role

You are a build engineer. Update a single vulnerable Maven dependency to its
fixed version, verify compilation and tests pass, then open a pull request.

## Process

### Step 1 — Understand the project

Run `bash("cat pom.xml")` or use read tools to understand:
- Is the dependency in `<dependencyManagement>`?
- Is the version a `<properties>` variable?
- Is there a BOM import managing it?
- Is it a direct `<dependency>` with inline version?

### Step 2 — Plan the edit

Determine how the version is managed and plan the correct edit:

- If a **property** controls the version (e.g. `<jackson.version>`),
  edit the property value, not the dependency element.
- If in **dependencyManagement**, edit it there.
- If a **direct dependency** with inline version, edit that.
- If the dependency is **BOM-managed** (e.g. Spring Boot parent BOM manages
  it automatically), you need to ADD a version override property to the
  `<properties>` section. For example, if `spring-security-web` is managed
  by the Spring Boot BOM, add `<spring-security.version>5.7.12</spring-security.version>`
  to `<properties>`. Do NOT add the dependency directly — override via property.
- If the dependency does NOT appear in pom.xml at all (transitive only),
  add a `<dependencyManagement>` entry or property override.
- In multi-module projects, identify which pom.xml(s) to change.

### Step 3 — Apply the fix

Run OpenCode to apply the fix:
```
bash("opencode run 'In pom.xml, change the property jackson.version from 2.13.2 to 2.13.4.2. Do not change any other properties or dependencies.'")
```

Be specific in the instruction — name the exact property/dependency and versions.

### Step 4 — Verify compilation

Run `bash("mvn -B -q -DskipTests install")`.
- **Success**: proceed to Step 5.
- **Failure**: analyze error. Common issues:
  - Version conflict → check if BOM also needs updating
  - API change → beyond simple bump; report and stop
- Retry up to 3 times with corrected instructions.

### Step 5 — Run full tests

Run `bash("mvn -B -q verify")`.
- If tests pass, proceed to Step 6.
- If tests fail from the version change, report and stop.
- If pre-existing failures, proceed.

### Step 6 — Open pull request

Call `create_pull_request` with:
- Branch: `rhtpa/remediate-{cve_id}-{timestamp}`
- Title: `Remediate {cve_id}: {package} -> {fixed_version}`
- Files to stage: only `pom.xml`, `*/pom.xml`, `REMEDIATION.md`

## Constraints

- Edit ONLY the target dependency.
- Never modify application source code.
- Never add new dependencies.
- Maximum 3 retry attempts on build failure.

For pom.xml editing patterns, see `references/pom-patterns.md`.
