# ADR-002: Agents-and-Skills-First Architecture

## Status
Accepted

## Context
The original ssc-demo used "LLM reasoning calls" — dump 260K characters of JSON
into a single prompt and parse the response. This is not agentic. There were no
skills, no iterative tool use, no decision loops, no memory.

The question: should agents be skill-driven (skills define behavior, agents load
them on demand) or prompt-driven (behavior hardcoded in agent instructions)?

## Decision
**Skills-first architecture.** Skills define HOW the agent thinks — its
methodology, constraints, and decision framework. Agents load skills on demand
via ADK's `SkillToolset` during their reasoning loop. Tools are shaped by the
skills' process steps.

Skills are stored as `SKILL.md` files with YAML frontmatter in a `skills/`
directory. The agent discovers skills via `list_skills` (L1 metadata), loads full
instructions via `load_skill` (L2), and reads reference docs via
`load_skill_resource` (L3 resources).

## Rationale
- Skills are independently updatable — change a skill file, agent picks it up
  without redeployment
- Progressive disclosure keeps the context window lean — skills load only when
  the agent decides it needs them
- Skills are testable — eval cases can verify the agent follows the skill's
  process steps
- The pattern matches ADK's native SkillToolset API (load_skill_from_dir,
  SkillToolset, list_skills/load_skill/load_skill_resource)
- Reference docs in `references/` subdirectories provide additional context
  without bloating the main instruction

## Consequences
- Agent instructions must tell the agent to load skills ("first call load_skill
  to read the cve-triage skill")
- Skills must be written as clear process steps that reference available tools
- The skills/ directory must be included in the container image
- Skill validation (frontmatter, name matching) is enforced by ADK at load time
