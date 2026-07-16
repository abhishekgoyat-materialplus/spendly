"""
tests/test_08-edit-expense.py

Pytest tests for the Edit Expense feature (Step 08).
Spec: .claude/specs/08-edit-expense.md

Coverage:
- Unit tests for get_expense_by_id() DB helper (direct calls, no HTTP)
- Unit tests for update_expense() DB helper (direct calls, no HTTP)
- GET /expenses/<id>/edit auth guard (unauthenticated → 302 to /login)
- GET /expenses/<id>/edit authenticated, own expense (200, form pre-filled,
  correct category pre-selected, all 7 categories present)
- GET /expenses/<id>/edit authenticated, other user's expense (404)
- GET /expenses/<id>/edit authenticated, non-existent id (404)
- POST /expenses/<id>/edit auth guard (unauthenticated → 302 to /login)
- POST /expenses/<id>/edit happy path (valid data → 302 to /profile, DB updated)
- POST /expenses/<id>/edit other user's expense (404)
- POST /expenses/<id>/edit validation errors: missing amount, zero amount,
  non-numeric amount, invalid category, invalid date string
- POST /expenses/<id>/edit no description (redirect, description=NULL in DB)
- Form re-population: submitted values survive a validation error re-render
- Profile page: Edit links per transaction row use the correct expense id
"""

import pytest
from werkzeug.security import generate_password_hash

from database.db import get_db
from database.queries import get_expense_by_id, update_expense


# ---------------------------------------------------------------------------
# Additional fixtures
# (test_db and client are inherited from tests/conftest.py)
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_client(client, test_db):
    """
    Logged-in test client for the primary demo user.
    Injects a valid session without going through the login form.
    Returns (client, user_id).
    """
    _, user_id = test_db
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Demo User"
    return client, user_id


@pytest.fixture()
def seed_expense(test_db):
    """
    Fetches and returns (as a plain dict) the first seed expense for the
    primary user — amount=450.0, category='Food', date='2026-07-01',
    description='Grocery run'.

    Depends on test_db to ensure DB_PATH is monkeypatched before the query.
    """
    _, user_id = test_db
    conn = get_db()
    row = conn.execute(
        "SELECT id, amount, category, date, description "
        "FROM expenses WHERE user_id = ? ORDER BY id ASC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row)


@pytest.fixture()
def other_user_expense(test_db):
    """
    Inserts a second user with one expense into the test DB.
    Returns (other_user_id, other_expense_id).

    Depends explicitly on test_db so that DB_PATH is already monkeypatched
    when the INSERT statements execute.
    """
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (
            "Other User",
            "other@spendly.com",
            generate_password_hash("otherpass123", method="pbkdf2:sha256"),
            "2026-01-01 00:00:00",
        ),
    )
    other_user_id = cursor.lastrowid
    cursor2 = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (other_user_id, 25.0, "Food", "2026-06-01", "Other user lunch"),
    )
    other_expense_id = cursor2.lastrowid
    conn.commit()
    conn.close()
    return other_user_id, other_expense_id


# ---------------------------------------------------------------------------
# Unit tests — get_expense_by_id() DB helper
# ---------------------------------------------------------------------------


