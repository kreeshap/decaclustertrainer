"""Shared, validated, rate-limited multi-provider lesson generation."""

from .ai import call_cloudflare, call_gemini_json, call_groq, call_mistral
from .ai_coordinator import coordinator
from .learn_validation import LearnContentError, validate_lesson


def generate_valid_lesson(prompt: str, expected_plan: dict, priority: str = "audit") -> tuple[dict | None, list[str]]:
    messages = [{"role": "user", "content": prompt}]
    providers = [
        ("Groq", lambda: call_groq(messages, max_tokens=6000)),
        ("Mistral", lambda: call_mistral(messages, max_tokens=6000)),
        ("Cloudflare", lambda: call_cloudflare(messages, max_tokens=6000)),
        ("Gemini", lambda: call_gemini_json(
            prompt, max_tokens=6000, temperature=0.2, retry_invalid_json=True
        )),
    ]
    errors: list[str] = []
    with coordinator.slot(priority):
        for name, call in providers:
            if not coordinator.available(name):
                errors.append(f"{name}: temporarily cooling down")
                continue
            result, error = call()
            if error:
                errors.append(f"{name}: {error}")
                if any(token in error.lower() for token in ("429", "resource_exhausted", "rate limit", "timeout", "504")):
                    coordinator.cool_down(name, error, 0)
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
            return lesson, errors
    return None, errors
