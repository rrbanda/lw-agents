---
name: junit-test-generation
description: >
  JUnit 5 test generation methodology for Maven/Quarkus projects. Guides the
  agent through project analysis, coverage gap identification, test generation
  via OpenCode, verification via Maven, and opening a tests-only PR.
---

# JUnit Test Generation

## Your Role

You are a test engineer. Generate JUnit 5 unit tests for a Maven/Quarkus
project, verify they compile and pass, then open a pull request.

## Process

### Step 1 — Understand the project

Run `bash("cat pom.xml")` to check:
- Quarkus, Spring Boot, or plain Maven?
- Testing dependencies (JUnit 5, Mockito, etc.)?
- Source layout (src/main/java, src/test/java)?

### Step 2 — Identify coverage gaps

Run OpenCode in analysis mode:
```
bash("opencode run 'Analyze the project. List public service and business-logic classes under src/main/java that have NO corresponding test class under src/test/java. Skip POJOs, DTOs, and config classes.'")
```

### Step 3 — Generate tests

Run OpenCode with generation instructions:
```
bash("opencode run 'Generate JUnit 5 unit tests for the identified classes. Put tests under src/test/java mirroring the package layout. Use Mockito for dependencies. Keep tests deterministic and offline. Do NOT modify src/main. Run mvn test and fix failures.'")
```

### Step 4 — Verify

Run `bash("mvn -B -q test")`.
- Pass: proceed to Step 5.
- Fail: run OpenCode again with failure output to fix tests.
- Maximum 3 iterations.

### Step 5 — Full verification

Run `bash("mvn -B -q verify")` — existing + generated tests together.

### Step 6 — Open pull request

Call `create_pull_request` with:
- Branch: `ai-tests/generated-{timestamp}`
- Title: `Add AI-generated unit tests`
- Files to stage: only `src/test/`, `*/src/test/`

## Constraints

- NEVER modify files under src/main.
- NEVER remove or change existing tests.
- Tests must be deterministic — no randomness, network, or live DB.
- If no classes lack coverage, report that and stop.
