import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "spendly.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            email        TEXT    UNIQUE NOT NULL,
            password_hash TEXT   NOT NULL,
            created_at   TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count > 0:
        conn.close()
        return

    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123", method="pbkdf2:sha256")),
    )
    user_id = cursor.lastrowid

    expenses = [
        (user_id, 450.00,  "Food",          "2026-07-01", "Grocery run"),
        (user_id, 120.00,  "Transport",     "2026-07-02", "Metro card recharge"),
        (user_id, 1800.00, "Bills",         "2026-07-03", "Electricity bill"),
        (user_id, 600.00,  "Health",        "2026-07-05", "Pharmacy"),
        (user_id, 350.00,  "Entertainment", "2026-07-07", "Movie tickets"),
        (user_id, 2200.00, "Shopping",      "2026-07-09", "Clothes"),
        (user_id, 180.00,  "Other",         "2026-07-10", "Miscellaneous"),
        (user_id, 320.00,  "Food",          "2026-07-10", "Restaurant dinner"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        expenses,
    )
    conn.commit()
    conn.close()
