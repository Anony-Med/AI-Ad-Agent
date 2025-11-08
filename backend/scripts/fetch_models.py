"""
Script to fetch all available models from Unified API.

This script logs in to the Unified API and retrieves all available models
for video and image generation, saving them to a JSON file.

Usage:
    python scripts/fetch_models.py --email <email> --password <password>
    python scripts/fetch_models.py  # Will prompt for credentials
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List
import argparse
from getpass import getpass

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.unified_api_client import unified_api_client, UnifiedAPIError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def fetch_models(email: str, password: str) -> Dict[str, Any]:
    """
    Login and fetch all available models from Unified API.

    Args:
        email: User email
        password: User password

    Returns:
        Dictionary containing all models information
    """
    try:
        # Login to get JWT token
        logger.info("Logging in to Unified API...")
        token = await unified_api_client.login(email, password)
        logger.info(f"✅ Login successful! Token: {token.access_token[:20]}...")

        # Fetch available models
        logger.info("Fetching available models...")
        models = await unified_api_client.get_models()

        logger.info(f"✅ Found {len(models)} models")

        # Organize models by type
        video_models = []
        image_models = []
        other_models = []

        for model in models:
            model_type = model.get("type", "").lower()
            if "video" in model_type:
                video_models.append(model)
            elif "image" in model_type:
                image_models.append(model)
            else:
                other_models.append(model)

        result = {
            "total_models": len(models),
            "video_models": video_models,
            "image_models": image_models,
            "other_models": other_models,
            "all_models": models,
        }

        return result

    except UnifiedAPIError as e:
        logger.error(f"❌ Unified API Error: {e.message}")
        if e.status_code == 401:
            logger.error("Invalid credentials. Please check your email and password.")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        raise


def print_models_summary(models_data: Dict[str, Any]):
    """Print a summary of available models."""
    print("\n" + "="*80)
    print("📊 UNIFIED API MODELS SUMMARY")
    print("="*80)

    print(f"\n📈 Total Models: {models_data['total_models']}")
    print(f"🎬 Video Models: {len(models_data['video_models'])}")
    print(f"🖼️  Image Models: {len(models_data['image_models'])}")
    print(f"🔧 Other Models: {len(models_data['other_models'])}")

    # Video Models
    if models_data['video_models']:
        print("\n" + "-"*80)
        print("🎬 VIDEO MODELS:")
        print("-"*80)
        for model in models_data['video_models']:
            print(f"\n  Name: {model.get('name', 'N/A')}")
            print(f"  ID: {model.get('id', 'N/A')}")
            print(f"  Type: {model.get('type', 'N/A')}")
            if model.get('description'):
                print(f"  Description: {model['description']}")
            if model.get('supported_aspect_ratios'):
                print(f"  Aspect Ratios: {', '.join(model['supported_aspect_ratios'])}")
            if model.get('max_duration'):
                print(f"  Max Duration: {model['max_duration']}s")
            if model.get('price_per_generation'):
                print(f"  Price: ${model['price_per_generation']}")

    # Image Models
    if models_data['image_models']:
        print("\n" + "-"*80)
        print("🖼️  IMAGE MODELS:")
        print("-"*80)
        for model in models_data['image_models']:
            print(f"\n  Name: {model.get('name', 'N/A')}")
            print(f"  ID: {model.get('id', 'N/A')}")
            print(f"  Type: {model.get('type', 'N/A')}")
            if model.get('description'):
                print(f"  Description: {model['description']}")
            if model.get('supported_aspect_ratios'):
                print(f"  Aspect Ratios: {', '.join(model['supported_aspect_ratios'])}")
            if model.get('price_per_generation'):
                print(f"  Price: ${model['price_per_generation']}")

    print("\n" + "="*80)


def save_models_to_file(models_data: Dict[str, Any], output_file: str):
    """Save models data to JSON file."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(models_data, f, indent=2, ensure_ascii=False)

    logger.info(f"✅ Models data saved to: {output_path}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Fetch models from Unified API")
    parser.add_argument("--email", help="Email for login")
    parser.add_argument("--password", help="Password for login")
    parser.add_argument(
        "--output",
        default="data/models.json",
        help="Output file path (default: data/models.json)"
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Don't print summary to console"
    )

    args = parser.parse_args()

    # Get credentials
    email = args.email or input("Email: ")
    password = args.password or getpass("Password: ")

    try:
        # Fetch models
        models_data = await fetch_models(email, password)

        # Print summary
        if not args.no_summary:
            print_models_summary(models_data)

        # Save to file
        save_models_to_file(models_data, args.output)

        print(f"\n✅ Success! Models data saved to {args.output}")
        return 0

    except Exception as e:
        logger.error(f"❌ Failed to fetch models: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
