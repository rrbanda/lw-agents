---
title: Sources
summary: What each source is allowed to prove. Current skill text proves only what the code does today.
---

Use a source for the column it owns. A workshop lab that demonstrates a pin does not prove a Lens API. A skill file that mentions OSV.dev does not prove that OSV.dev is the Lightwell feed.

## Working map

| Source | Proves | Does not prove |
| --- | --- | --- |
| CVE lifecycle notes, the static page and `app.js` phases | The ten phase texts, the four workstreams, the priority equation, and the AI controls, as transcribed in [CVE lifecycle](01-cve-lifecycle.html) | That the CVE Program standardized those ten names |
| [CVE Record Lifecycle](https://www.cve.org/about/Process) and [CVE Services](https://www.cve.org/AllResources/CveServices) | Formal record states: reserved, published, updated, rejected | A product mapping onto phase 09 |
| [CVSS specification](https://www.first.org/cvss/specification-document) | CVSS is a severity score. Several vectors can exist | Priority, or a coordinate |
| [EPSS FAQ](https://www.first.org/epss/faq) | EPSS is an estimated probability of exploitation | That a high score selects a version |
| [CISA KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) | Confirmed exploitation in the wild, when a CVE is listed | A Lightwell coordinate |
| [NVD](https://nvd.nist.gov/) | Published enrichment, including CVSS and CWE | The pin |

The lifecycle page's own footer applies here: it is a conceptual map, and processes vary.

## Lightwell product

| Source | Proves | Does not prove |
| --- | --- | --- |
| [Lightwell product page](https://www.redhat.com/en/lightwell) | The product exists and how Red Hat describes it | An API list |
| [Console](https://console.redhat.com/lightwell) and [Lens](https://console.redhat.com/lightwell/lens) | There is a console, and Lens is a page in it | A programmatic coverage API. The console is an authenticated application |
| Lightwell Network documentation on choosing a repository, configuring Java and Python, the patch-delivery lifecycle, and Artifactory | Repository roles, the suffix, and consumption through an artifact manager | That this repository's skills already follow those docs |
| HTTP checks in October 2026 | Production Java OSV indexes at the URLs in [Lightwell](02-lightwell.html) responded 401 without credentials. The public demo Java OSV index responded with a directory of JSON files | Python OSV. That feed is not documented |
| What's new for Lightwell Network | Predisclosure is a documented repository tier | That these agents select predisclosure coordinates by default |

Some Network doc URLs use the path `lightwell_network` and some use `red_hat_lightwell_network`. Follow the URL that resolves. Do not invent a third path.

Help and OSV troubleshooting live on the Lightwell Network troubleshooting and help page in that same documentation set.

## Workshop and customer kit

| Source | Proves | Does not prove |
| --- | --- | --- |
| [lightwell-tssc-workshop](https://github.com/rrbanda/lightwell-tssc-workshop) AsciiDoc, also published at [rhpds.github.io/lightwell-tssc-workshop](https://rhpds.github.io/lightwell-tssc-workshop) | The scored post-disclosure pin, the wrong answers, and the later hermetic, signing, admission, and TPA tracks | The root README. That file describes a different module outline and is stale |
| `appendix-lightwell-concepts.adoc` | Network versus Premier, embargo as a concept, validated versus remediated, and coexistence with RHEL, hardened images, and TSSC | Pricing, and a live Premier membership. The lab omits those |
| [lightwell-integrations](https://github.com/anurag-saran/lightwell-integrations) | How a customer proxy is pointed at the package directories | A Lens or coverage API. Artifactory and Nexus demo hosts in that kit are proxies |

The workshop's Trusted Profile Analyzer calls are evidence about that lab's deployment (`/api/v3/sbom`, `/api/v3/advisory`, OSV not OpenVEX). Trustify's own documentation has also described `/api/v2/sbom`. Neither version is universal.

## Planning deck

The 110-page deck *Secure SSC SDLC Lightwell Integration CVE Remediation* is the source for [Customer clock](03-customer-clock.html): the two-week claim, the day bands, levels 0 and 3–5, the three use cases, and the path from "patch released" to a pull request. Many middle slides repeat the same maturity picture. The deck is a planning model. It is not an API specification and not a service-level agreement.

## This repository, as evidence of current behavior only

| Source | Proves |
| --- | --- |
| `skills/cve-triage`, `skills/cve-analysis` | Central and OSV.dev are the version authorities in the text the agent loads today |
| `skills/maven-remediation`, `skills/gradle-remediation` | The edit is a manifest version change after an upstream-commit investigation |
| `skills/junit-test-generation` | Tests are asked to prove the vulnerability fix, including upstream reproducers |
| `skills/validation-architect`, `skills/validation-pentester` | Validation is an adversarial review of the vulnerability mechanism |
| `skills/scm-conventions` | The pull request template says bump, and it allows a source-patch claim |
| `docs/architecture.md` | External systems drawn today omit the Lightwell feed and the internal proxy |
| `docs/adr/002-agents-and-skills-first.md` | Skills hold the methodology. Agents load them. A domain correction belongs in the skill, after this pack |

## Explicitly not sources

- A guessed path for a Lens REST API.
- The Service Accounts OpenAPI document. It is IAM.
- Demo credentials for an Artifactory or Nexus proxy. They are not part of this pack, and they must not appear in a skill, a fixture, or a pull request.
- Memory of a catalog version that is not on the fixed event for the case.
