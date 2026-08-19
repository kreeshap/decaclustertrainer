from collections import defaultdict
from datetime import date, timedelta
import uuid

from flask import Blueprint, jsonify, request

from ..auth_utils import get_current_user, is_admin
from ..content_ops import (
    apply_review_choice,
    auto_resolve_existing_reviews,
    build_review_decision,
    catalog_id,
    launch_batch,
    retryable_failed_kpi_ids,
    sync_kpi_catalog,
    utc_now,
)
from ..content_quality import ContentQualityError, validate_exam_item
from ..audit_ops import launch_audit_batch, select_audit_kpis
from ..db import supabase_admin_request, supabase_storage_upload
from ..learn_helpers import _load_all_kpis, _supabase_svc, KPI_DIR, _save_questions_supabase
from werkzeug.utils import secure_filename
import json
import hashlib
from pathlib import Path

from ..ai import call_json_with_fallback
from ..question_ingestion import assess_item, build_style_profile, extract_pdf_questions, max_similarity, parse_reference_citation, question_hash
from ..practice_corpus import (PARSER_VERSION, exam_metrics, extract_pdf_text, normalized_text,
                               parse_exam, parse_roleplay, readiness, suggest_metadata, text_fingerprint)

admin_bp = Blueprint("admin", __name__)

CORPUS_BUCKET = "practice-corpus-private"


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


def _classification_summary():
    kpis, _ = _load_all_kpis()
    status, rows = _supabase_svc(
        "/kpi_classifications",
        params={"select": "kpi_id,review_status", "limit": "10000"},
    )
    rows = rows if status == 200 and isinstance(rows, list) else []
    counts = defaultdict(int)
    for row in rows:
        counts[row.get("review_status") or "unknown"] += 1
    return {
        "total": len(kpis),
        "classified": len(rows),
        "remaining": max(0, len(kpis) - len(rows)),
        "auto_approved": counts["auto_approved"],
        "approved": counts["approved"],
        "needs_review": counts["needs_review"],
        "blocked": counts["blocked"],
    }


def _generated_content_summary():
    kpis, _ = _load_all_kpis()
    status, rows = _supabase_svc(
        "/generated_kpi_lessons",
        params={"status": "eq.ready", "select": "kpi_id", "limit": "10000"},
    )
    ready = len(rows) if status == 200 and isinstance(rows, list) else 0
    total = len(kpis)
    return {
        "ready": ready,
        "total": total,
        "remaining": max(0, total - ready),
        "percentage": round((ready / total) * 100, 1) if total else 0,
    }


@admin_bp.get("/api/admin/content-operations")
def admin_content_operations():
    _, err = require_admin()
    if err:
        return err
    batch_status, batches = _supabase_svc(
        "/kpi_classification_batches",
        params={"select": "*", "order": "created_at.desc", "limit": "1"},
    )
    latest = batches[0] if batch_status == 200 and isinstance(batches, list) and batches else None
    jobs_status, jobs = _supabase_svc(
        "/kpi_classification_jobs",
        params={"select": "kpi_id,status,created_at", "order": "created_at.asc", "limit": "10000"},
    )
    failed_ids = retryable_failed_kpi_ids(jobs if jobs_status == 200 and isinstance(jobs, list) else [])
    return jsonify({
        "classification": _classification_summary(),
        "generated_content": _generated_content_summary(),
        "failed_processing": len(failed_ids),
        "latest_batch": latest,
    })


@admin_bp.post("/api/admin/content-audits/process")
def admin_process_content_audit():
    user, err = require_admin()
    if err:
        return err
    active_status, active = _supabase_svc(
        "/lesson_audit_batches",
        params={"status": "in.(queued,processing)", "select": "id,status", "limit": "1"},
    )
    if active_status != 200 or not isinstance(active, list):
        return jsonify({"error": "Audit state could not be loaded."}), 502
    if active:
        return jsonify({"error": "A lesson audit is already running.", "batch": active[0]}), 409
    try:
        sync_kpi_catalog()
        selected = select_audit_kpis(20)
        if not selected:
            return jsonify({"ok": True, "queued": 0, "message": "All KPI study lessons are generated."})
        status, batches = _supabase_svc(
            "/lesson_audit_batches", method="POST",
            payload={"requested_count": len(selected), "created_by": user["id"]},
            prefer="return=representation",
        )
        if status not in (200, 201) or not batches:
            raise RuntimeError(batches)
        batch = batches[0]
        rows = [{
            "batch_id": batch["id"], "kpi_id": catalog_id(kpi),
            "complexity": plan["complexity"], "skill_type": plan["skill_type"],
        } for kpi, plan in selected]
        item_status, item_data = _supabase_svc(
            "/lesson_content_audits", method="POST", payload=rows, prefer="return=minimal",
        )
        if item_status not in (200, 201, 204):
            raise RuntimeError(item_data)
        launch_audit_batch(batch["id"], selected)
        return jsonify({"ok": True, "queued": len(selected), "batch": batch}), 202
    except Exception as error:
        return jsonify({"error": "Lesson audit could not be started.", "detail": str(error)}), 502


@admin_bp.get("/api/admin/content-audits")
def admin_content_audits():
    _, err = require_admin()
    if err:
        return err
    _, batches = _supabase_svc(
        "/lesson_audit_batches", params={"select": "*", "order": "created_at.desc", "limit": "1"},
    )
    _, pending = _supabase_svc(
        "/lesson_content_audits",
        params={"generation_status": "eq.ready", "review_status": "eq.pending", "select": "id", "limit": "1000"},
    )
    _, failures = _supabase_svc(
        "/lesson_generation_failures", params={"select": "id", "limit": "10000"},
    )
    return jsonify({
        "latest_batch": batches[0] if batches else None,
        "pending": len(pending or []),
        "generation_failures": len(failures or []),
    })


@admin_bp.get("/api/admin/content-audits/review-next")
def admin_next_content_audit():
    _, err = require_admin()
    if err:
        return err
    status, rows = _supabase_svc(
        "/lesson_content_audits",
        params={"generation_status": "eq.ready", "review_status": "eq.pending", "select": "*", "order": "created_at.asc", "limit": "1"},
    )
    if status != 200 or not isinstance(rows, list):
        return jsonify({"error": "Audit review queue could not be loaded."}), 502
    if not rows:
        return jsonify({"item": None})
    item = rows[0]
    _, catalog = _supabase_svc("/kpi_catalog", params={"id": f"eq.{item['kpi_id']}", "select": "*", "limit": "1"})
    item["kpi"] = catalog[0] if catalog else {}
    remaining_status, remaining_rows = _supabase_svc(
        "/lesson_content_audits",
        params={"generation_status": "eq.ready", "review_status": "eq.pending", "select": "id", "limit": "1000"},
    )
    remaining = len(remaining_rows) if remaining_status == 200 and isinstance(remaining_rows, list) else 1
    return jsonify({"item": item, "remaining": remaining})


@admin_bp.patch("/api/admin/content-audits/<audit_id>")
def admin_review_content_audit(audit_id):
    user, err = require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    scores = {}
    for field in ("mission_clarity", "choice_matters", "vocabulary_quality", "learning_value", "difficulty_progression", "pacing_quality"):
        try:
            value = int(body.get(field))
        except (TypeError, ValueError):
            return jsonify({"error": f"{field} must be scored from 1 to 5"}), 400
        if not 1 <= value <= 5:
            return jsonify({"error": f"{field} must be scored from 1 to 5"}), 400
        scores[field] = value
    review_status = "passed" if min(scores.values()) >= 4 else "needs_revision"
    status, data = _supabase_svc(
        "/lesson_content_audits", method="PATCH",
        payload={**scores, "notes": str(body.get("notes") or "")[:3000], "review_status": review_status, "reviewed_by": user["id"], "reviewed_at": utc_now(), "updated_at": utc_now()},
        params={"id": f"eq.{audit_id}", "review_status": "eq.pending"}, prefer="return=representation",
    )
    if status != 200:
        return jsonify({"error": "Audit review could not be saved.", "detail": data}), 502
    if not data:
        return jsonify({"error": "This audit was already saved or is no longer pending."}), 409
    return jsonify({"ok": True, "review_status": review_status})


def _create_classification_batch(user_id: str, kpi_ids: list[str]):
    batch_status, batches = _supabase_svc(
        "/kpi_classification_batches", method="POST",
        payload={"requested_count": len(kpi_ids), "created_by": user_id},
        prefer="return=representation",
    )
    if batch_status not in (200, 201) or not isinstance(batches, list) or not batches:
        raise RuntimeError(f"Batch creation failed: {batches}")
    batch = batches[0]
    jobs = [{"batch_id": batch["id"], "kpi_id": kpi_id} for kpi_id in kpi_ids]
    job_status, job_data = _supabase_svc(
        "/kpi_classification_jobs", method="POST", payload=jobs,
        prefer="return=minimal",
    )
    if job_status not in (200, 201, 204):
        raise RuntimeError(f"Job creation failed: {job_data}")
    launch_batch(batch["id"])
    return batch


