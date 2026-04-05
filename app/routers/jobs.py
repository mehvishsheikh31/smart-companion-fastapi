# app/routers/jobs.py
#
# PURPOSE: Job search (Adzuna API) and save job to DB.
#
# OLD FLASK ROUTES:
#   GET  /jobs         → render jobs.html
#   POST /jobs/search  → call Adzuna, return HTML cards
#   POST /jobs/save    → save job to saved_jobs table

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import SavedJob
from app.schemas.schemas import SaveJobRequest
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["Jobs"])
from app.core.templates import templates
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def jobs_page(request: Request):
    """Show job search page."""
    try:
        current_user = get_current_user(request)
    except HTTPException:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/")
    
    return templates.TemplateResponse(request, "jobs.html", {
    "user": current_user
})
# jobs.py
from app.core.limiter import limiter

@router.post("/search", response_class=HTMLResponse)
@limiter.limit("5/minute;30/hour;80/day")
async def search_jobs(
    request: Request,
    role: str = Form(...),
    location: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Search jobs via Adzuna API (with caching).
    
    Old Flask (~80 lines with API call + HTML generation inline):
        response = requests.get(url, params=params)  # BLOCKING — freezes server
        html = ""
        for job in data.get('results', []):
            html += f"<div>...</div>"
        return html
    
    Now:
        jobs = await job_service.search_jobs(...)  # ASYNC — non-blocking
        html = job_service.generate_jobs_html(jobs)  # Pure function
        return HTMLResponse(html)
    """
    try:
        current_user = get_current_user(request)
    except HTTPException:
        return HTMLResponse(content="Unauthorized", status_code=401)
    
    try:
        jobs_data = await job_service.search_jobs(role=role, location=location, db=db)
        html = job_service.generate_jobs_html(jobs_data)
        return HTMLResponse(content=html)
    except Exception as e:
        logger.error(f"Job search failed: {e}")
        return HTMLResponse(
            content=f"<div class='alert alert-danger'>Search Error: {str(e)}</div>",
            status_code=500
        )


@router.post("/save")
async def save_job(
    request: Request,
    # SaveJobRequest Pydantic schema validates the JSON body
    data: SaveJobRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Save a job to the user's saved list.
    
    Old Flask:
        data = request.json  # No validation — KeyError possible
        c.execute("SELECT id FROM saved_jobs WHERE user_email = ? AND url = ?", ...)
    
    Now:
        data: SaveJobRequest  # Validated (title, company, location, url all required)
        SQLAlchemy handles the query
    """
    try:
        current_user = get_current_user(request)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    email = current_user["sub"]
    
    # Check if already saved (prevent duplicates)
    existing = await db.execute(
        select(SavedJob).where(
            SavedJob.user_email == email,
            SavedJob.url == data.url
        )
    )
    if existing.scalar_one_or_none():
        # Return 200 (not 409) to match your original Flask behavior
        return {"message": "Already saved"}
    
    # Save the job
    job = SavedJob(
        user_email=email,
        title=data.title,
        company=data.company,
        location=data.location,
        url=data.url,
        created_at=datetime.now(timezone.utc)
    )
    db.add(job)
    await db.commit()
    
    return {"message": "Job saved successfully"}