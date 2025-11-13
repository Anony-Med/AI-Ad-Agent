"""Test Gemini prompt generation locally."""
import asyncio
import sys
import os
import json
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

from app.ad_agent.clients.gemini_client import GeminiClient


async def test_prompt_generation():
    """Test generating Veo prompts for the script."""

    script = """Tired of hurricanes, repairs, or just ready for a change?

Hi, I'm Heather with She Buys Houses — a woman-owned company helping homeowners sell as-is.

No repairs. No waiting. No stress.

Whether you're downsizing, moving closer to family, or simply ready to let go — you deserve a fair cash offer and a seamless, easy process.

Call 1-888-SHE-BUYS or visit SheBuysHousesCash.com.

We'll take care of everything — so you can move forward with peace of mind."""

    character_name = "Heather"

    print("=" * 80)
    print("TESTING GEMINI PROMPT GENERATION")
    print("=" * 80)
    print(f"\nScript:\n{script}\n")
    print(f"Character: {character_name}\n")
    print("=" * 80)

    # Check if API key is available
    api_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_AI_API_KEY or GEMINI_API_KEY environment variable required")
        print("\nOptions:")
        print("1. Add GOOGLE_AI_API_KEY=your_key to backend/.env")
        print("2. Set environment variable: set GOOGLE_AI_API_KEY=your_key")
        print("3. Run: set GOOGLE_AI_API_KEY=your_key && python test_gemini_prompts.py")
        return

    # Initialize Gemini client
    try:
        client = GeminiClient()
        print("✅ Gemini client initialized\n")
    except Exception as e:
        print(f"ERROR: Failed to initialize Gemini client: {e}")
        return

    # Generate prompts with segments
    print("🔄 Generating Veo prompts with script segments...\n")

    try:
        prompts, segments = await client.generate_veo_prompts_with_segments(
            script=script,
            character_name=character_name
        )

        print("=" * 80)
        print(f"✅ Generated {len(prompts)} prompts\n")

        # Display results
        for i, (prompt, segment) in enumerate(zip(prompts, segments)):
            print(f"\n{'='*80}")
            print(f"CLIP {i + 1}")
            print(f"{'='*80}")

            print(f"\n📝 VISUAL PROMPT (what Veo sees):")
            print(f"{prompt}")

            print(f"\n🗣️  SCRIPT SEGMENT (what avatar speaks):")
            print(f'"{segment}"')

            print(f"\n🎬 COMBINED PROMPT (sent to Veo):")
            combined = f'{prompt} The character speaks: "{segment}"'
            print(f"{combined}")

        # Save to JSON for review
        output = {
            "character_name": character_name,
            "original_script": script,
            "total_clips": len(prompts),
            "clips": []
        }

        for i, (prompt, segment) in enumerate(zip(prompts, segments)):
            combined = f'{prompt} The character speaks: "{segment}"'
            output["clips"].append({
                "clip_number": i + 1,
                "visual_prompt": prompt,
                "script_segment": segment,
                "combined_prompt_to_veo": combined
            })

        with open('test_veo_prompts_output.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 80)
        print(f"✅ Saved full output to: test_veo_prompts_output.json")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error generating prompts: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_prompt_generation())
