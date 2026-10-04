---
title: Agent map
summary: Which module owns which phase, what it may do, and where the current skill text disagrees.
---

The pipeline a person sees today is: a scan produces `must-fix-cves.json`, then selection, analysis, remediation, tests, and validation, then a person merges. That sequence is phase 09. It starts after a fix exists. It is not the Lightwell backport factory, and the scan is not discovery.

`opencode_writer` writes files when a step asks it to. It has no phase of its own.

Machine-readable copy: [placement.yaml](placement.yaml).

## cve-triage

| | |
| --- | --- |
| Module | `app/agents/cve_selection.py` |
| Skill | `skills/cve-triage` |
| Phase | 09, prioritize. Choose one advisory from the must-fix set |
| Use case | CVE remediation |

:::in
Prefer the advisory whose Lightwell fixed event names a coordinate on the same upstream version the application already uses. Report that coordinate as `fixed_version`. If none of the must-fix advisories have such an event, report `selected=false`.
:::

:::out
Do not discover a vulnerability. Do not treat a Maven Central version, an OSV.dev fixed version, or a newer minor as the Lightwell fix. Do not select an advisory that is not in the must-fix set.
:::

:::now
The skill verifies candidates with `check_version_exists`, which looks at Maven Central, and `lookup_osv`, which reads OSV.dev. It prefers a verified fix, then EPSS above 0.5, then CVSS, then the same major.minor, and it prefers a patch bump over a minor bump. A `.rhlw` coordinate fails the Central check, so the rule "never select without a verified fixed version" rejects the pin this pack requires. A timeout on that check must not be repaired by substituting Central.
:::

## cve-analysis

| | |
| --- | --- |
| Module | `app/agents/cve_analysis.py` |
| Skill | `skills/cve-analysis` |
| Phase | 09, the rest of the must-fix set. File an issue for each advisory that has a Lightwell fixed coordinate |
| Use case | CVE remediation |

:::in
Every advisory in the set is classified. Fixable means a Lightwell fixed event names a coordinate for the package the application uses. The issue names the advisory id, the coordinate, and the feed that event came from.
:::

:::out
Do not recommend the lowest upstream version on the same release line as if it were the Lightwell pin. Do not mark an advisory fixable because OSV.dev or NVD names an upstream release.
:::

:::now
The skill's recommended version is the lowest version that `check_version_exists` confirms on the same release line. `lookup_vex` is Red Hat product VEX, not Lightwell OSV. The example in the skill is `4.1.100.Final` to `4.1.108.Final`, which is an upstream bump.
:::

## maven-remediation and gradle-remediation

| | |
| --- | --- |
| Module | `app/agents/remediation.py` |
| Skills | `skills/maven-remediation`, `skills/gradle-remediation` |
| Phase | 09, remediate. Change the manifest and open the pull request |
| Use case | CVE remediation |

:::in
Edit only the version that selects the coordinate from the fixed event. Gradle may store it in a version catalog, an extra property, a direct declaration, or a constraint. Maven may store it in a property, a BOM override, a direct dependency, or `dependencyManagement`. The build must resolve that coordinate from the trusted repository. Then open the pull request.
:::

:::out
Do not patch library source into the application repository. Do not add a dependency. Do not investigate an upstream commit in order to re-implement the backport. That investigation is phase 06, and Lightwell has already done it when the fixed event exists. Do not put the registry token in the diff. Do not automerge.
:::

:::now
Both skills tell the agent to inspect the upstream fix before editing. Maven classifies the upstream commit as a version bump, a source patch, or a configuration change, and it will describe a source patch rather than apply it to application code. The written constraint is already "edit only the dependency version" and "do not modify application source." The domain miss is the authority for the version: the skills still obtain it from GitHub Advisory, OSV.dev, and NVD, and the commit message is a bump. `scm-conventions` still allows the pull request to claim `source_patch` or `config_change`.
:::

## junit-test-generation

| | |
| --- | --- |
| Module | `app/agents/test_generation.py` |
| Skill | `skills/junit-test-generation` |
| Phase | 09, the test evidence that lets a person treat the pin as a standard change |
| Use case | CVE remediation |

:::in
Show that the application still builds and that the resolved coordinate is the coordinate the fixed event named. Existing application tests are the regression suite. A dependency-tree or property assertion is in domain.
:::

:::out
Do not add a test that proves the CVE by exploiting it. Do not import an upstream proof-of-concept into the application repository. Library regression tests belong in Lightwell's build, phase 06.
:::

:::now
The skill's role line is to prove the vulnerability fix works. Its first tier adapts upstream reproducer tests, and its second tier writes tests from the vulnerability pattern. That is the behavior the contract withdraws for a Lightwell pin.
:::

## validation-architect and validation-pentester

| | |
| --- | --- |
| Module | `app/agents/validation.py` |
| Skills | `skills/validation-architect`, `skills/validation-pentester` |
| Phase | 09, check the pull request before a person merges it |
| Use case | CVE remediation |

:::in
Read-only. The diff changes the manifest to the fixed-event coordinate and does not change application logic. The build resolved that coordinate from the trusted repository. The advisory text in the pull request matches the event. A failure is a wrong coordinate, a resolution from Central, a drive-by edit, or a claim that production is already remediated.
:::

:::out
Do not write or request an exploit. Do not re-judge the Lightwell library patch. Do not score a regex, a parser, or an upstream commit as if this repository had authored the fix.
:::

:::now
The architect skill reviews root cause in source, including ReDoS patterns, using NVD and OSV. The pentester skill's role line is to find a bypass and prove the fix does not work, and it reconstructs the attack from the finding. Both are outside the pin check. The future skills do not keep that procedure.
:::

## scm-conventions

| | |
| --- | --- |
| Skill | `skills/scm-conventions` |
| Phase | 09, the words on the issue and the pull request |
| Use case | CVE remediation |

:::in
Branch names may stay on the current `rhtpa/remediate-{cve}-{timestamp}` pattern until a later edit. The commit subject for a pin is `fix({advisory}): pin {package} to {version}`. The body names the advisory id, the package, the current version, the pinned version, and the fixed-event source. It says the build system. It does not say the application is remediated in production.
:::

:::out
Do not put embargoed or predisclosure vulnerability detail in a public pull request. Do not claim `source_patch` for a manifest pin. Do not use the word bump for a Lightwell suffix.
:::

:::now
The template says `bump {package} to {fixed_version}`, sets "upstream fix analyzed" to yes or no, and allows `version_bump`, `source_patch`, or `config_change`.
:::

## External systems the code calls today

| System in `docs/architecture.md` | Domain reading |
| --- | --- |
| RHTPA / Trustify vulnerability reports | Phase 09 input. The must-fix list. Not Lens, and not the Lightwell feed |
| GitHub or GitLab | The pull request and the issue |
| The model | The harness. Not a source of versions |
| OpenCode | A way to write files. Not a domain actor |
| Maven Central | Evidence about upstream releases only. Not the store that must contain the pin |

The domain picture adds two systems the diagram does not name: the Lightwell OSV feed, and the internal repository that proxies Lightwell. A skill edit that still has Central as the only version authority is not aligned, even if the prose mentions Lightwell.
