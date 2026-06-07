from flask import g, jsonify, request

from ..db import supabase_rest_request
import json
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..ai import call_gemini, call_gemini_json, call_groq
from ..auth_utils import get_bearer_token, get_current_user
from ..db import supabase_rest_request
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
    _get_kpi_meta,
)
learn_bp = Blueprint("learn", __name__)

@learn_bp.get("/api/kpis")
def api_kpis():
    all_kpis, events = _load_all_kpis()
    event_filter = request.args.get("event", "").strip()
    if event_filter:
        all_kpis = [k for k in all_kpis if k["event"] == event_filter]

    # Filter to only due/unstarted KPIs if the user is logged in
    user = get_current_user()
    if user:
        token = get_bearer_token()
        event_id = event_filter or (events[0]["id"] if events else "")
        if event_id:
            all_kpis = get_due_kpis(user["id"], token, event_id)

    return jsonify({"kpis": all_kpis, "events": events})

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
    event_id = (body.get("event_id") or "").strip()

    if not code or not text:
        return jsonify({"error": "Missing required fields: code, text"}), 400

    prompt = f"""You are a DECA exam coach creating study materials for high school business students.

Generate educational content for this DECA Performance Indicator (KPI):
- Code: {code}
- KPI: {text}
- Subject Cluster: {cluster}
- Standard: {standard}

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
    "explanation": "2-3 paragraphs for a high school student. Plain language, real-world examples, why it matters.",
    "bullets": ["Key insight 1", "Key insight 2", "Key insight 3"],
    "table": [
      {{"term": "Term 1", "definition": "Brief definition"}},
      {{"term": "Term 2", "definition": "Brief definition"}},
      {{"term": "Term 3", "definition": "Brief definition"}}
    ]
  }},
  "questions": [
    {{
      "text": "The full question text",
      "choices": [
        "Choice A — complete answer text",
        "Choice B — complete answer text",
        "Choice C — complete answer text",
        "Choice D — complete answer text"
      ],
      "correct": 0,
      "explanation": "Choice A is correct because [specific reason]. Choice B is wrong because [reason]. Choice C is wrong because [reason]. Choice D is wrong because [reason].",
      "kpi_code": "{code}",
      "kpi_text": "{text}",
      "cluster": "{cluster}",
      "deca_cluster": "{deca_cluster or "Finance"}"
    }}
  ]
}}

For the "questions" array generate EXACTLY 10 multiple-choice questions about this KPI.
Requirements for each question:
  1. A clear, specific question stem.
  2. Four plausible answer choices (A–D) — only one correct.
  3. A brief explanation: why the correct choice is right.
  4. The kpi_code, kpi_text, cluster, and deca_cluster fields must be present.
Vary difficulty across the 10 questions (mix of recall, application, analysis).
Distribute the correct answer index (0–3) roughly evenly across the 10 questions."""

    # Try Groq first; fall back to Gemini if unavailable.
    # max_tokens kept under 4K to stay within free-tier 12K TPM on Groq.
    result, err = call_groq([{"role": "user", "content": prompt}], max_tokens=3500)
    if err:
        result, err = call_gemini_json(prompt, max_tokens=3500)
    if err:
        return jsonify({"error": err}), 500

    if (
        not isinstance(result, dict)
        or "concept" not in result
        or "questions" not in result
    ):
        return jsonify(
            {"error": "Groq returned unexpected format. Please try again."}
        ), 500

    # Override metadata fields with authoritative values from the request
    raw_questions = result.get("questions", [])
    for q in raw_questions:
        q["kpi_code"] = code
        q["kpi_text"] = text
        q["cluster"] = cluster
        q["deca_cluster"] = deca_cluster

    # Persist to Supabase and attach UUIDs
    saved = _save_questions_supabase(
        raw_questions, code, text, cluster, deca_cluster, event_id
    )
    # Map UUID back onto each question by position or text match
    if saved:
        by_text = {s["text"]: s["id"] for s in saved}
        for q in raw_questions:
            q["id"] = by_text.get(q.get("text", ""), "")

    result["questions"] = raw_questions
    return jsonify(result)


