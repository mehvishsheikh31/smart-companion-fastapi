# app/core/security.py
#
# PURPOSE: All authentication logic lives here.
#
# YOUR OLD FLASK APPROACH:
#   session['user'] = user_info  # Stored user in a server-side cookie
#   if 'user' not in session: return redirect('/')  # Checked session in every route
#
# THE FASTAPI/JWT APPROACH:
#   When user logs in → we give them a JWT token (a signed string)
#   Client stores the token (in a cookie or localStorage)
#   On every request → client sends the token in a cookie
#   Server verifies the token's signature → no database lookup needed
#
# WHY JWT IS BETTER FOR APIs:
#   - Stateless: server doesn't store session data
#   - Works across multiple servers (important for Render's auto-scaling)
#   - Can be verified without a DB query
#
# JWT STRUCTURE: header.payload.signature
#   - Header: algorithm info
#   - Payload: the actual data (email, name, expiry time)
#   - Signature: HMAC hash of header+payload using your SECRET_KEY
#     → If anyone tampers with the payload, the signature won't match → rejected

from datetime import datetime, timedelta, timezone
from typing import Optional
import httpx  # Modern async HTTP client (replaces requests for async code)
from jose import JWTError, jwt  # python-jose for JWT
from fastapi import HTTPException, status, Cookie, Request
from app.core.config import settings

# ─────────────────────────────────────────────
# JWT FUNCTIONS
# ─────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT token containing the given data.
    
    Example:
        token = create_access_token({"sub": "user@email.com", "name": "Alice"})
        # Returns: "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOi..."
    
    The token contains:
        - sub: subject (user's email) — standard JWT claim
        - name, picture: user profile info
        - exp: expiry timestamp — jose checks this automatically
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    # Sign the token with our secret key
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Verify and decode a JWT token. Raises HTTPException if invalid.
    
    jose automatically checks:
        - Signature validity (was it signed with our SECRET_KEY?)
        - Expiry (is the exp claim in the past?)
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )


# ─────────────────────────────────────────────
# DEPENDENCY: GET CURRENT USER
# ─────────────────────────────────────────────
# This is what replaces: if 'user' not in session: return redirect('/')
#
# Usage in a route:
#   @router.get("/resume")
#   async def resume_page(current_user: dict = Depends(get_current_user)):
#       # current_user is the decoded token payload
#       email = current_user["sub"]
#
# If the token is missing or invalid, FastAPI automatically returns 401.
# You never need to check authentication manually in route handlers!

def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency that extracts and validates the JWT from cookies.
    
    We use cookies (not Authorization headers) to match your Flask session approach
    and because cookies work naturally with Jinja2 HTML templates.
    """
    token = request.cookies.get("access_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in."
        )
    
    # decode_access_token will raise HTTPException if token is bad
    payload = decode_access_token(token)
    
    # Verify the token has the required fields
    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    return payload  # {"sub": email, "name": "...", "picture": "...", ...}


def get_optional_user(request: Request) -> Optional[dict]:
    """
    Like get_current_user, but returns None instead of raising an error.
    Use for pages that work for both logged-in and anonymous users.
    """
    try:
        return get_current_user(request)
    except HTTPException:
        return None


def require_admin(current_user: dict) -> dict:
    """
    Check if current user is the admin.
    Call this inside admin routes after get_current_user.
    
    Usage:
        user = get_current_user(request)
        require_admin(user)  # raises 403 if not admin
    """
    if current_user.get("sub") != settings.ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# ─────────────────────────────────────────────
# GOOGLE OAUTH HELPERS
# ─────────────────────────────────────────────
# Your Flask app used authlib's flask_client which handled the redirect flow.
# We do the same thing manually here using httpx (async HTTP).
# The flow is always:
#   1. User clicks Login → we redirect to Google with our client_id
#   2. User approves → Google redirects to /auth/google/callback with ?code=...
#   3. We exchange the code for an access token
#   4. We use the access token to fetch user profile
#   5. We create our own JWT and set it as a cookie

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"

from urllib.parse import urlencode

def get_google_auth_url(state: str) -> str:
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online"
    }
    # urlencode properly encodes :// and / characters
    query_string = urlencode(params)
    return f"{GOOGLE_AUTH_URL}?{query_string}"
 

async def exchange_code_for_token(code: str) -> dict:
    """
    Exchange the authorization code (from Google's callback) for an access token.
    This is a server-to-server call — the user never sees this.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        })
        response.raise_for_status()
        return response.json()


async def get_google_user_info(access_token: str) -> dict:
    """
    Use the Google access token to fetch the user's profile.
    Returns: {"email": "...", "name": "...", "picture": "...", "id": "..."}
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()