from datetime import datetime
from database.db import get_db


def _date_conditions(date_from, date_to):
    date_conds, date_params = [], []
    if date_from:
        date_conds.append("date >= ?")
        date_params.append(date_from)
    if date_to:
        date_conds.append("date <= ?")
        date_params.append(date_to)
    return date_conds, date_params


def get_user_by_id(user_id):
    db = get_db()
    try:
        row = db.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        dt = datetime.strptime(row["created_at"][:10], "%Y-%m-%d")
        return {
            "name": row["name"],
            "email": row["email"],
            "member_since": dt.strftime("%B %Y"),
        }
    finally:
        db.close()


def get_summary_stats(user_id, date_from=None, date_to=None):
    db = get_db()
    try:
        date_conds, date_params = _date_conditions(date_from, date_to)
        where = " AND ".join(["user_id = ?"] + date_conds)
        rows = db.execute(
            "SELECT amount, category FROM expenses WHERE " + where,
            [user_id] + date_params,
        ).fetchall()
    finally:
        db.close()

    if not rows:
        return {"total_spent": "₹0", "transactions": 0, "top_category": "—"}

    total = sum(r["amount"] for r in rows)
    cat_totals = {}
    for r in rows:
        cat_totals[r["category"]] = cat_totals.get(r["category"], 0) + r["amount"]
    top_category = max(cat_totals, key=cat_totals.get)

    return {
        "total_spent": f"₹{total:,.0f}",
        "transactions": len(rows),
        "top_category": top_category,
    }


def get_recent_transactions(user_id, date_from=None, date_to=None, limit=10):
    db = get_db()
    try:
        date_conds, date_params = _date_conditions(date_from, date_to)
        where = " AND ".join(["user_id = ?"] + date_conds)
        base = "SELECT id, date, description, category, amount FROM expenses WHERE "
        if date_from or date_to:
            # Date range active — return all matching rows, no cap
            sql = base + where + " ORDER BY date DESC"
            params = [user_id] + date_params
        else:
            sql = base + where + " ORDER BY date DESC LIMIT ?"
            params = [user_id] + date_params + [limit]
        rows = db.execute(sql, params).fetchall()
    finally:
        db.close()

    result = []
    for r in rows:
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        result.append(
            {
                "id": r["id"],
                "date": f"{dt.strftime('%b')} {dt.day}",
                "description": r["description"],
                "category": r["category"],
                "amount": f"₹{r['amount']:,.0f}",
            }
        )
    return result


def get_category_breakdown(user_id, date_from=None, date_to=None):
    db = get_db()
    try:
        date_conds, date_params = _date_conditions(date_from, date_to)
        where = " AND ".join(["user_id = ?"] + date_conds)
        rows = db.execute(
            "SELECT category, SUM(amount) AS total FROM expenses WHERE "
            + where
            + " GROUP BY category ORDER BY total DESC",
            [user_id] + date_params,
        ).fetchall()
    finally:
        db.close()

    if not rows:
        return []

    grand_total = sum(r["total"] for r in rows)
    items = [
        {
            "category": r["category"],
            "amount": f"₹{r['total']:,.0f}",
            "pct": round(r["total"] / grand_total * 100),
        }
        for r in rows
    ]

    # Adjust largest category so pct values sum exactly to 100
    remainder = 100 - sum(item["pct"] for item in items)
    items[0]["pct"] += remainder

    return items


def get_expense_by_id(expense_id, user_id):
    db = get_db()
    try:
        row = db.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def update_expense(expense_id, user_id, amount, category, date, description):
    db = get_db()
    try:
        db.execute(
            "UPDATE expenses SET amount=?, category=?, date=?, description=? "
            "WHERE id=? AND user_id=?",
            (amount, category, date, description, expense_id, user_id),
        )
        db.commit()
    finally:
        db.close()


def insert_expense(user_id, amount, category, date, description):
    db = get_db()
    try:
        db.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        db.commit()
    finally:
        db.close()
