from flask import g, jsonify, request

from app.db import supabase_rest_request
from app.learn_helpers import _get_kpi_meta, _update_kpi_mastery, _upsert_daily_activity, compute_sm2


@learn_bp.route("/api/answer", methods=["POST"]) # pyright: ignore[reportUndefinedVariable]
def record_answer():
    user_id = g.user["id"]
    token   = g.token
    data    = request.get_json()

    question_id = data["question_id"]
    kpi_code    = data["kpi_code"]
    quality     = int(data["quality"])   # 0=wrong, 4=correct, 5=perfect

    # 1. Fetch current SRS state for this (user, question)
    _, rows = supabase_rest_request(
        "/user_srs_state", token=token,
        params={
            "user_id":     f"eq.{user_id}",
            "question_id": f"eq.{question_id}",
            "select":      "ease_factor,interval_days,repetitions,correct_attempts,total_attempts",
        },
        prefer="",
    )
    row  = rows[0] if rows else {}
    ef   = float(row.get("ease_factor",  2.5))
    iv   = int(row.get("interval_days",  0))
    reps = int(row.get("repetitions",    0))

    # 2. Run SM-2
    new_ef, new_iv, new_reps, next_review = compute_sm2(ef, iv, reps, quality)

    # 3. Upsert SRS state
    supabase_rest_request(
        "/user_srs_state", method="POST", token=token,
        payload={
            "user_id":          user_id,
            "question_id":      question_id,
            "ease_factor":      new_ef,
            "interval_days":    new_iv,
            "repetitions":      new_reps,
            "next_review":      next_review,
            "correct_attempts": row.get("correct_attempts", 0) + (1 if quality >= 3 else 0),
            "total_attempts":   row.get("total_attempts",   0) + 1,
        },
        prefer="resolution=merge-duplicates,return=minimal",
    )

    # 4. Recompute mastery
    meta = _get_kpi_meta(kpi_code)
    _update_kpi_mastery(
        user_id, token,
        kpi_code     = kpi_code,
        kpi_cluster  = meta.get("cluster", ""),
        deca_cluster = meta.get("deca_cluster", ""),
        event_id     = meta.get("event_id", ""),
    )

    # 5. Daily activity
    _upsert_daily_activity(
        user_id, token,
        q_answered=1,
        q_correct=1 if quality >= 3 else 0,
    )

    return jsonify({"ok": True, "next_review": next_review})