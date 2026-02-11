"""Helper to create proper request body for create-stream endpoint."""
import base64
import json
from pathlib import Path

# Configuration
AVATAR_PATH = "Avatar.png"
SCRIPT = """Hi, I'm Heather with She Buys Houses. We help homeowners sell their properties as-is, with no repairs needed. Whether you're facing foreclosure, inherited a property, or just need to sell fast, we can help. We'll make you a fair cash offer and close on your timeline. Call us today for a free consultation."""

CHARACTER_NAME = "Heather"
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs default voice (Rachel)
ASPECT_RATIO = "16:9"
RESOLUTION = "720p"

def create_request_body():
    """Create the request body with base64-encoded image."""

    # Read and encode avatar image
    avatar_file = Path(AVATAR_PATH)

    if not avatar_file.exists():
        print(f"❌ Avatar file not found: {AVATAR_PATH}")
        print("Please provide an avatar image file")
        return None

    print(f"✅ Reading avatar: {AVATAR_PATH}")

    with open(avatar_file, "rb") as f:
        avatar_bytes = f.read()

    # Encode to base64
    avatar_b64 = base64.b64encode(avatar_bytes).decode('utf-8')

    # Determine mime type from file extension
    if avatar_file.suffix.lower() in ['.jpg', '.jpeg']:
        mime_type = "image/jpeg"
    else:
        mime_type = "image/png"

    # Create data URI
    character_image = f"data:{mime_type};base64,{avatar_b64}"

    print(f"✅ Image encoded ({len(avatar_b64)} chars)")

    # Create request body
    request_body = {
        "script": SCRIPT,
        "character_image": character_image,
        "character_name": CHARACTER_NAME,
        "voice_id": VOICE_ID,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION
    }

    # Save to file for easy copy-paste
    with open("request_body.json", "w", encoding='utf-8') as f:
        json.dump(request_body, f, indent=2)

    print(f"\n✅ Request body saved to: request_body.json")
    print(f"\n📝 Request Details:")
    print(f"   Script length: {len(SCRIPT)} chars")
    print(f"   Character: {CHARACTER_NAME}")
    print(f"   Voice ID: {VOICE_ID}")
    print(f"   Aspect ratio: {ASPECT_RATIO}")
    print(f"   Resolution: {RESOLUTION}")
    print(f"   Image data URI length: {len(character_image)} chars")

    # Also create a compact version for Swagger UI
    # (Some UIs don't handle large JSON well)
    print(f"\n📋 For Swagger UI:")
    print(f"   1. Open the request_body.json file")
    print(f"   2. Copy the entire JSON content")
    print(f"   3. Paste into Swagger UI request body")

    return request_body

def show_voice_options():
    """Show available ElevenLabs voice options."""
    print("\n🎤 Popular ElevenLabs Voice IDs:")
    print("=" * 60)
    voices = {
        "21m00Tcm4TlvDq8ikWAM": "Rachel - Young female, American",
        "ErXwobaYiN019PkySvjV": "Antoni - Well-rounded male",
        "VR6AewLTigWG4xSOukaG": "Arnold - Crisp male, American",
        "pNInz6obpgDQGcFmaJgB": "Adam - Deep male, American",
        "yoZ06aMxZJJ28mfd3POQ": "Sam - Dynamic male, American",
        "EXAVITQu4vr4xnSDxMaL": "Bella - Soft female, American",
        "MF3mGyEYCl7XYWbV9V6O": "Elli - Emotional female, American",
        "TxGEqnHWrfWFTfGW9XjX": "Josh - Young male, American",
        "AZnzlk1XvdvUeBnXmlld": "Domi - Strong female, American",
        "GBv7mTt0atIp3Br8iCZE": "Thomas - Calm male, American",
    }

    for voice_id, description in voices.items():
        print(f"   {voice_id}: {description}")

    print("\n💡 To use a different voice, change VOICE_ID in this script")
    print("   Or set voice_id to None to use default voice enhancement")

if __name__ == "__main__":
    print("🎬 Create Stream Request Body Generator")
    print("=" * 60)
    print()

    # Edit these variables at the top of the script:
    print("📝 Current Configuration:")
    print(f"   Script: {SCRIPT[:100]}...")
    print(f"   Avatar: {AVATAR_PATH}")
    print(f"   Character: {CHARACTER_NAME}")
    print(f"   Voice: {VOICE_ID}")
    print()

    # Generate request body
    request = create_request_body()

    if request:
        print("\n✅ Ready to use!")
        print("\n🚀 Next Steps:")
        print("   1. Open request_body.json")
        print("   2. Copy the entire JSON content")
        print("   3. Go to Swagger UI: /api/ad-agent/create-stream")
        print("   4. Paste into the request body")
        print("   5. Click Execute")

    # Show voice options
    show_voice_options()
