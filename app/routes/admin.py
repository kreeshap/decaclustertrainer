from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from ..auth_utils import get_current_user, is_admin
from ..db import supabase_admin_request
from ..learn_helpers import _load_all_kpis, _supabase_svc, KPI_DIR, _save_questions_supabase
from werkzeug.utils import secure_filename
import json
from pathlib import Path

admin_bp = Blueprint("admin", __name__)


def require_admin():
    """Returns (user, error_response).

    Usage::

        user, err = require_admin()
        if err:
            return err
    """
    user = get_current_user()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if not is_admin(user):
        return None, (jsonify({"error": "Forbidden"}), 403)
    return user, None


# ─── Dashboard ────────────────────────────────────────────────────────────────


@admin_bp.get("/api/admin/dashboard")
def admin_dashboard():
    _, err = require_admin()
    if err:
        return err

    # Users total — fetch first page with high per_page to get a count
    users_total = 0
    u_status, u_data = supabase_admin_request("/admin/users?page=1&per_page=1000")
    if u_status == 200 and isinstance(u_data, dict):
        users_total = len(u_data.get("users", []))

    # Questions total (select only id to minimise payload)
    q_status, q_data = _supabase_svc(
        "/kpi_questions", params={"select": "id", "limit": "10000"}
    )
    questions_total = len(q_data) if q_status == 200 and isinstance(q_data, list) else 0

    # KPIs total — loaded from JSON files
    kpis, _ = _load_all_kpis()
    kpis_total = len(kpis)

    # Sessions today
    today = date.today().isoformat()
    s_status, s_data = _supabase_svc(
        "/user_study_sessions",
        params={"select": "id", "started_at": f"gte.{today}T00:00:00Z"},
    )
    sessions_today = len(s_data) if s_status == 200 and isinstance(s_data, list) else 0

    # Recent activity — last 10 rows
    a_status, a_data = _supabase_svc(
        "/user_daily_activity",
        params={"select": "*", "order": "activity_date.desc", "limit": "10"},
    )
    recent_activity = a_data if a_status == 200 and isinstance(a_data, list) else []

    return jsonify(
        {
            "users_total": users_total,
            "questions_total": questions_total,
            "kpis_total": kpis_total,
            "sessions_today": sessions_today,
            "recent_activity": recent_activity,
        }
    )


# ─── Users ────────────────────────────────────────────────────────────────────


@admin_bp.get("/api/admin/users")
def admin_list_users():
    _, err = require_admin()
    if err:
        return err

    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 50))
    search = request.args.get("search", "").strip().lower()

    u_status, u_data = supabase_admin_request(
        f"/admin/users?page={page}&per_page={limit}"
    )
    if u_status != 200 or not isinstance(u_data, dict):
        return jsonify({"error": "Failed to fetch users", "detail": u_data}), u_status

    users = u_data.get("users", [])
    if search:
        users = [u for u in users if search in (u.get("email") or "").lower()]

    result = [
        {
            "id": u.get("id"),
            "email": u.get("email"),
            "display_name": (
                (u.get("user_metadata") or {}).get("display_name")
                or (u.get("user_metadata") or {}).get("full_name")
                or ""
            ),
            "created_at": u.get("created_at"),
            "last_sign_in_at": u.get("last_sign_in_at"),
            "banned_until": u.get("banned_until"),
        }
        for u in users
    ]

    return jsonify({"users": result, "total": len(result)})


@admin_bp.post("/api/admin/users/<user_id>/suspend")
def admin_suspend_user(user_id):
    _, err = require_admin()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    suspend = bool(body.get("suspend", True))
    payload = {"ban_duration": "876600h" if suspend else "none"}

    status, data = supabase_admin_request(
        f"/admin/users/{user_id}", method="PUT", payload=payload
    )
    if status not in (200, 204):
        return jsonify({"error": "Failed to update user", "detail": data}), status

    return jsonify({"ok": True, "suspended": suspend})


@admin_bp.delete("/api/admin/users/<user_id>")
def admin_delete_user(user_id):
    _, err = require_admin()
    if err:
        return err

    status, data = supabase_admin_request(f"/admin/users/{user_id}", method="DELETE")
    if status not in (200, 204):
        return jsonify({"error": "Failed to delete user", "detail": data}), status

    return jsonify({"ok": True})


