"""Test if a specific service account has Veo 3.1 access."""
import asyncio
import sys
from pathlib import Path
from google.auth import impersonated_credentials
from google.auth import default
import google.auth.transport.requests

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.veo_client import DirectVeoClient

async def test_service_account_veo(service_account_email: str):
    """Test Veo API access with a specific service account."""

    print(f"Testing Veo 3.1 access for: {service_account_email}")
    print("=" * 80)

    try:
        # Get default credentials (your user account)
        source_credentials, project = default()

        # Create impersonated credentials
        target_scopes = ['https://www.googleapis.com/auth/cloud-platform']

        print(f"\nImpersonating service account...")
        target_credentials = impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=service_account_email,
            target_scopes=target_scopes,
            lifetime=300  # 5 minutes
        )

        # Force token refresh
        auth_req = google.auth.transport.requests.Request()
        target_credentials.refresh(auth_req)

        print(f"[OK] Successfully impersonated {service_account_email}")
        print(f"[OK] Access token obtained")

        # Now try to use Veo API with these credentials
        print("\nAttempting Veo API call...")

        # Create a simple test prompt
        test_prompt = "A person walking in a park, camera following from behind"

        # Create a small test image (1x1 pixel)
        import base64
        # Tiny 1x1 red PNG
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="

        # Create Veo client and inject the impersonated credentials
        veo_client = DirectVeoClient()
        veo_client._credentials = target_credentials
        veo_client._access_token = target_credentials.token

        print(f"\nCalling Veo API with prompt: '{test_prompt}'")
        print("This will test if the service account is whitelisted for Veo 3.1...")

        # Try to create a video job
        try:
            job_name = await veo_client.create_video_job(
                prompt=test_prompt,
                character_image_b64=test_image_b64,
                duration_seconds=5,
            )

            print(f"\n[SUCCESS] Service account HAS Veo 3.1 access!")
            print(f"Job created: {job_name}")
            print(f"\nThis service account can be used for Cloud Run!")
            return True

        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg or "Forbidden" in error_msg:
                print(f"\n[FAILED] 403 Forbidden")
                print(f"Service account does NOT have Veo 3.1 whitelist access")
                print(f"Error: {error_msg}")
                return False
            else:
                print(f"\n[UNKNOWN ERROR] {error_msg}")
                print("This might be a different issue (not permissions)")
                return None

    except Exception as e:
        print(f"\n[ERROR] Error during impersonation: {e}")
        return None

async def main():
    """Test both candidate service accounts."""

    service_accounts = [
        "viral-video-automation@sound-invention-432122-m5.iam.gserviceaccount.com",
        "for-veo-3-testing@sound-invention-432122-m5.iam.gserviceaccount.com",
    ]

    results = {}

    for sa in service_accounts:
        print("\n\n" + "=" * 80)
        result = await test_service_account_veo(sa)
        results[sa] = result
        print("=" * 80)

    # Summary
    print("\n\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for sa, result in results.items():
        status = "[HAS ACCESS]" if result else "[NO ACCESS]" if result is False else "[UNKNOWN]"
        print(f"{sa}")
        print(f"  Status: {status}\n")

    # Recommendation
    working_accounts = [sa for sa, result in results.items() if result]
    if working_accounts:
        print("\n[RECOMMENDATION]")
        print(f"Use this service account for Cloud Run: {working_accounts[0]}")
    else:
        print("\n[NO ACCESS FOUND]")
        print("No service accounts have Veo 3.1 access")
        print("You'll need to request whitelist access from Google")

if __name__ == "__main__":
    asyncio.run(main())
