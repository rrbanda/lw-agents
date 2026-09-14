# ADK agent service — containerized for OpenShift deployment.
# Serves via ADK's built-in adk api_server (no custom FastAPI needed).
#
# Contains: Python 3.11 + ADK + OpenCode (coding agent) + glab/gh (SCM CLIs)
#           + Maven (for build verification) + git
#
# Build:
#   podman build --platform linux/amd64 -t quay.io/<org>/lw-agents:v1.0.0 .
#   podman push quay.io/<org>/lw-agents:v1.0.0
#
# Run locally:
#   podman run -p 8080:8080 --env-file .env quay.io/<org>/lw-agents:v1.0.0

FROM python:3.11-slim

ARG GLAB_VERSION=1.48.0
ARG GH_VERSION=2.63.2
ARG MAVEN_VERSION=3.9.9

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git jq ca-certificates tar gzip findutils \
    openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# Maven (for build verification in remediation/test-gen tasks)
RUN curl -fsSL "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/${MAVEN_VERSION}/apache-maven-${MAVEN_VERSION}-bin.tar.gz" \
    -o /tmp/maven.tar.gz \
    && tar -xzf /tmp/maven.tar.gz -C /opt \
    && ln -s "/opt/apache-maven-${MAVEN_VERSION}/bin/mvn" /usr/local/bin/mvn \
    && rm /tmp/maven.tar.gz

# OpenCode — open-source coding agent (headless mode for ExecuteBashTool)
RUN curl -fsSL https://opencode.ai/install | bash \
    && opencode --version

# glab (GitLab CLI) for opening MRs and issues
RUN ARCH=$(dpkg --print-architecture | sed 's/amd64/amd64/; s/arm64/arm64/') \
    && curl -fsSL "https://gitlab.com/gitlab-org/cli/-/releases/v${GLAB_VERSION}/downloads/glab_${GLAB_VERSION}_linux_${ARCH}.tar.gz" \
    -o /tmp/glab.tar.gz \
    && tar -xzf /tmp/glab.tar.gz -C /usr/local bin/glab \
    && rm /tmp/glab.tar.gz

# gh (GitHub CLI) for opening PRs and issues
RUN ARCH=$(dpkg --print-architecture | sed 's/amd64/amd64/; s/arm64/arm64/') \
    && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.tar.gz" \
    -o /tmp/gh.tar.gz \
    && tar -xzf /tmp/gh.tar.gz -C /tmp \
    && cp "/tmp/gh_${GH_VERSION}_linux_${ARCH}/bin/gh" /usr/local/bin/gh \
    && rm -rf /tmp/gh.tar.gz "/tmp/gh_${GH_VERSION}_linux_${ARCH}"

# Install uv for fast Python dependency management
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY app/ app/
COPY skills/ skills/

# Install Python dependencies
RUN uv pip install --system --no-cache .

# ADK api_server serves on port 8080 by default
EXPOSE 8080

# Non-root user for OpenShift compatibility
RUN useradd -m -s /bin/bash agent \
    && chown -R agent:agent /app
USER agent

# Use ADK's built-in server — discovers root_agent from app/agent.py
CMD ["adk", "api_server", "--port", "8080", "app"]
