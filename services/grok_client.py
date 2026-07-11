"""
services/grok_client.py
=========================
Wraps Groq AI API (groq.com) using the OpenAI-compatible SDK.
Uses the free llama-3.3-70b-versatile model.
Provides 4 prompt templates and generates all narrative formats.
"""

import time
import os
import config

try:
    from openai import OpenAI
    GROK_AVAILABLE = True
except ImportError:
    GROK_AVAILABLE = False

# ── Prompt Templates ───────────────────────────────────────────────────────────
PROMPTS = {
    "release": """You are a technical writer. Based ONLY on the commit data below, write professional Release Notes in Markdown.

Instructions:
- **Commit Context Understanding**: Instead of raw messages like "Added login", convert them into descriptive, professional summaries like "Implemented user authentication system".
- Group by week/sprint with `## Week of ...` headings
- Use bullet points: `- **[Type]** Short, clear description`
- Include a `### 🏷️ Milestones` section if any version tags exist
- End with a `### 📊 Summary` with commit counts by type
- Do NOT invent features not mentioned in commits
- Be concise and professional

---START_COMMIT_DATA---
{commit_data}
---END_COMMIT_DATA---

Output only the Markdown release notes. Start with `# Release Notes`.
""",

    "standup": """You are a team lead writing a weekly standup report. Based ONLY on the commit data below, write a clear standup summary.

Instructions:
- **Commit Context Understanding**: Convert fragmented commit messages into meaningful narratives (e.g., "Updated CSS" -> "Refined user interface styling for better responsiveness").
- One paragraph per week: "This week the team..." 
- Mention key features shipped, bugs fixed, and any milestones
- Use active voice and team-friendly language
- Keep each weekly paragraph to 3-5 sentences
- Do NOT invent work not shown in commits

---START_COMMIT_DATA---
{commit_data}
---END_COMMIT_DATA---

Output only the standup summary in Markdown. Start with `# Standup Summary`.
""",

    "onboarding": """You are a senior engineer writing an onboarding guide for a new team member. Based ONLY on the commit history below, tell the story of how this project evolved.

Instructions:
- **Commit Context Understanding**: Convert technical commit logs into educational storytelling (e.g., "Merged PR #12" -> "Integrated the foundational data storage architecture").
- Start with an introduction paragraph about the project
- Tell the story chronologically: "The project started with...", "In the following weeks...", "A major milestone was reached when..."
- Explain what each major phase accomplished
- Highlight key architectural decisions visible from commits
- End with a "Current State" paragraph
- Be welcoming and educational

---START_COMMIT_DATA---
{commit_data}
---END_COMMIT_DATA---

Output only the onboarding story in Markdown. Start with `# Project History & Onboarding Guide`.
""",

    "portfolio": """You are a developer writing a professional portfolio README for this project. Based ONLY on the commit data below, write a compelling project description.

Instructions:
- **Commit Context Understanding**: Present technical work as impressive achievements (e.g., "Fixed bug" -> "Enhanced application stability and performance through targeted bug resolution").
- `# Project Name` heading (infer from commit context)
- A 2-3 sentence project description
- `## ✨ Features` — bullet list of key features implemented (from feature commits)
- `## 🛠️ Tech Signals` — infer technologies from commit messages
- `## 📈 Development Stats` — commit counts, active weeks, milestones
- `## 🏗️ Development Journey` — brief narrative of how it was built
- Professional, impressive tone suitable for a portfolio

---START_COMMIT_DATA---
{commit_data}
---END_COMMIT_DATA---

Output only the portfolio README in Markdown. Start with `# ` followed by the project name.
""",
}

