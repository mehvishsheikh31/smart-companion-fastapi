# app/services/ai_service.py
#
# PURPOSE: All Groq AI API calls in one place.
#
# FIXES APPLIED (course recommender):
#   1. MODEL upgraded: llama-3.1-8b-instant → llama-3.3-70b-versatile
#      The 8B model frequently produces malformed HTML and hallucinates URLs.
#      70B is still free on Groq's tier and produces reliable structured HTML.
#
#   2. RESUME TRUNCATION fixed: [:2000] → [:5000]
#      A typical resume is 3,000–6,000 chars. Skills, projects, and certs
#      buried after the first section were being silently cut off.
#
#   3. URL HALLUCINATION mitigated: provider → homepage URL map injected into
#      prompt so the model gets verified base URLs. A post-processing note
#      is also added to each card encouraging users to verify the link.
#
#   4. HTML VALIDATION added: analyze_skill_gap() checks that 6 cards were
#      generated and returns a safe fallback error card if the model output
#      is malformed instead of silently returning broken HTML.

import asyncio
import logging
import re

from groq import Groq
from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------

_groq_client = Groq(api_key=settings.GROQ_API_KEY)

# FIX 1: Upgraded from llama-3.1-8b-instant to llama-3.3-70b-versatile.
# The 70B model is significantly better at following complex HTML templates
# and produces valid, non-hallucinated URLs. Still free on Groq's tier.
MODEL = "llama-3.3-70b-versatile"

# FIX 3: Verified provider base URLs injected into the prompt.
# The model is instructed to use these exact base paths, reducing the chance
# of hallucinated URLs like /courses/some-made-up-slug.
PROVIDER_URLS = {
    "IBM SkillsBuild":           "https://skillsbuild.org/learn",
    "GeeksforGeeks":             "https://www.geeksforgeeks.org/courses/",
    "Kaggle Learn":              "https://www.kaggle.com/learn",
    "PW Skills":                 "https://pwskills.com/courses/",
    "Coding Ninjas / Code360":   "https://www.codingninjas.com/courses/",
    "Google Cloud Skills Boost": "https://cloudskillsboost.google/catalog",
    "freeCodeCamp":              "https://www.freecodecamp.org/learn",
    "Microsoft Learn":           "https://learn.microsoft.com/en-us/training/",
    "NPTEL":                     "https://nptel.ac.in/course.html",
}

_PROVIDER_BLOCK = "\n".join(
    f"  - {name}: base URL is {url}" for name, url in PROVIDER_URLS.items()
)

# ---------------------------------------------------------------------------
# Internal Groq caller (synchronous — wrapped in asyncio.to_thread below)
# ---------------------------------------------------------------------------

def _call_groq(prompt: str, temperature: float = 0.7) -> str:
    """
    Internal synchronous call to Groq API.
    Wrapped by async functions via asyncio.to_thread() to avoid blocking
    FastAPI's event loop.
    """
    completion = _groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL,
        temperature=temperature,
    )
    content = completion.choices[0].message.content
    # Strip markdown code fences if the model adds them despite instructions
    return content.replace("```html", "").replace("```", "").strip()


# ---------------------------------------------------------------------------
# Fallback error card (used when HTML validation fails)
# ---------------------------------------------------------------------------

_FALLBACK_ERROR_HTML = """
<div class="col-12">
  <div class="alert alert-warning rounded-4 text-center py-4">
    <i class="fas fa-exclamation-triangle fa-2x text-warning mb-3 d-block"></i>
    <h5 class="fw-bold">Could not generate course cards</h5>
    <p class="text-muted mb-0 small">
      The AI returned an unexpected response. Please try again — this usually
      resolves on retry. If it keeps failing, try a shorter or cleaner PDF.
    </p>
  </div>
</div>
"""

# ---------------------------------------------------------------------------
# FIX 4: HTML validation helper
# ---------------------------------------------------------------------------

