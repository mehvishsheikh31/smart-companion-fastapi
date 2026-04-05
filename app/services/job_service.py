# app/services/job_service.py
#
# PURPOSE: All Adzuna job API logic and HTML generation.
#
# YOUR OLD FLASK APPROACH:
#   - API call, HTML generation all inline in the /jobs/search route (~80 lines)
#   - Hard to read, hard to test
#
# NOW:
#   - search_jobs() → returns structured data (list of dicts)
#   - generate_jobs_html() → turns data into HTML
#   - Route just calls these two functions and returns the result
#
# WHY ASYNC?
#   HTTP calls to external APIs (Adzuna) are I/O-bound — the server just waits.
#   With async + httpx, FastAPI can handle other requests while waiting for Adzuna.
#   With sync requests (your Flask code), the whole server freezes for every API call.

import httpx
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.models.models import JobCache

logger = logging.getLogger(__name__)


async def search_jobs(
    role: str,
    location: str,
    db: AsyncSession,
    use_cache: bool = True,
    cache_hours: int = 6
) -> List[dict]:
    """
    Search for jobs using Adzuna API with database caching.
    
    Caching strategy:
        - First, check if we have recent results in job_cache table
        - If cache is fresh (< cache_hours old): return cached results
        - If cache is stale/missing: call Adzuna API, store in cache, return results
        
    This reduces API calls significantly (Adzuna has rate limits).
    Your Flask app had a job_cache table but didn't seem to use it — now we do!
    """
    
    # --- 1. Check Cache ---
    search_key = f"{role.lower().strip()}_{location.lower().strip()}"
    
    if use_cache:
        # Query the cache table for this search key
        result = await db.execute(
            select(JobCache).where(JobCache.search_key == search_key)
        )
        cached = result.scalar_one_or_none()
        
        if cached:
            cache_age = datetime.now(timezone.utc) - cached.updated_at.replace(tzinfo=timezone.utc)
            if cache_age < timedelta(hours=cache_hours):
                logger.info(f"Cache hit for '{search_key}' (age: {cache_age})")
                return json.loads(cached.json_data)
    
    # --- 2. Call Adzuna API ---
    logger.info(f"Cache miss for '{search_key}' — calling Adzuna API")
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://api.adzuna.com/v1/api/jobs/in/search/1",
                params={
                    "app_id": settings.ADZUNA_APP_ID,
                    "app_key": settings.ADZUNA_APP_KEY,
                    "results_per_page": 10,
                    "what": role,
                    "where": location,
                    "content-type": "application/json"
                }
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        raise Exception("Job search API timed out. Please try again.")
    except httpx.HTTPStatusError as e:
        raise Exception(f"Job API returned error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        raise Exception(f"Failed to connect to job API: {str(e)}")
    
    # --- 3. Parse Results ---
    jobs_data = []
    for job in data.get('results', []):
        desc = job.get('description', '')
        jobs_data.append({
            "title": job.get('title', 'Unknown Role'),
            "company": job.get('company', {}).get('display_name', 'Unknown Company'),
            "location": job.get('location', {}).get('display_name', location),
            "desc": desc[:140] + "..." if len(desc) > 140 else desc,
            "full_desc": desc,
            "url": job.get('redirect_url', '#'),
            "date": job.get('created', '')[:10]  # Extract YYYY-MM-DD
        })
    
    # --- 4. Store in Cache ---
    if jobs_data:
        json_str = json.dumps(jobs_data)
        
        # Upsert: insert if not exists, update if exists
        existing = await db.execute(
            select(JobCache).where(JobCache.search_key == search_key)
        )
        cache_entry = existing.scalar_one_or_none()
        
        if cache_entry:
            cache_entry.json_data = json_str
            cache_entry.updated_at = datetime.now(timezone.utc)
        else:
            db.add(JobCache(
                search_key=search_key,
                json_data=json_str,
                updated_at=datetime.now(timezone.utc)
            ))
        
        await db.commit()
        logger.info(f"Cached {len(jobs_data)} jobs for '{search_key}'")
    
    return jobs_data


def generate_jobs_html(jobs_data: List[dict]) -> str:
    """
    Convert job data list → HTML card grid.
    
    This is the same HTML your Flask app generated, just as a pure function.
    Pure function = same input always gives same output = easy to test.
    """
    if not jobs_data:
        return "<div class='text-center mt-5'><h5 class='text-muted'>No jobs found. Try a different search.</h5></div>"
    
    html = ""
    for job in jobs_data:
        logo_url = f"https://ui-avatars.com/api/?name={job['company']}&background=random&size=128"
        # Escape quotes in title to prevent JS injection in onclick
        safe_title = job['title'].replace("'", "").replace('"', "")
        safe_company = job['company'].replace("'", "").replace('"', "")
        safe_location = job['location'].replace("'", "").replace('"', "")
        safe_url = job['url'].replace("'", "").replace('"', "")
        
        html += f"""
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card h-100 border-0 shadow-sm rounded-4 hover-lift" style="transition: transform 0.2s;">
                <div class="card-body p-4 d-flex flex-column">
                    <div class="d-flex align-items-center mb-3">
                        <img src="{logo_url}" class="rounded-circle me-3 border p-1" width="45" height="45" alt="Logo">
                        <div style="overflow: hidden;">
                            <h6 class="fw-bold text-dark mb-0 text-truncate">{job['title']}</h6>
                            <small class="text-primary fw-bold">{job['company']}</small>
                        </div>
                    </div>
                    <div class="mb-3">
                        <span class="badge bg-light text-dark border me-1">
                            <i class="fas fa-map-marker-alt me-1 text-danger"></i> {job['location']}
                        </span>
                        <span class="badge bg-light text-muted border">
                            <i class="far fa-clock me-1"></i> {job['date']}
                        </span>
                    </div>
                    <p class="text-muted small mb-4 flex-grow-1" style="line-height: 1.6;">{job['desc']}</p>
                    <div class="d-flex gap-2 mt-auto">
                        <a href="{job['url']}" target="_blank" class="btn btn-dark rounded-pill fw-bold btn-sm flex-grow-1">
                            Apply Now <i class="fas fa-external-link-alt ms-1"></i>
                        </a>
                        <button onclick="saveJob(this, '{safe_title}', '{safe_company}', '{safe_location}', '{safe_url}')" 
                                class="btn btn-outline-secondary rounded-pill btn-sm" title="Save Job">
                            <i class="far fa-bookmark"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
        """
    
    return html