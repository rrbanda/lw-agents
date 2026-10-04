---
title: Sources
summary: Where the facts on this site come from. Each source proves one thing.
---

## CVE and vulnerability standards

| Source | What it proves |
| --- | --- |
| [CVE Program — CVE Record Lifecycle](https://www.cve.org/about/Process) | Formal record states: reserved, published, updated, rejected |
| [CVE Program — CVE Services](https://www.cve.org/AllResources/CveServices) | How records are submitted and managed |
| [FIRST — CVSS specification](https://www.first.org/cvss/specification-document) | CVSS is a severity score. Multiple vectors can exist. It is not priority |
| [FIRST — EPSS FAQ](https://www.first.org/epss/faq) | EPSS is an estimated probability of exploitation |
| [CISA — Known Exploited Vulnerabilities](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) | Confirmed exploitation in the wild |
| [NVD](https://nvd.nist.gov/) | Published enrichment, including CVSS and CWE |

## Lifecycle

| Source | What it proves |
| --- | --- |
| CVE lifecycle notes (the static page with `app.js` phases) | The ten phase texts, the four workstreams, the priority equation, and the AI controls as transcribed on the Lifecycle page |

The lifecycle page's footer applies: it is a conceptual map, and processes vary by organization and ecosystem.

## Lightwell

| Source | What it proves |
| --- | --- |
| [Lightwell product page](https://www.redhat.com/en/lightwell) | The product exists and how Red Hat describes it |
| [Console](https://console.redhat.com/lightwell) and [Lens](https://console.redhat.com/lightwell/lens) | There is a console, and Lens is a page in it. Not a programmatic API |
| Lightwell Network documentation (choosing a repository, configuring Java and Python, patch-delivery lifecycle, Artifactory integration) | Repository roles, the suffix, and consumption through an artifact manager |
| HTTP checks (October 2026) | Production Java OSV indexes returned 401 without credentials. The public demo Java OSV index returned a directory of JSON files |

## Workshop

| Source | What it proves |
| --- | --- |
| [lightwell-tssc-workshop](https://github.com/rrbanda/lightwell-tssc-workshop) AsciiDoc | The scored post-disclosure pin (`org.apache.commons:commons-lang3:3.14.0.rhlw-00001` for `LW-DEMO-0002`), the wrong answers, and the later hermetic, signing, admission, and TPA tracks |
| [lightwell-integrations](https://github.com/anurag-saran/lightwell-integrations) | How a customer proxy is pointed at the package directories |

## Execution models

| Source | What it proves |
| --- | --- |
| `ssc-demo` — `maven-build-ci-pipeline.yaml` | The pipeline-only model: clone, build, SBOM, scan, policy, ACS checks, deploy. No AI |
| `ssc-demo` — `agentic-cve-selection.yaml`, `agentic-cve-analysis.yaml`, `agentic-cve-remediation.yaml`, `agentic-test-generation.yaml` | The inline agent model: same pipeline head, then an `ai-*` task. Six-field contract. Manual handoff between selection and remediation |
| `ssc-demo` — `lw-cve-selection.yaml`, `lw-cve-analysis.yaml`, `lw-cve-remediation.yaml`, `lw-test-generation.yaml` | The remote agent service model: same pipeline head, then an `lw-*` task that calls an ADK service over SSE |
| `ssc-demo` — demo narrative | End-to-end evidence: 77 CVEs scanned, 56 fixable, 13 issues created. Successful remediation with `CHANGED=1`. Incompatible fix correctly rejected with `CHANGED=0` |

## Not sources

- Confidential handbooks or sales materials. Not quoted and not committed.
- A guessed path for a Lens REST API.
- The Service Accounts OpenAPI document. It is IAM, not Lightwell catalog data.
- Demo credentials for an Artifactory or Nexus proxy.
- Memory of a catalog version that is not on the fixed event for the case in front of the agent.
