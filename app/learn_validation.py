"""Strict validation for AI-generated Learn Mode content."""

from __future__ import annotations

from typing import Any


class LearnContentError(ValueError):
    pass


def _text(value: Any, field: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise LearnContentError(f"{field} must be non-empty text")
    return value.strip()


def validate_question(raw: Any, field: str) -> dict:
    if not isinstance(raw, dict):
        raise LearnContentError(f"{field} must be an object")
    text = _text(raw.get("text"), f"{field}.text", 8)
    explanation = _text(raw.get("explanation"), f"{field}.explanation", 8)
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) != 4:
        raise LearnContentError(f"{field}.choices must contain exactly four choices")
    clean_choices = [_text(choice, f"{field}.choices[{i}]") for i, choice in enumerate(choices)]
    if len({choice.casefold() for choice in clean_choices}) != 4:
        raise LearnContentError(f"{field}.choices must be unique")
    correct = raw.get("correct")
    if isinstance(correct, bool) or not isinstance(correct, int) or not 0 <= correct <= 3:
        raise LearnContentError(f"{field}.correct must be an integer from 0 to 3")
    return {**raw, "text": text, "choices": clean_choices, "correct": correct, "explanation": explanation}


def validate_lesson(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise LearnContentError("lesson must be an object")

    vocab = raw.get("vocab")
    if not isinstance(vocab, list) or len(vocab) != 6:
        raise LearnContentError("vocab must contain exactly six terms")
    clean_vocab = []
    for index, item in enumerate(vocab):
        if not isinstance(item, dict):
            raise LearnContentError(f"vocab[{index}] must be an object")
        clean_vocab.append({
            "term": _text(item.get("term"), f"vocab[{index}].term"),
            "definition": _text(item.get("definition"), f"vocab[{index}].definition", 8),
        })

    concept = raw.get("concept")
    if not isinstance(concept, dict):
        raise LearnContentError("concept must be an object")
    bullets = concept.get("bullets")
    if not isinstance(bullets, list) or len(bullets) < 3:
        raise LearnContentError("concept.bullets must contain at least three concepts")
    clean_concept = {
        **concept,
        "summary": _text(concept.get("summary"), "concept.summary", 8),
        "explanation": _text(concept.get("explanation"), "concept.explanation", 40),
        "bullets": [_text(item, f"concept.bullets[{i}]", 4) for i, item in enumerate(bullets)],
    }
    concept_check = concept.get("concept_check")
    if concept_check is not None:
        if isinstance(concept_check, dict) and "text" not in concept_check and "question" in concept_check:
            concept_check = {**concept_check, "text": concept_check["question"]}
        clean_concept["concept_check"] = validate_question(concept_check, "concept.concept_check")

    recognition = raw.get("recognition_questions")
    if not isinstance(recognition, list) or len(recognition) != 5:
        raise LearnContentError("recognition_questions must contain exactly five questions")
    clean_recognition = [validate_question(item, f"recognition_questions[{i}]") for i, item in enumerate(recognition)]
    application = validate_question(raw.get("application_question"), "application_question")

    return {
        **raw,
        "vocab": clean_vocab,
        "concept": clean_concept,
        "concepts": clean_concept["bullets"],
        "recognition_questions": clean_recognition,
        "application_question": application,
    }


def validate_roleplay_prompt(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise LearnContentError("roleplay prompt must be an object")
    return {
        "scenario": _text(raw.get("scenario"), "scenario", 40),
        "role": _text(raw.get("role"), "role", 3),
        "focus": _text(raw.get("focus"), "focus", 8),
    }


def validate_roleplay_grade(raw: Any, kpi_codes: list[str]) -> dict:
    if not isinstance(raw, dict):
        raise LearnContentError("roleplay grade must be an object")
    score = raw.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 1 <= score <= 10:
        raise LearnContentError("score must be between 1 and 10")
    coverage = raw.get("kpi_coverage")
    if not isinstance(coverage, list):
        raise LearnContentError("kpi_coverage must be a list")
    by_code = {str(item.get("code", "")): item for item in coverage if isinstance(item, dict)}
    if any(code not in by_code for code in kpi_codes):
        raise LearnContentError("kpi_coverage must include every requested KPI")
    clean_coverage = []
    for code in kpi_codes:
        item = by_code[code]
        clean_coverage.append({
            "code": code,
            "addressed": bool(item.get("addressed")),
            "note": _text(item.get("note"), f"kpi_coverage[{code}].note", 4),
        })
    strengths = raw.get("strengths")
    improvements = raw.get("improvements")
    if not isinstance(strengths, list) or not strengths or not isinstance(improvements, list) or not improvements:
        raise LearnContentError("strengths and improvements must be non-empty lists")
    return {
        **raw,
        "score": int(round(score)),
        "grade": _text(raw.get("grade"), "grade"),
        "overall": _text(raw.get("overall"), "overall", 12),
        "strengths": [_text(item, "strength", 4) for item in strengths],
        "improvements": [_text(item, "improvement", 4) for item in improvements],
        "kpi_coverage": clean_coverage,
    }
