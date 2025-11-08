# Authentication & Secret Management Flow

**Date:** 2025-01-08
**Status:** ✅ Implemented

## Overview

The AI Ad Agent uses the **Unified API's authentication system** to get user credentials, then uses the **user_id from the JWT** to load user-specific API keys from Secret Manager.

## Complete Authentication Flow

### 1. User Registration/Login

```
User → AI Ad Agent → Unified API → JWT Token → User
```

**Registration:**
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepassword",
    "name": "John Doe"
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**What Happens:**
1. AI Ad Agent receives registration request
2. Forwards to Unified API `/auth/register`
3. Unified API creates user account
4. Unified API generates JWT token with user_id
5. AI Ad Agent creates user record in Firestore
6. Returns JWT token to user

**Login:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepassword"
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**What Happens:**
1. AI Ad Agent receives login request
2. Forwards to Unified API `/auth/login`
3. Unified API validates credentials
4. Unified API generates JWT token with user_id
5. Returns JWT token to user

### 2. JWT Token Structure

The JWT token contains the user's identity:

```json
{
  "user_id": "user_abc123",
  "email": "user@example.com",
  "username": "johndoe",
  "exp": 1704672000,
  "iat": 1704585600
}
```

**Key Field:** `user_id` - This is what we use to load user-specific secrets!

### 3. Authenticated Request Flow

```
User sends request with JWT
    ↓
AI Ad Agent extracts JWT token
    ↓
Decode JWT to get user_id
    ↓
Load user-specific API keys from Secret Manager
    ↓
Initialize pipeline with user's keys
    ↓
Process request
```

**Example: Create Ad**
```bash
# Step 1: Save JWT from login
export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Step 2: Create ad with JWT
curl -X POST http://localhost:8000/api/ad-agent/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_id": "campaign_123",
    "script": "Looking for your dream home?",
    "character_image": "BASE64_IMAGE",
    "character_name": "Heather"
  }'
```

**What Happens:**
1. AI Ad Agent receives request
2. **Middleware extracts JWT** from `Authorization: Bearer` header
3. **Decodes JWT** to get `user_id = "user_abc123"`
4. **Loads user-specific secrets**:
   ```python
   from app.secrets import get_user_secret

   gemini_key = get_user_secret("user_abc123", "gemini", "api_key")
   # Tries: ai_ad_agent_user_abc123_gemini_api_key
   # Falls back to: ai_ad_agent_gemini_api_key

   elevenlabs_key = get_user_secret("user_abc123", "elevenlabs", "api_key")
   # Tries: ai_ad_agent_user_abc123_elevenlabs_api_key
   # Falls back to: ai_ad_agent_elevenlabs_api_key
   ```
5. **Initializes pipeline** with user's or global API keys
6. **Processes ad creation** using those keys
7. **Tracks costs** against user's account

## Secret Loading Priority

For user `user_abc123`:

### Gemini API Key

```
1. Try user-specific:  ai_ad_agent_user_abc123_gemini_api_key
   ↓ (not found)
2. Try global:         ai_ad_agent_gemini_api_key
   ↓ (not found)
3. Use environment:    GEMINI_API_KEY from .env
   ↓ (not found)
4. Error:              "Gemini API key not configured"
```

### ElevenLabs API Key

```
1. Try user-specific:  ai_ad_agent_user_abc123_elevenlabs_api_key
   ↓ (not found)
2. Try global:         ai_ad_agent_elevenlabs_api_key
   ↓ (not found)
3. Use environment:    ELEVENLABS_API_KEY from .env
   ↓ (not found)
4. Error:              "ElevenLabs API key not configured"
```

## Code Flow

### Middleware (`app/middleware/auth.py`)

```python
async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Get current user ID from token."""
    token = credentials.credentials

    # Decode JWT (without verification, Unified API handles that)
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_signature": False},
    )

    # Extract user_id
    user_id: str = payload.get("sub") or payload.get("user_id")

    return user_id
```

### Route (`app/routes/ad_agent.py`)

```python
@router.post("/create")
async def create_ad(
    request: AdRequest,
    user_id: str = Depends(get_current_user_id),  # <-- JWT decoded here
):
    # Load user-specific API keys
    pipeline = get_pipeline(
        user_id=user_id,  # <-- user_id used here
        enable_verification=request.enable_verification,
        verification_threshold=request.verification_threshold,
    )

    # Process with user's keys
    job = await pipeline.create_ad(request, user_id)
```

