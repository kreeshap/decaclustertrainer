"""Persistent KPI classification pipeline used by Admin Content Operations."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import threading

from .ai import call_cloudflare, call_gemini_json, call_groq, call_mistral
from .ai_coordinator import coordinator
from .config import GEMINI_MODEL
from .learn_helpers import _load_all_kpis, _supabase_svc
from .lesson_design import classify_kpi


CLASSIFIER_VERSION = "content-classifier-2026-08-v1"
CLASSIFICATION_SCHEMA_VERSION = 1
GROQ_CLASSIFIER_MODEL = "llama-3.3-70b-versatile"

SKILL_TYPES = {"concept", "decision", "communication", "process", "calculation_data", "analysis"}
COMPLEXITIES = {"quick", "standard", "deep"}
ARCHETYPES = {
    "concept_discovery", "decision_lab", "diagnose_problem", "build_process",
    "tradeoff_challenge", "communication_coach", "numbers_lab",
}
LEARNER_ACTIONS = {
    "identify", "classify", "predict", "choose", "rank", "sequence",
    "calculate", "diagnose", "compare", "respond", "justify",
}
DECA_ACTIONS = {
    "explain", "identify", "demonstrate", "analyze", "calculate",
    "recommend", "justify", "respond", "develop", "evaluate",
}
DECA_ACTION_ALIASES = {
    "apply": "demonstrate",
    "assess": "evaluate",
    "comply": "demonstrate",
    "decide": "recommend",
    "describe": "explain",
}

COMPARE_FIELDS = ("skill_type", "complexity", "primary_archetype", "learner_action", "deca_action")
ACTION_COMPATIBILITY = {
    "identify": {"identify", "explain"},
    "classify": {"identify", "analyze"},
    "predict": {"analyze", "evaluate"},
    "choose": {"recommend", "evaluate"},
    "rank": {"evaluate", "recommend"},
    "sequence": {"demonstrate", "develop"},
    "calculate": {"calculate", "analyze"},
    "diagnose": {"analyze", "evaluate"},
    "compare": {"analyze", "evaluate", "explain"},
    "respond": {"respond", "demonstrate"},
    "justify": {"justify", "recommend", "evaluate"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def catalog_id(kpi: dict) -> str:
    return f"{kpi.get('event', '')}:{kpi.get('code', '')}"


def sync_kpi_catalog() -> list[dict]:
    kpis, events = _load_all_kpis()
    event_rows = [
        {
            "id": event.get("id", ""),
            "name": event.get("name", ""),
            "cluster": event.get("cluster", ""),
            "is_beta": True,
        }
        for event in events
        if event.get("id") and event.get("name") and event.get("cluster")
    ]
    if event_rows:
        status, data = _supabase_svc(
            "/deca_events",
            method="POST",
            payload=event_rows,
            params={"on_conflict": "id"},
            prefer="resolution=merge-duplicates,return=minimal",
        )
        if status not in (200, 201, 204):
            raise RuntimeError(f"DECA event sync failed: {data}")

    rows = [
        {
            "id": catalog_id(kpi),
            "event_id": kpi.get("event", ""),
            "code": kpi.get("code", ""),
            "name": kpi.get("text", ""),
            "cluster": kpi.get("cluster", ""),
            "instructional_area": kpi.get("deca_cluster", ""),
            "standard": kpi.get("standard", ""),
            "source_updated_at": utc_now(),
        }
        for kpi in kpis
        if kpi.get("event") and kpi.get("code") and kpi.get("text")
    ]
    if rows:
        status, data = _supabase_svc(
            "/kpi_catalog",
            method="POST",
            payload=rows,
            params={"on_conflict": "id"},
            prefer="resolution=merge-duplicates,return=minimal",
        )
        if status not in (200, 201, 204):
            raise RuntimeError(f"KPI catalog sync failed: {data}")
    return rows


def get_approved_instructional_plan(kpi_id: str) -> dict | None:
    status, rows = _supabase_svc(
        "/kpi_classifications",
        params={
            "kpi_id": f"eq.{kpi_id}",
            "review_status": "in.(auto_approved,approved)",
            "select": "skill_type,complexity,primary_archetype,learner_action,deca_action,recommended_interactions",
            "limit": "1",
        },
    )
    if status != 200 or not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    complexity = row["complexity"]
    return {
        **row,
        "target_minutes": {"quick": "2-3", "standard": "3-5", "deep": "5-7"}[complexity],
        "required_block_count": {"quick": 2, "standard": 3, "deep": 4}[complexity],
        "vocab_mode": "embedded" if complexity == "quick" else "preteach",
        "vocab_count": {"quick": 3, "standard": 4, "deep": 5}[complexity],
    }


def _classification_prompt(kpi: dict) -> str:
    return f"""You are an instructional classification engine for DECA performance indicators.
