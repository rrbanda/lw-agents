# ADK agent service — containerized for OpenShift deployment.
# Serves via ADK's built-in adk api_server (no custom FastAPI needed).
#
# Build:
#   podman build -t quay.io/<org>/lw-agents:v1.0.0 .
#   podman push quay.io/<org>/lw-agents:v1.0.0
#
# Run locally:
#   podman run -p 8080:8080 --env-file .env quay.io/<org>/lw-agents:v1.0.0

FROM python:3.11-slim

# System deps for OpenCode and Maven (if running coding tasks in-container)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git jq ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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

# Use ADK's built-in server — it discovers root_agent from app/agent.py
CMD ["adk", "api_server", "--port", "8080", "app"]
