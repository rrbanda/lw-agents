---
title: Skill contract
summary: The conditions a future skill edit has to meet. No skill is rewritten by this pack.
---

Do not edit `skills/` or `app/agents/` in order to "catch up" in the same change as a wording tweak. A skill changes only after this pack covers the behavior, and the change names one phase and one use case.

## Header

The next revision of a skill adds this block beside the existing front matter. It is absent today, which is expected.

```yaml
domain:
  phase: 9
  phase_name: Prioritize and remediate
  use_case: cve-remediation
  authority: docs/domain/04-agent-map.md
```

`use_case` is `cve-remediation` for every skill in the [agent map](04-agent-map.html). A freshness skill would be a new skill with `use_case: dependency-freshness`, not a quiet widening of `cve-triage`.

The body of the skill starts from the in-domain and out-of-domain lists on the agent map. It does not start from the current procedure and then append a Lightwell paragraph.

## Fixtures the eval has to grow

These files are specifications. They are not wired into the runner yet.

| Fixture | File | Pass condition |
| --- | --- | --- |
| Lightwell pin absent from Central | [fixtures/rhlw-pin-not-on-central.json](fixtures/rhlw-pin-not-on-central.json) | Selection and analysis choose `3.14.0.rhlw-00001` for `LW-DEMO-0002` even though Central does not have it |
| Freshness is not a CVE fix | [fixtures/freshness-upgrade-refused.json](fixtures/freshness-upgrade-refused.json) | `3.14.0` to `3.18.0` is refused, or the output's use case is `dependency-freshness` and `selected` is false for CVE remediation |
| Wrong advisory | [fixtures/wrong-advisory-coordinate.json](fixtures/wrong-advisory-coordinate.json) | `spring-core` / `LW-DEMO-0001` / `5.3.18.rhlw-00003` is not the pin for the commons-lang3 case |

A green build on `3.18.0` fails the first two fixtures. The coordinate is the assertion, not the compiler.

Production cases use the same rules with a `RHLW-YYYY-NNNN` id and whatever coordinate that event names. The workshop GAVs are the regression cases, not a table for the agent to memorize in place of reading the event.

## Pull request text

A public pull request for this use case may contain:

- the advisory id
- the package coordinate
- the version the application has now
- the pinned version
- the words that name the source, such as "Lightwell OSV fixed event"
- the build system
- a statement that a person must review before merge

A public pull request must not contain:

- embargoed vulnerability detail, or a predisclosure write-up
- member-specific Premier request content
- a registry token, or a demo password
- an exploit procedure, a proof-of-concept payload, or steps to reproduce the vulnerability
- a statement that production is already remediated

The commit subject uses **pin**, not **bump**, when the version change is a Lightwell suffix.

## Validation and tests

Validation skills stay read-only. Their future text has room for three checks: the manifest coordinate matches the fixed event, the resolution repository is the trusted proxy, and the pull request does not claim more than it did.

Their future text has no room for an attack narrative, a payload, a bypass recipe, or a verdict on whether Lightwell's library patch is semantically sufficient. The current pentester skill contains that kind of instruction. The replacement deletes it. It does not soften it.

Test generation may assert the resolved coordinate and may run the application's existing tests. It may not add a test whose purpose is to exploit the CVE.

## Definition of done for a skill edit

1. The header names phase 9 and `cve-remediation`, and it points at the agent map section for that skill.
2. The procedure's version authority is a Lightwell fixed event, then resolution from the trusted repository.
3. Maven Central, OSV.dev, NVD, EPSS, and Red Hat VEX are labeled as the signals they actually are, matching [Lightwell](02-lightwell.html).
4. The two negative fixtures fail in the way the JSON describes, once they are wired. Until they are wired, the skill text still states those failures in prose.
5. The pull request template matches the text rules above.
6. The validation skill contains no exploit procedure.
7. The edit does not enable automerge, ServiceNow, Lens calls, or Trusted Profile Analyzer uploads.

Accurate means that list. It does not mean the skill knows next month's catalog.
