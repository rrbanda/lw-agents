---
title: Lightwell
summary: When the application library cannot move to a newer upstream version, a security-only backport on the version already running is the response.
---

Lightwell is a supplier of security-only backports for upstream open-source application libraries. It covers Java (Maven) and Python (PyPI) ecosystems. A vulnerability exists in a library version the application depends on. The application cannot upgrade to a newer upstream line because of certification, compatibility, a release window, or a pin. Lightwell publishes a fix on the exact version already running.

That fix is an application-layer artifact: libraries, frameworks, build tools, and transitive dependencies. It is not a platform patch. It is not a base image. It does not replace Red Hat Enterprise Linux, OpenShift, Advanced Cluster Security, or a hardened container foundation. Those products cover different layers.

## When Lightwell is the right response

| Situation | Right response |
| --- | --- |
| The vulnerability is in an upstream open-source library the application depends on, and the application cannot take a newer upstream version | Lightwell. A security-only backport on the same version |
| The application can upgrade to a newer upstream version that contains the fix | Upstream upgrade. Lightwell is not needed |
| The vulnerability is in the operating system or platform | Platform patch or erratum. Not an application library fix |
| The vulnerability is in the container base image | A hardened or minimal base image. Not an application dependency fix |
| The library is end-of-life and no backport is available | Accept, retire, or find an alternative. Lightwell covers libraries it has remediated |

## Two offers

| Offer | What the customer gets |
| --- | --- |
| Lightwell Network | Access to the catalog of validated and remediated repositories. Network customers consume what is published |
| Lightwell Clearing House | Network access, plus the ability to request remediations for specific upstream open-source libraries at any previous version, including transitive dependencies. Clearing House members can submit novel vulnerabilities found through frontier models and receive remediated packages under an embargo period before public disclosure |

Clearing House members are typically organizations that use frontier AI models to discover novel vulnerabilities in upstream open-source software. They request remediations from Red Hat through Lightwell. During the embargo period, the fix and the vulnerability details are not public, so that customers are not exposed by the disclosure itself.

## Two repository types

| Repository | What it contains |
| --- | --- |
| Validated | The upstream binary, rebuilt from source by Red Hat with signatures, attestations, and provenance. No security patches applied. It is the upstream release from a trusted source |
| Remediated | The same upstream version with a security-only patch applied by the Lightwell project. The package carries the `.rhlw` suffix for Java or `+rhlw` for Python |

## The version suffix

The pin keeps the upstream version the application already runs and adds a Lightwell suffix.

| Ecosystem | Shape | Example |
| --- | --- | --- |
| Java, remediated | `{upstream}.rhlw-` plus five digits | `3.14.0.rhlw-00001` |
| Python | PEP 440 local version, `+rhlw.` plus five digits | `1.0.0+rhlw.00001` |

`3.14.0` to `3.14.0.rhlw-00001` is a CVE remediation. `3.14.0` to `3.18.0` is a freshness upgrade. Even when `3.18.0` contains the upstream fix, using it is a different change with a different risk profile.

## The fixed event

A fixed event is an OSV document that says this advisory is fixed at a Lightwell coordinate. That document is the authority for the pin. The agent reads the fixed event to know which coordinate to use. It does not pick a version by guessing.

Other sources are evidence about the vulnerability, not a substitute coordinate:

| Source | What it tells the agent | What it does not decide |
| --- | --- | --- |
| Lightwell OSV | The coordinate to pin | |
| OSV.dev, GitHub Advisory | Upstream affected ranges | The Lightwell coordinate |
| NVD | CVSS, CWE, references | The coordinate |
| EPSS, KEV | Which advisory to do first | The coordinate |
| Maven Central | Whether an upstream version exists on Central | Whether to reject a `.rhlw` coordinate, which is not on Central |

## Repository URLs

Production repositories require a registry service account.

| Use | URL |
| --- | --- |
| Java validated | `https://packages.redhat.com/lightwell/java/validated` |
| Java remediated | `https://packages.redhat.com/lightwell/java/remediated` |
| Java OSV, remediated | `https://packages.redhat.com/lightwell/osv/java/remediated` |
| Python validated | `https://packages.redhat.com/lightwell/python/validated` |
| Python remediated | `https://packages.redhat.com/lightwell/python/remediated` |

Authentication is HTTP basic with the registry service account. The token stays on the artifact manager or in the CI settings. It does not go in the pull request.

A public demo index (no credentials required) is available for Java:

| Use | URL |
| --- | --- |
| Demo remediated | `https://packages.redhat.com/lightwell/public-lightwell-demo/java/remediated` |
| Demo OSV | `https://packages.redhat.com/api/pulp-content/public-lightwell-demo/osv/java/remediated/` |

## The 40-day problem

The embargo period for Clearing House remediations is approximately two weeks. After that, the fixed packages and OSV data become public. If the customer takes 40 days to patch, the advisory was public for 26 days before the application absorbed the fix. Lightwell has limited value when the consumption path is that slow.

The execution models described on this site exist to compress that interval. The agent changes the dependency version, runs the build, and opens a pull request in minutes. A developer reviews and merges. The goal is to reach 14 days or less, and ideally under a day.

## What sits beside Lightwell

| Product | Layer | Relation |
| --- | --- | --- |
| Red Hat Enterprise Linux, OpenShift, ACS | Operating system and platform | Complementary. Platform patches cover a different layer |
| Red Hat Hardened Images | Container foundation | The base image. Not an application library fix |
| Red Hat Trusted Profile Analyzer | SBOM analysis and vulnerability scanning | The scanner that produces the must-fix list. Not the library fix |
| Lightwell Lens | Console coverage report | Upload an SBOM and see which packages are in the catalog. Not a programmatic API for agents |
| IBM LSOS | Selected end-of-life Java frameworks | A different offer |

Applications consume Lightwell through an artifact repository (Artifactory, Nexus, or similar) that proxies `packages.redhat.com`. The same mirror patterns used for other Red Hat content apply in a disconnected environment.