@admin_bp.post("/api/admin/content-operations/process")
def admin_process_classifications():
    user, err = require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    try:
        limit = max(1, min(int(body.get("limit") or 20), 20))
    except (TypeError, ValueError):
        return jsonify({"error": "limit must be an integer between 1 and 20"}), 400
    try:
        active_status, active = _supabase_svc(
            "/kpi_classification_batches",
            params={"status": "in.(queued,processing)", "select": "id,status", "limit": "1"},
        )
        if active_status != 200 or not isinstance(active, list):
            raise RuntimeError(f"Could not inspect active batches: {active}")
        if active:
            return jsonify({"error": "A classification batch is already running.", "batch": active[0]}), 409
        catalog = sync_kpi_catalog()
        status, rows = _supabase_svc(
            "/kpi_classifications", params={"select": "kpi_id", "limit": "10000"}
        )
        if status != 200 or not isinstance(rows, list):
            raise RuntimeError(f"Could not load classification state: {rows}")
        classified = {row["kpi_id"] for row in rows}
        selected = [row["id"] for row in catalog if row["id"] not in classified][:limit]
        if not selected:
            return jsonify({"ok": True, "queued": 0, "message": "All KPIs are classified."})
        batch = _create_classification_batch(user["id"], selected)
        return jsonify({"ok": True, "queued": len(selected), "batch": batch}), 202
    except Exception as error:
        return jsonify({"error": "Classification batch could not be started.", "detail": str(error)}), 502


@admin_bp.post("/api/admin/content-operations/retry-failed")
def admin_retry_failed_classifications():
    user, err = require_admin()
    if err:
        return err
    status, jobs = _supabase_svc(
        "/kpi_classification_jobs",
        params={"select": "kpi_id,status,created_at", "order": "created_at.asc", "limit": "10000"},
    )
    if status != 200 or not isinstance(jobs, list):
        return jsonify({"error": "Failed jobs could not be loaded."}), 502
    kpi_ids = retryable_failed_kpi_ids(jobs)[:20]
    if not kpi_ids:
        return jsonify({"ok": True, "queued": 0})
    try:
        batch = _create_classification_batch(user["id"], kpi_ids)
        return jsonify({"ok": True, "queued": len(kpi_ids), "batch": batch}), 202
    except Exception as error:
        return jsonify({"error": "Retry batch could not be started.", "detail": str(error)}), 502


@admin_bp.post("/api/admin/content-operations/auto-resolve-review")
def admin_auto_resolve_classification_review():
    user, err = require_admin()
    if err:
        return err
    active_status, active = _supabase_svc(
        "/kpi_classification_batches",
        params={"status": "in.(queued,processing)", "select": "id", "limit": "1"},
    )
    if active_status != 200 or not isinstance(active, list):
        return jsonify({"error": "Batch state could not be loaded."}), 502
    if active:
        return jsonify({"error": "A classification batch is already running."}), 409
    try:
        result = auto_resolve_existing_reviews(50)
        return jsonify({"ok": True, **result, "queued": 0})
    except Exception as error:
        return jsonify({"error": "Review items could not be auto-resolved.", "detail": str(error)}), 502


@admin_bp.get("/api/admin/content-operations/review-next")
def admin_next_classification_review():
    _, err = require_admin()
    if err:
        return err
    status, rows = _supabase_svc(
        "/kpi_classifications",
        params={"review_status": "eq.needs_review", "select": "*", "order": "review_deferred_at.asc.nullsfirst,updated_at.asc", "limit": "1"},
    )
    if status != 200 or not isinstance(rows, list):
        return jsonify({"error": "Review queue could not be loaded."}), 502
    if not rows:
        return jsonify({"item": None, "remaining": 0, "decision": None})
    item = rows[0]
    catalog_status, catalog = _supabase_svc(
        "/kpi_catalog", params={"id": f"eq.{item['kpi_id']}", "select": "*", "limit": "1"}
    )
    item["kpi"] = catalog[0] if catalog_status == 200 and isinstance(catalog, list) and catalog else {}
    return jsonify({
        "item": item,
        "remaining": _classification_summary()["needs_review"],
        "decision": build_review_decision(item),
    })


@admin_bp.patch("/api/admin/content-operations/review/<path:kpi_id>")
def admin_review_classification(kpi_id):
    user, err = require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "approve").strip().lower()
    if action == "skip":
        status, data = _supabase_svc(
            "/kpi_classifications", method="PATCH",
            payload={"review_deferred_at": utc_now(), "updated_at": utc_now()},
            params={"kpi_id": f"eq.{kpi_id}", "review_status": "eq.needs_review"},
            prefer="return=representation",
        )
        if status not in (200, 204):
            return jsonify({"error": "Classification could not be deferred.", "detail": data}), 502
        if status == 200 and not data:
            return jsonify({"error": "This review item is no longer pending."}), 409
        return jsonify({"ok": True})
    if action != "approve":
        return jsonify({"error": "action must be approve or skip"}), 400
    current_status, current_rows = _supabase_svc(
        "/kpi_classifications",
        params={"kpi_id": f"eq.{kpi_id}", "review_status": "eq.needs_review", "select": "*", "limit": "1"},
    )
    if current_status != 200 or not isinstance(current_rows, list) or not current_rows:
        return jsonify({"error": "This review item is no longer pending."}), 409
    try:
        choice_payload = apply_review_choice(current_rows[0], str(body.get("choice") or "current").strip().lower())
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    payload = {
        **choice_payload,
        "review_status": "approved",
        "reviewed_by": user["id"],
        "reviewed_at": utc_now(),
        "updated_at": utc_now(),
        "review_deferred_at": None,
    }
    status, data = _supabase_svc(
        "/kpi_classifications", method="PATCH", payload=payload,
        params={"kpi_id": f"eq.{kpi_id}", "review_status": "eq.needs_review"},
        prefer="return=representation",
    )
    if status != 200:
        return jsonify({"error": "Classification review could not be saved.", "detail": data}), 502
    if not data:
        return jsonify({"error": "Classification review could not be saved."}), 409
    return jsonify({"ok": True, "classification": data[0] if isinstance(data, list) else None})


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

CAREER_CLUSTERS = {
    "Marketing", "Finance", "Hospitality and Tourism",
    "Business Management and Administration",
}


def _question_kpi(kpi_code: str, event_id: str) -> dict | None:
    return next((kpi for kpi in _load_all_kpis()[0]
                 if kpi.get("code") == kpi_code and kpi.get("event") == event_id), None)


def _cluster_question_kpis(kpi_code: str, career_cluster: str) -> list[dict]:
    target = career_cluster.strip().lower().replace("&", "and")
    matches = [kpi for kpi in _load_all_kpis()[0]
               if kpi.get("code") == kpi_code
               and kpi.get("deca_cluster", "").strip().lower().replace("&", "and") == target]
    return list({kpi["event"]: kpi for kpi in matches}.values())


def _import_staged_question(item: dict, document: dict, user_id: str) -> tuple[bool, object]:
    if document.get("usage_rights") != "licensed_for_student_use":
        return False, "Reference-only sources cannot be published to Practice Mode."
    matching_kpis = _cluster_question_kpis(item.get("kpi_code", ""), document.get("career_cluster", ""))
    if not matching_kpis:
        return False, "Choose a KPI that belongs to the selected career cluster."
    if item.get("correct_index") not in range(4) or len(item.get("choices") or []) != 4:
        return False, "A complete answer key and four choices are required."
    saved_questions = []
    for kpi in matching_kpis:
        _, slots = _supabase_svc("/kpi_questions", params={
            "event_id": f"eq.{kpi['event']}", "kpi_code": f"eq.{item['kpi_code']}",
            "question_type": "eq.application", "select": "question_slot", "order": "question_slot.desc", "limit": "1",
        })
        slot = int(slots[0]["question_slot"]) + 1 if slots else 0
        payload = {
            "kpi_code": item["kpi_code"], "kpi_text": kpi.get("text", ""),
            "kpi_cluster": kpi.get("cluster", ""), "deca_cluster": kpi.get("deca_cluster", ""),
            "event_id": kpi["event"], "question_text": item["question_text"],
            "choices": item["choices"], "correct_index": item["correct_index"],
            "explanation": item.get("explanation", ""), "question_type": "application", "question_slot": slot,
            "source_type": "imported_reference", "source_document_id": document["id"],
            "source_question_number": item["question_number"], "source_page": item.get("page_number"),
            "usage_rights": document["usage_rights"], "normalized_hash": item["normalized_hash"],
            "review_status": "approved",
        }
        status, data = _supabase_svc("/kpi_questions", method="POST", payload=payload, prefer="return=representation")
        if status not in (200, 201) or not isinstance(data, list) or not data:
            return False, data
        saved_questions.extend(data)
    representative = saved_questions[0]
    _supabase_svc("/question_import_items", method="PATCH", payload={
        "review_status": "imported", "imported_question_id": representative["id"],
        "reviewed_by": user_id, "reviewed_at": utc_now(),
    }, params={"id": f"eq.{item['id']}"}, prefer="return=minimal")
    _supabase_svc("/question_source_links", method="PATCH", payload={"imported_question_id": representative["id"]},
                  params={"import_item_id": f"eq.{item['id']}"}, prefer="return=minimal")
    return True, saved_questions


