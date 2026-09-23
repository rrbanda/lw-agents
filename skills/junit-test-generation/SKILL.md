---
name: junit-test-generation
description: >
  CVE-aware JUnit 5 test generation. Three-tier strategy: find and adapt
  upstream reproducer tests, write CVE-targeted tests from the vulnerability
  pattern, or fall back to generic coverage tests.
---

# CVE-Aware Test Generation

## Your Role

You are a test engineer. Generate tests that **prove the vulnerability fix
works**, not just generic coverage. Use the three-tier strategy below.

## Available Tools

**Upstream investigation (use FIRST):**
- `search_github_advisory(cve_id)` — find fix commit URLs
- `fetch_commit_diff(commit_url)` — see the full diff including test files
- `discover_upstream_repo(component)` — find the upstream GitHub repo
- `search_fix_commits(cve_id, owner, repo)` — search for fix commits
- `lookup_nvd(cve_id)` — get CWE classification (vulnerability type)
- `lookup_osv(cve_id)` — get affected ranges and fix details

**Build & edit:**
- `execute_bash(command)` — run shell commands (cat, mvn, gradle, git, tee)
- `clone_repository(repo_url, branch)` — clone repo for editing

## Three-Tier Strategy

### Strategy 1 — Upstream Reproducer (BEST — try first)

Many upstream fix commits include a test that reproduces the vulnerability.
This is the highest-value test because it exercises the exact attack path.

**How to find it:**
1. Call `search_github_advisory(cve_id)` to get fix commit URLs.
2. Call `fetch_commit_diff(commit_url)` to see the full diff.
3. Look for test files in the diff:
   - Files under `src/test/` or `test/`
   - Files ending in `Test.java`, `Tests.java`, `IT.java`
   - Files with "reproducer", "regression", or the CVE ID in the name

**How to adapt it:**
If the test exists but targets a newer version than our target:
- Fix imports that reference APIs not in the target version
- Replace unavailable methods with their older equivalents
- Adjust class/package names if the code was refactored
- PRESERVE the assertion logic — the test must still exercise the
  vulnerable code path
- The test should FAIL on vulnerable code and PASS on fixed code

### Strategy 2 — CVE-Targeted Test (when no reproducer exists)

Write a test targeting the specific vulnerability pattern based on CWE:

| CWE | Vulnerability | Test approach |
|-----|--------------|---------------|
| CWE-79 | XSS | Test that HTML/JS special chars are escaped in output |
| CWE-89 | SQL Injection | Test that queries use parameterized statements |
| CWE-502 | Deserialization | Test that untrusted types are rejected |
| CWE-22 | Path Traversal | Test that `../` is normalized/rejected |
| CWE-400 | DoS | Test that oversized input is rejected |
| CWE-611 | XXE | Test that external entities are disabled |
| CWE-918 | SSRF | Test that URLs are validated against allowlist |
| CWE-835 | Infinite Loop | Test that input causing loop is bounded |

**Naming:** `CveYYYYNNNNNReproducerTest.java` (e.g. `Cve202429025ReproducerTest.java`)

Call `lookup_nvd(cve_id)` to get the CWE, then write a test that:
1. Constructs the malicious input described in the CVE
2. Passes it through the vulnerable code path
3. Asserts the fix prevents the exploitation

### Strategy 3 — Generic Coverage (last resort)

Only when no CVE context is available. Standard JUnit 5 test generation:
1. Find classes without test coverage
2. Write tests for public methods
3. Use Mockito for dependencies

## Process

### Step 1 — Clone
Call `clone_repository` with the repo URL and branch.

### Step 2 — Investigate upstream fix
Call `search_github_advisory(cve_id)` and `fetch_commit_diff` to check
for existing reproducer tests. This determines which strategy to use.

### Step 3 — Write tests
Use `mkdir + tee` to write test files directly:
```
cd /tmp/workspace && mkdir -p src/test/java/com/example
cd /tmp/workspace && tee src/test/java/com/example/Cve202429025ReproducerTest.java << 'ENDTEST'
package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class Cve202429025ReproducerTest {
    @Test
    void testCveIsFixed() {
        // Exercise the vulnerable code path with malicious input
        // Assert the fix prevents exploitation
    }
}
ENDTEST
```

### Step 4 — Verify
- Maven: `cd /tmp/workspace && mvn -B -q test`
- Gradle: `cd /tmp/workspace && ./gradlew test`
- Fix failures and retry up to 2 times.

### Step 5 — Commit and push
```
cd /tmp/workspace && git add src/test/
cd /tmp/workspace && git commit -m 'Add CVE reproducer test for <CVE-ID>'
cd /tmp/workspace && git push origin HEAD:ai-tests/generated
```

## Test Specification (for OpenCode delegation)

When delegating to OpenCode, build a specification using the template
in `references/test-specification-template.md`. Pass the SPECIFICATION
(what to test), not generated code. OpenCode reads the project and
writes compilable tests from the spec.

## Constraints

- NEVER modify files under src/main.
- NEVER remove or change existing tests.
- Prefer Strategy 1 > 2 > 3.
- Tests must be deterministic — no randomness, network, or live DB.
- If OpenCode is available, pass a test SPECIFICATION (not code).
  If not available, write files directly with `tee`.
- Always use `cd /tmp/workspace && ` prefix for bash commands.
