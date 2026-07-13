import pytest
from werkzeug.security import generate_password_hash
import database.db as db_module
from database.db import init_db, get_db
from app import app as flask_app


SEED_EXPENSES = [
    (450.00,  "Food",          "2026-07-01", "Grocery run"),
    (120.00,  "Transport",     "2026-07-02", "Metro card recharge"),
    (1800.00, "Bills",         "2026-07-03", "Electricity bill"),
    (600.00,  "Health",        "2026-07-05", "Pharmacy"),
    (350.00,  "Entertainment", "2026-07-07", "Movie tickets"),
    (2200.00, "Shopping",      "2026-07-09", "Clothes"),
    (180.00,  "Other",         "2026-07-10", "Miscellaneous"),
    (320.00,  "Food",          "2026-07-10", "Restaurant dinner"),
]


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_spendly.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    init_db()

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Demo User", "demo@spendly.com",
         generate_password_hash("demo123", method="pbkdf2:sha256"),
         "2026-07-01 00:00:00"),
    )
    user_id = cursor.lastrowid
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(user_id, *row) for row in SEED_EXPENSES],
    )
    conn.commit()
    conn.close()

    yield db_path, user_id


@pytest.fixture()
def client(test_db, monkeypatch):
    db_path, _ = test_db
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.test_client() as c:
        yield c
