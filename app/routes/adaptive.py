"""Deterministic, privacy-minimal adaptive state and daily study planning."""

from datetime import date, datetime, timezone
from statistics import median

from flask import Blueprint, jsonify, request

from ..adaptive_planner import build_plan, refresh_progress
from ..auth_utils import get_current_user
from ..events import canonical_event_id
from ..learn_helpers import _load_all_kpis, _supabase_svc
from ..student_evidence import first_attempts
from .practice import _analytics, _data

adaptive_bp = Blueprint("adaptive", __name__)


def _rows(path, **params):
    _, rows = _supabase_svc(path, params=params)
    return rows if isinstance(rows, list) else []


def _clamp(value, low, high):
    return max(low, min(high, int(value)))


def _derive(user_id, event_id):
    profile_rows = _rows("/profiles", id=f"eq.{user_id}", select="study_goal_minutes,competition_tier", limit="1")
    profile = profile_rows[0] if profile_rows else {}
    catalog = [k for k in _load_all_kpis()[0] if k.get("event") == event_id]
    completions = _rows("/user_lesson_completions", user_id=f"eq.{user_id}", event_id=f"eq.{event_id}", lesson_version="eq.4", select="kpi_code,completed_at", limit="10000")
    mastery = _rows("/user_kpi_mastery", user_id=f"eq.{user_id}", event_id=f"eq.{event_id}", select="kpi_code,kpi_cluster,mastery_score", limit="10000")
    sessions = _rows("/user_study_sessions", user_id=f"eq.{user_id}", event_id=f"eq.{event_id}", select="duration_seconds,ended_at,kpis_studied", order="started_at.desc", limit="20")
    questions, responses, _, due_ids = _data(user_id, event_id)
    completion_codes = {r.get("kpi_code") for r in completions if r.get("kpi_code")}
    studied_mastery = [{"kpi_code": code, "kpi_cluster": next((k.get("cluster") for k in catalog if k.get("code") == code), "Other")} for code in completion_codes]
    topic_analysis = _analytics(questions, responses, catalog, studied_mastery)
    evidence = first_attempts(responses)
    total = len({k.get("code") for k in catalog if k.get("code")})
    studied = len(completion_codes)
    coverage_pct = round(100 * studied / total) if total else 0
    valid_durations = [int(s.get("duration_seconds") or 0) for s in sessions if int(s.get("duration_seconds") or 0) >= 60]
    preferred_minutes = round(median(valid_durations) / 60) if len(valid_durations) >= 3 else int(profile.get("study_goal_minutes") or 20)
    qualified = sorted((x for x in topic_analysis if x.get("qualified")), key=lambda x: x.get("accuracy") if x.get("accuracy") is not None else 101)
    correct = evidence["correct"]
    weakest = qualified[0] if qualified and (qualified[0].get("accuracy") or 100) < 80 else None
    qmap = {q["id"]: q for q in questions}
    due_by_topic = {}
    for question_id in due_ids:
        topic = (qmap.get(question_id) or {}).get("kpi_cluster") or "Other"
        due_by_topic[topic] = due_by_topic.get(topic, 0) + 1
    active_sets = _rows("/practice_sets", user_id=f"eq.{user_id}", event_id=f"eq.{event_id}", status="eq.active", select="id,title,current_index,question_count", order="created_at.desc", limit="1")
    active = active_sets[0] if active_sets else None
    kpi_samples = [int(s.get("duration_seconds") or 0) / max(1, int(s.get("kpis_studied") or 0)) / 60 for s in sessions if int(s.get("duration_seconds") or 0) >= 60 and int(s.get("kpis_studied") or 0) > 0]
    response_samples = [int(r.get("response_time_ms") or 0) / 1000 for r in responses[-50:] if int(r.get("response_time_ms") or 0) >= 1000]
    first_rows = evidence["rows"]
    application_rows = [r for r in first_rows if r.get("question_type") == "application"]
    recognition_rows = [r for r in first_rows if r.get("question_type") != "application"]
    state = {
        "median_session_active_minutes": round(median(valid_durations) / 60, 1) if len(valid_durations) >= 3 else None,
        "session_duration_sample_count": len(valid_durations),
        "median_kpi_minutes": round(median(kpi_samples), 1) if len(kpi_samples) >= 3 else 6,
        "kpi_timing_sample_count": len(kpi_samples),
        "median_question_seconds": round(median(response_samples), 1) if len(response_samples) >= 10 else 45,
        "question_timing_sample_count": len(response_samples),
        "application_attempt_count": len(application_rows),
        "application_accuracy": round(100 * sum(bool(r.get("correct")) for r in application_rows) / len(application_rows)) if application_rows else None,
        "recognition_attempt_count": len(recognition_rows),
        "recent_session_completion_rate": round(sum(bool(s.get("ended_at")) for s in sessions) / len(sessions), 3) if sessions else None,
        "qualified_strongest_topic": max(qualified, key=lambda x: x.get("accuracy") or 0).get("topic") if qualified else None,
        "qualified_weakest_topic": {k: weakest.get(k) for k in ("topic", "accuracy", "attempts", "kpis_studied", "kpis_total", "coverage_pct")} if weakest else None,
        "recent_question_accuracy": round(correct / evidence["attempts"], 3) if evidence["attempts"] else None,
        "competition_days_remaining": None,
        "unfinished_practice": active,
        "coverage": {"studied": studied, "total": total, "percent": coverage_pct},
        "practice_correct_count": correct,
        "practice_attempt_count": evidence["attempts"],
        "practice_retry_count": evidence["retry_count"],
        "due_review_count": len(due_ids),
        "due_reviews_by_topic": due_by_topic,
        "evidence_thresholds": {"topic_coverage_percent": 50, "topic_question_attempts": 10},
    }
    return state, profile, responses


