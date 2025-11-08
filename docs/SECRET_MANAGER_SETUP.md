# Secret Manager Setup - AI Ad Agent

**Date:** 2025-01-08
**Pattern:** Unified API compatible

## Overview

The AI Ad Agent uses **GCP Secret Manager** to store API keys, following the same pattern as the Unified API for consistency across projects.

### Key Benefits

- **User-specific API keys**: Each user can have their own Gemini/ElevenLabs API keys
- **Global fallback**: If user doesn't have keys, use shared global keys
- **Secure storage**: Keys stored in GCP Secret Manager, not in code or environment
- **Consistent pattern**: Same naming convention as Unified API

## Secret Naming Convention

### Pattern

```
ai_ad_agent_{scope}_{provider}_{key_type}
```

Where:
- **scope**: `global` or `{user_id}` (e.g., `user_abc123`)
- **provider**: `gemini`, `elevenlabs`, `google`
- **key_type**: `api_key`, `secret_key`

### Examples

**Global secrets (shared by all users):**
```
ai_ad_agent_gemini_api_key
ai_ad_agent_elevenlabs_api_key
ai_ad_agent_google_api_key      # Alias for gemini
ai_ad_agent_unified_api_url     # Unified API endpoint
ai_ad_agent_gcs_bucket          # GCS bucket name
```

**User-specific secrets:**
```
ai_ad_agent_user123_gemini_api_key
ai_ad_agent_user123_elevenlabs_api_key
ai_ad_agent_user456_gemini_api_key
ai_ad_agent_user456_elevenlabs_api_key
```

## Required API Keys

### 1. Gemini API Key (Required)

**Purpose:** Text generation (prompt creation, script analysis, creative suggestions, clip verification)

**Provider:** Google AI Studio

**Get Key:**
1. Go to https://makersuite.google.com/app/apikey
2. Create or select a project
3. Click "Create API Key"
4. Copy the key (starts with `AIzaSy...`)

**Secret Name:**
- Global: `ai_ad_agent_gemini_api_key`
- User-specific: `ai_ad_agent_{user_id}_gemini_api_key`

### 2. ElevenLabs API Key (Required)

**Purpose:** Audio generation (voiceover, background music, sound effects)

**Provider:** ElevenLabs

**Get Key:**
1. Go to https://elevenlabs.io/
2. Sign up or log in
3. Go to Profile → API Keys
4. Copy your API key

**Secret Name:**
- Global: `ai_ad_agent_elevenlabs_api_key`
- User-specific: `ai_ad_agent_{user_id}_elevenlabs_api_key`

### 3. Unified API Endpoint (Optional)

**Purpose:** Veo 3.1 video generation

**Default:** `https://unified-api-interface-994684344365.europe-west1.run.app`

**Secret Name:** `ai_ad_agent_unified_api_url`

### 4. GCS Bucket (Optional)

**Purpose:** Video storage

**Default:** From `GCS_BUCKET_NAME` environment variable

**Secret Name:** `ai_ad_agent_gcs_bucket`

## Setup Instructions

### Option 1: Using gcloud CLI

#### Create Global Secrets

```bash
# Set project
export PROJECT_ID="sound-invention-432122-m5"
gcloud config set project $PROJECT_ID

# Create Gemini API key secret
echo -n "YOUR_GEMINI_API_KEY_HERE" | gcloud secrets create ai_ad_agent_gemini_api_key \
  --replication-policy="automatic" \
  --data-file=-

# Create ElevenLabs API key secret
echo -n "YOUR_ELEVENLABS_API_KEY_HERE" | gcloud secrets create ai_ad_agent_elevenlabs_api_key \
  --replication-policy="automatic" \
  --data-file=-

# Create Unified API URL (optional)
echo -n "https://unified-api-interface-994684344365.europe-west1.run.app" | \
  gcloud secrets create ai_ad_agent_unified_api_url \
  --replication-policy="automatic" \
  --data-file=-

# Create GCS bucket name (optional)
echo -n "your-bucket-name" | gcloud secrets create ai_ad_agent_gcs_bucket \
  --replication-policy="automatic" \
  --data-file=-
```

#### Create User-Specific Secrets

```bash
# User ID
export USER_ID="user_abc123"

# Create user's Gemini key
echo -n "USER_GEMINI_API_KEY" | gcloud secrets create ai_ad_agent_${USER_ID}_gemini_api_key \
  --replication-policy="automatic" \
  --data-file=-

# Create user's ElevenLabs key
echo -n "USER_ELEVENLABS_API_KEY" | gcloud secrets create ai_ad_agent_${USER_ID}_elevenlabs_api_key \
  --replication-policy="automatic" \
  --data-file=-
```

