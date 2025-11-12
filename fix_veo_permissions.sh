#!/bin/bash
# Fix Veo API permissions for Cloud Run service account

PROJECT_ID="sound-invention-432122-m5"
SERVICE_ACCOUNT="994684344365-compute@developer.gserviceaccount.com"

echo "======================================================================"
echo "Fixing Veo API Permissions for Cloud Run"
echo "======================================================================"
echo ""
echo "Project: $PROJECT_ID"
echo "Service Account: $SERVICE_ACCOUNT"
echo ""

# 1. Enable Vertex AI API (if not already enabled)
echo "Step 1: Enabling Vertex AI API..."
gcloud services enable aiplatform.googleapis.com --project=$PROJECT_ID
echo ""

# 2. Grant Vertex AI User role
echo "Step 2: Granting Vertex AI User role to service account..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/aiplatform.user"
echo ""

# 3. Grant additional permissions if needed
echo "Step 3: Granting Service Account Token Creator role..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/iam.serviceAccountTokenCreator"
echo ""

# 4. Verify permissions
echo "Step 4: Verifying current IAM roles for service account..."
gcloud projects get-iam-policy $PROJECT_ID \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:${SERVICE_ACCOUNT}" \
    --format="table(bindings.role)"
echo ""

echo "======================================================================"
echo "DONE! Permissions updated."
echo "======================================================================"
echo ""
echo "Next steps:"
echo "1. Wait 1-2 minutes for permissions to propagate"
echo "2. Redeploy Cloud Run service (or wait for auto-deploy from GitHub)"
echo "3. Test the /create-stream-upload endpoint again"
echo ""
