"""Download and examine job files from GCS."""
from google.cloud import storage
import json
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT = "sound-invention-432122-m5"
BUCKET = "ai-ad-agent-videos"
JOB_ID = "ad_1762980163.250578"

print(f"📥 Downloading files for job: {JOB_ID}")
print("=" * 80)

try:
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)

    # Download gemini_prompt_generation.json
    prompt_gen_path = f"jobs/{JOB_ID}/gemini_prompt_generation.json"
    prompt_gen_blob = bucket.blob(prompt_gen_path)

    if prompt_gen_blob.exists():
        print(f"\n✅ Found: {prompt_gen_path}")
        prompt_gen_data = json.loads(prompt_gen_blob.download_as_text())
        print("\n📄 GEMINI PROMPT GENERATION DATA:")
        print("=" * 80)
        print(json.dumps(prompt_gen_data, indent=2))
    else:
        print(f"❌ Not found: {prompt_gen_path}")

    # Download gemini_parsed_prompts.json
    parsed_prompts_path = f"jobs/{JOB_ID}/gemini_parsed_prompts.json"
    parsed_prompts_blob = bucket.blob(parsed_prompts_path)

    if parsed_prompts_blob.exists():
        print(f"\n\n✅ Found: {parsed_prompts_path}")
        parsed_prompts_data = json.loads(parsed_prompts_blob.download_as_text())
        print("\n📄 GEMINI PARSED PROMPTS DATA:")
        print("=" * 80)
        print(json.dumps(parsed_prompts_data, indent=2))

        if isinstance(parsed_prompts_data, list):
            print(f"\n📊 Total prompts to generate: {len(parsed_prompts_data)}")
    else:
        print(f"❌ Not found: {parsed_prompts_path}")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
