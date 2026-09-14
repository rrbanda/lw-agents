# ADR-010: EvalHub Integration for Safety and Quality Gates

## Status

Accepted

## Context

lw-agents produces AI-driven code changes for CVE remediation. Before these
changes are deployed, we need confidence that:

1. The underlying LLM passes safety and fairness benchmarks (truthfulness,
   toxicity, bias, ethics).
2. The model is resistant to prompt injection, jailbreaking, and other
   adversarial attacks (OWASP LLM Top 10).
3. CVE-specific evaluation metrics (selection accuracy, remediation success
   rate, fix safety) are tracked over time.

RHOAI 3.5 ships **EvalHub** — a GA evaluation orchestration service already
deployed on our cluster — with providers for `lm_evaluation_harness` (standard
LLM benchmarks), `garak` (red-teaming), and `GuideLLM` (performance). Results
are automatically logged to the co-deployed MLflow instance.

## Decision

Integrate EvalHub as a **pre-agent quality gate** in the Tekton pipeline:

1. **Tekton Task** (`evalhub-eval-gate`): Runs before `call-ssc-agent`.
   Submits evaluation configs, waits for completion, fails the pipeline if
   thresholds are not met.
2. **Safety Baseline** (`evalhub-safety-baseline.yaml`): truthfulqa_mc1,
   toxigen, ethics_cm, bbq benchmarks via lm_evaluation_harness.
3. **Security Scan** (`evalhub-garak-security.yaml`): OWASP LLM Top 10, CWE,
   and quality probes via Garak.
4. **Custom CVE Metrics** (`app/eval/cve_metrics.py`): Selection accuracy,
   remediation success rate, fix safety score, PR hygiene — logged to MLflow.
5. **Pipeline** (`eval-gate-pipeline.yaml`): Chains eval-gate → call-agent.

## Consequences

### Positive
- No code changes ship without passing safety/fairness/security benchmarks.
- Garak red-teaming catches prompt injection and jailbreak vulnerabilities
  before production.
- CVE eval metrics are tracked in MLflow alongside standard LLM benchmarks,
  enabling regression detection.
- Uses existing RHOAI 3.5 infrastructure (EvalHub + MLflow) — zero new
  infrastructure to deploy.

### Negative
- Eval gate adds ~5-15 min to pipeline execution for benchmark computation.
- Threshold values need tuning based on baseline results.
- Custom CVE provider is not yet a first-class EvalHub provider (uses API
  directly rather than the provider plugin system).

### Risks
- EvalHub is GA but the Garak provider may have fewer benchmarks available
  than standalone Garak.
- Model endpoint must be accessible from the EvalHub evaluation pods on the
  cluster network.

## Alternatives Considered

1. **Standalone lm-eval + garak** — More flexible but requires managing
   infrastructure, result storage, and threshold logic ourselves.
2. **No eval gate** — Ship faster but with no safety guarantees on model
   behavior.
3. **Post-deploy only** — Catch issues after deployment; unacceptable for
   security-critical CVE remediation.
