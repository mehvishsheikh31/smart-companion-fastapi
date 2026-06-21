import logging
import os
from slowapi.errors import RateLimitExceeded
from app.routers.courses import rate_limit_handler
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse  # ✅ add HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from slowapi import _rate_limit_exceeded_handler          # ✅ add
from slowapi.errors import RateLimitExceeded              # ✅ add
from app.core.limiter import limiter                      # ✅ add

from app.core.config import settings
from app.core.database import init_db
from app.routers import auth, resume, interview, jobs, courses, dashboard

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Smart Companion AI starting up...")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    await init_db()
    logger.info(f"✅ App started. Debug={settings.DEBUG}")
    yield
    logger.info("👋 Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter  # ✅ attach limiter to app

# ── Middleware ────────────────────────────────
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files (MUST be before routers) ────
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
logger.info("📂 Static files mounted")

# ── Routers (AFTER static mount) ─────────────
app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(resume.router)
app.include_router(interview.router)
app.include_router(jobs.router)
app.include_router(courses.router)
logger.info("✅ All routers registered")

# ── Exception handlers ────────────────────────
@app.exception_handler(RateLimitExceeded)          # ✅ add rate limit handler
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return HTMLResponse(
            content="<div class='alert alert-warning text-center mt-3'>⚠️ Too many requests. Please wait a moment and try again.</div>",
            status_code=429
        )
    return JSONResponse({"detail": "Too many requests."}, status_code=429)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"detail": f"Route '{request.url.path}' not found"})

# ── Health check ──────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "healthy", "app": settings.APP_NAME}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)