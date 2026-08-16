"""Shared, validated multi-provider lesson generation."""

from concurrent.futures import ThreadPoolExecutor, as_completed

from .ai import call_gemini_json, call_groq
from .learn_validation import LearnContentError, validate_lesson


def generate_valid_lesson(prompt: str, expected_plan: dict) -> tuple[dict | None, list[str]]:
    providers = {
        "Groq": lambda: call_groq([{"role": "user", "content": prompt}], max_tokens=4000),
        "Gemini": lambda: call_gemini_json(
            prompt, max_tokens=6000, temperature=0.2, retry_invalid_json=True
        ),
    }
    errors: list[str] = []
    executor = ThreadPoolExecutor(max_workers=len(providers))
    futures = {executor.submit(call): name for name, call in providers.items()}
    for future in as_completed(futures):
        name = futures[future]
        try:
            result, error = future.result()
        except Exception as error:
            errors.append(f"{name}: {error}")
            continue
        if error:
            errors.append(f"{name}: {error}")
            continue
        try:
            lesson = validate_lesson(result, expected_plan)
        except LearnContentError as error:
            errors.append(f"{name}: invalid lesson content ({error})")
            continue
        returned_plan = lesson["instructional_plan"]
        mismatches = [
            field for field in ("primary_archetype", "learner_action", "deca_action")
            if returned_plan.get(field) != expected_plan.get(field)
        ]
        if mismatches:
            errors.append(f"{name}: instructional plan drifted on {', '.join(mismatches)}")
            continue
        for pending in futures:
            if pending is not future:
                pending.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        return lesson, errors
    executor.shutdown(wait=True)
    return None, errors
