import os
import re
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
    insert_expense,
    get_expense_by_id,
    update_expense,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-in-production")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _safe_date(val):
    value = (val or "").strip()
    return value if _DATE_RE.match(value) else None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)

    return decorated


with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #


@app.route("/")
def landing():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if len(password) < 8:
            return render_template(
                "register.html", error="Password must be at least 8 characters."
            )

        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            db.close()
            return render_template(
                "register.html", error="An account with that email already exists."
            )

        password_hash = generate_password_hash(password, method="pbkdf2:sha256")
        cursor = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        user_id = cursor.lastrowid
        db.commit()
        db.close()

        session["user_id"] = user_id
        session["user_name"] = name
        return redirect(url_for("profile"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("landing"))
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        db.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid email or password.")

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        next_url = request.form.get("next", "")
        if not next_url.startswith("/"):
            next_url = url_for("profile")
        return redirect(next_url)

    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
@login_required
def profile():
    user_id = session["user_id"]

    date_from = _safe_date(request.args.get("from"))
    date_to = _safe_date(request.args.get("to"))

    user_row = get_user_by_id(user_id)
    words = user_row["name"].split()
    initials = (words[0][0] + (words[-1][0] if len(words) > 1 else "")).upper()
    user = {**user_row, "initials": initials}

    stats = get_summary_stats(user_id, date_from, date_to)
    transactions = get_recent_transactions(user_id, date_from, date_to)
    breakdown = get_category_breakdown(user_id, date_from, date_to)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        breakdown=breakdown,
        date_from=date_from or "",
        date_to=date_to or "",
    )


@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")


VALID_CATEGORIES = {
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
}


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "GET":
        return render_template("add_expense.html")

    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "")
    date_raw = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip() or None

    error = None
    amount = None

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        error = "Amount must be a positive number."

    if not error and category not in VALID_CATEGORIES:
        error = "Please select a valid category."

    if not error:
        if not _DATE_RE.match(date_raw):
            error = "Date must be in YYYY-MM-DD format."
        else:
            try:
                datetime.strptime(date_raw, "%Y-%m-%d")
            except ValueError:
                error = "Date must be in YYYY-MM-DD format."

    if error:
        return render_template(
            "add_expense.html",
            error=error,
            amount=amount_raw,
            category=category,
            date=date_raw,
            description=description or "",
        )

    insert_expense(session["user_id"], amount, category, date_raw, description)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    user_id = session["user_id"]
    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "GET":
        return render_template("edit_expense.html", expense=expense)

    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "")
    date_raw = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip() or None

    error = None
    amount = None

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        error = "Amount must be a positive number."

    if not error and category not in VALID_CATEGORIES:
        error = "Please select a valid category."

    if not error:
        if not _DATE_RE.match(date_raw):
            error = "Date must be in YYYY-MM-DD format."
        else:
            try:
                datetime.strptime(date_raw, "%Y-%m-%d")
            except ValueError:
                error = "Date must be in YYYY-MM-DD format."

    if error:
        return render_template(
            "edit_expense.html",
            error=error,
            expense=expense,
            amount=amount_raw,
            category=category,
            date=date_raw,
            description=description or "",
        )

    update_expense(id, user_id, amount, category, date_raw, description)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete")
@login_required
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