@learn_bp.get("/api/learn/questions")
def learn_get_questions():
    """Return questions from Supabase for a KPI, annotated with the user's mastery."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    kpi_code = request.args.get("kpi_code", "").strip()
    if not kpi_code:
        return jsonify({"error": "Missing kpi_code"}), 400

    token = get_bearer_token()
    user_id = user.get("id", "")

    rows = _fetch_kpi_questions(kpi_code)
    questions = [_normalise_db_question(r) for r in rows]

    # Fetch this user's answer history for these question IDs
    q_ids = [q["id"] for q in questions if q["id"]]
    answered_correctly: set[str] = set()
    if q_ids and token:
        # PostgREST "in" filter: ?question_id=in.(uuid1,uuid2,...)
        id_list = ",".join(q_ids)
        status, results = supabase_rest_request(
            "/user_question_results",
            token=token,
            params={
                "user_id": f"eq.{user_id}",
                "question_id": f"in.({id_list})",
                "correct": "eq.true",
                "select": "question_id",
            },
            prefer="",
        )
        if status == 200 and isinstance(results, list):
            answered_correctly = {r["question_id"] for r in results}

    for q in questions:
        q["mastered"] = q["id"] in answered_correctly

    return jsonify({"questions": questions, "total": len(questions)})


@learn_bp.post("/api/learn/answer")
def learn_record_answer():
    """
    Record a question answer.
    Runs SM-2, updates user_srs_state, recomputes KPI mastery, updates daily activity.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    question_id = (body.get("question_id") or "").strip()
    correct = bool(body.get("correct", False))
    # quality: caller can pass 0-5; we default to 4=correct / 1=wrong
    quality = int(body.get("quality", 4 if correct else 1))
    quality = max(0, min(5, quality))
    kpi_code = (body.get("kpi_code") or "").strip()
    kpi_cluster = (body.get("cluster") or "").strip()
    deca_cluster = (body.get("deca_cluster") or "").strip()
    event_id = (body.get("event_id") or "").strip()

    if not question_id:
        return jsonify({"error": "Missing question_id"}), 400

    token = get_bearer_token()
    user_id = user.get("id", "")

    # ── 1. Load current SRS state ─────────────────────────────────────────────
    _, rows = supabase_rest_request(
        "/user_srs_state",
        token=token,
        params={
            "user_id": f"eq.{user_id}",
            "question_id": f"eq.{question_id}",
            "select": "*",
            "limit": "1",
        },
        prefer="",
    )
    cur = rows[0] if isinstance(rows, list) and rows else {}

    ef = float(cur.get("ease_factor", 2.5))
    iv = int(cur.get("interval_days", 0))
    reps = int(cur.get("repetitions", 0))
    total = int(cur.get("total_attempts", 0))
    correct_count = int(cur.get("correct_attempts", 0))

    # ── 2. SM-2 ───────────────────────────────────────────────────────────────
    new_ef, new_iv, new_reps, next_review = compute_sm2(ef, iv, reps, quality)
    new_total = total + 1
    new_correct = correct_count + (1 if correct else 0)

    # ── 3. Upsert SRS state ───────────────────────────────────────────────────
    srs_payload = {
        "user_id": user_id,
        "question_id": question_id,
        "ease_factor": new_ef,
        "interval_days": new_iv,
        "repetitions": new_reps,
        "last_quality": quality,
        "last_reviewed": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "next_review": next_review,
        "total_attempts": new_total,
        "correct_attempts": new_correct,
    }
    supabase_rest_request(
        "/user_srs_state",
        method="POST",
        token=token,
        payload=srs_payload,
        prefer="resolution=merge-duplicates,return=minimal",
    )

    # ── 4. Recompute KPI mastery (if kpi_code known) ──────────────────────────
    mastery_payload: dict = {}
    if kpi_code:
        mastery_payload = _update_kpi_mastery(
            user_id, token, kpi_code, kpi_cluster, deca_cluster, event_id
        )

    # ── 5. Daily activity ─────────────────────────────────────────────────────
    _upsert_daily_activity(
        user_id,
        token,
        q_answered=1,
        q_correct=(1 if correct else 0),
    )

    return jsonify(
        {
            "ok": True,
            "srs": {
                "ease_factor": new_ef,
                "interval_days": new_iv,
                "next_review": next_review,
                "repetitions": new_reps,
            },
            "mastery_score": mastery_payload.get("mastery_score"),
        }
    )


