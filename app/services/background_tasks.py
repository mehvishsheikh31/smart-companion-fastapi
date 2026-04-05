# app/services/background_tasks.py
#
# PURPOSE: Run long-running operations without making the user wait.
#
# THE PROBLEM:
#   AI calls to Groq can take 5-15 seconds. If you have 10 users analyzing
#   resumes simultaneously, and each takes 10 seconds, the 10th user waits 100 seconds.
#
# FASTAPI'S SOLUTION: BackgroundTasks
#   Route returns immediately → background task runs after response is sent
#
# TWO APPROACHES:
#   1. FastAPI BackgroundTasks (simple, no extra setup) — used below
#   2. Celery + Redis (for truly heavy workloads, multi-server setups)
#
# WHEN TO USE BACKGROUND TASKS:
#   - Sending emails after registration
#   - Logging / analytics
#   - Sending Slack notifications
#   - Cache warming (pre-fetching data)
#   - NOT for: things the user needs in the response (use async await instead)
#
# NOTE: For your AI calls, asyncio.to_thread() (what we use in ai_service.py)
# is actually better because the user still waits for the AI result (they need it!).
# Background tasks are for fire-and-forget operations.
#
# EXAMPLE USAGE in a router:
#
#   from fastapi import BackgroundTasks
#   from app.services.background_tasks import send_analysis_email, log_usage
#
#   @router.post("/resume/analyze")
#   async def analyze_resume(
#       background_tasks: BackgroundTasks,
#       ...
#   ):
#       # Do the main work
#       result = await ai_service.analyze_resume(text, role)
#       
#       # Schedule these to run AFTER the response is sent
#       background_tasks.add_task(log_usage, user_email=email, action="resume_analyze")
#       background_tasks.add_task(send_analysis_email, email=email, role=role)
#       
#       # This response is sent immediately
#       # The background tasks run after it's sent
#       return templates.TemplateResponse(...)

import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


async def log_usage(user_email: str, action: str, metadata: Optional[dict] = None):
    """
    Log user activity for analytics.
    
    This is a fire-and-forget task — the user doesn't need to wait for it.
    You could write to a database, send to a logging service (Datadog, Sentry), etc.
    """
    logger.info(f"USAGE_LOG | user={user_email} | action={action} | time={datetime.now(timezone.utc)} | meta={metadata}")
    
    # Example: write to a separate analytics table
    # async with AsyncSessionLocal() as db:
    #     db.add(UsageLog(user_email=user_email, action=action, ...))
    #     await db.commit()


async def warm_job_cache(role: str, locations: list[str]):
    """
    Pre-fetch job results for common searches.
    Call this after a user saves a job to warm up related searches.
    
    Example: User searches "Python Developer" → warm cache for nearby cities
    """
    logger.info(f"Cache warming for role='{role}', locations={locations}")
    
    # In a real app, you'd call job_service.search_jobs() for each location
    # to pre-populate the cache before users ask for it.
    # For now, this is a placeholder showing the pattern.
    await asyncio.sleep(0)  # Placeholder


# ─────────────────────────────────────────────
# HOW TO ADD BACKGROUND TASKS TO YOUR ROUTES
# ─────────────────────────────────────────────
#
# 1. Import BackgroundTasks from fastapi
# 2. Add it as a parameter to your route function
# 3. Call background_tasks.add_task(func, arg1, arg2, ...)
#
# FULL EXAMPLE:
#
# from fastapi import APIRouter, BackgroundTasks
# from app.services.background_tasks import log_usage
#
# router = APIRouter()
#
# @router.post("/resume/analyze")
# async def analyze_resume(
#     request: Request,
#     background_tasks: BackgroundTasks,    # ← Add this parameter
#     job_role: str = Form(...),
#     resume: UploadFile = File(...),
#     db: AsyncSession = Depends(get_db)
# ):
#     current_user = get_current_user(request)
#     
#     # Main work (user waits for this)
#     resume_text = await pdf_service.extract_text_from_upload(resume)
#     analysis_html = await ai_service.analyze_resume(resume_text, job_role)
#     
#     # Schedule background work (runs AFTER response is sent)
#     background_tasks.add_task(
#         log_usage,
#         user_email=current_user["sub"],
#         action="resume_analyze",
#         metadata={"role": job_role}
#     )
#     
#     # User gets response immediately
#     return templates.TemplateResponse(...)