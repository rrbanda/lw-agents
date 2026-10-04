# Page briefs

Five lines per page. No prose until these pass.

## 1. Start here
- Question: What is a CVE, and why does knowing the number not make you safe?
- Answer: A CVE is a publicly recorded flaw. Absorbing the fix is the work. Different people in the organization own different parts of that work.
- Reader leaves knowing: The vocabulary, the eight personas, and where to read next.
- Must not claim: That any tool solves the whole problem. That agents are needed.
- Source: CVE Program public page, lifecycle notes.

## 2. Concerns
- Question: What decisions does the organization actually face when a CVE is published?
- Answer: Seven questions, from "is this flaw in software we run?" through "what if an attack is already underway?" Each maps to a lifecycle phase.
- Reader leaves knowing: Which concern is theirs, and that the concerns come in an order.
- Must not claim: That every concern has an automated answer. That Lightwell or agents resolve all of them.
- Source: Lifecycle phases mapped to plain language.

## 3. Lifecycle
- Question: Where do the concerns sit across the full CVE lifecycle?
- Answer: Ten phases, the formal record track, four overlapping workstreams, and for each phase whether an agent may assist, own a bounded step, or must stay out.
- Reader leaves knowing: The map, and that most phases are not where agents act.
- Must not claim: That these phase names are a CVE Program standard.
- Source: CVE lifecycle notes (app.js), CVE Program process page, FIRST CVSS, EPSS, CISA KEV.

## 4. Solutions
- Question: What kinds of response exist, and where does each help?
- Answer: Scanner finds. Upstream upgrade when the app can move. Platform patch for the OS. Hardened image for the container base. Security-only backport (Lightwell) for a library that cannot move. Mitigate, isolate, accept, or retire. Agents are a way to do the work, not a new kind of fix.
- Reader leaves knowing: That the response depends on what layer the vulnerability is in and whether the application can take a change.
- Must not claim: That one product covers every layer.
- Source: Public product pages, workshop coexistence appendix.

## 5. Pipeline only
- Question: What does a CI/CD pipeline do for CVEs without any AI?
- Answer: Clone, build, SBOM, scan, policy gate, deploy check. It surfaces what is wrong. A person reads and acts.
- Reader leaves knowing: The pipeline head that every execution model shares, and that it does not open the fix.
- Must not claim: That the pipeline remediates anything.
- Source: ssc-demo maven-build-ci-pipeline.yaml.

## 6. Pipeline with agents
- Question: What changes when agent tasks run inside the pipeline?
- Answer: Two variants share one shape. The pipeline owns the DAG and the gates. An agent task does one bounded step. Inline agents are stateless (one prompt, one answer). A remote agent service holds a session and retries. PRs are never auto-merged. Fail-closed.
- Reader leaves knowing: The difference between inline and remote service, the six-field contract, and the human handoff.
- Must not claim: That the agent decides what to do next. The pipeline does.
- Source: ssc-demo agentic-*.yaml, lw-*.yaml, demo narrative.

## 7. Fully agentic
- Question: What would a system with no fixed pipeline look like?
- Answer: A coordinator decides the next action across phases inside written rules. Not built. Bounds: one advisory, person approves, no exploit procedure, no embargo leak.
- Reader leaves knowing: What it gains (no handoff bottleneck) and what it loses (declared auditability).
- Must not claim: That this system exists.
- Source: Conceptual. Bounds derived from lifecycle controls.

## 8. How to choose
- Question: Given my constraints, which execution model fits?
- Answer: A table from organizational constraint to model, with a column for what a person still does.
- Reader leaves knowing: Their row in the table.
- Must not claim: That a single model fits everyone.
- Source: Synthesis of the preceding pages.

## 9. Lightwell
- Question: When is a security-only backport the right response, and how does it work?
- Answer: When the application library cannot move to a newer upstream version. The pin keeps the same version and adds a suffix. The fixed event names the coordinate.
- Reader leaves knowing: Validated vs remediated, the suffix, the repository URLs, and when Lightwell is not the answer.
- Must not claim: That Lightwell replaces the platform, the base image, or the decision to upgrade.
- Source: Lightwell product docs, workshop appendix, HTTP checks.

## 10. Sources
- Question: Where do the facts on this site come from?
- Answer: Public references grouped by what each source proves.
- Reader leaves knowing: Which source to check for which claim.
- Must not claim: Anything from the confidential handbook.
- Source: Links to CVE Program, FIRST, CISA, NVD, Lightwell docs, workshop, ssc-demo.