@learn_bp.post("/api/learn/session/start")
def learn_session_start():
    """Create a session record and return its id."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    event_id = (body.get("event_id") or "").strip()
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
    kpis_studied = int(body.get("kpis_studied", 0))
    questions_answered = int(body.get("questions_answered", 0))
    questions_correct = int(body.get("questions_correct", 0))
    vocab_total = int(body.get("vocab_total", 0))
    vocab_correct = int(body.get("vocab_correct", 0))
    roleplay_score = body.get("roleplay_score")  # int or None
    duration_seconds = int(body.get("duration_seconds", 0))
    ar_answers = body.get("ar_answers", [])  # list of {kpi_code, kpi_text, answer, timestamp}

    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    token = get_bearer_token()
    user_id = user.get("id", "")

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

    supabase_rest_request(
        f"/user_study_sessions",
        method="PATCH",
        token=token,
        payload=payload,
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
        prefer="return=minimal",
    )

    # Update daily activity with session-level deltas
    _upsert_daily_activity(
        user_id,
        token,
        kpis_delta=kpis_studied,
        minutes=duration_seconds // 60,
    )

    return jsonify({"ok": True, "accuracy_pct": acc})


@learn_bp.get("/api/learn/analytics")
def learn_analytics():
    """
    Full mastery + session analytics for the home dashboard.
    Returns: summary, per-KPI mastery, cluster breakdown, recent sessions,
             30-day activity heatmap, streak.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    token = get_bearer_token()
    user_id = user.get("id", "")
    event_id = request.args.get("event_id", "").strip()

    # KPI mastery rows
    mastery_params: dict = {"user_id": f"eq.{user_id}", "select": "*"}
    if event_id:
        mastery_params["event_id"] = f"eq.{event_id}"
    _, mastery_rows = supabase_rest_request(
        "/user_kpi_mastery",
        token=token,
        params=mastery_params,
        prefer="",
    )
    mastery_rows = mastery_rows if isinstance(mastery_rows, list) else []

    # Recent sessions (last 20)
    _, sessions = supabase_rest_request(
        "/user_study_sessions",
        token=token,
        params={
            "user_id": f"eq.{user_id}",
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
        "next_review": f"lte.{now_iso}",
        "select": "question_id",
    }
    _, due_rows = supabase_rest_request(
        "/user_srs_state",
        token=token,
        params=due_params,
        prefer="",
    )
    due_count = len(due_rows) if isinstance(due_rows, list) else 0

    # ── Aggregates ────────────────────────────────────────────────────────────
    avg_mastery = round(
        sum(m.get("mastery_score", 0) for m in mastery_rows)
        / max(len(mastery_rows), 1),
        1,
    )
    mastered_kpis = sum(
        1 for m in mastery_rows if float(m.get("mastery_score", 0)) >= 80
    )
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

    # Weak / strong KPIs
    weak = sorted(mastery_rows, key=lambda m: m.get("mastery_score", 0))[:5]
    strong = sorted(
        mastery_rows, key=lambda m: m.get("mastery_score", 0), reverse=True
    )[:5]

    streak = _compute_streak(daily)

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
            "kpi_mastery": mastery_rows,
            "cluster_breakdown": cluster_breakdown,
            "weak_kpis": weak,
            "strong_kpis": strong,
            "recent_sessions": sessions,
            "daily_activity": daily,
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
    event_id = request.args.get("event_id", "").strip()
    limit = min(int(request.args.get("limit", "50")), 200)

    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fetch due SRS states
    due_params: dict = {
        "user_id": f"eq.{user_id}",
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
            "select": "id,kpi_code,kpi_text,kpi_cluster,deca_cluster,event_id,question_text,choices,correct_index,explanation",
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

    if not kpis:
        return jsonify({"error": "No KPIs provided"}), 400

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

    result, err = call_groq([{"role": "user", "content": prompt}])
    if err:
        result, err = call_gemini_json(prompt, max_tokens=512, temperature=0.9)
    if err:
        return jsonify({"error": err}), 500

    return jsonify(result)


@learn_bp.post("/api/learn/grade")
def learn_grade():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    scenario = (body.get("scenario") or "").strip()
    response_text = (body.get("response") or "").strip()
    kpis = body.get("kpis", [])

    if not scenario or not response_text:
        return jsonify({"error": "Missing scenario or response"}), 400

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

    text, err = call_gemini(prompt)
    if err:
        return jsonify({"error": err}), 500

    # Strip markdown code fences Gemini sometimes adds
    clean = text.strip()
    if clean.startswith("```"):
        parts = clean.split("```")
        clean = parts[1] if len(parts) > 1 else clean
        if clean.startswith("json"):
            clean = clean[4:]
    clean = clean.strip()

    try:
        result = json.loads(clean)
    except Exception:
        return jsonify(
            {"error": "Failed to parse grading response", "raw": text[:500]}
        ), 500

    return jsonify(result)
