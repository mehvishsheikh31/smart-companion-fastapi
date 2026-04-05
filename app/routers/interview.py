# app/routers/interview.py
#
# PURPOSE: Interview question generation and saving.
#
# OLD FLASK ROUTES:
#   GET  /chatbot               → render interview.html
#   POST /interview/generate    → PDF upload + form, call AI, return HTML
#   POST /interview/save        → JSON body, save to reports table

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Report
from app.schemas.schemas import SaveInterviewRequest
from app.services import pdf_service, ai_service

router = APIRouter(tags=["Interview"])
from app.core.templates import templates
logger = logging.getLogger(__name__)


@router.get("/chatbot", response_class=HTMLResponse)
async def interview_page(request: Request):
    """Show interview prep page."""
    try:
        current_user = get_current_user(request)
    except HTTPException:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/")
    
    
    return templates.TemplateResponse(request, "interview.html", {"user": current_user})


@router.post("/interview/generate", response_class=HTMLResponse)
async def generate_interview_questions(
    request: Request,
    role: str = Form(...),
    company: str = Form(...),
    q_type: str = Form(...),
    count: str = Form(...),
    resume: UploadFile = File(...),
):
    """
    Generate interview questions from resume + form inputs.
    
    Old Flask: request.form.get('role'), request.files['resume']
    Now: FastAPI injects these from the multipart form automatically.
    """
    try:
        current_user = get_current_user(request)
    except HTTPException:
        return HTMLResponse(content="<div class='alert alert-danger'>Please log in first.</div>", status_code=401)
    
    # Extract and validate resume text
    resume_text = await pdf_service.extract_text_from_upload(resume)
    
    if len(resume_text) < 50:
        return HTMLResponse(
            content="<div class='alert alert-warning'>Resume could not be read. Please upload a text-based PDF.</div>",
            status_code=400
        )
    
    # Generate questions via AI service
    logger.info(f"Generating {count} {q_type} questions for {role} at {company}")
    try:
        html_result = await ai_service.generate_interview_questions(
            resume_text=resume_text,
            role=role,
            company=company,
            q_type=q_type,
            count=count
        )
        return HTMLResponse(content=html_result)
    except Exception as e:
        logger.error(f"Interview generation failed: {e}")
        return HTMLResponse(
            content=f"<div class='alert alert-danger'>AI Error: {str(e)}</div>",
            status_code=500
        )


@router.post("/interview/save")
async def save_interview_result(
    request: Request,
    # SaveInterviewRequest is our Pydantic schema — FastAPI validates the JSON body automatically
    data: SaveInterviewRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Save interview prep results to DB.
    
    Old Flask:
        data = request.json  # No validation
        content_str = data.get('content', '')
    
    Now:
        data: SaveInterviewRequest  # Validated automatically
        data.content, data.role  # Type-safe access
    """
    try:
        current_user = get_current_user(request)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    report = Report(
        user_email=current_user["sub"],
        role=f"Interview Prep: {data.role}",
        content=data.content,
        created_at=datetime.now(timezone.utc)
    )
    db.add(report)
    await db.commit()
    
    return {"message": "Saved successfully"}