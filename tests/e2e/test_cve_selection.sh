#!/usr/bin/env bash
# End-to-end test: start agent server, send a CVE selection request, verify response.
# Requires: GEMINI_API_KEY set in .env or environment.
#
# Usage: bash tests/e2e/test_cve_selection.sh
set -euo pipefail

PORT=8090
FIXTURE_DIR="$(cd "$(dirname "$0")/fixtures/case1" && pwd)"

echo "=== Starting ADK agent server on port ${PORT} ==="
uv run adk api_server --port "${PORT}" app &
SERVER_PID=$!
trap "kill ${SERVER_PID} 2>/dev/null || true" EXIT

echo "Waiting for server..."
for i in $(seq 1 30); do
    if curl -sf "http://localhost:${PORT}/list-apps" >/dev/null 2>&1; then
        echo "Server ready."
        break
    fi
    sleep 1
done

echo ""
echo "=== Sending CVE selection request ==="
RESPONSE=$(curl -sf -X POST "http://localhost:${PORT}/run" \
    -H "Content-Type: application/json" \
    -d "{
        \"app_name\": \"app\",
        \"user_id\": \"e2e-test\",
        \"new_message\": {
            \"role\": \"user\",
            \"parts\": [{
                \"text\": \"Select the best CVE to remediate. Workspace path: ${FIXTURE_DIR}\"
            }]
        }
    }" 2>&1) || {
    echo "ERROR: Agent call failed"
    echo "${RESPONSE}"
    exit 1
}

echo ""
echo "=== Agent Response ==="
echo "${RESPONSE}" | python3 -m json.tool 2>/dev/null || echo "${RESPONSE}"

echo ""
echo "=== Test Complete ==="
echo "Review the response above. The agent should have:"
echo "  1. Called load_skill to read the cve-triage skill"
echo "  2. Called list_must_fix_cves to get the CVE set"
echo "  3. Called lookup_cve_detail for CVE-2024-29025"
echo "  4. Called parse_maven_purl to extract coordinates"
echo "  5. Called check_version_exists to verify the fix"
echo "  6. Reported a selection with all 6 fields"
