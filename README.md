# Sam the Sommelier

An AI sommelier agent built with Google's Agent Development Kit (ADK) and deployed to Vertex AI Agent Engine. Sam helps manage wine cellars, provide tasting notes, and offer wine recommendations through Slack.

## Features

- **Wine Cellar Management**: Track your wine collection in Google Sheets
- **Tasting Notes**: Record and retrieve tasting notes for wines
- **Wine Recommendations**: Get personalized wine recommendations
- **Consumption Tracking**: Log wines as you drink them
- **Slack Integration**: Interact with Sam directly in Slack

## Prerequisites

- Google Cloud Project with billing enabled
- Vertex AI API enabled
- Secret Manager API enabled
- Firestore API enabled
- ADK (Agent Development Kit) installed
- Slack workspace and bot token
- [Slack Vertex AI Middleware](https://github.com/jonathanagustin/slack-vertex-ai-middleware) deployed

## Project Setup

### 1. Google Cloud Resources

#### Enable Required APIs
```bash
gcloud services enable aiplatform.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable firestore.googleapis.com
```

#### Create Firestore Database
```bash
gcloud firestore databases create --location=nam5 --type=firestore-native
```

#### Create Staging Bucket for ADK Deployments

ADK requires a Cloud Storage bucket to stage deployment artifacts. The deploy script expects a bucket named `gs://${PROJECT_ID}-staging`.

```bash
# Set your project ID
export PROJECT_ID=your-project-id

# Create staging bucket (one-time setup)
gsutil mb -p ${PROJECT_ID} -l us-central1 gs://${PROJECT_ID}-staging

# Optional: Set lifecycle policy to auto-delete old staging files after 7 days
cat > /tmp/lifecycle.json <<EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 7}
      }
    ]
  }
}
EOF

gsutil lifecycle set /tmp/lifecycle.json gs://${PROJECT_ID}-staging
rm /tmp/lifecycle.json
```

**Note**: If the bucket doesn't exist, ADK will create it automatically on first deployment, but creating it manually allows you to set lifecycle policies and choose the location.

#### Create Service Account for Google Sheets/Docs Access
```bash
# Create service account
gcloud iam service-accounts create sommelier-sa \
    --display-name="Sam the Sommelier Service Account"

# Create and download key
gcloud iam service-accounts keys create sommelier-sa-key.json \
    --iam-account=sommelier-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com

# Upload to Secret Manager
gcloud secrets create sommelier-credentials \
    --data-file=sommelier-sa-key.json \
    --project=YOUR_PROJECT_ID

# Grant the service account access to your Google Sheets
# Share your sheets with: sommelier-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### 2. Slack Bot Token

Store your Slack bot token in Secret Manager:

```bash
# If migrating from another project
gcloud secrets versions access latest \
    --secret=slack-sommelier \
    --project=OLD_PROJECT_ID > /tmp/slack-token.txt

# Create in new project
cat /tmp/slack-token.txt | gcloud secrets create slack-sommelier \
    --data-file=- \
    --project=vertex-ai-middleware-prod

# Clean up
rm /tmp/slack-token.txt
```

Or create a new one:

```bash
echo -n "xoxb-YOUR-SLACK-BOT-TOKEN" | gcloud secrets create slack-sommelier \
    --data-file=- \
    --project=vertex-ai-middleware-prod
```

### 3. Environment Configuration

Create or update your `.env` file with the appropriate settings:

#### For Windows Development
```bash
# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=vertex-ai-middleware-prod
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=TRUE

# Google ADK Agent Models
HIGH_QUALITY_AGENT_MODEL=gemini-3.1-pro-preview
QUICK_AGENT_MODEL=gemini-3-flash-preview
IMAGE_ANALYSIS_MODEL=gemini-3-flash-preview

# Google Sheets/Docs Service Account
SOMMELIER_SECRET_NAME=sommelier-credentials
SOMMELIER_CREDENTIALS=C:/Users/YourName/path/to/sommelier-sa-key.json

# Spreadsheet and Document IDs
SOMMELIER_CELLAR_SSID=your-cellar-spreadsheet-id
SOMMELIER_CONSUMED_SSID=your-consumed-spreadsheet-id
SOMMELIER_TASTING_NOTES_SSID=your-tasting-notes-spreadsheet-id
SOMMELIER_MEMORY_DOC_ID=your-memory-doc-id

# Deployment paths (Windows)
ADK_BIN=/c/Users/YourName/AppData/Roaming/Python/Python313/Scripts/adk
ADK_PYTHON=/c/Python313/python
MIDDLEWARE_DIR=/c/Users/YourName/projects/slack-vertex-ai-middleware
AGENT_DISPLAY_NAME="Sam the Som"
AGENT_FIRESTORE_ID=your-agent-firestore-document-id

# Staging bucket: gs://${GOOGLE_CLOUD_PROJECT}-staging
# The deploy script automatically uses this naming convention

# Enable Monitoring
GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=TRUE
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=TRUE
```

#### For Cloud Shell Deployment
```bash
# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT=vertex-ai-middleware-prod
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=TRUE

# Google ADK Agent Models
HIGH_QUALITY_AGENT_MODEL=gemini-3.1-pro-preview
QUICK_AGENT_MODEL=gemini-3-flash-preview
IMAGE_ANALYSIS_MODEL=gemini-3-flash-preview

# Google Sheets/Docs Service Account
SOMMELIER_SECRET_NAME=sommelier-credentials
SOMMELIER_CREDENTIALS=/home/jonathan/projects/agents/sommelier/credentials/sommelier-sa-key.json

# Spreadsheet and Document IDs
SOMMELIER_CELLAR_SSID=your-cellar-spreadsheet-id
SOMMELIER_CONSUMED_SSID=your-consumed-spreadsheet-id
SOMMELIER_TASTING_NOTES_SSID=your-tasting-notes-spreadsheet-id
SOMMELIER_MEMORY_DOC_ID=your-memory-doc-id

# Deployment paths (Cloud Shell)
ADK_BIN=/home/jonathan/.local/bin/adk
ADK_PYTHON=/usr/bin/python3
MIDDLEWARE_DIR=/home/jonathan/slack-vertex-ai-middleware
AGENT_DISPLAY_NAME="Sam the Som"
AGENT_FIRESTORE_ID=your-agent-firestore-document-id

# Staging bucket: gs://${GOOGLE_CLOUD_PROJECT}-staging
# The deploy script automatically uses this naming convention

# Enable Monitoring
GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=TRUE
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=TRUE
```

## Deployment

### Option 1: Deploy from Google Cloud Shell (Recommended)

**Why Cloud Shell?** ADK deployment from Windows can fail due to `.git` directory file locking issues during cleanup. Cloud Shell provides a clean Linux environment without these issues.

#### Steps:

1. **Open Cloud Shell** in your GCP Console

2. **Install ADK**
   ```bash
   pip install google-genai-adk --user
   export PATH="$PATH:$HOME/.local/bin"
   ```

3. **Clone Repositories**
   ```bash
   mkdir -p ~/projects
   cd ~/projects

   # Clone sommelier agent
   git clone https://github.com/YOUR_USERNAME/sommelier.git

   # Clone middleware
   git clone https://github.com/jonathanagustin/slack-vertex-ai-middleware.git
   ```

4. **Create .env File**
   ```bash
   cd ~/projects/sommelier
   # Copy the Cloud Shell configuration example above and adjust paths
   nano .env
   ```

5. **Run Deployment**
   ```bash
   chmod +x deploy_and_update.sh
   ./deploy_and_update.sh
   ```

### Option 2: Deploy from Windows (Not Recommended)

If you must deploy from Windows:

1. Ensure `.ae_ignore` file exists (critical for preventing `.git` directory issues)
2. Install ADK in your Python environment
3. Configure `.env` with Windows paths
4. Run: `bash deploy_and_update.sh`

**Known Issue**: Windows deployment may fail during cleanup phase due to file locking on `.git` directory. The `.ae_ignore` file helps prevent this, but Cloud Shell is more reliable.

## File Exclusion Configuration

The `.ae_ignore` file is **critical** for successful deployments. ADK uses this file (NOT `.adkignore` or `.gcloudignore`) to exclude files during deployment.

Key exclusions:
- `.git/` directory (prevents Windows file locking)
- `__pycache__/` and `*.pyc` files
- `.env` and credential files
- IDE configuration files

## What the Deployment Script Does

The `deploy_and_update.sh` script automates:

1. **Pre-flight checks**: Validates ADK, middleware, and credentials
2. **gcloud configuration**: Sets the correct GCP project
3. **Find existing agent**: Checks for previous deployment
4. **Deploy new agent**: Deploys to Vertex AI Agent Engine using `gs://${PROJECT_ID}-staging` bucket
5. **Smoke test**: Verifies the new agent is accessible
6. **Middleware registration**: Updates Firestore with new agent ID
7. **Session cleanup**: Clears stale sessions for this agent
8. **Old agent cleanup**: Deletes the previous version (with force=true to handle child resources)

**Staging Bucket**: The script uses `gs://${PROJECT_ID}-staging` to store temporary deployment artifacts. If the bucket doesn't exist, ADK will create it automatically. See the "Create Staging Bucket" section above for manual setup with lifecycle policies.

## Middleware Configuration

The deployment script automatically registers Sam with the Slack middleware by:

1. Creating/updating an agent document in Firestore (`agents` collection)
2. Linking the Slack bot ID to the Vertex AI agent resource name
3. Storing the Slack bot token reference

### Verify Middleware Registration

```bash
# Check Firestore for agent registration
gcloud firestore documents list agents --project=vertex-ai-middleware-prod

# Or use Python
python3 -c "
from google.cloud import firestore
db = firestore.Client(project='vertex-ai-middleware-prod')
agents = db.collection('agents').stream()
for agent in agents:
    print(f'{agent.id}: {agent.to_dict()}')
"
```

## Testing

After deployment, test Sam in Slack:

1. Send a direct message to the Sam bot
2. Try: "What wines do I have in my cellar?"
3. Try: "Recommend a wine for steak"

## Monitoring

View agent logs and traces:

```bash
# View recent logs
gcloud logging read "resource.type=vertex_ai_agent" \
    --limit 50 \
    --project=vertex-ai-middleware-prod

# Check telemetry in Cloud Trace
# Navigate to: Cloud Console → Trace → Trace List
```

## Troubleshooting

### Deployment fails with "Permission denied" on .git files (Windows)
- **Solution**: Deploy from Cloud Shell instead, or ensure `.ae_ignore` is properly configured

### "Could not retrieve Slack bot token from Secret Manager"
- **Solution**: Verify the secret exists and you have access:
  ```bash
  gcloud secrets versions access latest \
      --secret=slack-sommelier \
      --project=vertex-ai-middleware-prod
  ```

### "Middleware registration failed"
- **Solution**: Check that Firestore is enabled and the middleware repo is accessible
  ```bash
  gcloud services enable firestore.googleapis.com
  ```

### Agent deploys but doesn't respond in Slack
- **Solution**:
  1. Verify middleware is running
  2. Check Firestore agent registration
  3. Clear stale sessions (deployment script does this automatically)

## Development

### Local Testing with ADK Web UI

```bash
# Activate virtual environment (if using)
source .my_venv/bin/activate  # Linux/Mac
# or
.my_venv\Scripts\activate  # Windows

# Run local web interface
adk web sommelier
```

### Updating the Agent

1. Make code changes
2. Run `./deploy_and_update.sh`
3. The script handles version management automatically

## Project Structure

```
sommelier/
├── .ae_ignore              # ADK file exclusion configuration (CRITICAL)
├── .env                    # Environment configuration (gitignored)
├── agent.py                # Main agent definition
├── custom_agents.py        # Custom agent implementations
├── custom_functions.py     # Tool/function definitions
├── sheet_utilities.py      # Google Sheets integration
├── requirements.txt        # Python dependencies
├── deploy_and_update.sh    # Deployment automation script
└── README.md              # This file
```

## Security Notes

- Never commit `.env` files or credentials to git
- Use Secret Manager for all sensitive data
- Service account keys are stored in Secret Manager (sommelier-credentials)
- Slack bot tokens are stored in Secret Manager (slack-sommelier)

## License

[Your License Here]

## Contributing

[Your Contributing Guidelines Here]
