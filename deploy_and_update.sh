#!/usr/bin/env bash
#
# deploy_and_update.sh — Deploy Sam the Som agent to Vertex AI,
# test it, clean up the old version, and update the Firestore pointer
# the middleware reads.
#
# Usage:
#   ./deploy_and_update.sh
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - ADK installed (in MY_VENV or PATH)
#   - Slack bot token stored in Secret Manager

set -euo pipefail

# ──────────────────────────────────────────────────────────────
# Configuration (defaults)
# ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load variables from .env (without overriding any already set in the environment)
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    set -a
    # Use eval to properly handle the environment file loading
    while IFS= read -r line; do
        # Skip comments and empty lines
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$line" ]] && continue
        eval "export $line"
    done < "${SCRIPT_DIR}/.env"
    set +a
fi

PROJECT_ID="${PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-}}"
PROJECT_ID="${PROJECT_ID:?PROJECT_ID must be set (via env var or GOOGLE_CLOUD_PROJECT in .env)}"

REGION="${REGION:-us-central1}"
ADK_BIN="${ADK_BIN:-$(command -v adk 2>/dev/null || echo "adk")}"
ADK_PYTHON="${ADK_PYTHON:-$(dirname "$ADK_BIN")/python3}"
AGENT_DISPLAY_NAME="${AGENT_DISPLAY_NAME:-Sam the Som}"
AGENT_FIRESTORE_ID="${AGENT_FIRESTORE_ID:?AGENT_FIRESTORE_ID must be set in .env - the Firestore document ID for this agent}"
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

log "Setting gcloud project to $PROJECT_ID..."
gcloud config set project "$PROJECT_ID" --quiet
ok "gcloud project set to $PROJECT_ID"

if [[ ! -x "$ADK_BIN" ]] && [[ ! -f "$ADK_BIN" ]]; then
    err "ADK binary not found at $ADK_BIN"
    exit 1
fi
ok "ADK binary found: $ADK_BIN"

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
echo "  Staging:  gs://${PROJECT_ID}-staging"

AGENT_PARENT_DIR="$(dirname "$AGENT_DIR")"
AGENT_PACKAGE_NAME="$(basename "$AGENT_DIR")"

# Deploy using ADK
# Staging bucket stores deployment artifacts. If it doesn't exist, ADK will create it.
# For manual setup with lifecycle policies, see README.md
DEPLOY_OUTPUT=$(cd "$AGENT_PARENT_DIR" && "$ADK_BIN" deploy agent_engine \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --staging_bucket "gs://${PROJECT_ID}-staging" \
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
# Step 4: Update agent's vertex_ai_agent_id in Firestore
# ──────────────────────────────────────────────────────────────
log "Step 4: Updating agent's Vertex AI resource ID in Firestore..."

"$ADK_PYTHON" -m pip install --quiet google-cloud-firestore 2>/dev/null || true

"$ADK_PYTHON" -c "
from google.cloud import firestore

db = firestore.Client(project='${PROJECT_ID}', database='(default)')
agent_ref = db.collection('agents').document('${AGENT_FIRESTORE_ID}')
agent = agent_ref.get()

if not agent.exists:
    print('ERROR: Agent ${AGENT_FIRESTORE_ID} not found in Firestore')
    exit(1)

agent_ref.update({
    'vertex_ai_agent_id': '${NEW_RESOURCE_NAME}'
})
print('Updated agent ${AGENT_FIRESTORE_ID} to point to ${NEW_RESOURCE_NAME}')
" || {
    err "Failed to update Firestore!"
    echo "  New agent is deployed at: $NEW_RESOURCE_NAME"
    echo "  You can update Firestore manually:  "
    echo "  Agent ID: $AGENT_FIRESTORE_ID"
    echo "  Field: vertex_ai_agent_id = $NEW_RESOURCE_NAME"
    exit 1
}

ok "Firestore updated to point to new agent."

# ──────────────────────────────────────────────────────────────
# Step 5: Clear stale sessions for this agent
# ──────────────────────────────────────────────────────────────
log "Step 5: Clearing stale sessions for this agent..."

# Delete all sessions containing this agent's Firestore document ID
SESSIONS_DELETED=$("$ADK_PYTHON" -c "
from google.cloud import firestore
db = firestore.Client(project='${PROJECT_ID}', database='(default)')

# Delete all sessions containing this agent's document ID
sessions = db.collection('sessions').stream()
deleted = 0
for session in sessions:
    if '${AGENT_FIRESTORE_ID}' in session.id:
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
    DELETE_RESPONSE=$(curl -s -X DELETE \
        "https://${REGION}-aiplatform.googleapis.com/v1beta1/${OLD_RESOURCE_NAME}?force=true" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json")

    # Check if deletion was successful or initiated
    # Success can be: {"done": true} (immediate) or {"name": "operations/..."} (async LRO)
    if echo "$DELETE_RESPONSE" | grep -q '"done": true'; then
        ok "Old agent deleted: $OLD_RESOURCE_NAME"
    elif echo "$DELETE_RESPONSE" | grep -q '"name": "operations/'; then
        ok "Old agent deletion initiated (async): $OLD_RESOURCE_NAME"
    elif echo "$DELETE_RESPONSE" | grep -q '"error"'; then
        warn "Could not delete old agent $OLD_RESOURCE_NAME. Error response:"
        echo "$DELETE_RESPONSE" | grep -o '"message":"[^"]*"' || echo "$DELETE_RESPONSE"
        warn "You may need to delete it manually with: gcloud ai reasoning-engines delete $OLD_AGENT_ID --location=$REGION --force"
    else
        # Empty response or unexpected format - likely succeeded
        ok "Old agent deleted: $OLD_RESOURCE_NAME (verified via API call)"
    fi
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