class TestGetExpenseByIdHelper:
    """
    Unit tests for get_expense_by_id(expense_id, user_id) in database/queries.py.
    All calls are direct (no HTTP); the HTTP layer is tested separately.
    """

    def test_valid_id_correct_user_returns_matching_row(self, test_db, seed_expense):
        """
        Spec: get_expense_by_id with a valid expense_id and the correct user_id
        must return a dict-like object whose fields match the stored expense.
        """
        _, user_id = test_db
        expense_id = seed_expense["id"]

        result = get_expense_by_id(expense_id, user_id)

        assert (
            result is not None
        ), f"Expected a row for expense_id={expense_id}, user_id={user_id}, got None"
        assert (
            result["id"] == expense_id
        ), f"Row id mismatch: expected {expense_id}, got {result['id']}"
        assert (
            result["user_id"] == user_id
        ), f"Row user_id mismatch: expected {user_id}, got {result['user_id']}"
        assert (
            result["amount"] == seed_expense["amount"]
        ), f"Row amount mismatch: expected {seed_expense['amount']}, got {result['amount']}"
        assert (
            result["category"] == seed_expense["category"]
        ), f"Row category mismatch: expected {seed_expense['category']!r}, got {result['category']!r}"
        assert (
            result["date"] == seed_expense["date"]
        ), f"Row date mismatch: expected {seed_expense['date']!r}, got {result['date']!r}"
        assert result["description"] == seed_expense["description"], (
            f"Row description mismatch: expected {seed_expense['description']!r}, "
            f"got {result['description']!r}"
        )

    def test_valid_id_wrong_user_returns_none(
        self, test_db, seed_expense, other_user_expense
    ):
        """
        Spec: get_expense_by_id with a valid expense_id but the wrong user_id
        (ownership mismatch) must return None — not the row belonging to another user.
        """
        _, primary_user_id = test_db
        other_user_id, _ = other_user_expense
        expense_id = seed_expense["id"]

        result = get_expense_by_id(expense_id, other_user_id)

        assert result is None, (
            f"Expected None when user_id={other_user_id} queries expense_id={expense_id} "
            f"that belongs to user_id={primary_user_id}; got {result!r}"
        )

    def test_nonexistent_id_returns_none(self, test_db):
        """
        Spec: get_expense_by_id with an expense_id that does not exist in the DB
        must return None regardless of user_id.
        """
        _, user_id = test_db
        nonexistent_id = 999999

        result = get_expense_by_id(nonexistent_id, user_id)

        assert (
            result is None
        ), f"Expected None for non-existent expense_id={nonexistent_id}, got {result!r}"


# ---------------------------------------------------------------------------
# Unit tests — update_expense() DB helper
# ---------------------------------------------------------------------------


class TestUpdateExpenseHelper:
    """
    Unit tests for update_expense(expense_id, user_id, amount, category, date, description).
    Each test calls the helper directly, then re-reads the DB to confirm the side effect.
    """

    def test_correct_user_updates_amount_in_db(self, test_db, seed_expense):
        """
        Spec: update_expense with the correct user_id must persist the new amount=99.0
        to the DB.  After the call, querying the row must reflect the updated amount.
        """
        _, user_id = test_db
        expense_id = seed_expense["id"]

        update_expense(
            expense_id,
            user_id,
            amount=99.0,
            category=seed_expense["category"],
            date=seed_expense["date"],
            description=seed_expense["description"],
        )

        conn = get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        conn.close()

        assert row is not None, "Expected expense row to still exist after update"
        assert (
            row["amount"] == 99.0
        ), f"Expected amount=99.0 after update, got {row['amount']}"

    def test_wrong_user_row_unchanged_no_error_raised(
        self, test_db, seed_expense, other_user_expense
    ):
        """
        Spec: update_expense with the wrong user_id must silently leave the DB row
        unchanged (0 rows affected) and must not raise any exception.
        The WHERE id = ? AND user_id = ? clause enforces ownership.
        """
        _, primary_user_id = test_db
        other_user_id, _ = other_user_expense
        expense_id = seed_expense["id"]
        original_amount = seed_expense["amount"]

        # Must not raise — silently does nothing
        update_expense(
            expense_id,
            other_user_id,
            amount=999.0,
            category="Transport",
            date="2026-01-01",
            description="attempted override",
        )

        conn = get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, primary_user_id),
        ).fetchone()
        conn.close()

        assert row is not None, "Expected original expense row to still exist"
        assert row["amount"] == original_amount, (
            f"Expected amount to remain {original_amount} after wrong-user update, "
            f"got {row['amount']}"
        )


