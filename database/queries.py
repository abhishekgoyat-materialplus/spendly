from datetime import datetime
from database.db import get_db


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


def get_summary_stats(user_id):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT amount, category FROM expenses WHERE user_id = ?", (user_id,)
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


def get_recent_transactions(user_id, limit=10):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT date, description, category, amount FROM expenses"
            " WHERE user_id = ? ORDER BY date DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        db.close()

    result = []
    for r in rows:
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        result.append({
            "date": f"{dt.strftime('%b')} {dt.day}",
            "description": r["description"],
            "category": r["category"],
            "amount": f"₹{r['amount']:,.0f}",
        })
    return result


def get_category_breakdown(user_id):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT category, SUM(amount) AS total FROM expenses"
            " WHERE user_id = ? GROUP BY category ORDER BY total DESC",
            (user_id,),
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