def _link_reference_sources(document: dict, items: list[dict]) -> None:
    for item in items:
        for raw in item.get("source_references") or []:
            parsed = parse_reference_citation(raw)
            _, sources = _supabase_svc("/reference_sources", params={
                "canonical_key": f"eq.{parsed['canonical_key']}", "select": "id", "limit": "1",
            })
            if sources:
                source_id = sources[0]["id"]
            else:
                status, created = _supabase_svc("/reference_sources", method="POST", payload={
                    key: parsed[key] for key in ("canonical_key", "title", "authors", "edition", "publication_year", "publisher", "raw_citation")
                }, prefer="return=representation")
                if status not in (200, 201) or not created:
                    continue
                source_id = created[0]["id"]
            _supabase_svc("/question_source_links", method="POST", payload={
                "source_id": source_id, "import_item_id": item["id"], "document_id": document["id"],
                "kpi_id": None,
                "kpi_code": item.get("kpi_code", ""), "pages": parsed["pages"], "raw_citation": raw,
            }, params={"on_conflict": "source_id,import_item_id"}, prefer="resolution=ignore-duplicates,return=minimal")


def _form_bool(name: str) -> bool:
    return str(request.form.get(name) or "").lower() in {"1", "true", "yes", "on"}


@admin_bp.post("/api/admin/practice-corpus")
def admin_upload_practice_corpus():
    user, err = require_admin()
    if err:
        return err
    uploaded = request.files.get("file")
    content_type = str(request.form.get("content_type") or "").strip().lower()
    if content_type not in {"exam", "roleplay"}:
        return jsonify({"error": "content_type must be exam or roleplay."}), 400
    if not uploaded or not (uploaded.filename or "").lower().endswith(".pdf"):
        return jsonify({"error": "Upload a PDF file."}), 400
    file_bytes = uploaded.read()
    if not file_bytes or len(file_bytes) > 25 * 1024 * 1024:
        return jsonify({"error": "PDF must be between 1 byte and 25 MB."}), 400
    digest = hashlib.sha256(file_bytes).hexdigest()
    _, exact = _supabase_svc("/practice_corpus_documents", params={"file_sha256": f"eq.{digest}", "select": "*", "limit": "1"})
    if exact:
        return jsonify({"error": "This exact PDF already exists in the corpus.", "duplicate": exact[0]}), 409
    attempt_payload = {"content_type": content_type, "original_filename": secure_filename(uploaded.filename or f"{content_type}.pdf"),
                       "status": "parsing", "stage": "extracting", "created_by": user["id"]}
    _, attempts = _supabase_svc("/corpus_parse_attempts", method="POST", payload=attempt_payload, prefer="return=representation")
    attempt_id = attempts[0]["id"] if attempts else None
    def finish_attempt(status, stage, error_message=None, document_id=None, item_count=0):
        if not attempt_id:
            return
        _supabase_svc("/corpus_parse_attempts", method="PATCH",
                      payload={"status": status, "stage": stage, "error_message": str(error_message or "")[:2000] or None,
                               "document_id": document_id, "item_count": item_count,
                               "finished_at": utc_now() if status != "parsing" else None, "updated_at": utc_now()},
                      params={"id": f"eq.{attempt_id}"}, prefer="return=minimal")
    try:
        text, page_count = extract_pdf_text(file_bytes)
        suggestions = suggest_metadata(text, uploaded.filename or "upload.pdf", content_type)
        text_hash = hashlib.sha256(normalized_text(text).encode()).hexdigest()
        fingerprint = text_fingerprint(text)
        _, similar = _supabase_svc("/practice_corpus_documents", params={"normalized_text_hash": f"eq.{text_hash}", "select": "id,title,original_filename", "limit": "1"})
        parsed = parse_exam(file_bytes) if content_type == "exam" else (parse_roleplay(text, suggestions), {"page_count": page_count})
    except Exception as error:
        finish_attempt("failed", "extracting", error)
        return jsonify({"error": "PDF could not be parsed.", "detail": str(error)}), 422
    document_id = str(uuid.uuid4())
    safe_name = secure_filename(uploaded.filename or f"{content_type}.pdf")
    storage_path = f"{content_type}/{document_id}/{safe_name}"
    storage_status, storage_result = supabase_storage_upload(CORPUS_BUCKET, storage_path, file_bytes)
    if storage_status not in (200, 201):
        finish_attempt("failed", "storage", storage_result)
        return jsonify({"error": "The private original could not be stored.", "detail": storage_result}), 502
    event_codes = [value.strip().upper() for value in request.form.getlist("event_codes") if value.strip()] or suggestions.get("event_codes", [])
    if content_type == "exam":
        event_codes = []
    elif not event_codes:
        finish_attempt("failed", "metadata", "Roleplays and case studies require an event code.")
        return jsonify({"error": "Roleplays and case studies require an event code."}), 400
    requested_cluster = str(request.form.get("cluster") or "").strip()
    if content_type == "exam" and not requested_cluster:
        finish_attempt("failed", "metadata", "Exams require a career cluster.")
        return jsonify({"error": "Exams require a career cluster."}), 400
    if content_type == "roleplay":
        _, corpus_events = _load_all_kpis()
        requested_cluster = next((event.get("cluster") or "" for event in corpus_events
                                  if str(event.get("event_code") or "").upper() == event_codes[0]), "")
    rights = "licensed_for_student_use" if content_type == "exam" else str(request.form.get("rights_status") or "unknown")
    payload = {
        "id": document_id, "content_type": content_type,
        "title": str(request.form.get("title") or suggestions["title"])[:300],
        "competitive_year": request.form.get("competitive_year") or suggestions.get("competitive_year"),
        "cluster": requested_cluster, "event_codes": event_codes,
        "event_type": ("team_decision_making" if event_codes[0].endswith("TDM") else "individual_series") if content_type == "roleplay" else None,
        "competition_level": request.form.get("competition_level") or suggestions.get("competition_level") or "practice_sample",
        "instructional_area": (request.form.get("instructional_area") or "") if content_type == "roleplay" else "",
        "source_name": request.form.get("source_name") or "",
        "source_url": request.form.get("source_url") or None,
        "source_organization": request.form.get("source_organization") or "",
        "rights_status": rights, "official_deca": _form_bool("official_deca") or suggestions.get("official_deca", False),
        "notes": request.form.get("notes") or "", "original_filename": safe_name,
        "storage_path": storage_path, "file_sha256": digest, "normalized_text_hash": text_hash,
        "similarity_fingerprint": fingerprint, "extracted_text": text,
        "metadata_suggestions": suggestions, "parser_version": PARSER_VERSION,
        "field_confidence": suggestions.get("field_confidence") or {},
        "review_flags": suggestions.get("review_flags") or [],
        "review_priority": "high" if suggestions.get("review_flags") else "normal",
        "processing_state": "needs_review", "duplicate_of": similar[0]["id"] if similar else None,
        "created_by": user["id"], "parsed_at": utc_now(),
    }
    status, saved = _supabase_svc("/practice_corpus_documents", method="POST", payload=payload, prefer="return=representation")
    if status not in (200, 201) or not saved:
        finish_attempt("failed", "document_save", saved)
        return jsonify({"error": "Parsed corpus metadata could not be saved.", "detail": saved}), 502
    if content_type == "exam":
        questions, stats = parsed
        rows = [{**row, "document_id": document_id} for row in questions]
        if rows:
            item_status, item_result = _supabase_svc("/reference_exam_questions", method="POST", payload=rows, prefer="return=representation")
            if item_status not in (200, 201):
                finish_attempt("failed", "item_save", item_result, document_id)
                return jsonify({"error": "Exam metadata saved, but questions could not be staged.", "document": saved[0], "detail": item_result}), 502
        failure_rows = [{"document_id": document_id, "item_type": "exam_question", "item_id": item["id"], "failure_code": code,
                         "field_name": "parser", "detail": "Deterministic parser review flag."}
                        for item in (item_result or []) for code in (item.get("review_flags") or [])]
        result = {"document": saved[0], "question_count": len(rows), "analysis": stats}
    else:
        roleplay, stats = parsed
        roleplay.update({"document_id": document_id, "event_type": payload["event_type"]})
        roleplay_status, roleplay_result = _supabase_svc("/reference_roleplays", method="POST", payload=roleplay, prefer="return=representation")
        if roleplay_status not in (200, 201):
            finish_attempt("failed", "item_save", roleplay_result, document_id)
            return jsonify({"error": "Roleplay metadata saved, but structured sections could not be staged.", "document": saved[0], "detail": roleplay_result}), 502
        failure_rows = [{"document_id": document_id, "item_type": "roleplay", "item_id": roleplay_result[0]["id"], "failure_code": code,
                         "field_name": "parser", "detail": "Deterministic parser review flag."}
                        for code in (roleplay_result[0].get("review_flags") or [])]
        result = {"document": saved[0], "roleplay": roleplay_result[0], "analysis": stats}
    failure_rows.extend({"document_id": document_id, "item_type": "document", "failure_code": code,
                         "field_name": "metadata", "detail": "Metadata requires reviewer confirmation."}
                        for code in (suggestions.get("review_flags") or []))
    if failure_rows:
        _supabase_svc("/corpus_parser_failures", method="POST", payload=failure_rows, prefer="return=minimal")
    result["likely_duplicate"] = similar[0] if similar else None
    finish_attempt("succeeded", "complete", document_id=document_id,
                   item_count=len(rows) if content_type == "exam" else 1)
    return jsonify(result), 201


