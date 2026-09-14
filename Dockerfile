# lw-agents — all-in-one sandbox image for OpenShell.
#
# Contains: ADK agent service + OpenCode + Maven + JDK 17 + glab/gh CLIs.
# Everything runs in one OpenShell sandbox. ADK agents are in-process Python.
# When they need code edits, ExecuteBashTool spawns opencode as a subprocess.
#
# Build:
#   podman build --platform linux/amd64 -t quay.io/<org>/lw-agents:latest .
#
# Run via OpenShell:
#   openshell sandbox create --name lw-agents \
#     --from ghcr.io/rrbanda/lw-agents:latest \
#     --forward 8080 --env GEMINI_API_KEY=... \
#     --policy sandbox-policy.yaml \
#     -- python -m google.adk.cli api_server --port 8080 app
#
# Run standalone:
#   podman run -p 8080:8080 --env-file .env ghcr.io/rrbanda/lw-agents:latest

FROM registry.access.redhat.com/ubi9/python-312@sha256:e95978812895b9abb2bdc109b501078da2a47c8dbb9fa23758af40ed50ab6023

ARG GLAB_VERSION=1.48.0
ARG GH_VERSION=2.63.2
ARG MAVEN_VERSION=3.9.9

USER 0

# OpenShell deps + Java + build tools
RUN dnf install -y --nodocs \
        iproute nftables \
        java-17-openjdk-headless \
        git jq tar gzip findutils \
    && dnf clean all && rm -rf /var/cache/dnf

# Maven (for build verification in remediation/test-gen tasks)
RUN curl -fsSL "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/${MAVEN_VERSION}/apache-maven-${MAVEN_VERSION}-bin.tar.gz" \
    -o /tmp/maven.tar.gz \
    && tar -xzf /tmp/maven.tar.gz -C /opt \
    && rm /tmp/maven.tar.gz

# OpenCode — coding agent called via ExecuteBashTool as a subprocess
RUN curl -fsSL https://opencode.ai/install | bash; \
    OPENCODE_BIN=$(find / -name opencode -type f -executable 2>/dev/null | head -1); \
    if [ -z "$OPENCODE_BIN" ]; then echo "ERROR: opencode not found" && exit 1; fi; \
    cp "$OPENCODE_BIN" /usr/local/bin/opencode && \
    opencode --version

# glab (GitLab CLI) for opening MRs and issues
RUN ARCH=$(uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/') \
    && curl -fsSL "https://gitlab.com/gitlab-org/cli/-/releases/v${GLAB_VERSION}/downloads/glab_${GLAB_VERSION}_linux_${ARCH}.tar.gz" \
    -o /tmp/glab.tar.gz \
    && tar -xzf /tmp/glab.tar.gz -C /usr/local bin/glab \
    && rm /tmp/glab.tar.gz

# gh (GitHub CLI) for opening PRs and issues
RUN ARCH=$(uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/') \
    && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.tar.gz" \
    -o /tmp/gh.tar.gz \
    && tar -xzf /tmp/gh.tar.gz -C /tmp \
    && cp "/tmp/gh_${GH_VERSION}_linux_${ARCH}/bin/gh" /usr/local/bin/gh \
    && rm -rf /tmp/gh.tar.gz "/tmp/gh_${GH_VERSION}_linux_${ARCH}"

# uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv@sha256:fc93e9ecd7218e9ec8fba117af89348eef8fd2463c50c13347478769aaedd0ce /uv /usr/local/bin/uv

# Application directory (OpenShell convention: /sandbox)
RUN install -d -o 1001 -g 0 -m 775 /sandbox
WORKDIR /sandbox

# Install Python dependencies to system Python
COPY --chown=1001:0 pyproject.toml uv.lock README.md ./
COPY --chown=1001:0 app/ ./app/
RUN uv pip install --python /opt/app-root/bin/python3 --no-cache .

# Copy skills (loaded at runtime via SkillToolset)
COPY --chown=1001:0 skills/ ./skills/

USER 1001

EXPOSE 8080

ENV PORT=8080 \
    PYTHONPATH=/sandbox \
    JAVA_HOME=/usr/lib/jvm/jre-17-openjdk \
    PATH="/opt/apache-maven-3.9.9/bin:/opt/app-root/bin:/usr/local/bin:${PATH}"

# ADK web serves both the playground UI + API — single entry point for everything
# OpenShell supervisor overrides CMD at runtime
CMD ["python", "-m", "google.adk.cli", "web", "--host", "0.0.0.0", "--port", "8080", "/sandbox"]
