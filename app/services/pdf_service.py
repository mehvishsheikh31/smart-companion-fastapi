# app/services/pdf_service.py
#
# PURPOSE: All PDF-related logic in one place.
#
# YOUR OLD FLASK APPROACH:
#   def extract_text_from_pdf(file):  # defined in app.py, used in 3+ routes
#       with pdfplumber.open(file) as pdf: ...
#
# WHY MOVE IT TO A SERVICE?
#   - Reusability: resume.py, interview.py, and courses.py all need PDF extraction
#   - Testability: you can test this function independently
#   - Clarity: routes stay thin, logic stays here
#
# WHAT CHANGES FROM FLASK?
#   FastAPI receives uploaded files as "UploadFile" objects (not Werkzeug FileStorage).
#   The API is slightly different — we need to read bytes, then wrap in BytesIO.

import io
import pdfplumber
from pypdf import PdfReader
from fastapi import UploadFile, HTTPException
import logging

logger = logging.getLogger(__name__)


async def extract_text_from_upload(file: UploadFile) -> str:
    """
    Extract text from an uploaded PDF file.
    
    Args:
        file: FastAPI UploadFile object (from request.files equivalent)
    
    Returns:
        Extracted text string (empty string if extraction fails)
    
    How it works:
        1. Read the file bytes from the upload stream
        2. Wrap in BytesIO (pdfplumber needs a file-like object, not raw bytes)
        3. Extract text from each page
        4. Fall back to pypdf if pdfplumber fails
    """
    # Read all bytes from the upload
    # In Flask: file.read() worked directly on Werkzeug's FileStorage
    # In FastAPI: file.read() is an async operation
    file_bytes = await file.read()
    
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    
    # Wrap bytes in a file-like object (pdfplumber.open() needs this)
    file_stream = io.BytesIO(file_bytes)
    
    # --- Method 1: pdfplumber (better for complex layouts) ---
    try:
        text = ""
        with pdfplumber.open(file_stream) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        if len(text.strip()) > 50:
            logger.info(f"Extracted {len(text)} chars using pdfplumber")
            return text.strip()
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}, trying pypdf...")
    
    # --- Method 2: pypdf (fallback) ---
    try:
        file_stream.seek(0)  # Reset to start of file
        reader = PdfReader(file_stream)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        logger.info(f"Extracted {len(text)} chars using pypdf")
        return text.strip()
    except Exception as e:
        logger.error(f"Both PDF extractors failed: {e}")
        return ""


def validate_resume_text(text: str, min_length: int = 50) -> None:
    """
    Validate that we got meaningful text from the PDF.
    Raises HTTPException if the text is too short.
    
    Why separate function? Because resume.py, interview.py, and courses.py
    all do this same check. DRY principle (Don't Repeat Yourself).
    """
    if len(text) < min_length:
        raise HTTPException(
            status_code=400,
            detail="Resume could not be read or is too short. Please upload a text-based PDF (not a scanned image)."
        )