.PHONY: install install-tracing dev dev-traced playground test lint eval eval-generate eval-grade run \
       evalhub-safety evalhub-security evalhub-status evalhub-cve-eval evalhub-full \
       agent-eval agent-eval-baseline agent-eval-ci deploy-eval-tasks \
       build build-sandbox push deploy undeploy dry-run

CONTAINER_CLI := $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)

install:
	uv sync

install-eval:
	uv sync --extra eval

install-tracing:
	uv sync --extra tracing

dev:
	uv run adk api_server app

dev-traced:  ## Start ADK dev server with MLflow tracing (requires MLFLOW_TRACKING_URI)
	MLFLOW_TRACKING_URI=$${MLFLOW_TRACKING_URI:-https://mlflow-redhat-ods-applications.apps.ocp.qn6c5.sandbox1388.opentlc.com} \
	MLFLOW_WORKSPACE=$${MLFLOW_WORKSPACE:-autorag} \
	MLFLOW_TRACKING_INSECURE_TLS=$${MLFLOW_TRACKING_INSECURE_TLS:-true} \
	uv run adk api_server app

playground:
	uv run adk web

test:
	uv run pytest tests/ -xvs

lint:
	uv run ruff check --fix app/ tests/
	uv run ruff format app/ tests/

eval:
	uv run agents-cli eval run

eval-generate:
	uv run agents-cli eval generate

eval-grade:
	uv run agents-cli eval grade

run:
	uv run agents-cli run "$(PROMPT)"

# --- EvalHub targets (RHOAI 3.5) ---

evalhub-safety:  ## Run safety-and-fairness-v1 benchmarks
	uv run evalhub eval run --config tests/eval/evalhub-safety-baseline.yaml

evalhub-safety-wait:  ## Run safety benchmarks and wait for completion
	uv run evalhub eval run --config tests/eval/evalhub-safety-baseline.yaml --wait --timeout 1800

evalhub-security:  ## Run Garak security red-teaming scan
	uv run evalhub eval run --config tests/eval/evalhub-garak-security.yaml

evalhub-security-wait:  ## Run Garak scan and wait for completion
	uv run evalhub eval run --config tests/eval/evalhub-garak-security.yaml --wait --timeout 1800

evalhub-status:  ## Check status of all EvalHub jobs
	uv run evalhub eval status

evalhub-cve-eval:  ## Run CVE-specific evaluation metrics
	uv run python -m app.eval.runner

evalhub-full:  ## Run full evaluation suite (safety + security + CVE)
	@echo "=== Safety Gate ===" && $(MAKE) evalhub-safety-wait
	@echo "=== Security Scan ===" && $(MAKE) evalhub-security-wait
	@echo "=== CVE Eval ===" && $(MAKE) evalhub-cve-eval

# --- Agent-level eval targets (automated, regression-gated) ---

AGENT_ENDPOINT ?= http://ssc-agent.tssc-agents.svc:8080

agent-eval:  ## Run agent evals against live service (38 cases, 6 agents)
	uv run python -m app.eval.agent_eval --agent-endpoint $(AGENT_ENDPOINT)

agent-eval-baseline:  ## Run agent evals and save results as new baseline
	uv run python -m app.eval.agent_eval --agent-endpoint $(AGENT_ENDPOINT) --update-baseline

agent-eval-ci:  ## CI mode: run agent evals, fail on regression, log to MLflow
	uv run python -m app.eval.agent_eval \
		--agent-endpoint $(AGENT_ENDPOINT) \
		--output /tmp/agent-eval-report.json \
		--fail-on-regression

agent-eval-set:  ## Run a specific eval set: make agent-eval-set SET=cve-selection
	uv run python -m app.eval.agent_eval --agent-endpoint $(AGENT_ENDPOINT) --set $(SET)

# --- Deploy all eval infrastructure to the cluster ---

deploy-eval-tasks:  ## Apply Tekton tasks, pipeline, triggers, and CronJob
	oc apply -f deployment/tekton/eval-gate-task.yaml
	oc apply -f deployment/tekton/agent-eval-task.yaml
	oc apply -f deployment/tekton/eval-gate-pipeline.yaml
	oc apply -f deployment/tekton/scheduled-eval-trigger.yaml
	@echo "Eval infrastructure deployed. Evals will run automatically."

# --- Full CI gate (everything) ---

ci-gate:  ## Full CI quality gate: model evals + agent evals (what Tekton runs)
	@echo "=== Gate 1: Model Safety ===" && $(MAKE) evalhub-safety-wait
	@echo "=== Gate 2: Model Security ===" && $(MAKE) evalhub-security-wait
	@echo "=== Gate 3: Agent Evals ===" && $(MAKE) agent-eval-ci
	@echo "ALL GATES PASSED"

# --- Container image build targets ---

build:  ## Build the lw-agents service image
	@[ -n "$(CONTAINER_CLI)" ] || { echo "ERROR: neither podman nor docker found"; exit 1; }
	@source .env 2>/dev/null; \
	[ -n "$${CONTAINER_IMAGE}" ] || { echo "ERROR: CONTAINER_IMAGE not set in .env"; exit 1; }; \
	$(CONTAINER_CLI) build --platform linux/amd64 -t "$${CONTAINER_IMAGE}" -f Dockerfile .

build-sandbox:  ## Build the OpenCode sandbox image
	@[ -n "$(CONTAINER_CLI)" ] || { echo "ERROR: neither podman nor docker found"; exit 1; }
	@source .env 2>/dev/null; \
	[ -n "$${SANDBOX_IMAGE}" ] || { echo "ERROR: SANDBOX_IMAGE not set in .env"; exit 1; }; \
	$(CONTAINER_CLI) build --platform linux/amd64 -t "$${SANDBOX_IMAGE}" -f Containerfile.openshell .

push:  ## Push both images to registry
	@[ -n "$(CONTAINER_CLI)" ] || { echo "ERROR: neither podman nor docker found"; exit 1; }
	@source .env 2>/dev/null; \
	[ -n "$${CONTAINER_IMAGE}" ] || { echo "ERROR: CONTAINER_IMAGE not set in .env"; exit 1; }; \
	[ -n "$${SANDBOX_IMAGE}" ] || { echo "ERROR: SANDBOX_IMAGE not set in .env"; exit 1; }; \
	$(CONTAINER_CLI) push "$${CONTAINER_IMAGE}" && \
	$(CONTAINER_CLI) push "$${SANDBOX_IMAGE}"

# --- Kustomize deployment targets ---

KUSTOMIZE_OVERLAY ?= production

deploy:  ## Deploy to OpenShift via Kustomize (KUSTOMIZE_OVERLAY=dev|production)
	oc apply -k deployment/kustomize/overlays/$(KUSTOMIZE_OVERLAY)
	@echo "Waiting for rollout..." && \
	oc rollout status deployment/lw-agents --timeout=120s && \
	ROUTE=$$(oc get route lw-agents -o jsonpath='{.spec.host}' 2>/dev/null || true); \
	if [ -n "$$ROUTE" ]; then echo "Agent available at: https://$$ROUTE"; fi

undeploy:  ## Remove deployment from OpenShift
	oc delete -k deployment/kustomize/overlays/$(KUSTOMIZE_OVERLAY)

dry-run:  ## Preview Kustomize manifests without deploying
	oc kustomize deployment/kustomize/overlays/$(KUSTOMIZE_OVERLAY)
