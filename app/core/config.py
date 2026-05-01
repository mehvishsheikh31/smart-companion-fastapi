
# PURPOSE: Central configuration object.
# Instead of calling os.getenv() everywhere in the code (messy, error-prone),
# we read ALL environment variables once here and expose them as typed Python
# attributes. If a required variable is missing, the app crashes at startup
# with a clear error — better than failing silently at runtime.
#
# FastAPI community convention: use pydantic-settings for this.
# We use python-dotenv here for simplicity (same as your Flask app).

import os
from dotenv import load_dotenv

load_dotenv()  # Load .env file into os.environ

class Settings:
    """
    Single source of truth for all configuration.
    Access anywhere with: from app.core.config import settings
    """

    # --- App ---
    APP_NAME: str = "Smart Companion AI"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # --- Security ---
    # This is used to sign JWT tokens. Must be long, random, and SECRET.
    # Anyone with this key can forge tokens — treat it like a password.
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change_this_in_production_please")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    # How long tokens stay valid. 10080 min = 7 days.
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    # After Google login, redirect back here:
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

    # --- AI ---
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # --- Job API ---
    ADZUNA_APP_ID: str = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY: str = os.getenv("ADZUNA_APP_KEY", "")

    # --- Database ---
    # If DATABASE_URL is set (Postgres on Render), use that.
    # Otherwise, use local SQLite file.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # SQLAlchemy wants a specific URL format.
    # For async SQLite: "sqlite+aiosqlite:///./database.db"
    # For Postgres:     "postgresql+psycopg2://user:pass@host/db"
    @property
    def db_url(self) -> str:
        if self.DATABASE_URL:
            # Render gives "postgres://..." but SQLAlchemy needs "postgresql://..."
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return url
        # Local SQLite — the +aiosqlite part tells SQLAlchemy to use async driver
        return "sqlite+aiosqlite:///./database.db"

    # --- Admin ---
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")

    # --- File Uploads ---
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10  # same as your Flask config


# Create a single instance — import this everywhere
settings = Settings()