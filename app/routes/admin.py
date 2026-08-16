from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from ..auth_utils import get_current_user, is_admin
from ..content_ops import ARCHETYPES, catalog_id, launch_batch, sync_kpi_catalog, utc_now
from ..audit_ops import launch_audit_batch, select_audit_kpis
from ..db import supabase_admin_request
from ..learn_helpers import _load_all_kpis, _supabase_svc, KPI_DIR, _save_questions_supabase
from werkzeug.utils import secure_filename
import json
import hashlib
from pathlib import Path

from ..ai import call_json_with_fallback
from ..question_ingestion import assess_item, build_style_profile, extract_pdf_questions, max_similarity, parse_reference_citation, question_hash

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
    failed_status, failed = _supabase_svc(
        "/kpi_classification_jobs",
        params={"status": "eq.failed", "select": "id", "limit": "10000"},
    )
    return jsonify({
        "classification": _classification_summary(),
        "generated_content": _generated_content_summary(),
        "failed_processing": len(failed) if failed_status == 200 and isinstance(failed, list) else 0,
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
    return jsonify({"item": item})


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
    status, rows = _supabase_svc(
        "/kpi_classification_jobs",
        params={"status": "eq.failed", "select": "kpi_id", "order": "completed_at.asc", "limit": "20"},
    )
    if status != 200 or not isinstance(rows, list):
        return jsonify({"error": "Failed jobs could not be loaded."}), 502
    kpi_ids = list(dict.fromkeys(row["kpi_id"] for row in rows))
    if not kpi_ids:
        return jsonify({"ok": True, "queued": 0})
    try:
        batch = _create_classification_batch(user["id"], kpi_ids)
        return jsonify({"ok": True, "queued": len(kpi_ids), "batch": batch}), 202
    except Exception as error:
        return jsonify({"error": "Retry batch could not be started.", "detail": str(error)}), 502


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
        return jsonify({"item": None})
    item = rows[0]
    catalog_status, catalog = _supabase_svc(
        "/kpi_catalog", params={"id": f"eq.{item['kpi_id']}", "select": "*", "limit": "1"}
    )
    item["kpi"] = catalog[0] if catalog_status == 200 and isinstance(catalog, list) and catalog else {}
    return jsonify({"item": item, "remaining": _classification_summary()["needs_review"]})


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
            prefer="return=minimal",
        )
        if status not in (200, 204):
            return jsonify({"error": "Classification could not be deferred.", "detail": data}), 502
        return jsonify({"ok": True})
    if action != "approve":
        return jsonify({"error": "action must be approve or skip"}), 400
    payload = {
        "review_status": "approved",
        "reviewed_by": user["id"],
        "reviewed_at": utc_now(),
        "updated_at": utc_now(),
        "review_deferred_at": None,
    }
    selected = str(body.get("primary_archetype") or "").strip()
    if selected and selected not in ARCHETYPES:
        return jsonify({"error": "Unsupported primary_archetype"}), 400
    if selected:
        payload["primary_archetype"] = selected
        payload["manual_override"] = True
    status, data = _supabase_svc(
        "/kpi_classifications", method="PATCH", payload=payload,
        params={"kpi_id": f"eq.{kpi_id}", "review_status": "eq.needs_review"},
        prefer="return=representation",
    )
    if status != 200:
        return jsonify({"error": "Classification review could not be saved.", "detail": data}), 502
    return jsonify({"ok": True, "classification": data[0] if isinstance(data, list) and data else None})


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


def _question_kpi(kpi_code: str, event_id: str) -> dict | None:
    return next((kpi for kpi in _load_all_kpis()[0]
                 if kpi.get("code") == kpi_code and kpi.get("event") == event_id), None)


def _import_staged_question(item: dict, document: dict, user_id: str) -> tuple[bool, object]:
    if document.get("usage_rights") != "licensed_for_student_use":
        return False, "Reference-only sources cannot be published to Practice Mode."
    kpi = _question_kpi(item.get("kpi_code", ""), document.get("event_id", ""))
    if not kpi:
        return False, "Choose a KPI that belongs to the selected event."
    if item.get("correct_index") not in range(4) or len(item.get("choices") or []) != 4:
        return False, "A complete answer key and four choices are required."
    _, slots = _supabase_svc("/kpi_questions", params={
        "event_id": f"eq.{document['event_id']}", "kpi_code": f"eq.{item['kpi_code']}",
        "question_type": "eq.application", "select": "question_slot", "order": "question_slot.desc", "limit": "1",
    })
    slot = int(slots[0]["question_slot"]) + 1 if slots else 0
    payload = {
        "kpi_code": item["kpi_code"], "kpi_text": kpi.get("text", ""),
        "kpi_cluster": kpi.get("cluster", ""), "deca_cluster": kpi.get("deca_cluster", ""),
        "event_id": document["event_id"], "question_text": item["question_text"],
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
    _supabase_svc("/question_import_items", method="PATCH", payload={
        "review_status": "imported", "imported_question_id": data[0]["id"],
        "reviewed_by": user_id, "reviewed_at": utc_now(),
    }, params={"id": f"eq.{item['id']}"}, prefer="return=minimal")
    _supabase_svc("/question_source_links", method="PATCH", payload={"imported_question_id": data[0]["id"]},
                  params={"import_item_id": f"eq.{item['id']}"}, prefer="return=minimal")
    return True, data[0]


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
                "kpi_id": f"{document['event_id']}:{item['kpi_code']}" if item.get("kpi_code") else None,
                "kpi_code": item.get("kpi_code", ""), "pages": parsed["pages"], "raw_citation": raw,
            }, params={"on_conflict": "source_id,import_item_id"}, prefer="resolution=ignore-duplicates,return=minimal")


