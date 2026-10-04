---
title: Pipeline only
summary: A CI/CD pipeline that finds what is wrong, without any AI. The starting point every execution model shares.
---

Before any agent is involved, the pipeline already does useful work. It clones, builds, generates an SBOM, scans for vulnerabilities, applies policy, and checks the image. The output is a report. A person reads it and decides what to do.

## What the pipeline does

| Step | What happens | External system |
| --- | --- | --- |
| Clone | Pull the application source from Git | SCM (GitLab, GitHub) |
| Build | Compile the application (`mvn install`, `gradle build`, or equivalent) | Artifact repository for dependency resolution |
| Container build | Build the container image and generate an SBOM | Image registry |
| Upload SBOM | Send the bill of materials to a vulnerability analyzer | Red Hat Trusted Profile Analyzer, or a substitute like Artifactory X-ray, Prisma, or Snyk |
| Vulnerability analysis | The analyzer compares the SBOM against known advisories and returns the findings | Same analyzer |
| Policy gate | A policy engine filters the findings to the must-fix set (for example, critical and high severity) | Conforma, or any policy engine |
| Image scan and deploy check | The container image is checked against security policies before deployment | Red Hat Advanced Cluster Security, or equivalent |

The pipeline is a sequence of deterministic steps. Each step has a clear input and output. The pipeline does not decide what to fix, and it does not open a pull request. Its output is a vulnerability report and a must-fix set.

## What it does not do

- It does not prioritize which CVE to fix first among the must-fix set.
- It does not change the application's `pom.xml` or `build.gradle`.
- It does not open a pull request.
- It does not generate tests.
- It does not tell the developer which version to use.

A person reads the must-fix list, researches each advisory, decides on a version, edits the manifest, runs the build, opens a pull request, and asks for review. That manual path is where the 30-to-90-day clock runs.

## Why it matters

Every execution model that adds agents shares this pipeline head. The scan, the SBOM, the policy gate, and the image checks are the same whether agents are involved or not. The agent tasks attach after the policy gate. Understanding the pipeline without agents is the prerequisite for understanding what agents change.

The Red Hat products shown here (Trusted Profile Analyzer, Conforma, Advanced Cluster Security) are examples. Customers can substitute their own tools at each step. The architecture is the sequence, not the product names.
