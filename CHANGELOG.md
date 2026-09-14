# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-09-14

### Added

- Five specialist agents: CVE Selection, CVE Analysis, Remediation, Test Generation, Fix Validation
- LLM coordinator with intent-based routing to specialists
- 7 ADK skills (cve-triage, cve-analysis, maven-remediation, junit-test-generation, scm-conventions, validation-architect, validation-pentester)
- CVE exploration tools (list, lookup, parse PURL, verify version on Maven Central)
- SCM tools (create issues, open PRs on GitLab/GitHub with deduplication)
- SafetyPlugin (LLM-as-judge content filtering)
- RedactionPlugin (3-layer secret masking)
- Pre-gate and post-gate policy validation
- Fail-closed CVE selection scoring
- Multi-persona adversarial fix validation with deterministic weighted scoring
- EvalHub integration for safety and security benchmarks (ADR-010)
- MLflow tracing via OpenTelemetry (ADR-011)
- Red Hat MaaS model serving support via rh-maas-litellm
- 64 unit tests, 38 eval cases across 6 datasets
- Tekton pipeline integration (thin HTTP caller pattern)
- Dockerfile for OpenShift deployment
- 11 Architecture Decision Records
