---
title: Boundaries
summary: Lightwell builds the library fix. This repository pins it into an application. The scanner only names what must be fixed.
---

Three systems show up in this repository's README, and they are not the same system.

| System | What it owns | What it does not own |
| --- | --- | --- |
| Lightwell | A security-only backport of an application library, on the version the application already runs, published as a signed artifact with an OSV fixed event | Scanning the customer's estate, opening the application's pull request, or replacing RHEL, OpenShift, or a hardened base image |
| Red Hat Trusted Profile Analyzer, as this repo uses it | The must-fix list for one application, today the file `must-fix-cves.json` | Building the Lightwell backport, and the console page called Lightwell Lens |
| `lw-agents` | Phase 09 for one application: choose a published advisory that has a Lightwell fixed coordinate, pin that coordinate, open a pull request, and stop for a person | Discovering vulnerabilities, writing the library patch, publishing the CVE record, or declaring production exposure gone |

:::in
The agent's job ends at a reviewed pull request for one pin. Production verification happens after that pull request is merged and deployed.
:::

## The name collision

**RHTPA** in this repository means the scan input. The selection agent calls `list_must_fix_cves` and reads that report. That is phase 09 intake for one application.

**Trusted Profile Analyzer** in the Lightwell workshop is also the SBOM system of record. The lab uploads a CycloneDX SBOM and an advisory so the image can be checked later. Same product family, later moment. This repository does not perform that upload.

**Lightwell Lens** is a console page at `console.redhat.com/lightwell/lens`. A person uploads an SBOM, a Maven POM, a Python requirements file, or a list of PURLs, and sees which names and versions are in the Lightwell catalog. Exact match means name and version. Partial match means the name only. It is a point-in-time coverage view. It is not the scanner, and it is not the pin.

:::out
There is no documented Lens API for these agents to call. Do not invent `POST /api/lens` or any coverage endpoint. The Service Accounts API on the Hybrid Cloud Console is IAM. It creates credentials. It does not query the Lightwell catalog.
:::

## Clocks that overlap

| Clock | Starts when | These agents |
| --- | --- | --- |
| CVE record | A private finding exists | Do not move the record. They consume it after it is public |
| Lightwell release | Lightwell has a library fix to build | Do not build it. They wait for the published coordinate |
| Customer patch-to-production | A fixed coordinate exists and an application still runs the affected version | This is their clock, and only the portion that ends in a pull request |

The customer clock is the one in [Customer clock](03-customer-clock.html). Lightwell's value in that model collapses when the application still takes longer than about two weeks to absorb a fix that is already published. These agents exist to shorten the pin, not to shorten discovery.

## What sits beside Lightwell

| Product | Layer | Relation |
| --- | --- | --- |
| RHEL, OpenShift, ACS | Operating system and platform | Complementary. Not where an application library pin is applied |
| Red Hat Hardened Images, Hummingbird in the workshop | Container foundation | The base image. Not the application dependency |
| Lightwell Network | Application libraries, frameworks, build tools, transitive dependencies | The catalog these agents pin from |
| IBM LSOS | Selected end-of-life Java frameworks | A different offer. Not this pipeline |

Lightwell is not delivered through Satellite content views. Applications consume it through an artifact repository that proxies `packages.redhat.com`. The same mirror patterns used for other Red Hat content apply in a disconnected environment. These agents do not run that mirror.

## Authority order

When two documents disagree, use the one higher on this list.

1. The fixed event for the advisory in front of the agent, from Lightwell OSV.
2. Current Lightwell Network documentation for repository layout, suffixes, and authentication.
3. This pack, for what `lw-agents` is allowed to do with those facts.
4. The workshop AsciiDoc, for the scored post-disclosure lab. The workshop's root README is stale and is not authority.
5. `skills/*/SKILL.md`, `docs/architecture.md`, and the repository README, for what the code does today.

:::now
The README says this repository is the agent application that powers the Lightwell engine. The architecture diagram's external systems are RHTPA, source control, the model, OpenCode, and Maven Central. Neither description is the domain model. The domain model is the table at the top of this page.
:::

## Glossary

| Term | Meaning in this pack |
| --- | --- |
| Pin | A manifest change to the exact coordinate named by a Lightwell fixed event. The upstream version stays. A suffix is added |
| Freshness | Moving to a newer upstream line because it is newer. Not CVE remediation |
| Fixed event | The OSV statement that names the coordinate where this advisory is fixed |
| Validated | The upstream release, republished by Red Hat with signature and metadata. Not a backport |
| Remediated | A security-only backport on a pinned baseline. It stays remediated until upstream accepts and releases the fix |
| Predisclosure | A novel fix held for members before public disclosure. Not the path these agents score |
| Network | The available Lightwell catalog: validated and remediated, plus predisclosure in the product docs |
| Clearinghouse Premier | Limited availability. Network, plus member-specific versions, embargo handling, and support. Same pin mechanism, different when the advisory is public |
| Embargo | The coordinated window before public disclosure. A pin can exist in a private proxy before the public OSV record |
| OSV.dev | The public open-source vulnerability database. Not the Lightwell OSV feed |
| Red Hat VEX | Product advisory data the current `lookup_vex` tool reads. Not a Lightwell fixed event |
