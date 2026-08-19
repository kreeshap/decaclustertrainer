"""Deterministic PDF ingestion and readiness rules for Practice Corpus v1."""

from __future__ import annotations

import hashlib
import io
import re
from collections import Counter
from typing import Any

import pdfplumber

from .question_ingestion import build_style_profile, extract_pdf_questions

PARSER_VERSION = "practice-corpus-2026-08-v2"
EVENT_CODE = re.compile(r"\b(?:ACT|BFS|FTDM|HLM|QSRM|RFSM|HTDM|TTDM|PHT|HTPS|MCS|MMS|RMS|SEM|BTDM|MTDM|STDM)\b", re.I)
PI_CODE = re.compile(r"\b[A-Z]{2,4}:\d{3}\b")
YEAR = re.compile(r"\b(20\d{2})(?:\s*[-–]\s*(\d{2,4}))?\b")
PAGE_ARTIFACT = re.compile(r"(?:copyright\s*©?|all rights reserved|\bDECA Inc\b|\bTest\s+\d+\b|\b(?:FINANCE|MARKETING|HOSPITALITY|BUSINESS MANAGEMENT|ENTREPRENEURSHIP)\s+EXAM(?:—KEY)?\s+\d+)", re.I)
INCOMPLETE_ENDING = re.compile(r"\b(?:a|an|and|as|at|because|but|for|from|how|if|in|of|on|or|that|the|their|to|which|who|with|without)\s*[?:,]?\s*$", re.I)


def normalized_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def text_fingerprint(text: str) -> str:
    words = normalized_text(text).split()
    shingles = {" ".join(words[i:i + 5]) for i in range(max(0, len(words) - 4))}
    return hashlib.sha256("\n".join(sorted(shingles)).encode()).hexdigest()


def extract_pdf_text(file_bytes: bytes) -> tuple[str, int]:
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = [page.extract_text(x_tolerance=2, y_tolerance=3) or "" for page in pdf.pages]
    text = "\n\n".join(pages)
    if len(text.strip()) < 200:
        raise ValueError("Scanned or image-only PDF detected; selectable text is required in v1.")
    return text, len(pages)


def suggest_metadata(text: str, filename: str, content_type: str) -> dict:
    upper = f"{filename}\n{text[:5000]}"
    events = sorted({match.group(0).upper() for match in EVENT_CODE.finditer(upper)})
    year = YEAR.search(upper)
    level = next((value for token, value in (("ICDC", "icdc"), ("DISTRICT", "district"), ("ASSOCIATION", "association")) if token in upper.upper()), "practice_sample")
    result = {
        "title": re.sub(r"[_-]+", " ", filename.rsplit(".", 1)[0]).strip(),
        "competitive_year": year.group(0) if year else None,
        "event_codes": events,
        "competition_level": level,
        "official_deca": "DECA" in upper.upper(),
        "content_type": content_type,
        "performance_indicators": sorted(set(PI_CODE.findall(upper))) if content_type == "roleplay" else [],
    }
    result["field_confidence"] = {
        "title": "medium", "competitive_year": "high" if year else "unresolved",
        "event_codes": "high" if events else "unresolved",
        "competition_level": "high" if level != "practice_sample" else "unresolved",
        "official_deca": "medium",
    }
    result["review_flags"] = (["metadata_year_unknown"] if not year else []) + (["metadata_event_unknown"] if not events else []) + (["metadata_competition_level_unknown"] if level == "practice_sample" else [])
    return result


def _section(text: str, start_patterns: list[str], end_patterns: list[str]) -> str:
    start = next((m for pattern in start_patterns if (m := re.search(pattern, text, re.I | re.M))), None)
    if not start:
        return ""
    tail = text[start.end():]
    ends = [m.start() for pattern in end_patterns if (m := re.search(pattern, tail, re.I | re.M))]
    return tail[:min(ends) if ends else len(tail)].strip()


