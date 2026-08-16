from flask import Blueprint, jsonify, request
import json
from datetime import datetime

from ..ai import call_json_with_fallback
from ..auth_utils import get_bearer_token, get_current_user
from ..db import supabase_rest_request
from ..events import canonical_event_id
from ..content_ops import catalog_id
from ..learn_validation import (
    LearnContentError,
    validate_roleplay_grade,
    validate_roleplay_prompt,
)
from ..learn_helpers import (
    _compute_streak,
    _fetch_kpi_questions,
    _load_all_kpis,
    _normalise_db_question,
    _save_questions_supabase,
    _supabase_svc,
    _update_kpi_mastery,
    _upsert_daily_activity,
    compute_sm2,
    get_due_kpis,
    get_ready_kpi_ids,
    get_kpi_catalog,
    _get_kpi_meta,
)
from .blueprint import learn_bp  # noqa: F401 — re-exported for app registration


@learn_bp.get("/api/kpis")
def api_kpis():
    all_kpis, events = _load_all_kpis()
    event_filter = request.args.get("event_id", "").strip()

    # Legacy param name support — remove once all clients send event_id
    if not event_filter:
        event_filter = request.args.get("event", "").strip()

    event_filter = canonical_event_id(event_filter)
    if request.args.get("event_id") and not event_filter:
        return jsonify({"error": "Unsupported beta event"}), 400

    if event_filter:
        all_kpis = [k for k in all_kpis if k["event"] == event_filter]
        try:
            ready_ids = get_ready_kpi_ids()
        except RuntimeError as error:
            return jsonify({"error": str(error)}), 502
        all_kpis = [kpi for kpi in all_kpis if catalog_id(kpi) in ready_ids]
    else:
        # No event specified — return events list for selection, no KPIs
        all_kpis = []

    # Filter to only due/unstarted KPIs if the user is logged in
    user = get_current_user()
    if user and event_filter:
        token = get_bearer_token()
        try:
            catalog = get_kpi_catalog(user["id"], token, event_filter)
        except RuntimeError as error:
            return jsonify({"error": str(error)}), 502
        return jsonify({**catalog, "events": events})

    return jsonify({"kpis": all_kpis, "unstarted": all_kpis, "due": [], "mastered": [], "in_progress": [], "events": events})

@learn_bp.post("/api/learn/generate")
def learn_generate():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    code = (body.get("code") or "").strip()
    text = (body.get("text") or "").strip()
    cluster = (body.get("cluster") or "").strip()
    standard = (body.get("standard") or "").strip()
    deca_cluster = (body.get("deca_cluster") or "").strip()
    event_id = canonical_event_id(body.get("event_id"))

    if not code or not text or not event_id:
        return jsonify({"error": "Missing required fields: code, text"}), 400
    kpi = next((k for k in _load_all_kpis()[0] if k["code"] == code and k["event"] == event_id), None)
    if not kpi:
        return jsonify({"error": "KPI does not belong to the selected beta event"}), 400
    text = kpi["text"]
    cluster = kpi["cluster"]
    standard = kpi["standard"]
    deca_cluster = kpi["deca_cluster"]

    prompt = f"""You are a DECA exam coach creating study materials for high school business students.

Generate educational content for this DECA Performance Indicator (KPI):
- Code: {code}
- KPI: {text}
- Subject Cluster: {cluster}
- Standard: {standard}
- DECA Cluster: {deca_cluster or "Business"}

Return ONLY valid JSON (no markdown, no extra text) with this exact structure:

{{
  "vocab": [
    {{"term": "Key Term 1", "definition": "Clear, precise definition a student must know"}},
    {{"term": "Key Term 2", "definition": "Clear, precise definition"}},
    {{"term": "Key Term 3", "definition": "Clear, precise definition"}},
    {{"term": "Key Term 4", "definition": "Clear, precise definition"}},
    {{"term": "Key Term 5", "definition": "Clear, precise definition"}},
    {{"term": "Key Term 6", "definition": "Clear, precise definition"}}
  ],
  "concept": {{
    "summary": "One clear sentence explaining what this KPI is about",
    "explanation": "2-3 paragraphs for a high school student. Plain language, real-world examples, why it matters in DECA.",
    "bullets": ["Key insight 1", "Key insight 2", "Key insight 3"],
    "table": [
      {{"term": "Term 1", "definition": "Brief definition"}},
      {{"term": "Term 2", "definition": "Brief definition"}},
      {{"term": "Term 3", "definition": "Brief definition"}}
    ],
    "concept_check": {{
      "question": "One short question testing the core idea of this KPI (not vocab, not a scenario — just the main concept in plain language)",
      "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
      "correct": 0,
      "explanation": "One sentence explaining why this is correct."
    }}
  }},
  "recognition_questions": [
    {{
      "text": "Question stem testing recall or definition of this KPI",
      "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
      "correct": 0,
      "explanation": "Choice A is correct because [reason]. The others are wrong because [reason].",
      "kpi_code": "{code}",
      "kpi_text": "{text}",
      "cluster": "{cluster}",
      "deca_cluster": "{deca_cluster or 'Business'}"
    }}
  ],
  "application_question": {{
    "text": "A realistic business scenario where a student must apply this KPI concept. 2-3 sentences setting the scene, then a clear question.",
    "choices": ["Choice A — specific action or decision", "Choice B", "Choice C", "Choice D"],
    "correct": 0,
    "explanation": "Choice A is correct because [specific business reasoning]. The others are wrong because [reason each].",
    "kpi_code": "{code}",
    "kpi_text": "{text}",
    "cluster": "{cluster}",
    "deca_cluster": "{deca_cluster or 'Business'}"
  }}
}}

Rules:
- "recognition_questions": generate EXACTLY 5 questions. These test recall, definition, and identification — straightforward knowledge checks.
- "application_question": generate EXACTLY 1 question. This is a scenario-based question where the student must apply the concept in a realistic business situation (a manager facing a decision, a consultant giving advice, etc.). Make it feel like a real DECA exam scenario.
- All questions: 4 plausible choices (A–D), only one correct. Distribute correct index (0–3) across the 5 recognition questions.
- Do NOT repeat the same scenario angle in both recognition and application questions."""

    ready_status, ready_rows = _supabase_svc(
        "/generated_kpi_lessons",
        params={"kpi_id": f"eq.{catalog_id(kpi)}", "status": "eq.ready", "select": "lesson,lesson_version", "limit": "1"},
    )
    if ready_status != 200:
        return jsonify({"error": "Generated lesson readiness could not be loaded."}), 502
    if not isinstance(ready_rows, list) or not ready_rows:
        return jsonify({"error": "This KPI is not ready for Learn Mode yet."}), 404
    result = ready_rows[0].get("lesson") or {}

    # ── Normalise into a unified questions list for storage ───────────────────
    # recognition_questions (list) + application_question (single) → questions[]
    practice = result.get("practice_questions") or []
    recognition = practice[:2] or result.get("recognition_questions") or []
    application = practice[2:] or result.get("application_questions") or []

    # Tag each question with its type
    for q in recognition:
        q["question_type"] = "recognition"
        q["kpi_code"] = code
        q["kpi_text"] = text
        q["cluster"] = cluster
        q["deca_cluster"] = deca_cluster

    all_questions = list(recognition)

    if isinstance(application, dict):
        application = [application]
    for q in application:
        if not isinstance(q, dict) or not q.get("text"):
            continue
        q["question_type"] = "application"
        q["kpi_code"] = code
        q["kpi_text"] = text
        q["cluster"] = cluster
        q["deca_cluster"] = deca_cluster
        all_questions.append(q)

    # ── Persist to Supabase with UUIDs ────────────────────────────────────────
    saved = _save_questions_supabase(
        all_questions, code, text, cluster, deca_cluster, event_id
    )
    if len(saved) < 3:
        return jsonify({"error": "Generated questions could not be persisted reliably."}), 502
    all_questions = saved[:3]

    # ── Return structured response the frontend expects ───────────────────────
    result["recognition_questions"] = [q for q in all_questions if q.get("question_type") == "recognition"]
    application_questions = [q for q in all_questions if q.get("question_type") == "application"]
    result["application_question"] = application_questions[0] if application_questions else None
    result["application_questions"] = application_questions
    result["practice_questions"] = all_questions
    # Keep a flat "questions" list for backward compat with cached clients
    result["questions"] = all_questions
    result["lesson_version"] = int(ready_rows[0].get("lesson_version") or 4)
    return jsonify(result)


