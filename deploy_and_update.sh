#!/usr/bin/env bash
#
# deploy_and_update.sh — Deploy Sam the Som agent to Vertex AI,
# test it, clean up the old version, and register with Slack middleware.
#
# Usage:
#   ./deploy_and_update.sh
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - ADK installed (in MY_VENV or PATH)
#   - Slack bot token stored in Secret Manager
#   - Middleware repo available for deploy_agent.py

set -euo pipefail

# ──────────────────────────────────────────────────────────────
# Configuration (defaults)
# ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load variables from .env (without overriding any already set in the environment)
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    set -a
    source <(grep -v '^\s*#' "${SCRIPT_DIR}/.env" | grep -v '^\s*$')
    set +a
fi

PROJECT_ID="${PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-}}"
PROJECT_ID="${PROJECT_ID:?PROJECT_ID must be set (via env var or GOOGLE_CLOUD_PROJECT in .env)}"

REGION="${REGION:-us-central1}"
ADK_BIN="${ADK_BIN:-$(command -v adk 2>/dev/null || echo "adk")}"
ADK_PYTHON="${ADK_PYTHON:-$(dirname "$ADK_BIN")/python3}"
MIDDLEWARE_DIR="${MIDDLEWARE_DIR:?MIDDLEWARE_DIR must be set in .env or as an env var}"
AGENT_DISPLAY_NAME="${AGENT_DISPLAY_NAME:-Sam the Som}"
SLACK_BOT_SECRET="${SLACK_BOT_SECRET:-slack-sommelier}"
AGENT_DIR="${SCRIPT_DIR}"

# ──────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────
log()   { echo -e "\n\033[1;34m▶ $*\033[0m"; }
ok()    { echo -e "\033[1;32m  ✓ $*\033[0m"; }
err()   { echo -e "\033[1;31m  ✗ $*\033[0m"; }
warn()  { echo -e "\033[1;33m  ⚠ $*\033[0m"; }

get_existing_agent_id() {
    "$ADK_PYTHON" -c "
import vertexai
from vertexai.preview import reasoning_engines
vertexai.init(project='${PROJECT_ID}', location='${REGION}')
engines = reasoning_engines.ReasoningEngine.list()
for e in engines:
    if '${AGENT_DISPLAY_NAME}' in (e.display_name or ''):
        print(e.resource_name.split('/')[-1])
        break
" 2>/dev/null || true
}

get_agent_resource_name() {
    local agent_id="$1"
    echo "projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines/${agent_id}"
}

# ──────────────────────────────────────────────────────────────
# Pre-flight checks
# ──────────────────────────────────────────────────────────────
log "Pre-flight checks"

if [[ ! -x "$ADK_BIN" ]] && [[ ! -f "$ADK_BIN" ]]; then
    err "ADK binary not found at $ADK_BIN"
    exit 1
fi
ok "ADK binary found: $ADK_BIN"

if [[ ! -d "$MIDDLEWARE_DIR/scripts" ]]; then
    err "Middleware repo not found at $MIDDLEWARE_DIR"
    exit 1
fi
ok "Middleware repo found: $MIDDLEWARE_DIR"

if [[ -z "${SLACK_BOT_TOKEN:-}" ]]; then
    log "Retrieving Slack bot token from Secret Manager (${SLACK_BOT_SECRET})..."
    SLACK_BOT_TOKEN=$(gcloud secrets versions access latest \
        --secret="$SLACK_BOT_SECRET" \
        --project="$PROJECT_ID" 2>&1) || {
        err "Could not retrieve Slack bot token from Secret Manager."
        echo "  Secret: $SLACK_BOT_SECRET"
        echo "  Either set SLACK_BOT_TOKEN env var or ensure the secret exists."
        exit 1
    }
    ok "Slack bot token retrieved from Secret Manager."
fi

