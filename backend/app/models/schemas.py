"""Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .enums import (
    AdType,
    Platform,
    AspectRatio,
    JobStatus,
    ModelType,
    CampaignStatus,
)


# ============================================================================
# Authentication Schemas
# ============================================================================

class UserLogin(BaseModel):
    """User login request. Accepts username (treated as email) or email."""
    username: Optional[str] = None
    email: Optional[str] = None
    password: str


class UserRegister(BaseModel):
    """User registration request."""
    email: str
    password: str
    name: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None


class Token(BaseModel):
    """JWT token response with user info."""
    access_token: str
    token_type: str = "bearer"
    user_id: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None


class UserInfo(BaseModel):
    """User information."""
    user_id: str
    email: str
    username: Optional[str] = None
    name: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


class UserUpdate(BaseModel):
    """User profile update request."""
    email: Optional[str] = None
    name: Optional[str] = None
    full_name: Optional[str] = None


# ============================================================================
# Campaign Schemas
# ============================================================================

class CampaignBase(BaseModel):
    """Base campaign model."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    platform: Platform
    ad_type: AdType
    aspect_ratio: AspectRatio
    target_audience: Optional[str] = None
    budget: Optional[float] = None
    tags: List[str] = Field(default_factory=list)


class CampaignCreate(CampaignBase):
    """Create campaign request."""
    pass


class CampaignUpdate(BaseModel):
    """Update campaign request."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    platform: Optional[Platform] = None
    status: Optional[CampaignStatus] = None
    target_audience: Optional[str] = None
    budget: Optional[float] = None
    tags: Optional[List[str]] = None


class Campaign(CampaignBase):
    """Campaign response."""
    id: str
    user_id: str
    status: CampaignStatus = CampaignStatus.DRAFT
    total_cost: float = 0.0
    asset_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Generation Schemas
# ============================================================================

class VideoGenerationRequest(BaseModel):
    """Video generation request."""
    campaign_id: str
    prompt: str = Field(..., min_length=1, max_length=2000)
    model: ModelType
    aspect_ratio: Optional[AspectRatio] = AspectRatio.RATIO_16_9
    duration: Optional[int] = Field(default=5, ge=1, le=30)
    style: Optional[str] = None
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    first_frame_image_url: Optional[str] = None
    last_frame_image_url: Optional[str] = None
    extra_params: Optional[Dict[str, Any]] = None


class ImageGenerationRequest(BaseModel):
    """Image generation request."""
    campaign_id: str
    prompt: str = Field(..., min_length=1, max_length=2000)
    model: ModelType
    aspect_ratio: Optional[AspectRatio] = AspectRatio.RATIO_1_1
    style: Optional[str] = None
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    num_images: Optional[int] = Field(default=1, ge=1, le=4)
    extra_params: Optional[Dict[str, Any]] = None


class JobResponse(BaseModel):
    """Generation job response."""
    job_id: str
    campaign_id: str
    ad_type: AdType
    status: JobStatus
    progress: Optional[int] = None
    model: ModelType
    prompt: str
    output_urls: Optional[List[str]] = None
    error_message: Optional[str] = None
    cost: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


# ============================================================================
# Asset Schemas
# ============================================================================

class Asset(BaseModel):
    """Generated asset model."""
    id: str
    campaign_id: str
    job_id: str
    user_id: str
    ad_type: AdType
    model: ModelType
    prompt: str
    url: str
    gcs_path: Optional[str] = None
    thumbnail_url: Optional[str] = None
    aspect_ratio: AspectRatio
    duration: Optional[int] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    cost: float
    tags: List[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AssetFilter(BaseModel):
    """Asset filtering parameters."""
    campaign_id: Optional[str] = None
    ad_type: Optional[AdType] = None
    model: Optional[ModelType] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    tags: Optional[List[str]] = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


# ============================================================================
# Billing & Usage Schemas
# ============================================================================

class UsageStats(BaseModel):
    """Usage statistics."""
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    total_cost: float
    jobs_by_model: Dict[str, int]
    cost_by_model: Dict[str, float]
    jobs_by_type: Dict[str, int]
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class BillingRecord(BaseModel):
    """Billing record."""
    id: str
    user_id: str
    job_id: str
    amount: float
    model: str
    ad_type: str
    description: str
    created_at: datetime


# ============================================================================
# Prompt Builder Schemas
# ============================================================================

class PromptTemplate(BaseModel):
    """Prompt template for different ad types."""
    id: str
    name: str
    category: str
    template: str
    variables: List[str]
    example: str
    recommended_models: List[ModelType]


class PromptEnhanceRequest(BaseModel):
    """Request to enhance a prompt."""
    prompt: str
    ad_type: AdType
    platform: Platform
    style: Optional[str] = None


class PromptEnhanceResponse(BaseModel):
    """Enhanced prompt response."""
    original_prompt: str
    enhanced_prompt: str
    suggestions: List[str]


# ============================================================================
# Model Info Schemas
# ============================================================================

class ModelInfo(BaseModel):
    """AI model information."""
    id: str
    name: str
    type: str
    description: Optional[str] = None
    supported_aspect_ratios: List[str]
    max_duration: Optional[int] = None
    price_per_generation: Optional[float] = None
    capabilities: List[str]


# ============================================================================
# Common Response Schemas
# ============================================================================

class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