def _validate_course_html(html: str) -> bool:
    """
    Check that the AI returned at least 6 course cards.
    We look for the distinctive course-card class rather than counting
    col-md-6 divs (which could be legitimately present for other reasons).
    """
    return html.count("course-card") >= 6


# ---------------------------------------------------------------------------
# Public async functions
# ---------------------------------------------------------------------------

async def analyze_resume(resume_text: str, target_role: str) -> str:
    """Generate HTML resume analysis for the given role."""
    prompt = f"""
    Role: Expert Resume Strategist.
    Task: Audit this resume for the role of "{target_role}".
    Resume Content: "{resume_text[:5000]}"

    OUTPUT HTML ONLY. NO MARKDOWN.

    REQUIREMENTS:
    1. Summaries: Write 3 versions (Short/Medium/Long).
    2. Skills: Identify what the candidate HAS (Green) vs what is MISSING (Red) for "{target_role}".
    3. Bullets: Pick 3 weak bullet points and rewrite them to be result-oriented.

    USE THIS EXACT HTML STRUCTURE:

    <div class="analysis-container">
        <div class="mb-5 animate-fade-up">
            <h4 class="fw-bold text-dark mb-4"><i class="fas fa-pen-nib text-primary me-2"></i>Profile Summary Options</h4>
            <div class="row g-3">
                <div class="col-md-4">
                    <div class="p-4 border rounded-4 h-100 bg-white shadow-sm border-top-blue">
                        <h5 class="fw-bold text-primary mb-2">Short Version</h5>
                        <p class="text-dark small mb-0" style="line-height: 1.6;">{{Write Short Summary}}</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="p-4 border rounded-4 h-100 bg-white shadow-sm border-top-purple">
                        <h5 class="fw-bold text-purple mb-2">Medium Version</h5>
                        <p class="text-dark small mb-0" style="line-height: 1.6;">{{Write Medium Summary}}</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="p-4 border rounded-4 h-100 bg-white shadow-sm border-top-teal">
                        <h5 class="fw-bold text-teal mb-2">Long Version</h5>
                        <p class="text-dark small mb-0" style="line-height: 1.6;">{{Write Long Summary}}</p>
                    </div>
                </div>
            </div>
        </div>

        <div class="mb-5 animate-fade-up" style="animation-delay: 0.2s;">
            <h4 class="fw-bold text-dark mb-4"><i class="fas fa-chart-pie text-warning me-2"></i>Skill Gap Analysis</h4>
            <div class="row g-4">
                <div class="col-md-6">
                    <div class="p-4 rounded-4 h-100 bg-light-green border border-success">
                        <h6 class="fw-bold text-success mb-3"><i class="fas fa-check-circle me-2"></i>Skills You Have</h6>
                        <div class="d-flex flex-wrap gap-2">
                            {{Create 4-5 spans like this: <span class="badge bg-white text-success border border-success px-3 py-2 rounded-pill shadow-sm">Skill Name</span>}}
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="p-4 rounded-4 h-100 bg-light-red border border-danger">
                        <h6 class="fw-bold text-danger mb-3"><i class="fas fa-exclamation-triangle me-2"></i>Missing for {target_role}</h6>
                        <div class="d-flex flex-wrap gap-2">
                             {{Create 4-5 spans like this: <span class="badge bg-white text-danger border border-danger px-3 py-2 rounded-pill shadow-sm">Missing Skill</span>}}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="mb-4 animate-fade-up" style="animation-delay: 0.4s;">
            <h4 class="fw-bold text-dark mb-4"><i class="fas fa-magic text-purple me-2"></i>Bullet Point Improvements</h4>
            <div class="card border-0 shadow-sm rounded-4 overflow-hidden">
                <div class="table-responsive">
                    <table class="table table-bordered align-middle mb-0">
                        <thead class="bg-light">
                            <tr>
                                <th width="45%" class="text-muted text-uppercase small p-3">🔴 Weak Original</th>
                                <th width="10%" class="text-center bg-white border-0"></th>
                                <th width="45%" class="text-success text-uppercase small fw-bold p-3">🟢 Strong Rewrite</th>
                            </tr>
                        </thead>
                        <tbody>
                            {{Create 3 rows like this:
                            <tr>
                                <td class="text-muted p-3 bg-light-red small">Weak Bullet</td>
                                <td class="text-center border-0"><i class="fas fa-arrow-right text-muted"></i></td>
                                <td class="fw-bold text-dark p-3 bg-light-green small">Strong Rewrite</td>
                            </tr>
                            }}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    """
    return await asyncio.to_thread(_call_groq, prompt, 0.7)