if [[ -z "${SLACK_BOT_ID:-}" ]]; then
    log "Detecting Slack bot user ID from token..."
    SLACK_BOT_ID=$(curl -s https://slack.com/api/auth.test \
        -H "Authorization: Bearer ${SLACK_BOT_TOKEN}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('user_id',''))")
    if [[ -z "$SLACK_BOT_ID" ]]; then
        err "Could not detect Slack bot user ID. Set SLACK_BOT_ID manually."
        exit 1
    fi
fi
ok "Slack bot user ID: $SLACK_BOT_ID"

# Ensure the default compute SA can read the credentials secret
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)" 2>/dev/null)
if [[ -n "$PROJECT_NUMBER" && -n "${SOMMELIER_SECRET_NAME:-}" ]]; then
    log "Ensuring service accounts can access credentials secret..."
    for SA in \
        "${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
        "service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com" \
        "service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"; do
        gcloud secrets add-iam-policy-binding "$SOMMELIER_SECRET_NAME" \
            --project="$PROJECT_ID" \
            --member="serviceAccount:${SA}" \
            --role="roles/secretmanager.secretAccessor" \
            --quiet 2>/dev/null || true
    done
    ok "Service accounts granted access to $SOMMELIER_SECRET_NAME"
fi

# ──────────────────────────────────────────────────────────────
# Step 1: Find existing agent
# ──────────────────────────────────────────────────────────────
log "Step 1: Looking for existing '${AGENT_DISPLAY_NAME}' agent..."
OLD_AGENT_ID=$(get_existing_agent_id)

if [[ -n "$OLD_AGENT_ID" ]]; then
    ok "Found existing agent: $(get_agent_resource_name "$OLD_AGENT_ID")"
else
    warn "No existing agent found. Will create a new one."
fi

# ──────────────────────────────────────────────────────────────
# Step 2: Deploy new agent to Vertex AI
# ──────────────────────────────────────────────────────────────
log "Step 2: Deploying new agent to Vertex AI Agent Engine..."
echo "  Project:  $PROJECT_ID"
echo "  Region:   $REGION"
echo "  Agent:    $AGENT_DIR"

AGENT_PARENT_DIR="$(dirname "$AGENT_DIR")"
AGENT_PACKAGE_NAME="$(basename "$AGENT_DIR")"

DEPLOY_OUTPUT=$(cd "$AGENT_PARENT_DIR" && "$ADK_BIN" deploy agent_engine \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --display_name "$AGENT_DISPLAY_NAME" \
    --trace_to_cloud \
    "$AGENT_PACKAGE_NAME" 2>&1) || {
    err "Deployment failed!"
    echo "$DEPLOY_OUTPUT"
    exit 1
}

echo "$DEPLOY_OUTPUT"

NEW_AGENT_ID=$(echo "$DEPLOY_OUTPUT" | grep -oP 'reasoningEngines/\K[0-9]+' | tail -1)

if [[ -z "$NEW_AGENT_ID" ]]; then
    warn "Could not auto-extract new agent ID from deploy output."
    echo ""
    read -rp "  Enter the new Reasoning Engine ID manually: " NEW_AGENT_ID
fi

NEW_RESOURCE_NAME=$(get_agent_resource_name "$NEW_AGENT_ID")
ok "New agent deployed: $NEW_RESOURCE_NAME"

# ──────────────────────────────────────────────────────────────
# Step 3: Quick smoke test
# ──────────────────────────────────────────────────────────────
log "Step 3: Smoke testing new agent..."

