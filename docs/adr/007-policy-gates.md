# ADR-007: Policy Gates Before and After the Agent

## Status
Accepted

## Context
VVAH uses a "policy sandwich" — pre-gate validates before the LLM runs,
post-gate verifies the diff after the LLM runs. This means a junk LLM
response can never produce a junk PR.

lw-agents had no pre-validation or post-validation. The remediation agent
called create_pull_request with whatever the LLM decided.

## Decision
Add pre-gate and post-gate callbacks to the remediation agent:
- **Pre-gate** validates CVE ID format, Maven coordinates, version strings
  before the agent spends tokens. Invalid requests get a guidance-only
  response with zero model cost.
- **Post-gate** validates the git diff against policy: forbidden patterns
  (nosec, SuppressWarnings, verify=False), max diff size, allowed file
  pathspecs. Violations are rejected.

## Rationale
- Fail-fast on invalid input saves model tokens
- Post-gate catches LLM hallucinations that look like fixes but suppress
  security linters or disable TLS verification
- The pattern is proven at scale in VVAH's production pipeline
