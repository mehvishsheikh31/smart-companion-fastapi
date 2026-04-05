# app/routers/dashboard.py
#
# PURPOSE: Home dashboard, admin panel, and database reset route.
#
# OLD FLASK ROUTES:
#   GET /        → dashboard.html or login.html (based on session)
#   GET /admin   → admin.html (admin only)
#   GET /nuclear-reset → drops and recreates all tables

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
    """
    Home page: shows dashboard if logged in, login page if not.
    
    Old Flask:
        if 'user' in session: return render_template('dashboard.html', ...)
        return render_template('login.html')
    
    Now: get_optional_user returns None instead of raising an error.
    """
    current_user = get_optional_user(request)
    
    if not current_user:
        # Not logged in — show landing/login page
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
    "saved_jobs": saved_jobs_list
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
    except HTTPException:
        return RedirectResponse(url="/")
    
    # Will raise 403 if not admin
    require_admin(current_user)
    
    # Get all users, ordered by most recent login
    users_result = await db.execute(
        select(User).order_by(User.last_login.desc())
    )
    users = users_result.scalars().all()
    
    # Count total reports
    count_result = await db.execute(select(func.count()).select_from(Report))
    total_scans = count_result.scalar_one()
    
    return templates.TemplateResponse(request, "admin.html", {
    "user": current_user,
    "users": users,
    "total_users": len(users),
    "total_scans": total_scans
})


@router.get("/nuclear-reset")
async def nuclear_reset(request: Request):
    """
    Emergency database reset — drops all tables and recreates them.
    
    DANGER: This deletes ALL data. Only use in emergencies.
    
    Old Flask: Same functionality, just in Flask syntax.
    
    Production improvement: Add a secret token check so random people
    can't hit this URL and wipe your database.
    """
    # Basic security: only admin can reset
    try:
        current_user = get_current_user(request)
        require_admin(current_user)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Admin access required for database reset")
    
    logger.warning("⚠️  NUCLEAR RESET initiated!")
    
    async with engine.begin() as conn:
        # Drop all tables
        await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All tables dropped")
    
    # Recreate fresh
    await init_db()
    logger.info("Tables recreated")
    
    return HTMLResponse(
        content="<h1>✅ DATABASE RESET SUCCESSFUL. All tables recreated. <a href='/'>Go Home</a></h1>"
    )