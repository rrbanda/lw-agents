# Lightwell Detail Reference

## Workshop Fixture: LW-DEMO-0002

The scored lab uses this advisory as the demonstration case:

| Field | Value |
|-------|-------|
| Advisory | `LW-DEMO-0002` |
| Coordinate | `org.apache.commons:commons-lang3:3.14.0.rhlw-00001` |
| Affected version | `3.14.0` |
| Demo OSV URL | `https://packages.redhat.com/api/pulp-content/public-lightwell-demo/osv/java/remediated/LW-DEMO-0002.json` |

### Wrong Answers for the LW-DEMO-0002 Case

| Wrong Answer | Why It's Wrong |
|-------------|----------------|
| `3.18.0` | A newer Central line. That's freshness, not remediation |
| `3.14.0` | The affected version. Claiming it is fixed is wrong |
| `3.14.0.rhlw-00000` | The pre-pin marker, not the fixed event |
| A coordinate from `LW-DEMO-0001` | A different advisory for a different package |

## Agent Tool Usage for Lightwell

When the agent encounters a Lightwell advisory or `.rhlw` version:

1. **`lookup_lightwell_osv(advisory_id)`** — Fetches the advisory from
   the Lightwell OSV feed. Returns the fixed coordinate, affected
   ranges, and advisory metadata. This is the VERSION AUTHORITY.

2. **`check_lightwell_version_exists(group_id, artifact_id, version)`**
   — HEAD request to the Lightwell repository to verify the `.rhlw`
   artifact exists. Central does NOT have these versions.

3. **`check_version_exists_smart(group_id, artifact_id, version)`**
   — Auto-routes: detects `.rhlw-` or `+rhlw.` suffix → Lightwell
   repository. All other versions → Maven Central.

4. **`list_lightwell_advisories()`** — Reads the PULP_MANIFEST index
   to list all published advisories and their checksums.

## Resolution Chain

The application's build resolves the Lightwell coordinate from an
internal artifact repository (Artifactory, Nexus) that proxies
`packages.redhat.com`. The agent changes the manifest (`pom.xml`).
The repository manager performs the fetch. The agent does NOT paste
tokens into the project to make the fetch work.

## What Sits Beside Lightwell

| Product | Layer | Relation to Lightwell |
|---------|-------|-----------------------|
| RHEL, OpenShift, ACS | OS and platform | Complementary — platform patches cover a different layer |
| Red Hat Hardened Images | Container foundation | The base image, not an application library fix |
| RHTPA (Trusted Profile Analyzer) | SBOM analysis | The scanner that produces the must-fix list |
| Lightwell Lens | Coverage report | Upload SBOM, see catalog coverage. Not a programmatic API |
| IBM LSOS | End-of-life Java frameworks | A different offer |