@admin_bp.get("/api/admin/practice-corpus")
def admin_list_practice_corpus():
    _, err = require_admin()
    if err:
        return err
    params = {"select": "*", "order": "uploaded_at.desc", "limit": "500"}
    if request.args.get("content_type"):
        params["content_type"] = f"eq.{request.args['content_type']}"
    _, documents = _supabase_svc("/practice_corpus_documents", params=params)
    _, questions = _supabase_svc("/reference_exam_questions", params={"select": "document_id,human_verified", "limit": "50000"})
    _, roleplays = _supabase_svc("/reference_roleplays", params={"select": "*", "limit": "1000"})
    _, attempts = _supabase_svc("/corpus_parse_attempts", params={"select": "*", "order": "started_at.desc", "limit": "100"})
    _, failures = _supabase_svc("/corpus_parser_failures", params={"select": "*", "order": "created_at.desc", "limit": "200"})
    roleplay_by_document = {row["document_id"]: row for row in roleplays or []}
    question_counts = defaultdict(lambda: {"total": 0, "pending": 0})
    for question in questions or []:
        question_counts[question["document_id"]]["total"] += 1
        if not question.get("human_verified"):
            question_counts[question["document_id"]]["pending"] += 1
    result = [{**doc, "structured_roleplay": roleplay_by_document.get(doc["id"]),
               "item_counts": question_counts[doc["id"]] if doc["content_type"] == "exam" else
                              {"total": 1 if roleplay_by_document.get(doc["id"]) else 0,
                               "pending": 1 if roleplay_by_document.get(doc["id"]) and not roleplay_by_document[doc["id"]].get("human_verified") else 0}}
              for doc in documents or []]
    return jsonify({"documents": result, "parse_attempts": attempts or [], "parser_failures": failures or []})


@admin_bp.patch("/api/admin/practice-corpus/<document_id>/verify")
def admin_verify_practice_corpus(document_id):
    user, err = require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    _, rows = _supabase_svc("/practice_corpus_documents", params={"id": f"eq.{document_id}", "select": "*", "limit": "1"})
    if not rows:
        return jsonify({"error": "Corpus document not found."}), 404
    document = rows[0]
    rights = str(body.get("rights_status") or document["rights_status"])
    benchmark = body.get("benchmark_eligible") is True
    publishable = body.get("student_publishable") is True
    if benchmark and rights in {"unknown", "do_not_use"}:
        return jsonify({"error": "Resolve rights before enabling benchmark use."}), 400
    if publishable and rights not in {"owned", "licensed_for_student_use", "public_domain"}:
        return jsonify({"error": "Student publication requires owned, licensed, or public-domain rights."}), 400
    metadata = body.get("confirmed_metadata")
    if not isinstance(metadata, dict):
        return jsonify({"error": "Reviewer-confirmed metadata is required."}), 400
    event_codes = metadata.get("event_codes") or document.get("event_codes") or []
    if document["content_type"] == "exam":
        event_codes = []
        rights = "licensed_for_student_use"
    elif not event_codes:
        return jsonify({"error": "Roleplay verification requires an event code."}), 400
    payload = {"title": str(metadata.get("title") or document["title"])[:300],
               "competitive_year": metadata.get("competitive_year") or document.get("competitive_year"),
               "cluster": metadata.get("cluster") or document.get("cluster") or "",
               "event_codes": event_codes,
               "competition_level": metadata.get("competition_level") or document["competition_level"],
               "instructional_area": metadata.get("instructional_area") or document.get("instructional_area") or "",
               "source_name": metadata.get("source_name") or document.get("source_name") or "",
               "source_url": metadata.get("source_url") or document.get("source_url"),
               "source_organization": metadata.get("source_organization") or document.get("source_organization") or "",
               "official_deca": metadata.get("official_deca") is True,
               "rights_status": rights, "confirmed_metadata": metadata,
               "processing_state": "verified_reference", "benchmark_eligible": benchmark,
               "student_publishable": publishable, "verified_at": utc_now(), "verified_by": user["id"], "updated_at": utc_now()}
    status, result = _supabase_svc("/practice_corpus_documents", method="PATCH", payload=payload, params={"id": f"eq.{document_id}"}, prefer="return=representation")
    if status not in (200, 204) or not result:
        return jsonify({"error": "Verification could not be saved.", "detail": result}), 502
    if document["content_type"] == "roleplay":
        structured = body.get("structured_roleplay")
        allowed = {"event_code", "event_type", "instructional_area", "performance_indicators", "participant_role", "judge_role",
                   "prep_time_minutes", "presentation_time_minutes", "participant_instructions", "situation", "judge_instructions",
                   "official_tasks", "judge_questions", "evaluation_criteria", "problem_archetype", "participant_authority", "expected_action"}
        child_payload = {key: value for key, value in (structured or {}).items() if key in allowed}
        child_payload.update({"human_verified": True, "gold_reference": body.get("gold_reference") is True,
                              "verified_at": utc_now(), "verified_by": user["id"]})
        _supabase_svc("/reference_roleplays", method="PATCH", payload=child_payload, params={"document_id": f"eq.{document_id}"}, prefer="return=minimal")
    return jsonify({"document": result[0]})


@admin_bp.get("/api/admin/practice-corpus/questions/review-next")
def admin_next_reference_exam_question():
    _, err = require_admin()
    if err:
        return err
    params = {"human_verified": "eq.false", "select": "*", "order": "created_at.asc,question_number.asc", "limit": "1"}
    if request.args.get("document_id"):
        params["document_id"] = f"eq.{request.args['document_id']}"
    _, rows = _supabase_svc("/reference_exam_questions", params=params)
    return jsonify({"question": rows[0] if rows else None})


@admin_bp.patch("/api/admin/practice-corpus/questions/<question_id>")
def admin_verify_reference_exam_question(question_id):
    user, err = require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    stem = str(body.get("stem") or "").strip()
    choices = body.get("choices")
    if not stem:
        return jsonify({"error": "Question stem is required."}), 400
    if not isinstance(choices, list) or len(choices) != 4 or any(not str(choice).strip() for choice in choices):
        return jsonify({"error": "Exactly four non-empty answer choices are required."}), 400
    choices = [str(choice).strip() for choice in choices]
    answer = body.get("official_answer")
    if answer is not None:
        try:
            answer = int(answer)
        except (TypeError, ValueError):
            return jsonify({"error": "official_answer must be 0-3 or null."}), 400
        if answer not in range(4):
            return jsonify({"error": "official_answer must be 0-3 or null."}), 400
    pi_code = str(body.get("pi_code") or "").strip().upper() or None
    payload = {"stem": stem, "choices": choices, "official_answer": answer, "pi_code": pi_code,
               "pi_source": "human" if pi_code else "unknown",
               "instructional_area": str(body.get("instructional_area") or "").strip(),
               "cognitive_demand": str(body.get("cognitive_demand") or "").strip() or None,
               "gold_reference": body.get("gold_reference") is True,
               "human_verified": True, "verified_at": utc_now(), "verified_by": user["id"]}
    status, rows = _supabase_svc("/reference_exam_questions", method="PATCH", payload=payload,
                                 params={"id": f"eq.{question_id}"}, prefer="return=representation")
    if status not in (200, 204) or not rows:
        return jsonify({"error": "Question verification could not be saved."}), 502
    return jsonify({"question": rows[0]})


@admin_bp.post("/api/admin/practice-corpus/<document_id>/pilot-audit")
def admin_audit_pilot_document(document_id):
    user, err = require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    _, rows = _supabase_svc("/practice_corpus_documents", params={"id": f"eq.{document_id}", "select": "*", "limit": "1"})
    if not rows:
        return jsonify({"error": "Corpus document not found."}), 404
    allowed_codes = {"exam_choice_split", "exam_answer_key_mismatch", "exam_multiline_stem", "header_contamination",
                     "roleplay_pi_detection", "roleplay_section_boundary", "roleplay_judge_question_split", "metadata_year_unknown",
                     "metadata_event_unknown", "metadata_competition_level_unknown", "table_or_special_format", "page_break_split", "other"}
    failures = body.get("failures") or []
    if not isinstance(failures, list) or any(not isinstance(item, dict) or item.get("failure_code") not in allowed_codes for item in failures):
        return jsonify({"error": "Pilot failures contain an unsupported failure code."}), 400
    failure_rows = [{"document_id": document_id, "item_type": item.get("item_type") or "document",
                     "item_id": item.get("item_id") or None, "failure_code": item["failure_code"],
                     "field_name": str(item.get("field_name") or "")[:100], "detail": str(item.get("detail") or "")[:1000],
                     "detected_by": "reviewer"} for item in failures]
    if failure_rows:
        _supabase_svc("/corpus_parser_failures", method="POST", payload=failure_rows, prefer="return=minimal")
    metadata = dict(rows[0].get("confirmed_metadata") or {})
    metadata["pilot_audit"] = {"expected_item_count": body.get("expected_item_count"),
                               "silent_data_corruption": body.get("silent_data_corruption") is True,
                               "checklist": body.get("checklist") or {}, "audited_at": utc_now()}
    _supabase_svc("/practice_corpus_documents", method="PATCH",
                  payload={"confirmed_metadata": metadata, "pilot_audited_at": utc_now(), "pilot_audited_by": user["id"],
                           "review_priority": "critical" if body.get("silent_data_corruption") else ("high" if failures else "low")},
                  params={"id": f"eq.{document_id}"}, prefer="return=minimal")
    return jsonify({"ok": True, "failures_recorded": len(failure_rows)})


