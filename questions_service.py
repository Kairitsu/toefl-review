"""Question row mapping and list/query helpers."""
from __future__ import annotations

import json

from db import now_iso
from parsing import TYPE_LABELS, as_clean_string, json_loads


def question_to_row(question, existing_created_at=None):
    timestamp = now_iso()
    title = question.get("title") or (
        ""
        if question.get("type") in {"build_sentence", "complete_words"}
        else TYPE_LABELS.get(question["type"], "题目")
    )
    return {
        "type": question["type"],
        "title": title,
        "article": question.get("article", ""),
        "prompt": question.get("prompt", ""),
        "explanation": question.get("explanation", ""),
        "tags": "[]",
        "data": json.dumps(question.get("data", {}), ensure_ascii=False),
        # Import warnings never become a library state. Successful create/update
        # means the question passed validation and was explicitly confirmed.
        "needs_confirmation": 0,
        "created_at": existing_created_at or timestamp,
        "updated_at": timestamp,
    }


def row_to_question(row, stats=None):
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "article": row["article"],
        "prompt": row["prompt"],
        "explanation": row["explanation"],
        "data": json_loads(row["data"], {}),
        # Compatibility response for older clients; persisted questions are
        # always confirmed even if a legacy/manual row still contains 1.
        "needsConfirmation": False,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "stats": stats or empty_stats(),
    }


def empty_stats():
    return {"attempts": 0, "correct": 0, "incorrect": 0, "errorRate": 0, "lastPracticedAt": None}


def stats_for_question(db, question_id):
    row = db.execute(
        """
        SELECT
            COUNT(*) AS attempts,
            COALESCE(SUM(is_correct), 0) AS correct,
            COALESCE(SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END), 0) AS incorrect,
            MAX(created_at) AS last_practiced_at
        FROM attempts
        WHERE question_id = ?
        """,
        (question_id,),
    ).fetchone()
    attempts = int(row["attempts"] or 0)
    incorrect = int(row["incorrect"] or 0)
    return {
        "attempts": attempts,
        "correct": int(row["correct"] or 0),
        "incorrect": incorrect,
        "errorRate": round((incorrect / attempts) * 100, 1) if attempts else 0,
        "lastPracticedAt": row["last_practiced_at"],
    }


def question_list_query(args):
    filters = []
    params = []
    qtype = as_clean_string(args.get("type"))
    query = as_clean_string(args.get("q"))
    if qtype:
        filters.append("q.type = ?")
        params.append(qtype)
    if query:
        like = f"%{query}%"
        filters.append("(q.title LIKE ? OR q.article LIKE ? OR q.prompt LIKE ? OR q.data LIKE ?)")
        params.extend([like, like, like, like])
    where = "WHERE " + " AND ".join(filters) if filters else ""
    sort = args.get("sort", "created")
    if sort == "error_rate":
        order_by = "ORDER BY error_rate DESC, attempts DESC, q.updated_at DESC"
    elif sort == "recent_practice":
        order_by = "ORDER BY last_practiced_at IS NULL, last_practiced_at DESC, q.updated_at DESC"
    else:
        order_by = "ORDER BY q.created_at DESC"
    return (
        f"""
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
        {order_by}
        """,
        params,
    )
