# AI Ad Agent - Utility Scripts

This directory contains utility scripts for managing and configuring the AI Ad Agent.

## Available Scripts

### 1. `verify_gcp_setup.py`

Verify that all GCP services are properly configured.

**Usage:**
```bash
python scripts/verify_gcp_setup.py
```

**Checks:**
- ✅ Service Account configuration
- ✅ Firestore connection and collections
- ✅ Cloud Storage bucket access
- ✅ Secret Manager secrets

**Example Output:**
```
🚀 GCP SETUP VERIFICATION
================================================================================
Project ID: sound-invention-432122-m5
Region: europe-west1
Environment: development

🔍 Checking Service Account...
✅ Service account key configured
   Path: ./service-account-key.json
   ✅ File exists

🔍 Checking Firestore...
✅ Connected to Firestore
   Project: sound-invention-432122-m5
   Database: (default)
   Collections found: 3
     - users (has documents: true)
     - campaigns (has documents: true)
     - jobs (has documents: false)

🔍 Checking Cloud Storage...
✅ Connected to Cloud Storage
   Bucket: your-bucket-name
   Location: EUROPE-WEST1
   Storage Class: STANDARD
   Bucket is empty (ready for use)

🔍 Checking Secret Manager...
✅ Connected to Secret Manager
   Project: sound-invention-432122-m5
   Secrets found: 2
     - ai-ad-agent-secret-key
       ✅ Accessible
     - unified-api-credentials
       ✅ Accessible

📊 SUMMARY
================================================================================
✅ PASS - Service Account
✅ PASS - Firestore
✅ PASS - Cloud Storage
✅ PASS - Secret Manager
================================================================================
✅ All checks passed! Your GCP setup is ready.
```

---

### 2. `fetch_models.py`

Fetch all available models from the Unified API.

**Usage:**
```bash
# Interactive (will prompt for email/password)
python scripts/fetch_models.py

# With credentials
python scripts/fetch_models.py --email user@example.com --password mypassword

# Custom output file
python scripts/fetch_models.py --output models_export.json

# No summary (just save to file)
python scripts/fetch_models.py --no-summary
```

**Options:**
- `--email` - Email for Unified API login
- `--password` - Password for Unified API login
- `--output` - Output file path (default: data/models.json)
- `--no-summary` - Don't print summary to console

**Example Output:**
```
Logging in to Unified API...
✅ Login successful! Token: eyJhbGciOiJIUzI1NiIs...
Fetching available models...
✅ Found 12 models

================================================================================
📊 UNIFIED API MODELS SUMMARY
================================================================================

📈 Total Models: 12
🎬 Video Models: 4
🖼️  Image Models: 8
🔧 Other Models: 0

--------------------------------------------------------------------------------
🎬 VIDEO MODELS:
--------------------------------------------------------------------------------

  Name: Google Veo 3.1
  ID: veo
  Type: video
  Description: High-quality video generation with advanced motion control
  Aspect Ratios: 16:9, 9:16, 1:1
  Max Duration: 30s
  Price: $0.50

  Name: OpenAI Sora
  ID: sora
  Type: video
  ...

--------------------------------------------------------------------------------
🖼️  IMAGE MODELS:
--------------------------------------------------------------------------------

  Name: Gemini Nanobanana
  ID: nanobanana
  Type: image
  ...

================================================================================

✅ Models data saved to: data/models.json
✅ Success! Models data saved to data/models.json
```

**Output File Format:**
```json
{
  "total_models": 12,
  "video_models": [...],
  "image_models": [...],
  "other_models": [],
  "all_models": [...]
}
```

---

## Setting Up GCP Services

### Prerequisites

1. **Create GCP Project** (if not exists)
```bash
gcloud projects create sound-invention-432122-m5
gcloud config set project sound-invention-432122-m5
```

2. **Enable Required APIs**
```bash
gcloud services enable \
  firestore.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com
```

### 1. Setup Firestore

```bash
# Create Firestore database
gcloud firestore databases create \
  --region=europe-west1 \
  --type=firestore-native

# Verify
gcloud firestore databases describe --database="(default)"
```

### 2. Setup Cloud Storage

```bash
# Create bucket (replace with your bucket name)
gsutil mb -l europe-west1 gs://your-bucket-name

# Set lifecycle policy (optional - auto-delete old files)
cat > lifecycle.json << EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 365}
      }
    ]
  }
}
EOF
gsutil lifecycle set lifecycle.json gs://your-bucket-name

# Verify
gsutil ls -L -b gs://your-bucket-name
```

### 3. Setup Secret Manager

