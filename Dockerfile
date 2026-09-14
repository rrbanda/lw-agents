# lw-agents service image — ADK agent on UBI9 for OpenShift.
#
# This is the agent service only. OpenCode, Maven, and SCM CLIs
# run in a separate OpenShell sandbox (see Containerfile.openshell).
#
# Build:
#   podman build --platform linux/amd64 -t quay.io/<org>/lw-agents:latest .
#
# Run locally:
#   podman run -p 8080:8080 --env-file .env quay.io/<org>/lw-agents:latest

# --- Base: Red Hat UBI9 Python 3.12 ---
FROM registry.access.redhat.com/ubi9/python-312@sha256:e95978812895b9abb2bdc109b501078da2a47c8dbb9fa23758af40ed50ab6023
WORKDIR /opt/app-root/src

# Switch to root for installs
USER 0

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

# ADK's built-in server — discovers root_agent from app/agent.py
CMD ["adk", "api_server", "--port", "8080", "app"]
