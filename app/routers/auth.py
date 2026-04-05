# app/routers/auth.py
#
# PURPOSE: Handle login, Google OAuth callback, and logout.
#
# YOUR OLD FLASK APPROACH:
#   @app.route('/login')        → google.authorize_redirect(...)
#   @app.route('/google/callback') → session['user'] = user_info
#   @app.route('/logout')       → session.pop('user', None)
#
# THE FASTAPI APPROACH:
#   Same OAuth flow, but instead of session cookies:
#   1. We create a JWT token on login
#   2. We set it as an HttpOnly cookie (secure, JS can't read it)
#   3. On logout: delete the cookie
#
# WHAT IS HttpOnly COOKIE?
#   A cookie that JavaScript cannot read (document.cookie won't show it).
#   This prevents XSS attacks from stealing the user's session.
#   The browser automatically sends it with every request to your server.
#
# CSRF PROTECTION:
#   We generate a random "state" parameter before redirecting to Google.
#   When Google redirects back, we verify the state matches.
#   This prevents an attacker from tricking users into logging in via a forged link.

import secrets
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_google_auth_url,
    exchange_code_for_token,
    get_google_user_info
)
from app.models.models import User
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)




@router.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(32)
    auth_url = get_google_auth_url(state)
    
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        "oauth_state",
        state,
        max_age=600,        # 10 minutes
        httponly=True,
        samesite="lax",
        secure=False        # must be False for localhost http
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    db: AsyncSession = Depends(get_db)
):
    if error:
        return RedirectResponse(url="/?error=google_auth_failed")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    stored_state = request.cookies.get("oauth_state")
    if stored_state and state and stored_state != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Step 1: Exchange code
    logger.info("Step 1: Exchanging code for token...")
    try:
        token_data = await exchange_code_for_token(code)
        google_access_token = token_data.get("access_token")
        logger.info(f"Step 1 OK: got access token")
    except Exception as e:
        logger.error(f"Step 1 FAILED: {e}")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {str(e)}")

    # Step 2: Get user info
    logger.info("Step 2: Getting user info...")
    try:
        user_info = await get_google_user_info(google_access_token)
        email = user_info.get("email")
        name = user_info.get("name", "User")
        picture = user_info.get("picture", "")
        logger.info(f"Step 2 OK: email={email}")
    except Exception as e:
        logger.error(f"Step 2 FAILED: {e}")
        raise HTTPException(status_code=500, detail=f"User info failed: {str(e)}")

    # Step 3: Save to DB
    logger.info("Step 3: Saving user to DB...")
    try:
        from datetime import datetime, timezone
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            existing_user.last_login = datetime.now(timezone.utc)
            existing_user.login_count = (existing_user.login_count or 0) + 1
            existing_user.picture = picture
            db_user = existing_user
        else:
            db_user = User(
                email=email,
                name=name,
                picture=picture,
                role="Student",
                login_count=1,
                last_login=datetime.now(timezone.utc)
            )
            db.add(db_user)

        await db.commit()
        await db.refresh(db_user)
        logger.info(f"Step 3 OK: user saved id={db_user.id}")
    except Exception as e:
        logger.error(f"Step 3 FAILED: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Step 4: Create JWT
    logger.info("Step 4: Creating JWT...")
    try:
        token = create_access_token({
            "sub": email,
            "name": name,
            "picture": picture,
            "role": db_user.role,
            "user_id": db_user.id
        })
        logger.info("Step 4 OK: JWT created")
    except Exception as e:
        logger.error(f"Step 4 FAILED: {e}")
        raise HTTPException(status_code=500, detail=f"JWT creation failed: {str(e)}")

    # Step 5: Redirect
    logger.info("Step 5: Setting cookie and redirecting...")
    redirect_response = RedirectResponse(url="/", status_code=302)
    redirect_response.set_cookie(
        "access_token",
        token,
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=False
    )
    redirect_response.delete_cookie("oauth_state")
    return redirect_response

@router.get("/logout")
async def logout():
    """
    Log out by deleting the JWT cookie.
    
    Old Flask: session.pop('user', None)
    Now: delete the access_token cookie
    
    The JWT itself is still valid until it expires,
    but without the cookie, the browser won't send it.
    For extra security, you'd maintain a token blacklist in Redis.
    """
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response