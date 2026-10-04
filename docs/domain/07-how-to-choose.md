---
title: How to choose
summary: A table from organizational constraints to execution model.
---

The choice depends on what the organization is stuck with, not on which model sounds most advanced. Start from the constraint.

## Decision table

| What is stuck | Pipeline only | Pipeline with agents | Fully agentic |
| --- | --- | --- | --- |
| We do not know which CVEs affect us | Start here. The scanner and SBOM analysis are the prerequisite for everything else | Same scanner. The agent adds triage and issue creation after the scan | Same scanner. The coordinator adds estate-level prioritization |
| We know the CVEs but triage takes days | The person reads the report and researches each advisory | The agent reads the advisories and produces a prioritized list in minutes | The coordinator triages across applications without per-issue human input |
| We can triage but the manifest change takes a sprint | The developer edits `pom.xml`, runs the build, opens the PR | The agent edits the manifest, runs the build, and opens the PR. The developer reviews and merges | Same, but the coordinator can sequence multiple applications |
| We need a change-advisory board for every change | The PR goes through the existing CAB process | Same. The agent opens the PR. The CAB reviews it. Nothing changes about the approval | The coordinator must respect the same CAB. Automerge is not available |
| We cannot connect to external AI providers | The pipeline runs without any AI. Manual triage and remediation | Use an on-premise model (IBM Granite via vLLM, OpenShift AI serving, Ollama). The agent backend is pluggable | Same requirement. The coordinator needs a model |
| We have thousands of applications | One pipeline run per application, each triggered manually or on a schedule | Same. One remediation per application per CVE. The `/remediate` trigger automates the start | The coordinator sequences across the estate. This is its main advantage |
| The fix comes from Lightwell | The developer pins the remediated coordinate manually | The agent pins the coordinate from the Lightwell fixed event. See [Lightwell](08-lightwell.html) | Same pin rules. The coordinator does not change the version authority |
| There is an active exploit | Incident response. The SOC owns this. The pipeline may run as part of the response, but the decision is human | Same. The agent can compress the remediation step, but the SOC decides the priority and the window | Same. The coordinator does not replace incident response |
| The vulnerability is under embargo | The fix may exist in a private repository. The pull request must not carry the advisory description | Same. The agent must not write embargoed detail to a public branch | Same. Written policy must enforce the boundary |

## Who says yes

| Persona | Pipeline only | Pipeline with agents | Fully agentic |
| --- | --- | --- | --- |
| Vulnerability management | Reads the scan report | Reviews the agent's prioritized issues | Grants the coordinator authority to triage |
| Application owner | Decides whether to take the change | Reviews the agent's pull request | Same review, unless automerge policy is granted |
| Developer | Edits the manifest, opens the PR | Reviews and merges the agent's PR | Reviews and merges, or approves automerge policy |
| Platform engineering | Maintains the pipeline | Adds agent tasks to the pipeline, manages the model backend | Deploys and monitors the coordinator service |
| Change management | Approves the change type | Same approval. The agent provides evidence for standard change classification | Same approval. The coordinator does not bypass CAB |
| SRE and operations | Owns rollout and rollback | Same. The agent stops at the pull request | Same, unless level 5 orchestrated rollout is granted |
| Risk owner | Accepts residual risk | Same. The agent does not accept risk | Grants the broader authority the coordinator needs |

## The short version

- If the organization does not yet have a pipeline that produces an SBOM and a vulnerability scan, **start with the pipeline**.
- If triage and remediation are the bottleneck and the change process requires human approval, **add agent tasks to the pipeline**.
- If handoffs between applications are the bottleneck and the organization is ready to grant bounded authority under explicit policy, **design toward the fully agentic model**, knowing it is not built yet.

The inline agent and the remote agent service are both "pipeline with agents." The choice between them depends on whether the organization needs multi-step reasoning, retry, and skill loading (remote service) or prefers a simpler, stateless agent call (inline).
