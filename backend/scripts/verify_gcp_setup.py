"""
Verify GCP setup (Firestore, Storage, Secret Manager).

This script checks that all required GCP services are properly configured.

Usage:
    python scripts/verify_gcp_setup.py
"""
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from google.cloud import firestore, storage, secretmanager
from google.api_core import exceptions
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_firestore():
    """Check Firestore connection and collections."""
    print("\n" + "="*80)
    print("🔍 Checking Firestore...")
    print("="*80)

    try:
        db = firestore.Client(project=settings.GCP_PROJECT_ID)

        # Try to list collections
        collections = list(db.collections())
        print(f"✅ Connected to Firestore")
        print(f"   Project: {settings.GCP_PROJECT_ID}")
        print(f"   Database: {settings.FIRESTORE_DATABASE}")

        if collections:
            print(f"   Collections found: {len(collections)}")
            for col in collections:
                count = len(list(col.limit(1).stream()))
                print(f"     - {col.id} (has documents: {count > 0})")
        else:
            print(f"   No collections yet (will be created on first use)")

        return True

    except exceptions.PermissionDenied:
        print("❌ Permission denied. Ensure service account has 'Cloud Datastore User' role")
        return False
    except exceptions.NotFound:
        print(f"❌ Firestore database not found in project {settings.GCP_PROJECT_ID}")
        return False
    except Exception as e:
        print(f"❌ Error connecting to Firestore: {e}")
        return False


def check_storage():
    """Check Cloud Storage bucket."""
    print("\n" + "="*80)
    print("🔍 Checking Cloud Storage...")
    print("="*80)

    try:
        client = storage.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(settings.GCS_BUCKET_NAME)

        # Check if bucket exists
        if bucket.exists():
            print(f"✅ Connected to Cloud Storage")
            print(f"   Bucket: {settings.GCS_BUCKET_NAME}")
            print(f"   Location: {bucket.location}")
            print(f"   Storage Class: {bucket.storage_class}")

            # List some blobs
            blobs = list(bucket.list_blobs(max_results=5))
            if blobs:
                print(f"   Objects found: {len(blobs)}")
                for blob in blobs[:5]:
                    print(f"     - {blob.name}")
            else:
                print(f"   Bucket is empty (ready for use)")

            return True
        else:
            print(f"❌ Bucket '{settings.GCS_BUCKET_NAME}' not found")
            print(f"   Create it with: gsutil mb -l {settings.GCP_REGION} gs://{settings.GCS_BUCKET_NAME}")
            return False

    except exceptions.PermissionDenied:
        print("❌ Permission denied. Ensure service account has 'Storage Object Admin' role")
        return False
    except Exception as e:
        print(f"❌ Error connecting to Cloud Storage: {e}")
        return False


def check_secret_manager():
    """Check Secret Manager secrets."""
    print("\n" + "="*80)
    print("🔍 Checking Secret Manager...")
    print("="*80)

    try:
        client = secretmanager.SecretManagerServiceClient()
        parent = f"projects/{settings.GCP_PROJECT_ID}"

        # List all secrets
        secrets = list(client.list_secrets(request={"parent": parent}))

        print(f"✅ Connected to Secret Manager")
        print(f"   Project: {settings.GCP_PROJECT_ID}")

        if secrets:
            print(f"   Secrets found: {len(secrets)}")
            for secret in secrets:
                name = secret.name.split("/")[-1]
                print(f"     - {name}")

                # Check if we can access it
                try:
                    version_name = f"{secret.name}/versions/latest"
                    client.access_secret_version(request={"name": version_name})
                    print(f"       ✅ Accessible")
                except exceptions.PermissionDenied:
                    print(f"       ❌ Permission denied")
                except exceptions.NotFound:
                    print(f"       ⚠️  No versions found")

        else:
            print(f"   No secrets found")
            print(f"\n   Expected secrets:")
            print(f"     - {settings.SECRET_MANAGER_SECRET_KEY_NAME}")
            print(f"     - {settings.SECRET_MANAGER_API_CREDENTIALS_NAME}")
            print(f"\n   Create them with:")
            print(f"     echo -n 'your-secret-value' | gcloud secrets create <secret-name> --data-file=-")

        return True

    except exceptions.PermissionDenied:
        print("❌ Permission denied. Ensure service account has 'Secret Manager Secret Accessor' role")
        return False
    except Exception as e:
        print(f"❌ Error connecting to Secret Manager: {e}")
        return False


def check_service_account():
    """Check service account configuration."""
    print("\n" + "="*80)
    print("🔍 Checking Service Account...")
    print("="*80)

    if settings.GOOGLE_APPLICATION_CREDENTIALS:
        print(f"✅ Service account key configured")
        print(f"   Path: {settings.GOOGLE_APPLICATION_CREDENTIALS}")

        # Check if file exists
        key_path = Path(settings.GOOGLE_APPLICATION_CREDENTIALS)
        if key_path.exists():
            print(f"   ✅ File exists")
            return True
        else:
            print(f"   ❌ File not found")
            return False
    else:
        print("ℹ️  Using Workload Identity (no service account key needed)")
        print("   This is the recommended approach for Cloud Run")
        return True


def main():
    """Run all checks."""
    print("\n" + "="*80)
    print("🚀 GCP SETUP VERIFICATION")
    print("="*80)
    print(f"\nProject ID: {settings.GCP_PROJECT_ID}")
    print(f"Region: {settings.GCP_REGION}")
    print(f"Environment: {settings.ENVIRONMENT}")

    results = {
        "Service Account": check_service_account(),
        "Firestore": check_firestore(),
        "Cloud Storage": check_storage(),
        "Secret Manager": check_secret_manager(),
    }

    # Summary
    print("\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)

    all_passed = True
    for service, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {service}")
        if not passed:
            all_passed = False

    print("\n" + "="*80)

    if all_passed:
        print("✅ All checks passed! Your GCP setup is ready.")
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        print("\nCommon fixes:")
        print("1. Ensure service account has required IAM roles:")
        print("   - Cloud Datastore User")
        print("   - Storage Object Admin")
        print("   - Secret Manager Secret Accessor")
        print("\n2. Create missing resources:")
        print("   - Firestore: gcloud firestore databases create --region=europe-west1")
        print("   - Storage: gsutil mb -l europe-west1 gs://YOUR-BUCKET-NAME")
        print("   - Secrets: gcloud secrets create SECRET-NAME")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
