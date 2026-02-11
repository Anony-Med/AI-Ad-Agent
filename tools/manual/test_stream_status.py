"""Quick test to check Cloud Run deployment status and test ad creation."""
import asyncio
import httpx
import base64
from pathlib import Path

BASE_URL = "https://ai-ad-agent-994684344365.europe-west1.run.app"
AVATAR_PATH = r"C:\Users\shrey\Desktop\projects\ai ad agent\Avatar.png"

async def main():
    """Test the deployment."""

    async with httpx.AsyncClient(timeout=600.0) as client:

        # Test health endpoint first
        print("Testing health endpoint...")
        try:
            health_response = await client.get(f"{BASE_URL}/api/ad-agent/health")
            print(f"Health check: {health_response.status_code}")
            print(health_response.json())
        except Exception as e:
            print(f"Health check failed: {e}")
            return

        print("\nAuthenticating...")
        # Login
        try:
            login_response = await client.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": "ad_agent", "password": "agent1234"}
            )
            if login_response.status_code == 200:
                token = login_response.json()["access_token"]
                print(f"Logged in successfully")
            else:
                print(f"Login failed: {login_response.status_code}")
                print(login_response.text)
                return
        except Exception as e:
            print(f"Login failed: {e}")
            return

        # Create a small test ad with just 1-2 clips
        print("\nCreating test ad with shorter script...")
        short_script = """Hi, I'm Heather with She Buys Houses. We help homeowners sell as-is. No repairs needed."""

        with open(AVATAR_PATH, "rb") as f:
            files = {"avatar": (Path(AVATAR_PATH).name, f, "image/png")}
            data = {
                "script": short_script,
                "character_name": "Heather",
                "aspect_ratio": "16:9",
                "resolution": "720p"
            }
            headers = {"Authorization": f"Bearer {token}"}

            try:
                print("Starting stream...")
                async with client.stream(
                    "POST",
                    f"{BASE_URL}/api/ad-agent/create-stream-upload",
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=600.0
                ) as response:
                    print(f"Response status: {response.status_code}")

                    if response.status_code != 200:
                        error_text = await response.aread()
                        print(f"ERROR: {error_text.decode()}")
                        return

                    # Parse SSE events
                    line_count = 0
                    async for line in response.aiter_lines():
                        line_count += 1
                        if line_count > 100:  # Limit output
                            print("... (more lines)")
                            break

                        if line.strip():
                            print(line)

            except Exception as e:
                print(f"\nStream failed: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
