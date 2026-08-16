"""Persistent KPI classification pipeline used by Admin Content Operations."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import threading

from .ai import call_gemini_json, call_groq
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def catalog_id(kpi: dict) -> str:
    return f"{kpi.get('event', '')}:{kpi.get('code', '')}"


def sync_kpi_catalog() -> list[dict]:
    kpis, _ = _load_all_kpis()
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
        "target_minutes": {"quick": "5-7", "standard": "8-10", "deep": "10-13"}[complexity],
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
  "alternative_archetype": null
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
    return result


def classify_with_ai(kpi: dict) -> tuple[dict, str]:
    prompt = _classification_prompt(kpi)
    raw, error = call_groq(
        [{"role": "user", "content": prompt}],
        model=GROQ_CLASSIFIER_MODEL,
        temperature=0.1,
        max_tokens=1200,
    )
    model = GROQ_CLASSIFIER_MODEL
    if error:
        raw, error = call_gemini_json(prompt, max_tokens=1200, temperature=0.1)
        model = GEMINI_MODEL
    if error:
        raise RuntimeError(error)
    return _validate_classification(raw), model


def deterministic_disagreements(kpi: dict, ai_result: dict) -> tuple[dict, list[str]]:
    fallback = classify_kpi(kpi["name"])
    compared = ("skill_type", "complexity", "primary_archetype", "learner_action", "deca_action")
    disagreements = [field for field in compared if ai_result.get(field) != fallback.get(field)]
    return fallback, disagreements


def skeptical_review(kpi: dict, classification: dict, deterministic: dict, disagreements: list[str]) -> dict:
    prompt = f"""Act as a skeptical instructional reviewer. Try to find a material failure in this DECA KPI classification.
Focus on cognitive-demand mismatch, cluster bias, quantitative requirements, communication treated as recall, process treated as definition recall, and archetype/action inconsistency.

KPI: {kpi['name']}
AI classification: {json.dumps(classification, separators=(',', ':'))}
Deterministic check: {json.dumps(deterministic, separators=(',', ':'))}
Disagreement fields: {json.dumps(disagreements)}

Return only JSON:
{{"verdict":"pass|review","issue":null,"recommended_archetype":null,"reason":"Concise reason"}}"""
    raw, error = call_gemini_json(prompt, max_tokens=500, temperature=0.1)
    if error:
        raw, error = call_groq(
            [{"role": "user", "content": prompt}],
            model=GROQ_CLASSIFIER_MODEL,
            temperature=0.1,
            max_tokens=500,
        )
    if error or not isinstance(raw, dict):
        return {"verdict": "review" if disagreements else "pass", "issue": "reviewer_unavailable", "recommended_archetype": deterministic.get("primary_archetype"), "reason": error or "Reviewer returned invalid data"}
    verdict = str(raw.get("verdict") or "review").strip().lower()
    if verdict not in {"pass", "review"}:
        verdict = "review"
    recommendation = raw.get("recommended_archetype")
    if recommendation not in ARCHETYPES:
        recommendation = None
    return {
        "verdict": verdict,
        "issue": str(raw.get("issue") or "").strip() or None,
        "recommended_archetype": recommendation,
        "reason": str(raw.get("reason") or "").strip() or "No reviewer reason supplied.",
    }


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
        ambiguous = bool(ai_result.get("ambiguity_reason") or ai_result.get("alternative_archetype"))
        needs_review = (
            ai_result["certainty"] != "high"
            or ambiguous
            or bool(disagreements)
            or reviewer["verdict"] == "review"
        )
        status = "needs_review" if needs_review else "auto_approved"
        payload = {
            "kpi_id": kpi["id"],
            **{key: ai_result.get(key) for key in (
                "skill_type", "complexity", "primary_archetype", "secondary_archetype",
                "learner_action", "deca_action", "recommended_interactions",
                "classification_reason", "certainty", "ambiguity_reason", "alternative_archetype",
            )},
            "deterministic_check": {**deterministic, "disagreements": disagreements},
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
