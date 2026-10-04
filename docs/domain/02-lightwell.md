---
title: Lightwell
summary: The catalog, the suffix, the OSV fixed event, and the surfaces that are not an API for these agents.
---

Scanners find vulnerabilities in application libraries. The application often cannot move to a newer upstream release, because of certification, compatibility, a release window, or a pin. Lightwell publishes a security-only backport on the version already running.

That backport is an application-layer artifact: libraries, frameworks, build tools, and transitive dependencies. It is not an operating-system erratum and not a new base image.

## Network and Premier

| Offer | What a consumer gets | What this repository scores |
| --- | --- | --- |
| Lightwell Network | The catalog. Validated and remediated repositories, consumed through the build's existing artifact manager. Public docs also describe a predisclosure repository | The post-disclosure Network path |
| Clearinghouse Premier | Network, plus member-specific versions, verification of novel vulnerabilities, embargo handling, anonymized member requests, and a technical account manager. Limited availability | Not scored. A Premier pin would still be a coordinate from a fixed event, resolved through the same proxy |

An embargo is the coordinated-disclosure window. The vulnerability and the patch stay with a closed set of members until a public date. During that window a member can receive a private pin before the public OSV record exists. Network's published lifecycle ends at public disclosure. These agents run after that. A public pull request must not carry embargoed detail. See the [skill contract](05-skill-contract.html).

## Two repositories, one baseline

| Repository | Artifact | When it is the right pin |
| --- | --- | --- |
| Validated | The upstream binary, republished from Red Hat, signed, with SBOM and provenance. The workshop describes it as the upstream binary from a trusted Red Hat source, checked for known CVEs | When the fixed event names that republished upstream coordinate. It is not a backport |
| Remediated | A security-only patch on a pinned baseline | When the fixed event names a `.rhlw` or `+rhlw` coordinate. It stays remediated until upstream accepts the fix and releases it |
| Predisclosure | A novel fix built before public disclosure, on the latest remediated baseline | Only when the case is explicitly that private advisory. Not the default, and not the public demo |

When more than one Lightwell build exists for a line, the usual order is predisclosure, then remediated, then validated. The agent does not pick from that order. It uses the coordinate on the fixed event.

Customer testing of the application remains the customer's job. Red Hat tests the library before publishing it. These agents run the application's build and the application's existing tests. They do not re-decide whether the library patch is correct.

## Version grammar

The pin keeps the upstream version the application already runs, then adds a Lightwell suffix.

| Ecosystem | Shape | Example |
| --- | --- | --- |
| Java, remediated | `{upstream}.rhlw-` plus five digits | `3.14.0.rhlw-00001`. The next fix on that baseline is `3.14.0.rhlw-00002` |
| Java, predisclosure | the remediated form plus `-n` and four digits | `5.3.17.rhlw-00001-n0001` |
| Python | PEP 440 local version, `+rhlw.` plus five digits | `1.0.0+rhlw.00001` |

:::in
`org.apache.commons:commons-lang3:3.14.0` affected, fixed by `3.14.0.rhlw-00001`, is a pin. `3.14.0` to `3.18.0` is freshness. Freshness is not this use case even when `3.18.0` is the upstream release that contains a fix.
:::

Java source archives ship beside the binaries. Agents do not need them to pin. They are how a person diffs the backport. They are not an invitation to patch the library inside the application repository.

## Where the bytes are

Production repositories require a registry service account. Unauthenticated requests to the production Java OSV indexes returned 401.

| Use | URL |
| --- | --- |
| Java validated | `https://packages.redhat.com/lightwell/java/validated` |
| Java remediated | `https://packages.redhat.com/lightwell/java/remediated` |
| Java predisclosure | `https://packages.redhat.com/lightwell/java/predisclosure` |
| Java OSV, remediated | `https://packages.redhat.com/lightwell/osv/java/remediated` |
| Java OSV, predisclosure | `https://packages.redhat.com/lightwell/osv/java/predisclosure` |
| Python validated | `https://packages.redhat.com/lightwell/python/validated` |
| Python remediated | `https://packages.redhat.com/lightwell/python/remediated` |
| Python simple index | the repository URL plus `/simple` |

There is no documented Python OSV feed. Do not invent one. A Python pin still needs a fixed event the case actually has, or the agent reports that it cannot see one.

Authentication is HTTP basic. The username is the registry service account in the form `{numeric-id}|{service-account-name}`. The password is that account's token. The token stays on the artifact manager, or in the CI settings that already exist for the build. It does not go in `pom.xml`, and it does not go in the pull request.

Public demo, no credentials, Java only, no predisclosure repository:

| Use | URL |
| --- | --- |
| Demo validated | `https://packages.redhat.com/lightwell/public-lightwell-demo/java/validated` |
| Demo remediated | `https://packages.redhat.com/lightwell/public-lightwell-demo/java/remediated` |
| Demo OSV | `https://packages.redhat.com/api/pulp-content/public-lightwell-demo/osv/java/remediated/` |

The demo OSV index is a public directory of JSON files. It is a demonstration feed, not the production id scheme. Production advisory ids look like `RHLW-YYYY-NNNN`. Workshop samples look like `LW-DEMO-0002`. The agent uses the id on the event it was given. It does not translate one scheme into the other.

