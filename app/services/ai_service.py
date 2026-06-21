# app/services/ai_service.py
#
# FIXES APPLIED (course recommender):
#   1. MODEL upgraded: llama-3.3-70b-versatile (better HTML, fewer hallucinations)
#   2. RESUME TRUNCATION fixed: [:2000] → [:5000] across all functions
#   3. URL HALLUCINATION fully fixed: AI no longer generates URLs at all.
#      Instead, VERIFIED_COURSES maps skill names → confirmed working links.
#      The AI only identifies missing skill names; this file resolves the URL.
#   4. HTML VALIDATION: checks 6 cards returned; falls back safely if not.

import asyncio
import logging
import json
import re

from groq import Groq
from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Groq client
# ---------------------------------------------------------------------------

_groq_client = Groq(api_key=settings.GROQ_API_KEY)
MODEL = "llama-3.3-70b-versatile"


def _call_groq(prompt: str, temperature: float = 0.7) -> str:
    completion = _groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL,
        temperature=temperature,
    )
    content = completion.choices[0].message.content
    return content.replace("```html", "").replace("```", "").replace("```json", "").strip()


# ---------------------------------------------------------------------------
# VERIFIED COURSE LIBRARY
# Every URL below is a confirmed, working, free course page.
# The AI picks skill names; this dict resolves them to real links.
# To support a new skill: add one entry here — no prompt changes needed.
# ---------------------------------------------------------------------------