async def generate_interview_questions(
    resume_text: str,
    role: str,
    company: str,
    q_type: str,
    count: str,
) -> str:
    """Generate interview questions HTML."""
    prompt = f"""
    Act as a Senior Interviewer at {company}.
    Role: {role}.
    Candidate Resume: "{resume_text[:5000]}"

    Task: Generate {count} {q_type} interview questions.
    FOR EACH QUESTION, PROVIDE A CONCISE "MODEL ANSWER".

    OUTPUT HTML ONLY. NO MARKDOWN.
    Use this exact card structure for EACH question:

    <div class="qa-card mb-4 animate-fade-up p-4 border rounded-4 shadow-sm bg-white">
        <div class="d-flex justify-content-between align-items-start mb-3">
            <h5 class="fw-bold text-dark w-100">Q: {{Question Text}}</h5>
        </div>
        <div class="d-flex align-items-center gap-2 mb-3">
            <button class="btn btn-sm btn-outline-danger rounded-pill fw-bold" onclick="toggleTimer(this)">
                <i class="fas fa-stopwatch me-1"></i> Timer
            </button>
            <span class="timer-display fw-bold text-danger me-3"></span>
            <button class="btn btn-sm btn-outline-success rounded-pill fw-bold" onclick="this.closest('.qa-card').querySelector('.answer-box').classList.toggle('d-none')">
                <i class="fas fa-eye me-1"></i> Show Answer
            </button>
        </div>
        <div class="p-3 bg-light rounded border small text-muted mb-2">
            <strong><i class="fas fa-lightbulb text-warning me-1"></i> Hint:</strong> {{One sentence hint}}
        </div>
        <div class="answer-box d-none p-3 bg-success bg-opacity-10 border border-success rounded text-dark small">
            <h6 class="fw-bold text-success mb-2"><i class="fas fa-check-circle me-2"></i>Model Answer</h6>
            {{Write a professional, concise model answer here}}
        </div>
    </div>
    """
    return await asyncio.to_thread(_call_groq, prompt, 0.7)