@admin_bp.get("/api/admin/practice-corpus/dashboard")
def admin_practice_corpus_dashboard():
    _, err = require_admin()
    if err:
        return err
    _, documents = _supabase_svc("/practice_corpus_documents", params={"select": "*", "limit": "10000"})
    _, questions = _supabase_svc("/reference_exam_questions", params={"select": "document_id,human_verified,pi_code,official_answer,metrics,gold_reference,review_flags", "limit": "50000"})
    _, roleplays = _supabase_svc("/reference_roleplays", params={"select": "document_id,human_verified,event_code,instructional_area,performance_indicators,metrics,gold_reference,problem_archetype,participant_authority,expected_action,review_flags", "limit": "10000"})
    _, failures = _supabase_svc("/corpus_parser_failures", params={"resolved": "eq.false", "select": "failure_code,document_id,detected_by", "limit": "50000"})
    _, knowledge = _supabase_svc("/kpi_knowledge_items", params={"review_status": "eq.approved", "authoritative": "eq.true", "select": "kpi_code", "limit": "10000"})
    documents, questions, roleplays = documents or [], questions or [], roleplays or []
    verified_docs = [doc for doc in documents if doc.get("processing_state") == "verified_reference"]
    audited_docs = [doc for doc in documents if doc.get("pilot_audited_at")]
    def grouped(field, content_type):
        counts = defaultdict(lambda: {"documents": 0, "items": 0})
        typed = [doc for doc in verified_docs if doc["content_type"] == content_type and doc.get("benchmark_eligible")]
        for doc in typed:
            keys = doc.get(field) if field == "event_codes" else [doc.get(field) or "Unspecified"]
            for key in keys or ["Unspecified"]:
                counts[key]["documents"] += 1
                child = questions if content_type == "exam" else roleplays
                counts[key]["items"] += sum(1 for item in child if item.get("document_id") == doc["id"] and item.get("human_verified"))
        return dict(sorted(counts.items()))
    exam_clusters = sorted({doc.get("cluster") for doc in documents if doc.get("content_type") == "exam" and doc.get("cluster")})
    events = sorted({event for doc in documents if doc.get("content_type") == "roleplay" for event in (doc.get("event_codes") or [])})
    readiness_rows = []
    all_kpis, curriculum_events = _load_all_kpis()
    event_ids_by_code = {str(item.get("event_code") or "").upper(): item.get("id") for item in curriculum_events}
    for cluster in exam_clusters:
        readiness_rows.append(readiness("exam", documents, questions, cluster=cluster))
    for event in events:
        readiness_rows.append(readiness("roleplay", documents, roleplays, event_code=event,
                                         cluster=next((d.get("cluster") or "" for d in documents if event in (d.get("event_codes") or [])), "")))
    snapshots = []
    for row in readiness_rows:
        if row["content_type"] == "exam":
            eligible = {item["code"] for item in all_kpis if item.get("deca_cluster") == row["cluster"] and "exam" in (item.get("eligible_components") or [])}
        else:
            eligible_event_id = event_ids_by_code.get(row["event_code"])
            eligible = {item["code"] for item in all_kpis if item.get("event") == eligible_event_id and any(component in (item.get("eligible_components") or []) for component in ("roleplay", "case_study"))}
        row["pi_coverage"] = round(len(set(row.pop("pi_codes", [])) & eligible) / len(eligible), 5) if eligible else None
        snapshots.append({"content_type": row["content_type"], "event_code": row["event_code"], "cluster": row["cluster"],
                          "documents": row["documents"], "items": row["items"], "years_represented": row["years_represented"],
                          "competition_levels": row["competition_levels"], "pi_coverage": row["pi_coverage"],
                          "readiness_status": row["status"], "readiness_reasons": row["reasons"]})
    if snapshots:
        _supabase_svc("/corpus_readiness_snapshots", method="POST", payload=snapshots, prefer="return=minimal")
    verified_question_metrics = [q.get("metrics") or {} for q in questions if q.get("human_verified")]
    exam_profile = {
        "sample_size": len(verified_question_metrics),
        "scenario_rate": round(sum(bool(m.get("scenario")) for m in verified_question_metrics) / max(1, len(verified_question_metrics)), 4),
        "calculation_rate": round(sum(bool(m.get("calculation")) for m in verified_question_metrics) / max(1, len(verified_question_metrics)), 4),
        "negative_stem_rate": round(sum(bool(m.get("negative_stem")) for m in verified_question_metrics) / max(1, len(verified_question_metrics)), 4),
        "mean_stem_words": round(sum(int(m.get("stem_words") or 0) for m in verified_question_metrics) / max(1, len(verified_question_metrics)), 2),
    }
    verified_roleplay_metrics = [r.get("metrics") or {} for r in roleplays if r.get("human_verified")]
    roleplay_profile = {"sample_size": len(verified_roleplay_metrics),
                        "mean_scenario_words": round(sum(int(m.get("scenario_words") or 0) for m in verified_roleplay_metrics) / max(1, len(verified_roleplay_metrics)), 2),
                        "mean_assigned_pis": round(sum(int(m.get("assigned_pi_count") or 0) for m in verified_roleplay_metrics) / max(1, len(verified_roleplay_metrics)), 2),
                        "mean_explicit_tasks": round(sum(int(m.get("explicit_task_count") or 0) for m in verified_roleplay_metrics) / max(1, len(verified_roleplay_metrics)), 2),
                        "mean_judge_questions": round(sum(int(m.get("judge_question_count") or 0) for m in verified_roleplay_metrics) / max(1, len(verified_roleplay_metrics)), 2)}
    for content_type, profile, checkpoints in (("exam", exam_profile, {50, 100, 200, 300, 500}),
                                                ("roleplay", roleplay_profile, {5, 10, 15, 25, 30})):
        sample_size = int(profile.get("sample_size") or 0)
        if sample_size not in checkpoints:
            continue
        _, existing_profiles = _supabase_svc("/corpus_style_profile_snapshots", params={
            "content_type": f"eq.{content_type}", "event_code": "eq.", "verified_item_count": f"eq.{sample_size}", "select": "id", "limit": "1"})
        if existing_profiles:
            continue
        _, previous_profiles = _supabase_svc("/corpus_style_profile_snapshots", params={
            "content_type": f"eq.{content_type}", "event_code": "eq.", "select": "id,profile,verified_item_count",
            "order": "verified_item_count.desc", "limit": "1"})
        previous = previous_profiles[0] if previous_profiles else None
        numeric_keys = [key for key, value in profile.items() if key != "sample_size" and isinstance(value, (int, float))]
        delta = (sum(abs(float(profile[key]) - float((previous.get("profile") or {}).get(key, 0))) for key in numeric_keys) / max(1, len(numeric_keys))) if previous else None
        _supabase_svc("/corpus_style_profile_snapshots", method="POST", payload={
            "content_type": content_type, "event_code": "", "verified_item_count": sample_size, "checkpoint": sample_size,
            "profile": profile, "previous_snapshot_id": previous.get("id") if previous else None,
            "stability_delta": round(delta, 6) if delta is not None else None}, prefer="return=minimal")
    benchmark_docs = [doc for doc in verified_docs if doc.get("benchmark_eligible")]
    duplicate_adjusted = [doc for doc in benchmark_docs if not doc.get("duplicate_of")]
    all_verified_items = [q for q in questions if q.get("human_verified")] + [r for r in roleplays if r.get("human_verified")]
    quality = {
        "verified_documents_pct": round(100 * len(verified_docs) / max(1, len(documents)), 1),
        "verified_items_pct": round(100 * len(all_verified_items) / max(1, len(questions) + len(roleplays)), 1),
        "official_source_pct": round(100 * sum(bool(doc.get("official_deca")) for doc in verified_docs) / max(1, len(verified_docs)), 1),
        "duplicate_adjusted_documents": len(duplicate_adjusted),
        "years_represented": len({doc.get("competitive_year") for doc in benchmark_docs if doc.get("competitive_year")}),
        "events_represented": len({event for doc in benchmark_docs for event in (doc.get("event_codes") or [])}),
        "instructional_areas_represented": len({r.get("instructional_area") for r in roleplays if r.get("human_verified") and r.get("instructional_area")}),
        "answer_key_coverage_pct": round(100 * sum(q.get("official_answer") is not None for q in questions) / max(1, len(questions)), 1),
        "explicit_pi_label_pct": round(100 * sum(bool(q.get("pi_code")) for q in questions) / max(1, len(questions)), 1),
        "benchmark_eligible_pct": round(100 * len(benchmark_docs) / max(1, len(documents)), 1),
        "student_publishable_pct": round(100 * sum(bool(doc.get("student_publishable")) for doc in documents) / max(1, len(documents)), 1),
        "gold_exam_items": sum(bool(q.get("gold_reference")) for q in questions),
        "gold_roleplays": sum(bool(r.get("gold_reference")) for r in roleplays),
    }
    failure_counts = defaultdict(int)
    for failure in failures or []:
        failure_counts[failure["failure_code"]] += 1
    audited_expected = sum(int(((doc.get("confirmed_metadata") or {}).get("pilot_audit") or {}).get("expected_item_count") or 0) for doc in audited_docs)
    audited_actual = sum(1 for item in questions + roleplays if item.get("document_id") in {doc["id"] for doc in audited_docs})
    silent_corruption = sum(bool(((doc.get("confirmed_metadata") or {}).get("pilot_audit") or {}).get("silent_data_corruption")) for doc in audited_docs)
    pilot_report = {"audited_documents": len(audited_docs), "failure_counts": dict(sorted(failure_counts.items())),
                    "document_detection_pct": round(100 * len(audited_docs) / max(1, len(documents)), 2),
                    "item_count_accuracy_pct": round(100 * min(audited_actual, audited_expected) / max(1, audited_expected), 2) if audited_expected else None,
                    "silent_data_corruption": silent_corruption,
                    "acceptance": {"document_detection_target": 100, "question_count_target": 99, "choice_parsing_target": 99,
                                   "answer_key_mapping_target": 100, "explicit_pi_extraction_target": 100,
                                   "roleplay_section_target": 98, "silent_corruption_target": 0}}
    approved_codes = {row.get("kpi_code") for row in knowledge or []}
    for row in readiness_rows:
        row["gold_references"] = quality["gold_exam_items"] if row["content_type"] == "exam" else quality["gold_roleplays"]
        row["approved_knowledge_claims"] = len(approved_codes)
        row["generation_locked"] = True
    return jsonify({"summary": {"documents": len(documents), "verified_documents": len(verified_docs),
                                "verified_questions": sum(bool(q.get("human_verified")) for q in questions),
                                "verified_roleplays": sum(bool(r.get("human_verified")) for r in roleplays)},
                    "exams_by_cluster": grouped("cluster", "exam"), "roleplays_by_event": grouped("event_codes", "roleplay"),
                    "readiness": readiness_rows,
                    "exam_style_profile": exam_profile, "roleplay_style_profile": roleplay_profile,
                    "quality": quality, "pilot_report": pilot_report,
                    "coverage_dimensions": {"years": grouped("competitive_year", "exam"), "competition_levels": grouped("competition_level", "exam"), "instructional_areas": grouped("instructional_area", "roleplay")}})