```bash
# Create secrets
echo -n "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" | \
  gcloud secrets create ai-ad-agent-secret-key --data-file=-

# Verify
gcloud secrets list
gcloud secrets versions access latest --secret="ai-ad-agent-secret-key"
```

### 4. Setup Service Account

```bash
# Create service account
gcloud iam service-accounts create ai-ad-agent \
  --display-name="AI Ad Agent Service Account"

# Grant permissions
gcloud projects add-iam-policy-binding sound-invention-432122-m5 \
  --member="serviceAccount:ai-ad-agent@sound-invention-432122-m5.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding sound-invention-432122-m5 \
  --member="serviceAccount:ai-ad-agent@sound-invention-432122-m5.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding sound-invention-432122-m5 \
  --member="serviceAccount:ai-ad-agent@sound-invention-432122-m5.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Download key (for local development)
gcloud iam service-accounts keys create service-account-key.json \
  --iam-account=ai-ad-agent@sound-invention-432122-m5.iam.gserviceaccount.com

# Move to backend directory
mv service-account-key.json ../
```

---

## Verification Workflow

### Quick Verification

```bash
# 1. Verify GCP setup
python scripts/verify_gcp_setup.py

# 2. Fetch models (will prompt for credentials)
python scripts/fetch_models.py

# 3. Check the models data
cat data/models.json | jq .
```

### Full Setup from Scratch

```bash
# 1. Enable APIs
gcloud services enable firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com

# 2. Create Firestore
gcloud firestore databases create --region=europe-west1

# 3. Create Storage Bucket
gsutil mb -l europe-west1 gs://ai-ad-agent-assets

# 4. Create Secret
echo -n "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" | \
  gcloud secrets create ai-ad-agent-secret-key --data-file=-

# 5. Setup Service Account
gcloud iam service-accounts create ai-ad-agent
gcloud projects add-iam-policy-binding sound-invention-432122-m5 \
  --member="serviceAccount:ai-ad-agent@sound-invention-432122-m5.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
gcloud projects add-iam-policy-binding sound-invention-432122-m5 \
  --member="serviceAccount:ai-ad-agent@sound-invention-432122-m5.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
gcloud projects add-iam-policy-binding sound-invention-432122-m5 \
  --member="serviceAccount:ai-ad-agent@sound-invention-432122-m5.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# 6. Download service account key
gcloud iam service-accounts keys create ../service-account-key.json \
  --iam-account=ai-ad-agent@sound-invention-432122-m5.iam.gserviceaccount.com

# 7. Update .env file
cd ..
cp .env.example .env
# Edit .env and set:
# - GCS_BUCKET_NAME=ai-ad-agent-assets
# - GOOGLE_APPLICATION_CREDENTIALS=./service-account-key.json
# - USE_SECRET_MANAGER=true (for production) or false (for local dev)

# 8. Verify setup
python scripts/verify_gcp_setup.py

# 9. Fetch models
python scripts/fetch_models.py
```

---

## Troubleshooting

### Error: "Permission denied"

**Solution:**
```bash
# Check service account permissions
gcloud projects get-iam-policy sound-invention-432122-m5 \
  --flatten="bindings[].members" \
  --filter="bindings.members:ai-ad-agent@sound-invention-432122-m5.iam.gserviceaccount.com"

# Add missing roles
gcloud projects add-iam-policy-binding sound-invention-432122-m5 \
  --member="serviceAccount:ai-ad-agent@sound-invention-432122-m5.iam.gserviceaccount.com" \
  --role="roles/MISSING_ROLE"
```

### Error: "Firestore database not found"

**Solution:**
```bash
# Check if Firestore exists
gcloud firestore databases list

# Create if missing
gcloud firestore databases create --region=europe-west1
```

### Error: "Bucket not found"

**Solution:**
```bash
# List buckets
gsutil ls

# Create bucket
gsutil mb -l europe-west1 gs://your-bucket-name
```

### Error: "Secret not found"

**Solution:**
```bash
# List secrets
gcloud secrets list

# Create secret
echo -n "your-secret-value" | gcloud secrets create SECRET-NAME --data-file=-
```

---

## Environment Variables

See `../.env.example` for all configuration options.

**Key Variables:**
- `GCP_PROJECT_ID` - Your GCP project ID
- `GCS_BUCKET_NAME` - Cloud Storage bucket name
- `USE_SECRET_MANAGER` - true (production) or false (local dev)
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to service account key (local only)

---

## Additional Resources

- [Firestore Documentation](https://cloud.google.com/firestore/docs)
- [Cloud Storage Documentation](https://cloud.google.com/storage/docs)
- [Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [Service Accounts Best Practices](https://cloud.google.com/iam/docs/best-practices-service-accounts)