#### Grant Access to Service Account

```bash
# Service account for Cloud Run (adjust if different)
export SERVICE_ACCOUNT="994684344365-compute@developer.gserviceaccount.com"

# Grant access to all AI Ad Agent secrets
gcloud secrets add-iam-policy-binding ai_ad_agent_gemini_api_key \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding ai_ad_agent_elevenlabs_api_key \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

# Repeat for user-specific secrets
gcloud secrets add-iam-policy-binding ai_ad_agent_${USER_ID}_gemini_api_key \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"
```

### Option 2: Using GCP Console

1. **Go to Secret Manager**
   - Navigate to: https://console.cloud.google.com/security/secret-manager
   - Select project: `sound-invention-432122-m5`

2. **Create Global Secrets**
   - Click "CREATE SECRET"
   - Name: `ai_ad_agent_gemini_api_key`
   - Secret value: Your Gemini API key
   - Click "CREATE"
   - Repeat for ElevenLabs

3. **Grant Permissions**
   - Click on the secret
   - Go to "PERMISSIONS" tab
   - Click "GRANT ACCESS"
   - Add service account: `994684344365-compute@developer.gserviceaccount.com`
   - Role: "Secret Manager Secret Accessor"
   - Click "SAVE"

### Option 3: Using Python Script

Create `setup_secrets.py`:

```python
from google.cloud import secretmanager
import os

PROJECT_ID = "sound-invention-432122-m5"

def create_secret(secret_id: str, secret_value: str):
    """Create or update a secret."""
    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{PROJECT_ID}"

    # Try to create secret
    try:
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            }
        )
        print(f"✅ Created secret: {secret_id}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"ℹ️  Secret {secret_id} already exists, adding version")
        else:
            print(f"❌ Error creating {secret_id}: {e}")
            return

    # Add secret version
    secret_path = f"{parent}/secrets/{secret_id}"
    client.add_secret_version(
        request={
            "parent": secret_path,
            "payload": {"data": secret_value.encode("UTF-8")},
        }
    )
    print(f"✅ Added version to: {secret_id}")


# Create global secrets
create_secret("ai_ad_agent_gemini_api_key", "YOUR_GEMINI_KEY_HERE")
create_secret("ai_ad_agent_elevenlabs_api_key", "YOUR_ELEVENLABS_KEY_HERE")
create_secret("ai_ad_agent_unified_api_url", "https://unified-api-interface-994684344365.europe-west1.run.app")
create_secret("ai_ad_agent_gcs_bucket", "your-bucket-name")

# Create user-specific secrets (example)
user_id = "user_abc123"
create_secret(f"ai_ad_agent_{user_id}_gemini_api_key", "USER_SPECIFIC_GEMINI_KEY")
create_secret(f"ai_ad_agent_{user_id}_elevenlabs_api_key", "USER_SPECIFIC_ELEVENLABS_KEY")
```

Run:
```bash
python setup_secrets.py
```

## How It Works

### Application Startup

1. **Load Global Secrets** (`main.py`):
   ```python
   from app.secrets import ensure_secrets_loaded
   ensure_secrets_loaded()
   ```

2. **Sets Environment Variables**:
   - `GEMINI_API_KEY` → Global Gemini key
   - `ELEVENLABS_API_KEY` → Global ElevenLabs key
   - `UNIFIED_API_BASE_URL` → Unified API endpoint
   - `GCS_BUCKET_NAME` → Storage bucket

### Per-Request Key Loading

When a user creates an ad (`POST /api/ad-agent/create`):

1. **Extract user_id** from JWT token
2. **Load user-specific keys**:
   ```python
   from app.secrets import get_user_secret

   gemini_key = get_user_secret(user_id, "gemini", "api_key")
   # If not found, falls back to global key
   ```
3. **Initialize pipeline** with user's or global keys

### Fallback Chain

```
User-specific secret → Global secret → Environment variable
```

Example for `user_abc123`:
1. Try: `ai_ad_agent_user_abc123_gemini_api_key`
2. If not found, try: `ai_ad_agent_gemini_api_key`
3. If not found, try: `GEMINI_API_KEY` environment variable

## Code Usage

### Get User-Specific Secret

```python
from app.secrets import get_user_secret

# Get user's Gemini key (falls back to global)
gemini_key = get_user_secret("user_abc123", "gemini", "api_key")

# Get user's ElevenLabs key (no fallback)
elevenlabs_key = get_user_secret(
    "user_abc123",
    "elevenlabs",
    "api_key",
    fallback_to_global=False
)
```

### Save User-Specific Secret

```python
from app.secrets import save_user_secret

# Save user's custom API key
success = save_user_secret(
    user_id="user_abc123",
    provider="gemini",
    key_type="api_key",
    secret_value="AIzaSy..."
)
```