An optional poll of `{java-osv-url}/PULP_MANIFEST` tells a mirror that the index changed. A changed digest means read the index. The manifest is not a version to pin.

## The fixed event

A fixed event is an OSV document whose affected range says this advisory is fixed at a Lightwell coordinate.

That document is the authority for the pin. The following are evidence about the vulnerability, and they are not a substitute coordinate:

| Source | What it can tell the agent | What it must not decide |
| --- | --- | --- |
| Lightwell OSV | The coordinate to pin, and the advisory id | |
| OSV.dev and GitHub Advisory | Upstream affected ranges and the upstream release that contains a fix | The Lightwell coordinate |
| NVD | CVSS, CWE, references | The coordinate |
| `lookup_vex` as implemented today | Red Hat product VEX | A Maven or Python pin |
| Maven Central `check_version_exists` | Whether an upstream version is on Central | Rejection of a `.rhlw` coordinate. Those coordinates are not on Central |
| EPSS and KEV | Which advisory to do first, among advisories that have a fixed event | The coordinate |

Resolution is part of the fix. The build must download that coordinate from the internal repository that proxies Lightwell. A tree that resolves the same string from Maven Central is the wrong repository. The agent's diff changes the manifest. The repository manager, already configured, performs the fetch. The agent does not paste a token into the project to make the fetch work.

## Workshop fixtures

The scored lab is a seven-track Java Maven path on OpenShift. The root README of the workshop repository describes a different outline and is stale. The scored pin is:

| | |
| --- | --- |
| Advisory | `LW-DEMO-0002` |
| Coordinate | `org.apache.commons:commons-lang3:3.14.0.rhlw-00001` |
| Affected | `3.14.0` |
| Remediation statement used by the lab | `via-lightwell-pin` |

These are wrong answers for that case, and a future eval treats them as wrong:

| Wrong answer | Why |
| --- | --- |
| `3.18.0` | A newer Central line. Freshness |
| `3.14.0` | The affected upstream version. The lab forbids claiming it is fixed |
| `3.14.0.rhlw-00000` | The pre-pin marker in the workshop pins file, not the fixed event |
| `org.springframework:spring-core:5.3.18.rhlw-00003` with `LW-DEMO-0001` | A worked example of a different advisory. Using it as the pin for the commons-lang3 case fails the lab check |

The lab's later tracks bind that pin into Git, build hermetically, sign, admit, and record the SBOM in Trusted Profile Analyzer. Those tracks are the customer's platform. They are context. They are not steps the agent performs. The agent must not report them as done because the manifest changed.

## Surfaces that are not the pin API

**Lens.** Console upload of SPDX, CycloneDX, `pom.xml`, `requirements.txt`, or PURLs. The report is exact matches, partial matches, an ecosystem breakdown, and a searchable inventory. The catalog was described as more than 15,000 package versions and growing. Match percentage is not the value of the catalog. Quality of the remediations that matter is the point of the page. Continuous monitoring is Trusted Profile Analyzer, not Lens. No Lens book was published under `lightwell_lens` or `red_hat_lightwell_lens` at the time of this research. Do not call a coverage API that is not documented.

**Trusted Profile Analyzer.** The workshop uploads CycloneDX to `/api/v3/sbom` and an advisory to `/api/v3/advisory`. That lab accepts CSAF, CVE, or OSV as the advisory. It does not accept an OpenVEX document as the SBOM or as that advisory upload. Other Trustify documentation has shown `/api/v2/sbom`. The version belongs to the deployment the agent was pointed at. Read that deployment's API. Do not hardcode v2 or v3 as universal, and do not upload anything from this pipeline unless the task is explicitly that ingest.

**lightwell-integrations.** A customer kit that points Maven at Artifactory or Nexus, and points those at `packages.redhat.com`. The demo hosts are proxies. They are not a Lightwell product API. An Xray client in that kit posts to JFrog's events API. That is JFrog, not Lightwell.

**Service accounts.** The console API at `/apis/service_accounts/v1`, loaded from `service-accounts.yaml`, creates Hybrid Cloud Console service accounts. Scope `api.iam.service_accounts`. It does not list Lightwell packages.

## Provenance, for a person checking an artifact

Agents do not need these URLs to open a pin. They are where a reviewer finds the supplier's metadata.

| Ecosystem | Where it lives |
| --- | --- |
| Java | `cyclonedx.json` beside the jar, with the signature |
| Python | SPDX at `*.dist-info/sboms/redhat.spdx.json` inside the wheel |
| Python provenance | `https://packages.redhat.com/api/pypi/lightwell/python/{repo}/integrity/{package}/{version}/{wheel}/provenance/` |

Compliance artifacts described for the catalog include SLSA build level 3, signing, CycloneDX and VEX for Maven, and SPDX for Python wheels. Verifying that provenance is the customer's admission policy. It is not a step in `maven-remediation`.

## What an agent may assume

- A Lightwell pin is the same upstream version plus the suffix grammar above.
- The fixed event names the coordinate. Central, OSV.dev, and NVD do not.
- The token never enters the git diff.
- Java OSV is the documented feed. Python OSV is not documented.
- Lens has a console UI and no documented programmatic coverage API.
- Premier and predisclosure exist. This pipeline's default case is a public Network remediated pin.
- The application may run on a non-Red Hat operating system. Do not require RHEL to accept the pin.
