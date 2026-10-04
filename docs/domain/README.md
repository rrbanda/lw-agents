---
title: Domain knowledge
summary: What the CVE lifecycle, Lightwell, and this repository each do, before any skill is rewritten.
---

Read this pack before changing an agent or a skill. It is the domain authority for `lw-agents`. The files under `skills/` are the current implementation. Where they disagree with this pack, this pack wins, and the skill is waiting to be corrected.

:::cards
Boundaries | Three systems, and the names that keep getting collapsed. | 00-boundaries.html
CVE lifecycle | Ten phases, the formal record, and the only phase these agents occupy. | 01-cve-lifecycle.html
Lightwell | Repositories, version suffixes, OSV, Lens, and Trusted Profile Analyzer. | 02-lightwell.html
Customer clock | The patch-to-production model after a library fix already exists. | 03-customer-clock.html
Agent map | Each skill's phase, use case, and the mismatch in the current text. | 04-agent-map.html
Skill contract | The rules the next skill edit has to satisfy. | 05-skill-contract.html
:::

## What this repository does

`lw-agents` is a phase 09 application. It takes a published advisory that already has a fixed coordinate, and it opens a pull request that pins that coordinate in one application. A person merges it.

The use case is **CVE remediation**: one advisory, one dependency, the smallest change that lands the fixed coordinate. A newer upstream line, chosen because it is newer, is a different use case called **dependency freshness**. These skills do not do freshness.

## What accurate means

A later skill is accurate when it matches this pack and the sources in [Sources](sources.html). It is not accurate because a model remembers the catalog. Catalog membership changes. The skill reads the fixed event for the case in front of it.

Two future fixtures are already specified in [the skill contract](05-skill-contract.html):

- A `.rhlw` pin that is not on Maven Central, which must still be selected.
- A freshness upgrade, which the CVE skill must refuse or relabel.

## How to read the code after this

| Read this | For |
| --- | --- |
| [Agent map](04-agent-map.html) | Which module and skill own which job |
| [placement.yaml](placement.yaml) | The same map in a form a later edit can load |
| `skills/*/SKILL.md` | What the agent does today |
| `docs/architecture.md` | How the ADK service is wired today |
| `docs/adr/` | Why the harness is skills-first |

Do not copy a skill back into this pack. This pack does not absorb the current mismatch.

## Preview

From the repository root:

```
python3 docs/domain/build_site.py
python3 -m http.server -d docs/domain/site
```

GitHub Pages publishes that build. The existing slide deck stays at `slides/`.
