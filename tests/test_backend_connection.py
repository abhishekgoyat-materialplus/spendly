import database.db as db_module
from database.db import get_db, init_db
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)
from werkzeug.security import generate_password_hash


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _make_empty_user(tmp_path, monkeypatch):
    """Create a fresh DB with one user who has no expenses; return user_id."""
    db_path = str(tmp_path / "empty.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    init_db()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("New User", "new@example.com",
         generate_password_hash("pass1234", method="pbkdf2:sha256"), "2026-01-15 10:00:00"),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


# ------------------------------------------------------------------ #
# get_user_by_id                                                      #
# ------------------------------------------------------------------ #

def test_get_user_by_id_found(test_db):
    _, user_id = test_db
    result = get_user_by_id(user_id)
    assert result is not None
    assert result["name"] == "Demo User"
    assert result["email"] == "demo@spendly.com"
    assert result["member_since"] == "July 2026"


def test_get_user_by_id_not_found(test_db):
    result = get_user_by_id(99999)
    assert result is None


# ------------------------------------------------------------------ #
# get_summary_stats                                                   #
# ------------------------------------------------------------------ #

def test_summary_stats_with_expenses(test_db):
    _, user_id = test_db
    stats = get_summary_stats(user_id)
    assert stats["total_spent"] == "₹6,020"
    assert stats["transactions"] == 8
    assert stats["top_category"] == "Shopping"


def test_summary_stats_no_expenses(tmp_path, monkeypatch):
    user_id = _make_empty_user(tmp_path, monkeypatch)
    stats = get_summary_stats(user_id)
    assert stats == {"total_spent": "₹0", "transactions": 0, "top_category": "—"}


# ------------------------------------------------------------------ #
# get_recent_transactions                                             #
# ------------------------------------------------------------------ #

def test_recent_transactions_ordered(test_db):
    _, user_id = test_db
    txns = get_recent_transactions(user_id)
    assert len(txns) == 8
    # Newest dates first — both Jul 10 entries come before Jul 9, Jul 7, etc.
    dates_raw = [t["date"] for t in txns]
    assert dates_raw[0].startswith("Jul")
    # Each item has required keys
    for t in txns:
        assert {"date", "description", "category", "amount"} <= t.keys()
    # First item (newest) should be one of the Jul 10 entries
    assert txns[0]["date"] == "Jul 10"
    # Last item should be the Jul 1 entry
    assert txns[-1]["date"] == "Jul 1"


def test_recent_transactions_empty(tmp_path, monkeypatch):
    user_id = _make_empty_user(tmp_path, monkeypatch)
    assert get_recent_transactions(user_id) == []


# ------------------------------------------------------------------ #
# get_category_breakdown                                              #
# ------------------------------------------------------------------ #

def test_category_breakdown_pct_sum(test_db):
    _, user_id = test_db
    breakdown = get_category_breakdown(user_id)
    assert len(breakdown) == 7
    # All items have required keys
    for item in breakdown:
        assert {"category", "amount", "pct"} <= item.keys()
    # pct values must sum to exactly 100
    assert sum(item["pct"] for item in breakdown) == 100
    # Sorted descending by amount — Shopping is first
    assert breakdown[0]["category"] == "Shopping"


def test_category_breakdown_empty(tmp_path, monkeypatch):
    user_id = _make_empty_user(tmp_path, monkeypatch)
    assert get_category_breakdown(user_id) == []


# ------------------------------------------------------------------ #
# Route tests                                                         #
# ------------------------------------------------------------------ #

def test_profile_unauthenticated(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_profile_authenticated(client, test_db):
    _, user_id = test_db
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Demo User"
    resp = client.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "₹" in body


def test_profile_zero_expenses(client, tmp_path, monkeypatch):
    user_id = _make_empty_user(tmp_path, monkeypatch)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "New User"
    resp = client.get("/profile")
    assert resp.status_code == 200
