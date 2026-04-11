# Sam the Sommelier - Dedicated Google Chat Bot Project

This Terraform configuration creates a dedicated GCP project for Sam the Sommelier's Google Chat bot.

Based on the middleware template from `slack-vertex-ai-middleware/docs/terraform-templates/agent-project/`.

## Why a Dedicated Project?

Google Chat API has a restriction: **only one Google Chat bot can be configured per GCP project**. To support multiple Google Chat bots (Sam the Sommelier, Growth Coach, etc.), each bot needs its own GCP project.

## Architecture

```
┌─────────────────────────────────────┐
│   vertex-ai-middleware-prod         │
│   (Middleware Project)              │
│                                     │
│   - Cloud Run (middleware)          │
│   - Firestore (config & sessions)   │
│   - Secret Manager (reads from Sam) │
│                                     │
└──────────────────────────────────────┘
                    │
                    │ (reads SA credentials)
                    ▼
┌─────────────────────────────────────┐
│   sam-sommelier-chat-prod           │
│   (Sam's Dedicated Project)         │
│                                     │
│   - Google Chat API                 │
│   - Secret Manager                  │
│     └─ sommelier-credentials        │
│   - Service Accounts:               │
│     └─ sam-sommelier (Chat bot)     │
│     └─ sam-sommelier-apis (Sheets)  │
│                                     │
└─────────────────────────────────────┘
```

## What This Creates

This Terraform configuration creates:

### Section 1: Common Infrastructure (All Agents)
- New GCP project
- Secret Manager API enabled
- Google Drive API enabled
- Google Sheets API enabled
- Service account for Google APIs (Drive, Sheets) - **share your Sheets with this SA**
- Organization policy override (allows SA key creation)

### Section 2: Slack Infrastructure (Active)
- Secret Manager secret for storing the Slack bot token

### Section 3: Google Chat Infrastructure (Active)
- Google Chat API enabled
- Service account for Google Chat bot operations
- IAM role `roles/chat.owner` for the bot SA
- Secret Manager secret for storing the bot's credentials

## Prerequisites

- GCP organization ID (Google Chat bots require a Workspace organization)
- Billing account ID
- Terraform 1.0+
- `gcloud` CLI authenticated
- Access to the middleware repository and project

## Setup Instructions

### 1. Configure Variables

```bash
cd google-chat-terraform
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars
```

Fill in your actual values:
- `project_id`: Globally unique ID (e.g., `sam-sommelier-chat-prod`)
- `organization_id`: Your GCP organization ID
- `billing_account`: Your billing account ID
- `bot_account_id`: Service account prefix (e.g., `sam-sommelier`)
- `secret_name`: Secret name (e.g., `sommelier-credentials`)

### 2. Deploy Infrastructure

```bash
terraform init
terraform plan
terraform apply
```

### 3. Follow Next Steps Output

After `terraform apply` completes, follow the instructions in the "next_steps" output. The key steps are:

#### 3a. Create Service Account Key

```bash
# Get the service account email from terraform output
export CHAT_SA_EMAIL=$(terraform output -raw chat_service_account_email)
export PROJECT_ID=$(terraform output -raw project_id)

# Create the key
gcloud iam service-accounts keys create sam-sommelier-sa-key.json \
  --iam-account=$CHAT_SA_EMAIL \
  --project=$PROJECT_ID
```

#### 3b. Store Key in Secret Manager

```bash
# Store in THIS project's Secret Manager (NOT the middleware project)
gcloud secrets versions add sommelier-credentials \
  --data-file=sam-sommelier-sa-key.json \
  --project=$PROJECT_ID

# Securely delete the key file
rm -f sam-sommelier-sa-key.json
```

#### 3b-slack. (Optional) Store Slack Bot Token

If you're using Slack, store the Slack bot token in the agent's project:

```bash
# Get your Slack bot token from https://api.slack.com/apps
# It starts with "xoxb-"
echo -n "xoxb-YOUR-SLACK-BOT-TOKEN" | gcloud secrets versions add sam-sommelier-slack-token \
  --data-file=- \
  --project=$PROJECT_ID
```

#### 3c. Grant Middleware Access to Secrets

**CRITICAL**: The middleware's Cloud Run service account needs permission to read the secrets in your agent's project. Without this, messages will fail with `403 Permission Denied` errors.

```bash
# Set up variables
export MIDDLEWARE_PROJECT_ID="vertex-ai-middleware-prod"
export MIDDLEWARE_PROJECT_NUMBER=$(gcloud projects describe $MIDDLEWARE_PROJECT_ID --format="value(projectNumber)")
export MIDDLEWARE_SA="${MIDDLEWARE_PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Grant access to Google Chat credentials secret
gcloud secrets add-iam-policy-binding sommelier-credentials \
  --member="serviceAccount:${MIDDLEWARE_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project=$PROJECT_ID

# If using Slack, also grant access to Slack token secret
gcloud secrets add-iam-policy-binding sam-sommelier-slack-token \
  --member="serviceAccount:${MIDDLEWARE_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project=$PROJECT_ID
```

**What this does**: Allows the middleware's service account to read the bot credentials from your agent's project so it can authenticate API calls to Google Chat and/or Slack.

#### 3d. Configure Google Chat Bot

