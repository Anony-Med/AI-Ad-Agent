"""Client for interacting with the Unified Video/Image API."""
import logging
from typing import Optional, Dict, Any, List
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from app.config import settings
from app.models.schemas import UserLogin, UserRegister, Token, UserInfo

logger = logging.getLogger(__name__)


class UnifiedAPIError(Exception):
    """Custom exception for Unified API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: Any = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)
I

class UnifiedAPIClient:
    """Client for Unified API interactions."""

    def __init__(self):
        self.base_url = settings.UNIFIED_API_BASE_URL.rstrip("/")
        self.timeout = settings.UNIFIED_API_TIMEOUT
        self._token: Optional[str] = None

    def set_token(self, token: str):
        """Set the JWT token for authenticated requests."""
        self._token = token

    def _get_headers(self, authenticated: bool = True) -> Dict[str, str]:
        """Get request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if authenticated and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        authenticated: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic."""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(authenticated)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    **kwargs,
                )

                # Log request/response for debugging
                logger.debug(f"{method} {url} - Status: {response.status_code}")

                # Handle different status codes
                if response.status_code == 401:
                    raise UnifiedAPIError(
                        "Unauthorized - Invalid or expired token",
                        status_code=401,
                    )
                elif response.status_code == 403:
                    raise UnifiedAPIError(
                        "Forbidden - Insufficient permissions",
                        status_code=403,
                    )
                elif response.status_code == 404:
                    raise UnifiedAPIError(
                        "Resource not found",
                        status_code=404,
                    )
                elif response.status_code >= 500:
                    raise UnifiedAPIError(
                        "Unified API server error",
                        status_code=response.status_code,
                        detail=response.text,
                    )
                elif not response.is_success:
                    error_data = response.json() if response.text else {}
                    logger.error(f"Unified API error: status={response.status_code}, response={response.text[:500]}")
                    raise UnifiedAPIError(
                        error_data.get("error", error_data.get("detail", "Unknown error")),
                        status_code=response.status_code,
                        detail=error_data,
                    )

                return response.json()

            except httpx.RequestError as e:
                logger.error(f"Request error: {e}")
                raise UnifiedAPIError(f"Network error: {str(e)}")

    # ========================================================================
    # Authentication Endpoints
    # ========================================================================

    async def login(self, email: str, password: str) -> Token:
        """Login to get JWT token."""
        # Unified API expects username field, not email
        # Use email as username if it looks like an email, otherwise use as-is
        username = email.split("@")[0] if "@" in email else email
        data = {"username": username, "password": password}
        logger.info(f"Attempting login with username='{username}' (email parameter was='{email}')")
        response = await self._request(
            "POST",
            "/v1/auth/login",
            authenticated=False,
            json=data,
        )
        token = response.get("access_token") or response.get("token")
        if not token:
            raise UnifiedAPIError("No token in response")

        self.set_token(token)
        return Token(access_token=token, token_type="bearer")

    async def register(self, email: str, password: str, name: Optional[str] = None, username: Optional[str] = None) -> Token:
        """Register a new user."""
        data = {
            "email": email,
            "password": password,
            "username": username or email.split("@")[0],  # Use email prefix as username if not provided
        }
        if name:
            data["name"] = name

        response = await self._request(
            "POST",
            "/v1/auth/register",
            authenticated=False,
            json=data,
        )
        token = response.get("access_token") or response.get("token")
        if not token:
            raise UnifiedAPIError("No token in response")

        self.set_token(token)
        return Token(access_token=token, token_type="bearer")

    async def get_user_info(self) -> UserInfo:
        """Get current user information."""
        response = await self._request("GET", "/v1/auth/me")
        return UserInfo(**response)

    # ========================================================================
    # Video Generation Endpoints
    # ========================================================================

    async def create_video_job(self, **params) -> Dict[str, Any]:
        """Create a video generation job."""
        response = await self._request(
            "POST",
            "/v1/videos",
            json=params,
        )
        return response

    async def get_video_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get video job status."""
        response = await self._request("GET", f"/v1/videos/{job_id}")
        return response

    async def cancel_video_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel a video generation job."""
        response = await self._request("DELETE", f"/v1/videos/{job_id}")
        return response

    # ========================================================================
    # Image Generation Endpoints
    # ========================================================================

    async def create_image_job(self, **params) -> Dict[str, Any]:
        """Create an image generation job."""
        response = await self._request(
            "POST",
            "/v1/images",
            json=params,
        )
        return response

    async def get_image_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get image job status."""
        response = await self._request("GET", f"/v1/images/{job_id}")
        return response

    async def cancel_image_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel an image generation job."""
        response = await self._request("DELETE", f"/v1/images/{job_id}")
        return response

    # ========================================================================
    # History & Billing Endpoints
    # ========================================================================

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        job_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get generation history."""
        params = {"limit": limit, "offset": offset}
        if job_type:
            params["type"] = job_type

        response = await self._request("GET", "/v1/history", params=params)
        return response.get("jobs", response)

    async def get_billing_history(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get billing history."""
        params = {"limit": limit, "offset": offset}
        response = await self._request("GET", "/v1/billing/history", params=params)
        return response.get("records", response)

    # ========================================================================
    # Models Endpoint
    # ========================================================================

    async def get_models(self) -> List[Dict[str, Any]]:
        """Get available models."""
        response = await self._request("GET", "/v1/models")
        return response.get("models", response)


# Singleton instance
unified_api_client = UnifiedAPIClient()