# ─── Questions ────────────────────────────────────────────────────────────────


@admin_bp.get("/api/admin/questions")
def admin_list_questions():
    _, err = require_admin()
    if err:
        return err

    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 50))
    kpi_code = request.args.get("kpi_code", "").strip()
    search = request.args.get("search", "").strip().lower()

    offset = (page - 1) * limit
    params: dict = {
        "select": "id,kpi_code,question_text,correct_index,created_at",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if kpi_code:
        params["kpi_code"] = f"eq.{kpi_code}"

    status, data = _supabase_svc("/kpi_questions", params=params)
    if status != 200 or not isinstance(data, list):
        return jsonify({"error": "Failed to fetch questions", "detail": data}), status

    if search:
        data = [q for q in data if search in (q.get("question_text") or "").lower()]

    return jsonify({"questions": data, "total": len(data)})


@admin_bp.delete("/api/admin/questions/<question_id>")
def admin_delete_question(question_id):
    _, err = require_admin()
    if err:
        return err

    status, data = _supabase_svc(
        "/kpi_questions",
        method="DELETE",
        params={"id": f"eq.{question_id}"},
        prefer="return=minimal",
    )
    if status not in (200, 204):
        return jsonify({"error": "Failed to delete question", "detail": data}), status

    return jsonify({"ok": True})


# ─── KPIs ─────────────────────────────────────────────────────────────────────


@admin_bp.get("/api/admin/kpis")
def admin_list_kpis():
    _, err = require_admin()
    if err:
        return err

    kpis, events = _load_all_kpis()
    return jsonify({"kpis": kpis, "events": events})


# ─── KPI Import / Review Stubs ─────────────────────────────────────────────────


@admin_bp.post("/api/admin/kpis/import")
def admin_import_kpis():
    _, err = require_admin()
    if err:
        return err
    # Support file upload (multipart/form-data) or JSON body.
    uploaded = request.files.get("file") or request.files.get("kpi_file")
    if uploaded:
        filename = secure_filename(uploaded.filename or "import.json")
        # Ensure KPI_DIR exists
        Path(KPI_DIR).mkdir(parents=True, exist_ok=True)
        dest = Path(KPI_DIR) / filename
        try:
            uploaded.save(str(dest))
            # Parse and save questions if the file contains them
            file_content = json.load(open(str(dest), 'r'))
            if isinstance(file_content, dict) and 'questions' in file_content:
                q_list = file_content.get('questions', [])
                for q in q_list:
                    if q.get('kpi_code'):
                        _save_questions_supabase(
                            [q],
                            q.get('kpi_code'),
                            q.get('kpi_text', ''),
                            q.get('kpi_cluster', ''),
                            q.get('deca_cluster', ''),
                            q.get('event_id', ''),
                        )
        except Exception as exc:
            return jsonify({"error": "Failed to save file", "detail": str(exc)}), 500
        # Re-load KPIs to give feedback on current total
        kpis, events = _load_all_kpis()
        return jsonify({"ok": True, "saved_file": filename, "kpis_total": len(kpis)})

    body = request.get_json(silent=True) or {}
    kpis = body.get("kpis") or []
    return jsonify({"ok": True, "imported": len(kpis)})


@admin_bp.post("/api/admin/questions/approve")
def admin_approve_question():
    _, err = require_admin()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    qid = body.get("question_id") or ""
    approve = bool(body.get("approve", True))
    # Stub: pretend we toggled approved flag
    return jsonify({"ok": True, "question_id": qid, "approved": approve})


@admin_bp.post("/api/admin/scenarios/approve")
def admin_approve_scenario():
    _, err = require_admin()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    sid = body.get("scenario_id") or ""
    approve = bool(body.get("approve", True))
    return jsonify({"ok": True, "scenario_id": sid, "approved": approve})


# ─── Analytics ────────────────────────────────────────────────────────────────


@admin_bp.get("/api/admin/analytics")
def admin_analytics():
    _, err = require_admin()
    if err:
        return err

    # Top KPIs by questions_seen from user_kpi_mastery — fetch top 100 rows,
    # aggregate by kpi_code in Python, return top 10.
    tk_status, tk_data = _supabase_svc(
        "/user_kpi_mastery",
        params={
            "select": "kpi_code,questions_seen",
            "order": "questions_seen.desc",
            "limit": "100",
        },
    )
    if tk_status != 200 or not isinstance(tk_data, list):
        tk_data = []

    kpi_agg: dict[str, dict] = {}
    for row in tk_data:
        code = row.get("kpi_code") or ""
        if code not in kpi_agg:
            kpi_agg[code] = {"kpi_code": code, "questions_seen": 0}
        kpi_agg[code]["questions_seen"] += row.get("questions_seen", 0) or 0
    top_kpis = sorted(
        kpi_agg.values(), key=lambda x: x["questions_seen"], reverse=True
    )[:10]

    # Daily activity — last 30 days, aggregated across all users
    thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()
    da_status, da_data = _supabase_svc(
        "/user_daily_activity",
        params={
            "select": "activity_date,questions_answered,questions_correct,minutes_studied",
            "activity_date": f"gte.{thirty_days_ago}",
            "order": "activity_date.asc",
            "limit": "5000",
        },
    )
    if da_status != 200 or not isinstance(da_data, list):
        da_data = []

    daily_agg: dict = defaultdict(
        lambda: {
            "questions_answered": 0,
            "questions_correct": 0,
            "minutes_studied": 0,
            "active_users": 0,
        }
    )
    for row in da_data:
        d = row.get("activity_date") or ""
        if not d:
            continue
        daily_agg[d]["questions_answered"] += row.get("questions_answered", 0) or 0
        daily_agg[d]["questions_correct"] += row.get("questions_correct", 0) or 0
        daily_agg[d]["minutes_studied"] += row.get("minutes_studied", 0) or 0
        daily_agg[d]["active_users"] += 1
    daily_activity = [{"date": k, **v} for k, v in sorted(daily_agg.items())]

    # Average mastery score
    am_status, am_data = _supabase_svc(
        "/user_kpi_mastery",
        params={"select": "mastery_score", "limit": "10000"},
    )
    avg_mastery = 0.0
    if am_status == 200 and isinstance(am_data, list) and am_data:
        scores = [
            r.get("mastery_score")
            for r in am_data
            if r.get("mastery_score") is not None
        ]
        avg_mastery = round(sum(scores) / len(scores), 1) if scores else 0.0

    # Total answers (sum of all total_attempts in user_srs_state)
    ta_status, ta_data = _supabase_svc(
        "/user_srs_state",
        params={"select": "total_attempts", "limit": "10000"},
    )
    total_answers = 0
    if ta_status == 200 and isinstance(ta_data, list):
        total_answers = sum((r.get("total_attempts") or 0) for r in ta_data)

    return jsonify(
        {
            "top_kpis": top_kpis,
            "daily_activity": daily_activity,
            "avg_mastery": avg_mastery,
            "total_answers": total_answers,
        }
    )


# ─── Logs ─────────────────────────────────────────────────────────────────────


@admin_bp.get("/api/admin/logs")
def admin_logs():
    _, err = require_admin()
    if err:
        return err

    status, data = _supabase_svc(
        "/user_study_sessions",
        params={
            "select": (
                "id,user_id,started_at,ended_at,"
                "kpi_code,questions_answered,questions_correct"
            ),
            "order": "started_at.desc",
            "limit": "50",
        },
    )
    logs = data if status == 200 and isinstance(data, list) else []
    return jsonify({"logs": logs})


# ─── Announcements ────────────────────────────────────────────────────────────


@admin_bp.post("/api/admin/announcements")
def admin_post_announcement():
    _, err = require_admin()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "")).strip()
    message = str(body.get("message", "")).strip()
    ann_type = str(body.get("type", "info")).strip()

    if not title or not message:
        return jsonify({"error": "title and message are required"}), 400

    payload = {
        "title": title,
        "message": message,
        "type": ann_type,
        "created_at": date.today().isoformat(),
    }
    status, data = _supabase_svc(
        "/system_announcements",
        method="POST",
        payload=payload,
        prefer="return=representation",
    )
    if status in (200, 201):
        return jsonify({"ok": True})
    # Table probably doesn't exist yet — degrade gracefully
    return jsonify({"ok": True, "note": "Announcements table not set up yet"})
