"""Test ad creation on Cloud Run endpoint."""
import asyncio
import httpx
import base64
from pathlib import Path

BASE_URL = "https://ai-ad-agent-994684344365.europe-west1.run.app"
AVATAR_PATH = r"C:\Users\shrey\Desktop\projects\ai ad agent\Avatar.png"

script = """
    Tired of hurricanes, repairs, or just ready for a change? 
    Hi, I’m Heather with She Buys Houses — a woman-owned company helping homeowners sell as-is. 
    No repairs. No waiting. No stress. 
    Whether you’re downsizing, moving closer to family, or simply ready to let go — you deserve a fair cash offer and a seamless, easy process.
    Call 1-888-SHE-BUYS or visit SheBuysHousesCash.com. 
    We’ll take care of everything — so you can move forward with peace of mind.
    """

async def test_cloud_run_ad():
    """Test the Cloud Run /create-stream-upload endpoint."""

    async with httpx.AsyncClient(timeout=600.0) as client:

        print("=" * 80)
        print("TESTING CLOUD RUN AD CREATION")
        print("=" * 80)
        print(f"\nEndpoint: {BASE_URL}")
        print(f"Avatar: {AVATAR_PATH}")
        print(f"Script length: {len(script)} characters\n")

        # Step 1: Register/Login
        print("Step 1: Authenticating...")
        print("-" * 80)

        # Try to login first
        login_data = {
            "email": "ad_agent",
            "password": "agent1234"
        }

        try:
            login_response = await client.post(
                f"{BASE_URL}/api/auth/login",
                json=login_data
            )

            if login_response.status_code == 200:
                token = login_response.json()["access_token"]
                print(f"[OK] Logged in successfully")
            else:
                # Try to register
                print(f"Login failed, trying to register...")
                register_data = {
                    "email": "ad_agent",
                    "password": "agent1234",
                    "name": "AI Ad Agent Test User"
                }

                register_response = await client.post(
                    f"{BASE_URL}/api/auth/register",
                    json=register_data
                )

                if register_response.status_code == 200:
                    token = register_response.json()["access_token"]
                    print(f"[OK] Registered and logged in successfully")
                else:
                    print(f"[ERROR] Registration failed: {register_response.text}")
                    return

        except Exception as e:
            print(f"[ERROR] Authentication failed: {e}")
            return

        print(f"Access token: {token[:50]}...\n")

        # Step 2: Prepare file upload
        print("Step 2: Preparing avatar image...")
        print("-" * 80)

        avatar_path = Path(AVATAR_PATH)
        if not avatar_path.exists():
            print(f"[ERROR] Avatar file not found: {AVATAR_PATH}")
            return

        print(f"[OK] Found avatar: {avatar_path.name} ({avatar_path.stat().st_size} bytes)\n")

        # Step 3: Create ad with streaming
        print("Step 3: Creating ad (this will take several minutes)...")
        print("-" * 80)
        print("Streaming progress updates:\n")

        with open(AVATAR_PATH, "rb") as f:
            files = {"avatar": (avatar_path.name, f, "image/png")}
            data = {
                "script": script,
                "character_name": "Heather",
                "aspect_ratio": "16:9",
                "resolution": "720p"
            }

            headers = {"Authorization": f"Bearer {token}"}

            try:
                async with client.stream(
                    "POST",
                    f"{BASE_URL}/api/ad-agent/create-stream-upload",
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=600.0
                ) as response:

                    if response.status_code != 200:
                        error_text = await response.aread()
                        print(f"\n[ERROR] Request failed with status {response.status_code}")
                        print(f"Response: {error_text.decode()}")
                        return

                    # Parse SSE events
                    current_event = None
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            current_event = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            import json
                            data_str = line.split(":", 1)[1].strip()
                            try:
                                data = json.loads(data_str)

                                if current_event == "step1":
                                    print(f"\n[STEP 1] {data.get('message', '')}")
                                    print(f"  Progress: {data.get('progress', 0)}%")

                                elif current_event == "step1_complete":
                                    print(f"\n[STEP 1 COMPLETE] {data.get('message', '')}")
                                    print(f"  Total clips: {data.get('total_clips', 0)}")

                                elif current_event == "step2":
                                    print(f"\n[STEP 2] {data.get('message', '')}")
                                    print(f"  Progress: {data.get('progress', 0)}%")

                                elif current_event == "video_progress":
                                    current = data.get('current_clip', 0)
                                    total = data.get('total_clips', 0)
                                    print(f"  Generating video {current}/{total}...")

                                elif current_event == "step2_complete":
                                    print(f"\n[STEP 2 COMPLETE] {data.get('message', '')}")
                                    print(f"  Videos generated: {data.get('videos_generated', 0)}")

                                elif current_event == "step3":
                                    print(f"\n[STEP 3] {data.get('message', '')}")
                                    print(f"  Progress: {data.get('progress', 0)}%")

                                elif current_event == "step3_complete":
                                    print(f"\n[STEP 3 COMPLETE] {data.get('message', '')}")

                                elif current_event == "complete":
                                    print(f"\n{'=' * 80}")
                                    print("AD CREATION COMPLETE!")
                                    print("=" * 80)
                                    print(f"\nStatus: {data.get('status', '')}")
                                    print(f"Job ID: {data.get('job_id', '')}")
                                    print(f"\nFinal Video URL:")
                                    print(f"{data.get('final_video_url', '')}")
                                    print(f"\n{'=' * 80}")

                                elif current_event == "error":
                                    print(f"\n[ERROR] {data.get('message', '')}")
                                    print(f"\n{'=' * 80}")

                            except json.JSONDecodeError:
                                print(f"Could not parse: {data_str}")

            except Exception as e:
                print(f"\n[ERROR] Request failed: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_cloud_run_ad())