@learn_bp.get("/api/learn/questions")
def learn_get_questions():
    """Return questions from Supabase for a KPI, annotated with the user's mastery."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    kpi_code = request.args.get("kpi_code", "").strip()
    event_id = canonical_event_id(request.args.get("event_id"))
    if not kpi_code or not event_id:
        return jsonify({"error": "Missing kpi_code or supported event_id"}), 400

    token = get_bearer_token()
    user_id = user.get("id", "")

    rows = _fetch_kpi_questions(kpi_code, event_id)
    questions = [_normalise_db_question(r) for r in rows]

    # Fetch this user's answer history for these question IDs
    q_ids = [q["id"] for q in questions if q["id"]]
    answered_correctly: set[str] = set()
    if q_ids and token:
        # PostgREST "in" filter: ?question_id=in.(uuid1,uuid2,...)
        id_list = ",".join(q_ids)
        status, results = supabase_rest_request(
            "/user_srs_state",
            token=token,
            params={
                "user_id": f"eq.{user_id}",
                "question_id": f"in.({id_list})",
                "event_id": f"eq.{event_id}",
                "interval_days": "gte.7",
                "select": "question_id",
            },
            prefer="",
        )
        if status == 200 and isinstance(results, list):
            answered_correctly = {r["question_id"] for r in results}

    for q in questions:
        q["mastered"] = q["id"] in answered_correctly

    return jsonify({"questions": questions, "total": len(questions)})


@learn_bp.get("/api/learn/question-benchmark")
def learn_question_benchmark():
    """Return per-question benchmarking data for the current user."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    token = get_bearer_token()
    user_id = user.get("id", "")
    question_id = request.args.get("question_id", "").strip()
    if not question_id:
        return jsonify({"error": "Missing question_id"}), 400

    _, question_rows = _supabase_svc(
        "/kpi_questions",
        params={
            "id": f"eq.{question_id}",
            "select": "id,kpi_code,kpi_text,kpi_cluster,deca_cluster,event_id,question_text,question_type,quality_state,answer_reveal",
            "limit": "1",
        },
    )
    if not isinstance(question_rows, list) or not question_rows:
        return jsonify({"error": "Question not found"}), 404

    question = question_rows[0]
    quality_state = question.get("quality_state") or {}
    mcq_quality = quality_state.get("mcq_quality") or {}
    quality_score = float(mcq_quality.get("score", 0) or 0)

    _, response_rows = supabase_rest_request(
        "/responses",
        token=token,
        params={
            "user_id": f"eq.{user_id}",
            "question_id": f"eq.{question_id}",
            "select": "response_time_ms,correct,answered_at",
            "order": "answered_at.desc",
            "limit": "25",
        },
        prefer="",
    )
    response_rows = response_rows if isinstance(response_rows, list) else []
    attempts = len(response_rows)
    correct_attempts = sum(1 for row in response_rows if row.get("correct") is True)
    accuracy_pct = round(correct_attempts / max(attempts, 1) * 100, 1) if attempts else 0
    avg_response_ms = round(
        sum(int(row.get("response_time_ms", 0) or 0) for row in response_rows) / max(attempts, 1),
        1,
    ) if attempts else 0

    _, baseline_rows = supabase_rest_request(
        "/user_timing_profile",
        token=token,
        params={
            "user_id": f"eq.{user_id}",
            "question_type": f"eq.{question.get('question_type', 'recognition')}",
            "kpi_cluster": f"eq.{question.get('kpi_cluster', '')}",
            "select": "median_ms,sample_count",
            "limit": "1",
        },
        prefer="",
    )
    baseline_row = baseline_rows[0] if isinstance(baseline_rows, list) and baseline_rows else {}
    baseline_ms = int(baseline_row.get("median_ms", 12000))
    pace_vs_baseline_pct = round(((avg_response_ms - baseline_ms) / max(baseline_ms, 1)) * 100, 1) if attempts else 0

    if quality_score >= 85:
        benchmark_label = "Excellent"
        benchmark_class = "is-strong"
    elif quality_score >= 70:
        benchmark_label = "Usable"
        benchmark_class = "is-usable"
    elif quality_score >= 55:
        benchmark_label = "Needs work"
        benchmark_class = "is-weak"
    else:
        benchmark_label = "Review"
        benchmark_class = "is-weak"

    if attempts:
        if pace_vs_baseline_pct <= -15:
            pace_label = "faster than baseline"
        elif pace_vs_baseline_pct >= 15:
            pace_label = "slower than baseline"
        else:
            pace_label = "about on pace"
    else:
        pace_label = "no personal baseline yet"

    summary = (
        f"{accuracy_pct:.1f}% accuracy across {attempts} attempt(s). "
        f"Response speed is {pace_label}. "
        f"Question quality is {quality_score:.0f}%."
    )

    return jsonify(
        {
            "benchmark": {
                "question_id": question_id,
                "attempts": attempts,
                "correct_attempts": correct_attempts,
                "accuracy_pct": accuracy_pct,
                "avg_response_ms": avg_response_ms,
                "baseline_ms": baseline_ms,
                "pace_vs_baseline_pct": pace_vs_baseline_pct,
                "quality_score": round(quality_score, 1),
                "benchmark_label": benchmark_label,
                "benchmark_class": benchmark_class,
                "summary": summary,
            }
        }
    )


