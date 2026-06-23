# app/routers/dashboard.py
#
# CHANGES vs original:
#   1. Pass `admin_email` to every TemplateResponse so base.html can
#      conditionally show the Admin navbar button.
#   2. Admin panel now also shows a "Login Attempts" section using the
#      existing login_count + last_login columns already in the User model.

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db, init_db, engine, Base
from app.core.security import get_current_user, get_optional_user, require_admin
from app.models.models import User, Report, SavedJob
from app.core.config import settings

router = APIRouter(tags=["Dashboard"])
from app.core.templates import templates
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = get_optional_user(request)

    if not current_user:
        return templates.TemplateResponse(request, "login.html", {})

    email = current_user["sub"]

    reports_result = await db.execute(
        select(Report)
        .where(Report.user_email == email)
        .order_by(Report.id.desc())
        .limit(3)
    )
    saved_reports = reports_result.scalars().all()

    jobs_result = await db.execute(
        select(SavedJob)
        .where(SavedJob.user_email == email)
        .order_by(SavedJob.id.desc())
        .limit(5)
    )
    saved_jobs_list = jobs_result.scalars().all()

    return templates.TemplateResponse(request, "dashboard.html", {
        "user": current_user,
        "reports": saved_reports,
        "saved_jobs": saved_jobs_list,
        # ── Pass admin email so base.html can show the Admin button ──
        "admin_email": settings.ADMIN_EMAIL,
    })


@router.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        current_user = get_current_user(request)
        require_admin(current_user)
    except HTTPException:
        return RedirectResponse(url="/")

    # All users ordered by most recent login (= most recent login attempt)
    users_result = await db.execute(
        select(User).order_by(User.last_login.desc())
    )
    users = users_result.scalars().all()

    # Total AI resume scans
    count_result = await db.execute(select(func.count()).select_from(Report))
    total_scans = count_result.scalar_one()

    # Total login attempts across all users
    login_attempts_result = await db.execute(
        select(func.sum(User.login_count))
    )
    total_login_attempts = login_attempts_result.scalar_one() or 0

    return templates.TemplateResponse(request, "admin.html", {
        "user": current_user,
        "users": users,
        "total_users": len(users),
        "total_scans": total_scans,
        "total_login_attempts": total_login_attempts,
        # ── Needed so base.html shows the Admin button while on /admin too ──
        "admin_email": settings.ADMIN_EMAIL,
    })


@router.get("/nuclear-reset")
async def nuclear_reset(request: Request):
    try:
        current_user = get_current_user(request)
        require_admin(current_user)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Admin access required for database reset")

    logger.warning("⚠️  NUCLEAR RESET initiated!")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All tables dropped")

    await init_db()
    logger.info("Tables recreated")

    return HTMLResponse(
        content="<h1>✅ DATABASE RESET SUCCESSFUL. All tables recreated. <a href='/'>Go Home</a></h1>"
    )