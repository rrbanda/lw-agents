# lw-agents service image for OpenShell sandbox.
#
# BYOC (Bring Your Own Container) following the OpenShell pattern:
# https://github.com/NVIDIA/OpenShell/tree/main/examples/bring-your-own-container
#
# Build:
#   podman build --platform linux/amd64 -t quay.io/<org>/lw-agents:latest .
#
# Run via OpenShell:
#   openshell sandbox create --name lw-agents \
#     --from quay.io/<org>/lw-agents:latest \
#     --forward 8080 --env GEMINI_API_KEY=... \
#     -- python -m google.adk.cli api_server --port 8080 app
#
# Run standalone (without OpenShell):
#   podman run -p 8080:8080 --env-file .env quay.io/<org>/lw-agents:latest

FROM registry.access.redhat.com/ubi9/python-312@sha256:e95978812895b9abb2bdc109b501078da2a47c8dbb9fa23758af40ed50ab6023

USER 0

# OpenShell deps (iproute for network namespace, nftables for bypass detection)
RUN dnf install -y --nodocs iproute nftables && dnf clean all && rm -rf /var/cache/dnf

# uv for fast reproducible dependency installs (pinned digest)
COPY --from=ghcr.io/astral-sh/uv@sha256:fc93e9ecd7218e9ec8fba117af89348eef8fd2463c50c13347478769aaedd0ce /uv /usr/local/bin/uv

# Application directory (OpenShell convention: /sandbox)
RUN install -d -o 1001 -g 0 -m 775 /sandbox
WORKDIR /sandbox

# Install dependencies using the image's system Python
COPY --chown=1001:0 pyproject.toml uv.lock README.md ./
COPY --chown=1001:0 app/ ./app/
RUN uv pip install --python /opt/app-root/bin/python3 --no-cache .

# Copy skills (loaded at runtime via SkillToolset)
COPY --chown=1001:0 skills/ ./skills/

# Switch to non-root (OpenShift standard UID)
USER 1001

EXPOSE 8080

ENV PORT=8080 \
    PYTHONPATH=/sandbox \
    PATH="/opt/app-root/bin:${PATH}"

# NOTE: OpenShell's supervisor replaces CMD at runtime.
# Pass the start command explicitly via: openshell sandbox create ... -- python -m google.adk.cli api_server --port 8080 app
CMD ["python", "-m", "google.adk.cli", "api_server", "--port", "8080", "app"]
