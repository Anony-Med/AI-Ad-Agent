"""Example API tests."""
import pytest
from httpx import AsyncClient
from main import app


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "app" in data
        assert "version" in data


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test root endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "docs" in data


# Add more tests for your endpoints
# Example:
# @pytest.mark.asyncio
# async def test_create_campaign():
#     """Test campaign creation."""
#     async with AsyncClient(app=app, base_url="http://test") as client:
#         # First login to get token
#         login_response = await client.post(
#             "/api/auth/login",
#             json={"email": "test@example.com", "password": "test123"}
#         )
#         token = login_response.json()["access_token"]
#
#         # Create campaign
#         response = await client.post(
#             "/api/campaigns",
#             headers={"Authorization": f"Bearer {token}"},
#             json={
#                 "name": "Test Campaign",
#                 "platform": "instagram",
#                 "ad_type": "video",
#                 "aspect_ratio": "9:16"
#             }
#         )
#         assert response.status_code == 201
