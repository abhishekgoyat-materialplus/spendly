# Verify skill — Spendly

## Launch

```bash
source venv/bin/activate
lsof -ti :5001 | xargs kill -9 2>/dev/null
python app.py &
sleep 3  # wait for reloader child to come up
curl -s http://127.0.0.1:5001/ -o /dev/null -w "%{http_code}"  # confirm 200
```

## Drive auth flows with curl

```bash
# Register
curl -s -c /tmp/s-cookies.txt -X POST http://127.0.0.1:5001/register \
  -d "name=Test&email=test@example.com&password=secret123" -L \
  | grep -o 'nav-user[^<]*\|Sign out'

# Login (two-step: POST saves cookie, GET / confirms nav)
curl -s -c /tmp/s-cookies.txt -X POST http://127.0.0.1:5001/login \
  -d "email=demo@spendly.com&password=demo123" -o /dev/null
curl -s -b /tmp/s-cookies.txt http://127.0.0.1:5001/ | grep -o 'nav-user[^<]*\|Sign out'

# Logout
curl -s -c /tmp/s-cookies.txt -b /tmp/s-cookies.txt \
  http://127.0.0.1:5001/logout -L | grep -o 'Sign in\|Get started'
```

## Gotchas

- Flask debug mode spawns a reloader child; wait 2-3s before sending requests
- `-L` with POST on 302 converts to GET — correct behavior, but use two-step (POST then GET) when you need to check the nav after login
- `lsof -ti :5001 | xargs kill -9` kills both reloader parent and child
- Demo user: `demo@spendly.com` / `demo123` (seeded in `database/db.py`)

## Teardown

```bash
lsof -ti :5001 | xargs kill -9 2>/dev/null
```
