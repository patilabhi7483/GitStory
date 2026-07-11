"""
config.py — CENTRAL CONFIGURATION FILE
=======================================
This is the ONLY file you need to edit after deploying Commit Story.
All pages and services import from here. No other file needs to be modified.
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─── Database ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "commitstory.db")

# ─── Redis (Celery broker + rate limit storage) ──────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# ─── Groq AI API ──────────────────────────────────────────────────────────
# Get your FREE key at: https://console.groq.com/
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")
GROQ_MODEL = "llama-3.3-70b-versatile"  # Free model on Groq

# GitHub API (used for repository URL analysis on github.com)
GITHUB_API_TOKEN = os.environ.get("GITHUB_API_TOKEN", "")
GITHUB_API_BASE_URL = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")
GITHUB_API_TIMEOUT_SECONDS = int(os.environ.get("GITHUB_API_TIMEOUT_SECONDS", "20"))
GITHUB_API_USER_AGENT = os.environ.get("GITHUB_API_USER_AGENT", "CommitStory/1.0")

# ─── Branding ────────────────────────────────────────────────────────────────
APP_NAME = "Commit Story"
APP_TAGLINE = "Turn your git history into a human story"
APP_VERSION = "1.0.0"

# ─── Analysis Limits ────────────────────────────────────────────────────────
MAX_COMMITS_PER_ANALYSIS = 500          # Throttle for large repos
MAX_PASTE_CHARS = 50_000               # Max raw paste input size
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB max upload size

# ─── Git / Cloning ──────────────────────────────────────────────────────────
TEMP_CLONE_DIR = os.path.join(BASE_DIR, "temp")
CLONE_DEPTH = 200                       # Shallow clone depth
ENABLE_GIT_CLONE_FALLBACK = True
ALLOWED_REPO_HOSTS = [
    "github.com",
    "gitlab.com",
    "bitbucket.org",
]

# ─── Narrative Formats ───────────────────────────────────────────────────────
NARRATIVE_FORMATS = [
    ("release", "Release Notes"),
    ("standup", "Standup Summary"),
    ("onboarding", "Onboarding Story"),
    ("portfolio", "Portfolio README"),
]
DEFAULT_NARRATIVE_FORMAT = "release"

# ─── Feature Flags ────────────────────────────────────────────────────────────
ENABLE_HISTORY = True       # Show /history page
ENABLE_SHARE = True         # Enable /share/<slug> public links

# ─── Flask ───────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod-immediately")
DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"