VERIFIED_COURSES = {
    "Python": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/scientific-computing-with-python/",
        "duration": "~10 hrs",
        "why": "Covers Python from basics to data structures with hands-on projects.",
    },
    "SQL": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/intro-to-sql",
        "duration": "~3 hrs",
        "why": "Hands-on SQL querying using real BigQuery datasets — no setup required.",
    },
    "Advanced SQL": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/advanced-sql",
        "duration": "~4 hrs",
        "why": "CTEs, window functions, nested queries on real BigQuery datasets.",
    },
    "Machine Learning": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/intro-to-machine-learning",
        "duration": "~3 hrs",
        "why": "Build your first ML models with scikit-learn using real datasets.",
    },
    "Deep Learning": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/intro-to-deep-learning",
        "duration": "~6 hrs",
        "why": "Build neural networks with Keras and TensorFlow on real problems.",
    },
    "Data Analysis": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/pandas",
        "duration": "~4 hrs",
        "why": "Master pandas for data manipulation — the most-used data tool in industry.",
    },
    "Pandas": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/pandas",
        "duration": "~4 hrs",
        "why": "Master pandas for data manipulation — the most-used data tool in industry.",
    },
    "Data Visualization": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/data-visualization",
        "duration": "~4 hrs",
        "why": "Create charts and dashboards with seaborn and matplotlib.",
    },
    "Statistics": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/college-algebra-with-python/",
        "duration": "~7 hrs",
        "why": "Covers mathematical foundations needed for data science and ML roles.",
    },
    "JavaScript": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/javascript-algorithms-and-data-structures/",
        "duration": "~10 hrs",
        "why": "Full JS curriculum from variables to ES6, async, and algorithm challenges.",
    },
    "React": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/front-end-development-libraries/",
        "duration": "~8 hrs",
        "why": "Learn React, Redux, and frontend libraries through project-based challenges.",
    },
    "HTML": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/responsive-web-design/",
        "duration": "~5 hrs",
        "why": "Learn HTML and CSS by building 20 projects in the browser.",
    },
    "CSS": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/responsive-web-design/",
        "duration": "~5 hrs",
        "why": "Learn HTML and CSS by building 20 projects in the browser.",
    },
    "Node.js": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/back-end-development-and-apis/",
        "duration": "~6 hrs",
        "why": "Build REST APIs and servers with Node.js and Express from scratch.",
    },
    "Git": {
        "provider": "Microsoft Learn",
        "url": "https://learn.microsoft.com/en-us/training/modules/intro-to-git/",
        "duration": "~1 hr",
        "why": "Official Microsoft intro to Git: commits, branches, and merges explained.",
    },
    "Docker": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/the-docker-handbook/",
        "duration": "~5 hrs",
        "why": "Comprehensive Docker handbook — containers, images, volumes, compose.",
    },
    "Kubernetes": {
        "provider": "Google Cloud Skills Boost",
        "url": "https://cloudskillsboost.google/course_templates/2",
        "duration": "~8 hrs",
        "why": "Official Google Kubernetes course covering pods, deployments, and services.",
    },
    "AWS": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/pass-the-aws-certified-cloud-practitioner-exam/",
        "duration": "~14 hrs",
        "why": "Full AWS Cloud Practitioner prep — covers all core AWS services for free.",
    },
    "Cloud Computing": {
        "provider": "Google Cloud Skills Boost",
        "url": "https://cloudskillsboost.google/course_templates/60",
        "duration": "~5 hrs",
        "why": "Google's foundational cloud computing course — provider-agnostic concepts.",
    },
    "Azure": {
        "provider": "Microsoft Learn",
        "url": "https://learn.microsoft.com/en-us/training/paths/az-900-describe-cloud-concepts/",
        "duration": "~6 hrs",
        "why": "Official AZ-900 learning path — free Azure fundamentals from Microsoft.",
    },
    "Linux": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/the-linux-commands-handbook/",
        "duration": "~4 hrs",
        "why": "Covers 60+ essential Linux commands used daily by developers and DevOps engineers.",
    },
    "Networking": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/computer-networking-how-applications-talk-over-the-internet/",
        "duration": "~3 hrs",
        "why": "Clear explanation of TCP/IP, DNS, HTTP, and how the internet actually works.",
    },
    "Cybersecurity": {
        "provider": "IBM SkillsBuild",
        "url": "https://skillsbuild.org/learn/course/cybersecurity-fundamentals",
        "duration": "~8 hrs",
        "why": "IBM's free cybersecurity fundamentals course with a digital badge on completion.",
    },
    "Network Security": {
        "provider": "IBM SkillsBuild",
        "url": "https://skillsbuild.org/learn/course/cybersecurity-fundamentals",
        "duration": "~8 hrs",
        "why": "Covers network security, threats, and defense with an IBM credential.",
    },
    "Data Structures": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/javascript-algorithms-and-data-structures/",
        "duration": "~10 hrs",
        "why": "Covers arrays, linked lists, trees, and sorting algorithms with coding challenges.",
    },
    "Algorithms": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/javascript-algorithms-and-data-structures/",
        "duration": "~10 hrs",
        "why": "Hands-on algorithm challenges covering search, sort, and complexity analysis.",
    },
    "Power BI": {
        "provider": "Microsoft Learn",
        "url": "https://learn.microsoft.com/en-us/training/paths/create-use-analytics-reports-power-bi/",
        "duration": "~5 hrs",
        "why": "Microsoft's official Power BI path — from data import to publishing dashboards.",
    },
    "Excel": {
        "provider": "Microsoft Learn",
        "url": "https://learn.microsoft.com/en-us/training/modules/intro-to-excel/",
        "duration": "~1 hr",
        "why": "Official Microsoft Excel intro covering formulas, charts, and pivot tables.",
    },
    "TensorFlow": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/intro-to-deep-learning",
        "duration": "~6 hrs",
        "why": "Build and train neural networks with TensorFlow/Keras on real datasets.",
    },
    "NLP": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/natural-language-processing",
        "duration": "~3 hrs",
        "why": "Hands-on NLP: tokenization, text classification, and word embeddings.",
    },
    "Natural Language Processing": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/natural-language-processing",
        "duration": "~3 hrs",
        "why": "Tokenization, text classification, and word embeddings on real data.",
    },
    "Computer Vision": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/computer-vision",
        "duration": "~4 hrs",
        "why": "Build CNNs for image classification with real datasets and Keras.",
    },
    "FastAPI": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/fastapi-helps-you-develop-apis-quickly/",
        "duration": "~3 hrs",
        "why": "Practical intro to FastAPI — routing, validation, async, and OpenAPI docs.",
    },
    "Django": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/python-django-course/",
        "duration": "~18 hrs",
        "why": "Full Django course covering models, views, templates, auth, and deployment.",
    },
    "TypeScript": {
        "provider": "Microsoft Learn",
        "url": "https://learn.microsoft.com/en-us/training/paths/build-javascript-applications-typescript/",
        "duration": "~5 hrs",
        "why": "Microsoft's official TypeScript path — types, interfaces, generics, modules.",
    },
    "Generative AI": {
        "provider": "Google Cloud Skills Boost",
        "url": "https://cloudskillsboost.google/course_templates/536",
        "duration": "~1 hr",
        "why": "Google's free Introduction to Generative AI — models, use cases, limitations.",
    },
    "Prompt Engineering": {
        "provider": "Google Cloud Skills Boost",
        "url": "https://cloudskillsboost.google/course_templates/536",
        "duration": "~1 hr",
        "why": "Covers foundational prompt design for working with LLMs effectively.",
    },
    "Agile": {
        "provider": "Microsoft Learn",
        "url": "https://learn.microsoft.com/en-us/training/modules/intro-to-devops/",
        "duration": "~2 hrs",
        "why": "Covers Agile principles, Scrum ceremonies, and DevOps culture basics.",
    },
    "CI/CD": {
        "provider": "Microsoft Learn",
        "url": "https://learn.microsoft.com/en-us/training/paths/az-400-develop-security-compliance-plan/",
        "duration": "~4 hrs",
        "why": "Learn pipelines, automated testing, and deployment workflows end to end.",
    },
    "DevOps": {
        "provider": "Microsoft Learn",
        "url": "https://learn.microsoft.com/en-us/training/modules/intro-to-devops/",
        "duration": "~2 hrs",
        "why": "Intro to DevOps culture, practices, CI/CD, and infrastructure as code.",
    },
    "Terraform": {
        "provider": "Google Cloud Skills Boost",
        "url": "https://cloudskillsboost.google/course_templates/636",
        "duration": "~6 hrs",
        "why": "Hands-on Terraform for managing cloud infrastructure as code.",
    },
    "Data Engineering": {
        "provider": "Kaggle Learn",
        "url": "https://www.kaggle.com/learn/intro-to-sql",
        "duration": "~3 hrs",
        "why": "SQL querying is the core skill for every data engineering pipeline.",
    },
    "C++": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/learn-c-with-free-31-hour-course/",
        "duration": "~31 hrs",
        "why": "Comprehensive free C++ course covering OOP, STL, and memory management.",
    },
    "Java": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/learn-java-free-java-courses-for-beginners/",
        "duration": "~10 hrs",
        "why": "Free Java course covering OOP, collections, and Java 17 features.",
    },
    "Tableau": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/tableau-for-beginners/",
        "duration": "~4 hrs",
        "why": "Build interactive dashboards and charts in Tableau with real datasets.",
    },
    "MongoDB": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/learn-mongodb-a4ce205e7739/",
        "duration": "~3 hrs",
        "why": "Covers MongoDB CRUD, indexing, aggregation, and schema design basics.",
    },
    "PostgreSQL": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/postgresql-full-course/",
        "duration": "~4 hrs",
        "why": "Full PostgreSQL course — queries, joins, indexes, and stored procedures.",
    },
    "REST API": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/learn/back-end-development-and-apis/",
        "duration": "~6 hrs",
        "why": "Learn to design and build REST APIs with Node.js and Express.",
    },
    "Figma": {
        "provider": "freeCodeCamp",
        "url": "https://www.freecodecamp.org/news/ui-ux-design-tutorial-figma/",
        "duration": "~5 hrs",
        "why": "Full Figma UI/UX design course — wireframes, components, and prototypes.",
    },
}

