# ADR-008: Multi-Persona Fix Validation

## Status
Accepted

## Context
VVAH validates remediation fixes using three read-only personas
(security-architect, penetration-tester, cross-repo-analyzer) that
independently evaluate four weighted gates, with deterministic consensus.

lw-agents had no validation — PRs were opened without adversarial review.

## Decision
Add a validation agent with two personas (security architect + penetration
tester) and deterministic scoring. The validation pipeline:

1. Security architect evaluates fix design and control placement
2. Penetration tester tries to find bypasses
3. Deterministic scoring applies VVAH-style weighted gates:
   - root_cause: 0.43, instance_coverage: 0.25,
     no_new_vulnerabilities: 0.19, security_best_practices: 0.13
4. Conservative consensus: 2 personas agree -> HIGH; else most conservative

Both personas are read-only (no write tools, no bash).

## Rationale
- Adversarial review catches fixes that look correct but are bypassable
- Deterministic scoring removes LLM subjectivity from the final verdict
- Conservative consensus (most-conservative-wins on disagreement) is
  fail-safe — a bad fix is more costly than a delayed fix
- Two personas balance cost vs coverage; add cross-repo-analyzer later
