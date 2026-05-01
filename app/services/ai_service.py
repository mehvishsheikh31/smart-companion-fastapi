# app/services/ai_service.py
#
# PURPOSE: All Groq AI API calls in one place.
#
# YOUR OLD FLASK APPROACH:
#   client = Groq(api_key=os.getenv("GROK_API_KEY"))  # global variable
#   completion = client.chat.completions.create(...)   # called in every route
#
# PROBLEMS WITH THAT APPROACH:
#   - AI prompts mixed with HTTP routing code — hard to read
#   - Can't easily swap AI providers (if you want to try OpenAI, change 10+ places)
#   - Can't test AI logic without triggering a web request
#   - Groq client created once at import time (bad for async apps)
#
# THE SERVICE APPROACH:
#   - All prompts defined here as functions
#   - Routes call: result = await ai_service.analyze_resume(text, role)
#   - Easy to swap Groq for OpenAI: change only this file
#   - Easy to test: mock this module in tests

import logging
from groq import Groq
from app.core.config import settings

logger = logging.getLogger(__name__)

# Create Groq client once (it's thread-safe)
# Note: Groq's Python SDK is synchronous. We run it in a thread pool
# via asyncio.to_thread() in the functions below to avoid blocking FastAPI.
_groq_client = Groq(api_key=settings.GROQ_API_KEY)
MODEL = "llama-3.1-8b-instant"


def _call_groq(prompt: str, temperature: float = 0.7) -> str:
    """
    Internal synchronous call to Groq API.
    This is wrapped by async functions below using asyncio.to_thread().
    
    Why asyncio.to_thread()?
        FastAPI is async. If you call a synchronous/blocking function directly
        inside an async route, you freeze the entire server — no other request
        can be processed while the AI is thinking.
        
        asyncio.to_thread() runs the blocking function on a separate thread,
        letting FastAPI handle other requests while this one waits for Groq.
    """
    completion = _groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL,
        temperature=temperature
    )
    content = completion.choices[0].message.content
    # Clean up markdown code blocks if AI adds them
    return content.replace("```html", "").replace("```", "").strip()


import asyncio

async def analyze_resume(resume_text: str, target_role: str) -> str:
    """
    Generate HTML resume analysis for the given role.
    
    This is the same prompt as your Flask app, just moved here.
    Running in thread pool so it doesn't block FastAPI's event loop.
    """
    prompt = f"""
    Role: Expert Resume Strategist.
    Task: Audit this resume for the role of "{target_role}".
    Resume Content: "{resume_text[:3000]}"
    
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
    
    # asyncio.to_thread runs _call_groq in a thread pool
    # This prevents blocking the FastAPI event loop
    return await asyncio.to_thread(_call_groq, prompt, 0.7)


async def generate_interview_questions(
    resume_text: str,
    role: str,
    company: str,
    q_type: str,
    count: str
) -> str:
    """Generate interview questions HTML. Same prompt as Flask, moved here."""
    
    prompt = f"""
    Act as a Senior Interviewer at {company}.
    Role: {role}.
    Candidate Resume: "{resume_text[:2000]}"
    
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
    """Generate course recommendations HTML based on skill gap."""

    prompt = f"""
    Role: Senior Technical Career Coach.
    Task: Analyze the resume for the target role: "{target_role}".
    Resume Content: "{resume_text[:2000]}"

    1. Identify exactly 6 MOST CRITICAL MISSING SKILLS for this role.
    2. For each missing skill, recommend ONE high-quality FREE course from the providers below.
    3. Each card must use a DIFFERENT provider — no repeating the same source twice.

    USE ONLY THESE PROVIDERS (pick the best fit per skill):
    - IBM SkillsBuild (ibmskillsbuild.com)
    - GeeksforGeeks (geeksforgeeks.org/courses)
    - Kaggle Learn (kaggle.com/learn)
    - PW Skills (pwskills.com)
    - Coding Ninjas / Code360 (codingninjas.com)
    - Google Cloud Skills Boost (cloudskillsboost.google)
    - freeCodeCamp (freecodecamp.org/learn)
    - Microsoft Learn (learn.microsoft.com)
    - NPTEL (nptel.ac.in)

    OUTPUT HTML ONLY. NO MARKDOWN. NO EXPLANATION TEXT OUTSIDE HTML.

    Output exactly 6 cards in a 2-column grid (col-md-6 each). Use these exact gradient pairs rotating across cards:
    Card 1: #4facfe → #00f2fe
    Card 2: #43e97b → #38f9d7
    Card 3: #fa709a → #fee140
    Card 4: #a18cd1 → #fbc2eb
    Card 5: #f77062 → #fe5196
    Card 6: #0ba360 → #3cba92

    For each card use this EXACT HTML structure (replace ALL {{placeholders}}):

    <div class="col-md-6">
      <div class="course-card card h-100 border-0 shadow rounded-4 position-relative overflow-hidden">
        <div class="position-absolute top-0 start-0 w-100" style="height: 5px; background: linear-gradient(90deg, {{GRADIENT_START}} 0%, {{GRADIENT_END}} 100%);"></div>
        <div class="card-body p-4 d-flex flex-column">
          <div class="d-flex align-items-start mb-3">
            <div class="rounded-3 p-2 me-3 flex-shrink-0" style="background: linear-gradient(135deg, {{GRADIENT_START}}22, {{GRADIENT_END}}22); width:46px; height:46px; display:flex; align-items:center; justify-content:center;">
              <i class="fas fa-layer-group fa-lg" style="color:{{GRADIENT_START}};"></i>
            </div>
            <div>
              <span class="badge rounded-pill px-2 py-1 mb-1" style="background:{{GRADIENT_START}}22; color:{{GRADIENT_START}}; font-size:0.65rem; letter-spacing:1px; text-transform:uppercase; font-weight:700;">Missing Skill</span>
              <h6 class="fw-bold text-dark mb-0" style="font-size:1rem;">{{SKILL_NAME}}</h6>
            </div>
          </div>
          <div class="d-flex align-items-center gap-2 mb-3 flex-wrap">
            <span class="badge rounded-pill px-3 py-2" style="background: linear-gradient(90deg, {{GRADIENT_START}}, {{GRADIENT_END}}); color:#fff; font-size:0.72rem;">
              <i class="fas fa-university me-1"></i>{{PROVIDER_NAME}}
            </span>
            <span class="badge bg-success-subtle text-success rounded-pill px-2 py-1" style="font-size:0.68rem;">
              <i class="fas fa-check-circle me-1"></i>FREE
            </span>
            <span class="badge bg-light text-secondary rounded-pill px-2 py-1" style="font-size:0.68rem;">
              <i class="fas fa-clock me-1"></i>{{DURATION}}
            </span>
          </div>
          <p class="text-muted small mb-4" style="line-height:1.65; flex-grow:1;">{{WHY_THIS_COURSE_ONE_SENTENCE}}</p>
          <a href="{{COURSE_URL}}" target="_blank" rel="noopener"
             class="btn fw-bold rounded-pill w-100 py-2"
             style="background: linear-gradient(90deg, {{GRADIENT_START}}, {{GRADIENT_END}}); color:#fff; border:none; font-size:0.85rem;">
            Start Learning <i class="fas fa-arrow-right ms-2"></i>
          </a>
        </div>
      </div>
    </div>

    Wrap ALL 6 cards inside: <div class="row g-4">...</div>
    DURATION must be a realistic estimate like "~6 hrs", "~10 hrs", "~3 hrs".
    COURSE_URL must be a real, working URL to the free course on that provider's site.
    """

    return await asyncio.to_thread(_call_groq, prompt, 0.3)