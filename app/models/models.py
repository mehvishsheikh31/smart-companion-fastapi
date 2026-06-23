# app/models/models.py
#
# PURPOSE: Define your database schema as Python classes.
#
# YOUR OLD FLASK APPROACH:
#   Raw SQL strings scattered across init_db():
#   c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, ...)")
#   Different syntax for SQLite vs Postgres (?  vs %s)
#
# THE SQLALCHEMY ORM APPROACH:
#   Define tables as Python classes. SQLAlchemy handles:
#   - Table creation for both SQLite and Postgres
#   - The ? vs %s difference (uses its own parameter binding)
#   - Type checking and conversion
#   - Relationships between tables
#
# HOW IT WORKS:
#   class User(Base):             ← Python class
#       __tablename__ = "users"   ← maps to SQL table "users"
#       id = Column(Integer, ...)  ← maps to SQL column "id INTEGER ..."
#
# When SQLAlchemy sees this class, it knows exactly what SQL to run.
# "Base.metadata.create_all()" is equivalent to all your CREATE TABLE IF NOT EXISTS statements.

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base


# ─────────────────────────────────────────────
# USER MODEL
# ─────────────────────────────────────────────
class User(Base):
    """
    Maps to the 'users' table.
    
    Old SQL:
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            picture TEXT,
            role TEXT,
            last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            login_count INTEGER DEFAULT 1
        )
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    role = Column(String, default="Student")
    last_login = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    login_count = Column(Integer, default=1)
    
    reports = relationship("Report", back_populates="user", cascade="all, delete-orphan")
    saved_jobs = relationship("SavedJob", back_populates="user", cascade="all, delete-orphan")
    # ── NEW: link to activity logs ──
    activity_logs = relationship("ActivityLog", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"


# ─────────────────────────────────────────────
# REPORT MODEL
# ─────────────────────────────────────────────
class Report(Base):
    """
    Maps to the 'reports' table.
    Stores AI-generated resume analyses and interview prep results.
    
    Old SQL:
        CREATE TABLE reports (
            id SERIAL PRIMARY KEY,
            user_email TEXT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    __tablename__ = "reports"
    
    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, ForeignKey("users.email"), nullable=False, index=True)
    role = Column(String)
    content = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = relationship("User", back_populates="reports")
    
    def __repr__(self):
        return f"<Report id={self.id} user={self.user_email} role={self.role}>"


# ─────────────────────────────────────────────
# SAVED JOB MODEL
# ─────────────────────────────────────────────
class SavedJob(Base):
    """
    Maps to the 'saved_jobs' table.
    When a user bookmarks a job from the search results.
    
    Old SQL:
        CREATE TABLE saved_jobs (
            id SERIAL PRIMARY KEY,
            user_email TEXT,
            title TEXT, company TEXT, location TEXT, url TEXT,
            created_at TEXT
        )
    """
    __tablename__ = "saved_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, ForeignKey("users.email"), nullable=False, index=True)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    url = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = relationship("User", back_populates="saved_jobs")
    
    def __repr__(self):
        return f"<SavedJob id={self.id} title={self.title} user={self.user_email}>"


# ─────────────────────────────────────────────
# JOB CACHE MODEL
# ─────────────────────────────────────────────
class JobCache(Base):
    """
    Maps to the 'job_cache' table.
    Caches Adzuna API results to avoid hitting rate limits.
    
    Old SQL:
        CREATE TABLE job_cache (
            search_key TEXT PRIMARY KEY,
            json_data TEXT,
            updated_at TEXT
        )
    """
    __tablename__ = "job_cache"
    
    search_key = Column(String, primary_key=True, index=True)
    json_data = Column(Text)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<JobCache key={self.search_key}>"


# ─────────────────────────────────────────────
# ACTIVITY LOG MODEL  ← NEW
# Tracks user actions for admin live feed
# and feature-usage charts.
# action values:
#   "login", "resume_scan", "job_search", "job_save"
# ─────────────────────────────────────────────
class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id         = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, ForeignKey("users.email"), nullable=False, index=True)
    user_name  = Column(String, nullable=True)
    action     = Column(String, nullable=False)
    detail     = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    user = relationship("User", back_populates="activity_logs")

    def __repr__(self):
        return f"<ActivityLog {self.action} by {self.user_email}>"