"""Test script for streaming ad creation endpoint."""
import httpx
import base64
import json
import asyncio


async def test_stream_ad():
    """Test the /create-stream endpoint with real-time progress updates."""

    # Configuration
    BASE_URL = "http://localhost:8001"
    AVATAR_PATH = r"C:\Users\shrey\Desktop\projects\ai ad agent\Avatar.png"

    # Script for the ad
    script = """Tired of hurricanes, repairs, or just ready for a change?

Hi, I'm Heather with She Buys Houses - a woman-owned company helping homeowners sell as-is.

No repairs. No waiting. No stress.

Whether you're downsizing, moving closer to family, or simply ready to let go - you deserve a fair cash offer and a seamless, easy process.

Call 1-888-SHE-BUYS or visit SheBuysHousesCash.com.

We'll take care of everything - so you can move forward with peace of mind."""

    print("=" * 80)
    print("🎬 AI Ad Agent - Streaming Endpoint Test")
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

    # Step 2: Load avatar image
    print(f"🖼️  Loading avatar from: {AVATAR_PATH}")
    with open(AVATAR_PATH, "rb") as f:
        avatar_bytes = f.read()

    avatar_b64 = base64.b64encode(avatar_bytes).decode('utf-8')
    avatar_data_uri = f"data:image/png;base64,{avatar_b64}"
    print(f"✅ Avatar loaded ({len(avatar_b64)} chars base64)")
    print()

    # Step 3: Create streaming request
    request_data = {
        "script": script,
        "character_image": avatar_data_uri,
        "character_name": "Heather",
        "aspect_ratio": "16:9",
        "resolution": "720p"
    }

    print("📡 Starting streaming ad creation...")
    print("=" * 80)
    print()

    # Step 4: Stream the response
    final_video_url = None

    async with httpx.AsyncClient(timeout=None) as client:  # No timeout for streaming
        async with client.stream(
            "POST",
            f"{BASE_URL}/api/ad-agent/create-stream",
            json=request_data,
            headers={"Authorization": f"Bearer {token}"}
        ) as response:

            if response.status_code != 200:
                print(f"❌ Request failed: {response.status_code}")
                print(await response.aread())
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

    if final_video_url:
        print("=" * 80)
        print("🎉 Success! Your ad is ready!")
        print("=" * 80)
    else:
        print("=" * 80)
        print("⚠️  Ad creation did not complete successfully")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_stream_ad())
