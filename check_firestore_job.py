"""Check Firestore for job status and logs."""
import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from app.database.firestore_db import FirestoreDB

async def check_job_in_firestore(job_id: str):
    """Check job status in Firestore."""

    db = FirestoreDB()

    print(f"Searching Firestore for job: {job_id}")
    print("=" * 80)

    # Get job document directly (we don't have user_id, so query by job_id)
    from google.cloud import firestore
    job_doc_ref = db.db.collection("ad_jobs").document(job_id).get()

    if job_doc_ref.exists:
        job_doc = job_doc_ref.to_dict()
        print(f"\nJob Status: {job_doc.get('status')}")
        print(f"Created: {job_doc.get('created_at')}")
        print(f"Updated: {job_doc.get('updated_at')}")
        print(f"Campaign ID: {job_doc.get('campaign_id')}")
        print(f"User ID: {job_doc.get('user_id')}")
        print()

        # Check for error message
        if 'error_message' in job_doc:
            print(f"ERROR MESSAGE: {job_doc['error_message']}")
            print()

        # Print all fields
        print("\n--- Full Job Document ---")
        import json
        print(json.dumps(job_doc, indent=2, default=str))
    else:
        print(f"\nNo job found in Firestore with ID: {job_id}")
        print("This could mean:")
        print("  1. The job was never created in Firestore")
        print("  2. The job ID is incorrect")
        print("  3. The job was deleted")

if __name__ == "__main__":
    job_id = "ad_1762931168.047527"
    asyncio.run(check_job_in_firestore(job_id))
