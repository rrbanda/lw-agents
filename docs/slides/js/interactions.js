(function () {
  'use strict';

  // Decision card expand/collapse
  document.querySelectorAll('.decision-header').forEach(function (hdr) {
    hdr.addEventListener('click', function () {
      var card = this.closest('.decision-card');
      var wasExpanded = card.classList.contains('expanded');
      document.querySelectorAll('.decision-card.expanded').forEach(function (c) { c.classList.remove('expanded'); });
      if (!wasExpanded) card.classList.add('expanded');
    });
  });
})();

// ===== SPEAKER NOTES & PRESENTER VIEW =====
(function () {
  'use strict';

  window.SPEAKER_NOTES = [
    "Welcome everyone. Today we're going to walk through something our team has been building at the intersection of AI and software supply chain security.\n\nThe core question is this: when AI-powered scanners can discover zero-day vulnerabilities faster than any human team, how do you keep your open source dependencies patched? Manual patch cycles don't scale. So we built an agentic system that does.\n\nThis deck covers the full story — from why Lightwell exists as a product, to the AI engine behind it, down to individual agent implementations, policy gates, and deployment on OpenShift. It's a technical deep dive, so stop me if you want to dig into any particular piece.",
    "Here's our roadmap. Seven sections, building from the business problem to production deployment.\n\nBefore we go deeper, look at these pain points on screen. These are real challenges our customers face daily. AI scanners surface hundreds of CVEs. Manual backports create permanent forks. Time-to-exploit has collapsed. And when you try to use AI to fix the problem, you need guardrails — because a hallucinated fix is worse than no fix at all.\n\nSo we need a system that's fast, accurate, and trustworthy. That's what we built.",
    "Let's set the stage. The Mythos moment changed everything in software security. When frontier AI proved it could autonomously discover decades-old zero-days and produce working exploits faster and cheaper than human research teams, Time-To-Exploit effectively collapsed to zero.\n\nLook at the three options enterprises have without Lightwell. Upgrade to latest — but the fix may not exist upstream yet, and you risk breaking production. DIY backport — congratulations, you now own a custom fork of that library forever. Or do nothing — and accept the regulatory and security risk of a confirmed exploit.\n\nLightwell Network gives you a fourth option: validated, non-breaking backported patches for Maven and PyPI, signed to SLSA L3, delivered with SBOMs and VEX advisories. Zero code refactoring — just point your build tools at the registry.\n\nLightwell Clearinghouse takes it further with SLA-backed remediation timelines and an anonymized collective intelligence network. One institution's discovery automatically expands the protective shield for every other member.\n\nThe four operating principles are important to call out — especially 'every fix goes upstream.' We never hoard patches.",
    "Lightwell Lens is the front door for many conversations. It's a self-service coverage assessment tool that instantly shows how much of a customer's actual software inventory is already covered by Lightwell Network.\n\nYou upload an SBOM — SPDX, CycloneDX, a pom.xml, requirements.txt, or a list of Package URLs — and Lens generates a coverage report in seconds. Exact matches mean the precise name and version exist in our catalog. Partial matches mean the package name exists, so there's a clear path to coverage.\n\nThe key positioning point: even small coverage fractions deliver massive value when they cover critical dependencies. A single patched Log4j or Spring Core dependency can eliminate more risk than covering hundreds of leaf packages. Quality and impact over raw volume.\n\nAnd the catalog is expanding rapidly — over 15,000 package versions and accelerating. For continuous monitoring, point them to Red Hat Trusted Profile Analyzer.",
    "Now here's where it gets interesting from an engineering perspective. Lightwell Network delivers the packages. This system — the one in this repo — creates them.\n\nThe flow is straightforward conceptually: scanner findings come in, we select the best CVE to fix, analyze it, remediate the Maven POM, generate tests to prove it works, validate the fix through adversarial security review, and open a pull request for human review.\n\nUnder the hood, this is a Google ADK 2.0 application with a coordinator agent that delegates to five specialists. Each specialist has domain-specific skills loaded from SKILL.md files — think of them as expert playbooks the LLM follows step by step.\n\nThe trust model is critical. We have five independent safety layers — safety plugin, redaction plugin, pre-gate, post-gate, and fail-closed scoring. And every PR goes through human review. The agents accelerate engineering; they don't replace engineering judgment.\n\nSomeone's going to ask about the numbers: 5 specialist agents, 8 skill playbooks, 38 eval cases that run on every code push, and up to 3 retry loops on build failures. Let's dig into each piece.",
    "So why do we need agents at all? Can't a script do this?\n\nLook at the manual remediation workflow. For each CVE you need to: triage it, parse the Package URL, check Maven Central for available versions, backport the fix, run mvn verify, write tests, do a security review, and open a PR. Each step requires judgment and context from previous steps.\n\nThe scale problem is real. Hundreds of CVEs across thousands of packages. Each one needs individual triage — you can't batch this because transitive dependency impacts are unique per project. Maven POM edits are particularly tricky because a single version bump can cascade failures through the dependency tree.\n\nAnd then there's the trust question. How do you know the AI-generated fix is safe? Did it slip in a nosec comment? Did it set verify=False somewhere? This is why we have policy gates — but I'll get to that.\n\nThe agent handles the repetitive, error-prone steps while humans review the final PR. It's augmentation, not replacement.",
    "Let's zoom out and look at the full system context. The ADK agent service is one component in a Tekton CI/CD pipeline.\n\nThe pipeline flow goes: clone the repo, build and package, generate the SBOM, run Conforma policy checks, then hit two eval gates — model safety and agent behavior regression — before the agent service ever processes real work.\n\nThe agent service itself is a long-lived HTTP server on port 8080. A thin Tekton Task called call-ssc-agent just POSTs the task type and workspace path. The agent returns structured results — SELECTED, CVE_ID, PR_URL — that get mapped back to Tekton result fields.\n\nFour task types: select-cve, analyze-cves, remediate, and generate-tests. Each maps to a specialist agent through the coordinator. The coordinator never attempts work itself — it's purely a router.\n\nSomeone's going to ask about statefulness. The service is stateless between requests but stateful within a session. ADK's ResumabilityConfig handles session resumption if Tekton needs to retry.",
    "This is the heart of the system. One root coordinator, five specialist agents, each with precisely the tools and skills they need.\n\nThe coordinator — ssc_coordinator — is an LlmAgent that delegates based on task type. Its instruction is explicit: 'Always delegate, never attempt the task yourself.' Two plugins wrap everything: SafetyPlugin for LLM-as-judge content screening, and RedactionPlugin for secret masking.\n\nLook at the five specialists. CVE Selection is an LlmAgent with the cve-triage skill and four CVE tools. CVE Analysis is similar but with the cve-analysis skill. These are the simplest agents — single LlmAgent, no loops.\n\nRemediation is where it gets interesting — it's a SequentialAgent with three phases. The initial planner, a retry loop with a BuildResultChecker, and a PR opener. If you look at remediation.py, you'll see the SequentialAgent wrapping a LoopAgent. Not a Workflow — we tried that, but Workflow can't be used as an LlmAgent sub-agent in ADK.\n\nTest generation mirrors that pattern — writer, refinement loop, PR opener.\n\nValidation is the most unusual: two LLM personas feed into a deterministic scorer that uses zero LLM calls. I'll cover that in detail shortly.",
    "ADR-002 established the skills-first architecture, and I'd argue it's the single most important design decision in the system.\n\nAgent behavior lives in SKILL.md files, not in Python instruction strings. When the agent starts, the first thing it does is call load_skill to get its playbook. The skill contains the full methodology — step by step — with examples, edge cases, and output format specifications.\n\nWe have seven skills. cve-triage encodes how to evaluate and rank CVEs for selection. maven-remediation has the complete POM editing procedure. junit-test-generation covers test scaffolding patterns. The two validation skills — validation-architect and validation-pentester — encode different security review perspectives.\n\nWhy not just put instructions in the Python code? Three reasons. First, skills are version-controlled markdown files that domain experts can edit without touching Python. Second, they're loaded on demand so they don't eat up the context window when they're not needed. Third, they're portable — the same skill works regardless of which model is serving inference.\n\nWhen you want to change how the agent triages CVEs, you edit skills/cve-triage/SKILL.md. No code change, no redeploy, no retest of the Python layer.",
    "The remediation pipeline is the most complex agent in the system. Let me walk through exactly what happens.\n\nPhase 1: The initial_remediation_planner loads the maven-remediation skill, clones the repository using clone_repository, analyzes the CVE, edits pom.xml using OpenCode through execute_bash, and runs mvn verify. The pre_gate_callback fires first — it validates the CVE ID format, checks Maven coordinates, and verifies versions. If the input is garbage, we reject before spending a single token.\n\nPhase 2: If the build fails — and it does fail sometimes, Maven transitive dependencies are gnarly — the LoopAgent kicks in. BuildResultChecker is a BaseAgent that parses the build output. If it's a PASS, escalate to PR creation. If FAIL, the remediation_retry_planner gets another shot with the full error context. Up to 3 attempts.\n\nPhase 3: remediation_pr_opener stages the changed files, commits, pushes, and opens a PR using glab or gh CLI.\n\nA technical detail people often ask about: execute_bash is NOT ADK's built-in ExecuteBashTool. It's a custom FunctionTool via build_bash_tool() in config.py that constrains commands to an allowlist — opencode, mvn, git, cat, ls, find, grep. The agent can't run arbitrary shell commands.\n\nThe post_gate_callback validates the diff after execution. If it finds nosec comments, @SuppressWarnings, verify=False, or other forbidden patterns — the diff is rejected.",
    "Test generation mirrors the remediation pattern but produces tests instead of fixes.\n\nThe initial_test_writer loads the junit-test-generation skill, generates JUnit test files using OpenCode, and runs mvn test. If tests fail, the refinement loop kicks in — test_evaluator grades the results, test_escalation_checker decides whether to escalate or retry, and test_fixer attempts to fix the failing tests.\n\nThe key architectural decision: test PRs are separate from remediation PRs. This is intentional. Reviewers can evaluate the dependency fix and its tests independently. A test failure doesn't block the remediation PR, and vice versa.\n\nThe TestEscalationChecker is a BaseAgent — no LLM. It's a deterministic check: if all tests pass, escalate. If not, send back for another iteration. Simple but critical for preventing infinite loops.",
    "Fix validation is my favorite part of the architecture because it solves a genuinely hard problem: how do you trust an AI-generated security fix?\n\nThe answer: adversarial review with deterministic consensus. Two LLM personas — a security architect and a penetration tester — provide independent assessments. Then a DeterministicScoring BaseAgent calculates the final verdict with zero LLM involvement.\n\nThe architect evaluates four gates: root cause coverage, instance coverage, no new vulnerabilities, and security best practices. The pentester tries to break the fix — finds bypasses, incomplete coverage, ways the vulnerability could still be exploited.\n\nThe scoring is pure weighted math. Root cause gets 0.43 weight — almost half the score — because if you didn't fix the actual vulnerability, nothing else matters. Instance coverage is 0.2467, no new vulns is 0.1867, best practices is 0.1366.\n\nConservative consensus means: if both personas agree it passes, HIGH confidence. If they disagree, the more conservative assessment wins, with FLAGGED confidence. And there's a critical gate cap: if root_cause is not PASS, the overall decision drops one level regardless of the total score.\n\nScore thresholds: 0.80 or above is FIXED. 0.50 to 0.80 is PARTIALLY_FIXED. Below 0.50 is NOT_FIXED. No ambiguity, no hallucination in the final call.",
    "Let me walk through the five safety layers because defense in depth is not just a buzzword here — it's five independent enforcement points.\n\nLayer 1: SafetyPlugin. An LLM-as-judge that screens user messages and model output at the App level. It wraps every agent in the system. Layer 2: RedactionPlugin. Regex-based secret masking on tool results — catches API keys, tokens, and credentials before they pollute the model context.\n\nLayer 3: Pre-gate. Validates inputs before spending tokens. The CVE ID must match the CVE-YYYY-NNNN pattern. The package must be valid Maven coordinates. Versions must contain digits and not be identical. If any check fails, the request gets a guidance-only response at zero model cost.\n\nLayer 4: Post-gate. Validates the diff after execution. Seven forbidden patterns: nosec, noqa, SuppressWarnings, verify=False, rejectUnauthorized false, bare except-pass, and PermitAll. Plus a hard limit of 5 files touched — if the agent is changing more than 5 files for a single CVE remediation, something has gone wrong. Oversized diffs above 100 lines get a warning.\n\nLayer 5: Fail-closed selection. The validation callback forces SELECTED=0 if anything is ambiguous — missing justification, placeholder text, unverified versions. Ambiguity means no.\n\nEach layer catches different failure modes. A prompt injection bypasses the SafetyPlugin? Hits the pre-gate. A hallucinated fix passes the pre-gate? Hits the post-gate. No single point of failure.",
    "The eval system is fully automated — zero manual steps. Two layers, both must pass.\n\nLayer 1 is model safety via EvalHub on RHOAI 3.5. Seven benchmarks: truthfulqa at 0.60, toxigen at 0.85, ethics at 0.75, bbq at 0.90 — those are all from lm_evaluation_harness. Then three Garak benchmarks: OWASP Top 10, CWE, and quality, all at 0.10 threshold where lower is better. If the model fails any benchmark, the pipeline blocks.\n\nLayer 2 is agent behavior — 38 test cases across all six agents. Coordinator gets 8 cases testing correct routing and out-of-scope decline. Selection gets 7 testing hallucination guards. Analysis gets 5. Remediation gets 7 testing the retry loop and gate enforcement. Test gen gets 5. Validation gets 6 testing gate accuracy and the root cause cap.\n\nEight custom LLM-as-judge metrics score each run: cve_selection_accuracy, version_not_hallucinated, correct_routing, skill_loaded_first, tool_use_completeness, remediation_build_passes, validation_gate_accuracy, and pr_hygiene.\n\nRegression detection compares against baseline.json with 10% tolerance. Floor enforcement blocks deploy if any metric drops below its absolute minimum.\n\nThis runs on every code push via Tekton EventListener, plus every 6 hours on a CronJob to catch model drift. When a model update causes regression, we know before it ever touches a real CVE.",
    "Observability is built on OpenTelemetry flowing into MLflow on Red Hat OpenShift AI.\n\nEvery LLM call, every tool execution, every agent delegation is captured as a span. There are two capture layers: OTel auto-instrumentation for ADK spans — agent runs, tool calls, delegation events — and LiteLLM autolog for LLM-specific data like model name, token counts, input/output, and latency.\n\nThe bootstrap sequence matters and it's in app/__init__.py: load_dotenv first, then enable_tracing, then import agents. Tracing has to initialize before any ADK imports to capture all spans from the start.\n\nKey design decision: tracing is opt-in. It only activates when MLFLOW_TRACKING_URI is set. If MLflow is unreachable, agents start normally — graceful degradation, not hard failure. And zero agent code changes — you get full tracing without modifying a single agent file.\n\nWhen a remediation fails on attempt 3 of the retry loop, you can trace back through every LLM call, every tool invocation, every state change to understand exactly what happened. That's the debugging superpower.",
    "Deployment is straightforward. UBI9 base with Python 3.12, JDK 17 and Maven for build verification, glab and gh CLIs for SCM operations, and OpenCode as the coding agent.\n\nKustomize layout: base directory has the Deployment, Service, Route, and ConfigMap. Dev and production overlays customize for each environment. The agent runs as adk api_server on port 8080.\n\nTekton integration has four tasks: call-agent-task is the thin HTTP caller, eval-gate-task submits EvalHub evals, agent-eval-task runs the 38 test cases, and scheduled-eval-trigger is the 6-hour CronJob.\n\nThree namespaces: tssc-app-ci for Tekton pipeline runs, tssc-agents for the agent deployment, and redhat-ods-applications for EvalHub and MLflow.\n\nLocal development is one command: make dev. Same agent code runs locally and in production. The only difference is configuration — model endpoints, SCM tokens, and MLflow URI come from environment variables. Make test for unit tests, make agent-eval for the 38 eval cases, make build and push for the container image.\n\nThat's the full picture — from scanner findings to validated pull request, running on OpenShift with full observability. Questions?"
  ];

  window.SECTION_TITLES = [
    "Opening",
    "Session Roadmap",
    "Why Lightwell Exists",
    "Lightwell Lens",
    "The AI Engine",
    "The Technical Challenge",
    "System Context",
    "Agent Hierarchy",
    "Skills-First Architecture",
    "Remediation Pipeline",
    "Test Generation",
    "Multi-Persona Validation",
    "Trust & Safety",
    "Automated Evaluation",
    "Observability",
    "Deployment"
  ];

  // Presenter View (P key or button)
  function openPresenterView() {
    var cur = window.getCurrentSlide ? window.getCurrentSlide() : 0;
    var total = window.getTotalSlides ? window.getTotalSlides() : window.SECTION_TITLES.length;
    var notes = window.SPEAKER_NOTES;
    var titles = window.SECTION_TITLES;

    var presenterWin = window.open('', 'presenter', 'width=900,height=700');
    if (!presenterWin) return;

    var d = presenterWin.document;
    d.open();
    d.write('<!DOCTYPE html><html><head><meta charset="utf-8"><title>Presenter View</title><style>');
    d.write('*{box-sizing:border-box;margin:0;padding:0}');
    d.write('body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#1a1a1a;color:#e0e0e0;display:grid;grid-template-rows:auto 1fr auto;height:100vh;overflow:hidden}');
    d.write('.pv-header{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;background:#111;border-bottom:1px solid #333;font-size:13px}');
    d.write('.pv-header .pv-title{color:#EE0000;font-weight:700;font-size:14px}');
    d.write('.pv-header .pv-timer{font-variant-numeric:tabular-nums;font-size:20px;font-weight:600;color:#fff}');
    d.write('.pv-header .pv-clock{color:#888;font-size:13px}');
    d.write('.pv-main{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px;overflow:hidden}');
    d.write('.pv-slide-col{display:flex;flex-direction:column;gap:8px;min-height:0}');
    d.write('.pv-slide-box{background:#212121;border:1px solid #333;border-radius:6px;padding:8px;flex:0 0 auto}');
    d.write('.pv-slide-box h4{font-size:11px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.5px}');
    d.write('.pv-slide-title{font-size:13px;color:#fff;font-weight:600;margin-top:4px;line-height:1.3}');
    d.write('.pv-notes-col{display:flex;flex-direction:column;min-height:0}');
    d.write('.pv-notes-col h3{font-size:12px;color:#EE0000;text-transform:uppercase;letter-spacing:0.5px;padding-bottom:6px;border-bottom:1px solid #333;margin-bottom:8px;flex-shrink:0}');
    d.write('.pv-notes{flex:1;overflow-y:auto;font-size:15px;line-height:1.6;color:#d2d2d2;white-space:pre-wrap;padding-right:8px}');
    d.write('.pv-notes strong{color:#fff}');
    d.write('.pv-footer{display:flex;align-items:center;justify-content:center;gap:12px;padding:8px 16px;background:#111;border-top:1px solid #333}');
    d.write('.pv-btn{background:#333;color:#fff;border:1px solid #555;border-radius:4px;padding:6px 18px;font-size:13px;cursor:pointer;font-family:inherit}');
    d.write('.pv-btn:hover{background:#444}');
    d.write('.pv-counter{font-size:15px;font-weight:600;min-width:80px;text-align:center}');
    d.write('</style></head><body>');
    d.write('<div class="pv-header"><span class="pv-title">Presenter View</span><span class="pv-timer" id="pv-timer">00:00</span><span class="pv-clock" id="pv-clock"></span></div>');
    d.write('<div class="pv-main">');
    d.write('<div class="pv-slide-col">');
    d.write('<div class="pv-slide-box"><h4>Current Slide</h4><div class="pv-slide-title" id="pv-cur-title"></div></div>');
    d.write('<div class="pv-slide-box"><h4>Next Slide</h4><div class="pv-slide-title" id="pv-next-title"></div></div>');
    d.write('</div>');
    d.write('<div class="pv-notes-col"><h3>Speaker Notes</h3><div class="pv-notes" id="pv-notes"></div></div>');
    d.write('</div>');
    d.write('<div class="pv-footer"><button class="pv-btn" id="pv-prev">◀ Prev</button><span class="pv-counter" id="pv-counter"></span><button class="pv-btn" id="pv-next">Next ▶</button></div>');
    d.write('</body></html>');
    d.close();

    var pvCurrent = cur;
    var startTime = Date.now();
    var pvChannel = null;
    try { pvChannel = new BroadcastChannel('presenter-sync'); } catch (e) {}

    function updatePV(idx) {
      pvCurrent = idx;
      var dd = presenterWin.document;
      if (!dd || !dd.getElementById) return;
      dd.getElementById('pv-cur-title').textContent = (idx + 1) + '. ' + (titles[idx] || '');
      dd.getElementById('pv-next-title').textContent = idx + 1 < total ? (idx + 2) + '. ' + (titles[idx + 1] || '') : '(End)';
      dd.getElementById('pv-notes').textContent = notes[idx] || '(No notes for this slide)';
      dd.getElementById('pv-counter').textContent = (idx + 1) + ' / ' + total;
    }

    function pvNavigate(idx) {
      idx = Math.max(0, Math.min(total - 1, idx));
      updatePV(idx);
      if (window.goToSlide) window.goToSlide(idx);
      if (pvChannel) pvChannel.postMessage({ type: 'navigate', index: idx });
    }

    if (pvChannel) {
      pvChannel.onmessage = function (e) {
        if (e.data && e.data.type === 'navigate') updatePV(e.data.index);
      };
    }

    presenterWin.document.getElementById('pv-prev').onclick = function () { pvNavigate(pvCurrent - 1); };
    presenterWin.document.getElementById('pv-next').onclick = function () { pvNavigate(pvCurrent + 1); };
    presenterWin.document.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); pvNavigate(pvCurrent + 1); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); pvNavigate(pvCurrent - 1); }
    });

    setInterval(function () {
      if (presenterWin.closed) return;
      var elapsed = Math.floor((Date.now() - startTime) / 1000);
      var mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
      var ss = String(elapsed % 60).padStart(2, '0');
      var dd = presenterWin.document;
      if (dd && dd.getElementById) {
        dd.getElementById('pv-timer').textContent = mm + ':' + ss;
        dd.getElementById('pv-clock').textContent = new Date().toLocaleTimeString();
      }
    }, 1000);

    updatePV(cur);
  }

  window.openPresenterView = openPresenterView;

  var notesBtn = document.getElementById('btn-notes');
  if (notesBtn) notesBtn.addEventListener('click', function (e) { e.stopPropagation(); openPresenterView(); });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'p' || e.key === 'P') {
      e.preventDefault();
      openPresenterView();
    }
  });
})();
