# Spec: Registration

## Overview

Implement user registration, login, and logout so visitors can create an account and authenticate. This step wires up the form POST handlers that the templates already expect, establishes Flask session management, and updates the nav to reflect the user's logged-in state. All data and security primitives are already in place from Step 01 (the `users` table and `werkzeug` password hashing).

## Depends on

- Step 01 — Database Setup (users table must exist, `get_db` must be working)

## Routes

- `POST /register` — validate form, create user, start session, redirect to `/` — public
- `POST /login` — verify credentials, start session, redirect to `/` — public
- `GET /logout` — clear session, redirect to `/` — logged-in

## Database changes

No database changes. The `users` table from Step 01 is sufficient.

## Templates

- **Modify:** `templates/base.html` — update nav to show user name + Sign out link when `session.user_id` is set; show Sign in / Get started when not

## Files to change

- `app.py` — add imports, set `secret_key`, convert `/register` and `/login` to `GET|POST`, implement `POST` handlers, implement `/logout`
- `templates/base.html` — conditional nav based on session state

## Files to create

None.

## New dependencies

No new dependencies. `werkzeug.security` is already installed.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only — never string-format SQL
- Passwords hashed with `werkzeug.security.generate_password_hash` (method `pbkdf2:sha256`)
- Check passwords with `werkzeug.security.check_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `app.secret_key` must be set via `os.environ.get("SECRET_KEY", "dev-only-change-in-production")`
- Store only `user_id` (int) and `user_name` (str) in the session — never store the password or hash
- Strip and lowercase email before every DB read/write
- Strip name before insert
- On registration: reject passwords shorter than 8 characters; reject duplicate emails with a user-friendly message
- On login: use a single generic error message for both wrong email and wrong password ("Invalid email or password") — do not reveal which field failed
- After successful register or login, redirect to `url_for("landing")`
- After logout, redirect to `url_for("landing")`
- `GET /logout` is acceptable for this stage (no CSRF protection needed yet)

## Definition of done

- [ ] `POST /register` with valid data creates a new user row in `users`, sets `session["user_id"]` and `session["user_name"]`, and redirects to `/`
- [ ] `POST /register` with a duplicate email re-renders `register.html` with an error message; no duplicate row is inserted
- [ ] `POST /register` with a password shorter than 8 characters re-renders `register.html` with an error message
- [ ] `POST /login` with correct credentials sets the session and redirects to `/`
- [ ] `POST /login` with wrong password re-renders `login.html` with the generic error message
- [ ] `POST /login` with an unknown email re-renders `login.html` with the same generic error message
- [ ] `GET /logout` clears the session and redirects to `/`; the nav immediately shows Sign in / Get started again
- [ ] Nav shows user's name and a Sign out link when logged in
- [ ] Nav shows Sign in and Get started when not logged in
- [ ] App starts without errors after all changes