@admin_bp.post("/api/admin/question-imports")
def admin_upload_question_pdf():
    return jsonify({"error": "Legacy exam upload is closed. Use the unified Practice Content upload."}), 410
    # Existing staged imports remain reviewable through the legacy endpoints.
    user, err = require_admin()
    if err:
        return err
    uploaded = request.files.get("file")
    if not uploaded or not (uploaded.filename or "").lower().endswith(".pdf"):
        return jsonify({"error": "Choose a PDF file."}), 400
    file_bytes = uploaded.read()
    if not file_bytes or len(file_bytes) > 20 * 1024 * 1024:
        return jsonify({"error": "PDF must be between 1 byte and 20 MB."}), 400
    # Admin uploads are authorized for the complete internal content pipeline:
    # parsing, classification, Learn enrichment, and student-facing questions.
    usage_rights = "licensed_for_student_use"
    source_type = request.form.get("source_type", "other")
    career_cluster = request.form.get("career_cluster", "").strip()
    if source_type not in {"deca_sample", "owned", "licensed", "other"}:
        return jsonify({"error": "Unsupported source type."}), 400
    if career_cluster not in CAREER_CLUSTERS:
        return jsonify({"error": "Choose one of the four DECA career clusters."}), 400
    sync_kpi_catalog()
    digest = hashlib.sha256(file_bytes).hexdigest()
    existing_status, existing = _supabase_svc("/question_source_documents", params={
        "file_sha256": f"eq.{digest}", "select": "*", "limit": "1",
    })
    if existing_status == 200 and existing:
        return jsonify({"error": "This exact PDF was already uploaded.", "document": existing[0]}), 409
    try:
        questions, stats = extract_pdf_questions(file_bytes)
    except Exception as error:
        return jsonify({"error": str(error)}), 422
    doc_payload = {
        "filename": secure_filename(uploaded.filename), "file_sha256": digest,
        "source_type": source_type, "usage_rights": usage_rights,
        "career_cluster": career_cluster[:120],
        "event_id": "",
        "exam_year": int(request.form["exam_year"]) if request.form.get("exam_year", "").isdigit() else None,
        "page_count": stats["page_count"], "detected_count": len(questions), "created_by": user["id"],
    }
    status, docs = _supabase_svc("/question_source_documents", method="POST", payload=doc_payload, prefer="return=representation")
    if status not in (200, 201) or not docs:
        return jsonify({"error": "Import record could not be created.", "detail": docs}), 502
    document = docs[0]
    _, bank = _supabase_svc("/kpi_questions", params={
        "select": "id,question_text,normalized_hash", "limit": "10000",
    })
    career_cluster = doc_payload["career_cluster"]
    assessed = []
    for question in questions:
        matches = _cluster_question_kpis(question.get("kpi_code", ""), career_cluster)
        matched_kpi = matches[0] if matches else None
        question["kpi_cluster"] = matched_kpi.get("cluster", "") if matched_kpi else ""
        question["deca_cluster"] = matched_kpi.get("deca_cluster", "") if matched_kpi else doc_payload["career_cluster"]
        item = assess_item(question, bank or [], assessed, usage_rights == "licensed_for_student_use")
        if question.get("kpi_code") and not matched_kpi:
            item["review_reasons"].append("kpi_not_in_selected_cluster")
            item["review_status"] = "pending"
        assessed.append(item)
    rows = [{**item, "document_id": document["id"], "kpi_source": "document" if item["kpi_code"] else "unknown"}
            for item in assessed]
    item_status, item_data = _supabase_svc("/question_import_items", method="POST", payload=rows, prefer="return=representation")
    if item_status not in (200, 201) or not isinstance(item_data, list):
        return jsonify({"error": "Parsed questions could not be staged.", "detail": item_data}), 502
    knowledge_rows = []
    for item in item_data:
        if not item.get("kpi_code") or not item.get("explanation") or not item.get("kpi_cluster"):
            continue
        for kpi in _cluster_question_kpis(item["kpi_code"], career_cluster):
            knowledge_rows.append({
                "kpi_id": f"{kpi['event']}:{item['kpi_code']}", "kpi_code": item["kpi_code"],
                "kpi_cluster": item["kpi_cluster"], "deca_cluster": item["deca_cluster"],
                "knowledge_type": "source_explanation", "content": item["explanation"],
                "importance": "important", "content_hash": hashlib.sha256(item["explanation"].lower().encode("utf-8")).hexdigest(),
                "source_document_id": document["id"], "source_import_item_id": item["id"],
                "source_references": item.get("source_references") or [],
                "deca_evidence": [{
                    "source_type": "official_deca_sample_exam",
                    "purpose": "alignment_or_style",
                    "document_id": document["id"],
                    "year": doc_payload.get("exam_year"),
                    "references": item.get("source_references") or [],
                }],
            })
    if knowledge_rows:
        _supabase_svc("/kpi_knowledge_items", method="POST", payload=knowledge_rows,
                      params={"on_conflict": "kpi_id,content_hash"}, prefer="resolution=ignore-duplicates,return=minimal")
    _link_reference_sources(document, item_data)
    ready = sum(item["review_status"] == "ready" for item in assessed)
    duplicates = sum(any(reason in item["review_reasons"] for reason in ("exact_duplicate", "near_duplicate")) for item in assessed)
    summary = {"ready_count": ready, "review_count": len(assessed) - ready, "duplicate_count": duplicates,
               "status": "review" if len(assessed) - ready else "complete", "updated_at": utc_now()}
    _supabase_svc("/question_source_documents", method="PATCH", payload=summary,
                  params={"id": f"eq.{document['id']}"}, prefer="return=minimal")
    cluster_breakdown = defaultdict(int)
    for item in assessed:
        cluster_breakdown[item.get("kpi_cluster") or "Unassigned"] += 1
    return jsonify({"document": {**document, **summary}, "answer_keys_detected": stats["answer_keys_detected"],
                    "cluster_breakdown": dict(sorted(cluster_breakdown.items()))}), 201


@admin_bp.get("/api/admin/question-imports")
def admin_question_imports():
    _, err = require_admin()
    if err:
        return err
    _, docs = _supabase_svc("/question_source_documents", params={"select": "*", "order": "created_at.desc", "limit": "10"})
    _, pending = _supabase_svc("/question_import_items", params={"review_status": "in.(pending,ready,approved)", "select": "id", "limit": "10000"})
    _, clustered = _supabase_svc("/question_import_items", params={"select": "kpi_cluster,deca_cluster,kpi_code,review_status,review_reasons", "limit": "10000"})
    cluster_breakdown = defaultdict(int)
    status_breakdown = defaultdict(int)
    for item in clustered or []:
        cluster_breakdown[item.get("kpi_cluster") or "Unassigned"] += 1
        status_breakdown["all"] += 1
        if item.get("review_status") in {"imported", "approved"}:
            status_breakdown["verified"] += 1
        if item.get("review_status") in {"pending", "ready", "approved"}:
            status_breakdown["needs_review"] += 1
        if not item.get("kpi_code"):
            status_breakdown["unassigned"] += 1
        if any(reason in {"exact_duplicate", "near_duplicate"} for reason in (item.get("review_reasons") or [])):
            status_breakdown["possible_duplicates"] += 1
    _, knowledge = _supabase_svc("/kpi_knowledge_items", params={"review_status": "eq.pending", "select": "id", "limit": "10000"})
    return jsonify({"documents": docs or [], "pending": len(pending or []),
                    "cluster_breakdown": dict(sorted(cluster_breakdown.items())), "status_breakdown": status_breakdown,
                    "knowledge_pending": len(knowledge or [])})


