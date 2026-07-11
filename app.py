"""
app.py — Flask Application Factory
Registers all page blueprints, initializes DB, and sets up Jinja2 template path.
"""

import os
from flask import Flask, jsonify
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import database
import config


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "components"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
        static_url_path="/static",
    )

    # ── Config ──────────────────────────────────────────────────────────────
    app.secret_key = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_FILE_SIZE_BYTES
    CSRFProtect(app)
    # ── Jinja globals ────────────────────────────────────────────────────────
    app.jinja_env.globals.update(
        APP_NAME=config.APP_NAME,
        APP_TAGLINE=config.APP_TAGLINE,
        NARRATIVE_FORMATS=config.NARRATIVE_FORMATS,
        ENABLE_HISTORY=config.ENABLE_HISTORY,
    )

    # ── Database ─────────────────────────────────────────────────────────────
    database.init_db()

    # ── Register Blueprints ──────────────────────────────────────────────────
    from pages.home import home_bp
    from pages.analyze import analyze_bp
    from pages.history import history_bp
    from pages.detail import detail_bp
    from pages.about import about_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(analyze_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(detail_bp)
    app.register_blueprint(about_bp)

    # ── Error Handlers ───────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template_string
        return render_template_string(ERROR_404_HTML, APP_NAME=config.APP_NAME), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template_string
        return render_template_string(ERROR_500_HTML, APP_NAME=config.APP_NAME, error=str(e)), 500

    return app


ERROR_404_HTML = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>404 — {{ APP_NAME }}</title>
<style>body{background:#0f0f1a;color:#e2e8f0;font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
h1{font-size:4rem;color:#7c3aed}p{color:#94a3b8}a{color:#a78bfa;text-decoration:none}</style></head>
<body><div><h1>404</h1><p>This page doesn't exist.</p><a href="/">← Back to home</a></div></body></html>
"""

ERROR_500_HTML = """
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>500 — {{ APP_NAME }}</title>
<style>body{background:#0f0f1a;color:#e2e8f0;font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
h1{font-size:4rem;color:#dc2626}p{color:#94a3b8;max-width:600px}a{color:#a78bfa;text-decoration:none}code{background:#1e1e2e;padding:4px 8px;border-radius:4px;font-size:.85rem}</style></head>
<body><div><h1>500</h1><p>Something went wrong.<br><code>{{ error }}</code></p><a href="/">← Back to home</a></div></body></html>
"""


if __name__ == "__main__":
    app = create_app()
    # DEBUG reads from FLASK_DEBUG env var via config.py — never hardcoded
    app.run(debug=config.DEBUG, host="0.0.0.0", port=5000)