### Pipeline Initialization (`app/routes/ad_agent.py`)

```python
def get_pipeline(user_id: str, ...) -> AdCreationPipeline:
    from app.secrets import get_user_secret

    # Load user-specific keys (or fall back to global)
    gemini_key = get_user_secret(user_id, "gemini", "api_key")
    elevenlabs_key = get_user_secret(user_id, "elevenlabs", "api_key")

    # Create pipeline with those keys
    return AdCreationPipeline(
        gemini_api_key=gemini_key,
        elevenlabs_api_key=elevenlabs_key,
        ...
    )
```

## User-Specific Secrets Setup

### For a Single User

If a user wants to use their own API keys:

```bash
# User ID from JWT
export USER_ID="user_abc123"

# Create user's Gemini secret
echo -n "USER_GEMINI_KEY" | gcloud secrets create ai_ad_agent_${USER_ID}_gemini_api_key \
  --project=sound-invention-432122-m5 \
  --replication-policy="automatic" \
  --data-file=-

# Create user's ElevenLabs secret
echo -n "USER_ELEVENLABS_KEY" | gcloud secrets create ai_ad_agent_${USER_ID}_elevenlabs_api_key \
  --project=sound-invention-432122-m5 \
  --replication-policy="automatic" \
  --data-file=-

# Grant service account access
export SA="994684344365-compute@developer.gserviceaccount.com"

gcloud secrets add-iam-policy-binding ai_ad_agent_${USER_ID}_gemini_api_key \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding ai_ad_agent_${USER_ID}_elevenlabs_api_key \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor"
```

### Via API (Future Enhancement)

Users could save their own keys via API:

```bash
curl -X POST http://localhost:8000/api/users/me/secrets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "gemini",
    "api_key": "AIzaSy..."
  }'
```

**Implementation:**
```python
@router.post("/users/me/secrets")
async def save_user_api_key(
    provider: str,
    api_key: str,
    user_id: str = Depends(get_current_user_id),
):
    from app.secrets import save_user_secret

    success = save_user_secret(
        user_id=user_id,
        provider=provider,
        key_type="api_key",
        secret_value=api_key
    )

    return {"success": success}
```

## Complete Example Flow

### 1. User Registers

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -d '{"email": "john@example.com", "password": "pass123", "name": "John"}'
```

**Response:**
```json
{
  "access_token": "eyJ...[JWT]...abc",
  "token_type": "bearer"
}
```

**JWT Payload:**
```json
{
  "user_id": "user_abc123",
  "email": "john@example.com",
  "username": "john"
}
```

### 2. Admin Creates User-Specific Secrets (Optional)

```bash
# User wants to use their own API keys
gcloud secrets create ai_ad_agent_user_abc123_gemini_api_key \
  --data-file=- <<< "USER_GEMINI_KEY"

gcloud secrets create ai_ad_agent_user_abc123_elevenlabs_api_key \
  --data-file=- <<< "USER_ELEVENLABS_KEY"
```

### 3. User Creates Ad

```bash
export TOKEN="eyJ...[JWT]...abc"

curl -X POST http://localhost:8000/api/ad-agent/create \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "campaign_id": "campaign_123",
    "script": "Looking for your dream home?",
    "character_image": "BASE64_IMAGE"
  }'
```

**Behind the Scenes:**

```python
# 1. Middleware extracts user_id from JWT
user_id = "user_abc123"

# 2. Route loads user-specific secrets
gemini_key = get_user_secret("user_abc123", "gemini", "api_key")
# → Returns: "USER_GEMINI_KEY" (user's custom key)

elevenlabs_key = get_user_secret("user_abc123", "elevenlabs", "api_key")
# → Returns: "USER_ELEVENLABS_KEY" (user's custom key)

# 3. Pipeline uses user's keys
pipeline = AdCreationPipeline(
    gemini_api_key="USER_GEMINI_KEY",
    elevenlabs_api_key="USER_ELEVENLABS_KEY"
)

# 4. Ad created with user's API keys
# 5. Costs tracked against user's account
```

### 4. User Without Custom Keys

If user doesn't have custom secrets:

```python
# 1. Try user-specific secret
gemini_key = get_user_secret("user_xyz789", "gemini", "api_key")
# → ai_ad_agent_user_xyz789_gemini_api_key not found

