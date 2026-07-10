# Spec: Login and Logout

## Overview

Step 02 wired up the `/login` and `/logout` routes and the `login.html` template, but the authentication layer is incomplete: no routes are guarded, already-logged-in users can still reach the auth pages, and there is no mechanism to redirect back to a protected page after login. This step hardens the auth layer by adding a `login_required` decorator, redirecting authenticated users away from `/login` and `/register`, and supporting a `?next=` parameter so users land on the right page after signing in.

## Depends on

- Step 01 — Database Setup (`users` table, `get_db`)
- Step 02 — Registration (session management, `login.html`, nav)

## Routes

- `GET /login` — if already logged in, redirect to `url_for("landing")` — public
- `GET /register` — if already logged in, redirect to `url_for("landing")` — public
- `GET /logout` — no change to logic; already clears session and redirects — logged-in

No new routes are added. The existing stubs (`/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`) must be decorated with `@login_required` so they redirect unauthenticated users to `/login?next=<path>`.

## Database changes

No database changes.

## Templates

- **Modify:** `templates/login.html` — update the form action to preserve the `next` parameter: `action="{{ url_for('login', next=request.args.get('next', '')) }}"`. Add a hidden input `<input type="hidden" name="next" value="{{ request.args.get('next', '') }}">` so the `next` value survives the POST.

## Files to change

- `app.py` — add `login_required` decorator; update `GET /login` and `GET /register` to redirect logged-in users; update `POST /login` to honour `next`; apply `@login_required` to all protected stubs
- `templates/login.html` — preserve `next` through the form POST

## Files to create

None.

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- The `login_required` decorator must be defined in `app.py` using `functools.wraps` so Flask's routing stays intact
- `next` values must be validated: only allow relative paths (paths starting with `/`) — never redirect to an absolute URL or external host
- When `next` is absent or invalid, fall back to `url_for("landing")`
- The decorator redirects to `url_for("login", next=request.path)` for unauthenticated requests
- Do not change the session structure — keep `user_id` and `user_name` only
- Do not add CSRF protection at this stage (`GET /logout` remains acceptable)

## Definition of done

- [ ] Visiting `/login` while logged in redirects immediately to `/` without showing the login form
- [ ] Visiting `/register` while logged in redirects immediately to `/` without showing the registration form
- [ ] Visiting `/profile` while not logged in redirects to `/login?next=/profile`
- [ ] After logging in from `/login?next=/profile`, the user lands on `/profile` (the stub page), not `/`
- [ ] Visiting `/expenses/add` while not logged in redirects to `/login?next=/expenses/add`
- [ ] After logging in from the redirect, the user lands on the correct stub page
- [ ] `GET /logout` still clears the session and redirects to `/`
- [ ] A `next` value pointing to an external URL (e.g. `next=https://evil.com`) is ignored and falls back to `/`
- [ ] App starts without errors after all changes