DEMO_OUTPUTS = {
    "release": """# Release Notes

> ⚠️ **Demo Mode** — Add your Groq API key in `.env` for real AI output.

## Week of Apr 01, 2024 (3 commits)

- **[Feature]** Added user authentication with JWT tokens
- **[Feature]** Implemented dashboard homepage
- **[Bug Fix]** Fixed login redirect loop on mobile browsers

### 📊 Summary
| Type | Count |
|------|-------|
| Feature | 2 |
| Bug Fix | 1 |
""",
    "standup": """# Standup Summary

> ⚠️ **Demo Mode** — Add your Groq API key in `.env` for real AI output.

This week the team made significant progress. We shipped the user authentication system including JWT token support, and built out the main dashboard. We also resolved a critical bug affecting mobile users where the login page was caught in a redirect loop.

""",
    "onboarding": """# Project History & Onboarding Guide

> ⚠️ **Demo Mode** — Add your Groq API key in `.env` for real AI output.

Welcome to the team! This guide will walk you through the history of this project based on its commit history.

The project began with foundational scaffolding and setup. Over the following weeks, the team built out core features including authentication, the main UI, and key business logic. The codebase has evolved through multiple rounds of bug fixing and refinement.

**Current State**: The project is actively developed with regular commits across features, bug fixes, and maintenance tasks.
""",
    "portfolio": """# My Project

> ⚠️ **Demo Mode** — Add your Groq API key in `.env` for real AI output.

A full-stack web application built from the ground up with modern development practices.

## ✨ Features
- User authentication and authorization
- Interactive dashboard with real-time data
- Mobile-responsive design

## 📈 Development Stats
- Multiple active development weeks
- Commits across features, bug fixes, and infrastructure

## 🏗️ Development Journey
This project was built iteratively, starting with core infrastructure and progressively adding features based on user feedback.
""",
}


class GrokClient:
    def __init__(self):
        self._configured = False
        self._client = None

        if not GROK_AVAILABLE:
            print("[Groq] openai package not installed. Run: pip install openai")
            return

        # Read key from env or config
        key = os.environ.get("GROQ_API_KEY") or getattr(config, "GROQ_API_KEY", "")

        # Valid key should not be empty or placeholder
        if key and key.strip() and key.strip() not in ("YOUR_GROQ_API_KEY_HERE", "YOUR_GROK_API_KEY_HERE"):
            try:
                self._client = OpenAI(
                    api_key=key.strip(),
                    base_url="https://api.groq.com/openai/v1",
                )
                self._configured = True
                print(f"[Groq] AI client initialized (model: {getattr(config, 'GROQ_MODEL', 'llama-3.3-70b-versatile')})")
            except Exception as e:
                print(f"[Groq] API Initialization Error: {e}")
                self._configured = False
        else:
            print("[Groq] GROQ_API_KEY not set or is placeholder. Running in demo mode.")

    def is_available(self) -> bool:
        return GROK_AVAILABLE and self._configured and self._client is not None

    def generate_all(self, commit_data_text: str, repo_name: str = "") -> dict:
        """Generate all 4 narrative formats. Returns dict keyed by format name."""
        results = {}
        formats = ["release", "standup", "onboarding", "portfolio"]

        if not self.is_available():
            return DEMO_OUTPUTS.copy()

        for i, fmt in enumerate(formats):
            try:
                results[fmt] = self._generate_single(fmt, commit_data_text)
                if i < len(formats) - 1:
                    time.sleep(0.5)  # small delay to be polite to API
            except Exception as e:
                print(f"Error generating {fmt} with Groq: {e}")
                results[fmt] = DEMO_OUTPUTS.get(fmt, f"Error generating {fmt}.")

        return results

    def generate_single(self, fmt: str, commit_data_text: str) -> str:
        """Generate one narrative format."""
        if not self.is_available():
            return DEMO_OUTPUTS.get(fmt, "Demo output not available.")

        try:
            return self._generate_single(fmt, commit_data_text)
        except Exception as e:
            print(f"Error in generate_single ({fmt}): {e}")
            return DEMO_OUTPUTS.get(fmt, f"Error: {str(e)}")

    def _generate_single(self, fmt: str, commit_data_text: str) -> str:
        if not self._client:
            raise ValueError("Groq client not initialized")

        prompt_template = PROMPTS.get(fmt, PROMPTS["release"])
        prompt = prompt_template.format(commit_data=commit_data_text)

        model = getattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile")

        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful technical writing assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=2048,
        )

        if not response or not response.choices:
            return DEMO_OUTPUTS.get(fmt, "AI response unavailable.")

        text = response.choices[0].message.content.strip()

        # Strip any preamble if AI adds conversational filler
        if "---END_COMMIT_DATA---" in text:
            text = text.split("---END_COMMIT_DATA---")[-1].strip()

        return text


# Global singleton instance — loads key from .env automatically via config
grok = GrokClient()
