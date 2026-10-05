---
title: How to choose
summary: Three execution models, two optional add-ons. Start from what is stuck.
---

## Three execution models

| Model | What it means | When it fits |
| --- | --- | --- |
| **Pipeline only** | The pipeline runs stages 1 and 5 (discover and deliver). A person does triage, remediation, and testing manually | The organization is getting started, or does not want AI in the loop |
| **Pipeline with agents** | Agent tasks do triage, remediation, and test generation inside the pipeline. A person reviews and merges the PR | The organization wants to compress the 30-to-90-day interval. This is the main model |
| **Fully agentic** | A coordinator decides the next action across stages and applications without a fixed DAG. Not built | The handoff between pipeline runs is the bottleneck, and the organization is ready to grant bounded authority under explicit policy |

## Two optional add-ons

| Add-on | What it adds | When it fits |
| --- | --- | --- |
| **Assessment agents** | The vulnerability analysis agent (exploit-iq) answers "is this CVE exploitable in my application?" before remediation effort is spent. Reduces false-positive remediation | The must-fix list has many CVEs that turn out to be non-exploitable |
| **Lightwell integration** | Lightwell tools read the OSV feed and verify `.rhlw` versions. The agent pins a security-only backport when the application cannot take a newer upstream release | The fix comes from Lightwell instead of an upstream upgrade |

## Decision table

| What is stuck | Pipeline only | Pipeline with agents |
| --- | --- | --- |
| We do not know which CVEs affect us | Start here. Scanner + SBOM + policy gate | Same. The agent adds triage after the gate |
| Triage takes days | Person reads the report | Agent produces a prioritized list in minutes |
| The manifest change takes a developer sprint | Person edits, builds, opens PR | Agent edits, builds, opens PR. Person reviews |
| We need a CAB for every change | PR goes through CAB | Same. The agent opens the PR. The CAB reviews it |
| No external AI providers | Pipeline runs without AI | Use on-premise models (IBM Granite via vLLM, Ollama). Backend is pluggable |
| Thousands of applications | One pipeline run per app | Same. `/remediate` trigger automates the start |
| Fix comes from Lightwell | Person pins manually | Agent pins from Lightwell fixed event. See [Where Lightwell fits](05-lightwell.html) |
| Active exploit | SOC owns the response | Agent can compress remediation, but SOC decides priority |
| Under embargo | Fix may be in a private repo | Agent must not write embargoed detail to a public branch |
| Fixing non-exploitable CVEs | Person researches exploitability | Add assessment agents (exploit-iq) to deprioritize non-exploitable findings |

## Who says yes

| Persona | Pipeline only | Pipeline with agents |
| --- | --- | --- |
| Vulnerability management | Reads the scan report | Reviews the agent's prioritized issues |
| Application owner | Decides whether to take the change | Reviews the agent's pull request |
| Developer | Edits the manifest, opens the PR | Reviews and merges the agent's PR |
| Platform engineering | Maintains the pipeline | Adds agent tasks, manages the model backend |
| Change management | Approves the change type | Same. Agent provides evidence for standard change |
| SRE and operations | Owns rollout and rollback | Same. Agent stops at the PR |
| Risk owner | Accepts residual risk | Grants authority over what agents may do |

## Optionality tiers

Everything is optional except the scan-and-report foundation. The tiers build on each other.

| Tier | What it adds | What it compresses |
| --- | --- | --- |
| 1. Pipeline only | SBOM scan, vulnerability analysis, policy gate. Person reads and acts | Nothing. This is the baseline |
| 2. Add triage agents | Selection and analysis agents prioritize and open issues | Triage from about 5 days to minutes |
| 3. Add remediation agents | Remediation and test generation agents change the manifest and open PRs | Developer sprint from 5–14 days to minutes |
| 4. Add assessment agents | Exploitability analysis answers "is this real in my app?" | False-positive remediation effort |
| 5. Add Lightwell tools | Agent reads the Lightwell OSV feed and verifies `.rhlw` versions | Version search when Central does not have the fix |
| 6. Fully agentic | Coordinator across stages and applications. Not built | Handoff delays between pipeline runs |

## About the fully agentic model

A coordinator would replace the fixed DAG with dynamic action selection: which application, which CVE, what to do next. It gains the ability to sequence across the estate without a person starting each pipeline run. It loses the declared auditability of a pipeline YAML.

What must already be true before it is safe: one advisory at a time per application, a person still approves the pull request, no exploit procedure, no embargo leak, bounded authority, and written policy (not learned behavior).

This model is not built. It is a design target for organizations that have operated the pipeline model long enough to trust the agent's output.
