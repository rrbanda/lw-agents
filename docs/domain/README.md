---
title: From advisory to production
summary: A guide to understanding CVE vulnerabilities, choosing how to respond, and using agents to compress the time from advisory to production fix.
---

Organizations face a growing volume of published software vulnerabilities. Knowing a CVE number exists is not the same as being safe. The path from advisory to a running application that no longer has the flaw crosses scanners, libraries, pipelines, approvals, and deployments. No single tool covers the whole path.

This site walks that path, from the problem through the options, so you can decide what fits your organization.

## What this site covers

:::cards
Start here | What a CVE is and who in the organization cares. | start-here.html
Concerns | The seven decisions an organization faces when a CVE is published. | 01-concerns.html
CVE lifecycle | Ten phases from discovery to lessons learned, and where agents fit. | 02-lifecycle.html
Solutions | Each kind of response and where it helps. | 03-solutions.html
:::

:::cards
Pipeline only | A CI/CD pipeline that finds what is wrong, without any AI. | 04-pipeline-only.html
Pipeline with agents | Two ways to put agent tasks inside the pipeline. | 05-pipeline-with-agents.html
Fully agentic | What a system with no fixed pipeline would own, and why it is not built yet. | 06-fully-agentic.html
How to choose | A table from organizational constraints to execution model. | 07-how-to-choose.html
:::

## Who this is for

- **Anyone new to CVEs** who needs to understand the problem before choosing a tool.
- **Security and vulnerability management** teams deciding how to accelerate patching.
- **Platform engineers** evaluating where agents fit in their CI/CD pipelines.
- **Application owners and developers** who will review and merge the pull requests agents open.
- **Risk owners and change management** who need to know what agents do and do not decide.

## How to read it

Start with [Start here](start-here.html) if the vocabulary is new. Start with [Concerns](01-concerns.html) if you already know what a CVE is and want to understand the organizational decisions. Start with [Pipeline with agents](05-pipeline-with-agents.html) if you want to see the execution models directly.

Each page answers one question. You can stop after any page and know one more thing. The execution model pages are written in the same shape so they can be compared.

The [Lightwell](08-lightwell.html) page explains when a security-only backport for upstream open-source libraries is the right response. The [Reference](sources.html) section in the sidebar has the skill-author material for contributors to the agent code.