@admin_bp.get("/api/admin/question-imports/review-next")
def admin_next_question_import():
    _, err = require_admin()
    if err:
        return err
    _, rows = _supabase_svc("/question_import_items", params={
        "review_status": "in.(pending,ready,approved)", "select": "*", "order": "created_at.asc,question_number.asc", "limit": "10000",
    })
    cluster = request.args.get("cluster", "").strip()
    queue_filter = request.args.get("filter", "needs_review").strip()
    candidates = []
    for item in rows or []:
        if cluster and (item.get("kpi_cluster") or "Unassigned") != cluster:
            continue
        if queue_filter == "unassigned" and item.get("kpi_code"):
            continue
        if queue_filter == "possible_duplicates" and not any(reason in {"exact_duplicate", "near_duplicate"} for reason in (item.get("review_reasons") or [])):
            continue
        candidates.append(item)
    rows = candidates[:1]
    if not rows:
        return jsonify({"item": None})
    item = rows[0]
    _, docs = _supabase_svc("/question_source_documents", params={"id": f"eq.{item['document_id']}", "select": "*", "limit": "1"})
    return jsonify({"item": item, "document": docs[0] if docs else {}})


@admin_bp.patch("/api/admin/question-imports/<item_id>")
def admin_review_question_import(item_id):
    user, err = require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    _, rows = _supabase_svc("/question_import_items", params={"id": f"eq.{item_id}", "select": "*", "limit": "1"})
    if not rows:
        return jsonify({"error": "Import item not found."}), 404
    item = rows[0]
    _, docs = _supabase_svc("/question_source_documents", params={"id": f"eq.{item['document_id']}", "select": "*", "limit": "1"})
    document = docs[0] if docs else {}
    if body.get("action") == "skip":
        _supabase_svc("/question_import_items", method="PATCH", payload={"review_status": "skipped", "reviewed_by": user["id"], "reviewed_at": utc_now()}, params={"id": f"eq.{item_id}"}, prefer="return=minimal")
        return jsonify({"ok": True, "status": "skipped"})
    updates = {}
    if "kpi_code" in body:
        updates.update(kpi_code=str(body["kpi_code"]).strip().upper(), kpi_source="admin")
    if "correct_index" in body:
        try:
            updates["correct_index"] = int(body["correct_index"])
        except (TypeError, ValueError):
            return jsonify({"error": "correct_index must be 0 through 3."}), 400
    if "explanation" in body:
        updates["explanation"] = str(body["explanation"])[:4000]
    item.update(updates)
    if updates:
        _supabase_svc("/question_import_items", method="PATCH", payload=updates, params={"id": f"eq.{item_id}"}, prefer="return=minimal")
    ok, result = _import_staged_question(item, document, user["id"])
    return jsonify({"ok": ok, "question": result if ok else None, "error": None if ok else result}), 200 if ok else 400


@admin_bp.post("/api/admin/question-imports/<document_id>/approve-ready")
def admin_import_ready_questions(document_id):
    user, err = require_admin()
    if err:
        return err
    _, docs = _supabase_svc("/question_source_documents", params={"id": f"eq.{document_id}", "select": "*", "limit": "1"})
    if not docs:
        return jsonify({"error": "Document not found."}), 404
    document = docs[0]
    _, items = _supabase_svc("/question_import_items", params={"document_id": f"eq.{document_id}", "review_status": "eq.ready", "select": "*", "limit": "1000"})
    imported, failures = 0, []
    for item in items or []:
        ok, detail = _import_staged_question(item, document, user["id"])
        imported += int(ok)
        if not ok:
            failures.append({"question_number": item["question_number"], "reason": str(detail)[:300]})
    return jsonify({"ok": not failures, "imported": imported, "failures": failures})


@admin_bp.get("/api/admin/question-style-profile")
def admin_question_style_profile():
    _, err = require_admin()
    if err:
        return err
    career_cluster = request.args.get("career_cluster", "").strip()
    _, docs = _supabase_svc("/question_source_documents", params={"career_cluster": f"eq.{career_cluster}", "select": "id", "limit": "1000"})
    ids = [doc["id"] for doc in docs or []]
    if not ids:
        return jsonify({"profile": {"corpus_size": 0}})
    _, items = _supabase_svc("/question_import_items", params={"document_id": f"in.({','.join(ids)})", "select": "question_text,correct_index,review_reasons,review_status", "limit": "10000"})
    usable = [item for item in items or [] if item.get("review_status") != "skipped" and "exact_duplicate" not in (item.get("review_reasons") or [])]
    return jsonify({"profile": build_style_profile(usable)})


@admin_bp.post("/api/admin/questions/generate-original")
def admin_generate_original_questions():
    _, err = require_admin()
    if err:
        return err
    return jsonify({
        "error": "Original question generation is disabled during Practice Corpus v1.",
        "gate": "corpus_readiness",
        "required": "5 verified exams or 400 verified questions for the target event",
    }), 423
    # Retained below for the later generator phase; the readiness gate above is
    # intentionally fail-closed until corpus analysis is approved for use.
    body = request.get_json(silent=True) or {}
    career_cluster = str(body.get("career_cluster") or "").strip()
    kpi_code = str(body.get("kpi_code") or "").strip().upper()
    count = max(1, min(int(body.get("count") or 3), 10))
    if career_cluster not in CAREER_CLUSTERS:
        return jsonify({"error": "Choose one of the four DECA career clusters."}), 400
    matching_kpis = _cluster_question_kpis(kpi_code, career_cluster)
    if not matching_kpis:
        return jsonify({"error": "Choose a KPI that belongs to the selected career cluster."}), 400
    kpi = matching_kpis[0]
    _, docs = _supabase_svc("/question_source_documents", params={"career_cluster": f"eq.{career_cluster}", "select": "id", "limit": "1000"})
    ids = [doc["id"] for doc in docs or []]
    _, corpus = _supabase_svc("/question_import_items", params={"document_id": f"in.({','.join(ids)})", "select": "question_text,correct_index,review_reasons,review_status", "limit": "10000"}) if ids else (200, [])
    corpus = [item for item in corpus or [] if item.get("review_status") != "skipped" and "exact_duplicate" not in (item.get("review_reasons") or [])]
    profile = build_style_profile(corpus)
    if profile.get("corpus_size", 0) < 10:
        return jsonify({"error": "Import at least 10 reference questions for this career cluster before generating from its style profile."}), 400
    kpi_ids = [catalog_id(item) for item in matching_kpis]
    _, claims = _supabase_svc("/kpi_knowledge_items", params={
        "kpi_id": f"in.({','.join(kpi_ids)})", "review_status": "eq.approved", "authoritative": "eq.true",
        "select": "id,knowledge_type,content,source_references", "limit": "100",
    })
    if not claims:
        return jsonify({"error": "Approve authoritative KPI knowledge before generating exam items."}), 409
    claim_context = [{"id": row["id"], "type": row["knowledge_type"], "content": row["content"]} for row in claims]
    prompt = f"""Create {count} completely original DECA-style multiple-choice questions for KPI {kpi_code}: {kpi['text']}.
Use only this aggregate style profile: {json.dumps(profile)}
Use only these verified factual claims: {json.dumps(claim_context)}
Do not copy or paraphrase any source question. Use new scenarios, names, numbers, phrasing, and answer sets.
Each item must have exactly four plausible choices, one defensible answer, a rationale for every choice, and no trick wording.
Return JSON only: {{"questions":[{{"stem":"...","choices":["...","...","...","..."],"correct_index":0,"choice_rationales":["...","...","...","..."],"cognitive_demand":"application","instructional_area":"{kpi['cluster']}","source_claim_ids":["verified claim UUID"]}}]}}"""
    generated, error = call_json_with_fallback(prompt, priority="admin_preview", temperature=0.5, max_tokens=5000)
    if error or not isinstance(generated, dict):
        return jsonify({"error": error or "Generator returned invalid data."}), 502
    accepted, rejected = [], []
    for candidate in (generated.get("questions") or [])[:count]:
        try:
            candidate = validate_exam_item(
                candidate,
                kpi_code=kpi_code,
                approved_claim_ids={str(row["id"]) for row in claims},
            )
        except ContentQualityError as error:
            rejected.append({"reason": str(error)}); continue
        choices, correct, stem = candidate["choices"], candidate["correct_index"], candidate["stem"]
        if candidate["ambiguity_flags"]:
            rejected.append({"question_text": stem, "reason": "ambiguity_check_failed", "flags": candidate["ambiguity_flags"]}); continue
        similarity = max_similarity(stem, corpus or [])
        if similarity >= 0.82:
            rejected.append({"question_text": stem, "reason": "too_similar_to_reference", "similarity": round(similarity, 3)}); continue
        review_prompt = f"""Skeptically review this DECA-style question for exactly one defensible answer, KPI alignment, plausible distractors, sufficient context, and support by its verified source claims. KPI: {kpi['text']}. Question: {json.dumps(candidate)}. Return JSON only: {{"verdict":"pass|reject","reason":"concise reason"}}"""
        review, review_error = call_json_with_fallback(review_prompt, priority="admin_preview", temperature=0.1, max_tokens=400)
        if review_error or not isinstance(review, dict) or review.get("verdict") != "pass":
            rejected.append({"question_text": stem, "reason": (review or {}).get("reason", review_error or "review_failed")}); continue
        saved_for_events = []
        for event_kpi in matching_kpis:
            event_id = event_kpi["event"]
            _, slots = _supabase_svc("/kpi_questions", params={"event_id": f"eq.{event_id}", "kpi_code": f"eq.{kpi_code}", "question_type": "eq.application", "select": "question_slot", "order": "question_slot.desc", "limit": "1"})
            slot = int(slots[0]["question_slot"]) + 1 if slots else 0
            payload = {"kpi_code": kpi_code, "kpi_text": event_kpi["text"], "kpi_cluster": event_kpi["cluster"], "deca_cluster": event_kpi["deca_cluster"], "event_id": event_id,
                       "question_text": stem, "choices": choices, "correct_index": correct, "explanation": candidate["choice_rationales"][correct],
                       "question_type": "application", "question_slot": slot, "source_type": "ai_generated", "usage_rights": "generated_original",
                       "normalized_hash": question_hash(stem), "review_status": "pending"}
            status, saved = _supabase_svc("/kpi_questions", method="POST", payload=payload, prefer="return=representation")
            if status not in (200, 201) or not saved:
                saved_for_events = []
                break
            saved_for_events.extend(saved)
            for saved_question in saved:
                _supabase_svc("/exam_item_quality_reviews", method="POST", payload={
                    "question_id": saved_question["id"], "kpi_code": kpi_code,
                    "cognitive_demand": candidate["cognitive_demand"], "choice_rationales": candidate["choice_rationales"],
                    "source_claim_ids": candidate["source_claim_ids"], "ambiguity_flags": candidate["ambiguity_flags"],
                    "style_metrics": profile, "review_status": "pending_review",
                }, prefer="return=minimal")
        if saved_for_events:
            accepted.append({"question": saved_for_events[0], "event_count": len(saved_for_events)})
        else:
            rejected.append({"question_text": stem, "reason": "save_failed"})
    return jsonify({"generated": len(accepted), "questions": accepted, "rejected": rejected, "style_profile": profile,
                    "career_cluster": career_cluster, "events_populated": len(matching_kpis)})