async def analyze_skill_gap(resume_text: str, target_role: str) -> str:
    """
    Generate course recommendations HTML based on skill gap.

    FIXES vs original:
      - resume_text[:5000] instead of [:2000]  (FIX 2)
      - Verified provider base URLs embedded in prompt  (FIX 3)
      - Post-process validates 6 cards were produced  (FIX 4)
    """

    # FIX 2: Increased from 2000 to 5000 chars so skills/certs buried
    # deeper in the resume are actually seen by the model.
    resume_snippet = resume_text[:5000]

    prompt = f"""
    Role: Senior Technical Career Coach.
    Task: Analyze the resume for the target role: "{target_role}".
    Resume Content: "{resume_snippet}"

    1. Identify exactly 6 MOST CRITICAL MISSING SKILLS for this role.
    2. For each missing skill, recommend ONE high-quality FREE course.
    3. Each card must use a DIFFERENT provider — no repeating the same source twice.

    FIX 3 — USE ONLY THESE PROVIDERS with their exact base URLs.
    Build COURSE_URL by appending a relevant path to the base URL below.
    Do NOT invent URLs — use the base URL as-is if you are unsure of the exact path.
{_PROVIDER_BLOCK}

    OUTPUT HTML ONLY. NO MARKDOWN. NO EXPLANATION TEXT OUTSIDE HTML.

    Output exactly 6 cards in a 2-column grid (col-md-6 each). Use these exact gradient pairs rotating across cards:
    Card 1: #4facfe → #00f2fe
    Card 2: #43e97b → #38f9d7
    Card 3: #fa709a → #fee140
    Card 4: #a18cd1 → #fbc2eb
    Card 5: #f77062 → #fe5196
    Card 6: #0ba360 → #3cba92

    For each card use this EXACT HTML structure (replace ALL placeholders):

    <div class="col-md-6">
      <div class="course-card card h-100 border-0 shadow rounded-4 position-relative overflow-hidden">
        <div class="position-absolute top-0 start-0 w-100" style="height: 5px; background: linear-gradient(90deg, GRADIENT_START 0%, GRADIENT_END 100%);"></div>
        <div class="card-body p-4 d-flex flex-column">
          <div class="d-flex align-items-start mb-3">
            <div class="rounded-3 p-2 me-3 flex-shrink-0" style="background: linear-gradient(135deg, GRADIENT_START22, GRADIENT_END22); width:46px; height:46px; display:flex; align-items:center; justify-content:center;">
              <i class="fas fa-layer-group fa-lg" style="color:GRADIENT_START;"></i>
            </div>
            <div>
              <span class="badge rounded-pill px-2 py-1 mb-1" style="background:GRADIENT_START22; color:GRADIENT_START; font-size:0.65rem; letter-spacing:1px; text-transform:uppercase; font-weight:700;">Missing Skill</span>
              <h6 class="fw-bold text-dark mb-0" style="font-size:1rem;">SKILL_NAME</h6>
            </div>
          </div>
          <div class="d-flex align-items-center gap-2 mb-3 flex-wrap">
            <span class="badge rounded-pill px-3 py-2" style="background: linear-gradient(90deg, GRADIENT_START, GRADIENT_END); color:#fff; font-size:0.72rem;">
              <i class="fas fa-university me-1"></i>PROVIDER_NAME
            </span>
            <span class="badge bg-success-subtle text-success rounded-pill px-2 py-1" style="font-size:0.68rem;">
              <i class="fas fa-check-circle me-1"></i>FREE
            </span>
            <span class="badge bg-light text-secondary rounded-pill px-2 py-1" style="font-size:0.68rem;">
              <i class="fas fa-clock me-1"></i>DURATION
            </span>
          </div>
          <p class="text-muted small mb-3" style="line-height:1.65; flex-grow:1;">WHY_THIS_COURSE_ONE_SENTENCE</p>
          <p class="text-muted" style="font-size:0.65rem; margin-bottom:0.5rem;">
            <i class="fas fa-info-circle me-1"></i>Verify the link opens the correct free course before enrolling.
          </p>
          <a href="COURSE_URL" target="_blank" rel="noopener"
             class="btn fw-bold rounded-pill w-100 py-2"
             style="background: linear-gradient(90deg, GRADIENT_START, GRADIENT_END); color:#fff; border:none; font-size:0.85rem;">
            Start Learning <i class="fas fa-arrow-right ms-2"></i>
          </a>
        </div>
      </div>
    </div>

    Wrap ALL 6 cards inside: <div class="row g-4">...</div>
    DURATION must be a realistic estimate like "~6 hrs", "~10 hrs", "~3 hrs".
    COURSE_URL must start with one of the verified base URLs listed above.
    """

    html = await asyncio.to_thread(_call_groq, prompt, 0.3)

    # FIX 4: Validate the model returned 6 cards. If not, return a safe
    # fallback error so the user sees a clear message instead of broken UI.
    if not _validate_course_html(html):
        logger.warning(
            f"analyze_skill_gap returned malformed HTML "
            f"(found {html.count('course-card')} cards, expected 6). "
            f"Returning fallback error card."
        )
        return f'<div class="row g-4">{_FALLBACK_ERROR_HTML}</div>'

    return html