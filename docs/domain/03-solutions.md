---
title: Solutions
summary: Each kind of response helps in one place. Agents are a way to do the work faster, not a new kind of fix.
---

A CVE can sit in different layers of the software stack. The right response depends on which layer the vulnerability is in and whether the application can absorb a change.

## Kinds of response

| Response | What layer it covers | When it helps |
| --- | --- | --- |
| Scanner or SBOM analysis | Discovery and inventory | You need to know whether the flaw is in software you run. A scanner compares advisories against your bill of materials. This is the intake for everything else |
| Upstream upgrade | The application library | The application can move to a newer version of the library that contains the fix. This is the simplest path when compatibility allows it |
| Security-only backport (Lightwell) | Upstream open-source application libraries | The application cannot move to a newer upstream version because of certification, compatibility, a release window, or a pin. Lightwell publishes a fix on the exact version already running. The application changes one dependency coordinate |
| Platform patch or erratum | The operating system | Red Hat Enterprise Linux, OpenShift, or another platform ships a fix for the OS layer. This does not fix an application library |
| Hardened base image | The container foundation | A hardened or minimal base image reduces the surface of the container runtime. This does not fix an application dependency |
| Compensating control | Network, runtime, or configuration | A firewall rule, a WAF signature, a runtime policy, or a configuration change reduces exposure while a fix is in progress |
| Accept or retire | Risk decision | The vulnerability is accepted with documentation, or the component is removed from service |

Agents do not add a new kind of fix. They are a way to do the work inside one of these responses faster and with less manual effort. The execution model pages describe [three ways](04-pipeline-only.html) to [use agents](05-pipeline-with-agents.html) for that acceleration.

## The upstream library problem

Platform patches and base images are delivered through channels the organization already consumes: errata, content views, image streams. The operating system team applies them. The application team does not change application code for a platform patch.

Upstream open-source libraries are different. They sit inside the application's dependency tree. A vulnerability in `spring-security-web` or `commons-lang3` is the application team's problem. The fix requires a manifest change, a build, tests, and a pull request. That pull request goes through the application's change process, not the platform's.

When the application can take a newer upstream release, the fix is an upgrade. When it cannot, the options are:

- **Wait** for the upstream project to backport the fix to the version the application uses, which may never happen.
- **Do it yourself**, which means maintaining a private fork of the library with the security patch applied.
- **Use a supplier** that publishes a security-only backport on the version already running, signed, with an SBOM, and with an advisory that says what was fixed. Lightwell is that supplier for Java and Python upstream open-source libraries.

In all three cases, the application team still has to change the manifest, rebuild, test, and ship. That is the 30-to-90-day interval. The execution model pages describe how to compress it.

## What agents actually do in this context

An agent does not scan, and it does not build the library fix. It sits between the scan result and the pull request.

| Step | Without an agent | With an agent |
| --- | --- | --- |
| A scanner reports 77 CVEs for this application | A person reads the report | Same report, same scanner |
| Triage: which ones have a fix, and which to do first | A person researches each advisory, checks versions, estimates blast radius. About 5 days | An agent reads the advisories, checks the fixed coordinates, and produces a prioritized list. Minutes |
| Remediate: change one dependency | A developer opens `pom.xml`, changes the version, runs the build, runs tests, opens a pull request. 5 to 14 days | An agent changes the version, runs the build, runs tests, and opens a pull request. Minutes, with a person reviewing before merge |
| Test: prove the application still works | A developer writes or runs tests. 1 to 3 days | An agent runs the application's existing tests. The build is green or it is not |
| Deliver: get the change to production | Manual rollout and rollback. 14 to 90 days | The agent stops at the pull request. Delivery is still the organization's pipeline |

The agent compresses triage and remediation from weeks to minutes. It does not compress delivery, because delivery is a deployment and rollback decision that belongs to operations.

## Three use cases, one platform

The CI pipeline, the signing, and the rollout can be shared across three use cases. The agent skills are different.

| Use case | The change | Agent role |
| --- | --- | --- |
| CVE remediation | One advisory, one dependency, the smallest change that lands the fixed coordinate | The use case the execution model pages describe |
| Dependency freshness | A newer upstream line so the application stays current | A different skill. Not the CVE fix even when the newer line contains the fix |
| Business functional change | A feature or behavior change in the application | Out of scope for CVE agents |

A pull request that moves `commons-lang3` from `3.14.0` to `3.18.0` is freshness even if `3.18.0` contains the upstream fix. The CVE remediation is `3.14.0` to `3.14.0.rhlw-00001`, which is the same version with only the security patch applied. These are different changes with different risk profiles and different approval paths. Mixing them extends the clock.
