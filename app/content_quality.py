"""Deterministic contracts for DECA Content Quality Pipeline v1."""

from __future__ import annotations

import re
from typing import Any


PIPELINE_VERSION = "deca-content-quality-2026-08-v1"
KNOWLEDGE_TYPES = {"definition", "rule", "formula", "process", "example", "misconception"}
COGNITIVE_DEMANDS = {"recall", "comprehension", "application", "analysis", "calculation"}
DEMONSTRATION_LABELS = {
    0: "not_addressed", 1: "mentioned", 2: "explained",
    3: "applied", 4: "applied_justified_outcome",
}


class ContentQualityError(ValueError):
    pass


def _text(value: Any, field: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ContentQualityError(f"{field} must contain at least {minimum} characters")
    return value.strip()


def validate_knowledge_pack(raw: Any, kpi_id: str) -> dict:
    if not isinstance(raw, dict):
        raise ContentQualityError("knowledge pack must be an object")
    claims = raw.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ContentQualityError("knowledge pack must contain claims")
    clean = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            raise ContentQualityError(f"claims[{index}] must be an object")
        kind = str(claim.get("knowledge_type") or "").strip().lower()
        if kind not in KNOWLEDGE_TYPES:
            raise ContentQualityError(f"claims[{index}].knowledge_type is unsupported")
        sources = claim.get("source_references")
        if not isinstance(sources, list) or not sources:
            raise ContentQualityError(f"claims[{index}] requires an authoritative source reference")
        clean.append({
            "knowledge_type": kind,
            "content": _text(claim.get("content"), f"claims[{index}].content", 8),
            "source_references": sources,
            "review_status": "pending",
        })
    return {"kpi_id": kpi_id, "claims": clean, "pipeline_version": PIPELINE_VERSION}


def validate_exam_item(raw: Any, *, kpi_code: str, approved_claim_ids: set[str] | None = None) -> dict:
    if not isinstance(raw, dict):
        raise ContentQualityError("exam item must be an object")
    choices = raw.get("choices")
    rationales = raw.get("choice_rationales")
    if not isinstance(choices, list) or len(choices) != 4:
        raise ContentQualityError("exam item must have four choices")
    choices = [_text(x, f"choices[{i}]") for i, x in enumerate(choices)]
    if len({x.casefold() for x in choices}) != 4:
        raise ContentQualityError("exam choices must be unique")
    if not isinstance(rationales, list) or len(rationales) != 4:
        raise ContentQualityError("exam item requires a rationale for every choice")
    correct = raw.get("correct_index")
    if isinstance(correct, bool) or not isinstance(correct, int) or not 0 <= correct <= 3:
        raise ContentQualityError("correct_index must be 0-3")
    demand = str(raw.get("cognitive_demand") or "").strip().lower()
    if demand not in COGNITIVE_DEMANDS:
        raise ContentQualityError("unsupported cognitive demand")
    source_claim_ids = raw.get("source_claim_ids")
    if not isinstance(source_claim_ids, list) or not source_claim_ids:
        raise ContentQualityError("exam item must reference verified source claims")
    source_claim_ids = [_text(value, "source_claim_ids[]") for value in source_claim_ids]
    if approved_claim_ids is not None and any(value not in approved_claim_ids for value in source_claim_ids):
        raise ContentQualityError("exam item references an unapproved source claim")
    flags = ambiguity_flags(choices, correct)
    return {
        **raw,
        "kpi_code": kpi_code,
        "stem": _text(raw.get("stem"), "stem", 12),
        "choices": choices,
        "correct_index": correct,
        "choice_rationales": [_text(x, f"choice_rationales[{i}]", 8) for i, x in enumerate(rationales)],
        "cognitive_demand": demand,
        "instructional_area": _text(raw.get("instructional_area"), "instructional_area", 2),
        "source_claim_ids": source_claim_ids,
        "ambiguity_flags": flags,
        "publish_status": "blocked" if flags else "pending_review",
        "pipeline_version": PIPELINE_VERSION,
    }


def ambiguity_flags(choices: list[str], correct_index: int) -> list[str]:
    flags = []
    normalized = [set(re.findall(r"[a-z0-9]+", x.casefold())) for x in choices]
    for i in range(4):
        for j in range(i + 1, 4):
            similarity = len(normalized[i] & normalized[j]) / max(1, len(normalized[i] | normalized[j]))
            if similarity >= 0.8:
                flags.append(f"choices_{i}_{j}_near_duplicate")
    if any(not words for words in normalized):
        flags.append("empty_choice_semantics")
    if len(choices[correct_index]) > max(len(x) for i, x in enumerate(choices) if i != correct_index) * 1.8:
        flags.append("correct_answer_length_cue")
    return flags


def validate_roleplay_spec(raw: Any, *, eligible_codes: set[str]) -> dict:
    if not isinstance(raw, dict):
        raise ContentQualityError("roleplay spec must be an object")
    kpis = raw.get("kpis")
    if not isinstance(kpis, list) or not kpis:
        raise ContentQualityError("roleplay spec requires KPIs")
    codes = [_text(k.get("code") if isinstance(k, dict) else None, "kpi.code") for k in kpis]
    if any(code not in eligible_codes for code in codes):
        raise ContentQualityError("roleplay contains an ineligible KPI")
    judge_questions = raw.get("judge_questions")
    if not isinstance(judge_questions, list) or not judge_questions:
        raise ContentQualityError("roleplay requires judge questions")
    return {
        **raw,
        "business_skill": _text(raw.get("business_skill"), "business_skill", 8),
        "business_problem": _text(raw.get("business_problem"), "business_problem", 30),
        "participant_role": _text(raw.get("participant_role"), "participant_role", 3),
        "judge_role": _text(raw.get("judge_role"), "judge_role", 3),
        "judge_questions": [_text(x, f"judge_questions[{i}]", 8) for i, x in enumerate(judge_questions)],
        "pipeline_version": PIPELINE_VERSION,
    }


def validate_demonstration_score(raw: Any, code: str) -> dict:
    if not isinstance(raw, dict):
        raise ContentQualityError(f"score for {code} must be an object")
    level = raw.get("demonstration_level")
    if isinstance(level, bool) or not isinstance(level, int) or level not in DEMONSTRATION_LABELS:
        raise ContentQualityError(f"{code}.demonstration_level must be 0-4")
    applied = raw.get("applied_to_situation") is True
    justified = raw.get("justified_recommendation") is True
    tied_to_outcome = raw.get("tied_to_business_outcome") is True
    if level >= 2 and not applied:
        level = 1
    if level == 4 and not (justified and tied_to_outcome):
        level = 3 if applied else 2
    return {
        "code": code,
        "demonstration_level": level,
        "demonstration_label": DEMONSTRATION_LABELS[level],
        "evidence": _text(raw.get("evidence"), f"{code}.evidence", 4),
        "feedback": _text(raw.get("feedback"), f"{code}.feedback", 4),
    }


def style_metrics(items: list[dict]) -> dict:
    stems = [str(item.get("stem") or item.get("question_text") or "") for item in items]
    scenario_words = {"company", "customer", "manager", "business", "client", "employee"}
    return {
        "sample_size": len(items),
        "mean_stem_words": round(sum(len(x.split()) for x in stems) / max(1, len(stems)), 2),
        "scenario_frequency": round(sum(bool(scenario_words & set(re.findall(r"[a-z]+", x.casefold()))) for x in stems) / max(1, len(stems)), 4),
        "calculation_frequency": round(sum(bool(re.search(r"\d|calculate|percent|ratio", x, re.I)) for x in stems) / max(1, len(stems)), 4),
    }
