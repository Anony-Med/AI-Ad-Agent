"""Quick test to verify dynamic prompt generation."""
import sys
import os
import asyncio

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.ad_agent.agents.prompt_generator import PromptGeneratorAgent

# Load environment
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

# Test script
test_script = """Tired of hurricanes, repairs, or just ready for a change?

Hi, I'm Heather with She Buys Houses — a woman-owned company helping homeowners sell as-is.

No repairs. No waiting. No stress."""

async def test_prompts():
    """Test dynamic prompt generation."""
    print("Testing dynamic prompt generation...")
    print(f"Script: {test_script}\n")

    # Initialize agent
    agent = PromptGeneratorAgent()

    # Generate prompts
    prompts, segments = await agent.generate_prompts_with_segments(
        script=test_script,
        character_name="Heather",
        max_clip_duration=7
    )

    print(f"\nGenerated {len(prompts)} prompts:\n")
    print("="*80)

    for i, (prompt, segment) in enumerate(zip(prompts, segments), 1):
        print(f"\nCLIP {i}:")
        print(f"Script: {segment}")
        print(f"\nPrompt: {prompt}")
        print("-"*80)

        # Check for movement keywords
        movement_keywords = ["walking", "gestur", "point", "demonstrat", "moving", "runs", "track", "follow"]
        has_movement = any(keyword in prompt.lower() for keyword in movement_keywords)

        if has_movement:
            print("[OK] Prompt includes MOVEMENT")
        else:
            print("[WARNING] Prompt may be STATIC")

    print("\n" + "="*80)
    print("Test complete!")

# Run test
if __name__ == "__main__":
    asyncio.run(test_prompts())
