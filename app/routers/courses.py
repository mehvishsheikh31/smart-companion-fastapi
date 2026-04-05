# app/routers/courses.py
#
# PURPOSE: Skill gap analysis + course recommendations.
#
# OLD FLASK ROUTES:
#   GET  /courses               → render courses.html
#   POST /courses/gap_analysis  → PDF + role → AI HTML

import logging
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.security import get_current_user
from app.services import pdf_service, ai_service

router = APIRouter(prefix="/courses", tags=["Courses"])
from app.core.templates import templates
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def courses_page(request: Request):
    """Show courses/skill gap page."""
    try:
        current_user = get_current_user(request)
    except HTTPException:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/")
    
    return templates.TemplateResponse(request, "courses.html", {
    "user": current_user
})

# courses.py
from app.core.limiter import limiter

@router.post("/gap_analysis", response_class=HTMLResponse)
@limiter.limit("3/minute;20/hour;50/day")
async def gap_analysis(
    request: Request,
    role: str = Form(...),
    resume: UploadFile = File(...)
):
    """
    Analyze skill gap and recommend free courses.
    
    Old Flask:
        role = request.form.get('role')
        file = request.files['resume']
        resume_text = extract_text_from_pdf(file)
        if len(resume_text) < 50: return "<div>error</div>"
        completion = client.chat.completions.create(...)
        return completion.choices[0].message.content...
    
    Now: Logic is clean, separated into services.
    """
    try:
        current_user = get_current_user(request)
    except HTTPException:
        return HTMLResponse(content="Unauthorized", status_code=401)
    
    resume_text = await pdf_service.extract_text_from_upload(resume)
    
    if len(resume_text) < 50:
        return HTMLResponse(
            content="<div class='text-danger text-center'>Resume unreadable. Please upload a text-based PDF.</div>",
            status_code=400
        )
    
    logger.info(f"Skill gap analysis for {current_user['sub']} → role: {role}")
    try:
        html_result = await ai_service.analyze_skill_gap(resume_text, role)
        return HTMLResponse(content=html_result)
    except Exception as e:
        logger.error(f"Skill gap analysis failed: {e}")
        return HTMLResponse(
            content=f"<div class='alert alert-danger'>AI Error: {str(e)}</div>",
            status_code=500
        )