def parse_roleplay(text: str, suggestions: dict) -> dict:
    participant = _section(text, [r"^PARTICIPANT INSTRUCTIONS?\s*$", r"^PARTICIPANT\b.*INSTRUCTIONS?"], [r"^THE SITUATION\s*$", r"^JUDGE INSTRUCTIONS?"])
    situation = _section(text, [r"^THE SITUATION\s*$", r"^BUSINESS SCENARIO\s*$", r"^SITUATION\s*$"], [r"^JUDGE INSTRUCTIONS?", r"^EVALUATION", r"^PERFORMANCE INDICATORS?"])
    judge = _section(text, [r"^JUDGE INSTRUCTIONS?\s*$", r"^JUDGE'S INSTRUCTIONS?\s*$"], [r"^JUDGE QUESTIONS?", r"^EVALUATION", r"^SCORING"])
    questions_block = _section(text, [r"^JUDGE QUESTIONS?\s*$", r"^QUESTIONS FOR THE PARTICIPANT"], [r"^EVALUATION", r"^SCORING", r"^JUDGE EVALUATION"])
    evaluation = _section(text, [r"^EVALUATION CRITERIA\s*$", r"^JUDGE EVALUATION"], [])
    questions = [q.strip() for q in re.split(r"(?:^|\n)\s*(?:\d+[.)]|[-•])\s*", questions_block) if len(q.strip()) > 8]
    tasks = [line.strip(" -•\t") for line in participant.splitlines() if re.search(r"\b(?:explain|recommend|analyze|create|develop|describe|respond|present|identify)\b", line, re.I)]
    combined = f"{participant}\n{situation}\n{judge}"
    archetypes = {
        "customer_complaint": r"complaint|dissatisfied|customer service",
        "financial_recommendation": r"financial|budget|investment|financ",
        "employee_issue": r"employee|staff|human resources",
        "operations_problem": r"operations|inventory|supply|process",
        "promotional_decision": r"promotion|campaign|advertis",
        "risk_decision": r"risk|compliance|loss|insurance",
    }
    archetype = next((name for name, pattern in archetypes.items() if re.search(pattern, combined, re.I)), "other")
    authority = next((name for name in ("consultant", "owner", "manager", "employee") if re.search(rf"\b{name}\b", combined, re.I)), "other")
    action = next((name for name in ("recommend", "explain", "analyze", "create", "respond", "persuade") if re.search(rf"\b{name}\w*\b", combined, re.I)), "other")
    role_matches = re.findall(r"You are to assume the role of ([^.\n]+)", text, re.I)
    prep_match = re.search(r"(?:prep(?:aration)? time)\D{0,12}(\d{1,2})", text, re.I)
    presentation_match = re.search(r"(?:presentation time|present)\D{0,12}(\d{1,2})\s*minutes?", text, re.I)
    area_match = re.search(r"INSTRUCTIONAL AREA\s*[:\-]?\s*([^\n]+)", text, re.I)
    flags = []
    if not PI_CODE.findall(text): flags.append("roleplay_pi_detection")
    if not participant or not situation or not judge: flags.append("roleplay_section_boundary")
    if questions_block and not questions: flags.append("roleplay_judge_question_split")
    confidence = {
        "event_code": "high" if suggestions.get("event_codes") else "unresolved",
        "instructional_area": "high" if area_match else "unresolved",
        "performance_indicators": "exact_source_match" if PI_CODE.findall(text) else "unresolved",
        "participant_role": "medium" if role_matches else "unresolved",
        "judge_role": "unresolved", "participant_instructions": "high" if participant else "unresolved",
        "situation": "high" if situation else "unresolved", "judge_instructions": "high" if judge else "unresolved",
        "judge_questions": "high" if questions else "unresolved", "evaluation_criteria": "high" if evaluation else "unresolved",
    }
    return {
        "event_code": (suggestions.get("event_codes") or [""])[0],
        "instructional_area": area_match.group(1).strip() if area_match else "",
        "performance_indicators": sorted(set(PI_CODE.findall(text))),
        "participant_role": role_matches[0].strip() if role_matches else "",
        "judge_role": "",
        "prep_time_minutes": int(prep_match.group(1)) if prep_match else None,
        "presentation_time_minutes": int(presentation_match.group(1)) if presentation_match else None,
        "participant_instructions": participant,
        "situation": situation,
        "judge_instructions": judge,
        "official_tasks": tasks,
        "judge_questions": questions,
        "evaluation_criteria": evaluation,
        "problem_archetype": archetype,
        "participant_authority": authority,
        "expected_action": action,
        "raw_sections": {"participant_instructions": participant, "situation": situation, "judge_instructions": judge, "judge_questions": questions_block, "evaluation": evaluation},
        "metrics": roleplay_metrics(participant, situation, tasks, questions, combined),
        "field_confidence": confidence, "review_flags": flags,
    }


def roleplay_metrics(participant: str, situation: str, tasks: list[str], questions: list[str], combined: str) -> dict:
    words = combined.split()
    ambiguity_terms = len(re.findall(r"\b(?:may|might|could|consider|possibly|approximately)\b", combined, re.I))
    return {
        "scenario_words": len(situation.split()),
        "participant_brief_words": len(participant.split()),
        "assigned_pi_count": len(set(PI_CODE.findall(combined))),
        "explicit_task_count": len(tasks),
        "judge_question_count": len(questions),
        "ambiguity_terms": ambiguity_terms,
        "prep_information_density": round((len(tasks) + len(set(PI_CODE.findall(combined)))) / max(1, len(words)) * 100, 3),
    }