### Get All Credentials

```python
from app.secrets import get_ai_agent_credentials

# Get all credentials for a user
creds = get_ai_agent_credentials("user_abc123")
# Returns: {
#   "GEMINI_API_KEY": "...",
#   "ELEVENLABS_API_KEY": "...",
#   "UNIFIED_API_BASE_URL": "...",
#   "GCS_BUCKET_NAME": "..."
# }
```

## Environment Variables (Development Only)

For **local development**, you can use `.env` file instead of Secret Manager:

```env
# .env file
GCP_PROJECT_ID=sound-invention-432122-m5
GEMINI_API_KEY=AIzaSy...
ELEVENLABS_API_KEY=your-key
UNIFIED_API_BASE_URL=https://unified-api-interface-994684344365.europe-west1.run.app
GCS_BUCKET_NAME=your-bucket-name
```

**Note:** In production (Cloud Run), always use Secret Manager, not environment variables.

## Verification

### Check if Secrets Exist

```bash
# List all AI Ad Agent secrets
gcloud secrets list --filter="name:ai_ad_agent"

# Expected output:
# NAME                                 CREATED
# ai_ad_agent_gemini_api_key           2025-01-08
# ai_ad_agent_elevenlabs_api_key       2025-01-08
# ai_ad_agent_unified_api_url          2025-01-08
```

### Test Secret Access

```python
from app.secrets import get_secret

gemini_key = get_secret("ai_ad_agent_gemini_api_key")
if gemini_key:
    print(f"✅ Gemini key found: {gemini_key[:10]}...")
else:
    print("❌ Gemini key not found")
```

### Health Check Endpoint

The AI Ad Agent has a health check that verifies API keys:

```bash
curl http://localhost:8000/api/ad-agent/health
```

Response:
```json
{
  "status": "healthy",
  "gemini_configured": true,
  "elevenlabs_configured": true,
  "unified_api_url": "https://unified-api-interface-994684344365.europe-west1.run.app"
}
```

## Troubleshooting

### Secret Not Found

**Error:** `Failed to fetch secret ai_ad_agent_gemini_api_key`

**Solutions:**
1. Verify secret exists: `gcloud secrets list --filter="name:ai_ad_agent_gemini_api_key"`
2. Check secret name matches pattern exactly
3. Verify service account has access

### Permission Denied

**Error:** `Permission denied for secret: ai_ad_agent_gemini_api_key`

**Solutions:**
```bash
# Grant access to service account
gcloud secrets add-iam-policy-binding ai_ad_agent_gemini_api_key \
  --member="serviceAccount:YOUR-SERVICE-ACCOUNT@PROJECT.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Using Environment Variables

If Secret Manager fails, the app falls back to environment variables:

```
WARNING: Failed to load secrets from Secret Manager: ...
WARNING: Using environment variable for Gemini API key (user user_abc123)
```

This is OK for development, but in production you should fix Secret Manager access.

## Security Best Practices

1. **Never commit API keys to git** - Always use Secret Manager
2. **Use user-specific keys** when possible - Better isolation
3. **Rotate keys regularly** - Add new versions to secrets
4. **Limit service account permissions** - Only give "Secret Accessor" role
5. **Use separate keys per environment** - dev, staging, prod

## Migration from Environment Variables

If you currently use `.env` file:

1. **Create secrets** from your current keys:
   ```bash
   # Read from .env and create secrets
   source .env
   echo -n "$GEMINI_API_KEY" | gcloud secrets create ai_ad_agent_gemini_api_key --data-file=-
   echo -n "$ELEVENLABS_API_KEY" | gcloud secrets create ai_ad_agent_elevenlabs_api_key --data-file=-
   ```

2. **Test** that secrets are loaded:
   ```bash
   python -c "from app.secrets import get_secret; print(get_secret('ai_ad_agent_gemini_api_key')[:10])"
   ```

3. **Remove keys from .env** file (keep project ID, bucket name)

4. **Deploy** - App will use Secret Manager

---

**Status:** ✅ Implemented
**Pattern:** Unified API Compatible
**Project:** AI Ad Agent

**Secrets to Create:**
- ✅ `ai_ad_agent_gemini_api_key` (required)
- ✅ `ai_ad_agent_elevenlabs_api_key` (required)
- ⚪ `ai_ad_agent_unified_api_url` (optional)
- ⚪ `ai_ad_agent_gcs_bucket` (optional)
- ⚪ `ai_ad_agent_{user_id}_gemini_api_key` (per user)
- ⚪ `ai_ad_agent_{user_id}_elevenlabs_api_key` (per user)
