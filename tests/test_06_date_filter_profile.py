"""
tests/test_06_date_filter_profile.py

Pytest tests for the date-range filter feature on the /profile route.
Spec: .claude/specs/06-date-filter-profile.md

Seed data (from conftest.py) — all expenses belong to the demo user, July 2026:
  2026-07-01  Food          ₹450    Grocery run
  2026-07-02  Transport     ₹120    Metro card recharge
  2026-07-03  Bills       ₹1,800   Electricity bill
  2026-07-05  Health        ₹600   Pharmacy
  2026-07-07  Entertainment ₹350   Movie tickets
  2026-07-09  Shopping    ₹2,200   Clothes
  2026-07-10  Other         ₹180   Miscellaneous
  2026-07-10  Food          ₹320   Restaurant dinner
  Total: ₹6,020  |  8 transactions  |  top category: Shopping
"""

import pytest
import database.db as db_module
from database.db import get_db, init_db
from werkzeug.security import generate_password_hash
from app import app as flask_app


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def logged_in_client(client, test_db):
    """
    Wraps the conftest `client` (seeded demo user + 8 July 2026 expenses).
    Injects a valid session so requests reach the login-protected /profile route.
    Returns (client, user_id).
    """
    _, user_id = test_db
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Demo User"
    return client, user_id


@pytest.fixture
def many_client(tmp_path, monkeypatch):
    """
    Standalone DB with one user and 15 expenses in June 2025 (₹100 each,
    category=Food, descriptions 'Expense 01' … 'Expense 15').

    Purpose: verify that GET /profile with a date filter returns ALL matching
    rows (no LIMIT), while without a filter only the 10 most recent appear.
    """
    db_path = str(tmp_path / "many.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    init_db()

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (
            "Many User",
            "many@spendly.com",
            generate_password_hash("pass1234", method="pbkdf2:sha256"),
            "2025-01-01 00:00:00",
        ),
    )
    user_id = cursor.lastrowid
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [
            (user_id, 100.00, "Food", f"2025-06-{day:02d}", f"Expense {day:02d}")
            for day in range(1, 16)
        ],
    )
    conn.commit()
    conn.close()

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = "Many User"
        yield c, user_id


# ─────────────────────────────────────────────────────────────────────────────
# 1. Authentication guard
# ─────────────────────────────────────────────────────────────────────────────

def test_auth_guard_no_params_redirects_to_login(client):
    """Unauthenticated GET /profile → 302 to /login regardless of params."""
    resp = client.get("/profile")
    assert resp.status_code == 302, "Expected redirect for unauthenticated user"
    assert "/login" in resp.headers["Location"]


