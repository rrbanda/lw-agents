---
name: domain-knowledge
description: >
  CVE lifecycle, Lightwell, and software supply chain security domain
  knowledge. Load this skill when the user asks conceptual or explanatory
  questions about CVEs, the remediation lifecycle, CVSS vs EPSS,
  Lightwell backports, or how the agents fit into the broader picture.
---

# Domain Knowledge — CVE Lifecycle and Lightwell

## When to Load This Skill

Load this when the user asks questions like:
- "What is a CVE?"
- "Why not just upgrade to the latest version?"
- "What is Lightwell?"
- "What does EPSS mean?"
- "Where do agents fit in the CVE lifecycle?"
- "What is the difference between severity and priority?"
- Any conceptual or domain-specific question

## The CVE Lifecycle — Ten Phases

A vulnerability moves through an ecosystem in phases. These are a working
map, not the names of states in the CVE Program.

| Phase | Name | Owner | Purpose |
|-------|------|-------|---------|
| 01 | Discover | Research | Find a weakness, build evidence |
| 02 | Intake | Disclosure intake | Route, acknowledge, track the report |
| 03 | Validate and scope | Product security | Reproduce, deduplicate, identify affected versions |
| 04 | Reserve and coordinate | CNA | CVE ID, embargo, disclosure plan |
| 05 | Assess in parallel | Scoring and threat analysis | CVSS, EPSS, exploit conditions, detections |
| 06 | Fix and release | Engineering | Design the fix, test, backport, sign, release |
| 07 | Publish and enrich | CNA and publishers | Public CVE record, advisories, enrichment |
| 08 | Repackage and integrate | Supply chain | Ingest the fix, rebuild packages, update dependencies |
| 09 | Prioritize and remediate | Vulnerability management | Match to assets, prioritize, patch or mitigate |
| 10 | Observe and learn | SOC and governance | Detect exploitation, postmortems, improve controls |

**These agents occupy Phase 09 only.** They do not discover, validate,
reserve, score, fix the library, publish the record, or handle incidents.
Their output is a pull request that a person can merge. Deployment and
verification that the running estate is clean are later work.

## Where Each Agent Fits

| Agent | Lifecycle Phase | Bounded Step |
|-------|----------------|--------------|
| `cve_selection` | Phase 09 — Prioritize | Select ONE advisory from the must-fix set |
| `cve_analysis` | Phase 09 — Prioritize | Assess every CVE for fixability, open issues |
| `cve_test_investigator` | Phase 09 — Verify | Research a CVE, produce a test specification |
| `remediation` | Phase 09 — Remediate | Change the manifest, build, open a pull request |
| `test_generation` | Phase 09 — Verify | Generate tests proving the fix works |
| `fix_validation` | Phase 09 — Verify | Adversarial security review of the fix |

Each agent owns ONE bounded step. A person reviews and merges.

## Severity Is Not Priority

Three different signals are often confused:

| Signal | What It Is | Example |
|--------|-----------|---------|
| **CVSS** | Technical severity. Intrinsic characteristics and impact. A number from 0 to 10 published by the CNA or NVD | CVSS 9.8 (CRITICAL). Tells you the bug is bad, not that anyone is attacking it |
| **EPSS** | Exploit Probability Scoring System. Estimates the likelihood of exploitation in the wild in the next 30 days. A probability from 0 to 1 | EPSS 0.87 means 87% chance of exploitation. Best predictor of real-world attacks |
| **KEV** | Known Exploited Vulnerabilities catalog from CISA. Binary: this CVE IS being exploited in the wild | If it's on KEV, it's urgent. Period |
| **Business context** | Exposure, reachability, compensating controls, operational risk | A CVSS 9.8 in a library your code never calls is less urgent than a CVSS 7.5 in your login flow |

**Priority = severity + threat evidence + environmental context.**

EPSS is especially valuable because a CVE with CVSS 7.5 and EPSS 0.9 is
more dangerous in practice than a CVE with CVSS 9.8 and EPSS 0.01. The
agents use EPSS scores in triage and analysis for exactly this reason.

## CWE — Common Weakness Enumeration

CWE classifies the *type* of weakness. CVE is a specific instance. CWE
tells the test-generation agent WHAT KIND of test to write.

| CWE | Vulnerability Type | Test Strategy |
|-----|--------------------|---------------|
| CWE-79 | Cross-Site Scripting (XSS) | Verify special chars are escaped |
| CWE-89 | SQL Injection | Verify parameterized queries |
| CWE-94 | Code Injection | Verify untrusted input is rejected |
| CWE-400 / CWE-770 | Resource Exhaustion / DoS | Verify oversized input is bounded |
| CWE-502 | Deserialization of Untrusted Data | Verify untrusted types are rejected |
| CWE-22 | Path Traversal | Verify `../` is normalized or rejected |
| CWE-611 | XML External Entity (XXE) | Verify external entities disabled |
| CWE-601 | Open Redirect | Verify URL host is validated |

## Lightwell — Security-Only Backports

### The Problem

A scanner finds a vulnerability in `commons-lang3:3.14.0`. The upstream
fix is in `3.18.0`. But the application cannot upgrade to `3.18.0`
because of certification, compatibility, a release window, or a
dependency pin. What do you do?