def exam_metrics(question: dict) -> dict:
    stem = str(question.get("question_text") or "")
    choices = [str(value) for value in question.get("choices") or []]
    negative = bool(re.search(r"\b(?:not|except|least)\b", stem, re.I))
    scenario = bool(re.search(r"\b(?:company|customer|manager|business|client|employee)\b", stem, re.I))
    correct = question.get("correct_index")
    token_sets = [set(re.findall(r"[a-z0-9]+", value.casefold())) for value in choices]
    similarities = [len(token_sets[i] & token_sets[j]) / max(1, len(token_sets[i] | token_sets[j]))
                    for i in range(len(token_sets)) for j in range(i + 1, len(token_sets))]
    vocabulary = Counter(re.findall(r"[a-z]{5,}", stem.casefold()))
    return {
        "stem_words": len(stem.split()), "answer_words": [len(value.split()) for value in choices],
        "scenario": scenario, "calculation": bool(re.search(r"\d|calculate|percent|ratio", stem, re.I)),
        "negative_stem": negative, "correct_answer_position": correct,
        "context_words": max(0, len(stem.split()) - 8),
        "distractor_similarity_mean": round(sum(similarities) / max(1, len(similarities)), 4),
        "distractor_similarity_max": round(max(similarities, default=0), 4),
        "vocabulary": [word for word, _ in vocabulary.most_common(12)],
    }


def exam_review_flags(question: dict) -> list[str]:
    stem = str(question.get("question_text") or "")
    choices = [str(value) for value in question.get("choices") or []]
    explanation = str(question.get("explanation") or "")
    combined = "\n".join([stem, *choices, explanation])
    flags = []
    if len(choices) != 4 or any(not value.strip() for value in choices) or INCOMPLETE_ENDING.search(stem):
        flags.append("exam_choice_split")
    if question.get("correct_index") is None:
        flags.append("exam_answer_key_mismatch")
    if PAGE_ARTIFACT.search(combined):
        flags.append("header_contamination")
    return flags


def parse_exam(file_bytes: bytes) -> tuple[list[dict], dict]:
    questions, stats = extract_pdf_questions(file_bytes)
    rows = []
    for question in questions:
        metrics = exam_metrics(question)
        choices = question.get("choices") or []
        flags = exam_review_flags(question)
        rows.append({
            "question_number": question["question_number"], "page_number": question.get("page_number"),
            "stem": question["question_text"], "choices": choices,
            "official_answer": question.get("correct_index"), "explanation": question.get("explanation") or "",
            "pi_code": question.get("kpi_code") or None,
            "pi_source": "document" if question.get("kpi_code") else "unknown",
            "cognitive_demand": "calculation" if metrics["calculation"] else ("application" if metrics["scenario"] else "comprehension"),
            "normalized_hash": question_hash(question["question_text"]), "metrics": metrics,
            "field_confidence": {"question_number": "high", "stem": "medium", "choices": "high" if "exam_choice_split" not in flags else "low",
                                 "official_answer": "high" if question.get("correct_index") is not None else "unresolved",
                                 "pi_code": "exact_source_match" if question.get("kpi_code") else "unresolved"},
            "review_flags": flags,
        })
    stats["style_profile"] = build_style_profile(questions)
    return rows, stats


def readiness(content_type: str, documents: list[dict], items: list[dict], event_code: str = "", cluster: str = "") -> dict:
    verified = [d for d in documents if d.get("processing_state") == "verified_reference" and d.get("benchmark_eligible")]
    if event_code:
        verified = [d for d in verified if event_code in (d.get("event_codes") or [])]
    if cluster:
        verified = [d for d in verified if d.get("cluster") == cluster]
    document_ids = {d["id"] for d in verified}
    usable = [item for item in items if item.get("document_id") in document_ids and item.get("human_verified")]
    years = {d.get("competitive_year") for d in verified if d.get("competitive_year")}
    levels = {d.get("competition_level") for d in verified if d.get("competition_level")}
    if content_type == "exam":
        ready = len(verified) >= 5 or len(usable) >= 400
        reasons = [] if ready else ["Requires 5 verified exams or 400 verified questions."]
    else:
        event_count = len(verified)
        family_count = sum(1 for d in documents if d.get("cluster") == cluster and d.get("processing_state") == "verified_reference" and d.get("benchmark_eligible")) if cluster else event_count
        ready = event_count >= 15 or (event_count >= 3 and family_count >= 30)
        reasons = [] if ready else ["Requires 15 event examples, or 30 cluster-family examples plus 3 event-specific examples."]
    pi_codes = {str(item.get("pi_code") or "") for item in usable if item.get("pi_code")}
    for item in usable:
        pi_codes.update(str(code) for code in (item.get("performance_indicators") or []) if code)
    return {"content_type": content_type, "event_code": event_code, "cluster": cluster, "documents": len(verified),
            "items": len(usable), "years_represented": len(years), "competition_levels": len(levels),
            "pi_codes": sorted(pi_codes), "status": "generator_ready" if ready else "insufficient", "reasons": reasons}


# Imported late to avoid a circular import in static analyzers.
from .question_ingestion import question_hash  # noqa: E402
