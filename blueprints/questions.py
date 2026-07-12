"""Question bank CRUD and attempt submission."""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from db import get_db, now_iso
from grading import grade_attempt, validate_question
from parsing import normalize_question
from questions_service import (
    empty_stats,
    question_list_query,
    question_to_row,
    row_to_question,
    stats_for_question,
)

bp = Blueprint("questions", __name__)


@bp.get("/api/questions")
def list_questions():
    sql, params = question_list_query(request.args)
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
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
    return jsonify({"items": items})


@bp.get("/api/questions/<int:question_id>")
def get_question(question_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if not row:
            return jsonify({"error": "题目不存在"}), 404
        return jsonify(row_to_question(row, stats_for_question(db, question_id)))


@bp.post("/api/questions")
def create_question():
    payload = request.get_json(force=True, silent=True) or {}
    question = normalize_question(payload)
    validation = validate_question(question)
    if not validation["ok"]:
        return jsonify({"error": "题目结构校验失败", "validation": validation}), 400
    row = question_to_row(question)
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO questions(type, title, article, prompt, explanation, tags, data, needs_confirmation, created_at, updated_at)
            VALUES(:type, :title, :article, :prompt, :explanation, :tags, :data, :needs_confirmation, :created_at, :updated_at)
            """,
            row,
        )
        db.commit()
        created = db.execute("SELECT * FROM questions WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify(row_to_question(created, empty_stats())), 201


@bp.put("/api/questions/<int:question_id>")
def update_question(question_id):
    payload = request.get_json(force=True, silent=True) or {}
    question = normalize_question(payload)
    validation = validate_question(question)
    if not validation["ok"]:
        return jsonify({"error": "题目结构校验失败", "validation": validation}), 400
    with get_db() as db:
        existing = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if not existing:
            return jsonify({"error": "题目不存在"}), 404
        row = question_to_row(question, existing["created_at"])
        db.execute(
            """
            UPDATE questions
            SET type = :type,
                title = :title,
                article = :article,
                prompt = :prompt,
                explanation = :explanation,
                tags = :tags,
                data = :data,
                needs_confirmation = :needs_confirmation,
                updated_at = :updated_at
            WHERE id = :id
            """,
            {**row, "id": question_id},
        )
        db.commit()
        updated = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        return jsonify(row_to_question(updated, stats_for_question(db, question_id)))


@bp.delete("/api/questions/<int:question_id>")
def delete_question(question_id):
    with get_db() as db:
        cursor = db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        db.commit()
    if cursor.rowcount == 0:
        return jsonify({"error": "题目不存在"}), 404
    return jsonify({"ok": True})


@bp.post("/api/questions/<int:question_id>/attempts")
def submit_attempt(question_id):
    payload = request.get_json(force=True, silent=True) or {}
    answer = payload.get("answer", {})
    if not isinstance(answer, dict):
        return jsonify({"error": "答案必须是 JSON 对象"}), 400
    with get_db() as db:
        row = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if not row:
            return jsonify({"error": "题目不存在"}), 404
        question = row_to_question(row)
        is_correct, detail = grade_attempt(question, answer)
        db.execute(
            """
            INSERT INTO attempts(question_id, answer, is_correct, detail, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                question_id,
                json.dumps(answer, ensure_ascii=False),
                1 if is_correct else 0,
                json.dumps(detail, ensure_ascii=False),
                now_iso(),
            ),
        )
        db.commit()
        stats = stats_for_question(db, question_id)
    return jsonify({"isCorrect": is_correct, "detail": detail, "stats": stats})
