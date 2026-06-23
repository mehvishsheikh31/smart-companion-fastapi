# app/routers/dashboard.py
#
# PURPOSE: Home dashboard, admin panel, and database reset route.
#
# OLD FLASK ROUTES:
#   GET /        → dashboard.html or login.html (based on session)
#   GET /admin   → admin.html (admin only)
#   GET /nuclear-reset → drops and recreates all tables

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db, init_db, engine, Base
from app.core.security import get_current_user, get_optional_user, require_admin
from app.models.models import User, Report, SavedJob, ActivityLog   # ← added ActivityLog
from app.core.config import settings

router = APIRouter(tags=["Dashboard"])
from app.core.templates import templates
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Home page: shows dashboard if logged in, login page if not.

    Old Flask:
        if 'user' in session: return render_template('dashboard.html', ...)
        return render_template('login.html')

    Now: get_optional_user returns None instead of raising an error.
    """
    current_user = get_optional_user(request)

    if not current_user:
        return templates.TemplateResponse(request, "login.html", {})

    email = current_user["sub"]

    # Fetch last 3 reports for this user
    reports_result = await db.execute(
        select(Report)
        .where(Report.user_email == email)
        .order_by(Report.id.desc())
        .limit(3)
    )
    saved_reports = reports_result.scalars().all()

    # Fetch last 5 saved jobs
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
        "admin_email": settings.ADMIN_EMAIL,   # ← NEW: for base.html Admin button
    })


@router.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Admin dashboard.

    Old Flask:
        admin_email = 'mehvishsheikh.3101@gmail.com'
        if session['user']['email'] != admin_email: return "Forbidden", 403

    Now: require_admin() does this check for us (raises 403 automatically).
    """
    try:
        current_user = get_current_user(request)
        require_admin(current_user)
    except HTTPException:
        return RedirectResponse(url="/")

    # All users ordered by most recent login
    users_result = await db.execute(
        select(User).order_by(User.last_login.desc())
    )
    users = users_result.scalars().all()

    # Total resume scans
    count_result = await db.execute(select(func.count()).select_from(Report))
    total_scans = count_result.scalar_one()

    # ── NEW: total login attempts ──────────────────────────────────
    login_sum = await db.execute(select(func.sum(User.login_count)))
    total_login_attempts = login_sum.scalar_one() or 0

    # ── NEW: Chart 1 — user activity per day (last 7 days) ────────
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    signup_rows = await db.execute(
        select(
            func.date(User.last_login).label("day"),
            func.count(User.id).label("count")
        )
        .where(User.last_login >= seven_days_ago)
        .group_by(func.date(User.last_login))
        .order_by(func.date(User.last_login))
    )
    signup_data = signup_rows.all()
    chart_labels = [str(r.day) for r in signup_data]
    chart_values = [r.count for r in signup_data]

    # ── NEW: Chart 2 — feature usage pie ──────────────────────────
    feature_rows = await db.execute(
        select(
            ActivityLog.action,
            func.count(ActivityLog.id).label("count")
        )
        .group_by(ActivityLog.action)
    )
    feature_data = feature_rows.all()
    feature_labels = [r.action.replace("_", " ").title() for r in feature_data]
    feature_values = [r.count for r in feature_data]

    # ── NEW: Live feed — last 10 actions ──────────────────────────
    feed_rows = await db.execute(
        select(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
    )
    recent_activity = feed_rows.scalars().all()
    # ──────────────────────────────────────────────────────────────

    return templates.TemplateResponse(request, "admin.html", {
        "user": current_user,
        "users": users,
        "total_users": len(users),
        "total_scans": total_scans,
        "admin_email": settings.ADMIN_EMAIL,          # ← NEW
        "total_login_attempts": total_login_attempts, # ← NEW
        "chart_labels": chart_labels,                 # ← NEW
        "chart_values": chart_values,                 # ← NEW
        "feature_labels": feature_labels,             # ← NEW
        "feature_values": feature_values,             # ← NEW
        "recent_activity": recent_activity,           # ← NEW
    })


# ── NEW: AJAX endpoint for live feed auto-refresh ─────────────────
@router.get("/admin/live-feed")
async def live_feed(request: Request, db: AsyncSession = Depends(get_db)):
    """Returns last 10 activity logs as JSON — polled every 30s by admin page."""
    try:
        current_user = get_current_user(request)
        require_admin(current_user)
    except HTTPException:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    rows = await db.execute(
        select(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
    )
    logs = rows.scalars().all()

    return JSONResponse([
        {
            "user_name": l.user_name or l.user_email,
            "action":    l.action.replace("_", " ").title(),
            "detail":    l.detail or "",
            "time":      l.created_at.strftime("%d %b, %I:%M %p") if l.created_at else ""
        }
        for l in logs
    ])


@router.get("/nuclear-reset")
async def nuclear_reset(request: Request):
    """
    Emergency database reset — drops all tables and recreates them.

    DANGER: This deletes ALL data. Only use in emergencies.

    Old Flask: Same functionality, just in Flask syntax.

    Production improvement: Add a secret token check so random people
    can't hit this URL and wipe your database.
    """
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