@adaptive_bp.route("/api/adaptive/today", methods=["GET", "POST"])
def today_plan():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    event_id = canonical_event_id(body.get("event_id") or request.args.get("event_id"))
    if not event_id:
        return jsonify({"error": "Supported event_id is required"}), 400
    state, profile, _ = _derive(user["id"], event_id)
    requested_budget = body.get("time_available_today")
    normal_budget = _clamp(profile.get("study_goal_minutes") or state["median_session_active_minutes"] or 20, 3, 90)
    budget = _clamp(requested_budget or normal_budget, 3, 90)
    regenerate = request.method == "POST" or requested_budget is not None
    today = date.today().isoformat()
    saved = _rows("/user_today_plans", user_id=f"eq.{user['id']}", event_id=f"eq.{event_id}", plan_date=f"eq.{today}", select="*", limit="1")
    cached_inputs = (saved[0].get("inputs") or {}) if saved else {}
    cached_tasks = (saved[0].get("tasks") or []) if saved else []
    cache_is_current = cached_inputs.get("planner_version") == 3 and all(task.get("activity_type") for task in cached_tasks)
    if saved and not regenerate and cache_is_current:
        row = saved[0]
        stored_inputs = row.get("inputs") or {}
        plan = {"date": today, "eventId": event_id, "time_budget_minutes": row["time_budget_minutes"], "tasks": row.get("tasks") or [], "reason_codes": stored_inputs.get("reason_codes") or [], "reason_details": stored_inputs.get("reason_details") or []}
    else:
        plan = build_plan(state, event_id, budget)
    plan = refresh_progress(plan, state)
    inputs = {"planner_version": 3, "coverage": state["coverage"], "due_reviews": state["due_review_count"], "practice_attempts": state["practice_attempt_count"]}
    _supabase_svc("/user_adaptive_state", method="POST", payload={"user_id": user["id"], "event_id": event_id, "state": state, "computed_at": datetime.now(timezone.utc).isoformat()}, params={"on_conflict": "user_id,event_id"}, prefer="resolution=merge-duplicates,return=minimal")
    _supabase_svc("/user_today_plans", method="POST", payload={"user_id": user["id"], "event_id": event_id, "plan_date": today, "time_budget_minutes": plan["time_budget_minutes"], "tasks": plan["tasks"], "rationale": " | ".join(plan.get("reason_details") or []), "inputs": {**inputs, "reason_codes": plan.get("reason_codes", []), "reason_details": plan.get("reason_details", [])}, "updated_at": datetime.now(timezone.utc).isoformat()}, params={"on_conflict": "user_id,event_id,plan_date"}, prefer="resolution=merge-duplicates,return=minimal")
    return jsonify({"adaptive_state": state, "plan": plan, "normal_time_budget": normal_budget})
