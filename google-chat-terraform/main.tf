# Sam the Sommelier - Dedicated Infrastructure
#
# This creates dedicated GCP infrastructure for Sam the Sommelier.
# Based on the middleware template with multi-platform support.
#
# STRUCTURE:
# Section 1: Common infrastructure (all agents)
# Section 2: Slack-specific infrastructure (UNCOMMENTED - Sam uses Slack)
# Section 3: Google Chat-specific infrastructure (UNCOMMENTED - Sam uses Google Chat)
# Section 4: Telegram-specific infrastructure (UNCOMMENTED - Sam uses Telegram)

terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  billing_project = var.project_id
  region          = var.region
}

# ==============================================================================
# SECTION 1: COMMON INFRASTRUCTURE (Required for all agents)
# ==============================================================================

# Reference the existing GCP Project (already created)
data "google_project" "agent_project" {
  project_id = var.project_id
}

# Use the existing project for subsequent resources
provider "google" {
  alias   = "agent"
  project = data.google_project.agent_project.project_id
  region  = var.region
}

# Enable Secret Manager API (used by all platforms)
resource "google_project_service" "secretmanager" {
  project = data.google_project.agent_project.project_id
  service = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

# Enable Google Drive API (Sam uses Google Drive)
resource "google_project_service" "drive" {
  project = data.google_project.agent_project.project_id
  service = "drive.googleapis.com"
  disable_on_destroy = false
}

# Enable Google Sheets API (Sam uses Google Sheets)
resource "google_project_service" "sheets" {
  project = data.google_project.agent_project.project_id
  service = "sheets.googleapis.com"
  disable_on_destroy = false
}

# Enable Google Docs API (Sam uses Google Docs for memory)
resource "google_project_service" "docs" {
  project = data.google_project.agent_project.project_id
  service = "docs.googleapis.com"
  disable_on_destroy = false
}

# Service Account for Google APIs (Drive, Sheets, Docs, etc.)
# This SA will be used by Sam to access Google Drive and Sheets
resource "google_service_account" "agent_apis" {
  project      = data.google_project.agent_project.project_id
  account_id   = "${var.bot_account_id}-apis"
  display_name = "${var.bot_name} Google APIs"
  description  = "Service account for ${var.bot_name} to access Google APIs (Drive, Sheets, etc.)"

  depends_on = [
    google_project_service.drive,
    google_project_service.sheets
  ]
}

# Allow service account key creation for this project
# This overrides the organization policy that blocks key creation
resource "google_project_organization_policy" "allow_sa_key_creation" {
  project    = data.google_project.agent_project.project_id
  constraint = "constraints/iam.disableServiceAccountKeyCreation"

  boolean_policy {
    enforced = false
  }
}

# ==============================================================================
# SECTION 2: SLACK-SPECIFIC INFRASTRUCTURE
# UNCOMMENTED - Sam uses Slack
# ==============================================================================

# Slack Bot Token Secret
resource "google_secret_manager_secret" "slack_bot_token" {
  project   = data.google_project.agent_project.project_id
  secret_id = "${var.bot_account_id}-slack-token"

  replication {
    auto {}
  }

  depends_on = [
    google_project_service.secretmanager
  ]
}

# Note: The Slack bot token must be added manually after terraform apply:
# echo -n "xoxb-YOUR-SLACK-BOT-TOKEN" | gcloud secrets versions add ${var.bot_account_id}-slack-token \
#   --data-file=- --project=${var.project_id}

# ==============================================================================
# SECTION 3: GOOGLE CHAT-SPECIFIC INFRASTRUCTURE
# UNCOMMENTED - Sam uses Google Chat
# ==============================================================================

# Enable Google Chat API
resource "google_project_service" "chat" {
  project = data.google_project.agent_project.project_id
  service = "chat.googleapis.com"
  disable_on_destroy = false
}

# Service Account for Google Chat bot
# This SA will be used for Google Chat API calls (sending messages)
resource "google_service_account" "chat_bot" {
  project      = data.google_project.agent_project.project_id
  account_id   = var.bot_account_id
  display_name = var.bot_name
  description  = "Service account for ${var.bot_name} Google Chat bot"

  depends_on = [
    google_project_service.chat
  ]
}

# Grant Google Chat bot permissions
resource "google_project_iam_member" "chat_owner" {
  project = data.google_project.agent_project.project_id
  role    = "roles/chat.owner"
  member  = "serviceAccount:${google_service_account.chat_bot.email}"
}

# Store Google Chat service account credentials in Secret Manager
resource "google_secret_manager_secret" "chat_credentials" {
  project   = data.google_project.agent_project.project_id
  secret_id = var.secret_name

  replication {
    auto {}
  }

  depends_on = [
    google_project_service.secretmanager
  ]
}

# Grant middleware service accounts access to the secret
# This allows the agent running in middleware to access its credentials
resource "google_secret_manager_secret_iam_member" "middleware_compute_access" {
  project   = data.google_project.agent_project.project_id
  secret_id = google_secret_manager_secret.chat_credentials.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.middleware_project_number}-compute@developer.gserviceaccount.com"
}

