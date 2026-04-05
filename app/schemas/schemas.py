# app/schemas/schemas.py
#
# PURPOSE: Define the "shape" of data coming in (requests) and going out (responses).
#
# YOUR OLD FLASK APPROACH:
#   data = request.json  # No validation — any garbage could come in
#   email = data['email']  # KeyError if 'email' missing → 500 error
#
# THE PYDANTIC/FASTAPI APPROACH:
#   class SaveJobRequest(BaseModel):
#       url: str  # FastAPI automatically validates this
#       title: str
#
#   If 'url' is missing from the request body, FastAPI returns a clear 422 error:
#   {"detail": [{"loc": ["body", "url"], "msg": "field required", "type": "value_error.missing"}]}
#
# THIS IS ONE OF THE BIGGEST WINS OF FASTAPI:
#   - No manual validation code
#   - Clear error messages for API consumers
#   - Automatic API documentation (Swagger shows request/response shapes)
#   - Type safety — your IDE catches bugs before runtime

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime


# ─────────────────────────────────────────────
# USER SCHEMAS
# ─────────────────────────────────────────────

class UserBase(BaseModel):
    """Common user fields shared between schemas."""
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None


class UserCreate(UserBase):
    """Data needed to create a new user (from Google OAuth)."""
    role: str = "Student"


class UserResponse(UserBase):
    """What we send back when returning user data."""
    id: int
    role: str
    last_login: Optional[datetime] = None
    login_count: int
    
    # model_config tells Pydantic to read data from SQLAlchemy model attributes
    # (without this, Pydantic only reads dict keys, not object attributes)
    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# REPORT SCHEMAS
# ─────────────────────────────────────────────

class ReportResponse(BaseModel):
    """Returned when listing/viewing reports."""
    id: int
    user_email: str
    role: Optional[str] = None
    content: Optional[str] = None
    created_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# JOB SCHEMAS
# ─────────────────────────────────────────────

class SaveJobRequest(BaseModel):
    """
    Body of POST /jobs/save request.
    
    Old Flask: data = request.json — no validation
    Now: FastAPI validates this automatically before your route runs
    """
    title: str
    company: str
    location: str
    url: str
    
    @field_validator('url')
    @classmethod
    def url_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('URL cannot be empty')
        return v.strip()


class SavedJobResponse(BaseModel):
    """Returned when listing saved jobs."""
    id: int
    title: Optional[str]
    company: Optional[str]
    location: Optional[str]
    url: Optional[str]
    created_at: Optional[datetime]
    
    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# INTERVIEW SCHEMAS
# ─────────────────────────────────────────────

class SaveInterviewRequest(BaseModel):
    """
    Body of POST /interview/save request.
    
    Old Flask: data = request.json with no validation
    """
    content: str
    role: str = "General"


# ─────────────────────────────────────────────
# ADMIN SCHEMAS
# ─────────────────────────────────────────────

class AdminStats(BaseModel):
    """Dashboard stats for admin panel."""
    total_users: int
    total_scans: int


# ─────────────────────────────────────────────
# GENERAL RESPONSE SCHEMAS
# ─────────────────────────────────────────────

class MessageResponse(BaseModel):
    """Simple success/error message response."""
    message: str
    success: bool = True


class TokenResponse(BaseModel):
    """Returned on successful login."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse