---
title: Where Lightwell fits
summary: Lightwell changes one task in the CVE flow. Everything else stays the same.
---

The [CVE task flow](03-cve-tasks.html) and the [agent matrix](04-agent-matrix.html) work without Lightwell. Lightwell is an add-on that changes where the fixed version comes from when the application cannot take a newer upstream release.

## Which task changes

In stage 3 (Remediate), the task "Identify the fixed version" has two paths:

| Path | When it applies | What the version looks like |
| --- | --- | --- |
| Upstream upgrade | The application can move to a newer version that contains the fix | `3.18.0` — a standard upstream release on Maven Central or PyPI |
| Lightwell backport | The application cannot upgrade because of certification, compatibility, a release window, or a pin | `3.14.0.rhlw-00001` — the same upstream version with a security-only patch applied by Lightwell |

Everything else in the flow — discover, triage, edit the manifest, build, test, review, deliver — is the same regardless of whether the fix comes from upstream or Lightwell.

## What Lightwell is

A supplier of security-only backports for upstream open-source application libraries. Java (Maven) and Python (PyPI). The backport keeps the version the application already runs and adds a Lightwell suffix. It is not a platform patch, not a base image, and not a scanner.

| Offer | What the customer gets |
| --- | --- |
| Lightwell Network | The catalog of validated and remediated repositories. Consume what is published |
| Lightwell Clearing House | Network plus the ability to request remediations for specific upstream libraries at any previous version, including transitive dependencies. Members can submit novel vulnerabilities found through frontier models under an embargo period |

## The version suffix

| Ecosystem | Shape | Example |
| --- | --- | --- |
| Java, remediated | `{upstream}.rhlw-` plus five digits | `3.14.0.rhlw-00001` |
| Python | PEP 440 local, `+rhlw.` plus five digits | `1.0.0+rhlw.00001` |

`3.14.0` to `3.14.0.rhlw-00001` is a CVE remediation. `3.14.0` to `3.18.0` is freshness. Even when `3.18.0` contains the upstream fix, using it is a different change with a different risk profile.

## The fixed event

The Lightwell OSV feed publishes an advisory document that says: this CVE is fixed at this coordinate. That document is the version authority for the pin. Not Maven Central, not OSV.dev, not NVD.

| Source | What it tells the agent | What it does not decide |
| --- | --- | --- |
| Lightwell OSV feed | The coordinate to pin | |
| OSV.dev, GitHub Advisory | Upstream affected ranges | The Lightwell coordinate |
| NVD | CVSS, CWE | The coordinate |
| Maven Central | Whether an upstream version exists | Whether a `.rhlw` version exists (it does not appear on Central) |

## What tools the agent needs

Without Lightwell tools, the agent cannot find or verify a `.rhlw` version. These tools were added to close that gap.

| Tool | What it does |
| --- | --- |
| `lookup_lightwell_osv(advisory_id)` | Read the Lightwell OSV feed and return the fixed coordinate, affected ranges, and advisory metadata |
| `check_lightwell_version_exists(group_id, artifact_id, version)` | Verify a `.rhlw` version exists in the Lightwell repository |
| `check_version_exists_smart(group_id, artifact_id, version)` | Auto-route: `.rhlw` suffix goes to Lightwell, everything else goes to Maven Central |
| `list_lightwell_advisories()` | List available advisory IDs from the PULP_MANIFEST index |

### Authentication

Production repositories require `LIGHTWELL_USERNAME` and `LIGHTWELL_TOKEN` environment variables (registry service account). The public demo feed requires no credentials:

```
LIGHTWELL_OSV_BASE_URL=https://packages.redhat.com/api/pulp-content/public-lightwell-demo/osv/java/remediated
```

## Repository URLs

| Use | URL |
| --- | --- |
| Java validated | `https://packages.redhat.com/lightwell/java/validated` |
| Java remediated | `https://packages.redhat.com/lightwell/java/remediated` |
| Java OSV, remediated | `https://packages.redhat.com/lightwell/osv/java/remediated` |
| Python validated | `https://packages.redhat.com/lightwell/python/validated` |
| Python remediated | `https://packages.redhat.com/lightwell/python/remediated` |

Applications consume Lightwell through an artifact manager (Artifactory, Nexus) that proxies `packages.redhat.com`. The token stays on the artifact manager, not in the pull request.

## When Lightwell is not the answer

| Situation | Right response |
| --- | --- |
| The application can upgrade to a newer upstream version | Upstream upgrade. Simpler, no Lightwell needed |
| The vulnerability is in the operating system | Platform patch or erratum |
| The vulnerability is in the container base image | Hardened or minimal base image |
| The library is not in the Lightwell catalog | Upstream upgrade, private fork, or accept/retire |

## What does NOT change when Lightwell is added

Every other task in the flow is identical:

- The scanner still produces the must-fix list
- The policy gate still filters by severity
- The agent still selects one CVE and opens one issue
- The manifest edit is still one dependency, one version
- The build and test run the same way
- The pull request still needs human approval
- Delivery is still the organization's CI/CD

The only difference is the version string in the manifest and where it resolves from.
