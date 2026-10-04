---
title: Fully agentic
summary: What a system with no fixed pipeline would own, and why it is not built yet.
---

The pipeline models described in the previous pages have a declared DAG. Tekton decides the order. The agent does one step. A person bridges selection and remediation. That bridge is the handoff, and for organizations with many applications and many advisories, the handoff is where time accumulates.

A fully agentic system would replace the fixed DAG with a coordinator that decides the next action across phases, inside written rules. It is not built. This page describes what it would need to be safe, what it would gain, and what it would lose.

## What it would own

A coordinator receives a signal (a new advisory, a scan result, a schedule) and decides:

- Which application is affected.
- Which advisory to act on first.
- Whether a fixed coordinate exists.
- Whether to open a pull request, generate tests, or wait.
- When to stop and ask a person.

It would move across the steps that the pipeline model splits into separate pipeline runs and manual handoffs. It would not need a person to comment `/remediate` on each issue.

## What must already be true

The same rules that protect the pipeline model apply here, with less room for error because there is no declared DAG enforcing order.

| Rule | Why |
| --- | --- |
| One advisory at a time per application | A change that touches multiple dependencies is not a standard change. It widens the blast radius |
| A person still approves the pull request | Automerge is a policy the organization grants, not a default the agent assumes |
| The fixed coordinate comes from the advisory's fixed event | The agent does not pick a version because it seems newer. The supplier named the coordinate |
| No exploit procedure in the pull request or the tests | Validation checks that the pin landed. It does not reconstruct the attack |
| No embargoed detail in a public branch | An embargo means the advisory description stays out of the pull request body |
| Bounded authority | The agent may change the manifest. It may not approve the change, deploy it, or declare the estate clean |
| Written policy, not learned behavior | The rules are loaded from configuration, not inferred from prior runs |

## What it gains

- **No handoff delay.** The coordinator moves from advisory to pull request without waiting for a person to comment on an issue.
- **Estate-level sequencing.** The coordinator can work across applications, choosing the next application to patch based on exposure and criticality.
- **Adaptive retry.** If a fix fails on one application, the coordinator can move to the next and return later.
- **Reduced context switching.** Developers review pull requests instead of researching advisories and editing manifests.

## What it loses

- **Declared auditability.** A Tekton pipeline run is a record of exactly which tasks ran, in which order, with which inputs and outputs. A coordinator's decisions are harder to audit unless the system logs every decision with the same fidelity.
- **Blast radius containment.** A pipeline that runs one application at a time cannot accidentally apply the wrong fix to the wrong application. A coordinator that sees the estate could make that mistake.
- **Operational simplicity.** A pipeline is a YAML file that a platform engineer reads. A coordinator is a running service that must be monitored, throttled, and stopped when it misbehaves.

## Maturity levels

The planning model for this work describes maturity levels.

| Level | What changes | Typical clock |
| --- | --- | --- |
| 0 | Manual work, tracked in a ticketing system | 30 to 90 days |
| 3 | Agent analysis and a person-approved pull request. Artifact and commit signing are part of the picture | Under 7 days |
| 4 | Automerge for changes that meet policy, and a standard change. A person still manages promotion | Under 1 day |
| 5 | An orchestrator, automatic tickets, automatic rollback | Under 1 day |

The pipeline models are level 3. The fully agentic model describes levels 4 and 5. Moving from level 3 to level 4 requires the organization to define which changes qualify as standard and to grant the agent permission to merge them. Moving to level 5 requires deployment orchestration and rollback, which are operations concerns outside the remediation agent.

## Where it stands

No implementation of the fully agentic model exists in the repositories described on this site. The pipeline models are production-ready. The fully agentic model is a design target for organizations that have operated the pipeline model long enough to trust the agent's output and are willing to grant broader authority under explicit policy.
