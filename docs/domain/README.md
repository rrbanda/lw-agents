---
title: From advisory to production
summary: A guide to understanding CVE vulnerabilities, choosing how to respond, and using agents to compress the time from advisory to production fix.
---

Organizations face a growing volume of published software vulnerabilities. Knowing a CVE number exists is not the same as being safe. The path from advisory to a running application that no longer has the flaw crosses scanners, libraries, pipelines, approvals, and deployments. No single tool covers the whole path.

This site walks that path in five layers, so you can understand the problem, see where agents help, and choose the right execution model.

## Understand

:::cards
Start here | What a CVE is and who in the organization cares. | start-here.html
Concerns | The seven decisions an organization faces when a CVE is published. | 01-concerns.html
CVE lifecycle | Ten phases from discovery to lessons learned. | 02-lifecycle.html
:::

## CVE tasks

:::cards
What people do | Every CVE task mapped to the patch-to-production flow, before any agent. | 03-cve-tasks.html
Where agents help | A matrix of every task mapped to agent capability. | 04-agent-matrix.html
Where Lightwell fits | When a security-only backport is the right response. | 05-lightwell.html
:::

## Execute

:::cards
The pipeline | One logical flow, five stages, split at human handoff points. | 06-the-pipeline.html
How to choose | Three execution models, two optional add-ons. | 07-how-to-choose.html
:::

## Who this is for

- **Anyone new to CVEs** who needs to understand the problem before choosing a tool.
- **Security and vulnerability management** teams deciding how to accelerate patching.
- **Platform engineers** evaluating where agents fit in their CI/CD pipelines.
- **Application owners and developers** who will review and merge the pull requests agents open.
- **Risk owners and change management** who need to know what agents do and do not decide.

## How to read it

Start with [Start here](start-here.html) if the vocabulary is new. Start with [What people do](03-cve-tasks.html) if you already know CVEs and want to see the task flow. Start with [The pipeline](06-the-pipeline.html) if you want the execution model directly.

Each page answers one question. You can stop after any page and know one more thing.