@admin_bp.post("/api/admin/question-imports")
def admin_upload_question_pdf():
    user, err = require_admin()
    if err:
        return err
    uploaded = request.files.get("file")
    if not uploaded or not (uploaded.filename or "").lower().endswith(".pdf"):
        return jsonify({"error": "Choose a PDF file."}), 400
    file_bytes = uploaded.read()
    if not file_bytes or len(file_bytes) > 20 * 1024 * 1024:
        return jsonify({"error": "PDF must be between 1 byte and 20 MB."}), 400
    usage_rights = request.form.get("usage_rights", "reference_only")
    source_type = request.form.get("source_type", "other")
    if usage_rights not in {"reference_only", "licensed_for_student_use"}:
        return jsonify({"error": "Unsupported usage rights."}), 400
    if source_type not in {"deca_sample", "owned", "licensed", "other"}:
        return jsonify({"error": "Unsupported source type."}), 400
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
        "career_cluster": request.form.get("career_cluster", "")[:120],
        "event_id": request.form.get("event_id", "")[:120],
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
    event_id = doc_payload["event_id"]
    kpi_lookup = {(kpi.get("event"), kpi.get("code")): kpi for kpi in _load_all_kpis()[0]}
    assessed = []
    for question in questions:
        matched_kpi = kpi_lookup.get((event_id, question.get("kpi_code")))
        question["kpi_cluster"] = matched_kpi.get("cluster", "") if matched_kpi else ""
        question["deca_cluster"] = matched_kpi.get("deca_cluster", "") if matched_kpi else doc_payload["career_cluster"]
        item = assess_item(question, bank or [], assessed, usage_rights == "licensed_for_student_use")
        if question.get("kpi_code") and not matched_kpi:
            item["review_reasons"].append("kpi_not_in_selected_event")
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
        knowledge_rows.append({
            "kpi_id": f"{event_id}:{item['kpi_code']}", "kpi_code": item["kpi_code"],
            "kpi_cluster": item["kpi_cluster"], "deca_cluster": item["deca_cluster"],
            "knowledge_type": "source_explanation", "content": item["explanation"],
            "importance": "important", "content_hash": hashlib.sha256(item["explanation"].lower().encode("utf-8")).hexdigest(),
            "source_document_id": document["id"], "source_import_item_id": item["id"],
            "source_references": item.get("source_references") or [],
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
    _, pending = _supabase_svc("/question_import_items", params={"review_status": "eq.pending", "select": "id", "limit": "10000"})
    _, clustered = _supabase_svc("/question_import_items", params={"select": "kpi_cluster,deca_cluster", "limit": "10000"})
    cluster_breakdown = defaultdict(int)
    for item in clustered or []:
        cluster_breakdown[item.get("kpi_cluster") or "Unassigned"] += 1
    _, knowledge = _supabase_svc("/kpi_knowledge_items", params={"review_status": "eq.pending", "select": "id", "limit": "10000"})
    return jsonify({"documents": docs or [], "pending": len(pending or []),
                    "cluster_breakdown": dict(sorted(cluster_breakdown.items())), "knowledge_pending": len(knowledge or [])})


@admin_bp.get("/api/admin/question-imports/review-next")
def admin_next_question_import():
    _, err = require_admin()
    if err:
        return err
    _, rows = _supabase_svc("/question_import_items", params={
        "review_status": "eq.pending", "select": "*", "order": "created_at.asc,question_number.asc", "limit": "1",
    })
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
    event_id = request.args.get("event_id", "").strip()
    _, docs = _supabase_svc("/question_source_documents", params={"event_id": f"eq.{event_id}", "select": "id", "limit": "1000"})
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
    body = request.get_json(silent=True) or {}
    event_id = str(body.get("event_id") or "").strip()
    kpi_code = str(body.get("kpi_code") or "").strip().upper()
    count = max(1, min(int(body.get("count") or 3), 10))
    kpi = _question_kpi(kpi_code, event_id)
    if not kpi:
        return jsonify({"error": "Choose a KPI that belongs to the selected event."}), 400
    _, docs = _supabase_svc("/question_source_documents", params={"event_id": f"eq.{event_id}", "select": "id", "limit": "1000"})
    ids = [doc["id"] for doc in docs or []]
    _, corpus = _supabase_svc("/question_import_items", params={"document_id": f"in.({','.join(ids)})", "select": "question_text,correct_index,review_reasons,review_status", "limit": "10000"}) if ids else (200, [])
    corpus = [item for item in corpus or [] if item.get("review_status") != "skipped" and "exact_duplicate" not in (item.get("review_reasons") or [])]
    profile = build_style_profile(corpus)
    if profile.get("corpus_size", 0) < 10:
        return jsonify({"error": "Import at least 10 reference questions for this event before generating from its style profile."}), 400
    prompt = f"""Create {count} completely original DECA-style multiple-choice questions for KPI {kpi_code}: {kpi['text']}.
Use only this aggregate style profile: {json.dumps(profile)}
Do not copy or paraphrase any source question. Use new scenarios, names, numbers, phrasing, and answer sets.
Each item must test application or analysis, have exactly four plausible choices, one defensible answer, concise rationale, and no trick wording.
Return JSON only: {{"questions":[{{"question_text":"...","choices":["...","...","...","..."],"correct_index":0,"explanation":"..."}}]}}"""
    generated, error = call_json_with_fallback(prompt, priority="admin_preview", temperature=0.5, max_tokens=5000)
    if error or not isinstance(generated, dict):
        return jsonify({"error": error or "Generator returned invalid data."}), 502
    accepted, rejected = [], []
    for candidate in (generated.get("questions") or [])[:count]:
        choices = candidate.get("choices") if isinstance(candidate, dict) else None
        correct = candidate.get("correct_index") if isinstance(candidate, dict) else None
        stem = str(candidate.get("question_text") or "").strip() if isinstance(candidate, dict) else ""
        if not stem or not isinstance(choices, list) or len(choices) != 4 or correct not in range(4):
            rejected.append({"reason": "invalid_structure"}); continue
        similarity = max_similarity(stem, corpus or [])
        if similarity >= 0.82:
            rejected.append({"question_text": stem, "reason": "too_similar_to_reference", "similarity": round(similarity, 3)}); continue
        review_prompt = f"""Review this DECA-style question for one correct answer, KPI alignment, plausible distractors, sufficient context, factual accuracy, and no giveaway. KPI: {kpi['text']}. Question: {json.dumps(candidate)}. Return JSON only: {{"verdict":"pass|reject","reason":"concise reason"}}"""
        review, review_error = call_json_with_fallback(review_prompt, priority="admin_preview", temperature=0.1, max_tokens=400)
        if review_error or not isinstance(review, dict) or review.get("verdict") != "pass":
            rejected.append({"question_text": stem, "reason": (review or {}).get("reason", review_error or "review_failed")}); continue
        _, slots = _supabase_svc("/kpi_questions", params={"event_id": f"eq.{event_id}", "kpi_code": f"eq.{kpi_code}", "question_type": "eq.application", "select": "question_slot", "order": "question_slot.desc", "limit": "1"})
        slot = int(slots[0]["question_slot"]) + 1 if slots else 0
        payload = {"kpi_code": kpi_code, "kpi_text": kpi["text"], "kpi_cluster": kpi["cluster"], "deca_cluster": kpi["deca_cluster"], "event_id": event_id,
                   "question_text": stem, "choices": choices, "correct_index": correct, "explanation": str(candidate.get("explanation") or ""),
                   "question_type": "application", "question_slot": slot, "source_type": "ai_generated", "usage_rights": "generated_original",
                   "normalized_hash": question_hash(stem), "review_status": "approved"}
        status, saved = _supabase_svc("/kpi_questions", method="POST", payload=payload, prefer="return=representation")
        if status in (200, 201) and saved:
            accepted.append(saved[0])
        else:
            rejected.append({"question_text": stem, "reason": "save_failed"})
    return jsonify({"generated": len(accepted), "questions": accepted, "rejected": rejected, "style_profile": profile})


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
    _supabase_svc("/kpi_knowledge_items", method="PATCH", payload={"content": content, "importance": importance,
                  "review_status": review_status, "reviewed_by": user["id"], "reviewed_at": utc_now()},
                  params={"id": f"eq.{item_id}"}, prefer="return=minimal")
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
