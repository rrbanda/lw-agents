# ADR-003: OpenCode as Coding Agent

## Status
Accepted

## Context
The original ssc-demo used Claude Code (proprietary) and aider (open-source) for
file editing tasks. We need an open-source coding agent that works with any LLM
provider and can run in headless mode for CI/automation.

Options considered:
- **OpenCode** — MIT-licensed, 195K+ GitHub stars, headless `opencode run` mode,
  75+ LLM providers, built-in agent/permission system
- **aider** — open-source, litellm-backed, mature but less featured
- **SWE-agent** — research-grade, strong on SWE-bench, focused on issue resolution
- **OpenHands** — full-featured, Docker-based sandbox

## Decision
Use **OpenCode** as the primary coding agent, invoked via ADK's
`ExecuteBashTool`. The agent calls `bash("opencode run '...'")` to delegate file
editing to OpenCode.

## Rationale
- Headless `opencode run "prompt"` mode is designed for scripts and CI
- Works with any model via Models.dev (75+ providers including local models)
- ADK's ExecuteBashTool provides the security boundary (BashToolPolicy with
  allowed_command_prefixes, timeout, memory limits, process isolation)
- OpenCode handles the "how" of file editing while the ADK agent handles the
  "what" and "verify" — clean separation of orchestration and execution
- The `ExecuteBashTool` approach means OpenCode is just one of the allowed
  commands — Maven, git, and file inspection commands are also available
  through the same tool

## Consequences
- OpenCode must be installed in the container image
- The `BashToolPolicy.allowed_command_prefixes` must include "opencode "
- Model configuration for OpenCode is separate from the ADK agent model
  (CODING_MODEL env var)
- No custom subprocess wrapper code needed — ADK handles it
