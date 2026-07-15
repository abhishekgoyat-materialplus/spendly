"""
tests/test_07-add-expense.py

Pytest tests for the Add Expense feature (Step 07).
Spec: .claude/specs/07-add-expense.md

Coverage:
- Unit tests for insert_expense() DB helper (direct calls, no HTTP)
- GET /expenses/add auth guard (unauthenticated → 302 to /login)
- GET /expenses/add authenticated (200, form structure, all 7 categories)
- POST /expenses/add auth guard (unauthenticated → 302 to /login)
- POST /expenses/add happy path (valid data → 302 to /profile, row in DB)
- POST /expenses/add validation errors (amount, category, date)
- POST /expenses/add optional description (blank / whitespace → NULL in DB)
- Form value re-population after validation failure
- Edge cases: SQL injection safety, all valid categories, no row on failure
"""

import pytest
from werkzeug.security import generate_password_hash

import database.db as db_module
from database.db import init_db, get_db
from database.queries import insert_expense
from app import app as flask_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    """
    Isolated temp-file SQLite DB with one test user and no seed expenses.
    Monkeypatches DB_PATH so every get_db() call in this test session uses
    this file rather than the real spendly.db on disk.
    Yields (db_path, user_id).
    """
    db_path = str(tmp_path / "test_add_expense.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    init_db()

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (
            "Test User",
            "testuser@spendly.com",
            generate_password_hash("testpass1", method="pbkdf2:sha256"),
            "2026-01-01 00:00:00",
        ),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    yield db_path, user_id


@pytest.fixture()
def client(test_db, monkeypatch):
    """
    Unauthenticated Flask test client backed by the isolated DB.
    No session is injected — use this to verify auth-guard behaviour.
    """
    db_path, _ = test_db
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.test_client() as c:
        yield c


@pytest.fixture()
def auth_client(client, test_db):
    """
    Flask test client with a valid session injected directly via
    session_transaction(), simulating a logged-in user without going
    through the login form.
    Returns (client, user_id).
    """
    _, user_id = test_db
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Test User"
    return client, user_id


# ---------------------------------------------------------------------------
# Unit tests — insert_expense() DB helper
# ---------------------------------------------------------------------------

class TestInsertExpenseHelper:
    """
    Tests for the insert_expense(user_id, amount, category, date, description)
    function in database/queries.py.  These call the helper directly and then
    query the DB to confirm the result — no HTTP involved.
    """

    def test_insert_expense_stores_all_field_values_correctly(self, test_db):
        """
        Spec (unit table): insert_expense with valid args should insert one row;
        querying the DB returns a row whose fields match every supplied argument.
        """
        _, user_id = test_db

        insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchall()
        conn.close()

        assert len(rows) == 1, \
            f"Expected exactly 1 expense row after insert, got {len(rows)}"
        row = rows[0]
        assert row["user_id"] == user_id, \
            f"user_id mismatch: expected {user_id}, got {row['user_id']}"
        assert row["amount"] == 50.0, \
            f"amount mismatch: expected 50.0, got {row['amount']}"
        assert row["category"] == "Food", \
            f"category mismatch: expected 'Food', got {row['category']}"
        assert row["date"] == "2026-03-20", \
            f"date mismatch: expected '2026-03-20', got {row['date']}"
        assert row["description"] == "Lunch", \
            f"description mismatch: expected 'Lunch', got {row['description']}"

    def test_insert_expense_with_none_description_stores_null(self, test_db):
        """
        Spec (unit table): when description=None is passed, the DB must store
        SQL NULL (Python None), not an empty string.
        """
        _, user_id = test_db

        insert_expense(user_id, 75.0, "Transport", "2026-03-21", None)

        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchone()
        conn.close()

        assert row is not None, "Expected expense row to exist in DB"
        assert row["description"] is None, (
            f"Expected NULL for description=None, got: {row['description']!r}"
        )

    def test_insert_expense_each_call_adds_one_row(self, test_db):
        """
        Spec: each call to insert_expense must add exactly one row.
        Two successive calls must produce two rows for that user.
        """
        _, user_id = test_db

        insert_expense(user_id, 100.0, "Bills", "2026-03-01", "Electricity")
        insert_expense(user_id, 200.0, "Health", "2026-03-02", "Doctor visit")

        conn = get_db()
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()

        assert count == 2, f"Expected 2 rows after two inserts, got {count}"


# ---------------------------------------------------------------------------
# Auth guard — unauthenticated requests must redirect to /login
# ---------------------------------------------------------------------------

class TestAuthGuard:
    """
    Spec: Unauthenticated access to both GET and POST /expenses/add must
    redirect to /login (302).
    """

    def test_get_unauthenticated_redirects_to_login(self, client):
        """
        Spec: GET /expenses/add while logged out → 302 redirect to /login.
        """
        resp = client.get("/expenses/add")
        assert resp.status_code == 302, (
            f"Expected 302 for unauthenticated GET /expenses/add, got {resp.status_code}"
        )
        assert "/login" in resp.headers.get("Location", ""), \
            "Expected Location header to contain '/login' for unauthenticated GET"

    def test_post_unauthenticated_redirects_to_login(self, client):
        """
        Spec: POST /expenses/add while logged out → 302 redirect to /login,
        regardless of form data.
        """
        resp = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 302, (
            f"Expected 302 for unauthenticated POST /expenses/add, got {resp.status_code}"
        )
        assert "/login" in resp.headers.get("Location", ""), \
            "Expected Location header to contain '/login' for unauthenticated POST"


# ---------------------------------------------------------------------------
# GET /expenses/add — authenticated
# ---------------------------------------------------------------------------

class TestGetAddExpenseAuthenticated:
    """
    Spec: GET /expenses/add while logged in renders the add-expense form (200)
    with all required fields and all 7 valid category options.
    """

    def test_get_returns_200(self, auth_client):
        """
        Spec: authenticated GET /expenses/add returns HTTP 200.
        """
        c, _ = auth_client
        resp = c.get("/expenses/add")
        assert resp.status_code == 200, (
            f"Expected 200 for authenticated GET /expenses/add, got {resp.status_code}"
        )

    def test_get_renders_form_element(self, auth_client):
        """
        Spec: The page must contain a <form> element.
        """
        c, _ = auth_client
        resp = c.get("/expenses/add")
        body = resp.data.decode()
        assert "<form" in body.lower(), \
            "Expected a <form> element in the add-expense page"

    def test_get_form_uses_post_method(self, auth_client):
        """
        Spec: The form must use method="POST" to submit expense data.
        """
        c, _ = auth_client
        resp = c.get("/expenses/add")
        body = resp.data.decode().lower()
        assert 'method="post"' in body or "method='post'" in body, \
            "Expected the form to declare method='post'"

    def test_get_form_action_targets_add_expense_route(self, auth_client):
        """
        Spec: The form action must point to /expenses/add.
        """
        c, _ = auth_client
        resp = c.get("/expenses/add")
        body = resp.data.decode()
        assert "/expenses/add" in body, \
            "Expected form action to include '/expenses/add'"

    def test_get_renders_amount_input(self, auth_client):
        """
        Spec: The form includes an amount field (number input, step=0.01, min=0.01, required).
        """
        c, _ = auth_client
        resp = c.get("/expenses/add")
        body = resp.data.decode()
        assert 'name="amount"' in body or "name='amount'" in body, \
            "Expected an input with name='amount' on the add-expense form"

    def test_get_renders_category_select(self, auth_client):
        """
        Spec: The form includes a category <select> element with name='category'.
        """
        c, _ = auth_client
        resp = c.get("/expenses/add")
        body = resp.data.decode()
        assert 'name="category"' in body or "name='category'" in body, \
            "Expected a select/input with name='category' on the add-expense form"

    def test_get_renders_date_input(self, auth_client):
        """
        Spec: The form includes a date input (type=date, required).
        """
        c, _ = auth_client
        resp = c.get("/expenses/add")
        body = resp.data.decode()
        assert 'name="date"' in body or "name='date'" in body, \
            "Expected an input with name='date' on the add-expense form"

    def test_get_renders_description_input(self, auth_client):
        """
        Spec: The form includes an optional description input (max 200 chars).
        """
        c, _ = auth_client
        resp = c.get("/expenses/add")
        body = resp.data.decode()
        assert 'name="description"' in body or "name='description'" in body, \
            "Expected an input with name='description' on the add-expense form"

    def test_get_renders_save_expense_submit_button(self, auth_client):
        """
        Spec: The form must include a submit button labelled 'Save Expense'.
        """
        c, _ = auth_client
        resp = c.get("/expenses/add")
        body = resp.data.decode()
        assert "Save Expense" in body, \
            "Expected 'Save Expense' submit button text on the add-expense page"

    @pytest.mark.parametrize("category", [
        "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"
    ])
    def test_get_renders_each_valid_category_option(self, auth_client, category):
        """
        Spec: The category select must contain exactly the 7 fixed options:
        Food, Transport, Bills, Health, Entertainment, Shopping, Other.
        Each is tested individually to make failures specific.
        """
        c, _ = auth_client
        resp = c.get("/expenses/add")
        body = resp.data.decode()
        assert category in body, (
            f"Expected category option '{category}' to be present in the form, "
            f"but it was not found in the response body"
        )


# ---------------------------------------------------------------------------
# POST /expenses/add — happy path (valid submission)
# ---------------------------------------------------------------------------

class TestPostAddExpenseHappyPath:
    """
    Spec: A POST with valid amount, category, date (and optional description)
    must insert one row and redirect to /profile (302) without re-rendering the form.
    """

    def test_valid_post_returns_302(self, auth_client):
        """
        Spec: After successful insert, redirect to url_for('profile') → 302.
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 302, (
            f"Expected 302 redirect after valid expense submission, got {resp.status_code}"
        )

    def test_valid_post_redirects_to_profile(self, auth_client):
        """
        Spec: The redirect after a successful insert must point to /profile.
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        location = resp.headers.get("Location", "")
        assert "/profile" in location, (
            f"Expected redirect to /profile after valid submit, got Location: {location!r}"
        )

    def test_valid_post_does_not_rerender_the_form(self, auth_client):
        """
        Spec: After successful insert, do NOT render the form again —
        the response must be a redirect, not a 200 with the form HTML.
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "99.00",
            "category": "Shopping",
            "date": "2026-05-01",
            "description": "New shoes",
        })
        assert resp.status_code != 200, (
            "Expected a redirect (not 200) after successful expense insertion; "
            "the form must not be re-rendered on success"
        )

    def test_valid_post_inserts_row_in_db_with_correct_values(self, auth_client, test_db):
        """
        Spec: After a valid POST the expense row must exist in the DB for
        the logged-in user with every field matching the submitted values.
        """
        c, user_id = auth_client

        c.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })

        conn = get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()

        assert row is not None, \
            "Expected an expense row in DB after valid form submission"
        assert row["amount"] == 50.0, \
            f"DB amount mismatch: expected 50.0, got {row['amount']}"
        assert row["category"] == "Food", \
            f"DB category mismatch: expected 'Food', got {row['category']}"
        assert row["date"] == "2026-03-20", \
            f"DB date mismatch: expected '2026-03-20', got {row['date']}"
        assert row["description"] == "Lunch", \
            f"DB description mismatch: expected 'Lunch', got {row['description']}"


# ---------------------------------------------------------------------------
# POST /expenses/add — optional description handling
# ---------------------------------------------------------------------------

class TestPostAddExpenseOptionalDescription:
    """
    Spec: description is optional; strip whitespace; store None if blank.
    Submitting without a description must succeed (redirect to /profile)
    and the DB row must have description = NULL.
    """

    def test_blank_description_redirects_to_profile(self, auth_client):
        """
        Spec: An empty string description must not trigger a validation error;
        the response must redirect to /profile (302).
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-03-20",
            "description": "",
        })
        assert resp.status_code == 302, (
            f"Expected 302 redirect for blank description, got {resp.status_code}"
        )
        assert "/profile" in resp.headers.get("Location", ""), \
            "Expected redirect to /profile when description is blank"

    def test_blank_description_stores_null_in_db(self, auth_client, test_db):
        """
        Spec: A blank description must be stored as NULL (Python None) in the DB,
        not as an empty string.
        """
        c, user_id = auth_client

        c.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Transport",
            "date": "2026-03-20",
            "description": "",
        })

        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchone()
        conn.close()

        assert row is not None, "Expected expense row in DB after submit with blank description"
        assert row["description"] is None, (
            f"Expected NULL for blank description, got: {row['description']!r}"
        )

    def test_whitespace_only_description_stores_null_in_db(self, auth_client, test_db):
        """
        Spec: description is stripped; if the stripped result is empty, store None.
        A whitespace-only string must behave identically to a blank description.
        """
        c, user_id = auth_client

        c.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Other",
            "date": "2026-03-20",
            "description": "   ",   # whitespace only
        })

        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchone()
        conn.close()

        assert row is not None, "Expected expense row in DB"
        assert row["description"] is None, (
            f"Expected NULL for whitespace-only description, got: {row['description']!r}"
        )

    def test_absent_description_field_redirects_to_profile(self, auth_client):
        """
        Spec: description is optional; omitting the field key entirely must
        succeed and redirect to /profile.
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Health",
            "date": "2026-04-01",
            # 'description' key is intentionally omitted
        })
        assert resp.status_code == 302, (
            f"Expected 302 redirect when description field is absent, got {resp.status_code}"
        )
        assert "/profile" in resp.headers.get("Location", ""), \
            "Expected redirect to /profile when description field is absent from POST"


# ---------------------------------------------------------------------------
# POST /expenses/add — validation errors (parametrised matrix)
# ---------------------------------------------------------------------------

_VALID_BASE = {
    "amount": "50.00",
    "category": "Food",
    "date": "2026-03-20",
    "description": "x",
}


@pytest.mark.parametrize("overrides, label", [
    # ── Amount errors ──────────────────────────────────────────────────────
    ({"amount": ""},        "empty amount"),
    ({"amount": "0"},       "zero amount (integer)"),
    ({"amount": "0.00"},    "zero amount (decimal)"),
    ({"amount": "-5"},      "negative amount"),
    ({"amount": "-0.01"},   "negative decimal amount"),
    ({"amount": "abc"},     "non-numeric amount string"),
    ({"amount": "12abc"},   "partially numeric amount string"),
    # ── Category errors ────────────────────────────────────────────────────
    ({"category": "Fuel"},      "category not in fixed list"),
    ({"category": ""},          "empty category"),
    ({"category": "food"},      "lowercase category (case-sensitive rejection)"),
    ({"category": "FOOD"},      "all-caps category (case-sensitive rejection)"),
    ({"category": "Food "},     "category with trailing space"),
    # ── Date errors ────────────────────────────────────────────────────────
    ({"date": ""},              "empty date"),
    ({"date": "not-a-date"},    "arbitrary invalid date string"),
    ({"date": "2026/03/20"},    "slash-separated date (wrong format)"),
    ({"date": "03-20-2026"},    "MM-DD-YYYY date format"),
    ({"date": "20-03-2026"},    "DD-MM-YYYY date format"),
    ({"date": "2026-13-01"},    "month out of range"),
    ({"date": "2026-00-15"},    "month zero"),
    ({"date": "2026-3-20"},     "month without zero-padding"),
])
def test_invalid_input_rerenders_form_with_200(auth_client, overrides, label):
    """
    Spec: Any invalid field value must re-render the add-expense form (200)
    with an error message — no redirect, no DB insert.
    Covers: missing/zero/negative/non-numeric amount; category not in fixed set;
    missing/malformed/out-of-range date.
    """
    c, _ = auth_client
    form_data = {**_VALID_BASE, **overrides}
    resp = c.post("/expenses/add", data=form_data)
    assert resp.status_code == 200, (
        f"[{label}] Expected 200 re-render for invalid input, got {resp.status_code}"
    )


@pytest.mark.parametrize("overrides, label", [
    ({"amount": ""},      "empty amount"),
    ({"amount": "0"},     "zero amount"),
    ({"amount": "abc"},   "non-numeric amount"),
    ({"category": ""},    "empty category"),
    ({"category": "Xyz"}, "invalid category"),
    ({"date": ""},        "empty date"),
    ({"date": "bad"},     "non-date string"),
])
def test_invalid_input_shows_error_message(auth_client, overrides, label):
    """
    Spec: On any validation error, the re-rendered form must contain a visible
    error signal so the user understands what went wrong.
    """
    c, _ = auth_client
    form_data = {**_VALID_BASE, **overrides}
    resp = c.post("/expenses/add", data=form_data)
    assert resp.status_code == 200
    body = resp.data.decode().lower()
    has_error_signal = (
        "error" in body
        or "invalid" in body
        or "required" in body
        or "positive" in body
        or "valid" in body
    )
    assert has_error_signal, (
        f"[{label}] Expected an error message in the re-rendered form body"
    )


@pytest.mark.parametrize("overrides, label", [
    ({"amount": "abc"},    "non-numeric amount"),
    ({"category": "Xyz"},  "invalid category"),
    ({"date": "bad-date"}, "invalid date"),
])
def test_validation_failure_does_not_insert_row(auth_client, test_db, overrides, label):
    """
    Spec: A validation error must not insert any row into the expenses table.
    After a failed POST the expense count for the user must remain zero.
    """
    c, user_id = auth_client
    form_data = {**_VALID_BASE, **overrides}
    c.post("/expenses/add", data=form_data)

    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    conn.close()

    assert count == 0, (
        f"[{label}] Expected 0 DB rows after validation failure, got {count}"
    )


# ---------------------------------------------------------------------------
# POST /expenses/add — form value re-population on validation error
# ---------------------------------------------------------------------------

class TestFormRepopulationOnError:
    """
    Spec: On any validation error, re-render the form with the previously
    submitted values pre-filled so the user does not lose their input.
    """

    def test_submitted_amount_appears_in_rerendered_form(self, auth_client):
        """
        Spec: The submitted amount must be pre-filled in the form after
        a validation error on another field.
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "99.99",
            "category": "INVALID_CATEGORY",
            "date": "2026-03-20",
            "description": "Test expense",
        })
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "99.99" in body, \
            "Expected submitted amount '99.99' to be pre-filled in re-rendered form"

    def test_submitted_date_appears_in_rerendered_form(self, auth_client):
        """
        Spec: The submitted date must be pre-filled in the form after
        a validation error on another field.
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "not-a-number",   # triggers amount error
            "category": "Food",
            "date": "2026-06-15",
            "description": "My lunch",
        })
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "2026-06-15" in body, \
            "Expected submitted date '2026-06-15' to be pre-filled in re-rendered form"

    def test_submitted_description_appears_in_rerendered_form(self, auth_client):
        """
        Spec: The submitted description must be pre-filled in the form after
        a validation error on another field.
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "not-a-number",   # triggers amount error
            "category": "Food",
            "date": "2026-06-15",
            "description": "My lunch",
        })
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "My lunch" in body, \
            "Expected submitted description 'My lunch' to be pre-filled in re-rendered form"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestAddExpenseEdgeCases:

    def test_sql_injection_in_description_stored_verbatim(self, auth_client, test_db):
        """
        Spec: Parameterised queries prevent SQL injection. A description
        containing SQL metacharacters must be stored verbatim without
        modifying or dropping the expenses table.
        """
        c, user_id = auth_client
        malicious = "Lunch'; DROP TABLE expenses; --"

        resp = c.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Food",
            "date": "2026-03-20",
            "description": malicious,
        })

        assert resp.status_code == 302, \
            "Expected redirect even when description contains SQL metacharacters"

        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()

        assert row is not None, (
            "Expected expense row to exist — SQL injection must not have dropped the table"
        )
        assert row["description"] == malicious, \
            "Expected SQL injection string to be stored verbatim, not executed"

    def test_decimal_amount_is_accepted(self, auth_client):
        """
        Spec: amount is parsed with float(); a properly formatted decimal like
        '12.50' must be accepted and produce a 302 redirect.
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "12.50",
            "category": "Bills",
            "date": "2026-04-15",
            "description": "Partial utility bill",
        })
        assert resp.status_code == 302, \
            f"Expected 302 for valid decimal amount '12.50', got {resp.status_code}"
        assert "/profile" in resp.headers.get("Location", "")

    @pytest.mark.parametrize("category", [
        "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"
    ])
    def test_all_seven_valid_categories_produce_redirect(self, auth_client, category):
        """
        Spec: All 7 fixed category values must be accepted without error;
        each must produce a 302 redirect to /profile.
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "10.00",
            "category": category,
            "date": "2026-05-01",
            "description": "Category acceptance test",
        })
        assert resp.status_code == 302, (
            f"Expected 302 for valid category '{category}', got {resp.status_code}"
        )
        assert "/profile" in resp.headers.get("Location", ""), (
            f"Expected redirect to /profile for category '{category}'"
        )

    def test_very_small_positive_amount_is_accepted(self, auth_client):
        """
        Spec: amount must be > 0; a very small positive value like 0.01
        (the step minimum) must be accepted and produce a redirect.
        """
        c, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "0.01",
            "category": "Other",
            "date": "2026-06-01",
            "description": "Smallest valid amount",
        })
        assert resp.status_code == 302, \
            f"Expected 302 for amount=0.01 (minimum positive), got {resp.status_code}"

    def test_profile_page_contains_add_expense_link(self, auth_client):
        """
        Spec: templates/profile.html must include an 'Add Expense' button/link
        pointing to /expenses/add so logged-in users can navigate to the form.
        """
        c, _ = auth_client
        resp = c.get("/profile")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "/expenses/add" in body, \
            "Expected /expenses/add link on the profile page ('Add Expense' button)"