1. Go to: https://console.cloud.google.com/apis/api/chat.googleapis.com/hangouts-chat?project=sam-sommelier-chat-prod
2. Click "Configuration"
3. Fill in bot details:
   - **Bot name**: Sam the Sommelier
   - **Avatar URL**: (optional)
   - **Description**: Your personal wine expert and sommelier
   - **Functionality**:
     - ✓ Receive 1:1 messages
     - ✓ Join spaces and group conversations
   - **Connection settings**: App URL
   - **Bot URL**: `https://slack-vertex-middleware-404939446326.us-central1.run.app/api/v1/google-chat/events`
   - **Permissions**: "Specific people and groups" (add test users)
4. Save

#### 3e. Enable Google Chat in Middleware

```bash
cd /path/to/slack-vertex-ai-middleware

# First, register Sam's agent if not already done
python scripts/deploy_agent.py \
  --agent-name "Sam the Sommelier" \
  --vertex-ai-agent-id "projects/YOUR_PROJECT/locations/us-central1/reasoningEngines/YOUR_ENGINE_ID"

# Note the agent's Firestore ID from the output, then enable Google Chat
python scripts/enable_google_chat_agent.py \
  --project vertex-ai-middleware-prod \
  --agent-id "YOUR_AGENT_FIRESTORE_ID" \
  --secret-name "sommelier-credentials" \
  --google-chat-project-id "sam-sommelier-chat-prod"
```

### 4. Share Google Sheets

Sam needs access to Google Sheets to analyze wine lists. Share your sheets with the **APIs service account** (NOT the Chat bot SA):

```bash
# Get the APIs service account email
terraform output apis_service_account_email
# Example output: sam-sommelier-apis@sam-sommelier-chat-prod.iam.gserviceaccount.com
```

Then:
1. Open your Google Sheet
2. Click "Share"
3. Add the APIs service account email
4. Give it "Editor" permissions

### 5. Test

1. Open Google Chat
2. Search for "Sam the Sommelier"
3. Send a test message: "Hello Sam!"

## Important Notes

### Two Service Accounts

This setup creates **two separate service accounts**:

1. **`sam-sommelier-apis@...`** (Google APIs SA)
   - Used by Sam's Reasoning Engine to access Google Drive and Sheets
   - **Share your Google Sheets with this SA**
   - No key needed (Vertex AI uses Workload Identity)

2. **`sam-sommelier@...`** (Google Chat bot SA)
   - Used by the middleware to send messages to Google Chat
   - Key stored in Secret Manager for middleware to use
   - **Do NOT share Sheets with this SA**

### Secret Location

The template stores the Google Chat credentials in **Sam's project** (not the middleware project). The middleware service account is granted `secretAccessor` permission to read it.

This is different from the previous approach where secrets were stored in the middleware project.

## Required Middleware Repository Access

This configuration integrates with the middleware system. You need access to:

- **Middleware Repository**: `slack-vertex-ai-middleware`
- **Middleware Project**: `vertex-ai-middleware-prod`
- **Required Scripts** (from middleware repo):
  - `scripts/deploy_agent.py` - Registers the agent with middleware
  - `scripts/enable_google_chat_agent.py` - Enables Google Chat platform for the agent

The middleware handles:
- Receiving Google Chat events
- Managing conversation sessions
- Routing messages to Sam's Vertex AI Reasoning Engine
- Streaming responses back to Google Chat users

## Adding More Bots

To add another Google Chat bot (e.g., Growth Coach):
1. Copy the middleware template to the new agent's repository
2. Update `terraform.tfvars` with the new bot's details
3. Run `terraform apply`
4. Follow the same setup steps
5. Use the middleware's scripts to register and enable the new bot

## Troubleshooting

### "Google Chat app not found" Error
- Verify the service account email in the Google Chat API configuration matches the one in Secret Manager
- Ensure the Google Chat API is enabled in Sam's project
- Check that the bot URL is correct

### "Insufficient permissions" or "403 Permission Denied" Error
This is the **most common error** when setting up a new bot. Check these items in order:

1. **Verify middleware has access to secrets** (most common issue):
   ```bash
   # Check Google Chat credentials
   gcloud secrets get-iam-policy sommelier-credentials --project=sam-sommelier-chat-prod

   # Check Slack token (if using Slack)
   gcloud secrets get-iam-policy sam-sommelier-slack-token --project=sam-sommelier-chat-prod
   ```

   You should see the middleware service account listed:
   ```
   - members:
     - serviceAccount:404939446326-compute@developer.gserviceaccount.com
     role: roles/secretmanager.secretAccessor
   ```

   If missing, run the commands from step 3c again.

2. **Verify the service account has `roles/chat.owner`** in Sam's project:
   ```bash
   gcloud projects get-iam-policy sam-sommelier-chat-prod \
     --flatten="bindings[].members" \
     --filter="bindings.members:serviceAccount:sam-sommelier@sam-sommelier-chat-prod.iam.gserviceaccount.com"
   ```

3. **Check that the service account key is properly stored** in Secret Manager:
   ```bash
   gcloud secrets versions list sommelier-credentials --project=sam-sommelier-chat-prod
   ```

### "Can't access Google Sheets" Error
- Make sure you shared the Sheets with the **APIs service account** (`sam-sommelier-apis@...`)
- NOT the Chat bot service account (`sam-sommelier@...`)
- Check that Drive and Sheets APIs are enabled in Sam's project

## Maintenance

- **Service Account Key Rotation**: Create a new key, update Secret Manager, delete old key
- **Project Billing**: Monitor costs in Sam's project (should be minimal, mostly API calls)
- **Access Control**: Manage who can chat with the bot via Google Chat API permissions

## Template Source

This configuration is based on the official middleware template:
`slack-vertex-ai-middleware/docs/terraform-templates/agent-project/`
