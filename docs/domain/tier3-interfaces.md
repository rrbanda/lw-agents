---
title: Tier 3 integration interfaces
summary: Interface designs for SBOM Index, App Lineage orchestrator, and verification API. These components require product investment. Designing the interfaces now prevents rework when they arrive.
---

# Tier 3 Integration Interface Designs

These interfaces are not implemented. They document how the existing
remediation engine will connect to future platform capabilities.

## Interface 1: SBOM Index → Remediation Pipeline

### Current state
The pipeline generates an SBOM per run, uploads it to RHTPA, and scans it.
Each pipeline run discovers what is vulnerable in one repo.

### Future state
A persistent SBOM Index (Tkn Results) knows what every built artifact
contains. When a CVE is published, the index returns all affected repos
instantly.

### Interface contract

```yaml
# Trigger: new CVE published or OSV feed updated
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerBinding
metadata:
  name: sbom-index-cve-trigger
spec:
  params:
    - name: CVE_ID
      value: $(body.cve_id)
    - name: AFFECTED_REPOS
      value: $(body.affected_repos)
      # JSON array: [{"repo_url": "...", "package": "...",
      #   "current_version": "...", "image_url": "...",
      #   "deployment": "...", "priority": 1}]
    - name: FIXED_VERSION
      value: $(body.fixed_version)
    - name: SOURCE
      value: $(body.source)
      # "lightwell-osv" | "osv-dev" | "nvd"
```

When the SBOM Index is available, the pipeline head (stages 1 of the
current flow: clone, build, SBOM, scan) becomes optional. The index
already knows. The pipeline starts at stage 2 (triage) with the affected
repos list as input.

### What the engine needs to change
Nothing in `lw-agents`. The remediation agent takes `(repo_url, cve_id,
package, current_version, fixed_version)` today. The SBOM Index adds
`image_url`, `deployment`, and `priority` to the input params. These
become available in session state for the remediation plan to use.

## Interface 2: App Lineage → Cross-Repo Orchestrator

### Current state
One repo, one CVE, one PR. No awareness of dependency order.

### Future state
The App Lineage Graph maps artifacts to source repos and to production
deployments via ArgoCD. An orchestrator calls the remediation engine
for each repo in dependency order.

### Interface contract

```yaml
# Orchestrator calls remediation pipeline for each repo in order
# The engine does not change — it gets called more intelligently
orchestration:
  trigger: sbom-index-cve-alert
  strategy: dependency-order
  params_per_repo:
    - repo_url: string        # existing
    - cve_id: string           # existing
    - package: string          # existing
    - current_version: string  # existing
    - fixed_version: string    # existing
    - priority: integer        # NEW: from lineage graph
    - sla_window_hours: integer # NEW: from remediation plan
    - dependency_order: integer # NEW: rebuild sequence position
    - dependent_repos: list    # NEW: repos that depend on this one
    - deployment_target: string # NEW: ArgoCD app name
```

### What the engine needs to change
The remediation pipeline params already accept all the core fields.
New fields (`priority`, `sla_window_hours`, `dependency_order`) can be
added as optional params with defaults. The agent does not use them
directly — they are for the orchestrator and the remediation plan.

## Interface 3: Verification API

### Current state
The pipeline stops at the PR. No verification that the fix is live.

### Future state
After merge, deploy, and rebuild, the verification pipeline (T2.4)
re-scans. It needs to report the result somewhere persistent.

### Interface contract

```yaml
# Verification result — written to issue, SBOM Index, and compliance record
verification:
  cve_id: string
  package: string
  fixed_version: string
  image_url: string
  verified: boolean
  verified_at: timestamp
  sbom_hash: string           # hash of the SBOM that confirms absence
  deployment: string          # ArgoCD app where it was verified
  
  # Where to report
  update_targets:
    - type: gitlab-issue
      url: string             # close the issue or add a verification comment
    - type: sbom-index
      action: mark-remediated # update the index entry for this CVE+artifact
    - type: compliance-record
      format: csaf-vex        # generate a VEX document confirming the fix
```

### What the engine needs to change
The verification pipeline (T2.4, `cve-verification.yaml`) already
produces `VERIFIED=1/0`. When the SBOM Index and compliance systems
arrive, the `report-status` finally task needs to write to those
targets. The interface is defined here so the task can be extended
without restructuring.

## Summary

| Interface | Input to engine | Output from engine | New params |
| --- | --- | --- | --- |
| SBOM Index | Affected repos list with priority | Same structured result | `image_url`, `deployment`, `priority` |
| App Lineage | Repos in dependency order | Same PR per repo | `dependency_order`, `dependent_repos`, `sla_window_hours` |
| Verification | Deployed image URL + CVE ID | `VERIFIED=1/0` + detail JSON | `sbom_hash`, `deployment`, compliance targets |

None of these require changes to the core remediation agent or the
Lightwell tools. They add context around the engine, not inside it.
