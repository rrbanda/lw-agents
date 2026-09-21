---
name: gradle-remediation
description: >
  Gradle dependency remediation methodology. Guides the agent through reading
  build.gradle/build.gradle.kts structure, planning the edit, applying the fix,
  verifying via Gradle build, and opening a pull request.
---

# Gradle Dependency Remediation

## Your Role

You are a build engineer. Update a single vulnerable Gradle dependency to its
fixed version, verify compilation and tests pass, then open a pull request.

## Process

### Step 1 — Understand the project

Use bash tools to examine the project structure:
- `cat build.gradle` or `cat build.gradle.kts` for the main build file
- Check for `buildSrc/`, `gradle.properties`, `libs.versions.toml` (version catalogs)
- Check if the project uses a BOM (platform dependency)

### Step 2 — Plan the edit

Determine how the version is managed:

- **Version catalog** (`gradle/libs.versions.toml`): edit the version entry there
- **ext/extra property** (e.g. `val jacksonVersion = "2.13.2"`): edit the property
- **Direct declaration** (e.g. `implementation("group:artifact:version")`): edit inline
- **BOM/platform** managed: add a `constraints` block or a forced resolution strategy
- **buildSrc**: check `buildSrc/src/main/kotlin/Versions.kt` or similar

### Step 3 — Apply the fix

Use bash to edit the appropriate file. For `.gradle.kts`:
```
sed -i 's/val jacksonVersion = "2.13.2"/val jacksonVersion = "2.13.4.2"/' build.gradle.kts
```

For version catalogs:
```
sed -i 's/jackson = "2.13.2"/jackson = "2.13.4.2"/' gradle/libs.versions.toml
```

### Step 4 — Verify compilation

Run `./gradlew build -x test --no-daemon -q`.
- **Success**: proceed to Step 5.
- **Failure**: analyze error. Common issues:
  - Version conflict → add resolution strategy
  - API change → beyond simple bump; report and stop
- Retry up to 3 times.

### Step 5 — Run full tests

Run `./gradlew test --no-daemon -q`.
- If tests pass, proceed.
- If pre-existing failures, proceed.
- If new failures from version change, report and stop.

### Step 6 — Open pull request

Call `create_pull_request` with:
- Branch: `rhtpa/remediate-{cve_id}-{timestamp}`
- Title: `Remediate {cve_id}: {package} -> {fixed_version}`
- Files to stage: `build.gradle` `build.gradle.kts` `gradle/libs.versions.toml` `gradle.properties`

## Constraints

- Edit ONLY the target dependency version.
- Never modify application source code.
- Always use `./gradlew` (wrapper) when available.
- Maximum 3 retry attempts on build failure.
