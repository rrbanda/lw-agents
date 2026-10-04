---
title: Concerns
summary: The seven decisions an organization faces when a CVE is published.
---

A published advisory does not tell the organization what to do. It tells the organization that a flaw exists. The decisions that follow are the real work. Each one belongs to someone, takes time, and can fail.

## The seven questions

### 1. Is this flaw in software we run?

A scanner compares the advisory against an inventory. If the inventory is incomplete, the answer is incomplete. The flaw may be in a transitive dependency the team did not know they had. The scanner's report is phase 09 intake. Without it, every later question is a guess.

### 2. How severe is it, and is anyone exploiting it?

Severity (CVSS) describes the flaw's characteristics. It does not say whether anyone is attacking it. EPSS estimates the probability of exploitation. The CISA Known Exploited Vulnerabilities catalog confirms it. A CVSS 9.8 with no known exploit and an unreachable code path is a different priority than a CVSS 7.5 that is actively exploited through a public-facing endpoint. Severity is not priority.

### 3. Can we take a fix without breaking the application?

An upstream upgrade may require a new API, a new runtime, or a recertification. A security-only backport on the same version avoids those changes. A platform patch covers the operating system but not the application library. A hardened base image covers the container foundation. The answer depends on the layer the vulnerability is in and the constraints the application carries.

### 4. How long will that take?

A typical manual path from advisory to production runs 30 to 90 days. Triage takes about five days. A developer sprint to change the dependency takes five to fourteen days. Cross-team tests and change approval take one to three days. Manual rollout and rollback take fourteen to ninety days. The advisory is public that entire time. Shortening that interval is the reason agents exist in this context.

### 5. Who approves the change?

A single dependency pin with passing tests is the shape of a standard change. A broader upgrade that changes behavior may need a change-advisory board. An active exploit may justify an emergency change. The agent does not decide the change type. It can produce the evidence that lets a person decide.

### 6. What if the details are still private?

An embargo means the vulnerability and the fix are shared with a closed set before public disclosure. During that window, a fix can exist in a private repository, but the pull request must not carry the vulnerability description into a public branch. The agent must respect the boundary between what is embargoed and what is public.

### 7. What if an attack is already underway?

Active exploitation is incident response, not routine remediation. The security operations center owns that response. Agents that are useful for routine patching must stay out of incident handling unless they are explicitly directed into it. Phase 10 of the lifecycle is where incidents, bypasses, and postmortems live.

## How these map to the lifecycle

Each concern sits across one or more of the [ten lifecycle phases](02-lifecycle.html). The lifecycle page shows who acts at each phase and where agents fit. The [solutions](03-solutions.html) page shows what kinds of response address each concern.

| Concern | Primary phases |
| --- | --- |
| Is this flaw in our software? | 07 (publish), 09 (scan and match) |
| How severe, and is it being exploited? | 05 (assess), 09 (prioritize) |
| Can we take a fix? | 06 (fix exists), 08 (repackage), 09 (apply) |
| How long will it take? | 08 through 09, the customer clock |
| Who approves? | 09 (change management) |
| What if it is embargoed? | 04 (coordinate), 06 (fix under embargo) |
| What if an attack is underway? | 10 (observe, respond, learn) |
