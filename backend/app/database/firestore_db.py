"""Firestore database operations."""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from app.config import settings
from app.models.enums import JobStatus, CampaignStatus, AdType

logger = logging.getLogger(__name__)


class FirestoreDB:
    """Firestore database service."""

    def __init__(self):
        """Initialize Firestore client."""
        try:
            # Use Application Default Credentials (same pattern as Unified API)
            # This automatically works with gcloud auth application-default login
            database_id = getattr(settings, 'FIRESTORE_DATABASE', 'ai-ad-agent')
            self.db = firestore.Client(
                project=settings.GCP_PROJECT_ID,
                database=database_id
            )
            logger.info(f"Firestore initialized successfully: {settings.GCP_PROJECT_ID}/{database_id}")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore: {e}")
            raise

    # ========================================================================
    # User Management
    # ========================================================================

    async def create_user(self, user_id: str, email: str, **extra_data) -> Dict[str, Any]:
        """Create a user record."""
        user_data = {
            "id": user_id,
            "email": email,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            **extra_data,
        }
        self.db.collection("users").document(user_id).set(user_data)
        return user_data

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        doc = self.db.collection("users").document(user_id).get()
        return doc.to_dict() if doc.exists else None

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email (used for login)."""
        docs = list(
            self.db.collection("users")
            .where(filter=FieldFilter("email", "==", email))
            .limit(1)
            .stream()
        )
        if docs:
            return docs[0].to_dict()
        return None

    async def update_user(self, user_id: str, **updates) -> Dict[str, Any]:
        """Update user data."""
        updates["updated_at"] = datetime.utcnow()
        self.db.collection("users").document(user_id).update(updates)
        return await self.get_user(user_id)

    # ========================================================================
    # Campaign Management
    # ========================================================================

    async def create_campaign(self, user_id: str, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new campaign."""
        doc_ref = self.db.collection("campaigns").document()
        campaign = {
            "id": doc_ref.id,
            "user_id": user_id,
            "status": CampaignStatus.DRAFT.value,
            "total_cost": 0.0,
            "asset_count": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            **campaign_data,
        }
        doc_ref.set(campaign)
        return campaign

    async def get_campaign(self, campaign_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get campaign by ID."""
        doc = self.db.collection("campaigns").document(campaign_id).get()
        if doc.exists:
            campaign = doc.to_dict()
            # Verify ownership
            if campaign.get("user_id") == user_id:
                return campaign
        return None

    async def list_campaigns(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List user's campaigns."""
        query = self.db.collection("campaigns").where(filter=FieldFilter("user_id", "==", user_id))

        if status:
            query = query.where(filter=FieldFilter("status", "==", status))

        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit).offset(offset)

        docs = query.stream()
        return [doc.to_dict() for doc in docs]

    async def update_campaign(
        self,
        campaign_id: str,
        user_id: str,
        **updates,
    ) -> Optional[Dict[str, Any]]:
        """Update campaign."""
        # Verify ownership first
        campaign = await self.get_campaign(campaign_id, user_id)
        if not campaign:
            return None

        updates["updated_at"] = datetime.utcnow()
        self.db.collection("campaigns").document(campaign_id).update(updates)
        return await self.get_campaign(campaign_id, user_id)

    async def delete_campaign(self, campaign_id: str, user_id: str) -> bool:
        """Delete campaign."""
        campaign = await self.get_campaign(campaign_id, user_id)
        if not campaign:
            return False

        self.db.collection("campaigns").document(campaign_id).delete()
        return True

    async def increment_campaign_cost(
        self,
        campaign_id: str,
        cost: float,
        increment_assets: bool = False,
    ):
        """Increment campaign total cost and optionally asset count."""
        doc_ref = self.db.collection("campaigns").document(campaign_id)
        updates = {
            "total_cost": firestore.Increment(cost),
            "updated_at": datetime.utcnow(),
        }
        if increment_assets:
            updates["asset_count"] = firestore.Increment(1)

        doc_ref.update(updates)

    # ========================================================================
    # Job Management
    # ========================================================================

    async def create_job(self, user_id: str, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a generation job record."""
        doc_ref = self.db.collection("jobs").document(job_data.get("job_id", None))
        job = {
            "user_id": user_id,
            "status": JobStatus.PENDING.value,
            "progress": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            **job_data,
        }
        doc_ref.set(job)
        return job

    async def get_job(self, job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID."""
        doc = self.db.collection("jobs").document(job_id).get()
        if doc.exists:
            job = doc.to_dict()
            if job.get("user_id") == user_id:
                return job
        return None

    async def update_job(self, job_id: str, **updates) -> Dict[str, Any]:
        """Update job status and data."""
        updates["updated_at"] = datetime.utcnow()
        if updates.get("status") == JobStatus.COMPLETED.value and "completed_at" not in updates:
            updates["completed_at"] = datetime.utcnow()

        self.db.collection("jobs").document(job_id).update(updates)
        doc = self.db.collection("jobs").document(job_id).get()
        return doc.to_dict()

    async def list_jobs(
        self,
        user_id: str,
        campaign_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List user's jobs."""
        query = self.db.collection("jobs").where(filter=FieldFilter("user_id", "==", user_id))

        if campaign_id:
            query = query.where(filter=FieldFilter("campaign_id", "==", campaign_id))
        if status:
            query = query.where(filter=FieldFilter("status", "==", status))

        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit).offset(offset)

        docs = query.stream()
        return [doc.to_dict() for doc in docs]

    # ========================================================================
    # Asset Management
    # ========================================================================

    async def create_asset(self, user_id: str, asset_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an asset record."""
        doc_ref = self.db.collection("assets").document()
        asset = {
            "id": doc_ref.id,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            **asset_data,
        }
        doc_ref.set(asset)
        return asset

    async def get_asset(self, asset_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get asset by ID."""
        doc = self.db.collection("assets").document(asset_id).get()
        if doc.exists:
            asset = doc.to_dict()
            if asset.get("user_id") == user_id:
                return asset
        return None

    async def list_assets(
        self,
        user_id: str,
        campaign_id: Optional[str] = None,
        ad_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List user's assets with filters."""
        query = self.db.collection("assets").where(filter=FieldFilter("user_id", "==", user_id))

        if campaign_id:
            query = query.where(filter=FieldFilter("campaign_id", "==", campaign_id))
        if ad_type:
            query = query.where(filter=FieldFilter("ad_type", "==", ad_type))
        if tags:
            query = query.where(filter=FieldFilter("tags", "array_contains_any", tags))

        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit).offset(offset)

        docs = query.stream()
        return [doc.to_dict() for doc in docs]

    async def update_asset(self, asset_id: str, user_id: str, **updates) -> Optional[Dict[str, Any]]:
        """Update asset."""
        asset = await self.get_asset(asset_id, user_id)
        if not asset:
            return None

        self.db.collection("assets").document(asset_id).update(updates)
        return await self.get_asset(asset_id, user_id)

    async def delete_asset(self, asset_id: str, user_id: str) -> bool:
        """Delete asset."""
        asset = await self.get_asset(asset_id, user_id)
        if not asset:
            return False

        self.db.collection("assets").document(asset_id).delete()
        return True

    # ========================================================================
    # Usage & Statistics
    # ========================================================================

    async def get_usage_stats(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get user usage statistics."""
        query = self.db.collection("jobs").where(filter=FieldFilter("user_id", "==", user_id))

        if start_date:
            query = query.where(filter=FieldFilter("created_at", ">=", start_date))
        if end_date:
            query = query.where(filter=FieldFilter("created_at", "<=", end_date))

        jobs = [doc.to_dict() for doc in query.stream()]

        # Calculate stats
        total_jobs = len(jobs)
        completed_jobs = sum(1 for j in jobs if j.get("status") == JobStatus.COMPLETED.value)
        failed_jobs = sum(1 for j in jobs if j.get("status") == JobStatus.FAILED.value)
        total_cost = sum(j.get("cost", 0) for j in jobs if j.get("cost"))

        # Group by model
        jobs_by_model = {}
        cost_by_model = {}
        for job in jobs:
            model = job.get("model", "unknown")
            jobs_by_model[model] = jobs_by_model.get(model, 0) + 1
            cost_by_model[model] = cost_by_model.get(model, 0) + job.get("cost", 0)

        # Group by type
        jobs_by_type = {}
        for job in jobs:
            ad_type = job.get("ad_type", "unknown")
            jobs_by_type[ad_type] = jobs_by_type.get(ad_type, 0) + 1

        return {
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "total_cost": total_cost,
            "jobs_by_model": jobs_by_model,
            "cost_by_model": cost_by_model,
            "jobs_by_type": jobs_by_type,
            "period_start": start_date,
            "period_end": end_date,
        }

    # ========================================================================
    # AI Ad Agent Jobs
    # ========================================================================

    async def save_ad_job(self, user_id: str, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save or update an ad creation job."""
        job_id = job_data.get("job_id")
        if not job_id:
            raise ValueError("job_id is required")

        doc_ref = self.db.collection("ad_jobs").document(job_id)

        # Convert datetime objects and enums to serializable format
        serializable_data = {}
        for key, value in job_data.items():
            if isinstance(value, datetime):
                serializable_data[key] = value
            elif hasattr(value, 'value'):  # Enum
                serializable_data[key] = value.value
            elif isinstance(value, list):
                # Handle list of objects (like VideoClip)
                serializable_data[key] = [
                    item.dict() if hasattr(item, 'dict') else item
                    for item in value
                ]
            elif hasattr(value, 'dict'):  # Pydantic models
                serializable_data[key] = value.dict()
            else:
                serializable_data[key] = value

        doc_ref.set(serializable_data, merge=True)
        logger.info(f"Saved ad job {job_id} for user {user_id}")
        return serializable_data

    async def get_ad_job(self, user_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        """Get an ad creation job by ID."""
        doc = self.db.collection("ad_jobs").document(job_id).get()
        if doc.exists:
            job = doc.to_dict()
            # Verify ownership
            if job.get("user_id") == user_id:
                return job
        return None

    async def list_ad_jobs(
        self,
        user_id: str,
        campaign_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List ad creation jobs for a user."""
        query = self.db.collection("ad_jobs").where(filter=FieldFilter("user_id", "==", user_id))

        if campaign_id:
            query = query.where(filter=FieldFilter("campaign_id", "==", campaign_id))

        query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit).offset(offset)

        docs = query.stream()
        return [doc.to_dict() for doc in docs]


# Singleton instance
_db_instance: Optional[FirestoreDB] = None


def get_db() -> FirestoreDB:
    """Get Firestore database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = FirestoreDB()
    return _db_instance
