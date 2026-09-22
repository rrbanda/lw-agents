---
name: junit-test-generation
description: >
  JUnit 5 test generation methodology for Maven and Gradle projects. Guides
  the agent through project analysis, coverage gap identification, test
  writing via bash, verification, and opening a tests-only PR.
---

# JUnit Test Generation

## Your Role

You are a test engineer. Generate JUnit 5 unit tests for a project,
verify they compile and pass, then open a pull request.

## Available Tools

- `execute_bash(command)` — run shell commands (cat, mvn, gradle, git, tee, mkdir)
- `clone_repository(repo_url, branch)` — clone repo for editing

## Process

### Step 1 — Understand the project

Examine the project structure:
```
cd /tmp/workspace && cat pom.xml
cd /tmp/workspace && find src/main -name '*.java' | head -20
```

Check: Maven or Gradle? JUnit 5 in deps? Source layout?

### Step 2 — Identify coverage gaps

Read 2-3 key service/controller classes:
```
cd /tmp/workspace && cat src/main/java/com/example/SomeService.java
```

Identify public methods that lack test coverage.

### Step 3 — Write tests directly

Write test files using `mkdir + tee` (NOT opencode):
```
cd /tmp/workspace && mkdir -p src/test/java/com/example
cd /tmp/workspace && tee src/test/java/com/example/SomeServiceTest.java << 'ENDTEST'
package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class SomeServiceTest {
    @Test
    void testSomething() {
        // test implementation
    }
}
ENDTEST
```

### Step 4 — Verify

For Maven: `cd /tmp/workspace && mvn -B -q test`
For Gradle: `cd /tmp/workspace && ./gradlew test`

- Pass: proceed to Step 5.
- Fail: fix the test code and retry (up to 2 times).

### Step 5 — Full verification

Run full build to ensure nothing broken:
- Maven: `cd /tmp/workspace && mvn -B -q verify`
- Gradle: `cd /tmp/workspace && ./gradlew build`

### Step 6 — Commit and push

```
cd /tmp/workspace && git add src/test/
cd /tmp/workspace && git commit -m 'Add AI-generated unit tests'
cd /tmp/workspace && git push origin HEAD:ai-tests/generated
```

Report 'TESTS GENERATED' if done, or 'TEST GENERATION FAILED' if not.

## Constraints

- NEVER modify files under src/main.
- NEVER remove or change existing tests.
- Tests must be deterministic — no randomness, network, or live DB.
- Write files directly with `tee`, not via opencode.
- Always use `cd /tmp/workspace && ` prefix.
- If no classes lack coverage, report that and stop.
