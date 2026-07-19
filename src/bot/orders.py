import sqlite3
from src.database.db import get_conn


def save_order(user_id: int, username: str, full_name: str,
               service: str, details: str, contact: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO orders (user_id, username, full_name, service, details, contact)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, username, full_name, service, details, contact)
    )
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id


def get_orders(status: str = None) -> list:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM orders WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return rows


def update_order_status(order_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()


def register_user(user_id: int, username: str, full_name: str):
    conn = get_conn()
    conn.execute(
        """INSERT OR IGNORE INTO users (user_id, username, full_name)
           VALUES (?, ?, ?)""",
        (user_id, username, full_name)
    )
    conn.commit()
    conn.close()
