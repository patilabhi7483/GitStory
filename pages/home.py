"""
pages/home.py — Landing page + repository input form
Routes:
  GET  /         → renders landing page with 3-tab input form
  POST /analyze  → validates input, runs pipeline, redirects to /result/<id>
"""

import re
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash
import database
import config
from services.git_parser import (
    parse_from_url, parse_from_file, parse_from_text,
    extract_repo_name
)
from services.commit_classifier import group_commits, serialize_groups_for_prompt
from services.grok_client import grok

home_bp = Blueprint("home", __name__, template_folder="../components")

# ── Landing Page ──────────────────────────────────────────────────────────────

@home_bp.get("/")
def index():
    return render_template("home_page.html")


# ── Analysis Pipeline ─────────────────────────────────────────────────────────

@home_bp.post("/analyze")
def analyze():
    input_mode = request.form.get("input_mode", "url").strip()
    format_pref = request.form.get("format_pref", config.DEFAULT_NARRATIVE_FORMAT)

    try:
        commits, repo_url, repo_name = _get_commits(input_mode)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("home.index"))
    except Exception as e:
        flash(f"Failed to parse repository: {str(e)}", "error")
        return redirect(url_for("home.index"))

    if not commits:
        flash("No commits found. Please check your input and try again.", "warning")
        return redirect(url_for("home.index"))

    # Classify + group
    groups = group_commits(commits)
    commit_data_text = serialize_groups_for_prompt(groups)

    # Unique shareable slug
    slug = _make_slug(repo_name)

    # Save to DB (status=pending)
    analysis_id = database.save_analysis(
        slug=slug,
        repo_url=repo_url,
        repo_name=repo_name,
        input_mode=input_mode,
        raw_commits=commits,
        grouped_commits=groups,
        commit_count=len(commits),
    )

    # Generate narratives via Grok
    try:
        narratives = grok.generate_all(commit_data_text, repo_name)
        database.update_narratives(analysis_id, narratives)
    except Exception as e:
        database.set_error(analysis_id, str(e))
        flash(f"AI generation failed: {str(e)}", "error")

    return redirect(url_for("analyze.result", analysis_id=analysis_id, fmt=format_pref))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_commits(input_mode: str):
    if input_mode == "url":
        url = request.form.get("repo_url", "").strip()
        if not url:
            raise ValueError("Please enter a repository URL.")
        commits = parse_from_url(url)
        repo_name = extract_repo_name(url)
        return commits, url, repo_name

    elif input_mode == "file":
        file = request.files.get("git_log_file")
        if not file or not file.filename:
            raise ValueError("Please upload a git log .txt file.")
        content = file.read().decode("utf-8", errors="replace")
        if len(content) > config.MAX_PASTE_CHARS:
            raise ValueError(f"File too large. Maximum {config.MAX_PASTE_CHARS:,} characters.")
        commits = parse_from_file(content)
        repo_name = file.filename.replace(".txt", "").replace("-", " ").title()
        return commits, f"uploaded:{file.filename}", repo_name

    elif input_mode == "paste":
        raw_text = request.form.get("raw_commits", "").strip()
        if not raw_text:
            raise ValueError("Please paste your git log output.")
        if len(raw_text) > config.MAX_PASTE_CHARS:
            raise ValueError(f"Input too large. Maximum {config.MAX_PASTE_CHARS:,} characters.")
        commits = parse_from_text(raw_text)
        return commits, "pasted:raw", "Pasted Repository"

    raise ValueError(f"Unknown input mode: {input_mode}")


def _make_slug(repo_name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (repo_name or "repo").lower()).strip("-")
    base = (base[:20] or "repo").strip("-") or "repo"
    unique = uuid.uuid4().hex[:6]
    return f"{base}-{unique}"