Do not write a lesson. Classify the cognitive demand of the KPI, not merely its cluster or first verb.

Allowed skill_type: concept, decision, communication, process, calculation_data, analysis
Allowed complexity: quick, standard, deep
Allowed primary_archetype and secondary_archetype: concept_discovery, decision_lab, diagnose_problem, build_process, tradeoff_challenge, communication_coach, numbers_lab
Allowed learner_action: identify, classify, predict, choose, rank, sequence, calculate, diagnose, compare, respond, justify
Allowed deca_action: explain, identify, demonstrate, analyze, calculate, recommend, justify, respond, develop, evaluate
Allowed certainty: high, medium, low

KPI code: {kpi['code']}
KPI: {kpi['name']}
Cluster: {kpi.get('cluster', '')}
Instructional area: {kpi.get('instructional_area', '')}
Standard: {kpi.get('standard', '')}

Return only JSON:
{{
  "skill_type": "allowed value",
  "complexity": "allowed value",
  "primary_archetype": "allowed value",
  "secondary_archetype": null,
  "learner_action": "allowed value",
  "deca_action": "allowed value",
  "recommended_interactions": ["two to four concise interaction names"],
  "classification_reason": "One concise explanation of the cognitive demand.",
  "certainty": "high|medium|low",
  "ambiguity_reason": null,
  "alternative_archetype": null,
  "field_confidence": {{"skill_type":0.0,"complexity":0.0,"primary_archetype":0.0,"learner_action":0.0,"deca_action":0.0}}
}}"""


def _validate_classification(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("classification must be an object")
    result = dict(raw)
    enum_fields = {
        "skill_type": SKILL_TYPES,
        "complexity": COMPLEXITIES,
        "primary_archetype": ARCHETYPES,
        "learner_action": LEARNER_ACTIONS,
        "deca_action": DECA_ACTIONS,
        "certainty": {"high", "medium", "low"},
    }
    for field, allowed in enum_fields.items():
        value = str(result.get(field) or "").strip().lower()
        if field == "deca_action":
            value = DECA_ACTION_ALIASES.get(value, value)
        if value not in allowed:
            raise ValueError(f"unsupported {field}: {value}")
        result[field] = value
    secondary = result.get("secondary_archetype")
    if secondary is not None:
        secondary = str(secondary).strip().lower()
        if secondary not in ARCHETYPES:
            raise ValueError("unsupported secondary_archetype")
    alternative = result.get("alternative_archetype")
    if alternative is not None:
        alternative = str(alternative).strip().lower()
        if alternative not in ARCHETYPES:
            raise ValueError("unsupported alternative_archetype")
    interactions = result.get("recommended_interactions")
    if not isinstance(interactions, list) or not 1 <= len(interactions) <= 4:
        raise ValueError("recommended_interactions must contain one to four values")
    interactions = [str(value).strip().lower() for value in interactions if str(value).strip()]
    reason = str(result.get("classification_reason") or "").strip()
    if len(reason) < 20:
        raise ValueError("classification_reason is too short")
    result.update(
        secondary_archetype=secondary,
        alternative_archetype=alternative,
        recommended_interactions=interactions,
        classification_reason=reason,
        ambiguity_reason=str(result.get("ambiguity_reason") or "").strip() or None,
    )
    confidence = result.get("field_confidence") or {}
    result["field_confidence"] = {
        field: max(0.0, min(1.0, float(confidence.get(field, 0))))
        for field in ("skill_type", "complexity", "primary_archetype", "learner_action", "deca_action")
    }
    return result


def classify_with_ai(kpi: dict) -> tuple[dict, str]:
    prompt = _classification_prompt(kpi)
    messages = [{"role": "user", "content": prompt}]
    raw, error, model = coordinator.run([
        ("Groq", lambda: call_groq(messages, model=GROQ_CLASSIFIER_MODEL, temperature=0.1, max_tokens=1200)),
        ("Mistral", lambda: call_mistral(messages, temperature=0.1, max_tokens=1200)),
        ("Cloudflare", lambda: call_cloudflare(messages, temperature=0.1, max_tokens=1200)),
        ("Gemini", lambda: call_gemini_json(prompt, max_tokens=1200, temperature=0.1)),
    ], "classification")
    if error:
        raise RuntimeError(error)
    return _validate_classification(raw), model or GEMINI_MODEL


def snapshot_fields(row: dict) -> dict:
    return {field: row.get(field) for field in COMPARE_FIELDS}


def fields_differ(left: dict, right: dict) -> bool:
    return any(left.get(field) != right.get(field) for field in COMPARE_FIELDS)


def compatibility_issues(classification: dict) -> list[str]:
    issues = []
    allowed = ACTION_COMPATIBILITY.get(classification.get("learner_action"), set())
    if classification.get("deca_action") not in allowed:
        issues.append("learner_action and deca_action are incompatible")
    return issues


def merge_classification(base: dict, overlay: dict | None, reason: str | None = None) -> dict:
    candidate = {**base, **(overlay or {})}
    if reason and len(reason.strip()) >= 20:
        candidate["classification_reason"] = reason
    if not candidate.get("recommended_interactions"):
        candidate["recommended_interactions"] = base.get("recommended_interactions") or ["choose"]
    if not candidate.get("classification_reason"):
        candidate["classification_reason"] = base.get("classification_reason") or "Classification updated during review."
    if not candidate.get("certainty"):
        candidate["certainty"] = base.get("certainty") or "medium"
    if "field_confidence" not in candidate:
        candidate["field_confidence"] = base.get("field_confidence") or {}
    return _validate_classification(candidate)


def deterministic_disagreements(kpi: dict, ai_result: dict) -> tuple[dict, list[str]]:
    fallback = classify_kpi(kpi["name"])
    disagreements = [field for field in COMPARE_FIELDS if ai_result.get(field) != fallback.get(field)]
    return fallback, disagreements


def sanitize_reviewer(raw: object, classification: dict) -> dict:
    """Drop contradictory or malformed reviewer output before it reaches admins."""
    if not isinstance(raw, dict):
        return {
            "verdict": "uncertain",
            "issues": ["reviewer_malformed"],
            "corrected": None,
            "confidence": 0.0,
            "recommended_archetype": None,
            "reason": "Reviewer returned invalid data",
        }
    verdict = str(raw.get("verdict") or "uncertain").strip().lower()
    if verdict not in {"pass", "correct", "uncertain"}:
        verdict = "uncertain"
    issues = [str(value)[:300] for value in (raw.get("issues") or []) if str(value).strip()][:6]
    reason = str(raw.get("reason") or "").strip() or "No reviewer reason supplied."
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence") or 0)))
    except (TypeError, ValueError):
        confidence = 0.0
        issues.append("reviewer_confidence_malformed")
    corrected_raw = raw.get("corrected") if isinstance(raw.get("corrected"), dict) else None
    corrected = None
    recommended_archetype = None
    if verdict == "correct":
        if not corrected_raw:
            verdict = "uncertain"
            issues.append("reviewer correction was missing")
        else:
            try:
                corrected = merge_classification(classification, corrected_raw, reason)
                if not fields_differ(classification, corrected):
                    verdict = "uncertain"
                    issues.append("reviewer criticized the classification but recommended the same values")
                    corrected = None
                elif compatibility_issues(corrected):
                    verdict = "uncertain"
                    issues.extend(compatibility_issues(corrected))
                    issues.append("recommended correction is internally inconsistent")
                    corrected = None
                else:
                    recommended_archetype = corrected["primary_archetype"]
            except (TypeError, ValueError) as error:
                verdict = "uncertain"
                issues.append(f"invalid reviewer correction: {error}")
                corrected = None
    return {
        "verdict": verdict,
        "issues": list(dict.fromkeys(issues)),
        "corrected": {field: corrected[field] for field in (*COMPARE_FIELDS, "recommended_interactions", "classification_reason", "certainty")} if corrected else None,
        "confidence": confidence,
        "recommended_archetype": recommended_archetype,
        "reason": reason,
    }


def skeptical_review(kpi: dict, classification: dict, deterministic: dict, disagreements: list[str]) -> dict:
    prompt = f"""Act as an adversarial instructional reviewer. Assume the classifier may be wrong and try to prove it.
