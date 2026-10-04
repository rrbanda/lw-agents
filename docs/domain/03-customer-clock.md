---
title: Customer clock
summary: After Lightwell has published a fix, the application still has to absorb it. That interval is the clock these agents shorten.
---

The planning deck *Secure SSC SDLC Lightwell Integration CVE Remediation* is the source for the numbers on this page. They are that deck's planning bands, not a contractual service level. Skills use them to tell a pin apart from a program of work. They do not quote them as a promise.

## The claim

Lightwell has limited value if an application still takes longer than about two weeks to get a published library fix into production. By then the public advisory is already usable by an attacker. A hardened base image does not remove this clock. The application dependency is still the application's to absorb.

The interval is:

**Discover → triage and log → remediate one CVE on one application → test and validate → deliver**

A typical run of that interval, in the deck, is 30 to 90 days or more.

| Band | Days | Meaning in the deck |
| --- | --- | --- |
| Safe | 7–14 | The window in which a published Lightwell fix still changes the outcome |
| Caution | 15–45 | The fix is aging |
| High risk | 45–90 | The publication-to-production gap is the exposure |

The two-week line is why the use case is one advisory and the smallest dependency change. A freshness upgrade, a feature change, and a library rewrite miss the window for a different reason: they are larger changes, and they wait on a different approval.

## Where the days go

| Stage | Typical duration in the deck | What actually happens |
| --- | --- | --- |
| Triage | about 5 days | Manual blast radius, exploitability, false positives |
| Remediate | 5–14 days | A developer sprint to change the dependency |
| Test | 1–3 days | Cross-team tests, audit, change approval |
| Deliver | 14–90 days or more | Manual rollout and rollback |

A streamlined path in the deck is under 14 days: an agent proposes the update, a person approves it, the test and the change record are standard, and rollout stays manual. The ideal path is about a day: priority is already known, the merge is automatic in under an hour, the change is a standard change in under a day, and rollout and rollback are orchestrated in under an hour.

## Maturity, and where this repository is

The deck's story names level 0 and levels 3 through 5. It does not give a separate operating definition for levels 1 and 2. Do not invent those names.

| Level | What changes | Clock in the deck |
| --- | --- | --- |
| 0 | Manual work, tracked in ServiceNow | 30–90 days |
| 3 | Agentic analysis and a person-approved pull request. Artifact and commit signing are part of the picture | Under 7 days |
| 4 | Automerge for changes that meet policy, and a standard change. A person still manages promotion | Under 1 day |
| 5 | An orchestrator, automatic tickets, automatic rollback | Under 1 day |

:::in
This repository is level 3. It analyzes, edits the manifest, and opens a pull request. A person merges. Level 4 automerge is allowed only when the policy loaded for that application says so. Nothing in the current skills grants that policy. Level 5, including ServiceNow tickets and automatic rollback, is outside this repository.
:::

## Three use cases share one platform

The deck separates three use cases that can share CI, signing, and rollout. They do not share a skill.

| Use case | The change | This repository |
| --- | --- | --- |
| CVE remediation | One advisory, one coordinate, the smallest delta. A Lightwell suffix on the same upstream version | The only use case the current skills are allowed to claim |
| Dependency freshness | A newer upstream line so the application stays current | Refuse, or relabel. Do not file it as the CVE fix |
| Business functional change | A feature or behavior change | Out of scope |

Change records in the deck are standard, normal (including a change-advisory board), or emergency. A single Lightwell pin, with the application's existing tests passing, is the shape of a standard change. The agent may say that in the pull request. The agent does not approve the change, and it does not open the operations ticket.

## The path after "patch released"

The deck's architecture, repeated across several slides, is:

1. A patch source publishes. Lightwell is the example the deck names. Other upstream sources exist beside it.
2. The artifact lands in an internal trusted repository. Artifactory is the example.
3. Something estate-aware decides this application is affected. Concert is the example. In this repository that input is the must-fix list from the scan.
4. An orchestrator can sequence the work. Ansible Automation Platform is the example. This repository does not replace it.
5. A dependency-update pull request is opened.
6. CI runs.
7. CD reaches clusters and virtual machines.

The trigger line in the deck is **patch released, for example Lightwell**, then the CVE scan, then the trusted repository, then sign and attest, then policy for the automatic patch, tests, and automerge, then whether the change is a standard change, the window, and the rollback.

One-time onboarding in the deck, which these agents do not perform, records the application's tier, its service level, its tests, and how the project is laid out.

## What the agent owes this clock

| Stage | Agent behavior |
| --- | --- |
| Triage | Choose among must-fix advisories that have a Lightwell fixed event. Severity and EPSS order the queue. They do not replace the event |
| Remediate | Edit the manifest to that coordinate. One advisory. One dependency |
| Test | The application still builds, existing tests still pass, and the resolved coordinate is the one requested |
| Deliver | Stop. The pull request is the handoff. Do not describe the running production revision as updated |

A pull request that bumps a family of dependencies, or that takes the newest version on Central because the advisory's upstream fix landed there, is a miss against this clock even when the build is green. It is the larger change the deck tells the program to keep separate.
