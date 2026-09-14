# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in lw-agents, please report it
responsibly. Do NOT open a public issue.

**Email:** secalert@redhat.com

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Response Timeline

- **Acknowledgment:** within 2 business days
- **Initial assessment:** within 5 business days
- **Fix or mitigation:** based on severity

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Security Practices

This project implements multiple security layers:

- **SafetyPlugin** -- LLM-as-judge content filtering at the Runner level
- **RedactionPlugin** -- 3-layer secret masking on all tool results
- **Pre-gate validation** -- rejects malformed input before model spend
- **Post-gate validation** -- blocks forbidden patterns in diffs (nosec, SuppressWarnings, verify=False)
- **Fail-closed scoring** -- every error path defaults to rejection
- **Tool confirmation** -- PR creation requires explicit confirmation

See [ADR-006](docs/adr/006-safety-at-runner-level.md) through
[ADR-009](docs/adr/009-output-redaction.md) for security design decisions.