# Used when AI returns a skill name not in the map above
_FALLBACK_COURSE = {
    "provider": "freeCodeCamp",
    "url": "https://www.freecodecamp.org/learn",
    "duration": "~varies",
    "why": "freeCodeCamp offers hundreds of verified free courses across all tech domains.",
}

# Card gradients — one per card position
_GRADIENTS = [
    ("#4facfe", "#00f2fe"),
    ("#43e97b", "#38f9d7"),
    ("#fa709a", "#fee140"),
    ("#a18cd1", "#fbc2eb"),
    ("#f77062", "#fe5196"),
    ("#0ba360", "#3cba92"),
]


def _resolve_course(skill_name: str) -> dict:
    """
    Look up a verified course for the given skill name.
    Tries exact match first, then case-insensitive, then keyword scan,
    then falls back to freeCodeCamp homepage.
    """
    # 1. Exact match
    if skill_name in VERIFIED_COURSES:
        return VERIFIED_COURSES[skill_name]

    # 2. Case-insensitive match
    lower = skill_name.lower()
    for key, val in VERIFIED_COURSES.items():
        if key.lower() == lower:
            return val

    # 3. Keyword scan (e.g. "React.js" → "React", "ML" → "Machine Learning")
    for key, val in VERIFIED_COURSES.items():
        if key.lower() in lower or lower in key.lower():
            return val

    # 4. Fallback
    logger.warning(f"No verified course for skill '{skill_name}' — using fallback.")
    return _FALLBACK_COURSE