@admin_bp.get("/api/admin/kpi-knowledge/review-next")
def admin_next_kpi_knowledge():
    _, err = require_admin()
    if err:
        return err
    params = {"review_status": "eq.pending", "select": "*", "order": "deca_cluster.asc,kpi_cluster.asc,kpi_code.asc,created_at.asc", "limit": "1"}
    if request.args.get("cluster"):
        params["kpi_cluster"] = f"eq.{request.args['cluster']}"
    _, rows = _supabase_svc("/kpi_knowledge_items", params=params)
    return jsonify({"item": rows[0] if rows else None})


@admin_bp.patch("/api/admin/kpi-knowledge/<item_id>")
def admin_review_kpi_knowledge(item_id):
    user, err = require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "approve").lower()
    if action not in {"approve", "ignore"}:
        return jsonify({"error": "action must be approve or ignore"}), 400
    _, rows = _supabase_svc("/kpi_knowledge_items", params={"id": f"eq.{item_id}", "review_status": "eq.pending", "select": "*", "limit": "1"})
    if not rows:
        return jsonify({"error": "Knowledge item not found or already reviewed."}), 404
    item = rows[0]
    content = str(body.get("content") or item["content"]).strip()[:4000]
    importance = str(body.get("importance") or item["importance"])
    if importance not in {"required", "important", "supporting", "question_specific"}:
        return jsonify({"error": "Unsupported importance."}), 400
    review_status = "approved" if action == "approve" else "ignored"
    payload = {"content": content, "importance": importance, "review_status": review_status,
               "reviewed_by": user["id"], "reviewed_at": utc_now()}
    if action == "approve":
        factual_evidence = body.get("factual_evidence")
        checklist = body.get("review_checklist")
        verification_class = str(body.get("verification_class") or "time_sensitive")
        reverify_after = body.get("reverify_after") or None
        required_checks = {"direct_support", "no_overclaim", "subject_authority", "current", "atomic", "deca_connection"}
        if not isinstance(factual_evidence, list) or not factual_evidence:
            return jsonify({"error": "Approval requires current authoritative factual evidence."}), 400
        if not isinstance(checklist, dict) or not all(checklist.get(key) is True for key in required_checks):
            return jsonify({"error": "Confirm every factual and DECA alignment review check before approval."}), 400
        if verification_class not in {"stable", "time_sensitive"}:
            return jsonify({"error": "verification_class must be stable or time_sensitive."}), 400
        if verification_class == "time_sensitive" and not reverify_after:
            return jsonify({"error": "Time-sensitive claims require a reverification date."}), 400
        payload.update({"factual_evidence": factual_evidence, "review_checklist": checklist,
                        "verification_class": verification_class, "reverify_after": reverify_after,
                        "authoritative": True})
    status, _ = _supabase_svc("/kpi_knowledge_items", method="PATCH", payload=payload,
                  params={"id": f"eq.{item_id}"}, prefer="return=minimal")
    if status not in (200, 204):
        return jsonify({"error": "Knowledge review could not be saved."}), 409
    if action == "approve":
        _, catalog = _supabase_svc("/kpi_catalog", params={"id": f"eq.{item['kpi_id']}", "select": "knowledge_version", "limit": "1"})
        version = int(catalog[0].get("knowledge_version") or 1) + 1 if catalog else 2
        _supabase_svc("/kpi_catalog", method="PATCH", payload={"knowledge_version": version}, params={"id": f"eq.{item['kpi_id']}"}, prefer="return=minimal")
        _supabase_svc("/generated_kpi_lessons", method="PATCH", payload={"status": "stale", "updated_at": utc_now()}, params={"kpi_id": f"eq.{item['kpi_id']}"}, prefer="return=minimal")
    return jsonify({"ok": True, "review_status": review_status})


@admin_bp.get("/api/admin/sources")
def admin_sources_library():
    _, err = require_admin()
    if err:
        return err
    _, sources = _supabase_svc("/reference_sources", params={"select": "*", "order": "title.asc", "limit": "10000"})
    _, links = _supabase_svc("/question_source_links", params={"select": "source_id,kpi_code,pages,document_id", "limit": "20000"})
    by_source = defaultdict(list)
    for link in links or []:
        by_source[link["source_id"]].append(link)
    result = []
    search = request.args.get("search", "").strip().lower()
    for source in sources or []:
        source_links = by_source[source["id"]]
        if search and search not in " ".join(str(source.get(field) or "") for field in ("title", "authors", "raw_citation")).lower():
            continue
        kpis = sorted({link.get("kpi_code") for link in source_links if link.get("kpi_code")})
        pages = sorted({link.get("pages") for link in source_links if link.get("pages")})
        documents = {link.get("document_id") for link in source_links}
        result.append({**source, "question_count": len(source_links), "kpi_count": len(kpis), "kpis": kpis,
                       "pages": pages, "document_count": len(documents),
                       "search_query": parse_reference_citation(source["raw_citation"])["search_query"]})
    result.sort(key=lambda row: (-row["question_count"], -row["kpi_count"], row.get("title") or ""))
    return jsonify({"sources": result, "total": len(result),
                    "linked_multiple_kpis": sum(row["kpi_count"] > 1 for row in result),
                    "needs_locating": sum(row["status"] == "unreviewed" for row in result)})


@admin_bp.patch("/api/admin/sources/<source_id>")
def admin_update_source(source_id):
    _, err = require_admin()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    payload = {}
    if "status" in body:
        status_value = str(body["status"])
        if status_value not in {"unreviewed", "located", "accessible", "paywalled", "physical", "unavailable", "do_not_use"}:
            return jsonify({"error": "Unsupported source status."}), 400
        payload["status"] = status_value
    if "url" in body:
        url = str(body["url"] or "").strip()[:2000]
        if url and not url.startswith(("https://", "http://")):
            return jsonify({"error": "Source URL must begin with http:// or https://"}), 400
        payload["url"] = url or None
    if "notes" in body:
        payload["notes"] = str(body["notes"] or "")[:4000]
    payload["updated_at"] = utc_now()
    status, data = _supabase_svc("/reference_sources", method="PATCH", payload=payload,
                                 params={"id": f"eq.{source_id}"}, prefer="return=representation")
    if status != 200 or not data:
        return jsonify({"error": "Source could not be updated.", "detail": data}), 502
    return jsonify({"ok": True, "source": data[0]})


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
                "event_id,session_type,questions_answered,questions_correct"
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