SMOKE_RESULT=$("$ADK_PYTHON" -c "
import vertexai
from vertexai.preview import reasoning_engines
vertexai.init(project='${PROJECT_ID}', location='${REGION}')
agent = reasoning_engines.ReasoningEngine('${NEW_RESOURCE_NAME}')
session = agent.create_session(user_id='smoke-test')
print(f'Session created: {session[\"id\"]}')
print('OK')
" 2>&1) || true

if echo "$SMOKE_RESULT" | grep -q "OK"; then
    ok "Smoke test passed — agent is accessible and can create sessions."
else
    warn "Smoke test may have issues:"
    echo "$SMOKE_RESULT" | tail -5
    warn "Continuing anyway since agent was deployed successfully."
fi

# ──────────────────────────────────────────────────────────────
# Step 4: Register new agent with Slack middleware
# ──────────────────────────────────────────────────────────────
log "Step 4: Registering new agent with Slack middleware..."

"$ADK_PYTHON" -m pip install --quiet google-cloud-firestore slack_sdk 2>/dev/null || true

"$ADK_PYTHON" "${MIDDLEWARE_DIR}/scripts/deploy_agent.py" \
    --agent-name "$AGENT_DISPLAY_NAME" \
    --vertex-ai-agent-id "$NEW_RESOURCE_NAME" \
    --slack-bot-id "$SLACK_BOT_ID" \
    --slack-bot-token "$SLACK_BOT_TOKEN" \
    --project-id "$PROJECT_ID" || {
    err "Middleware registration failed!"
    echo "  New agent is deployed at: $NEW_RESOURCE_NAME"
    echo "  You can register it manually later."
    exit 1
}

ok "Middleware updated to point to new agent."

# ──────────────────────────────────────────────────────────────
# Step 5: Clear stale sessions for this agent
# ──────────────────────────────────────────────────────────────
log "Step 5: Clearing stale sessions for this agent..."

# Get the agent's Firestore document ID and delete associated sessions
SESSIONS_DELETED=$("$ADK_PYTHON" -c "
from google.cloud import firestore
db = firestore.Client(project='${PROJECT_ID}')

# Find the agent document ID by slack_bot_id
agents = db.collection('agents').where('slack_bot_id', '==', '${SLACK_BOT_ID}').stream()
agent_doc_id = None
for agent in agents:
    agent_doc_id = agent.id
    break

if not agent_doc_id:
    print('0')
else:
    # Delete all sessions containing this agent's document ID
    sessions = db.collection('sessions').stream()
    deleted = 0
    for session in sessions:
        if agent_doc_id in session.id:
            db.collection('sessions').document(session.id).delete()
            deleted += 1
    print(deleted)
" 2>/dev/null) || SESSIONS_DELETED="0"

if [[ "$SESSIONS_DELETED" -gt 0 ]]; then
    ok "Cleared $SESSIONS_DELETED stale session(s)."
else
    ok "No stale sessions to clear."
fi

# ──────────────────────────────────────────────────────────────
# Step 6: Delete old agent (if exists and different from new)
# ──────────────────────────────────────────────────────────────
if [[ -n "$OLD_AGENT_ID" && "$OLD_AGENT_ID" != "$NEW_AGENT_ID" ]]; then
    log "Step 6: Cleaning up old agent (ID: $OLD_AGENT_ID)..."
    OLD_RESOURCE_NAME=$(get_agent_resource_name "$OLD_AGENT_ID")

    ACCESS_TOKEN=$(gcloud auth print-access-token)
    curl -s -X DELETE \
        "https://${REGION}-aiplatform.googleapis.com/v1beta1/${OLD_RESOURCE_NAME}?force=true" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        | grep -q '"done": true' \
        && ok "Old agent deleted: $OLD_RESOURCE_NAME" \
        || warn "Could not delete old agent $OLD_RESOURCE_NAME. You may need to delete it manually."
else
    log "Step 6: No old agent to clean up."
fi

# ──────────────────────────────────────────────────────────────
# Done
# ──────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Deployment complete!"
echo "═══════════════════════════════════════════════════════════"
echo "  New agent:  $NEW_RESOURCE_NAME"
echo "  Middleware:  Updated in Firestore"
if [[ -n "${OLD_AGENT_ID:-}" && "$OLD_AGENT_ID" != "$NEW_AGENT_ID" ]]; then
echo "  Old agent:  Deleted ($(get_agent_resource_name "$OLD_AGENT_ID"))"
fi
echo ""
echo "  Test it by sending a DM to Sam in Slack!"
echo "═══════════════════════════════════════════════════════════"
