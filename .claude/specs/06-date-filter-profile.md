# Spec: Date Filter for Profile Page

## Overview
Add a date-range filter bar to the profile page so users can narrow all
dashboard data — summary stats, recent transactions, and category breakdown —
to a specific period. Preset chips (This Month, Last 3 Months, This Year,
All Time) let users filter in one click; a pair of date inputs supports
custom ranges. The filter is submitted as a GET form so the filtered URL
is bookmarkable and shareable. This is the first interactivity layer on the
profile page and sets the pattern for future filtering features.

## Depends on
- Step 05: Backend routes for profile page (`/profile` route and all three
  query helpers must be working and returning real data).

## Routes
No new routes. The existing `GET /profile` route is extended to accept
optional `from` and `to` query parameters (ISO date strings `YYYY-MM-DD`).

## Database changes
No database changes.

## Templates
- **Modify:** `templates/profile.html`
  - Add a `<form method="get">` filter bar between the profile header and the
    stats grid.
  - The form contains: four preset `<button type="button">` chips and two
    `<input type="date">` fields (`name="from"`, `name="to"`) plus an Apply
    `<button type="submit">`.
  - Pass `date_from` and `date_to` back from the route so the inputs show the
    currently active range.

## Files to change
- `app.py` — read `request.args.get("from")` and `request.args.get("to")`,
  validate they are either empty or match `YYYY-MM-DD`, pass them to all three
  query helpers, and forward them to the template as `date_from` / `date_to`.
- `database/queries.py` — update `get_summary_stats`, `get_recent_transactions`,
  and `get_category_breakdown` to accept optional `date_from=None` and
  `date_to=None` keyword arguments and apply them as parameterised `WHERE`
  conditions. When a date filter is active, `get_recent_transactions` should
  return all matching rows (no `LIMIT`); without a filter it keeps `LIMIT 10`.
- `static/css/style.css` — add styles for `.date-filter`, `.filter-chip`,
  `.filter-chip--active`, `.date-input`, and `.filter-apply-btn`.
- `static/js/main.js` — add logic to compute preset date ranges client-side
  (relative to today) and populate + submit the form when a preset chip is
  clicked. Also mark the correct chip as active on page load by comparing the
  current input values to each preset's expected dates.

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw SQLite via `get_db()` only.
- Parameterised queries only — never interpolate user input into SQL strings
  (the `date_from` / `date_to` values come from query params; always bind them
  as `?` placeholders).
- Use CSS variables — never hardcode hex values in `style.css`.
- All templates extend `base.html`.
- The filter form must use `method="get"` so the URL reflects the active range.
- Date validation in the route: accept only empty strings or strings matching
  the pattern `YYYY-MM-DD` (10 chars, digits and dashes). Silently ignore
  malformed values rather than returning an error page.
- Do not create separate CSS or JS files — append to the existing
  `static/css/style.css` and `static/js/main.js`.

## Definition of done
- [ ] Visiting `/profile` with no query params shows all-time data (unchanged
      from Step 05 baseline).
- [ ] Clicking "This Month" submits the form and the URL updates to
      `?from=YYYY-MM-01&to=YYYY-MM-DD`; stats, transactions, and breakdown
      all reflect only that month's expenses.
- [ ] Clicking "Last 3 Months" filters data to the last 3 months.
- [ ] Clicking "This Year" filters data to January 1 of the current year
      through today.
- [ ] Clicking "All Time" clears the date inputs and shows all data.
- [ ] Typing custom from/to dates and clicking Apply filters data to that range.
- [ ] The active preset chip is visually highlighted (`.filter-chip--active`)
      when its date range matches the current filter.
- [ ] The date inputs are pre-filled with the current `from`/`to` values on
      page load (so the user sees what range is active).
- [ ] When a date range has no matching expenses the stats show `₹0`,
      `0 transactions`, `—` for top category, an empty transaction table, and
      an empty breakdown section — no crash.
- [ ] Malformed `?from=` or `?to=` query params do not crash the app — they
      are silently ignored and the page renders with the unfiltered data.
