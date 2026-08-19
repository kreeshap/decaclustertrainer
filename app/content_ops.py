"""Persistent KPI classification pipeline used by Admin Content Operations."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from collections import defaultdict
import json
import re
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
ENUM_FIELDS = {
    "skill_type": SKILL_TYPES,
    "complexity": COMPLEXITIES,
    "primary_archetype": ARCHETYPES,
    "learner_action": LEARNER_ACTIONS,
    "deca_action": DECA_ACTIONS,
}
VERDICT_KEEP = "keep"
VERDICT_CHANGE = "change"
VERDICT_UNCERTAIN = "uncertain"
CANONICAL_VERDICTS = {VERDICT_KEEP, VERDICT_CHANGE, VERDICT_UNCERTAIN}
KEEP_ALIASES = {"keep", "pass", "approve"}
CHANGE_ALIASES = {"change", "correct"}
MISSING_CORRECTION_ISSUE = "reviewer correction was missing"
STALE_REVIEW_ISSUES = {
    MISSING_CORRECTION_ISSUE,
    "reviewer could not decide",
}
LEGACY_KEEP_PATTERNS = (
    r"current classification is appropriate",
    r"original (ai )?classification better aligns",
    r"deterministic alternative oversimplif",
    r"standard complexity is more appropriate",
    r"existing archetype correctly represents",
    r"classification (is|looks|remains) (correct|appropriate|fine|right|valid)",
    r"better aligns with the kpi",
    r"reject(s|ed)? the (proposed |deterministic )?alternative",
    r"keep(ing)? the current",
    r"no correction (is )?needed",
    r"does not (need|require) (a )?correction",
    r"classification matches",
    r"more appropriate than the deterministic",
)
LEGACY_UNCERTAIN_PATTERNS = (
    r"cannot (safely )?determine",
    r"unable to determine",
    r"not (sure|clear) (whether|which|if)",
    r"too ambiguous",
    r"genuinely uncertain",
    r"i('m| am) uncertain",
    r"could go either way",
)
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
    """Soft heuristic comparison. Disagreements are evidence, not auto-review triggers."""
    fallback = classify_kpi(kpi["name"])
    disagreements = [field for field in COMPARE_FIELDS if ai_result.get(field) != fallback.get(field)]
    return fallback, disagreements


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def _reviewer_text(raw: dict) -> str:
    issues = raw.get("issues") or []
    issue_text = " ".join(str(item) for item in issues if str(item).strip())
    return f"{raw.get('reason') or ''} {issue_text}".strip().lower()


def infer_legacy_keep(raw: dict) -> bool:
    """Infer KEEP from stored reviewer prose only when the evidence is strong."""
    text = _reviewer_text(raw)
    if not text or _matches_any(text, LEGACY_UNCERTAIN_PATTERNS):
        return False
    return _matches_any(text, LEGACY_KEEP_PATTERNS)


def infer_legacy_uncertain(raw: dict) -> bool:
    return _matches_any(_reviewer_text(raw), LEGACY_UNCERTAIN_PATTERNS)


def _correction_payload(raw: dict) -> dict | None:
    for key in ("correction", "corrected"):
        value = raw.get(key)
        if isinstance(value, dict) and value:
            return value
    return None


def _had_missing_correction_flag(raw: dict) -> bool:
    return any(MISSING_CORRECTION_ISSUE in str(item).lower() for item in (raw.get("issues") or []))


def hard_classification_issues(classification: dict) -> list[tuple[str, str]]:
    """Structural/logical problems that can block auto-resolution."""
    issues: list[tuple[str, str]] = []
    if not isinstance(classification, dict):
        return [("hard_rule_conflict", "stored classification is missing")]
    for field, allowed in ENUM_FIELDS.items():
        value = str(classification.get(field) or "").strip().lower()
        if field == "deca_action":
            value = DECA_ACTION_ALIASES.get(value, value)
        if not value:
            issues.append(("hard_rule_conflict", f"missing required field {field}"))
        elif value not in allowed:
            issues.append(("hard_rule_conflict", f"unsupported {field}: {value}"))
    for message in compatibility_issues(classification):
        issues.append(("action_conflict", message))
    return issues


def _snapshot_correction(corrected: dict) -> dict:
    return {
        field: corrected[field]
        for field in (*COMPARE_FIELDS, "recommended_interactions", "classification_reason", "certainty")
    }


def _apply_correction(classification: dict, overlay: dict, reason: str | None) -> tuple[dict | None, str | None]:
    try:
        corrected = merge_classification(classification, overlay, reason)
    except (TypeError, ValueError) as error:
        return None, f"invalid reviewer correction: {error}"
    if not fields_differ(classification, corrected):
        return None, "reviewer criticized the classification but recommended the same values"
    if compatibility_issues(corrected):
        return None, "recommended correction is internally inconsistent"
    return corrected, None


def _public_issues(issues: list[str], verdict: str, routing_reason: str) -> list[str]:
    cleaned = []
    for item in issues:
        text = str(item).strip()
        if not text:
            continue
        if text in STALE_REVIEW_ISSUES and (
            verdict == VERDICT_KEEP or routing_reason == "legacy_keep_inferred"
        ):
            continue
        if text == MISSING_CORRECTION_ISSUE and routing_reason != "invalid_correction":
            continue
        cleaned.append(text)
    return list(dict.fromkeys(cleaned))[:8]


def sanitize_reviewer(raw: object, classification: dict) -> dict:
    """Normalize reviewer output to keep | change | uncertain without treating silence as uncertainty."""
    if not isinstance(raw, dict):
        return {
            "verdict": VERDICT_UNCERTAIN,
            "issues": ["reviewer_malformed"],
            "corrected": None,
            "correction": None,
            "confidence": 0.0,
            "recommended_archetype": None,
            "reason": "Reviewer returned invalid data",
            "routing_reason": "malformed_reviewer_output",
        }
    issues = [str(value)[:300] for value in (raw.get("issues") or []) if str(value).strip()][:6]
    reason = str(raw.get("reason") or "").strip() or "No reviewer reason supplied."
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence") or 0)))
    except (TypeError, ValueError):
        confidence = 0.0
        issues.append("reviewer_confidence_malformed")
    corrected_raw = _correction_payload(raw)
    raw_verdict = str(raw.get("verdict") or "").strip().lower()
    routing_reason = ""
    if raw_verdict in KEEP_ALIASES:
        verdict = VERDICT_KEEP
        routing_reason = "legacy_keep_inferred" if raw.get("routing_reason") == "legacy_keep_inferred" else "reviewer_keep"
    elif raw_verdict == "change":
        verdict = VERDICT_CHANGE
        routing_reason = "reviewer_change"
    elif raw_verdict == "correct":
        if corrected_raw:
            verdict = VERDICT_CHANGE
            routing_reason = "reviewer_change"
        elif infer_legacy_keep(raw) and not infer_legacy_uncertain(raw):
            verdict = VERDICT_KEEP
            routing_reason = "legacy_keep_inferred"
        else:
            verdict = VERDICT_UNCERTAIN
            routing_reason = "legacy_ambiguous" if not infer_legacy_uncertain(raw) else "reviewer_uncertain"
    elif raw_verdict == VERDICT_UNCERTAIN:
        if _had_missing_correction_flag(raw) and infer_legacy_keep(raw) and not infer_legacy_uncertain(raw):
            verdict = VERDICT_KEEP
            routing_reason = "legacy_keep_inferred"
        else:
            verdict = VERDICT_UNCERTAIN
            routing_reason = "reviewer_uncertain"
    elif not raw_verdict:
        if infer_legacy_keep(raw) and not infer_legacy_uncertain(raw):
            verdict = VERDICT_KEEP
            routing_reason = "legacy_keep_inferred"
        else:
            verdict = VERDICT_UNCERTAIN
            routing_reason = "legacy_ambiguous" if raw.get("reason") else "malformed_reviewer_output"
    else:
        verdict = VERDICT_UNCERTAIN
        routing_reason = "malformed_reviewer_output"

    corrected = None
    recommended_archetype = None
    if verdict == VERDICT_KEEP and corrected_raw:
        candidate, error = _apply_correction(classification, corrected_raw, reason)
        if candidate:
            verdict = VERDICT_UNCERTAIN
            routing_reason = "malformed_reviewer_output"
            issues.append("Reviewer said keep but also proposed a different classification.")
        elif error and "same values" not in (error or ""):
            corrected_raw = None
    if verdict == VERDICT_CHANGE:
        if not corrected_raw:
            verdict = VERDICT_UNCERTAIN
            routing_reason = "invalid_correction"
            issues.append("Reviewer marked this classification for change, but no valid correction was provided.")
        else:
            candidate, error = _apply_correction(classification, corrected_raw, reason)
            if candidate:
                corrected = candidate
                recommended_archetype = candidate["primary_archetype"]
                routing_reason = "reviewer_change"
            else:
                verdict = VERDICT_UNCERTAIN
                corrected = None
                if error and "same values" in error:
                    routing_reason = "same_value_correction"
                    issues.append(error)
                elif error and "inconsistent" in error:
                    routing_reason = "action_conflict"
                    issues.append(error)
                else:
                    routing_reason = "invalid_correction"
                    issues.append(error or "invalid reviewer correction")

    return {
        "verdict": verdict,
        "issues": _public_issues(issues, verdict, routing_reason),
        "corrected": _snapshot_correction(corrected) if corrected else None,
        "correction": _snapshot_correction(corrected) if corrected else None,
        "confidence": confidence,
        "recommended_archetype": recommended_archetype,
        "reason": reason,
        "routing_reason": routing_reason,
    }


def skeptical_review(kpi: dict, classification: dict, deterministic: dict, disagreements: list[str]) -> dict:
    prompt = f"""Act as an adversarial instructional reviewer. Assume the classifier may be wrong and try to prove it.