@learn_bp.post("/api/learn/question-report")
def learn_question_report():
    """Persist a user report for a problematic question."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    question_id = (body.get("question_id") or "").strip()
    reason = (body.get("reason") or "").strip()
    details = (body.get("details") or "").strip()
    benchmark = body.get("benchmark") or {}

    if not question_id or not reason:
        return jsonify({"error": "Missing question_id or reason"}), 400

    token = get_bearer_token()
    user_id = user.get("id", "")

    _, question_rows = _supabase_svc(
        "/kpi_questions",
        params={
            "id": f"eq.{question_id}",
            "select": "id,kpi_code,question_type",
            "limit": "1",
        },
    )
    question_row = question_rows[0] if isinstance(question_rows, list) and question_rows else {}

    payload = {
        "user_id": user_id,
        "question_id": question_id,
        "kpi_code": question_row.get("kpi_code", ""),
        "question_type": question_row.get("question_type", "recognition"),
        "reason": reason,
        "details": details,
        "benchmark": benchmark if isinstance(benchmark, dict) else {},
    }
    status, data = supabase_rest_request(
        "/question_reports",
        method="POST",
        token=token,
        payload=payload,
        prefer="return=representation",
    )
    if status in (200, 201) and isinstance(data, list):
        return jsonify({"ok": True, "report": data[0] if data else payload})
    return jsonify({"error": "Could not save report", "detail": data}), max(status, 400)


@learn_bp.post("/api/learn/answer")
def learn_record_answer():
    """
    Record a question answer. Runs the full adaptive learning engine:
    behavioral feature extraction → inference → dampened SM-2 → evaluation log.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    token   = get_bearer_token()
    user_id = user.get("id", "")
    body    = request.get_json(silent=True) or {}

    question_id = str(body.get("question_id") or "").strip()
    session_id = str(body.get("session_id") or "").strip()
    attempt_id = str(body.get("attempt_id") or "").strip()
    try:
        selected_index = int(body.get("selected_index"))
        response_time_ms = max(0, int(body.get("response_time_ms", 12000)))
        time_to_first_ms = body.get("time_to_first_ms")
        time_to_first_ms = None if time_to_first_ms is None else max(0, int(time_to_first_ms))
        answer_change_count = max(0, int(body.get("answer_change_count", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid answer telemetry"}), 400
    if not question_id or not session_id or not attempt_id or not 0 <= selected_index <= 3:
        return jsonify({"error": "question_id, session_id, attempt_id, and selected_index are required"}), 400

    status, result = supabase_rest_request(
        "/rpc/record_beta_answer", method="POST", token=token,
        payload={
            "p_session_id": session_id,
            "p_question_id": question_id,
            "p_selected_index": selected_index,
            "p_response_time_ms": response_time_ms,
            "p_time_to_first_ms": time_to_first_ms,
            "p_answer_change_count": answer_change_count,
            "p_idempotency_key": f"{user_id}:{attempt_id}",
        },
        prefer="return=representation",
    )
    if status not in (200, 201) or not isinstance(result, dict) or not result.get("ok"):
        return jsonify({"error": "Answer transaction failed", "detail": result}), 502
    return jsonify(result)

    question_id         = (body.get("question_id") or "").strip()
    selected_index      = body.get("selected_index")
    response_time_ms    = int(body.get("response_time_ms", 12000))
    time_to_first_ms    = body.get("time_to_first_ms")
    answer_change_count = int(body.get("answer_change_count", 0))
    session_id          = body.get("session_id", "")
    kpi_cluster_arg     = (body.get("cluster") or "").strip()
    deca_cluster        = (body.get("deca_cluster") or "").strip()
    event_id            = canonical_event_id(body.get("event_id"))

    if not question_id or selected_index is None or not event_id or not session_id:
        return jsonify({"error": "Missing question_id, selected_index, session_id, or supported event_id"}), 400

    session_status, session_rows = supabase_rest_request(
        "/user_study_sessions", token=token,
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}", "event_id": f"eq.{event_id}", "select": "id", "limit": "1"},
        prefer="",
    )
    if session_status != 200 or not isinstance(session_rows, list) or not session_rows:
        return jsonify({"error": "Session does not belong to this user and event"}), 400

    q_status, q_rows = _supabase_svc("/kpi_questions", params={
        "id": f"eq.{question_id}", "event_id": f"eq.{event_id}",
        "select": "id,kpi_code,kpi_cluster,deca_cluster,event_id,question_type,correct_index", "limit": "1",
    })
    if q_status != 200 or not isinstance(q_rows, list) or not q_rows:
        return jsonify({"error": "Question is not part of the selected event"}), 400
    question = q_rows[0]
    try:
        selected_index = int(selected_index)
    except (TypeError, ValueError):
        return jsonify({"error": "selected_index must be an integer"}), 400
    kpi_code = question["kpi_code"]
    question_type = question.get("question_type") or "recognition"
    kpi_cluster_arg = question.get("kpi_cluster") or kpi_cluster_arg
    deca_cluster = question.get("deca_cluster") or deca_cluster
    correct = selected_index == int(question["correct_index"])

    meta = {"cluster": kpi_cluster_arg, "deca_cluster": deca_cluster, "event_id": event_id}
    kpi_cluster = kpi_cluster_arg

    answered_at = datetime.now(timezone.utc)
    idem_hash   = make_idempotency_hash(user_id, session_id, question_id, correct, answered_at)

    # ── 1. SRS state ─────────────────────────────────────────────────────────
    _, srs_rows = supabase_rest_request(
        "/user_srs_state", token=token,
        params={
            "user_id":     f"eq.{user_id}",
            "question_id": f"eq.{question_id}",
            "event_id": f"eq.{event_id}",
            "select":      "ease_factor,interval_days,repetitions,correct_attempts,total_attempts",
            "limit":       "1",
        },
        prefer="",
    )
    cur              = srs_rows[0] if isinstance(srs_rows, list) and srs_rows else {}
    ef               = float(cur.get("ease_factor",   2.5))
    iv               = int(cur.get("interval_days",   0))
    reps             = int(cur.get("repetitions",     0))
    total_attempts   = int(cur.get("total_attempts",  0))
    correct_attempts = int(cur.get("correct_attempts", 0))

    # ── 2. Inference state ───────────────────────────────────────────────────
    _, inf_rows = supabase_rest_request(
        "/kpi_inference_state", token=token,
        params={
            "user_id":  f"eq.{user_id}",
            "kpi_code": f"eq.{kpi_code}",
            "event_id": f"eq.{event_id}",
            "select":   ("mastery_prob,recognition_mastery,application_mastery,"
                         "confidence_est,sample_count"),
        },
        prefer="",
    ) if kpi_code else (None, [])
    inf                = inf_rows[0] if isinstance(inf_rows, list) and inf_rows else {}
    prev_mastery       = float(inf.get("mastery_prob",        0.5))
    prev_recog_mastery = float(inf.get("recognition_mastery", 0.5))
    prev_app_mastery   = float(inf.get("application_mastery", 0.5))
    prev_confidence    = float(inf.get("confidence_est",      0.5))
    inf_samples        = int(inf.get("sample_count",          0))

    # ── 3. Timing baseline ───────────────────────────────────────────────────
    _, baseline_rows = supabase_rest_request(
        "/user_timing_profile", token=token,
        params={
            "user_id":       f"eq.{user_id}",
            "question_type": f"eq.{question_type}",
            "kpi_cluster":   f"eq.{kpi_cluster}",
            "event_id":      f"eq.{event_id}",
            "select":        "median_ms,sample_count",
        },
        prefer="",
    )
    bp             = baseline_rows[0] if isinstance(baseline_rows, list) and baseline_rows else {}
    baseline_ms    = int(bp.get("median_ms",    12000))
    baseline_count = int(bp.get("sample_count", 0))

    # ── 4. Feature extraction ────────────────────────────────────────────────
    features     = extract_features(response_time_ms, time_to_first_ms, answer_change_count, baseline_ms)
    instant_conf = infer_instant_confidence(features, correct)  # authority: SRS quality only

    # ── 5. Stability ─────────────────────────────────────────────────────────
    _, recent_rows = supabase_rest_request(
        "/responses", token=token,
        params={
            "user_id":       f"eq.{user_id}",
            "question_type": f"eq.{question_type}",
            "event_id":      f"eq.{event_id}",
            "select":        "instant_confidence",
            "order":         "answered_at.desc",
            "limit":         "8",
        },
        prefer="",
    )
    recent_scores = [
        float(r["instant_confidence"])
        for r in (recent_rows if isinstance(recent_rows, list) else [])
        if r.get("instant_confidence") is not None
    ]
    stability = compute_stability_confidence(recent_scores)

    # ── 6. EMA confidence + volatility ───────────────────────────────────────
    new_confidence_est    = update_confidence_ema(prev_confidence, instant_conf, inf_samples)
    confidence_volatility = compute_confidence_volatility(instant_conf, new_confidence_est)

    # ── 7. Inference ─────────────────────────────────────────────────────────
    uncertainty = compute_uncertainty(prev_mastery, new_confidence_est, stability)
    tensions    = classify_tensions(prev_mastery, new_confidence_est, uncertainty)

    new_mastery = update_mastery(prev_mastery, correct, new_confidence_est)
    new_recog_mastery = (
        update_recognition_mastery(prev_recog_mastery, correct, new_confidence_est)
        if question_type == "recognition" else prev_recog_mastery
    )
    new_app_mastery = (
        update_application_mastery(prev_app_mastery, correct, new_confidence_est)
        if question_type == "application" else prev_app_mastery
    )
    new_mastery     = reconcile_mastery(new_mastery, correct_attempts, total_attempts)
    queue_actions   = get_queue_adjustments(tensions)

    # ── 8. SRS ───────────────────────────────────────────────────────────────
    raw_quality      = srs_quality_score(correct, instant_conf)
    dampening        = compute_dampening(uncertainty, tensions, stability, confidence_volatility)
    dampened_quality = apply_dampened_quality(raw_quality, dampening)

    new_ef, new_iv, new_reps, next_review = compute_sm2(ef, iv, reps, dampened_quality)

    srs_status, srs_data = supabase_rest_request(
        "/user_srs_state", method="POST", token=token,
        params={"on_conflict": "user_id,event_id,question_id"},
        payload={
            "user_id":          user_id,
            "question_id":      question_id,
            "event_id":         event_id,
            "ease_factor":      new_ef,
            "interval_days":    new_iv,
            "repetitions":      new_reps,
            "next_review":      next_review,
            "correct_attempts": correct_attempts + (1 if correct else 0),
            "total_attempts":   total_attempts + 1,
        },
        prefer="resolution=merge-duplicates,return=minimal",
    )

    # ── 9. Response event ────────────────────────────────────────────────────
    response_status, response_data = supabase_rest_request(
        "/responses", method="POST", token=token,
        payload={
            "user_id":             user_id,
            "question_id":         question_id,
            "event_id":            event_id,
            "session_id":          session_id,
            "kpi_code":            kpi_code,
            "question_type":       question_type,
            "selected_index":      selected_index,
            "correct":             correct,
            "response_time_ms":    response_time_ms,
            "time_to_first_ms":    time_to_first_ms,
            "answer_changed":      answer_change_count > 0,
            "answer_change_count": answer_change_count,
            "instant_confidence":  instant_conf,
            "is_valid":            True,
            "idempotency_hash":    idem_hash,
            "answered_at":         answered_at.isoformat(),
        },
        prefer="resolution=ignore,return=minimal",
    )
    if srs_status not in (200, 201, 204) or response_status not in (200, 201, 204):
        return jsonify({"error": "Answer persistence failed", "detail": {"srs": srs_data, "response": response_data}}), 502

    # ── 10. Inference state ───────────────────────────────────────────────────
    if kpi_code:
        supabase_rest_request(
            "/kpi_inference_state", method="POST", token=token,
            params={"on_conflict": "user_id,event_id,kpi_code"},
            payload={
                "user_id":                 user_id,
                "kpi_code":                kpi_code,
                "event_id":                event_id,
                "mastery_prob":            new_mastery,
                "recognition_mastery":     new_recog_mastery,
                "application_mastery":     new_app_mastery,
                "confidence_est":          new_confidence_est,
                "last_instant_confidence": instant_conf,
                "uncertainty":             uncertainty,
                "sample_count":            inf_samples + 1,
                "last_updated":            answered_at.isoformat(),
            },
            prefer="resolution=merge-duplicates,return=minimal",
        )

    # ── 11. Evaluation log ────────────────────────────────────────────────────
    supabase_rest_request(
        "/learning_evaluation_log", method="POST", token=token,
        payload={
            "user_id":              user_id,
            "kpi_code":             kpi_code,
            "event_id":             event_id,
            "kpi_cluster":          kpi_cluster,
            "question_type":        question_type,
            "recognition_mastery":  new_recog_mastery,
            "application_mastery":  new_app_mastery,
            "predicted_mastery":    prev_mastery,
            "confidence_est":       new_confidence_est,
            "instant_confidence":   instant_conf,
            "volatility":           confidence_volatility,
            "uncertainty":          uncertainty,
            "correct":              correct,
            "response_time_ms":     response_time_ms,
            "recorded_at":          answered_at.isoformat(),
        },
        prefer="return=minimal",
    )

    # ── 12. Timing baseline ───────────────────────────────────────────────────
    new_baseline = update_baseline(baseline_ms, response_time_ms, baseline_count)
    supabase_rest_request(
        "/user_timing_profile", method="POST", token=token,
        params={"on_conflict": "user_id,event_id,question_type,kpi_cluster"},
        payload={
            "user_id":       user_id,
            "question_type": question_type,
            "kpi_cluster":   kpi_cluster,
            "event_id":      event_id,
            "median_ms":     new_baseline,
            "sample_count":  baseline_count + 1,
            "updated_at":    answered_at.isoformat(),
        },
        prefer="resolution=merge-duplicates,return=minimal",
    )

    # ── 13. KPI mastery + daily activity ─────────────────────────────────────
    if kpi_code:
        _update_kpi_mastery(user_id, token, kpi_code, kpi_cluster,
                            meta.get("deca_cluster", deca_cluster),
                            meta.get("event_id", event_id))
    _upsert_daily_activity(user_id, token, event_id, q_answered=1, q_correct=1 if correct else 0)

    return jsonify({
        "ok":                  True,
        "next_review":         next_review,
        "mastery":             new_mastery,
        "recognition_mastery": new_recog_mastery,
        "application_mastery": new_app_mastery,
        "confidence":          new_confidence_est,
        "instant":             instant_conf,
        "volatility":          confidence_volatility,
        "uncertainty":         uncertainty,
        "tensions":            list(tensions.keys()),
        "queue_actions":       queue_actions,
        "dampening":           dampening,
        "srs": {
            "ease_factor":   new_ef,
            "interval_days": new_iv,
            "next_review":   next_review,
            "repetitions":   new_reps,
        },
    })


@learn_bp.post("/api/learn/session/start")
def learn_session_start():
    """Create a session record and return its id."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    event_id = canonical_event_id(body.get("event_id"))
    if not event_id:
        return jsonify({"error": "Unsupported beta event"}), 400
    session_type = (body.get("session_type") or "full").strip()
    token = get_bearer_token()
    user_id = user.get("id", "")

    status, data = supabase_rest_request(
        "/user_study_sessions",
        method="POST",
        token=token,
        payload={
            "user_id": user_id,
            "event_id": event_id,
            "session_type": session_type,
        },
        prefer="return=representation",
    )
    if status in (200, 201) and isinstance(data, list) and data:
        return jsonify({"session_id": data[0].get("id")})
    return jsonify({"error": "Could not create session", "detail": data}), max(
        status, 400
    )


@learn_bp.post("/api/learn/session/end")
def learn_session_end():
    """Finalise session record and update daily activity."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    try:
        kpis_studied = int(body.get("kpis_studied", 0))
        vocab_total = int(body.get("vocab_total", 0))
        vocab_correct = int(body.get("vocab_correct", 0))
        roleplay_score = body.get("roleplay_score")
        roleplay_score = None if roleplay_score is None else int(roleplay_score)
        duration_seconds = int(body.get("duration_seconds", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid session summary"}), 400
    ar_answers = body.get("ar_answers", [])  # list of {kpi_code, kpi_text, answer, timestamp}

    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    token = get_bearer_token()
    status, result = supabase_rest_request(
        "/rpc/finish_beta_session", method="POST", token=token,
        payload={
            "p_session_id": session_id,
            "p_duration_seconds": duration_seconds,
            "p_kpis_studied": kpis_studied,
            "p_vocab_total": vocab_total,
            "p_vocab_correct": vocab_correct,
            "p_roleplay_score": roleplay_score,
            "p_ar_answers": ar_answers if isinstance(ar_answers, list) else [],
        },
        prefer="return=representation",
    )
    if status not in (200, 201) or not isinstance(result, dict) or not result.get("ok"):
        return jsonify({"error": "Session completion transaction failed", "detail": result}), 502
    return jsonify(result)

    token = get_bearer_token()
    user_id = user.get("id", "")

    session_status, session_rows = supabase_rest_request(
        "/user_study_sessions", token=token,
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}", "select": "event_id", "limit": "1"},
        prefer="",
    )
    if session_status != 200 or not isinstance(session_rows, list) or not session_rows:
        return jsonify({"error": "Study session not found"}), 404
    event_id = canonical_event_id(session_rows[0].get("event_id"))
    if not event_id:
        return jsonify({"error": "Study session has an unsupported event"}), 400

    acc = round(questions_correct / max(questions_answered, 1) * 100, 1)

    payload: dict = {
        "ended_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_seconds": duration_seconds,
        "kpis_studied": kpis_studied,
        "questions_answered": questions_answered,
        "questions_correct": questions_correct,
        "vocab_total": vocab_total,
        "vocab_correct": vocab_correct,
        "accuracy_pct": acc,
    }
    if roleplay_score is not None:
        payload["roleplay_score"] = int(roleplay_score)
    if ar_answers:
        payload["ar_answers"] = ar_answers

    end_status, end_data = supabase_rest_request(
        f"/user_study_sessions",
        method="PATCH",
        token=token,
        payload=payload,
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
        prefer="return=minimal",
    )
    if end_status not in (200, 204):
        return jsonify({"error": "Could not finish session", "detail": end_data}), 502

    # Update daily activity with session-level deltas
    _upsert_daily_activity(
        user_id,
        token,
        event_id,
        kpis_delta=kpis_studied,
        minutes=duration_seconds // 60,
    )

    return jsonify({"ok": True, "accuracy_pct": acc})


@learn_bp.get("/api/learn/analytics")
def learn_analytics():
    """
    Full mastery + session analytics for the home dashboard.
    Returns: summary, per-KPI mastery, cluster breakdown, recent sessions,
             30-day activity heatmap, streak, question type breakdown.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    token = get_bearer_token()
    user_id = user.get("id", "")
    event_id = canonical_event_id(request.args.get("event_id"))
    if not event_id:
        return jsonify({"error": "Supported event_id is required"}), 400

    # KPI mastery rows
    mastery_params: dict = {"user_id": f"eq.{user_id}", "event_id": f"eq.{event_id}", "select": "*"}
    _, mastery_rows = supabase_rest_request(
        "/user_kpi_mastery", token=token, params=mastery_params, prefer="",
    )
    mastery_rows = mastery_rows if isinstance(mastery_rows, list) else []

    # Recent sessions (last 20)
    _, sessions = supabase_rest_request(
        "/user_study_sessions",
        token=token,
        params={
            "user_id": f"eq.{user_id}",
            "event_id": f"eq.{event_id}",
            "select": "*",
            "order": "started_at.desc",
            "limit": "20",
        },
        prefer="",
    )
    sessions = sessions if isinstance(sessions, list) else []

    # 30-day activity
    _, daily = supabase_rest_request(
        "/user_daily_activity",
        token=token,
        params={
            "user_id": f"eq.{user_id}",
            "event_id": f"eq.{event_id}",
            "select": "*",
            "order": "activity_date.desc",
            "limit": "30",
        },
        prefer="",
    )
    daily = daily if isinstance(daily, list) else []

    # Due questions count
    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    due_params: dict = {
        "user_id": f"eq.{user_id}",
        "event_id": f"eq.{event_id}",
        "next_review": f"lte.{now_iso}",
        "select": "question_id",
    }
    _, due_rows = supabase_rest_request(
        "/user_srs_state", token=token, params=due_params, prefer="",
    )
    due_count = len(due_rows) if isinstance(due_rows, list) else 0

    # ── SRS state for question-type breakdown ──────────────────────────────
    srs_params: dict = {
        "user_id": f"eq.{user_id}",
        "event_id": f"eq.{event_id}",
        "select": "question_id,correct_attempts,total_attempts",
    }
    _, srs_rows = supabase_rest_request(
        "/user_srs_state", token=token, params=srs_params, prefer="",
    )
    srs_rows = srs_rows if isinstance(srs_rows, list) else []

    # Build question_type_breakdown if we have data
    question_type_breakdown: dict = {}
    if srs_rows:
        # Fetch question types for the answered question IDs (batch up to 200)
        q_ids = [r["question_id"] for r in srs_rows[:200]]
        id_list = ",".join(q_ids)
        _, q_meta = _supabase_svc(
            "/kpi_questions",
            params={
                "id": f"in.({id_list})",
                "select": "id,question_type",
            },
        )
        q_type_map = {}
        if isinstance(q_meta, list):
            q_type_map = {r["id"]: r.get("question_type", "recognition") for r in q_meta}

        recog_total = recog_correct = app_total = app_correct = 0
        for row in srs_rows:
            qtype = q_type_map.get(row["question_id"], "recognition")
            total = int(row.get("total_attempts", 0))
            correct = int(row.get("correct_attempts", 0))
            if qtype == "application":
                app_total += total
                app_correct += correct
            else:
                recog_total += total
                recog_correct += correct

        question_type_breakdown = {
            "recognition": {
                "total": recog_total,
                "correct": recog_correct,
                "accuracy": round(recog_correct / max(recog_total, 1) * 100, 1),
            },
            "application": {
                "total": app_total,
                "correct": app_correct,
                "accuracy": round(app_correct / max(app_total, 1) * 100, 1),
            },
        }

    # ── Aggregates ────────────────────────────────────────────────────────────
    avg_mastery = round(
        sum(m.get("mastery_score", 0) for m in mastery_rows) / max(len(mastery_rows), 1), 1,
    )
    mastered_kpis = sum(1 for m in mastery_rows if float(m.get("mastery_score", 0)) >= 80)
    total_q_ans = sum(s.get("questions_answered", 0) for s in sessions)

    # Cluster breakdown
    cluster_map: dict = {}
    for m in mastery_rows:
        c = m.get("kpi_cluster") or m.get("deca_cluster") or "Other"
        if c not in cluster_map:
            cluster_map[c] = {"cluster": c, "scores": [], "kpi_count": 0}
        cluster_map[c]["scores"].append(float(m.get("mastery_score", 0)))
        cluster_map[c]["kpi_count"] += 1
    cluster_breakdown = [
        {
            "cluster": v["cluster"],
            "avg_mastery": round(sum(v["scores"]) / len(v["scores"]), 1),
            "kpi_count": v["kpi_count"],
        }
        for v in cluster_map.values()
    ]
    cluster_breakdown.sort(key=lambda x: x["avg_mastery"])

    weak = sorted(mastery_rows, key=lambda m: m.get("mastery_score", 0))[:5]
    strong = sorted(mastery_rows, key=lambda m: m.get("mastery_score", 0), reverse=True)[:5]
    try:
        ready_ids = get_ready_kpi_ids()
    except RuntimeError:
        ready_ids = set()
    for row in weak + strong:
        row["learn_ready"] = f"{event_id}:{row.get('kpi_code', '')}" in ready_ids
    streak = _compute_streak(daily)

    # Recent question history (latest attempts, joined with question text)
    _, response_rows = supabase_rest_request(
        "/responses",
        token=token,
        params={
            "user_id": f"eq.{user_id}",
            "event_id": f"eq.{event_id}",
            "select": "question_id,kpi_code,question_type,correct,response_time_ms,time_to_first_ms,answer_change_count,instant_confidence,answered_at,session_id,event_id",
            "order": "answered_at.desc",
            "limit": "1000",
        },
        prefer="",
    )
    response_rows = response_rows if isinstance(response_rows, list) else []

    history_rows = []
    if response_rows:
        q_ids = [r.get("question_id") for r in response_rows if r.get("question_id")]
        q_ids = q_ids[:100]
        q_meta_map = {}
        if q_ids:
            id_list = ",".join(q_ids)
            _, q_meta = _supabase_svc(
                "/kpi_questions",
                params={
                    "id": f"in.({id_list})",
                    "select": "id,question_text,kpi_code,kpi_text,question_type",
                },
            )
            if isinstance(q_meta, list):
                q_meta_map = {row["id"]: row for row in q_meta}

        for row in response_rows[:50]:
            meta = q_meta_map.get(row.get("question_id"), {})
            response_ms = int(row.get("response_time_ms", 0) or 0)
            first_ms = row.get("time_to_first_ms")
            history_rows.append(
                {
                    "question_id": row.get("question_id", ""),
                    "question_text": meta.get("question_text", ""),
                    "kpi_code": row.get("kpi_code", "") or meta.get("kpi_code", ""),
                    "kpi_text": meta.get("kpi_text", ""),
                    "question_type": row.get("question_type", "") or meta.get("question_type", "recognition"),
                    "correct": bool(row.get("correct", False)),
                    "response_time_ms": response_ms,
                    "response_time_label": f"{round(response_ms / 1000, 1)}s" if response_ms else "--",
                    "time_to_first_ms": first_ms,
                    "time_to_first_label": f"{round(float(first_ms) / 1000, 1)}s" if first_ms is not None else "--",
                    "answer_change_count": int(row.get("answer_change_count", 0) or 0),
                    "instant_confidence": row.get("instant_confidence"),
                    "answered_at": row.get("answered_at", ""),
                    "session_id": row.get("session_id", ""),
                    "event_id": row.get("event_id", ""),
                }
            )

    questions_answered_total = max(total_q_ans, len(response_rows))
    questions_correct_total = sum(1 for row in response_rows if row.get("correct") is True)
    progress_accuracy = round(
        questions_correct_total / max(questions_answered_total, 1) * 100,
        1,
    ) if questions_answered_total else 0
    avg_recent_response_ms = 0
    if history_rows:
        avg_recent_response_ms = round(
            sum(row.get("response_time_ms", 0) for row in history_rows) / max(len(history_rows), 1),
            1,
        )

    return jsonify(
        {
            "summary": {
                "avg_mastery": avg_mastery,
                "mastered_kpis": mastered_kpis,
                "total_kpis_seen": len(mastery_rows),
                "questions_due": due_count,
                "streak_days": streak,
                "total_questions_answered": total_q_ans,
            },
            "progress": {
                "questions_answered": questions_answered_total,
                "questions_correct": questions_correct_total,
                "accuracy_pct": progress_accuracy,
                "avg_recent_response_ms": avg_recent_response_ms,
                "mastered_kpis": mastered_kpis,
                "questions_due": due_count,
                "streak_days": streak,
                "avg_mastery": avg_mastery,
                "history_count": len(history_rows),
            },
            "kpi_mastery": mastery_rows,
            "cluster_breakdown": cluster_breakdown,
            "weak_kpis": weak,
            "strong_kpis": strong,
            "recent_sessions": sessions,
            "daily_activity": daily,
            "question_type_breakdown": question_type_breakdown,
            "question_history": history_rows,
        }
    )


@learn_bp.get("/api/learn/due")
def learn_due_questions():
    """
    Return questions due for review for the current user,
    optionally filtered by event_id.
    Ordered by overdue amount (most overdue first).
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    token = get_bearer_token()
    user_id = user.get("id", "")
    event_id = canonical_event_id(request.args.get("event_id"))
    if not event_id:
        return jsonify({"error": "Supported event_id is required"}), 400
    limit = min(int(request.args.get("limit", "50")), 200)

    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fetch due SRS states
    due_params: dict = {
        "user_id": f"eq.{user_id}",
        "event_id": f"eq.{event_id}",
        "next_review": f"lte.{now_iso}",
        "select": "question_id,ease_factor,interval_days,repetitions,next_review,total_attempts,correct_attempts",
        "order": "next_review.asc",
        "limit": str(limit),
    }
    _, srs_rows = supabase_rest_request(
        "/user_srs_state",
        token=token,
        params=due_params,
        prefer="",
    )
    srs_rows = srs_rows if isinstance(srs_rows, list) else []
    if not srs_rows:
        return jsonify({"questions": [], "total": 0})

    # Fetch the actual question content
    q_ids = [r["question_id"] for r in srs_rows]
    id_list = ",".join(q_ids)
    _, q_rows = _supabase_svc(
        "/kpi_questions",
        params={
            "id": f"in.({id_list})",
            "select": "id,kpi_code,kpi_text,kpi_cluster,deca_cluster,event_id,question_text,choices,correct_index,explanation,question_type,quality_state,answer_reveal",
        },
    )
    q_rows = q_rows if isinstance(q_rows, list) else []

    # Filter by event if requested
    if event_id:
        q_rows = [q for q in q_rows if q.get("event_id") == event_id]

    # Join SRS state onto each question
    srs_by_qid = {r["question_id"]: r for r in srs_rows}
    questions = []
    for q in q_rows:
        srs = srs_by_qid.get(q["id"], {})
        questions.append(
            {
                "id": q["id"],
                "text": q.get("question_text", ""),
                "choices": q.get("choices", []),
                "correct": q.get("correct_index", 0),
                "explanation": q.get("explanation", ""),
                "kpi_code": q.get("kpi_code", ""),
                "kpi_text": q.get("kpi_text", ""),
                "cluster": q.get("kpi_cluster", ""),
                "deca_cluster": q.get("deca_cluster", ""),
                "event_id": q.get("event_id", ""),
                "question_type": q.get("question_type", "recognition"),
                "srs": {
                    "ease_factor": srs.get("ease_factor", 2.5),
                    "interval_days": srs.get("interval_days", 0),
                    "repetitions": srs.get("repetitions", 0),
                    "next_review": srs.get("next_review"),
                    "accuracy": round(
                        srs.get("correct_attempts", 0)
                        / max(srs.get("total_attempts", 1), 1)
                        * 100,
                        1,
                    ),
                },
            }
        )

    return jsonify({"questions": questions, "total": len(questions)})


@learn_bp.post("/api/learn/roleplay-prompt")
def learn_roleplay_prompt():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    kpis = body.get("kpis", [])  # list of {code, text, cluster}
    event_id = canonical_event_id(body.get("event_id"))

    if not kpis or not event_id:
        return jsonify({"error": "No KPIs or supported event provided"}), 400
    allowed = {(k["code"], k["text"]): k for k in _load_all_kpis()[0] if k["event"] == event_id}
    if any((str(k.get("code", "")), str(k.get("text", ""))) not in allowed for k in kpis):
        return jsonify({"error": "Roleplay KPIs do not belong to the selected event"}), 400

    kpi_lines = "\n".join(f"- {k.get('code', '')}: {k.get('text', '')}" for k in kpis)

    prompt = f"""You are a DECA judge creating a roleplay scenario for a high school business competition.

Create a realistic business scenario that lets a student demonstrate understanding of these 7 DECA performance indicators:
{kpi_lines}

The scenario should be a real business situation (consulting, management, sales, finance, etc.)
that naturally requires addressing all or most of these indicators.

Return ONLY valid JSON:
{{
  "scenario": "You are a [specific role] at [specific company/situation]. [2-3 sentences describing the business problem or situation]. Your task is to [what they must do/address].",
  "role": "The student's specific role (e.g. 'Financial Consultant')",
  "focus": "One sentence on what aspect to emphasize in the response"
}}"""

    result, err = call_json_with_fallback(
        prompt, priority="student", max_tokens=512, temperature=0.9
    )
    if err:
        return jsonify({"error": err}), 500

    try:
        return jsonify(validate_roleplay_prompt(result))
    except LearnContentError as error:
        return jsonify({"error": "Model returned invalid roleplay content.", "detail": str(error)}), 502


@learn_bp.post("/api/learn/grade")
def learn_grade():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    scenario = (body.get("scenario") or "").strip()
    response_text = (body.get("response") or "").strip()
    kpis = body.get("kpis", [])
    event_id = canonical_event_id(body.get("event_id"))
    session_id = str(body.get("session_id") or "").strip()

    if not scenario or not response_text or not event_id or not session_id:
        return jsonify({"error": "Missing scenario, response, session, or supported event"}), 400
    allowed_codes = {k["code"] for k in _load_all_kpis()[0] if k["event"] == event_id}
    kpi_codes = [str(k.get("code") or "") for k in kpis]
    if not kpi_codes or any(code not in allowed_codes for code in kpi_codes):
        return jsonify({"error": "Roleplay KPIs do not belong to the selected event"}), 400

    kpi_lines = "\n".join(f"- {k.get('code', '')}: {k.get('text', '')}" for k in kpis)

    prompt = f"""You are a DECA competition judge grading a student's roleplay response.

SCENARIO GIVEN TO STUDENT:
{scenario}

PERFORMANCE INDICATORS they should address:
{kpi_lines}

STUDENT'S RESPONSE:
{response_text}

Grade this response. Return ONLY valid JSON — no markdown, no extra text:
{{
  "score": 7,
  "grade": "B",
  "overall": "2-sentence overall assessment of the response quality.",
  "strengths": [
    "Specific strength 1",
    "Specific strength 2"
  ],
  "improvements": [
    "Specific improvement 1",
    "Specific improvement 2"
  ],
  "kpi_coverage": [
    {{"code": "XX:000", "addressed": true, "note": "How they addressed it or why it was missed"}}
  ]
}}

Scoring guide: 9-10=Excellent, 7-8=Good, 5-6=Adequate, 3-4=Needs work, 1-2=Poor.
Grade letter: 9-10=A, 7-8=B, 5-6=C, 3-4=D, 1-2=F."""

    result, err = call_json_with_fallback(
        prompt, priority="student", max_tokens=1600, temperature=0.3
    )
    if err:
        return jsonify({"error": err}), 500

    try:
        result = validate_roleplay_grade(result, kpi_codes)
    except LearnContentError as error:
        return jsonify({"error": "Model returned an invalid roleplay grade.", "detail": str(error)}), 502

    token = get_bearer_token()
    user_id = user.get("id", "")
    status, saved = supabase_rest_request(
        "/user_study_sessions", method="PATCH", token=token,
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}", "event_id": f"eq.{event_id}"},
        payload={"roleplay_score": result["score"], "roleplay_result": {"scenario": scenario, "response": response_text, **result}},
        prefer="return=representation",
    )
    if status not in (200, 204) or not isinstance(saved, list) or not saved:
        return jsonify({"error": "Roleplay grade could not be saved."}), 502
    return jsonify(result)


# Eval routes register themselves on learn_bp — must import after learn_bp is defined.
from app.routes.api import eval as _eval_module  # noqa: E402,F401