# ---------------------------------------------------------------------------
# GET /expenses/<id>/edit — auth guard
# ---------------------------------------------------------------------------


class TestGetEditExpenseAuthGuard:
    """
    Spec: Unauthenticated GET /expenses/<id>/edit must redirect to /login (302).
    """

    def test_unauthenticated_get_redirects_to_login(self, client, seed_expense):
        """
        Spec: GET /expenses/<id>/edit while logged out → 302 redirect to /login.
        """
        expense_id = seed_expense["id"]
        resp = client.get(f"/expenses/{expense_id}/edit")

        assert resp.status_code == 302, (
            f"Expected 302 for unauthenticated GET /expenses/{expense_id}/edit, "
            f"got {resp.status_code}"
        )
        assert "/login" in resp.headers.get(
            "Location", ""
        ), "Expected Location header to contain '/login' for unauthenticated GET"


# ---------------------------------------------------------------------------
# GET /expenses/<id>/edit — authenticated, own expense
# ---------------------------------------------------------------------------


class TestGetEditExpenseAuthenticated:
    """
    Spec: GET /expenses/<id>/edit while logged in for the user's own expense
    renders the edit form (200) with the current expense values pre-populated
    and the correct category pre-selected.
    """

    def test_own_expense_returns_200(self, auth_client, seed_expense):
        """
        Spec: authenticated GET /expenses/<id>/edit returns HTTP 200.
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")

        assert resp.status_code == 200, (
            f"Expected 200 for authenticated GET /expenses/{seed_expense['id']}/edit, "
            f"got {resp.status_code}"
        )

    def test_form_contains_amount_input(self, auth_client, seed_expense):
        """
        Spec: The edit form must include an amount input field (name='amount').
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode()

        assert (
            'name="amount"' in body or "name='amount'" in body
        ), "Expected an input with name='amount' in the edit expense form"

    def test_form_contains_category_select(self, auth_client, seed_expense):
        """
        Spec: The edit form must include a category <select> (name='category').
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode()

        assert (
            'name="category"' in body or "name='category'" in body
        ), "Expected a select/input with name='category' in the edit expense form"

    def test_form_contains_date_input(self, auth_client, seed_expense):
        """
        Spec: The edit form must include a date input (name='date').
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode()

        assert (
            'name="date"' in body or "name='date'" in body
        ), "Expected an input with name='date' in the edit expense form"

    def test_form_contains_description_input(self, auth_client, seed_expense):
        """
        Spec: The edit form must include an optional description input (name='description').
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode()

        assert (
            'name="description"' in body or "name='description'" in body
        ), "Expected an input with name='description' in the edit expense form"

    def test_form_prepopulated_with_current_amount(self, auth_client, seed_expense):
        """
        Spec: The form must be pre-filled with the expense's current amount.
        The seed expense has amount=450.0; '450' must appear in the response.
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode()

        assert (
            "450" in body
        ), "Expected the seed expense amount '450' to appear pre-filled in the form body"

    def test_form_prepopulated_with_current_date(self, auth_client, seed_expense):
        """
        Spec: The form must be pre-filled with the expense's current date.
        The seed expense date is '2026-07-01'.
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode()

        assert seed_expense["date"] in body, (
            f"Expected the seed expense date '{seed_expense['date']}' to appear "
            "pre-filled in the form body"
        )

    def test_form_prepopulated_with_current_description(
        self, auth_client, seed_expense
    ):
        """
        Spec: The form must be pre-filled with the expense's current description.
        The seed expense description is 'Grocery run'.
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode()

        assert seed_expense["description"] in body, (
            f"Expected the seed expense description '{seed_expense['description']}' "
            "to appear pre-filled in the form body"
        )

    def test_form_correct_category_preselected(self, auth_client, seed_expense):
        """
        Spec: The category <select> must have the expense's current category
        pre-selected (selected attribute on the matching <option>).
        The seed expense category is 'Food'.
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode()

        assert (
            seed_expense["category"] in body
        ), f"Expected category '{seed_expense['category']}' to appear in the edit form"
        assert (
            "selected" in body.lower()
        ), "Expected a 'selected' attribute in the category <select> element"

    def test_form_action_points_to_edit_route(self, auth_client, seed_expense):
        """
        Spec: Form action must be /expenses/<id>/edit (POST target for this expense).
        """
        c, _ = auth_client
        expense_id = seed_expense["id"]
        resp = c.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode()

        assert (
            f"/expenses/{expense_id}/edit" in body
        ), f"Expected form action to include '/expenses/{expense_id}/edit'"

    def test_form_uses_post_method(self, auth_client, seed_expense):
        """
        Spec: The edit form must use method='POST' to submit changes.
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode().lower()

        assert (
            'method="post"' in body or "method='post'" in body
        ), "Expected the edit form to declare method='post'"

    def test_form_renders_save_changes_button(self, auth_client, seed_expense):
        """
        Spec: The form must include a 'Save Changes' submit button.
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode()

        assert (
            "Save Changes" in body
        ), "Expected 'Save Changes' submit button text in the edit-expense form"

    @pytest.mark.parametrize(
        "category",
        ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"],
    )
    def test_all_seven_categories_present_in_form(
        self, auth_client, seed_expense, category
    ):
        """
        Spec: The category <select> must contain all 7 fixed options:
        Food, Transport, Bills, Health, Entertainment, Shopping, Other.
        Each option is tested individually for clearer failure messages.
        """
        c, _ = auth_client
        resp = c.get(f"/expenses/{seed_expense['id']}/edit")
        body = resp.data.decode()

        assert (
            category in body
        ), f"Expected category option '{category}' to be present in the edit form"


# ---------------------------------------------------------------------------
# GET /expenses/<id>/edit — 404 cases
# ---------------------------------------------------------------------------


class TestGetEditExpense404:
    """
    Spec: GET /expenses/<id>/edit must return 404 when the expense does not
    exist or belongs to a different user.
    """

    def test_other_users_expense_returns_404(self, auth_client, other_user_expense):
        """
        Spec: authenticated GET /expenses/<id>/edit where the expense belongs to
        a different user must return 404 — not 200 or 403.
        """
        c, _ = auth_client
        _, other_expense_id = other_user_expense
        resp = c.get(f"/expenses/{other_expense_id}/edit")

        assert resp.status_code == 404, (
            f"Expected 404 when primary user accesses another user's expense "
            f"(expense_id={other_expense_id}), got {resp.status_code}"
        )

    def test_nonexistent_id_returns_404(self, auth_client):
        """
        Spec: authenticated GET /expenses/<id>/edit with a non-existent expense id
        must return 404.
        """
        c, _ = auth_client
        resp = c.get("/expenses/999999/edit")

        assert (
            resp.status_code == 404
        ), f"Expected 404 for non-existent expense_id=999999, got {resp.status_code}"


# ---------------------------------------------------------------------------
# POST /expenses/<id>/edit — auth guard
# ---------------------------------------------------------------------------


class TestPostEditExpenseAuthGuard:
    """
    Spec: Unauthenticated POST /expenses/<id>/edit must redirect to /login (302).
    """

    def test_unauthenticated_post_redirects_to_login(self, client, seed_expense):
        """
        Spec: POST /expenses/<id>/edit while logged out → 302 redirect to /login,
        regardless of the form data submitted.
        """
        expense_id = seed_expense["id"]
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "100.00",
                "category": "Food",
                "date": "2026-07-15",
                "description": "updated",
            },
        )

        assert resp.status_code == 302, (
            f"Expected 302 for unauthenticated POST /expenses/{expense_id}/edit, "
            f"got {resp.status_code}"
        )
        assert "/login" in resp.headers.get(
            "Location", ""
        ), "Expected Location header to contain '/login' for unauthenticated POST"


# ---------------------------------------------------------------------------
# POST /expenses/<id>/edit — happy path
# ---------------------------------------------------------------------------


class TestPostEditExpenseHappyPath:
    """
    Spec: A valid POST to /expenses/<id>/edit must update the DB row and
    redirect to /profile (302).  The form must not be re-rendered on success.
    """

    def test_valid_data_redirects_to_profile(self, auth_client, seed_expense):
        """
        Spec: After a successful update, redirect to url_for('profile') → 302.
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={
                "amount": "99.99",
                "category": "Transport",
                "date": "2026-08-01",
                "description": "Updated description",
            },
        )

        assert (
            resp.status_code == 302
        ), f"Expected 302 redirect after valid edit submission, got {resp.status_code}"
        assert "/profile" in resp.headers.get(
            "Location", ""
        ), "Expected redirect to /profile after successful expense update"

    def test_valid_data_updates_all_fields_in_db(self, auth_client, seed_expense):
        """
        Spec: After a valid POST the expense row in the DB must reflect the newly
        submitted values for amount, category, date, and description.
        """
        c, user_id = auth_client
        expense_id = seed_expense["id"]

        c.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "123.45",
                "category": "Bills",
                "date": "2026-09-10",
                "description": "New description after edit",
            },
        )

        conn = get_db()
        row = conn.execute(
            "SELECT amount, category, date, description "
            "FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        conn.close()

        assert row is not None, "Expected expense row to still exist in DB after edit"
        assert (
            row["amount"] == 123.45
        ), f"Expected amount=123.45 after edit, got {row['amount']}"
        assert (
            row["category"] == "Bills"
        ), f"Expected category='Bills' after edit, got {row['category']!r}"
        assert (
            row["date"] == "2026-09-10"
        ), f"Expected date='2026-09-10' after edit, got {row['date']!r}"
        assert (
            row["description"] == "New description after edit"
        ), f"Expected updated description in DB, got {row['description']!r}"

    def test_does_not_rerender_form_on_success(self, auth_client, seed_expense):
        """
        Spec: After a successful update, do NOT render the form again —
        the response must be a redirect (not 200 with the form HTML).
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={
                "amount": "50.00",
                "category": "Health",
                "date": "2026-07-20",
                "description": "Checkup",
            },
        )

        assert resp.status_code != 200, (
            "Expected a redirect (not 200) after successful expense edit; "
            "the form must not be re-rendered on success"
        )

    def test_other_users_expense_post_returns_404(
        self, auth_client, other_user_expense
    ):
        """
        Spec: POST /expenses/<id>/edit where the expense belongs to a different
        user must return 404 — ownership is enforced on POST as well as GET.
        """
        c, _ = auth_client
        _, other_expense_id = other_user_expense
        resp = c.post(
            f"/expenses/{other_expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": "2026-07-15",
                "description": "Attempted override",
            },
        )

        assert resp.status_code == 404, (
            f"Expected 404 when primary user POSTs to another user's expense "
            f"(expense_id={other_expense_id}), got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# POST /expenses/<id>/edit — validation errors
# ---------------------------------------------------------------------------

# Valid baseline data used in every validation test (one field is overridden per test)
_VALID_EDIT_DATA = {
    "amount": "50.00",
    "category": "Food",
    "date": "2026-07-15",
    "description": "Valid description",
}


class TestPostEditExpenseValidation:
    """
    Spec: When any field fails validation the route must re-render the edit form
    (200) with an error message — no redirect, no DB update.
    Validation rules are identical to the add-expense route.
    """

    # ── Amount errors ─────────────────────────────────────────────────────────

    def test_missing_amount_returns_200(self, auth_client, seed_expense):
        """
        Spec: POST with amount='' (missing / empty string) must re-render
        the form with HTTP 200.
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={**_VALID_EDIT_DATA, "amount": ""},
        )

        assert (
            resp.status_code == 200
        ), f"Expected 200 re-render for missing amount, got {resp.status_code}"

    def test_missing_amount_shows_error_message(self, auth_client, seed_expense):
        """
        Spec: POST with missing amount must display an error message in the
        re-rendered form.
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={**_VALID_EDIT_DATA, "amount": ""},
        )
        body = resp.data.decode()

        assert (
            "Amount must be a positive number." in body or "positive" in body.lower()
        ), "Expected an error message about positive amount when amount is missing"

    def test_amount_zero_returns_200(self, auth_client, seed_expense):
        """
        Spec: amount must be > 0; submitting amount='0' must re-render the form
        with HTTP 200 (validation error, not a redirect).
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={**_VALID_EDIT_DATA, "amount": "0"},
        )

        assert (
            resp.status_code == 200
        ), f"Expected 200 for amount=0 (not > 0), got {resp.status_code}"

    def test_amount_zero_shows_error_message(self, auth_client, seed_expense):
        """
        Spec: amount=0 must display an error message in the re-rendered form.
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={**_VALID_EDIT_DATA, "amount": "0"},
        )
        body = resp.data.decode()

        assert (
            "Amount must be a positive number." in body or "positive" in body.lower()
        ), "Expected error message about positive amount when amount=0 is submitted"

    def test_nonnumeric_amount_returns_200(self, auth_client, seed_expense):
        """
        Spec: amount is parsed with float(); a non-numeric string like 'abc'
        must cause a 200 re-render (ValueError caught by the route).
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={**_VALID_EDIT_DATA, "amount": "abc"},
        )

        assert (
            resp.status_code == 200
        ), f"Expected 200 for non-numeric amount 'abc', got {resp.status_code}"

    def test_nonnumeric_amount_shows_error_message(self, auth_client, seed_expense):
        """
        Spec: A non-numeric amount must show an error message in the
        re-rendered form.
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={**_VALID_EDIT_DATA, "amount": "abc"},
        )
        body = resp.data.decode()

        assert (
            "Amount must be a positive number." in body or "positive" in body.lower()
        ), "Expected error message about positive/numeric amount for 'abc'"

    # ── Category error ────────────────────────────────────────────────────────

    def test_invalid_category_returns_200(self, auth_client, seed_expense):
        """
        Spec: category must be one of the 7 fixed options; a value outside
        the set (e.g., 'Fuel') must cause a 200 re-render.
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={**_VALID_EDIT_DATA, "category": "Fuel"},
        )

        assert (
            resp.status_code == 200
        ), f"Expected 200 for invalid category 'Fuel', got {resp.status_code}"

    def test_invalid_category_shows_error_message(self, auth_client, seed_expense):
        """
        Spec: An invalid category must display an error message in the
        re-rendered form.
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={**_VALID_EDIT_DATA, "category": "Fuel"},
        )
        body = resp.data.decode()

        assert (
            "Please select a valid category." in body or "valid" in body.lower()
        ), "Expected error message about valid category for 'Fuel'"

    # ── Date error ────────────────────────────────────────────────────────────

    def test_invalid_date_string_returns_200(self, auth_client, seed_expense):
        """
        Spec: date must be a valid YYYY-MM-DD string; submitting 'not-a-date'
        must cause a 200 re-render.
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={**_VALID_EDIT_DATA, "date": "not-a-date"},
        )

        assert (
            resp.status_code == 200
        ), f"Expected 200 for invalid date 'not-a-date', got {resp.status_code}"

    def test_invalid_date_string_shows_error_message(self, auth_client, seed_expense):
        """
        Spec: An invalid date string must display an error message in the
        re-rendered form.
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={**_VALID_EDIT_DATA, "date": "not-a-date"},
        )
        body = resp.data.decode()

        assert (
            "Date must be in YYYY-MM-DD format." in body or "date" in body.lower()
        ), "Expected error message about date format for 'not-a-date'"

    # ── DB unchanged on any validation failure (parametrised) ────────────────

    @pytest.mark.parametrize(
        "overrides, label",
        [
            ({"amount": ""}, "empty amount"),
            ({"amount": "0"}, "zero amount"),
            ({"amount": "0.00"}, "zero decimal amount"),
            ({"amount": "-5"}, "negative amount"),
            ({"amount": "abc"}, "non-numeric amount"),
            ({"category": "Fuel"}, "invalid category"),
            ({"category": ""}, "empty category"),
            ({"date": ""}, "empty date"),
            ({"date": "not-a-date"}, "invalid date string"),
            ({"date": "2026/07/15"}, "slash-separated date"),
        ],
    )
    def test_validation_failure_leaves_db_row_unchanged(
        self, auth_client, seed_expense, overrides, label
    ):
        """
        Spec: A validation error must not write any changes to the DB.
        After a failed POST the expense row must retain its original amount.
        """
        c, user_id = auth_client
        expense_id = seed_expense["id"]
        original_amount = seed_expense["amount"]

        c.post(f"/expenses/{expense_id}/edit", data={**_VALID_EDIT_DATA, **overrides})

        conn = get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        conn.close()

        assert (
            row is not None
        ), f"[{label}] Expected expense row to still exist after failed update"
        assert row["amount"] == original_amount, (
            f"[{label}] Expected amount to remain {original_amount} after validation "
            f"failure, got {row['amount']}"
        )


# ---------------------------------------------------------------------------
# POST /expenses/<id>/edit — optional description handling
# ---------------------------------------------------------------------------


class TestPostEditExpenseOptionalDescription:
    """
    Spec: description is optional; strip whitespace; store None if blank.
    Submitting without a description must succeed (redirect to /profile)
    and the DB row must have description = NULL.
    """

    def test_blank_description_redirects_to_profile(self, auth_client, seed_expense):
        """
        Spec: An empty string description must not trigger a validation error;
        the response must redirect to /profile (302).
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": "2026-07-15",
                "description": "",
            },
        )

        assert (
            resp.status_code == 302
        ), f"Expected 302 redirect for blank description, got {resp.status_code}"
        assert "/profile" in resp.headers.get(
            "Location", ""
        ), "Expected redirect to /profile when description is blank"

    def test_blank_description_stores_null_in_db(self, auth_client, seed_expense):
        """
        Spec: A blank description must be stored as NULL (Python None) in the DB,
        not as an empty string.
        """
        c, user_id = auth_client
        expense_id = seed_expense["id"]

        c.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": "2026-07-15",
                "description": "",
            },
        )

        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        conn.close()

        assert (
            row is not None
        ), "Expected expense row to exist after edit with blank description"
        assert (
            row["description"] is None
        ), f"Expected NULL for blank description, got: {row['description']!r}"

    def test_whitespace_only_description_stores_null_in_db(
        self, auth_client, seed_expense
    ):
        """
        Spec: description is stripped; a whitespace-only string must also be
        stored as NULL (not as the whitespace string itself).
        """
        c, user_id = auth_client
        expense_id = seed_expense["id"]

        c.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": "2026-07-15",
                "description": "   ",  # whitespace only
            },
        )

        conn = get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        conn.close()

        assert (
            row is not None
        ), "Expected expense row to exist after edit with whitespace description"
        assert (
            row["description"] is None
        ), f"Expected NULL for whitespace-only description, got: {row['description']!r}"

    def test_absent_description_field_redirects_to_profile(
        self, auth_client, seed_expense
    ):
        """
        Spec: Omitting the description key from the POST body entirely must
        succeed and redirect to /profile (no validation error for absent optional field).
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": "2026-07-15",
                # 'description' key intentionally omitted
            },
        )

        assert (
            resp.status_code == 302
        ), f"Expected 302 redirect when description field is absent, got {resp.status_code}"
        assert "/profile" in resp.headers.get(
            "Location", ""
        ), "Expected redirect to /profile when description field is absent from POST"


# ---------------------------------------------------------------------------
# POST /expenses/<id>/edit — form re-population on validation error
# ---------------------------------------------------------------------------


class TestEditFormRepopulationOnError:
    """
    Spec: On any validation error, re-render the form with the submitted
    (not original) values pre-filled, so the user does not lose their input.
    """

    def test_submitted_amount_appears_in_rerendered_form(
        self, auth_client, seed_expense
    ):
        """
        Spec: The submitted amount must appear in the re-rendered form after
        a validation error on another field (here: invalid category).
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={
                "amount": "77.77",
                "category": "INVALID_CATEGORY",  # triggers validation error
                "date": "2026-08-01",
                "description": "test",
            },
        )
        assert resp.status_code == 200
        body = resp.data.decode()

        assert "77.77" in body, (
            "Expected submitted amount '77.77' to appear in re-rendered form after "
            "validation error"
        )

    def test_submitted_date_appears_in_rerendered_form(self, auth_client, seed_expense):
        """
        Spec: The submitted date must appear in the re-rendered form after
        a validation error on another field (here: non-numeric amount).
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={
                "amount": "not-a-number",  # triggers validation error
                "category": "Food",
                "date": "2026-11-25",
                "description": "test",
            },
        )
        assert resp.status_code == 200
        body = resp.data.decode()

        assert "2026-11-25" in body, (
            "Expected submitted date '2026-11-25' to appear in re-rendered form after "
            "validation error"
        )

    def test_submitted_description_appears_in_rerendered_form(
        self, auth_client, seed_expense
    ):
        """
        Spec: The submitted description must appear in the re-rendered form after
        a validation error on another field (here: non-numeric amount).
        """
        c, _ = auth_client
        resp = c.post(
            f"/expenses/{seed_expense['id']}/edit",
            data={
                "amount": "not-a-number",  # triggers validation error
                "category": "Food",
                "date": "2026-08-01",
                "description": "My edited description",
            },
        )
        assert resp.status_code == 200
        body = resp.data.decode()

        assert "My edited description" in body, (
            "Expected submitted description 'My edited description' to appear in "
            "re-rendered form after validation error"
        )


# ---------------------------------------------------------------------------
# Profile page — Edit links per transaction row
# ---------------------------------------------------------------------------


class TestProfileEditLinks:
    """
    Spec: templates/profile.html must include an 'Edit' link per transaction row
    pointing to /expenses/<id>/edit, where <id> is that row's expense id.
    This requires get_recent_transactions to return the 'id' column.
    """

    def test_profile_page_contains_edit_links(self, auth_client):
        """
        Spec: The profile transactions table must include Edit action links.
        Verifies both the link text and the URL pattern are present.
        """
        c, _ = auth_client
        resp = c.get("/profile")
        assert resp.status_code == 200
        body = resp.data.decode()

        assert (
            "Edit" in body
        ), "Expected 'Edit' link text to be present on the profile page"
        assert (
            "/expenses/" in body and "/edit" in body
        ), "Expected at least one '/expenses/<id>/edit' URL on the profile page"

    def test_profile_edit_link_uses_correct_expense_id(self, auth_client, seed_expense):
        """
        Spec: The Edit link for each transaction row must reference that expense's
        own id.  Verifies that get_recent_transactions returns 'id' in its SELECT.
        The seed expense (id from seed_expense fixture) must produce a link
        '/expenses/<id>/edit' visible on the profile page.
        """
        c, _ = auth_client
        expense_id = seed_expense["id"]
        resp = c.get("/profile")
        assert resp.status_code == 200
        body = resp.data.decode()

        assert f"/expenses/{expense_id}/edit" in body, (
            f"Expected '/expenses/{expense_id}/edit' link on the profile page for the "
            f"seed expense (id={expense_id})"
        )
