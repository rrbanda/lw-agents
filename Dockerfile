# lw-agents service image for OpenShell sandbox.
#
# BYOC (Bring Your Own Container) following the OpenShell pattern.
# The ADK agent service runs inside an OpenShell sandbox with
# policy-enforced network isolation (LLM, SCM, Maven Central access).
#
# Build:
#   podman build --platform linux/amd64 -t quay.io/<org>/lw-agents:latest .
#
# Run via OpenShell:
#   openshell sandbox create --name lw-agents \
#     --from quay.io/<org>/lw-agents:latest \
#     --forward 8080 \
#     -e GEMINI_API_KEY=... -e SCM_TOKEN=... \
#     -- adk api_server --port 8080 app
#
# Run standalone (without OpenShell):
#   podman run -p 8080:8080 --env-file .env quay.io/<org>/lw-agents:latest

FROM registry.access.redhat.com/ubi9/python-312@sha256:e95978812895b9abb2bdc109b501078da2a47c8dbb9fa23758af40ed50ab6023
WORKDIR /opt/app-root/src

USER 0

# OpenShell deps (iproute for network namespace, nftables for bypass detection)
RUN dnf install -y --nodocs iproute nftables && dnf clean all && rm -rf /var/cache/dnf

# uv for fast reproducible dependency installs (pinned digest)
COPY --from=ghcr.io/astral-sh/uv@sha256:fc93e9ecd7218e9ec8fba117af89348eef8fd2463c50c13347478769aaedd0ce /uv /usr/local/bin/uv

# Install dependencies from lockfile (reproducible builds)
COPY pyproject.toml uv.lock ./
COPY app/ ./app/
ENV UV_PROJECT_ENVIRONMENT=/opt/app-root
RUN uv sync --frozen --no-dev

# Copy skills (loaded at runtime via SkillToolset)
COPY skills/ ./skills/

# Ensure app directory is owned by default non-root user (UID 1001)
RUN chown -R 1001:0 /opt/app-root/src && chmod -R g=u /opt/app-root/src

# Switch to non-root (OpenShift standard UID)
USER 1001

EXPOSE 8080

ENV PORT=8080 \
    PYTHONPATH=/opt/app-root/src

# NOTE: When running in OpenShell, the supervisor replaces CMD at runtime.
# Pass the start command explicitly: openshell sandbox create ... -- adk api_server --port 8080 app
CMD ["adk", "api_server", "--port", "8080", "app"]