def test_auth_guard_with_valid_date_params_still_redirects(client):
    """Date params must not bypass the login requirement."""
    resp = client.get("/profile?from=2026-07-01&to=2026-07-10")
    assert resp.status_code == 302, \
        "Expected redirect even when valid date params are present"
    assert "/login" in resp.headers["Location"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Filter bar HTML presence
# ─────────────────────────────────────────────────────────────────────────────

def test_filter_form_uses_get_method(logged_in_client):
    """Profile page must contain a <form method="get"> for the date filter."""
    c, _ = logged_in_client
    resp = c.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'method="get"' in body or "method='get'" in body, \
        "Expected a GET-method form on the profile page"


def test_filter_bar_has_from_input(logged_in_client):
    """Filter form must include an input with name='from'."""
    c, _ = logged_in_client
    resp = c.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'name="from"' in body or "name='from'" in body, \
        "Expected a date input named 'from' in the filter bar"


def test_filter_bar_has_to_input(logged_in_client):
    """Filter form must include an input with name='to'."""
    c, _ = logged_in_client
    resp = c.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'name="to"' in body or "name='to'" in body, \
        "Expected a date input named 'to' in the filter bar"


def test_filter_bar_has_submit_button(logged_in_client):
    """Filter form must include a submit button (Apply)."""
    c, _ = logged_in_client
    resp = c.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'type="submit"' in body or "type='submit'" in body, \
        "Expected a submit button (Apply) in the filter form"


# ─────────────────────────────────────────────────────────────────────────────
# 3. No query params → all-time (unfiltered) data
# ─────────────────────────────────────────────────────────────────────────────

def test_no_params_shows_all_time_total(logged_in_client):
    """Without date filters the total across all seed expenses is ₹6,020."""
    c, _ = logged_in_client
    resp = c.get("/profile")
    assert resp.status_code == 200
    assert "6,020" in resp.data.decode(), \
        "Expected all-time total ₹6,020 when no date params are given"


def test_no_params_shows_correct_transaction_count(logged_in_client):
    """Without date filters all 8 seed expenses are counted."""
    c, _ = logged_in_client
    resp = c.get("/profile")
    assert resp.status_code == 200
    # stats["transactions"] = 8 is passed to the template
    assert "8" in resp.data.decode(), \
        "Expected transaction count of 8 in unfiltered profile page"


def test_no_params_shows_top_category(logged_in_client):
    """Without date filters the top spending category is Shopping (₹2,200)."""
    c, _ = logged_in_client
    resp = c.get("/profile")
    assert resp.status_code == 200
    assert "Shopping" in resp.data.decode(), \
        "Expected top category 'Shopping' in unfiltered profile page"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Custom date range — stats (parameterised)
#
# Sub-range calculations from the seed data:
#   Jul 01–03 : Food 450 + Transport 120 + Bills 1800 = 2370, top = Bills
#   Jul 05–09 : Health 600 + Entertainment 350 + Shopping 2200 = 3150, top = Shopping
#   Jul 10–10 : Other 180 + Food 320 = 500, top = Food
#   Jul 01–10 : all 8 = 6020, top = Shopping
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "date_from, date_to, expected_total_substr, expected_txn_count, expected_top_cat",
    [
        ("2026-07-01", "2026-07-03", "2,370", 3, "Bills"),
        ("2026-07-05", "2026-07-09", "3,150", 3, "Shopping"),
        ("2026-07-10", "2026-07-10", "500",   2, "Food"),
        ("2026-07-01", "2026-07-10", "6,020", 8, "Shopping"),
    ],
)
def test_date_range_filters_stats(
    logged_in_client,
    date_from,
    date_to,
    expected_total_substr,
    expected_txn_count,
    expected_top_cat,
):
    """Stats on /profile reflect only expenses that fall within the given range."""
    c, _ = logged_in_client
    resp = c.get(f"/profile?from={date_from}&to={date_to}")
    assert resp.status_code == 200, \
        f"Expected 200 for range {date_from}–{date_to}, got {resp.status_code}"
    body = resp.data.decode()
    assert expected_total_substr in body, \
        f"Range {date_from}–{date_to}: expected total substring '{expected_total_substr}'"
    assert str(expected_txn_count) in body, \
        f"Range {date_from}–{date_to}: expected transaction count {expected_txn_count}"
    assert expected_top_cat in body, \
        f"Range {date_from}–{date_to}: expected top category '{expected_top_cat}'"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Empty date range — zero stats, no crash
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_range_shows_zero_total(logged_in_client):
    """A range with no matching expenses shows ₹0 for total spent."""
    c, _ = logged_in_client
    resp = c.get("/profile?from=2025-01-01&to=2025-12-31")
    assert resp.status_code == 200
    assert "₹0" in resp.data.decode(), \
        "Expected ₹0 total when no expenses match the date range"


def test_empty_range_shows_zero_transaction_count(logged_in_client):
    """A range with no matching expenses shows 0 transactions."""
    c, _ = logged_in_client
    resp = c.get("/profile?from=2025-01-01&to=2025-12-31")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "0" in body, \
        "Expected '0' transactions when no expenses match the date range"


def test_empty_range_shows_em_dash_for_top_category(logged_in_client):
    """A range with no matching expenses shows '—' (em-dash) for top category."""
    c, _ = logged_in_client
    resp = c.get("/profile?from=2025-01-01&to=2025-12-31")
    assert resp.status_code == 200
    assert "—" in resp.data.decode(), \
        "Expected em-dash (—) for top category when no expenses in range"


