# app/routers/interview.py
#
# PURPOSE: Interview question generation and saving.
#
# OLD FLASK ROUTES:
#   GET  /chatbot               → render interview.html
#   POST /interview/generate    → PDF upload + form, call AI, return HTML
#   POST /interview/save        → JSON body, save to reports table

import logging
import asyncio
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
from app.schemas.schemas import SaveInterviewRequest, ImproveAnswerRequest, ChatRequest
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


@router.post("/interview/improve", response_class=HTMLResponse)
async def improve_answer(
    request: Request,
    data: ImproveAnswerRequest,
):
    """Refine a user's interview answer using AI."""
    try:
        current_user = get_current_user(request)
    except HTTPException:
        return HTMLResponse(content="<div class='alert alert-danger'>Please log in first.</div>", status_code=401)

    prompt = f"""
    You are an expert interview coach. A candidate answered an interview question poorly.
    Rewrite their answer to be professional, structured (Situation-Task-Action-Result where relevant), and concise.
    
    Question: {data.question}
    Candidate's Answer: {data.answer}
    
    OUTPUT HTML ONLY. NO MARKDOWN.
    Use this structure:
    
    <div class="p-4 bg-white rounded-4 border border-success shadow-sm">
        <h6 class="fw-bold text-success mb-3"><i class="fas fa-check-circle me-2"></i>Improved Answer</h6>
        <p class="text-dark mb-3" style="line-height:1.7;">{{Write the improved answer here}}</p>
        <div class="p-3 bg-light rounded border-start border-warning border-3">
            <small class="text-muted"><strong>💡 Why this works:</strong> {{One sentence on what made the rewrite stronger}}</small>
        </div>
    </div>
    """

    try:
        html_result = await asyncio.to_thread(ai_service._call_groq, prompt, 0.6)
        return HTMLResponse(content=html_result)
    except Exception as e:
        logger.error(f"Answer improvement failed: {e}")
        return HTMLResponse(
            content=f"<div class='alert alert-danger'>AI Error: {str(e)}</div>",
            status_code=500
        )


@router.post("/interview/chat", response_class=HTMLResponse)
async def interview_chat(
    request: Request,
    data: ChatRequest,
):
    """General career chat endpoint for the chatbot panel."""
    try:
        current_user = get_current_user(request)
    except HTTPException:
        return HTMLResponse(content="Please log in first.", status_code=401)

    prompt = f"""
    You are a friendly and knowledgeable career coach AI assistant.
    Answer the following career-related question concisely and helpfully.
    Keep your response under 150 words. Do NOT use markdown — plain text only.
    
    User: {data.message}
    """

    try:
        result = await asyncio.to_thread(ai_service._call_groq, prompt, 0.7)
        return HTMLResponse(content=result)
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        return HTMLResponse(content=f"Sorry, something went wrong: {str(e)}", status_code=500)