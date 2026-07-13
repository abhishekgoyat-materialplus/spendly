import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-in-production")


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
            return render_template("register.html", error="Password must be at least 8 characters.")

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            db.close()
            return render_template("register.html", error="An account with that email already exists.")

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
    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "July 2026",
    }
    stats = {
        "total_spent": "₹6,020",
        "transactions": 8,
        "top_category": "Shopping",
    }
    transactions = [
        {"date": "Jul 10", "description": "Clothes",             "category": "Shopping",      "amount": "₹2,200"},
        {"date": "Jul 03", "description": "Electricity bill",    "category": "Bills",         "amount": "₹1,800"},
        {"date": "Jul 05", "description": "Pharmacy",            "category": "Health",        "amount": "₹600"},
        {"date": "Jul 01", "description": "Grocery run",         "category": "Food",          "amount": "₹450"},
        {"date": "Jul 09", "description": "Restaurant dinner",   "category": "Food",          "amount": "₹320"},
        {"date": "Jul 07", "description": "Movie tickets",       "category": "Entertainment", "amount": "₹350"},
        {"date": "Jul 10", "description": "Miscellaneous",       "category": "Other",         "amount": "₹180"},
        {"date": "Jul 02", "description": "Metro card recharge", "category": "Transport",     "amount": "₹120"},
    ]
    breakdown = [
        {"category": "Shopping",      "amount": "₹2,200", "pct": 37},
        {"category": "Bills",         "amount": "₹1,800", "pct": 30},
        {"category": "Food",          "amount": "₹770",   "pct": 13},
        {"category": "Health",        "amount": "₹600",   "pct": 10},
        {"category": "Entertainment", "amount": "₹350",   "pct": 6},
        {"category": "Other",         "amount": "₹180",   "pct": 3},
        {"category": "Transport",     "amount": "₹120",   "pct": 2},
    ]
    return render_template("profile.html", user=user, stats=stats,
                           transactions=transactions, breakdown=breakdown)


@app.route("/expenses/add")
@login_required
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
@login_required
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
@login_required
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