Check KPI-verb/action alignment, archetype fit, complexity, and contradictions.
If the current classification is appropriate, verdict must be keep and correction must be null.
If the classification is materially wrong, verdict must be change and correction must differ from the current values.
If you cannot safely determine the correct classification, verdict must be uncertain.
Never criticize a field while recommending the same value for that field.
A missing correction means keep, not uncertainty, unless verdict is change or uncertain.

KPI: {kpi['name']}
AI classification: {json.dumps(classification, separators=(',', ':'))}
Deterministic check (heuristic evidence only, not ground truth): {json.dumps(deterministic, separators=(',', ':'))}
Soft heuristic disagreements: {json.dumps(disagreements)}

Return only JSON:
{{"verdict":"keep|change|uncertain","reason":"Concise reason","correction":null,"issues":[],"confidence":0.0}}"""
    messages = [{"role": "user", "content": prompt}]
    raw, error, _ = coordinator.run([
        ("Groq", lambda: call_groq(messages, model=GROQ_CLASSIFIER_MODEL, temperature=0.1, max_tokens=500)),
        ("Mistral", lambda: call_mistral(messages, temperature=0.1, max_tokens=500)),
        ("Cloudflare", lambda: call_cloudflare(messages, temperature=0.1, max_tokens=500)),
        ("Gemini", lambda: call_gemini_json(prompt, max_tokens=500, temperature=0.1)),
    ], "classification")
    if error or not isinstance(raw, dict):
        raw = {"verdict": VERDICT_UNCERTAIN, "issues": ["reviewer_unavailable"], "correction": None, "confidence": 0.0, "reason": error or "Reviewer returned invalid data"}
    return sanitize_reviewer(raw, classification)


def _route_review(classification: dict, reviewer: dict) -> tuple[dict, dict, bool]:
    reviewer = sanitize_reviewer(reviewer, classification)
    final = dict(classification)
    issues = list(reviewer.get("issues") or [])
    repaired = False
    routing_reason = reviewer.get("routing_reason") or "reviewer_uncertain"
    hard_current = hard_classification_issues(classification)

    if reviewer["verdict"] == VERDICT_CHANGE and reviewer.get("corrected"):
        try:
            final = merge_classification(classification, reviewer["corrected"], reviewer.get("reason"))
            repaired = fields_differ(classification, final)
            if not repaired:
                routing_reason = "same_value_correction"
                issues.append("reviewer criticized the classification but recommended the same values")
                final = dict(classification)
            elif hard_classification_issues(final):
                routing_reason = hard_classification_issues(final)[0][0]
                issues.extend(code_message[1] for code_message in hard_classification_issues(final))
                repaired = False
                final = dict(classification)
            else:
                routing_reason = "reviewer_change"
        except (TypeError, ValueError) as error:
            routing_reason = "invalid_correction"
            issues.append(f"invalid reviewer correction: {error}")
            final = dict(classification)
    elif reviewer["verdict"] == VERDICT_KEEP:
        if hard_current:
            routing_reason = hard_current[0][0]
            issues.extend(item[1] for item in hard_current)
        else:
            routing_reason = reviewer.get("routing_reason") if reviewer.get("routing_reason") in {"reviewer_keep", "legacy_keep_inferred"} else "reviewer_keep"
    else:
        if routing_reason in {"reviewer_keep", "reviewer_change", "legacy_keep_inferred"}:
            routing_reason = "reviewer_uncertain"

    auto_approve = (
        reviewer["verdict"] == VERDICT_KEEP and not hard_current
    ) or (
        repaired and not hard_classification_issues(final)
    )
    if auto_approve and reviewer["verdict"] == VERDICT_KEEP:
        issues = [item for item in issues if item not in STALE_REVIEW_ISSUES]
    decision_basis = (
        "reviewer_pass" if reviewer["verdict"] == VERDICT_KEEP and auto_approve
        else ("valid_repair" if repaired and auto_approve else "manual_review")
    )
    validator = {
        "issues": list(dict.fromkeys(issues)),
        "repaired": repaired,
        "auto_approve": auto_approve,
        "decision_basis": decision_basis,
        "routing_reason": routing_reason,
    }
    return final, validator, not auto_approve


def resolve_classification(classification: dict, reviewer: dict) -> tuple[dict, dict, bool]:
    """Apply a structurally valid repair; escalate only genuine ambiguity or hard contradictions."""
    return _route_review(classification, reviewer)


def _problem_text(reviewer: dict, current: dict, recommended: dict | None, routing_reason: str) -> str:
    reason = str(reviewer.get("reason") or "").strip()
    hard_messages = [item[1] for item in hard_classification_issues(current)]
    if routing_reason == "reviewer_uncertain":
        return reason or "Reviewer is uncertain which classification is correct."
    if routing_reason == "invalid_correction":
        extra = next((item for item in reviewer.get("issues") or [] if "correction" in item.lower()), "")
        return extra or "Reviewer proposed a correction, but it is not a valid structured repair."
    if routing_reason == "same_value_correction":
        return "Reviewer criticized a value but recommended the same value."
    if routing_reason == "action_conflict":
        target = "Reviewer proposed a correction, but learner action and DECA action remain incompatible."
        if recommended is None and hard_messages:
            return hard_messages[0]
        return target
    if routing_reason == "hard_rule_conflict":
        return hard_messages[0] if hard_messages else "A hard classification rule is violated."
    if routing_reason == "malformed_reviewer_output":
        return reason if reason and reason != "No reviewer reason supplied." else "Reviewer output was malformed and could not be used."
    if routing_reason == "legacy_ambiguous":
        return reason or "Stored reviewer reasoning is too ambiguous to auto-resolve."
    if reviewer.get("issues"):
        return " ".join(dict.fromkeys([*(reviewer["issues"]), reason] if reason else reviewer["issues"])).strip()
    return reason or "This classification needs a human decision."


def build_review_decision(row: dict) -> dict:
    current = {
        **snapshot_fields(row),
        "secondary_archetype": row.get("secondary_archetype"),
        "recommended_interactions": row.get("recommended_interactions") or [],
        "certainty": row.get("certainty"),
        "classification_reason": row.get("classification_reason"),
    }
    reviewer = sanitize_reviewer(row.get("reviewer_result") or {}, current)
    final, validator, needs_review = resolve_classification(current, reviewer)
    routing_reason = validator.get("routing_reason") or reviewer.get("routing_reason") or "reviewer_uncertain"
    recommended = None
    if reviewer.get("corrected") and reviewer["verdict"] == VERDICT_CHANGE:
        recommended = {
            **snapshot_fields(reviewer["corrected"]),
            "recommended_interactions": reviewer["corrected"].get("recommended_interactions"),
            "certainty": reviewer["corrected"].get("certainty"),
        }
    elif reviewer.get("corrected") and not needs_review:
        recommended = None
    elif reviewer.get("corrected") and routing_reason not in {"same_value_correction", "invalid_correction"}:
        try:
            candidate = merge_classification(current, reviewer["corrected"], reviewer.get("reason"))
            if fields_differ(current, candidate) and not compatibility_issues(candidate):
                recommended = snapshot_fields(candidate)
                recommended["recommended_interactions"] = candidate.get("recommended_interactions")
                recommended["certainty"] = candidate.get("certainty")
        except (TypeError, ValueError):
            recommended = None
    changes = []
    if recommended:
        for field in COMPARE_FIELDS:
            if current.get(field) != recommended.get(field):
                changes.append({"field": field, "from": current.get(field), "to": recommended.get(field)})
    deterministic = row.get("deterministic_check") or {}
    original_ai = deterministic.get("original_ai") or {}
    already_applied_repair = bool(original_ai) and fields_differ(original_ai, current) and reviewer["verdict"] != VERDICT_CHANGE
    auto_resolvable = not needs_review
    auto_resolve_reason = ""
    apply_fields = snapshot_fields(current)
    applied_correction = False
    if auto_resolvable and reviewer["verdict"] == VERDICT_KEEP:
        auto_resolve_reason = (
            "Inferred KEEP from stored reviewer reasoning."
            if routing_reason == "legacy_keep_inferred"
            else "Reviewer agreed the current classification should be kept."
        )
        apply_fields = snapshot_fields(current)
    elif auto_resolvable and validator.get("repaired"):
        auto_resolve_reason = "Applied a structurally valid reviewer correction."
        apply_fields = snapshot_fields(final)
        if final.get("recommended_interactions"):
            apply_fields["recommended_interactions"] = final["recommended_interactions"]
        applied_correction = True
    elif already_applied_repair and not hard_classification_issues(current) and reviewer["verdict"] != VERDICT_UNCERTAIN:
        auto_resolvable = True
        auto_resolve_reason = "Reviewer repair already applied; no remaining contradiction."
        routing_reason = "reviewer_change"
    if routing_reason == "same_value_correction":
        auto_resolvable = False
        auto_resolve_reason = ""
        recommended = None
        changes = []
    problem = "" if auto_resolvable else _problem_text(reviewer, current, recommended, routing_reason)
    choice_ids = ["current"]
    if recommended and not auto_resolvable:
        choice_ids.append("recommended")
    elif not auto_resolvable:
        choice_ids.append("skip")
    return {
        "current": snapshot_fields(current),
        "recommended": {field: recommended[field] for field in COMPARE_FIELDS} if recommended else None,
        "changes": changes,
        "problem": problem,
        "reviewer": reviewer,
        "auto_resolvable": auto_resolvable,
        "auto_resolve_reason": auto_resolve_reason,
        "apply_fields": apply_fields,
        "choice_ids": choice_ids,
        "routing_reason": routing_reason,
        "applied_correction": applied_correction,
        "soft_heuristic_disagreement": bool(deterministic.get("disagreements")),
    }


def apply_review_choice(row: dict, choice: str) -> dict:
    decision = build_review_decision(row)
    if choice == "recommended":
        if not decision["recommended"]:
            raise ValueError("No valid recommended correction is available")
        payload = {field: decision["recommended"][field] for field in COMPARE_FIELDS}
        payload["manual_override"] = True
        return payload
    if choice == "skip":
        raise ValueError("skip is not an approval choice")
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


def _load_review_queue(limit: int = 10000) -> list[dict]:
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    while len(rows) < limit:
        status, page = _supabase_svc(
            "/kpi_classifications",
            params={
                "review_status": "eq.needs_review",
                "select": "*",
                "order": "updated_at.asc",
                "limit": str(min(page_size, limit - len(rows))),
                "offset": str(offset),
            },
        )
        if status != 200 or not isinstance(page, list):
            raise RuntimeError(f"Review queue could not be loaded: {page}")
        if not page:
            break
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += len(page)
    return rows


def auto_resolve_existing_reviews(limit: int = 10000) -> dict:
    rows = _load_review_queue(limit)
    remaining_reasons: dict[str, int] = defaultdict(int)
    auto_kept = 0
    auto_changed = 0
    still_review = 0
    uninterpretable = 0
    resolved = 0
    for row in rows:
        decision = build_review_decision(row)
        routing_reason = str(decision.get("routing_reason") or "legacy_ambiguous")
        if not decision["auto_resolvable"]:
            still_review += 1
            remaining_reasons[routing_reason] += 1
            if routing_reason in {"malformed_reviewer_output", "legacy_ambiguous"}:
                uninterpretable += 1
            continue
        deterministic = dict(row.get("deterministic_check") or {})
        deterministic.update({
            "auto_resolved": True,
            "auto_resolve_reason": decision["auto_resolve_reason"],
            "auto_resolved_at": utc_now(),
            "routing_reason": routing_reason,
            "applied_correction": bool(decision.get("applied_correction")),
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
            if decision.get("applied_correction"):
                auto_changed += 1
            else:
                auto_kept += 1
        else:
            still_review += 1
            remaining_reasons["save_failed"] += 1
    return {
        "resolved": resolved,
        "inspected": len(rows),
        "auto_kept": auto_kept,
        "auto_changed": auto_changed,
        "still_review": still_review,
        "uninterpretable": uninterpretable,
        "ai_calls": 0,
        "remaining_reasons": dict(remaining_reasons),
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
                "disagreement_severity": "soft",
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
