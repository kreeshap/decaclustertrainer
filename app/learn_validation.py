"""Strict validation for AI-generated Learn Mode content."""

from __future__ import annotations

from typing import Any
import re


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
    if _word_count(explanation) > 55:
        raise LearnContentError(f"{field}.explanation must be 55 words or fewer")
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


def _word_count(value: Any) -> int:
    if isinstance(value, str):
        return len(re.findall(r"\b[\w'-]+\b", value))
    if isinstance(value, list):
        return sum(_word_count(item) for item in value)
    if isinstance(value, dict):
        return sum(_word_count(item) for item in value.values())
    return 0


def _question_overlap(first: str, second: str) -> float:
    ignored = {"a", "an", "and", "best", "is", "of", "the", "this", "to", "what", "which"}
    left = {word for word in re.findall(r"[a-z0-9]+", first.lower()) if word not in ignored}
    right = {word for word in re.findall(r"[a-z0-9]+", second.lower()) if word not in ignored}
    return len(left & right) / max(1, len(left | right))


def validate_lesson(raw: Any, expected_plan: dict | None = None) -> dict:
    if not isinstance(raw, dict):
        raise LearnContentError("lesson must be an object")

    vocab = raw.get("vocab")
    if not isinstance(vocab, list) or not 3 <= len(vocab) <= 6:
        raise LearnContentError("vocab must contain three to six terms")
    clean_vocab = []
    for index, item in enumerate(vocab):
        if not isinstance(item, dict):
            raise LearnContentError(f"vocab[{index}] must be an object")
        importance = str(item.get("importance") or "supporting").strip().lower()
        if importance not in {"essential", "supporting", "context"}:
            raise LearnContentError(f"vocab[{index}].importance is unsupported")
        clean_vocab.append({
            "term": _text(item.get("term"), f"vocab[{index}].term"),
            "definition": _text(item.get("definition"), f"vocab[{index}].definition", 8),
            "importance": importance,
        })
    if len({item["term"].casefold() for item in clean_vocab}) != len(clean_vocab):
        raise LearnContentError("vocab terms must be unique")

    design = raw.get("lesson_design") if isinstance(raw.get("lesson_design"), dict) else {}
    complexity = str(design.get("complexity") or raw.get("complexity") or "standard").strip().lower()
    skill_type = str(design.get("skill_type") or raw.get("skill_type") or "concept").strip().lower()
    target_minutes = str(design.get("target_minutes") or raw.get("target_minutes") or "8-10").strip()
    if complexity not in {"quick", "standard", "deep"}:
        raise LearnContentError("lesson_design.complexity must be quick, standard, or deep")
    if skill_type not in {"concept", "decision", "communication", "process", "calculation_data", "analysis"}:
        raise LearnContentError("lesson_design.skill_type is unsupported")
    expected_vocab = int((expected_plan or {}).get("vocab_count") or {"quick": 3, "standard": 4, "deep": 5}[complexity])
    if len(clean_vocab) != expected_vocab:
        raise LearnContentError(f"vocab must contain exactly {expected_vocab} terms for a {complexity} KPI")

    plan = raw.get("instructional_plan")
    if not isinstance(plan, dict):
        raise LearnContentError("instructional_plan must be an object")
    archetype = str(plan.get("primary_archetype") or "").strip().lower()
    if archetype not in {"concept_discovery", "decision_lab", "diagnose_problem", "build_process", "tradeoff_challenge", "communication_coach", "numbers_lab"}:
        raise LearnContentError("instructional_plan.primary_archetype is unsupported")
    clean_plan = {
        "primary_archetype": archetype,
        "learner_action": _text(plan.get("learner_action"), "instructional_plan.learner_action"),
        "deca_action": _text(plan.get("deca_action"), "instructional_plan.deca_action"),
        "recommended_interactions": [
            _text(item, f"instructional_plan.recommended_interactions[{index}]")
            for index, item in enumerate(plan.get("recommended_interactions") or [])
        ][:4],
    }
    if not clean_plan["recommended_interactions"]:
        raise LearnContentError("instructional_plan.recommended_interactions must not be empty")

    mission = raw.get("mission")
    if not isinstance(mission, dict):
        raise LearnContentError("mission must be an object")
    opening = _validate_three_choice(mission.get("opening_interaction"), "mission.opening_interaction")
    opening["aha"] = _text((mission.get("opening_interaction") or {}).get("aha"), "mission.opening_interaction.aha", 12)
    choice_feedback = opening.get("choice_feedback")
    if not isinstance(choice_feedback, list) or len(choice_feedback) != 3:
        raise LearnContentError("mission.opening_interaction.choice_feedback must contain three responses")
    opening["choice_feedback"] = [
        _text(item, f"mission.opening_interaction.choice_feedback[{index}]", 8)
        for index, item in enumerate(choice_feedback)
    ]
    clean_mission = {
        "title": _text(mission.get("title"), "mission.title", 4),
        "brief": _text(mission.get("brief"), "mission.brief", 20),
        "opening_interaction": opening,
    }

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
    required_blocks = int((expected_plan or {}).get("required_block_count") or {"quick": 2, "standard": 3, "deep": 4}[complexity])
    if len(learning_blocks) != required_blocks:
        raise LearnContentError(f"learning_blocks must contain exactly {required_blocks} blocks for a {complexity} KPI")
    clean_blocks = []
    for index, block in enumerate(learning_blocks[:4]):
        if not isinstance(block, dict):
            raise LearnContentError(f"learning_blocks[{index}] must be an object")
        clean_blocks.append({
            "type": str(block.get("type") or "concept_reveal").strip().lower(),
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
    for first in range(len(clean_practice)):
        for second in range(first + 1, len(clean_practice)):
            if _question_overlap(clean_practice[first]["text"], clean_practice[second]["text"]) > 0.68:
                raise LearnContentError("practice questions are too semantically repetitive")

    lesson_word_cap = {"quick": 550, "standard": 850, "deep": 1200}[complexity]
    if _word_count(raw) > lesson_word_cap:
        raise LearnContentError(f"lesson exceeds the {lesson_word_cap}-word cap for {complexity} KPIs")

    clean_recognition = clean_practice[:2]
    application = clean_practice[2:]

    return {
        **raw,
        "lesson_design": {
            "complexity": complexity,
            "skill_type": skill_type,
            "target_minutes": target_minutes,
        },
        "instructional_plan": clean_plan,
        "mission": clean_mission,
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