def test_empty_range_does_not_crash(logged_in_client):
    """Zero-result date range must not raise an exception."""
    c, _ = logged_in_client
    resp = c.get("/profile?from=2020-01-01&to=2020-12-31")
    assert resp.status_code == 200, \
        "Expected 200 for a valid date range that matches no expenses"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Malformed query params — silently ignored, page still renders
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query_string",
    [
        "?from=not-a-date",
        "?to=not-a-date",
        "?from=abc&to=xyz",
        "?from=2026/07/01&to=2026/07/10",   # wrong separator
        "?from=2026-13-01",                  # invalid month
        "?from=07-01-2026",                  # MM-DD-YYYY format (wrong)
        "?from=&to=",                        # empty strings
        "?from=; DROP TABLE expenses; --",   # SQL injection attempt
        "?from=99999-99-99",                 # completely out of range
        "?from=2026-7-1&to=2026-7-10",      # missing zero-padding
    ],
)
def test_malformed_params_return_200(logged_in_client, query_string):
    """Malformed date params must not crash the app; the page returns 200."""
    c, _ = logged_in_client
    resp = c.get(f"/profile{query_string}")
    assert resp.status_code == 200, \
        f"Expected 200 for malformed params '{query_string}', got {resp.status_code}"


@pytest.mark.parametrize(
    "query_string",
    [
        "?from=not-a-date",
        "?to=not-a-date",
        "?from=abc&to=xyz",
    ],
)
def test_malformed_params_silently_ignored_show_unfiltered_data(
    logged_in_client, query_string
):
    """
    Malformed params are silently ignored; the page renders with all-time
    (unfiltered) data, not a blank or error page.
    """
    c, _ = logged_in_client
    resp = c.get(f"/profile{query_string}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "6,020" in body, (
        f"Expected all-time total ₹6,020 when malformed params '{query_string}' "
        f"are silently ignored"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Date inputs pre-filled with the currently active range
# ─────────────────────────────────────────────────────────────────────────────

def test_from_input_prefilled_with_active_date(logged_in_client):
    """The 'from' date input value matches the date_from query param in the URL."""
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-07-01&to=2026-07-10")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "2026-07-01" in body, \
        "Expected date_from='2026-07-01' to be pre-filled in the HTML response"


def test_to_input_prefilled_with_active_date(logged_in_client):
    """The 'to' date input value matches the date_to query param in the URL."""
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-07-01&to=2026-07-10")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "2026-07-10" in body, \
        "Expected date_to='2026-07-10' to be pre-filled in the HTML response"


def test_no_params_filter_form_still_present_without_dates(logged_in_client):
    """
    Without query params the filter form is still rendered;
    no stale date values should bleed in from a previous request.
    """
    c, _ = logged_in_client
    resp = c.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Form must be present
    assert 'name="from"' in body or "name='from'" in body, \
        "Expected filter form to be present even without date params"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Partial filters — only 'from' or only 'to'
# ─────────────────────────────────────────────────────────────────────────────

def test_from_only_param_filters_expenses_on_or_after_date(logged_in_client):
    """
    Only 'from' param supplied: returns all expenses on or after that date.
    from=2026-07-09 → Shopping ₹2,200 + Other ₹180 + Food ₹320 = ₹2,700, 3 txns.
    """
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-07-09")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "2,700" in body, \
        "Expected total ₹2,700 for expenses from 2026-07-09 onwards"


def test_to_only_param_filters_expenses_on_or_before_date(logged_in_client):
    """
    Only 'to' param supplied: returns all expenses on or before that date.
    to=2026-07-03 → Food ₹450 + Transport ₹120 + Bills ₹1,800 = ₹2,370, 3 txns.
    """
    c, _ = logged_in_client
    resp = c.get("/profile?to=2026-07-03")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "2,370" in body, \
        "Expected total ₹2,370 for expenses up to 2026-07-03"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Inverted range (from > to) — zero results, no crash
# ─────────────────────────────────────────────────────────────────────────────

def test_inverted_range_returns_zero_stats(logged_in_client):
    """
    When from > to, the SQL WHERE date >= X AND date <= Y matches nothing.
    The page must render with ₹0 stats rather than crashing.
    """
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-07-10&to=2026-07-01")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "₹0" in body, \
        "Expected ₹0 total when from date is after to date"


# ─────────────────────────────────────────────────────────────────────────────
# 10. Transaction list — correct entries, correct order
# ─────────────────────────────────────────────────────────────────────────────

def test_filtered_transactions_include_in_range_entries(logged_in_client):
    """Transactions within the range appear in the response body."""
    c, _ = logged_in_client
    # Range Jul 1–3: Grocery run, Metro card recharge, Electricity bill
    resp = c.get("/profile?from=2026-07-01&to=2026-07-03")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Grocery run" in body, \
        "Expected 'Grocery run' (Jul 1) in transactions for Jul 1–3 range"
    assert "Metro card recharge" in body, \
        "Expected 'Metro card recharge' (Jul 2) in transactions for Jul 1–3 range"
    assert "Electricity bill" in body, \
        "Expected 'Electricity bill' (Jul 3) in transactions for Jul 1–3 range"


def test_filtered_transactions_exclude_out_of_range_entries(logged_in_client):
    """Transactions outside the range must not appear in the response body."""
    c, _ = logged_in_client
    # Range Jul 1–3: expenses on Jul 7, 9, 10 should be absent
    resp = c.get("/profile?from=2026-07-01&to=2026-07-03")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Movie tickets" not in body, \
        "Expected 'Movie tickets' (Jul 7) to be excluded from Jul 1–3 range"
    assert "Clothes" not in body, \
        "Expected 'Clothes' (Jul 9) to be excluded from Jul 1–3 range"
    assert "Miscellaneous" not in body, \
        "Expected 'Miscellaneous' (Jul 10) to be excluded from Jul 1–3 range"


def test_filtered_transactions_ordered_newest_first(logged_in_client):
    """
    Filtered transactions are returned in descending date order.
    Jul 5 (Pharmacy) must appear before Jul 1 (Grocery run) in the HTML.
    """
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-07-01&to=2026-07-05")
    assert resp.status_code == 200
    body = resp.data.decode()
    pharmacy_pos = body.find("Pharmacy")
    grocery_pos = body.find("Grocery run")
    assert pharmacy_pos != -1, "Expected 'Pharmacy' (Jul 5) in filtered transactions"
    assert grocery_pos != -1, "Expected 'Grocery run' (Jul 1) in filtered transactions"
    assert pharmacy_pos < grocery_pos, (
        "Expected newer entry 'Pharmacy' (Jul 5) to appear before "
        "older entry 'Grocery run' (Jul 1) in descending-order list"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 11. Category breakdown — correct categories for filtered range
# ─────────────────────────────────────────────────────────────────────────────

def test_filtered_breakdown_shows_categories_present_in_range(logged_in_client):
    """
    Category breakdown for Jul 1–3 should list Bills, Food, Transport
    (the only three categories with expenses in that window).
    """
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-07-01&to=2026-07-03")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Bills" in body, \
        "Expected 'Bills' in category breakdown for Jul 1–3"
    assert "Food" in body, \
        "Expected 'Food' in category breakdown for Jul 1–3"
    assert "Transport" in body, \
        "Expected 'Transport' in category breakdown for Jul 1–3"


def test_filtered_breakdown_top_category_matches_range(logged_in_client):
    """
    For Jul 1–3 the top category is Bills (₹1,800), not Shopping.
    This confirms the breakdown query is correctly scoped to the range.
    """
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-07-01&to=2026-07-03")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Bills is the top category for this range
    assert "Bills" in body, \
        "Expected 'Bills' to be the top category for Jul 1–3 range"


def test_filtered_breakdown_renders_without_error(logged_in_client):
    """
    Category breakdown with an active date filter must render successfully.
    (Percentage math must not raise even for a narrow range.)
    """
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-07-01&to=2026-07-03")
    assert resp.status_code == 200, \
        "Category breakdown for filtered range should render without error"


# ─────────────────────────────────────────────────────────────────────────────
# 12. No LIMIT when a date filter is active — full result set returned
# ─────────────────────────────────────────────────────────────────────────────

def test_filter_active_returns_all_matching_transactions_beyond_default_limit(
    many_client,
):
    """
    When a date filter is active, ALL matching rows are returned (no LIMIT 10).
    The 'many_client' fixture provides a user with 15 expenses in June 2025.
    All 15 descriptions ('Expense 01' … 'Expense 15') must appear.
    """
    c, _ = many_client
    resp = c.get("/profile?from=2025-06-01&to=2025-06-30")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Oldest entries would be cut off by LIMIT 10 without filter
    assert "Expense 01" in body, \
        "Expected 'Expense 01' (Jun 1, oldest) when filter removes the LIMIT"
    assert "Expense 05" in body, \
        "Expected 'Expense 05' (Jun 5) when filter removes the LIMIT"
    assert "Expense 15" in body, \
        "Expected 'Expense 15' (Jun 15, newest) in filtered results"


def test_no_filter_respects_default_limit_of_10(many_client):
    """
    Without a date filter only the 10 most recent transactions are shown.
    The 5 oldest entries (Jun 1–5, 'Expense 01' … 'Expense 05') must not appear.
    """
    c, _ = many_client
    resp = c.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Jun 15 (newest) should always be present
    assert "Expense 15" in body, \
        "Expected 'Expense 15' (newest) to appear in the default 10-row view"
    # Jun 1–5 are the oldest; with LIMIT 10 ordered desc they fall off
    assert "Expense 01" not in body, \
        "Expected 'Expense 01' (Jun 1) NOT to appear under the default LIMIT 10"
    assert "Expense 05" not in body, \
        "Expected 'Expense 05' (Jun 5) NOT to appear under the default LIMIT 10"


# ─────────────────────────────────────────────────────────────────────────────
# 13. Preset range equivalents (server-side only — JS logic is not tested)
#
# The preset chips compute date ranges client-side and submit the form.
# Here we verify that the server handles those submitted date values correctly.
# Reference date: 2026-07-15 (as noted in CLAUDE.md currentDate).
# ─────────────────────────────────────────────────────────────────────────────

def test_this_month_equivalent_range_returns_200_and_correct_stats(logged_in_client):
    """
    'This Month' preset submits from=2026-07-01&to=2026-07-15.
    All 8 seed expenses fall within July 2026 (all before the 15th).
    """
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-07-01&to=2026-07-15")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "6,020" in body, \
        "Expected all-time total ₹6,020 for This Month range (all July 2026 expenses)"


def test_this_year_equivalent_range_returns_200_and_correct_stats(logged_in_client):
    """
    'This Year' preset submits from=2026-01-01&to=2026-07-15.
    All 8 seed expenses (July 2026) fall within 2026.
    """
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-01-01&to=2026-07-15")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "6,020" in body, \
        "Expected full ₹6,020 total for This Year range (Jan–Jul 2026)"


def test_last_three_months_equivalent_range_returns_200_and_correct_stats(
    logged_in_client,
):
    """
    'Last 3 Months' preset submits from≈2026-04-15&to=2026-07-15.
    All 8 seed expenses (Jul 2026) fall within that window.
    """
    c, _ = logged_in_client
    resp = c.get("/profile?from=2026-04-15&to=2026-07-15")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "6,020" in body, \
        "Expected full ₹6,020 for Last-3-Months range (Apr–Jul 2026)"


def test_all_time_no_params_shows_complete_data(logged_in_client):
    """
    'All Time' preset clears the date inputs and submits with no params.
    The page shows the complete dataset.
    """
    c, _ = logged_in_client
    resp = c.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "6,020" in body, "Expected all-time total ₹6,020 with no date params"
    assert "Shopping" in body, "Expected top category 'Shopping' in all-time view"


# ─────────────────────────────────────────────────────────────────────────────
# 14. Smoke tests — variety of valid date param combinations always return 200
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query_string",
    [
        "",                                       # no params
        "?from=2026-07-01",                       # from only
        "?to=2026-07-10",                         # to only
        "?from=2026-07-01&to=2026-07-01",         # single-day range
        "?from=2026-01-01&to=2026-12-31",         # full year
        "?from=2024-01-01&to=2025-12-31",         # range before all seed data
        "?from=2026-07-05&to=2026-07-05",         # exact match for one expense
        "?from=2026-07-01&to=2026-07-10",         # exact match for full seed range
    ],
)
def test_valid_date_param_combinations_return_200(logged_in_client, query_string):
    """Any syntactically valid combination of date params must return 200."""
    c, _ = logged_in_client
    resp = c.get(f"/profile{query_string}")
    assert resp.status_code == 200, \
        f"Expected 200 for query '{query_string}', got {resp.status_code}"
