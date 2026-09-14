# Architecture

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
        specialists["Specialist Agents\n(selection / analysis /\nremediation / test-gen)"]
    end

    subgraph external [External Systems]
        rhtpa["RHTPA / Trustify\n(vuln reports)"]
        scm["GitLab / GitHub\n(issues + PRs)"]
        llm["LLM Provider\n(Gemini / Anthropic /\nOpenAI-compat)"]
        opencode["OpenCode\n(coding agent)"]
        maven["Maven Central\n(version verification)"]
    end

    clone --> build --> sbom --> policy
    policy --> callAgent
    callAgent -->|"HTTP POST"| coordinator
    coordinator --> specialists
    specialists --> llm
    specialists -->|"ExecuteBashTool"| opencode
    specialists -->|"ExecuteBashTool"| maven
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
        sel["cve_selection\n(LlmAgent)"]
        selSkills["SkillToolset\ncve-triage\nscm-conventions"]
        selTools["FunctionTools\nlist_must_fix_cves\nlookup_cve_detail\nparse_maven_purl\ncheck_version_exists"]
    end

    subgraph analysisAgent [CVE Analysis Agent]
        ana["cve_analysis\n(LlmAgent)"]
        anaSkills["SkillToolset\ncve-analysis\nscm-conventions"]
        anaTools["FunctionTools\nlist_must_fix_cves\nlookup_cve_detail\nparse_maven_purl\ncheck_version_exists\ncreate_scm_issue"]
    end

    subgraph remAgent [Remediation Agent]
        rem["remediation\n(Workflow graph)"]
        remPlan["remediation_planner\n(LlmAgent node)"]
        remSkills["SkillToolset\nmaven-remediation\nscm-conventions"]
        remBash["ExecuteBashTool\nopencode / mvn"]
    end

    subgraph testAgent [Test Generation Agent]
        tst["test_generation\n(SequentialAgent)"]
        tstWriter["initial_test_writer\n(LlmAgent)"]
        tstLoop["test_refinement_loop\n(LoopAgent)"]
        tstPR["test_pr_opener\n(LlmAgent)"]
    end

    subgraph safety [Runner Plugins]
        safePlug["SafetyPlugin\n(LLM-as-judge)"]
    end

    coord -->|"delegates"| sel & ana & rem & tst
    sel --- selSkills & selTools
    ana --- anaSkills & anaTools
    rem --- remPlan
    remPlan --- remSkills & remBash
    tst --- tstWriter --> tstLoop --> tstPR
    safePlug -.->|"wraps all"| coord
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

## 4. Remediation Workflow Graph

The Workflow edges, conditional routing, retry loop, and HITL pause.

```mermaid
flowchart LR
    START((START)) --> readProject[read_project\nparse request\nstash state]
    readProject --> planAgent["remediation_planner\n(LlmAgent)\nload skill + bash\nopencode + mvn"]
    planAgent --> checkBuild{check_build_result}

    checkBuild -->|"SUCCESS"| requestApproval["request_pr_approval\n(RequestInput HITL)\npause for human"]
    checkBuild -->|"RETRY"| planAgent
    checkBuild -->|"MAX_RETRIES"| reportFail[report_failure]

    requestApproval -->|"human approves"| processPR["process_pr_decision\ncreate_pull_request"]
    requestApproval -->|"human rejects"| rejected[PR rejected]
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

## 6. Data Flow

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
        bashTool["ExecuteBashTool\nopencode run / mvn"]
    end

    subgraph agent [Agent Reasoning]
        reason["LLM Agent\nloads skill\ncalls tools\nreasons per-CVE"]
    end

    subgraph outputs [Outputs]
        issues["GitLab/GitHub Issues\n(one per fixable CVE)"]
        prs["Pull Requests\n(remediation or tests)"]
    end

    mustFix --> listTool --> reason
    vulnReport --> lookupTool --> reason
    reason --> parseTool
    reason --> checkTool
    reason --> bashTool
    pomXml --> bashTool
    reason --> issues
    reason --> prs
```

## 7. Deployment Architecture

How the ADK agent service is deployed on OpenShift alongside Tekton.

```mermaid
flowchart TB
    subgraph cluster [OpenShift Cluster]
        subgraph tektonNs [Namespace: tssc-app-ci]
            pipelineRun["Tekton PipelineRun\n(agentic-cve-remediation)"]
            taskPod["Task Pod: call-ssc-agent\n(curl -> agent service)"]
            buildPod["Task Pods: clone/build/scan\n(existing CI/CD)"]
        end

        subgraph agentNs [Namespace: tssc-agents]
            agentDeploy["Deployment: lw-agents\nreplicas: 1"]
            agentSvc["Service: ssc-agent\nport: 8080"]
            agentPod["Pod: ADK api_server\n+ root_agent + skills"]
        end

        subgraph config [Configuration]
            configMap["ConfigMap: agent-config\nMODEL_NAME\nWORKSPACE_PATH"]
            secret["Secret: agent-secrets\nGEMINI_API_KEY\nSCM_TOKEN"]
        end
    end

    pipelineRun --> buildPod
    pipelineRun --> taskPod
    taskPod -->|"HTTP POST :8080"| agentSvc
    agentSvc --> agentPod
    agentDeploy --> agentPod
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