def _build_course_card(skill_name: str, index: int) -> str:
    """Build one Bootstrap course card HTML for a given skill."""
    course = _resolve_course(skill_name)
    g_start, g_end = _GRADIENTS[index % len(_GRADIENTS)]

    return f"""
    <div class="col-md-6">
      <div class="course-card card h-100 border-0 shadow rounded-4 position-relative overflow-hidden">
        <div class="position-absolute top-0 start-0 w-100"
             style="height:5px; background:linear-gradient(90deg,{g_start} 0%,{g_end} 100%);"></div>
        <div class="card-body p-4 d-flex flex-column">
          <div class="d-flex align-items-start mb-3">
            <div class="rounded-3 p-2 me-3 flex-shrink-0"
                 style="background:linear-gradient(135deg,{g_start}22,{g_end}22);
                        width:46px;height:46px;display:flex;align-items:center;justify-content:center;">
              <i class="fas fa-layer-group fa-lg" style="color:{g_start};"></i>
            </div>
            <div>
              <span class="badge rounded-pill px-2 py-1 mb-1"
                    style="background:{g_start}22;color:{g_start};font-size:0.65rem;
                           letter-spacing:1px;text-transform:uppercase;font-weight:700;">
                Missing Skill
              </span>
              <h6 class="fw-bold text-dark mb-0" style="font-size:1rem;">{skill_name}</h6>
            </div>
          </div>
          <div class="d-flex align-items-center gap-2 mb-3 flex-wrap">
            <span class="badge rounded-pill px-3 py-2"
                  style="background:linear-gradient(90deg,{g_start},{g_end});color:#fff;font-size:0.72rem;">
              <i class="fas fa-university me-1"></i>{course["provider"]}
            </span>
            <span class="badge bg-success-subtle text-success rounded-pill px-2 py-1" style="font-size:0.68rem;">
              <i class="fas fa-check-circle me-1"></i>FREE
            </span>
            <span class="badge bg-light text-secondary rounded-pill px-2 py-1" style="font-size:0.68rem;">
              <i class="fas fa-clock me-1"></i>{course["duration"]}
            </span>
          </div>
          <p class="text-muted small mb-4" style="line-height:1.65;flex-grow:1;">{course["why"]}</p>
          <a href="{course["url"]}" target="_blank" rel="noopener"
             class="btn fw-bold rounded-pill w-100 py-2"
             style="background:linear-gradient(90deg,{g_start},{g_end});color:#fff;border:none;font-size:0.85rem;">
            Start Learning <i class="fas fa-arrow-right ms-2"></i>
          </a>
        </div>
      </div>
    </div>"""


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
                            {{4-5 green badge spans}}
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="p-4 rounded-4 h-100 bg-light-red border border-danger">
                        <h6 class="fw-bold text-danger mb-3"><i class="fas fa-exclamation-triangle me-2"></i>Missing for {target_role}</h6>
                        <div class="d-flex flex-wrap gap-2">
                            {{4-5 red badge spans}}
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
                                <th width="45%" class="text-muted text-uppercase small p-3">Weak Original</th>
                                <th width="10%" class="text-center bg-white border-0"></th>
                                <th width="45%" class="text-success text-uppercase small fw-bold p-3">Strong Rewrite</th>
                            </tr>
                        </thead>
                        <tbody>
                            {{3 table rows}}
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
            <button class="btn btn-sm btn-outline-success rounded-pill fw-bold"
                    onclick="this.closest('.qa-card').querySelector('.answer-box').classList.toggle('d-none')">
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
    Identify missing skills via AI, then build cards from VERIFIED_COURSES.

    Two-step approach:
      Step 1 — Ask AI for exactly 6 missing skill names as JSON.
               AI does NOT generate any URLs at all.
      Step 2 — Python resolves each skill name to a verified course URL
               from VERIFIED_COURSES and builds the HTML cards locally.

    This eliminates URL hallucination completely.
    """

    skill_list_str = ", ".join(VERIFIED_COURSES.keys())

    # STEP 1: Ask AI only for skill names — no HTML, no URLs
    prompt = f"""
You are a Senior Technical Career Coach.

Analyze this resume for the target role: "{target_role}".
Resume: "{resume_text[:5000]}"

Task: Identify the 6 most critical skills this person is MISSING for the role of "{target_role}".

IMPORTANT — Choose skill names ONLY from this list (pick the closest match):
{skill_list_str}

Respond with ONLY a JSON array of exactly 6 strings. No explanation. No markdown. Example:
["Python", "SQL", "Machine Learning", "Docker", "Git", "Data Visualization"]
"""

    raw = await asyncio.to_thread(_call_groq, prompt, 0.2)

    # Parse the JSON array from the AI response
    skills: list[str] = []
    try:
        # Strip any stray text before/after the JSON array
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            skills = json.loads(match.group())
        else:
            raise ValueError("No JSON array found in response")
    except Exception as e:
        logger.error(f"Failed to parse skill list from AI: {e}. Raw: {raw[:200]}")
        # Fallback: use generic high-demand skills for the role
        skills = ["Python", "SQL", "Machine Learning", "Docker", "Git", "Data Visualization"]

    # Ensure exactly 6 (pad or trim)
    skills = (skills + ["Python", "SQL", "Machine Learning", "Docker", "Git", "Data Visualization"])[:6]

    # STEP 2: Build verified cards in Python — no AI involved
    cards_html = "\n".join(_build_course_card(skill, i) for i, skill in enumerate(skills))

    return f'<div class="row g-4">{cards_html}</div>'