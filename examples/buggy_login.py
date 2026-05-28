"""Intentionally buggy example file — used to demo the reviewer.

Open a PR that adds or modifies this file and the 4 agents should each
catch their specialty: security flaws, style issues, missing tests,
and logic bugs.
"""
import os
import sqlite3

API_KEY = "sk-prod-9f8e7d6c5b4a3210"  # security: hardcoded secret


def login(username, password):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    # security: SQL injection
    query = f"SELECT id, role FROM users WHERE name='{username}' AND pw='{password}'"
    cur.execute(query)
    row = cur.fetchone()
    if row:
        return {"id": row[0], "role": row[1], "ok": True}
    # logic: connection never closed on failure path
    return None


def is_admin(user):
    # logic: returns True if user is None (NoneType has no 'role' attr -> raises,
    # but the truthiness check below means a missing key silently returns True)
    return user.get("role", "admin") == "admin"


def write_audit_log(path, message):
    # security: path traversal — caller-controlled path joined with no validation
    full = os.path.join("/var/log/app", path)
    with open(full, "a") as f:
        f.write(message + "\n")
