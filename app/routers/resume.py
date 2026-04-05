# app/routers/resume.py
#
# PURPOSE: Handle resume upload, analysis, and report viewing.
#
# YOUR OLD FLASK ROUTES:
#   GET  /resume           → render resume.html (if logged in)
#   POST /resume/analyze   → extract PDF text, call AI, save report, render result
#   GET  /report/<id>      → view a saved report
#
# WHAT CHANGES IN FASTAPI:
#   1. No request.files — use "file: UploadFile" parameter instead
#   2. No request.form — use "Form(...)" parameters
#   3. No session['user'] — use "current_user = get_current_user(request)"
#   4. Pydantic validates inputs automatically
#   5. HTML rendering uses Jinja2 TemplateResponse (same templates!)
#
# FILE UPLOADS IN FASTAPI:
#   Flask:   file = request.files['resume']
#   FastAPI: async def analyze(resume: UploadFile = File(...))
#
#   FastAPI's UploadFile is similar to Flask's FileStorage but:
#   - file.read() is async: await file.read()
#   - file.filename gives the original filename
#   - file.content_type gives MIME type

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Report
from app.services import pdf_service, ai_service

router = APIRouter(prefix="/resume", tags=["Resume"])
from app.core.templates import templates
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def resume_page(request: Request):
    """
    Show the resume upload page.
    
    Old Flask:
        @app.route('/resume')
        def resume_module():
            if 'user' not in session: return redirect('/')
            return render_template('resume.html')
    
    Now: get_current_user(request) does the auth check.
    If not logged in, it raises HTTPException(401) automatically.
    We catch it and redirect to home.
    """
    try:
        current_user = get_current_user(request)
    except HTTPException:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/")
    
    return templates.TemplateResponse(request, "resume.html", {"user": current_user})



@router.post("/analyze", response_class=HTMLResponse)
async def analyze_resume(
    request: Request,
    # Form fields: type annotation + Form(...) tells FastAPI this comes from multipart form
    job_role: str = Form(...),
    # File upload: UploadFile = File(...) tells FastAPI this is a file
    resume: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Main resume analysis endpoint.
    
    Old Flask:
        file = request.files['resume']       → resume: UploadFile = File(...)
        target_role = request.form.get('job_role')  → job_role: str = Form(...)
        if 'user' not in session: return redirect('/')  → get_current_user(request)
    
    Flow:
        1. Verify login
        2. Extract text from PDF
        3. Validate text length
        4. Call AI service (async)
        5. Save report to DB
        6. Return rendered HTML
    """
    
    # --- Auth check ---
    try:
        current_user = get_current_user(request)
    except HTTPException:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/")
    
    # --- Validate file type ---
    if not resume.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    if not resume.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Please upload a PDF file")
    
    # --- Extract text from PDF ---
    # pdf_service.extract_text_from_upload is async and handles BytesIO wrapping
    resume_text = await pdf_service.extract_text_from_upload(resume)
    
    # Validate minimum text length
    pdf_service.validate_resume_text(resume_text)
    
    # --- Call AI (async, non-blocking) ---
    logger.info(f"Starting resume analysis for {current_user['sub']} → role: {job_role}")
    try:
        analysis_html = await ai_service.analyze_resume(resume_text, job_role)
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")
    
    # --- Save report to database ---
    new_report = Report(
        user_email=current_user["sub"],
        role=job_role,
        content=analysis_html,
        created_at=datetime.now(timezone.utc)
    )
    db.add(new_report)
    await db.commit()
    await db.refresh(new_report)
    logger.info(f"Report saved: id={new_report.id}")
    
    # --- Render result ---
    # Same template as before! Templates don't need to change.
    return templates.TemplateResponse(request, "resume_result.html", {
    "user": current_user,
    "analysis": analysis_html
})


@router.get("/report/{report_id}", response_class=HTMLResponse)
async def view_report(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    View a previously saved report.
    
    Old Flask:
        @app.route('/report/<int:report_id>')
        c.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    
    Now: SQLAlchemy query with type safety.
    Note: Path parameter type is declared as `int` — FastAPI validates this automatically.
    If you visit /resume/report/abc, you get a 422 error, not a 500.
    """
    
    try:
        current_user = get_current_user(request)
    except HTTPException:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/")
    
    # SQLAlchemy query: SELECT * FROM reports WHERE id = :report_id
    result = await db.execute(
        select(Report).where(Report.id == report_id)
    )
    report = result.scalar_one_or_none()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Security: Only the report owner can view it
    if report.user_email != current_user["sub"]:
        raise HTTPException(status_code=403, detail="You don't have permission to view this report")
    
    return templates.TemplateResponse("resume_result.html", {
        "request": request,
        "user": current_user,
        "analysis": report.content
    })