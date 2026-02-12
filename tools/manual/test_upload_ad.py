"""Test script for file upload streaming endpoint - MUCH EASIER!"""
import httpx
import json
import asyncio


async def test_upload_ad():
    """Test the /create-stream-upload endpoint with file upload."""

    # Configuration
    BASE_URL = "http://localhost:8001"
    AVATAR_PATH = r"/Users/ar2427/Downloads/WhatsApp Image 2026-01-13 at 12.56.03.jpeg"

    # Script for the ad
    script = """I Was Done Stressing Over Repairs. 

Stop worrying. Get your free offer at shebuyshousescash.com or call 1-888-SHE-BUYS."""

    print("=" * 80)
    print("🎬 AI Ad Agent - File Upload Test (EASIER!)")
    print("=" * 80)
    print()

    # Step 1: Login
    print("🔐 Logging in...")
    async with httpx.AsyncClient(timeout=300) as client:
        login_response = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "ad_agent",
                "password": "agent1234"
            }
        )

        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.text}")
            return

        token = login_response.json()["access_token"]
        print(f"✅ Logged in successfully")
        print()

    # Step 2: Prepare file upload (NO BASE64 CONVERSION NEEDED!)
    print(f"🖼️  Using avatar: {AVATAR_PATH}")
    print("✅ No base64 conversion required!")
    print()

    # Step 3: Create streaming request with file upload
    files = {
        "avatar": open(AVATAR_PATH, "rb")
    }

    data = {
        "script": script,
        "character_name": "Heather",
        "aspect_ratio": "16:9",
        "resolution": "720p"
    }

    print("📡 Starting streaming ad creation with file upload...")
    print("=" * 80)
    print()

    # Step 4: Stream the response
    final_video_url = None

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/api/ad-agent/create-stream-upload",
            files=files,
            data=data,
            headers={"Authorization": f"Bearer {token}"}
        ) as response:

            if response.status_code != 200:
                print(f"❌ Request failed: {response.status_code}")
                error_text = await response.aread()
                print(error_text.decode())
                return

            # Parse Server-Sent Events
            current_event = None
            async for line in response.aiter_lines():
                line = line.strip()

                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_str = line.split(":", 1)[1].strip()
                    try:
                        data = json.loads(data_str)

                        # Print progress based on event type
                        if current_event == "step1":
                            print(f"📝 Step 1/5: {data['message']}")

                        elif current_event == "step1_complete":
                            print(f"✅ Step 1 Complete - Generated {data['total_clips']} prompts")
                            print()

                        elif current_event == "step2_clip":
                            clip_num = data['current_clip']
                            total = data['total_clips']
                            print(f"🎬 Step 2/5: Generating clip {clip_num}/{total}... ({data['progress']}%)")

                        elif current_event == "step3":
                            print()
                            print(f"🔗 Step 3/5: {data['message']}")

                        elif current_event == "step4":
                            print(f"🎤 Step 4/5: {data['message']}")

                        elif current_event == "step5":
                            print(f"🎯 Step 5/5: {data['message']}")

                        elif current_event == "complete":
                            print()
                            print("=" * 80)
                            print(f"✅ AD CREATION COMPLETED!")
                            print("=" * 80)
                            print()
                            print(f"Status: {data['status']}")
                            print(f"Job ID: {data['job_id']}")
                            print()
                            print(f"📹 Final Video URL:")
                            print(data['final_video_url'])
                            print()
                            final_video_url = data['final_video_url']

                        elif current_event == "error":
                            print()
                            print(f"❌ ERROR: {data['message']}")
                            print()

                    except json.JSONDecodeError:
                        print(f"⚠️  Failed to parse: {data_str}")

    # Close file
    files["avatar"].close()

    if final_video_url:
        print("=" * 80)
        print("🎉 Success! Your ad is ready!")
        print("=" * 80)
        print()
        print("💡 This was MUCH easier with file upload!")
        print("   - No base64 encoding needed")
        print("   - Smaller payload size")
        print("   - Standard multipart/form-data")
    else:
        print("=" * 80)
        print("⚠️  Ad creation did not complete successfully")
        print("=" * 80)


if __name__ == "__main__":
    print()
    print("💡 TIP: This endpoint uses file upload (multipart/form-data)")
    print("   Much easier than base64! Just upload the image file directly.")
    print()
    asyncio.run(test_upload_ad())