resource "google_secret_manager_secret_iam_member" "middleware_aiplatform_access" {
  project   = data.google_project.agent_project.project_id
  secret_id = google_secret_manager_secret.chat_credentials.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:service-${var.middleware_project_number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}

resource "google_secret_manager_secret_iam_member" "middleware_reasoning_engine_access" {
  project   = data.google_project.agent_project.project_id
  secret_id = google_secret_manager_secret.chat_credentials.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:service-${var.middleware_project_number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}

# ==============================================================================
# SECTION 4: TELEGRAM-SPECIFIC INFRASTRUCTURE
# UNCOMMENTED - Sam uses Telegram
# ==============================================================================

# Telegram Bot Token Secret
resource "google_secret_manager_secret" "telegram_bot_token" {
  project   = data.google_project.agent_project.project_id
  secret_id = "${var.bot_account_id}-telegram-token"

  replication {
    auto {}
  }

  depends_on = [
    google_project_service.secretmanager
  ]
}

# Grant middleware service accounts access to the Telegram token
resource "google_secret_manager_secret_iam_member" "telegram_middleware_compute_access" {
  project   = data.google_project.agent_project.project_id
  secret_id = google_secret_manager_secret.telegram_bot_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.middleware_project_number}-compute@developer.gserviceaccount.com"
}

resource "google_secret_manager_secret_iam_member" "telegram_middleware_aiplatform_access" {
  project   = data.google_project.agent_project.project_id
  secret_id = google_secret_manager_secret.telegram_bot_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:service-${var.middleware_project_number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}

resource "google_secret_manager_secret_iam_member" "telegram_middleware_reasoning_engine_access" {
  project   = data.google_project.agent_project.project_id
  secret_id = google_secret_manager_secret.telegram_bot_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:service-${var.middleware_project_number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}

# Note: The Telegram bot token must be added manually after terraform apply:
# echo -n "YOUR_TELEGRAM_BOT_TOKEN" | gcloud secrets versions add ${var.bot_account_id}-telegram-token \
#   --data-file=- --project=${var.project_id}

# ==============================================================================
# OUTPUTS
# ==============================================================================

output "project_id" {
  description = "GCP Project ID for the agent"
  value       = var.project_id
}

output "apis_service_account_email" {
  description = "Service account email for Google APIs (Drive, Sheets) - share your Google Docs with this"
  value       = google_service_account.agent_apis.email
}

output "chat_service_account_email" {
  description = "Service account email for Google Chat bot"
  value       = google_service_account.chat_bot.email
}

output "next_steps" {
  description = "Instructions for completing the setup"
  value       = <<EOT

==================== NEXT STEPS ====================

SECTION 1: COMMON SETUP

1. Review what sections are uncommented in main.tf (Slack, Google Chat, and Telegram are enabled for Sam)

SECTION 2: SLACK SETUP (if using)

2a. Store the Slack bot token:
    echo -n "xoxb-YOUR-SLACK-BOT-TOKEN" | gcloud secrets versions add ${var.bot_account_id}-slack-token \
      --data-file=- \
      --project=${var.project_id}

2b. Grant middleware access to the Slack token:
    export MIDDLEWARE_PROJECT_ID="vertex-ai-middleware-prod"
    export MIDDLEWARE_PROJECT_NUMBER=$(gcloud projects describe $MIDDLEWARE_PROJECT_ID --format="value(projectNumber)")
    export MIDDLEWARE_SA="$${MIDDLEWARE_PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

    gcloud secrets add-iam-policy-binding ${var.bot_account_id}-slack-token \
      --member="serviceAccount:$${MIDDLEWARE_SA}" \
      --role="roles/secretmanager.secretAccessor" \
      --project=${var.project_id}

SECTION 3: GOOGLE CHAT SETUP

3a. Create a service account key for the Google Chat bot:
    gcloud iam service-accounts keys create ${var.bot_account_id}-sa-key.json \
      --iam-account=${google_service_account.chat_bot.email} \
      --project=${var.project_id}

3b. Store the key in this project's Secret Manager:
    gcloud secrets versions add ${var.secret_name} \
      --data-file=${var.bot_account_id}-sa-key.json \
      --project=${var.project_id}

    # Securely delete the key file
    rm -f ${var.bot_account_id}-sa-key.json

3c. Grant middleware access to the Google Chat credentials:
    export MIDDLEWARE_PROJECT_ID="vertex-ai-middleware-prod"
    export MIDDLEWARE_PROJECT_NUMBER=$(gcloud projects describe $MIDDLEWARE_PROJECT_ID --format="value(projectNumber)")
    export MIDDLEWARE_SA="$${MIDDLEWARE_PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

    gcloud secrets add-iam-policy-binding ${var.secret_name} \
      --member="serviceAccount:$${MIDDLEWARE_SA}" \
      --role="roles/secretmanager.secretAccessor" \
      --project=${var.project_id}

    CRITICAL: Without this IAM binding, messages will fail with "403 Permission Denied" errors!

3d. Configure Google Chat bot in Console:
    - Go to: https://console.cloud.google.com/apis/api/chat.googleapis.com/hangouts-chat?project=${var.project_id}
    - Click "Configuration"
    - Bot name: ${var.bot_name}
    - Avatar URL: ${var.bot_avatar_url}
    - Description: ${var.bot_description}
    - Functionality: "Receive 1:1 messages" and "Join spaces and group conversations"
    - Connection settings: "App URL"
    - Bot URL: https://slack-vertex-middleware-404939446326.us-central1.run.app/api/v1/google-chat/events
    - Permissions: "Specific people and groups" (add test users)

3e. Enable Google Chat for your agent in middleware:
    cd /path/to/slack-vertex-ai-middleware

    python scripts/enable_google_chat_agent.py \
      --project vertex-ai-middleware-prod \
      --agent-id YOUR_AGENT_FIRESTORE_ID \
      --secret-name ${var.secret_name} \
      --google-chat-project-id ${var.project_id}

SECTION 4: TELEGRAM SETUP

4a. Create Telegram bot via BotFather:
    - Open Telegram and message @BotFather
    - Send command: /newbot
    - Follow prompts to choose name (e.g., "Sam the Sommelier") and username (e.g., "sam_sommelier_bot")
    - Copy the bot token (format: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz)

4b. Store the Telegram bot token in Secret Manager:
    echo -n "YOUR_TELEGRAM_BOT_TOKEN" | gcloud secrets versions add ${var.bot_account_id}-telegram-token \
      --data-file=- \
      --project=${var.project_id}

    CRITICAL: The IAM bindings for middleware access are already configured by terraform!

4c. Set Telegram webhook:
    # Generate a random secret token for webhook verification
    export WEBHOOK_SECRET=$$(openssl rand -base64 32)

    # Set the webhook
    curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
      -H "Content-Type: application/json" \
      -d '{
        "url": "https://slack-vertex-middleware-404939446326.us-central1.run.app/api/v1/telegram/events",
        "secret_token": "'$$WEBHOOK_SECRET'"
      }'

    # Save the webhook secret for agent configuration in Firestore
    echo "Webhook secret: $$WEBHOOK_SECRET"

4d. Enable Telegram for your agent in middleware (use Firestore console or script)

SECTION 5: GOOGLE APIS SETUP (Share Google Drive/Sheets)

5a. Share Google Sheets/Drive files with the Google APIs service account:
    Service Account Email: ${google_service_account.agent_apis.email}

    Instructions:
    - Open your Google Sheet or Drive file
    - Click "Share"
    - Add the service account email above
    - Give it "Editor" or "Viewer" access (depending on agent needs)

====================================================

EOT
}
