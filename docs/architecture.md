# Architecture

## Technology Stack

| Layer | What provides it | Role |
|---|---|---|
| **Agent harness** | [Google ADK 2.0](https://adk.dev/) | Core loop, tool dispatch, state, context management, plugins, MCP, skills |
| **Agent platform** | [Red Hat OpenShift AI](https://www.redhat.com/en/technologies/cloud-computing/openshift/openshift-ai) | EvalHub, MLflow, Tekton pipelines, OpenShift deployment |
| **Model serving** | Gemini API / [Red Hat MaaS](https://github.com/rrbanda/rh-maas-litellm) / vLLM | LLM inference |
| **Agent application** | This repo (lw-agents) | CVE tools, remediation skills, policy gates, scoring, multi-persona validation |

## 1. System Context

How the ADK agent service fits in the broader software supply chain.

```mermaid
flowchart TB
    subgraph tektonPipeline [Tekton CI/CD Pipeline]
        clone[clone-repository]
        build[package / build-container]
        sbom[upload-sbom / rhtpa-scan]
        policy[conforma-policy-check]
        callAgent["call-ssc-agent\n(thin HTTP caller)"]
        openPR[open-pr]
    end

    subgraph adkAgent [ADK Agent Service]
        coordinator["Root Coordinator"]
        specialists["Specialist Agents\n(selection / analysis /\nremediation / test-gen /\nvalidation)"]
    end

    subgraph evalLayer [EvalHub Layer - RHOAI 3.5]
        evalGate["evalhub-eval-gate\n(Tekton Task)"]
        evalHub["EvalHub API\n(safety + security)"]
        mlflow["MLflow\n(experiment tracking)"]
    end

    subgraph external [External Systems]
        rhtpa["RHTPA / Trustify\n(vuln reports)"]
        scm["GitLab / GitHub\n(issues + PRs)"]
        llm["LLM Provider\n(Gemini / Anthropic /\nOpenAI-compat)"]
        opencode["OpenCode\n(coding agent)"]
        maven["Maven Central\n(version verification)"]
    end

    clone --> build --> sbom --> policy
    policy --> evalGate
    evalGate -->|"submit + wait"| evalHub
    evalHub -->|"log results"| mlflow
    evalGate -->|"PASS"| callAgent
    callAgent -->|"HTTP POST"| coordinator
    coordinator --> specialists
    specialists --> llm
    specialists -->|"execute_bash\n(build_bash_tool)"| opencode
    specialists -->|"execute_bash\n(build_bash_tool)"| maven
    specialists -->|"FunctionTool"| scm
    specialists -->|"FunctionTool"| rhtpa
    callAgent --> openPR
```

## 2. Agent Hierarchy

The coordinator-to-specialist delegation tree with tools and skills.

```mermaid
flowchart TB
    subgraph root [Root Coordinator]
        coord["ssc_coordinator\n(LlmAgent)\ndelegates by task type"]
    end

    subgraph selectAgent [CVE Selection Agent]
        sel["cve_selection\n(LlmAgent)\nafter: fail_closed_selection_callback"]
        selSkills["SkillToolset\ncve-triage\nscm-conventions"]
        selTools["FunctionTools\nlist_must_fix_cves\nlookup_cve_detail\nparse_maven_purl\ncheck_version_exists"]
    end

    subgraph analysisAgent [CVE Analysis Agent]
        ana["cve_analysis\n(LlmAgent)"]
        anaSkills["SkillToolset\ncve-analysis\nscm-conventions"]
        anaTools["FunctionTools\nlist_must_fix_cves\nlookup_cve_detail\nparse_maven_purl\ncheck_version_exists"]
    end

    subgraph remAgent [Remediation Agent]
        rem["remediation\n(SequentialAgent)"]
        remInitPlan["initial_remediation_planner\n(LlmAgent)\npre/post_gate_callback"]
        subgraph remRetryLoop [LoopAgent: remediation_retry_loop, max=3]
            remChecker["build_result_checker\n(BaseAgent)\nemits CHANGED=1 via Event.state_delta\nclassifies: PATCH | ENV | PRE_EXISTING | NETWORK"]
            remRetryPlan["remediation_retry_planner\n(LlmAgent)\npre/post_gate_callback"]
        end
        remPR["remediation_pr_opener\n(LlmAgent)"]
        remSkills["SkillToolset\nmaven-remediation\nscm-conventions"]
        remBash["execute_bash\n(build_bash_tool)"]
        remClone["clone_repository_tool"]
        remPRTool["create_pull_request_tool"]
    end

    subgraph testAgent [Test Generation Agent]
        tst["test_generation\n(SequentialAgent)"]
        tstInvestigator["test_investigator\n(LlmAgent)\noutput_key: test_spec"]
        tstWriter["test_writer\n(LlmAgent)\ntee or OpenCode"]
        subgraph tstRetryLoop [LoopAgent: test_retry_loop, max=2]
            tstChecker["test_result_checker\n(TestResultChecker / BaseAgent)\nfinds *Test.java + mvn compile\nemits TESTS_ADDED=1"]
            tstFixer["test_fixer or opencode_fixer\n(LlmAgent)"]
        end
        tstCommitter["test_committer\n(LlmAgent)"]
        tstSkills["SkillToolset\njunit-test-generation\nscm-conventions"]
        tstBash["execute_bash\n(build_bash_tool)"]
        tstClone["clone_repository_tool"]
    end

    subgraph valAgent [Fix Validation Agent]
        val["fix_validation\n(SequentialAgent)"]
        valArch["security_architect\n(LlmAgent)"]
        valPen["penetration_tester\n(LlmAgent)"]
        valScore["deterministic_scoring\n(BaseAgent)"]
        valArchSkill["SkillToolset\nvalidation-architect"]
        valPenSkill["SkillToolset\nvalidation-pentester"]
        valTools["FunctionTools\nlookup_cve_detail\nparse_maven_purl"]
    end

    subgraph plugins [Runner Plugins]
        safePlug["SafetyPlugin\n(LLM-as-judge)"]
        redactPlug["RedactionPlugin\n(secret masking)"]
    end

    coord -->|"delegates"| sel & ana & rem & tst & val
    sel --- selSkills & selTools
    ana --- anaSkills & anaTools
    rem --- remInitPlan --> remRetryLoop --> remPR
    remInitPlan --- remSkills & remBash & remClone
    remChecker --> remRetryPlan
    remPR --- remPRTool
    tst --- tstInvestigator --> tstWriter --> tstRetryLoop --> tstCommitter
    tstInvestigator --- tstSkills & tstBash & tstClone
    val --- valArch --> valPen --> valScore
    valArch --- valArchSkill & valTools
    valPen --- valPenSkill
    plugins -.->|"wraps all"| coord
```

## 3. CVE Selection Agent Flow

How the CVE selection agent loads a skill, explores CVEs via tools, and decides.

```mermaid
sequenceDiagram
    participant User
    participant Coord as Coordinator
    participant Sel as CVE Selection Agent
    participant ST as SkillToolset
    participant T as CVE Tools
    participant MC as Maven Central

    User->>Coord: Select best CVE. Workspace: /ws
    Coord->>Sel: Delegates to cve_selection

    Sel->>ST: list_skills()
    ST-->>Sel: [cve-triage, scm-conventions]

    Sel->>ST: load_skill("cve-triage")
    ST-->>Sel: Full triage methodology

    Sel->>T: list_must_fix_cves("/ws")
    T-->>Sel: [{cve_id: CVE-2024-1234, severity: critical, ...}, ...]

    loop For each CVE in must-fix set
        Sel->>T: lookup_cve_detail("CVE-2024-1234", "/ws")
        T-->>Sel: {title, description, severity, affected_purls, hints}

        Sel->>T: parse_maven_purl("pkg:maven/com.example/lib@1.2.3")
        T-->>Sel: {group_id, artifact_id, version, package}

        Sel->>MC: check_version_exists("com.example", "lib", "1.2.4")
        MC-->>Sel: {exists: true, version: "1.2.4"}
    end

    Sel->>Sel: Score and rank candidates
    Sel-->>Coord: selection_result (selected, cve_id, package, versions, justification)
    Coord-->>User: Decision summary
```

## 4. Remediation Pipeline (SequentialAgent + LoopAgent)

The SequentialAgent pipeline with inner LoopAgent for build-retry logic.

```mermaid
flowchart LR
    START((START)) --> initPlan["initial_remediation_planner\n(LlmAgent)\nload skill + bash + clone\npre/post_gate_callback"]

    initPlan --> retryLoop

    subgraph retryLoop [LoopAgent: remediation_retry_loop, max=3]
        checker["build_result_checker\n(BaseAgent)\nescalate on success"]
        retryPlan["remediation_retry_planner\n(LlmAgent)\npre/post_gate_callback"]
        checker --> retryPlan
        retryPlan -.->|"next iteration"| checker
    end

    retryLoop --> prOpener["remediation_pr_opener\n(LlmAgent)\ncreate_pull_request"]
```

## 5. Test Generation Pipeline

SequentialAgent with inner LoopAgent for iterative test refinement.

```mermaid
flowchart LR
    subgraph seq [SequentialAgent: test_generation]
        writer["initial_test_writer\n(LlmAgent)\nload skill\nopencode run\ngenerate tests"]

        subgraph loop [LoopAgent: test_refinement_loop, max=3]
            evaluator["test_evaluator\n(LlmAgent)\nmvn test\nGRADE: pass/fail"]
            checker["TestEscalationChecker\n(BaseAgent)\nif pass -> escalate"]
            fixer["test_fixer\n(LlmAgent)\nfix failing tests"]
            evaluator --> checker --> fixer
            fixer -.->|"next iteration"| evaluator
        end

        prOpener["test_pr_opener\n(LlmAgent)\ncreate_pull_request"]
    end

    writer --> loop --> prOpener
```

## 6. Fix Validation Pipeline

Multi-persona adversarial review with deterministic consensus scoring.

```mermaid
flowchart LR
    subgraph seq [SequentialAgent: fix_validation]
        architect["security_architect\n(LlmAgent)\nload skill\nevaluate 4 gates"]
        pentester["penetration_tester\n(LlmAgent)\nload skill\nfind bypasses"]
        scoring["deterministic_scoring\n(BaseAgent)\nweighted consensus\nno LLM"]
    end

    architect --> pentester --> scoring

    scoring -->|"score >= 0.80"| fixed[FIXED]
    scoring -->|"score >= 0.50"| partial[PARTIALLY_FIXED]
    scoring -->|"score < 0.50"| notFixed[NOT_FIXED]
```

Gate weights: root_cause (0.43), instance_coverage (0.2467), no_new_vulnerabilities (0.1867), security_best_practices (0.1366). Skill instructions use rounded approximations (0.25/0.19/0.13) for LLM readability. Conservative consensus: unanimous agreement = HIGH confidence; disagreement = most-conservative-wins with FLAGGED confidence. Critical gate cap: root_cause not PASS caps decision down one level.

## 7. Policy Gates

Pre-gate and post-gate validation sandwich around the remediation agent.

```mermaid
flowchart LR
    request["Remediation\nRequest"] --> preGate{"pre_gate\nvalidate CVE ID\nMaven coords\nversions"}
    preGate -->|"invalid"| denied["Guidance-only\nresponse\nzero model cost"]
    preGate -->|"valid"| agent["Remediation\nAgent"]
    agent --> postGate{"post_gate\nvalidate diff\nforbidden patterns\nfile count"}
    postGate -->|"rejected"| blocked["Diff rejected\nnosec / suppress /\nverify=False"]
    postGate -->|"passed"| pr["Open PR"]
```

Post-gate enforcement levels: forbidden patterns (nosec, SuppressWarnings, verify=False, etc.) and file count exceeding `MAX_FILES_TOUCHED=5` are **hard rejections** that block the PR. Diff size exceeding `MAX_DIFF_LINES=100` produces a **warning only** (logged but does not reject) — large diffs are flagged for careful review rather than outright blocked.

## 8. Data Flow

How data moves from RHTPA workspace files through agent tools to SCM.

```mermaid
flowchart LR
    subgraph workspace [Pipeline Workspace]
        mustFix["rhtpa/must-fix-cves.json\n(Conforma output)"]
        vulnReport["rhtpa/vulnerabilities.json\n(RHTPA analysis)"]
        pomXml["source/pom.xml\n(Maven project)"]
    end

    subgraph tools [Agent Tools]
        listTool["list_must_fix_cves\nreads must-fix JSON"]
        lookupTool["lookup_cve_detail\nreads vuln report per-CVE"]
        parseTool["parse_maven_purl\nextracts coordinates"]
        checkTool["check_version_exists\nverifies via Maven Central"]
        bashTool["execute_bash\n(build_bash_tool)\nopencode run / mvn"]
        diffTool["diff_proof\nsnapshot + verify"]
    end

    subgraph agent [Agent Reasoning]
        reason["LLM Agent\nloads skill\ncalls tools\nreasons per-CVE"]
    end

    subgraph gates [Policy Gates]
        preGate["pre_gate\nvalidate input"]
        postGate["post_gate\nvalidate diff"]
    end

    subgraph outputs [Outputs]
        issues["GitLab/GitHub Issues\n(one per fixable CVE)"]
        prs["Pull Requests\n(remediation or tests)"]
    end

    mustFix --> listTool --> reason
    vulnReport --> lookupTool --> reason
    reason --> parseTool
    reason --> checkTool
    preGate --> reason
    reason --> bashTool
    pomXml --> bashTool
    bashTool --> postGate
    diffTool -->|"snapshot +\nverify"| postGate
    reason --> issues
    postGate --> prs
```

## 9. Automated Evaluation System

Two-layer evaluation system — **fully automated**, no manual intervention needed. Runs on every code change and every 6 hours on a schedule.

```mermaid
flowchart TB
    subgraph triggers [Triggers]
        codePush["Code Push\n(git webhook)"]
        modelUpdate["Model Update\n(OGX redeploy)"]
        cron["CronJob\n(every 6 hours)"]
    end

    subgraph pipeline [CI Pipeline: agent-with-eval-gates]
        gate1["Gate 1: model-eval-gate\n(Tekton Task)\nEvalHub safety + security"]
        gate2["Gate 2: agent-eval-gate\n(Tekton Task)\n38 cases × 6 agents\nregression detection"]
        agentTask["call-ssc-agent\n(Tekton Task)"]
    end

    subgraph evalhub [EvalHub - RHOAI 3.5]
        api["EvalHub API"]
        lmEval["lm_evaluation_harness\n(truthfulqa, toxigen,\nethics, bbq)"]
        garak["Garak\n(OWASP Top 10, CWE)"]
    end

    subgraph agentEval [Agent Eval Runner]
        runner["app.eval.agent_eval\n(38 eval cases)"]
        baseline["baseline.json\n(regression reference)"]
        scoring["Deterministic scoring\n+ LLM-as-judge metrics"]
    end

    subgraph tracking [Experiment Tracking]
        mlflow["MLflow\n(all metrics + artifacts)"]
    end

    triggers --> pipeline
    gate1 -->|"submit"| api
    api --> lmEval & garak
    gate1 -->|"PASS"| gate2
    gate1 -->|"FAIL"| blocked1["Pipeline\nBlocked"]
    gate2 --> runner
    runner --> baseline
    runner --> scoring
    gate2 -->|"PASS"| agentTask
    gate2 -->|"FAIL"| blocked2["Pipeline\nBlocked"]
    runner -->|"log"| mlflow
    api -->|"log"| mlflow
```

### Layer 1: Model-Level Eval (EvalHub)

Verifies the underlying LLM is safe before any agent runs.

| Benchmark | Provider | Threshold | What it catches |
|-----------|----------|-----------|-----------------|
| truthfulqa_mc1 | lm_evaluation_harness | 0.60 | Hallucination tendency |
| toxigen | lm_evaluation_harness | 0.85 | Toxic output generation |
| ethics_cm | lm_evaluation_harness | 0.75 | Ethical reasoning |
| bbq | lm_evaluation_harness | 0.90 | Bias in ambiguous contexts |
| owasp_llm_top10 | Garak | 0.10 | Prompt injection, jailbreaks |
| cwe | Garak | 0.10 | Code weakness exploitation |
| quality | Garak | 0.10 | Code quality patterns |

### Layer 2: Agent-Level Eval (38 cases across 6 agents)

Verifies each agent behaves correctly with regression detection.

| Agent | Cases | Key metrics tested |
|-------|-------|--------------------|
| Coordinator | 8 | Correct routing, out-of-scope decline, full pipeline orchestration |
| CVE Selection | 7 | Hallucination guard, structured output, skill-first, version verification |
| CVE Analysis | 5 | Multi-CVE handling, issue creation, empty set, duplicate detection |
| Remediation | 7 | Build retry loop, pre/post gate, max retries, skill-first |
| Test Generation | 5 | Compile failure retry, test-only PRs, config change tests |
| Fix Validation | 6 | Gate accuracy, nosec detection, root cause cap, persona consensus |

### Automation guarantees

- **Every code push** triggers the full pipeline via Tekton EventListener
- **Every 6 hours** a CronJob runs evals even with no code changes (catches model drift)
- **Model updates** trigger evals via the webhook EventListener
- **Regression detection** compares each metric against `baseline.json` (tolerance: 10%)
- **Floor enforcement** blocks deploy if any metric falls below its absolute minimum
- **MLflow logging** tracks every eval run for trend analysis
- **Zero manual steps** — `make deploy-eval-tasks` sets up everything on the cluster

### Custom eval metrics (LLM-as-judge)

| Metric | Applies to | What it measures |
|--------|-----------|-----------------|
| `cve_selection_accuracy` | Selection | Did the agent verify versions before deciding? |
| `version_not_hallucinated` | Selection | Every reported version was checked via tool call? |
| `correct_routing` | Coordinator | Delegated to the right sub-agent? |
| `skill_loaded_first` | Selection, Analysis, Remediation | Loaded methodology skill before acting? |
| `tool_use_completeness` | Selection, Analysis | Called all necessary tools? |
| `remediation_build_passes` | Remediation, Test Gen | Build succeeds after changes? |
| `validation_gate_accuracy` | Validation | Gates match expected results? |
| `pr_hygiene` | Remediation, Test Gen | PR is focused, described, no anti-patterns? |

## 10. MLflow Tracing

Full-stack observability via OpenTelemetry + MLflow. Every LLM call, tool execution, and agent delegation is captured as a span and forwarded to RHOAI MLflow.

### Span Architecture

```mermaid
flowchart TB
    subgraph agent [ADK Agent Process]
        subgraph otel [OpenTelemetry TracerProvider]
            adkSpans["ADK Auto-Spans\n(agent runs, tool calls,\ndelegate events)"]
            litellmSpans["LiteLLM Autolog Spans\n(LLM requests/responses,\ntoken counts, latencies)"]
            customSpans["Custom Spans\n(wrap_func_with_mlflow_trace)"]
        end

        subgraph exporter [OTLP HTTP Exporter]
            otlpExp["OTLPSpanExporter\nendpoint: /v1/traces\nheaders: experiment-id,\nworkspace, auth token"]
        end
    end

    subgraph rhoai [RHOAI 3.5 - MLflow]
        mlflowSvc["MLflow Service\n(redhat-ods-applications)"]
        experiments["Experiment: lw-agents"]
        traces["Trace Viewer\n(spans, latencies,\ntoken counts)"]
    end

    adkSpans --> otlpExp
    litellmSpans --> otlpExp
    customSpans --> otlpExp
    otlpExp -->|"OTLP/HTTP POST"| mlflowSvc
    mlflowSvc --> experiments --> traces
```

### Span Hierarchy (typical CVE selection run)

```mermaid
flowchart LR
    root["🔵 ssc_coordinator\n(agent span)"] --> sel["🔵 cve_selection\n(agent span)"]
    sel --> skill["🟢 load_skill\n(tool span)"]
    sel --> list["🟢 list_must_fix_cves\n(tool span)"]
    sel --> lookup["🟢 lookup_cve_detail\n(tool span)"]
    sel --> parse["🟢 parse_maven_purl\n(tool span)"]
    sel --> check["🟢 check_version_exists\n(tool span)"]
    sel --> llm1["🟡 gemini-2.5-flash\n(LLM span)\ntokens: 1.2k→0.8k"]
    sel --> llm2["🟡 gemini-2.5-flash\n(LLM span)\ntokens: 2.1k→1.5k"]
```

### Bootstrap Sequence

```mermaid
sequenceDiagram
    participant Init as app/__init__.py
    participant Tracing as app/tracing.py
    participant MLflow as MLflow Server
    participant OTel as TracerProvider
    participant ADK as ADK Agent

    Init->>Tracing: enable_tracing()
    Tracing->>Tracing: Check MLFLOW_TRACKING_URI
    alt URI not set
        Tracing-->>Init: No-op (tracing disabled)
    else URI set
        Tracing->>MLflow: Health check (probe /v1/traces)
        alt Unreachable
            Tracing-->>Init: Warning logged, continue without tracing
        else Healthy
            Tracing->>MLflow: set_tracking_uri() + set_experiment("lw-agents")
            Tracing->>Tracing: mlflow.litellm.autolog()
            Tracing->>OTel: Configure TracerProvider + OTLPSpanExporter
            Tracing-->>Init: Tracing enabled ✓
        end
    end
    Init->>ADK: Import and build agents (spans now captured)
```

### Configuration

| Env Var | Required | Default | Description |
|---------|----------|---------|-------------|
| `MLFLOW_TRACKING_URI` | Yes (to enable) | — | MLflow server URL |
| `MLFLOW_EXPERIMENT_NAME` | No | `lw-agents` | Experiment name in MLflow |
| `MLFLOW_WORKSPACE` | No | — | RHOAI workspace (maps to K8s namespace) |
| `MLFLOW_TRACKING_TOKEN` | No | — | Bearer token for auth |
| `MLFLOW_TRACKING_INSECURE_TLS` | No | `false` | Skip TLS verification |
| `MLFLOW_HEALTH_CHECK_TIMEOUT` | No | `5` | Seconds to wait for MLflow |

### Key Design Decisions

1. **Opt-in**: Tracing only activates when `MLFLOW_TRACKING_URI` is set
2. **Graceful degradation**: If MLflow is unreachable or deps are missing, agents start normally
3. **Two-layer capture**: OTel (ADK spans) + LiteLLM autolog (LLM call spans) for full coverage
4. **Bootstrap order**: Tracing initializes before any ADK imports to capture all spans
5. **Zero code changes to agents**: Existing agents get full tracing without modification

## 11. Deployment Architecture

How the ADK agent service is deployed on OpenShift alongside Tekton and EvalHub.

```mermaid
flowchart TB
    subgraph cluster [OpenShift Cluster]
        subgraph tektonNs [Namespace: tssc-app-ci]
            pipelineRun["Tekton PipelineRun\n(agent-with-eval-gate)"]
            evalTask["Task Pod: evalhub-eval-gate\n(submit + wait)"]
            taskPod["Task Pod: call-ssc-agent\n(curl -> agent service)"]
            buildPod["Task Pods: clone/build/scan\n(existing CI/CD)"]
        end

        subgraph agentNs [Namespace: tssc-agents]
            agentDeploy["Deployment: lw-agents\nreplicas: 1"]
            agentSvc["Service: ssc-agent\nport: 8080"]
            agentPod["Pod: ADK api_server\n+ root_agent + skills"]
        end

        subgraph rhoaiNs [Namespace: redhat-ods-applications]
            evalHubSvc["EvalHub Service\n(TrustyAI operator)"]
            mlflowSvc["MLflow Service\n(experiment tracking\n+ OTLP traces)"]
        end

        subgraph config [Configuration]
            configMap["ConfigMap: agent-config\nMODEL_NAME\nWORKSPACE_PATH\nSCM_BASE_BRANCH\nEVALHUB_URL"]
            secret["Secret: agent-secrets\nGEMINI_API_KEY\nSCM_TOKEN\nEVALHUB_TOKEN"]
        end
    end

    pipelineRun --> buildPod
    pipelineRun --> evalTask
    evalTask -->|"EvalHub API"| evalHubSvc
    evalHubSvc -->|"log metrics"| mlflowSvc
    evalTask -->|"PASS"| taskPod
    taskPod -->|"HTTP POST :8080"| agentSvc
    agentSvc --> agentPod
    agentDeploy --> agentPod
    agentPod -->|"OTLP /v1/traces\n(OTel spans)"| mlflowSvc
    config --> agentPod
```

## Architecture Decision Records

See [docs/adr/](adr/) for the full set:

| ADR | Title |
|-----|-------|
| [001](adr/001-agent-framework-selection.md) | Agent Framework Selection (Google ADK on OpenShift) |
| [002](adr/002-agents-and-skills-first.md) | Agents-and-Skills-First Architecture |
| [003](adr/003-opencode-as-coding-agent.md) | OpenCode as Coding Agent |
| [004](adr/004-tekton-calls-agent-via-api.md) | Tekton Calls Agent via API |
| [005](adr/005-orchestration-pattern-selection.md) | Orchestration Pattern Selection |
| [006](adr/006-safety-at-runner-level.md) | Safety at Runner Level |
| [007](adr/007-policy-gates.md) | Policy Gates Before and After the Agent |
| [008](adr/008-multi-persona-validation.md) | Multi-Persona Fix Validation |
| [009](adr/009-output-redaction.md) | Output Redaction at Runner Level |
| [010](adr/010-evalhub-integration.md) | EvalHub Integration for Safety and Quality Gates |
| [011](adr/011-mlflow-tracing.md) | MLflow Tracing via OpenTelemetry |
