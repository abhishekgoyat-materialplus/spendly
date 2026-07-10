# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate virtual environment (always required first)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the dev server (port 5001, debug mode)
python app.py

# Run tests
pytest

# Run a single test file
pytest tests/test_foo.py
```

## Architecture

**Spendly** is a Flask-based personal expense tracker. The stack is intentionally minimal: no frontend framework, no npm, vanilla JS only.

- `app.py` — single file containing the Flask app and all route definitions
- `database/db.py` — SQLite helpers (`get_db`, `init_db`, `seed_db`); currently a stub pending implementation
- `templates/base.html` — Jinja2 base template; all pages extend it
- `static/css/style.css` — single merged stylesheet (do not create separate CSS files)
- `static/js/main.js` — single vanilla JS file (no libraries)

**Route structure:** Public landing/auth routes are implemented; expense CRUD routes (`/logout`, `/profile`, `/expenses/...`) are placeholder stubs awaiting implementation.

**Database:** SQLite via the `database/db.py` helpers. Foreign keys and `row_factory` should be enabled in `get_db()`. Tables are created with `CREATE TABLE IF NOT EXISTS` in `init_db()`.
