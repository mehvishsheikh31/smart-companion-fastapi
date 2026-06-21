# app/routers/courses.py
#
# PURPOSE: Skill gap analysis + course recommendations.
#
# FIXES APPLIED:
#   1. Role validation: empty/blank role now returns a clear 400 instead of
#      passing an empty string to the AI (which produced garbage output).
#
#   2. Rate-limit (429) is now returned as a structured HTML fragment so the
#      frontend can display a specific "slow down" message instead of the
#      generic "Something went wrong" card with a Retry button that would
#      just get rate-limited again immediately.
#
#   3. File-type guard: non-PDF uploads are rejected early with a clear
#      message before wasting an AI call.
#
# NOTE: The frontend (courses.html) must also be updated to handle the
#       data-error-type="rate_limit" attribute this router now sends back.
#       See the companion courses.html fix.

import logging
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.security import get_current_user
from app.core.templates import templates
from app.core.limiter import limiter
from app.services import pdf_service, ai_service

router = APIRouter(prefix="/courses", tags=["Courses"])
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def courses_page(request: Request):
    """Show courses/skill gap page."""
    try:
        current_user = get_current_user(request)
    except HTTPException:
        return RedirectResponse(url="/")

    return templates.TemplateResponse(request, "courses.html", {"user": current_user})


@router.post("/gap_analysis", response_class=HTMLResponse)
@limiter.limit("3/minute;20/hour;50/day")
async def gap_analysis(
    request: Request,
    role: str = Form(...),
    resume: UploadFile = File(...),
):
    """
    Analyze skill gap and recommend free courses.

    Returns an HTML fragment that is injected directly into #courseResults
    by the frontend fetch() call.
    """
    # --- Auth ---
    try:
        current_user = get_current_user(request)
    except HTTPException:
        return HTMLResponse(content="Unauthorized", status_code=401)

    # --- FIX 1: Role validation ---
    # Blank or whitespace-only role slips through Form(...) validation and
    # produces an unhelpful AI response like "6 courses for ' '".
    role = role.strip()
    if not role:
        return HTMLResponse(
            content="""
            <div class='alert alert-warning rounded-4 text-center'>
                <i class='fas fa-exclamation-circle me-2'></i>
                Please select a target job role before analysing.
            </div>""",
            status_code=400,
        )

    # --- FIX 3: File-type guard ---
    # Reject non-PDF uploads before wasting an AI call. UploadFile.content_type
    # is set by the browser; we also check the filename extension as a fallback
    # because some browsers send application/octet-stream for PDFs.
    filename = (resume.filename or "").lower()
    content_type = (resume.content_type or "").lower()
    is_pdf = (
        content_type == "application/pdf"
        or filename.endswith(".pdf")
    )
    if not is_pdf:
        return HTMLResponse(
            content="""
            <div class='alert alert-danger rounded-4 text-center'>
                <i class='fas fa-file-slash me-2'></i>
                Only PDF files are supported. Please upload a <strong>.pdf</strong> resume.
            </div>""",
            status_code=415,
        )

    # --- PDF extraction ---
    resume_text = await pdf_service.extract_text_from_upload(resume)

    if len(resume_text) < 50:
        return HTMLResponse(
            content="""
            <div class='alert alert-danger rounded-4 text-center'>
                <i class='fas fa-file-circle-xmark me-2'></i>
                Resume is unreadable. Please upload a <strong>text-based PDF</strong>
                (not a scanned image). Try re-exporting from Word or Google Docs.
            </div>""",
            status_code=400,
        )

    logger.info(f"Skill gap analysis for {current_user['sub']} → role: {role}")

    # --- AI call ---
    try:
        html_result = await ai_service.analyze_skill_gap(resume_text, role)
        return HTMLResponse(content=html_result)

    except Exception as e:
        logger.error(f"Skill gap analysis failed: {e}")
        return HTMLResponse(
            content=f"""
            <div class='alert alert-danger rounded-4 text-center'>
                <i class='fas fa-robot me-2'></i>
                AI service error — please try again in a moment.
                <br><small class='text-muted'>{str(e)}</small>
            </div>""",
            status_code=500,
        )


# ---------------------------------------------------------------------------
# FIX 2: Custom 429 handler for the rate limiter
# ---------------------------------------------------------------------------
# slowapi (the library behind @limiter.limit) raises a 429 by default, but
# the default response is plain text "Rate limit exceeded". We override it
# here to return an HTML fragment with a data attribute the frontend can
# detect and display a specific friendly message.
#
# Register this in main.py:
#   from slowapi.errors import RateLimitExceeded
#   from app.routers.courses import rate_limit_handler
#   app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

from slowapi.errors import RateLimitExceeded
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response


async def rate_limit_handler(request: StarletteRequest, exc: RateLimitExceeded) -> Response:
    """
    Return an HTML fragment for rate-limited course analysis requests.
    The frontend checks for data-error-type="rate_limit" and shows a
    targeted message instead of the generic retry card.
    """
    return HTMLResponse(
        content="""
        <div class="col-12" data-error-type="rate_limit">
          <div class="alert alert-warning rounded-4 text-center py-4">
            <i class="fas fa-hourglass-half fa-2x text-warning mb-3 d-block"></i>
            <h5 class="fw-bold">Slow down — you're going fast!</h5>
            <p class="text-muted mb-0 small">
              You've used your free analysis limit for now.<br>
              Wait a minute and try again. Limit: <strong>3 analyses/minute, 20/hour</strong>.
            </p>
          </div>
        </div>""",
        status_code=429,
    )