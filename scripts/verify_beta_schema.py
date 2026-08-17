"""Fail fast when the beta backend/schema contract drifts.

This static check runs in CI without credentials. After migrations are applied,
run supabase/verify_beta_schema.sql against the target project for live catalog
verification.
"""

from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "supabase/migrations").glob("*.sql"))).lower()

REQUIRED = {
    "profiles": ("default_event_id", "competition_tier", "default_cluster"),
    "deca_events": ("id", "name", "cluster", "is_beta"),
    "kpi_questions": ("event_id", "kpi_code", "question_type", "question_slot"),
    "responses": ("user_id", "event_id", "session_id", "question_id", "selected_index", "idempotency_hash"),
    "user_srs_state": ("user_id", "event_id", "question_id", "next_review"),
    "user_kpi_mastery": ("user_id", "event_id", "kpi_code", "mastery_score"),
    "user_study_sessions": ("user_id", "event_id", "ar_answers", "roleplay_result"),
    "user_daily_activity": ("user_id", "event_id", "activity_date"),
    "user_lesson_completions": ("user_id", "event_id", "kpi_code", "lesson_version", "completed_at"),
    "user_adaptive_state": ("user_id", "event_id", "state", "computed_at"),
    "user_today_plans": ("user_id", "event_id", "plan_date", "time_budget_minutes", "tasks", "rationale"),
    "kpi_inference_state": ("user_id", "event_id", "kpi_code"),
    "user_timing_profile": ("user_id", "event_id", "question_type", "kpi_cluster"),
    "learning_evaluation_log": ("user_id", "event_id", "kpi_code"),
    "system_announcements": ("title", "message", "type"),
    "question_reports": ("user_id", "question_id", "reason"),
}

errors = []
for table, columns in REQUIRED.items():
    if f"table if not exists public.{table}" not in MIGRATIONS and f"table if not exists {table}" not in MIGRATIONS:
        errors.append(f"missing table migration: {table}")
    for column in columns:
        if column.lower() not in MIGRATIONS:
            errors.append(f"missing expected column token: {table}.{column}")

contract = (ROOT / "app/events.py").read_text(encoding="utf-8")
event_module = runpy.run_path(str(ROOT / "app/events.py"))
frontend = (ROOT / "static/js/clusters.js").read_text(encoding="utf-8")
for event_id in ("accounting_application_series", "business_finance_series", "financial_services_tdm"):
    if event_id not in contract or event_id not in frontend or event_id not in MIGRATIONS:
        errors.append(f"canonical event missing from a contract layer: {event_id}")
for function_name in ("record_beta_answer", "finish_beta_session"):
    if f"function public.{function_name}" not in MIGRATIONS:
        errors.append(f"missing transactional Learn function: {function_name}")
if event_module["canonical_event_id"]("Financial Services Team Decision Making") != "financial_services_tdm":
    errors.append("Financial Services TDM canonical mapping is incorrect")

opening = (ROOT / "static/js/opening.js").read_text(encoding="utf-8")
if "body: JSON.stringify({ cluster:" in opening or "OPENING_STATE.user.cluster" in opening:
    errors.append("opening still uses the legacy cluster field")
if 'addEventListener("pointerdown", chooseTier)' in opening:
    errors.append("tier selection still has the duplicate pointerdown handler")

admin = (ROOT / "app/routes/admin.py").read_text(encoding="utf-8")
logs_block = admin[admin.index("def admin_logs"):admin.index("#", admin.index("def admin_logs") + 20)]
if '"kpi_code,questions_answered' in logs_block:
    errors.append("admin logs still selects user_study_sessions.kpi_code")

if errors:
    raise SystemExit("Beta schema verification failed:\n- " + "\n- ".join(errors))
print(f"Beta schema contract verified: {len(REQUIRED)} tables, 3 events.")