Options:
- **Wait** for upstream to backport to 3.14.x — may never happen
- **DIY** — maintain a private fork with the security patch. Expensive
- **Use Lightwell** — get `3.14.0.rhlw-00001`, which is 3.14.0 with
  ONLY the security patch applied, built and signed by Red Hat

### Pin vs Freshness

| Change | What It Is | Risk Profile |
|--------|-----------|--------------|
| `3.14.0` → `3.14.0.rhlw-00001` | **CVE remediation** (Lightwell pin). Same version, security patch only | Minimal. No API changes, no behavioral changes |
| `3.14.0` → `3.18.0` | **Freshness upgrade**. Newer upstream with the fix | Higher. May include breaking API changes, new behaviors, transitive bumps |

Even when `3.18.0` contains the upstream fix, using it is a DIFFERENT
change with a DIFFERENT approval path. Mixing remediation and freshness
extends the clock.

### Two Repository Types

| Repository | What It Contains | When to Use |
|------------|-----------------|-------------|
| **Validated** | Upstream binary, rebuilt from source by Red Hat, signed, with SBOM and provenance. No patches applied | When the fixed event names that upstream coordinate |
| **Remediated** | Same upstream version + security-only patch. Carries the `.rhlw` suffix | When the fixed event names a `.rhlw` coordinate |

### Version Suffix Grammar

| Ecosystem | Format | Example |
|-----------|--------|---------|
| Java, remediated | `{upstream}.rhlw-NNNNN` | `3.14.0.rhlw-00001` |
| Java, predisclosure | `{upstream}.rhlw-NNNNN-nNNNN` | `5.3.17.rhlw-00001-n0001` |
| Python | PEP 440 local version `+rhlw.NNNNN` | `1.0.0+rhlw.00001` |

### The Fixed Event

The Lightwell OSV document is the **version authority** for a Lightwell
pin. It says: "This advisory is fixed at this coordinate."

Other sources are evidence about the vulnerability, not a substitute:

| Source | What It Tells the Agent | What It Does NOT Decide |
|--------|------------------------|------------------------|
| Lightwell OSV (`lookup_lightwell_osv`) | The coordinate to pin | |
| OSV.dev, GitHub Advisory | Upstream affected ranges | The Lightwell coordinate |
| NVD | CVSS, CWE, references | The coordinate |
| Maven Central (`check_version_exists`) | Whether an upstream version exists | Whether to reject a `.rhlw` version (those are NOT on Central) |
| EPSS, KEV | Which advisory to do first | The coordinate |

### Repository URLs

| Use | URL |
|-----|-----|
| Java remediated (production) | `https://packages.redhat.com/lightwell/java/remediated` |
| Java OSV feed (production) | `https://packages.redhat.com/lightwell/osv/java/remediated` |
| Java remediated (public demo) | `https://packages.redhat.com/lightwell/public-lightwell-demo/java/remediated` |
| Java OSV feed (public demo) | `https://packages.redhat.com/api/pulp-content/public-lightwell-demo/osv/java/remediated/` |

Production requires `LIGHTWELL_USERNAME` and `LIGHTWELL_TOKEN` (registry
service account). The demo feed is public, no credentials needed.

### Two Offers

| Offer | What the Customer Gets |
|-------|----------------------|
| **Lightwell Network** | The catalog of validated and remediated repositories |
| **Lightwell Clearing House** | Network + member-specific versions, novel vulnerability remediation, embargo handling, and a technical account manager |

### The 40-Day Problem

If the embargo period is ~2 weeks and the customer takes 40 days to
patch, the advisory was public for 26 days before the application
absorbed the fix. **Lightwell has limited value when consumption is that
slow.** The agents exist to compress the interval from 30–90 days to
under a day: change the manifest, build, test, open a PR — all in
minutes. A developer reviews and merges.

## What Agents Do NOT Do

- Agents do not **discover** vulnerabilities (Phase 01)
- Agents do not **validate** or reproduce exploits (Phase 03)
- Agents do not **build the library fix** — that's Lightwell's job (Phase 06)
- Agents do not **publish** CVE records (Phase 07)
- Agents do not **deploy** — they stop at the pull request
- Agents do not **handle incidents** (Phase 10)
- Agents do not **auto-merge** — a person always reviews

## Three Execution Models

| Model | How It Works | What a Person Still Does |
|-------|-------------|------------------------|
| **Pipeline only** | Scan, report, policy gate. No AI | Read the report, triage, fix, test, PR |
| **Pipeline with agents** | Pipeline owns the DAG. Agent tasks do bounded steps | Review the PR, approve, merge, deploy |
| **Fully agentic** | Coordinator decides next action. Not built | Set the rules, approve, handle exceptions |

## The Pipeline Steps (Tekton)

```
clone → build → SBOM → RHTPA scan → Conforma gate → agent task → PR
```

| Step | What It Does |
|------|-------------|
| clone | `git clone` the application source |
| build | `mvn package` — compile and package |
| SBOM | Generate CycloneDX Software Bill of Materials |
| RHTPA scan | Upload SBOM to Red Hat Trusted Profile Analyzer, get vulnerability findings |
| Conforma gate | Policy gate filters must-fix CVEs by severity/rules |
| Agent task | One of: select CVE, analyze CVEs, remediate, generate tests |
| PR | The agent opens a merge request. A person reviews and merges |

For advisory reading patterns, see `references/advisory-reading.md`.
For the Lightwell detail reference, see `references/lightwell-detail.md`.
