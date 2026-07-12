"""Practice next-question and session endpoints."""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from db import get_db, now_iso
from parsing import as_clean_string
from questions_service import row_to_question, stats_for_question

bp = Blueprint("practice", __name__)


@bp.get("/api/practice/next")
def practice_next():
    mode = request.args.get("mode", "random")
    qtype = as_clean_string(request.args.get("type"))
    try:
        count = max(1, min(100, int(request.args.get("count", "1") or "1")))
    except (ValueError, TypeError):
        count = 1
    filters = []
    params = []
    if qtype:
        filters.append("q.type = ?")
        params.append(qtype)
    where = "WHERE " + " AND ".join(filters) if filters else ""
    having = ""
    order = "ORDER BY RANDOM()"
    if mode == "wrong":
        having = "HAVING incorrect > 0"
        order = "ORDER BY last_practiced_at IS NULL, last_practiced_at ASC, RANDOM()"
    elif mode == "high_error":
        having = "HAVING attempts > 0"
        order = "ORDER BY error_rate DESC, incorrect DESC, RANDOM()"
    sql = f"""
        SELECT
            q.*,
            COUNT(a.id) AS attempts,
            COALESCE(SUM(a.is_correct), 0) AS correct,
            COALESCE(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END), 0) AS incorrect,
            MAX(a.created_at) AS last_practiced_at,
            CASE WHEN COUNT(a.id) = 0 THEN 0
                 ELSE 100.0 * COALESCE(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END), 0) / COUNT(a.id)
            END AS error_rate
        FROM questions q
        LEFT JOIN attempts a ON a.question_id = q.id
        {where}
        GROUP BY q.id
        {having}
        {order}
        LIMIT ?
    """
    params.append(count)
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    if not rows:
        return jsonify({"error": "没有符合条件的题目"}), 404
    items = []
    for row in rows:
        attempts = int(row["attempts"] or 0)
        incorrect = int(row["incorrect"] or 0)
        stats = {
            "attempts": attempts,
            "correct": int(row["correct"] or 0),
            "incorrect": incorrect,
            "errorRate": round((incorrect / attempts) * 100, 1) if attempts else 0,
            "lastPracticedAt": row["last_practiced_at"],
        }
        items.append(row_to_question(row, stats))
    if count == 1 and len(items) == 1:
        return jsonify(items[0])
    return jsonify({"items": items})



def session_row_to_summary(row):
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "total": int(row["total"]),
        "correct": int(row["correct"]),
        "wrong": int(row["wrong"]),
        "accuracy": float(row["accuracy"]),
    }


def session_row_to_full(row):
    try:
        items = json.loads(row["items"]) if row["items"] else []
    except (ValueError, TypeError):
        items = []
    data = session_row_to_summary(row)
    data["items"] = items
    return data


@bp.get("/api/practice/sessions")
def practice_sessions_list():
    with get_db() as db:
        rows = db.execute(
            "SELECT id, created_at, total, correct, wrong, accuracy "
            "FROM practice_sessions ORDER BY created_at DESC"
        ).fetchall()
    return jsonify({"items": [session_row_to_summary(r) for r in rows]})


@bp.get("/api/practice/sessions/<int:sid>")
def practice_sessions_detail(sid):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM practice_sessions WHERE id = ?", (sid,)
        ).fetchone()
    if not row:
        return jsonify({"error": "练习记录不存在"}), 404
    return jsonify(session_row_to_full(row))


@bp.post("/api/practice/sessions")
def practice_sessions_create():
    payload = request.get_json(force=True, silent=True) or {}
    total = payload.get("total")
    correct = payload.get("correct")
    wrong = payload.get("wrong")
    accuracy = payload.get("accuracy")
    items = payload.get("items")

    if not isinstance(total, int) or total < 0:
        return jsonify({"error": "total 必须是非负整数"}), 400
    if not isinstance(correct, int) or correct < 0:
        return jsonify({"error": "correct 必须是非负整数"}), 400
    if not isinstance(wrong, int) or wrong < 0:
        return jsonify({"error": "wrong 必须是非负整数"}), 400
    if not isinstance(accuracy, (int, float)) or accuracy < 0 or accuracy > 1:
        return jsonify({"error": "accuracy 必须是 0-1 之间的数值"}), 400
    if not isinstance(items, list) or not items:
        return jsonify({"error": "items 必须是非空数组"}), 400

    created_at = now_iso()
    items_json = json.dumps(items, ensure_ascii=False)
    with get_db() as db:
        cur = db.execute(
            """
            INSERT INTO practice_sessions(created_at, total, correct, wrong, accuracy, items)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (created_at, total, correct, wrong, float(accuracy), items_json),
        )
        sid = cur.lastrowid
        db.commit()
        row = db.execute("SELECT * FROM practice_sessions WHERE id = ?", (sid,)).fetchone()
    return jsonify(session_row_to_full(row)), 201
