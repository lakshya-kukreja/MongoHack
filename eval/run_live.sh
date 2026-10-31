#!/usr/bin/env bash
# Live Evaluation Runner (eval/run_live.sh)
# Usage: ./eval/run_live.sh

set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
INCIDENT_ID="${INCIDENT_ID:-incident_001}"

echo "=========================================================="
echo "   INCIDENT TIMELINE INVESTIGATOR - LIVE EVALUATION RUN   "
echo "=========================================================="

# 1. Healthcheck probe
HEALTH_URL="${API_BASE_URL%/}/api/health"
echo -e "\n[*] Step 1: Checking backend health at ${HEALTH_URL}..."
if ! curl -sf "${HEALTH_URL}" > /dev/null 2>&1; then
    echo -e "\033[0;31m[FAIL] Cannot reach backend server at ${HEALTH_URL}!\033[0m"
    echo "Please start Person 1's backend in another terminal window:"
    echo "    cd backend && uvicorn app.main:app --reload --port 8000"
    exit 1
fi
echo -e "\033[0;32m[PASS] Backend is alive and reachable.\033[0m"

# 2. Seed data
echo -e "\n[*] Step 2: Seeding incident datasets (incident_001 & incident_000)..."
if [ -z "${MONGODB_URI:-}" ]; then
    python3 demo/seed.py --offline
else
    python3 demo/seed.py
fi
echo -e "\033[0;32m[PASS] Datasets loaded successfully.\033[0m"

# 3. Run Pytest in LIVE mode and generate report
echo -e "\n[*] Step 3: Running Pytest evaluation suite in LIVE mode..."
export ADAPTER_MODE="live"
export API_BASE_URL="${API_BASE_URL}"
export INCIDENT_ID="${INCIDENT_ID}"

python3 eval/run_live.py
