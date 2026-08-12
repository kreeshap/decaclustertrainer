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


def _validate_three_choice(raw: Any, field: str) -> dict:
    if not isinstance(raw, dict):
        raise LearnContentError(f"{field} must be an object")
    question = _text(raw.get("question"), f"{field}.question", 8)
    explanation = _text(raw.get("explanation"), f"{field}.explanation", 8)
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) != 3:
        raise LearnContentError(f"{field}.choices must contain exactly three choices")
    clean_choices = [_text(choice, f"{field}.choices[{i}]") for i, choice in enumerate(choices)]
    correct = raw.get("correct")
    if isinstance(correct, bool) or not isinstance(correct, int) or not 0 <= correct <= 2:
        raise LearnContentError(f"{field}.correct must be an integer from 0 to 2")
    return {**raw, "question": question, "choices": clean_choices, "correct": correct, "explanation": explanation}


def _validate_mini_roleplay(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise LearnContentError("mini_roleplay must be an object")
    decisions = raw.get("decisions")
    if not isinstance(decisions, list) or not 1 <= len(decisions) <= 3:
        raise LearnContentError("mini_roleplay.decisions must contain one to three decisions")
    clean_decisions = []
    for index, decision in enumerate(decisions):
        clean = _validate_three_choice(decision, f"mini_roleplay.decisions[{index}]")
        clean["situation"] = _text(decision.get("situation"), f"mini_roleplay.decisions[{index}].situation", 12)
        clean["consequence"] = _text(decision.get("consequence"), f"mini_roleplay.decisions[{index}].consequence", 8)
        clean_decisions.append(clean)
    return {
        "role": _text(raw.get("role"), "mini_roleplay.role", 3),
        "setup": _text(raw.get("setup"), "mini_roleplay.setup", 20),
        "decisions": clean_decisions,
        "why_it_matters": _text(raw.get("why_it_matters"), "mini_roleplay.why_it_matters", 20),
    }


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

    design = raw.get("lesson_design") if isinstance(raw.get("lesson_design"), dict) else {}
    complexity = str(design.get("complexity") or raw.get("complexity") or "standard").strip().lower()
    skill_type = str(design.get("skill_type") or raw.get("skill_type") or "concept").strip().lower()
    target_minutes = str(design.get("target_minutes") or raw.get("target_minutes") or "8-10").strip()
    if complexity not in {"quick", "standard", "deep"}:
        raise LearnContentError("lesson_design.complexity must be quick, standard, or deep")
    if skill_type not in {"concept", "decision", "communication", "process", "calculation_data"}:
        raise LearnContentError("lesson_design.skill_type is unsupported")

    hook = _text(raw.get("hook"), "hook", 20)

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

    learning_blocks = raw.get("learning_blocks")
    if not isinstance(learning_blocks, list) or len(learning_blocks) < 2:
        raise LearnContentError("learning_blocks must contain at least two blocks")
    clean_blocks = []
    for index, block in enumerate(learning_blocks[:4]):
        if not isinstance(block, dict):
            raise LearnContentError(f"learning_blocks[{index}] must be an object")
        clean_blocks.append({
            "title": _text(block.get("title"), f"learning_blocks[{index}].title", 3),
            "body": _text(block.get("body"), f"learning_blocks[{index}].body", 30),
        })

    interactive_check = raw.get("interactive_check")
    if interactive_check is not None:
        interactive_check = _validate_three_choice(interactive_check, "interactive_check")

    example = raw.get("realistic_example")
    if not isinstance(example, dict):
        raise LearnContentError("realistic_example must be an object")
    clean_example = {
        "story": _text(example.get("story"), "realistic_example.story", 30),
        "flow": [
            _text(item, f"realistic_example.flow[{i}]", 3)
            for i, item in enumerate(example.get("flow") if isinstance(example.get("flow"), list) else [])
        ],
    }
    if len(clean_example["flow"]) < 3:
        raise LearnContentError("realistic_example.flow must contain at least three steps")

    mini_roleplay = _validate_mini_roleplay(raw.get("mini_roleplay"))

    takeaways = raw.get("key_takeaways")
    if not isinstance(takeaways, list) or not 1 <= len(takeaways) <= 3:
        raise LearnContentError("key_takeaways must contain one to three bullets")
    clean_takeaways = [_text(item, f"key_takeaways[{i}]", 4) for i, item in enumerate(takeaways)]

    practice = raw.get("practice_questions")
    if not isinstance(practice, list) or len(practice) != 3:
        raise LearnContentError("practice_questions must contain exactly three questions")
    clean_practice = []
    expected_labels = ["Check", "Apply", "DECA Challenge"]
    for index, item in enumerate(practice):
        clean = validate_question(item, f"practice_questions[{index}]")
        clean["stage_label"] = expected_labels[index]
        clean_practice.append(clean)

    clean_recognition = clean_practice[:2]
    application = clean_practice[2:]

    return {
        **raw,
        "lesson_design": {
            "complexity": complexity,
            "skill_type": skill_type,
            "target_minutes": target_minutes,
        },
        "hook": hook,
        "vocab": clean_vocab,
        "concept": clean_concept,
        "concepts": clean_concept["bullets"],
        "learning_blocks": clean_blocks,
        "interactive_check": interactive_check,
        "realistic_example": clean_example,
        "mini_roleplay": mini_roleplay,
        "key_takeaways": clean_takeaways,
        "practice_questions": clean_practice,
        "recognition_questions": clean_recognition,
        "application_question": application[0],
        "application_questions": application,
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
