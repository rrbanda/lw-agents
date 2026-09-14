# Contributing to lw-agents

Thank you for your interest in contributing to lw-agents! This document covers
how to set up your development environment, run tests, and submit changes.

## Development setup

```bash
# Clone the repo
git clone https://github.com/rrbanda/lw-agents.git
cd lw-agents

# Install dependencies (requires uv)
uv sync

# Set up credentials
cp .env.example .env
# Edit .env with your GEMINI_API_KEY or MAAS_BASE_URL + MAAS_API_KEY

# Verify everything works
make test
make lint
```

## Running locally

```bash
# Start the agent server
make dev

# Or with MLflow tracing
make dev-traced

# ADK web playground
make playground

# Single agent call
make run PROMPT="Select the best CVE to remediate. Workspace: /tmp/test"
```

## Running tests

```bash
# Unit tests (no LLM needed)
make test

# Agent evaluations (needs LLM + make dev running)
make eval

# Lint + format
make lint
```

## Coding conventions

- **Python 3.11+** with type hints
- **Ruff** for linting and formatting (line length 100, rules: E, F, I, W)
- **ADK patterns** -- use ADK's built-in primitives (plugins, callbacks, skills, tools) instead of building custom infrastructure
- **Fail-closed** -- every error path should default to rejection, not acceptance
- **Skills-first** -- agent behavior lives in SKILL.md files, not hardcoded in Python

## Project structure

- `app/` -- all application code (agents, tools, plugins, policies, scoring, eval)
- `skills/` -- ADK skill definitions (SKILL.md + references/)
- `tests/` -- unit tests, eval datasets, behavioral tests
- `deployment/` -- Tekton tasks, Dockerfile, deployment overlays
- `docs/` -- architecture docs and ADRs

## Submitting changes

1. Fork the repo and create a feature branch from `main`
2. Make your changes
3. Run `make lint` and `make test` -- both must pass
4. If your change is architectural, add an ADR in `docs/adr/`
5. Open a pull request with a clear description of what changed and why

## Architecture Decision Records

For significant architectural changes, we use lightweight ADRs (Architecture
Decision Records) in `docs/adr/`. See existing ADRs for the format. Number
sequentially (e.g., `012-your-decision.md`).

## Adding a new agent skill

1. Create a directory under `skills/` (e.g., `skills/my-skill/`)
2. Add a `SKILL.md` with YAML frontmatter and methodology instructions
3. Optionally add `references/` with supporting material
4. Register the skill in the relevant agent factory function

See [Google ADK Skills Guide](https://developers.googleblog.com/developers-guide-to-building-adk-agents-with-skills/) for the skill specification.

## Adding a new tool

1. Add the tool function to `app/tools/` (or create a new module)
2. Tools are plain Python functions that ADK wraps as `FunctionTool`
3. Add the tool to the relevant agent's `tools=[]` list
4. Add unit tests in `tests/`

## Questions?

Open an issue or start a discussion on the repository.