Check KPI-verb/action alignment, archetype fit, complexity, and contradictions.
If the classification is fine, verdict must be pass and corrected must be null.
If it is materially wrong, verdict must be correct and corrected must be a complete replacement that DIFFERS from the current classification.
Never criticize a field while recommending the same value for that field.

KPI: {kpi['name']}
AI classification: {json.dumps(classification, separators=(',', ':'))}
Deterministic check: {json.dumps(deterministic, separators=(',', ':'))}
Disagreement fields: {json.dumps(disagreements)}

Return only JSON:
{{"verdict":"pass|correct|uncertain","issues":[],"corrected":null,"confidence":0.0,"reason":"Concise reason"}}"""
    messages = [{"role": "user", "content": prompt}]
    raw, error, _ = coordinator.run([
        ("Groq", lambda: call_groq(messages, model=GROQ_CLASSIFIER_MODEL, temperature=0.1, max_tokens=500)),
        ("Mistral", lambda: call_mistral(messages, temperature=0.1, max_tokens=500)),
        ("Cloudflare", lambda: call_cloudflare(messages, temperature=0.1, max_tokens=500)),
        ("Gemini", lambda: call_gemini_json(prompt, max_tokens=500, temperature=0.1)),
    ], "classification")
    if error or not isinstance(raw, dict):
        raw = {"verdict": "uncertain", "issues": ["reviewer_unavailable"], "corrected": None, "confidence": 0.0, "reason": error or "Reviewer returned invalid data"}
    return sanitize_reviewer(raw, classification)


def resolve_classification(classification: dict, reviewer: dict) -> tuple[dict, dict, bool]:
    """Apply a structurally valid repair; escalate only genuine ambiguity or contradictions."""
    reviewer = sanitize_reviewer(reviewer, classification)
    final = dict(classification)
    issues = list(reviewer.get("issues") or [])
    repaired = False
    if reviewer["verdict"] == "correct" and reviewer.get("corrected"):
        try:
            final = merge_classification(classification, reviewer["corrected"], reviewer.get("reason"))
            repaired = fields_differ(classification, final)
            if not repaired:
                issues.append("reviewer criticized the classification but recommended the same values")
        except (TypeError, ValueError) as error:
            issues.append(f"invalid reviewer correction: {error}")
            final = dict(classification)
    elif reviewer["verdict"] == "uncertain":
        if "reviewer could not decide" not in issues:
            issues.append("reviewer could not decide")

    issues.extend(compatibility_issues(final))
    issues = list(dict.fromkeys(issues))
    auto_approve = (reviewer["verdict"] == "pass" and not compatibility_issues(classification)) or (
        repaired and not compatibility_issues(final)
    )
    validator = {
        "issues": issues,
        "repaired": repaired,
        "auto_approve": auto_approve,
        "decision_basis": "reviewer_pass" if reviewer["verdict"] == "pass" else ("valid_repair" if repaired else "manual_review"),
    }
    return final, validator, not auto_approve


def build_review_decision(row: dict) -> dict:
    current = {
        **snapshot_fields(row),
        "secondary_archetype": row.get("secondary_archetype"),
        "recommended_interactions": row.get("recommended_interactions") or [],
        "certainty": row.get("certainty"),
        "classification_reason": row.get("classification_reason"),
    }
    reviewer = sanitize_reviewer(row.get("reviewer_result") or {}, current)
    recommended = None
    if reviewer.get("corrected"):
        try:
            candidate = merge_classification(current, reviewer["corrected"], reviewer.get("reason"))
            if fields_differ(current, candidate) and not compatibility_issues(candidate):
                recommended = snapshot_fields(candidate)
                recommended["recommended_interactions"] = candidate.get("recommended_interactions")
                recommended["certainty"] = candidate.get("certainty")
        except (TypeError, ValueError):
            recommended = None
    deterministic = row.get("deterministic_check") or {}
    if recommended is None:
        try:
            fallback = {field: deterministic.get(field) for field in COMPARE_FIELDS if deterministic.get(field)}
            if fallback:
                candidate = merge_classification(current, fallback, "Deterministic instructional fallback.")
                if fields_differ(current, candidate) and not compatibility_issues(candidate):
                    recommended = snapshot_fields(candidate)
                    recommended["source"] = "deterministic"
        except (TypeError, ValueError):
            recommended = None
    changes = []
    if recommended:
        for field in COMPARE_FIELDS:
            if current.get(field) != recommended.get(field):
                changes.append({"field": field, "from": current.get(field), "to": recommended.get(field)})
    problem_parts = [item for item in (reviewer.get("issues") or []) if item not in {"reviewer could not decide"}]
    if reviewer.get("reason") and reviewer["verdict"] != "pass":
        problem_parts.append(reviewer["reason"])
    elif deterministic.get("issues"):
        problem_parts.extend(str(item) for item in deterministic["issues"])
    elif deterministic.get("disagreements"):
        problem_parts.append("Classifier and deterministic check disagree on " + ", ".join(deterministic["disagreements"]) + ".")
    problem = " ".join(dict.fromkeys(problem_parts)).strip() or "This classification needs a human decision."
    original_ai = deterministic.get("original_ai") or {}
    already_applied_repair = bool(original_ai) and fields_differ(original_ai, current) and not recommended
    auto_resolvable = False
    auto_resolve_reason = ""
    apply_fields = snapshot_fields(current)
    if reviewer["verdict"] == "pass" and not compatibility_issues(current):
        auto_resolvable = True
        auto_resolve_reason = "Reviewer agreed and deterministic checks passed."
    elif recommended and reviewer["verdict"] == "correct":
        auto_resolvable = True
        auto_resolve_reason = "Applied a structurally valid reviewer correction."
        apply_fields = {field: recommended[field] for field in COMPARE_FIELDS}
        if recommended.get("recommended_interactions"):
            apply_fields["recommended_interactions"] = recommended["recommended_interactions"]
    elif already_applied_repair and not compatibility_issues(current):
        auto_resolvable = True
        auto_resolve_reason = "Reviewer repair already applied; no remaining contradiction."
    if any("same values" in item for item in reviewer.get("issues") or []):
        auto_resolvable = False
        auto_resolve_reason = ""
    return {
        "current": snapshot_fields(current),
        "recommended": {field: recommended[field] for field in COMPARE_FIELDS} if recommended else None,
        "changes": changes,
        "problem": problem,
        "reviewer": reviewer,
        "auto_resolvable": auto_resolvable,
        "auto_resolve_reason": auto_resolve_reason,
        "apply_fields": apply_fields,
        "choice_ids": ["current"] + (["recommended"] if recommended else []),
    }


def apply_review_choice(row: dict, choice: str) -> dict:
    decision = build_review_decision(row)
    if choice == "recommended":
        if not decision["recommended"]:
            raise ValueError("No valid recommended correction is available")
        payload = {field: decision["recommended"][field] for field in COMPARE_FIELDS}
        payload["manual_override"] = True
        return payload
    if choice in {"", "current", "approve"}:
        return {"manual_override": True}
    raise ValueError("choice must be current or recommended")


def retryable_failed_kpi_ids(jobs: list[dict]) -> list[str]:
    latest: dict[str, dict] = {}
    for job in sorted(jobs, key=lambda row: str(row.get("created_at") or "")):
        kpi_id = job.get("kpi_id")
        if kpi_id:
            latest[kpi_id] = job
    return [kpi_id for kpi_id, job in latest.items() if job.get("status") == "failed"]


def auto_resolve_existing_reviews(limit: int = 50) -> dict:
    status, rows = _supabase_svc(
        "/kpi_classifications",
        params={"review_status": "eq.needs_review", "select": "*", "order": "updated_at.asc", "limit": str(limit)},
    )
    if status != 200 or not isinstance(rows, list):
        raise RuntimeError(f"Review queue could not be loaded: {rows}")
    resolved = 0
    for row in rows:
        decision = build_review_decision(row)
        if not decision["auto_resolvable"]:
            continue
        deterministic = dict(row.get("deterministic_check") or {})
        deterministic.update({
            "auto_resolved": True,
            "auto_resolve_reason": decision["auto_resolve_reason"],
            "auto_resolved_at": utc_now(),
        })
        payload = {
            **decision["apply_fields"],
            "review_status": "auto_approved",
            "manual_override": False,
            "reviewer_result": decision["reviewer"],
            "deterministic_check": deterministic,
            "updated_at": utc_now(),
            "review_deferred_at": None,
        }
        save_status, save_data = _supabase_svc(
            "/kpi_classifications", method="PATCH", payload=payload,
            params={"kpi_id": f"eq.{row['kpi_id']}", "review_status": "eq.needs_review"},
            prefer="return=representation",
        )
        if save_status == 200 and isinstance(save_data, list) and save_data:
            resolved += 1
    return {"resolved": resolved, "inspected": len(rows)}


def _process_job(job: dict, kpi: dict) -> str:
    now = utc_now()
    _supabase_svc(
        "/kpi_classification_jobs", method="PATCH",
        payload={"status": "processing", "attempts": int(job.get("attempts") or 0) + 1, "started_at": now, "failure_reason": None},
        params={"id": f"eq.{job['id']}"}, prefer="return=minimal",
    )
    try:
        ai_result, model = classify_with_ai(kpi)
        deterministic, disagreements = deterministic_disagreements(kpi, ai_result)
        reviewer = skeptical_review(kpi, ai_result, deterministic, disagreements)
        final_result, validation, needs_review = resolve_classification(ai_result, reviewer)
        status = "needs_review" if needs_review else "auto_approved"
        payload = {
            "kpi_id": kpi["id"],
            **{key: final_result.get(key) for key in (
                "skill_type", "complexity", "primary_archetype", "secondary_archetype",
                "learner_action", "deca_action", "recommended_interactions",
                "classification_reason", "certainty", "ambiguity_reason", "alternative_archetype",
            )},
            "deterministic_check": {
                **deterministic,
                "disagreements": disagreements,
                **validation,
                "original_ai": snapshot_fields(ai_result),
            },
            "reviewer_result": reviewer,
            "classifier_version": CLASSIFIER_VERSION,
            "classifier_model": model,
            "classification_schema_version": CLASSIFICATION_SCHEMA_VERSION,
            "review_status": status,
            "manual_override": False,
            "updated_at": utc_now(),
        }
        db_status, db_data = _supabase_svc(
            "/kpi_classifications", method="POST", payload=payload,
            params={"on_conflict": "kpi_id"},
            prefer="resolution=merge-duplicates,return=minimal",
        )
        if db_status not in (200, 201, 204):
            raise RuntimeError(f"classification save failed: {db_data}")
        _supabase_svc(
            "/kpi_classification_jobs", method="PATCH",
            payload={"status": status, "completed_at": utc_now()},
            params={"id": f"eq.{job['id']}"}, prefer="return=minimal",
        )
        return status
    except Exception as error:
        _supabase_svc(
            "/kpi_classification_jobs", method="PATCH",
            payload={"status": "failed", "failure_reason": str(error)[:1000], "completed_at": utc_now()},
            params={"id": f"eq.{job['id']}"}, prefer="return=minimal",
        )
        return "failed"


def process_batch(batch_id: str) -> None:
    _supabase_svc(
        "/kpi_classification_batches", method="PATCH",
        payload={"status": "processing", "started_at": utc_now()},
        params={"id": f"eq.{batch_id}"}, prefer="return=minimal",
    )
    status, jobs = _supabase_svc(
        "/kpi_classification_jobs",
        params={"batch_id": f"eq.{batch_id}", "status": "in.(queued,failed)", "select": "*", "order": "created_at.asc"},
    )
    if status != 200 or not isinstance(jobs, list):
        jobs = []
    catalog_status, catalog = _supabase_svc(
        "/kpi_catalog",
        params={"id": f"in.({','.join(job['kpi_id'] for job in jobs)})", "select": "*"},
    ) if jobs else (200, [])
    by_id = {row["id"]: row for row in catalog} if catalog_status == 200 and isinstance(catalog, list) else {}
    outcomes = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_process_job, job, by_id[job["kpi_id"]]) for job in jobs if job["kpi_id"] in by_id]
        for future in as_completed(futures):
            outcomes.append(future.result())
    totals = {
        "processed_count": len(outcomes),
        "auto_approved_count": outcomes.count("auto_approved"),
        "needs_review_count": outcomes.count("needs_review"),
        "failed_count": outcomes.count("failed") + max(0, len(jobs) - len(outcomes)),
    }
    _supabase_svc(
        "/kpi_classification_batches", method="PATCH",
        payload={"status": "complete" if totals["failed_count"] == 0 else "failed", **totals, "completed_at": utc_now()},
        params={"id": f"eq.{batch_id}"}, prefer="return=minimal",
    )


def launch_batch(batch_id: str) -> None:
    thread = threading.Thread(target=process_batch, args=(batch_id,), daemon=True, name=f"classification-{batch_id[:8]}")
    thread.start()