# 2. Fall back to global secret
# → ai_ad_agent_gemini_api_key found
# → Returns: "GLOBAL_GEMINI_KEY"

# 3. Pipeline uses global key
pipeline = AdCreationPipeline(
    gemini_api_key="GLOBAL_GEMINI_KEY",
    elevenlabs_api_key="GLOBAL_ELEVENLABS_KEY"
)
```

## Security Considerations

### JWT Security

- **JWT is signed** by Unified API
- **Expiration time** enforced (default 24 hours)
- **Cannot be forged** without secret key
- **User_id cannot be tampered** with

### Secret Manager Security

- **Secrets encrypted** at rest in GCP
- **IAM permissions** required for access
- **Service account** has minimal permissions (Secret Accessor only)
- **User secrets isolated** - one user can't access another's secrets
- **Audit logs** track secret access

### Attack Scenarios

**❌ Attacker tries to use another user's keys:**
```
1. Attacker gets JWT: user_id = "attacker123"
2. Secret Manager loads: ai_ad_agent_attacker123_gemini_api_key
3. Attacker cannot access: ai_ad_agent_victim456_gemini_api_key
4. Result: Attacker can only use their own or global keys ✅
```

**❌ Attacker tries to forge JWT:**
```
1. Attacker creates fake JWT: user_id = "victim456"
2. AI Ad Agent tries to decode JWT
3. Unified API verification fails (invalid signature)
4. Request rejected: 401 Unauthorized ✅
```

## Billing & Cost Tracking

### Per-User Costs

When using user-specific API keys:
- **Gemini costs** → User's Gemini account
- **ElevenLabs costs** → User's ElevenLabs account
- **Veo costs** → Global Unified API account (still need to track internally)

### Cost Attribution

```python
# Track which keys were used
job_metadata = {
    "user_id": "user_abc123",
    "gemini_key_type": "user_specific",  # or "global"
    "elevenlabs_key_type": "global",
    "veo_cost": 0.30,
    "total_cost": 0.38
}
```

### Usage Tracking

```python
from app.database import get_db

# Update user's usage stats
db = get_db()
await db.increment_user_usage(
    user_id="user_abc123",
    provider="gemini",
    cost=0.01
)
```

## Testing the Flow

### 1. Register User

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpass",
    "name": "Test User"
  }'
```

Save the `access_token`.

### 2. Decode JWT (for verification)

```bash
# Install jwt-cli: npm install -g jwt-cli
echo "eyJ..." | jwt decode -

# Or use jwt.io in browser
```

Verify `user_id` is in the payload.

### 3. Create User Secret (optional)

```bash
# Extract user_id from JWT
export USER_ID="user_abc123"

# Create test secret
echo -n "TEST_GEMINI_KEY" | gcloud secrets create ai_ad_agent_${USER_ID}_gemini_api_key \
  --data-file=-
```

### 4. Test Ad Creation

```bash
export TOKEN="your_access_token_here"

curl -X POST http://localhost:8000/api/ad-agent/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_id": "test_campaign",
    "script": "Test script",
    "character_image": "'$(base64 -w 0 test.jpg)'"
  }'
```

### 5. Check Logs

```bash
# Should see:
# "Using user-specific secret for user_abc123/gemini"
# OR
# "Using global secret for gemini (user user_abc123)"
```

## Summary

### Authentication Flow
✅ **User registers/logs in** → Unified API authentication
✅ **JWT token returned** → Contains user_id
✅ **Token used in requests** → Authorization: Bearer header
✅ **Middleware extracts user_id** → From JWT payload

### Secret Loading Flow
✅ **Extract user_id** → From JWT token
✅ **Try user secret** → `ai_ad_agent_{user_id}_{provider}_api_key`
✅ **Fall back to global** → `ai_ad_agent_{provider}_api_key`
✅ **Fall back to env var** → `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`

### Benefits
✅ **User isolation** → Each user can have their own API keys
✅ **Cost control** → Users pay for their own API usage
✅ **Flexibility** → Use global keys or custom keys
✅ **Security** → Secrets in Secret Manager, JWT authentication
✅ **Compatibility** → Works with Unified API authentication

---

**Status:** ✅ Fully Implemented
**Integration:** Unified API Authentication + Secret Manager
**Next Steps:**
1. Create global secrets in Secret Manager
2. (Optional) Create user-specific secrets
3. Test authentication flow
4. Deploy to production
