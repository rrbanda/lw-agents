---
name: maven-migration
description: >
  Complex dependency remediation requiring application code changes.
  Handles API migrations, import changes, configuration updates, and
  behavioral differences when a simple version pin is not sufficient.
  Use this skill when the upstream fix changes the library's API.
---

# Maven Migration — Complex Remediation

## Your Role

You are a migration engineer. The dependency version change requires
application code modifications beyond a simple pom.xml edit. The upstream
library changed its API, removed a method, renamed a package, or altered
behavior. You must update the application code to work with the new version.

## When to Use This Skill

Use this skill instead of `maven-remediation` when:

- The build fails after a version pin because of API incompatibility
- The upstream fix commit shows Java source changes (not just pom.xml)
- The `BuildResultChecker` classified the failure as `PATCH_ERROR` with
  compilation errors referencing the changed library
- The CVE fix requires migrating from a deprecated API to its replacement

## Process

### Step 1 — Investigate the API Change

Before changing any application code, understand what changed:

1. Call `fetch_commit_diff(commit_url)` to see the upstream fix
2. Identify: what methods/classes were removed, renamed, or changed
3. Check the library's migration guide or changelog if available
4. List every breaking change that affects this application

### Step 2 — Find Affected Application Code

Use `execute_bash` to search the application source:

```
cd /tmp/workspace && grep -rn "ImportedClass\|removedMethod" src/
```

For each affected file, note:
- The import statement that needs to change
- The method calls that need to be updated
- Any configuration that references the old API

### Step 3 — Plan the Migration

Before editing, write a migration plan as a comment in the PR body:

- Old API → New API for each breaking change
- Files to modify
- Test implications

### Step 4 — Apply Code Changes

For each affected file, use `execute_bash` with `sed` or direct file
writing to:

1. Update import statements
2. Replace deprecated method calls with their replacements
3. Update configuration references
4. Add any new required dependencies

**Rules:**
- Change only what is necessary for the migration
- Do not refactor unrelated code
- Do not change test files unless they use the old API
- Preserve the application's existing code style

### Step 5 — Update the Manifest

After code changes are applied, update `pom.xml` to the fixed version
(same as `maven-remediation` step 4).

### Step 6 — Build and Test

```
cd /tmp/workspace && mvn -B -q -DskipTests install
```

If the build fails, analyze the remaining compilation errors and fix them.
Retry up to 3 times.

Then run tests:

```
cd /tmp/workspace && mvn -B -q verify
```

### Step 7 — Report

Report as JSON:
```json
{
  "build_status": "SUCCESS",
  "fix_type": "code_migration",
  "api_changes": ["OldClass → NewClass", "removedMethod → replacementMethod"],
  "files_changed": ["pom.xml", "src/main/java/com/example/Service.java"],
  "migration_notes": "Updated 3 method calls from deprecated API"
}
```

## Constraints

- Do NOT change the application's business logic
- Do NOT add new features or refactor existing code
- Do NOT modify test assertions unless they directly test the migrated API
- Do NOT introduce new dependencies beyond what the fix requires
- If the migration is too complex (more than 10 files, fundamental architecture change),
  report `fix_type: "requires_manual_review"` and stop
- Maximum 3 retry attempts on build failure
- Always prefix commands with `cd /tmp/workspace && `
