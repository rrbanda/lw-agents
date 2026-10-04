---
title: Start here
summary: A CVE is a publicly recorded flaw in software. Knowing the number is not the same as being safe.
---

A **CVE** (Common Vulnerabilities and Exposures) identifier is a public label for a security flaw in software. When a CVE is published, anyone can read its description, including attackers. The flaw exists whether or not the organization knows about it. The number makes it trackable. It does not make it fixed.

Getting from the number to a running application that no longer has the flaw is the actual work. That work crosses several people, several tools, and several approval steps. No single product or agent covers the whole path.

## Who cares, and about what

Different people in the organization own different parts of a CVE response. When someone says they want CVE handling to be agentic, the work they are pointing at depends on who they are.

| Who | What they are stuck with | What they want |
| --- | --- | --- |
| Vulnerability management | The queue of findings, false positives, and deciding which advisory to act on first | Faster triage, fewer false positives, clear priority |
| Application or service owner | Whether this application can absorb a change without breaking | Confidence that the fix does not introduce a new failure |
| Developer | The manifest, the build, and the pull request | The smallest change that lands the right coordinate |
| Platform engineering | The pipeline, the trusted repository, signing, and the gates | Agent tasks that fit inside the existing pipeline |
| Change management | Standard change, change-advisory board, or emergency | Evidence that the change qualifies as standard |
| SRE and operations | The maintenance window, rollout, and rollback | A pull request that stops before deployment |
| Risk owner | Exceptions, the service-level agreement, and residual risk | Authority over what an agent may do |
| Security operations (SOC) | Active exploitation, incidents, and indicators | Agents that stay out of incident response unless explicitly directed |

An agent can help with some of those rows. It cannot own all of them at once.

## What this site covers

:::cards
Concerns | The seven decisions an organization faces when a CVE is published. | 01-concerns.html
Lifecycle | Ten phases and where agents may assist, own a step, or must stay out. | 02-lifecycle.html
Solutions | Each kind of response and where it helps. | 03-solutions.html
Pipeline only | A CI/CD pipeline that finds what is wrong, without any AI. | 04-pipeline-only.html
Pipeline with agents | Two ways to put agent tasks inside the pipeline. | 05-pipeline-with-agents.html
Fully agentic | What a system with no fixed pipeline would own, and why it is not built yet. | 06-fully-agentic.html
How to choose | A table from organizational constraints to execution model. | 07-how-to-choose.html
Lightwell | When a security-only backport is the right response. | 08-lightwell.html
:::

## How to read the path

Start with [Concerns](01-concerns.html). Each page answers one question. You can stop after any page and know one more thing. The execution model pages are written in the same shape so they can be compared.

If you are looking for the repository's skill contract or agent map, those are in the Reference section of the sidebar.
