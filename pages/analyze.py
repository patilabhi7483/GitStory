"""
pages/analyze.py — Results display page + export endpoint
Routes:
  GET /result/<analysis_id>              → two-panel results view
  GET /export/<id>/<format>/<extension>  → download narrative file
"""

import html
import json
from flask import Blueprint, render_template, abort, send_file, request
import io
import database
import config
from services.commit_classifier import build_contribution_insights, get_type_info
from services.exporter import to_markdown, to_text, get_filename

analyze_bp = Blueprint("analyze", __name__, template_folder="../components")


@analyze_bp.get("/result/<int:analysis_id>")
def result(analysis_id: int):
    analysis = database.get_analysis_by_id(analysis_id)
    if not analysis:
        abort(404)

    # Parse stored JSON
    raw_commits = _safe_json(analysis.get("raw_commits_json", "[]"))
    groups = _safe_json(analysis.get("grouped_commits_json", "[]"))
    active_format = request.args.get("fmt", config.DEFAULT_NARRATIVE_FORMAT)
    allowed_formats = {fmt_key for fmt_key, _ in config.NARRATIVE_FORMATS}
    if active_format not in allowed_formats:
        active_format = config.DEFAULT_NARRATIVE_FORMAT

    # Render markdown to HTML for display
    narratives_html = {}
    for fmt_key, _ in config.NARRATIVE_FORMATS:
        raw = analysis.get(f"narrative_{fmt_key}") or ""
        narratives_html[fmt_key] = _markdown_to_html(raw)

    # Build enriched analysis dict for template
    enriched = dict(analysis)
    for fmt_key, _ in config.NARRATIVE_FORMATS:
        enriched[f"narrative_{fmt_key}"] = narratives_html.get(fmt_key, "")

    # Type info for badges
    type_info_map = {k: get_type_info(k) for k in [
        "feature", "bugfix", "hotfix", "refactor", "docs", "test", "devops", "chore"
    ]}
    insights = build_contribution_insights(raw_commits, groups)

    # Prepare chart data (last 10 weeks)
    chart_data = _prepare_chart_data(groups)

    return render_template(
        "analyze_page.html",
        analysis=enriched,
        groups=groups,
        active_format=active_format,
        type_info=type_info_map,
        insights=insights,
        chart_data=chart_data,
    )


@analyze_bp.get("/export/<int:analysis_id>/<fmt>/<ext>")
def export(analysis_id: int, fmt: str, ext: str):
    analysis = database.get_analysis_by_id(analysis_id)
    if not analysis:
        abort(404)

    allowed_fmts = [k for k, _ in config.NARRATIVE_FORMATS]
    if fmt not in allowed_fmts or ext not in ("md", "txt"):
        abort(400)

    narrative = analysis.get(f"narrative_{fmt}") or ""
    repo_name = analysis.get("repo_name", "repo")
    filename = get_filename(repo_name, fmt, ext)

    if ext == "md":
        data = to_markdown(narrative, repo_name, fmt)
        mime = "text/markdown"
    else:
        data = to_text(narrative, repo_name, fmt)
        mime = "text/plain"

    return send_file(
        io.BytesIO(data),
        mimetype=mime,
        as_attachment=True,
        download_name=filename,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _prepare_chart_data(groups: list[dict]):
    """Prepare data for Chart.js velocity timeline."""
    # Take last 10 groups (weeks) and reverse to chronological
    timeline_groups = [g for g in groups if g.get("week_key") != "undated"][:10]
    timeline_groups.reverse()
    
    labels = [g["label"].replace("Week of ", "") for g in timeline_groups]
    features = [g["type_counts"].get("feature", 0) for g in timeline_groups]
    fixes = [g["type_counts"].get("bugfix", 0) + g["type_counts"].get("hotfix", 0) for g in timeline_groups]
    others = [g["commit_count"] - features[i] - fixes[i] for i, g in enumerate(timeline_groups)]
    
    return {
        "labels": labels,
        "features": features,
        "fixes": fixes,
        "others": others
    }


def _safe_json(text: str):
    try:
        return json.loads(text) if text else []
    except Exception:
        return []


def _markdown_to_html(md_text: str) -> str:
    """Convert markdown to safe HTML for display."""
    if not md_text:
        return ""
    try:
        import re

        text = html.escape(md_text)

        # Headings
        text = re.sub(r'^#{6}\s+(.+)$', r'<h6>\1</h6>', text, flags=re.MULTILINE)
        text = re.sub(r'^#{5}\s+(.+)$', r'<h5>\1</h5>', text, flags=re.MULTILINE)
        text = re.sub(r'^#{4}\s+(.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'^#{3}\s+(.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^#{2}\s+(.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^#{1}\s+(.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)

        # Bold + italic
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

        # Inline code
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

        # Blockquotes
        text = re.sub(r'^>\s*(.+)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)

        # Unordered lists
        def replace_list(m):
            items = re.findall(r'^[-*+]\s+(.+)$', m.group(0), re.MULTILINE)
            return '<ul>' + ''.join(f'<li>{i}</li>' for i in items) + '</ul>'
        text = re.sub(r'(^[-*+]\s+.+$\n?)+', replace_list, text, flags=re.MULTILINE)

        # Tables (basic)
        def replace_table(m):
            rows = [r.strip() for r in m.group(0).strip().split('\n') if r.strip() and not re.match(r'^\|[-:| ]+\|$', r.strip())]
            if not rows:
                return m.group(0)
            html = '<table>'
            for i, row in enumerate(rows):
                cells = [c.strip() for c in row.strip('|').split('|')]
                tag = 'th' if i == 0 else 'td'
                html += '<tr>' + ''.join(f'<{tag}>{c}</{tag}>' for c in cells) + '</tr>'
            html += '</table>'
            return html
        text = re.sub(r'(^\|.+\|$\n?)+', replace_table, text, flags=re.MULTILINE)

        # Horizontal rules
        text = re.sub(r'^---+$', '<hr>', text, flags=re.MULTILINE)

        # Paragraphs (convert double newlines)
        paragraphs = re.split(r'\n\n+', text)
        result = []
        for p in paragraphs:
            p = p.strip()
            if p and not re.match(r'^<(h[1-6]|ul|ol|li|blockquote|table|hr|pre)', p):
                p = f'<p>{p}</p>'
            result.append(p)
        text = '\n'.join(result)

        # Clean up line breaks within paragraphs
        text = re.sub(r'(?<!</p>)\n(?!<)', '<br>', text)

        return text
    except Exception:
        return f'<pre>{html.escape(md_text)}</pre>'
