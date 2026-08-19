"""First-attempt evidence and readiness gates used by student-facing analytics."""

EARLY_COVERAGE_PCT = 50
EARLY_ATTEMPT_FLOOR = 10


def first_attempts(responses):
    """Keep the earliest row per question_id, regardless of input order."""
    seen = {}
    retries = 0
    ordered = sorted(
        responses or [],
        key=lambda row: (str(row.get("answered_at") or ""), str(row.get("question_id") or "")),
    )
    for row in ordered:
        qid = row.get("question_id")
        if not qid:
            continue
        if qid in seen:
            retries += 1
        else:
            seen[qid] = row
    rows = list(seen.values())
    correct = sum(1 for row in rows if row.get("correct"))
    attempts = len(rows)
    return {
        "rows": rows,
        "attempts": attempts,
        "correct": correct,
        "retry_count": retries,
        "accuracy": round(100 * correct / attempts) if attempts else None,
    }


def chronological(responses):
    return sorted(
        responses or [],
        key=lambda row: (str(row.get("answered_at") or ""), str(row.get("question_id") or "")),
    )


def readiness_status(coverage_pct, first_attempt_count, mastery=None, accuracy=None):
    """Never report Strong/Developing from thin coverage or tiny samples."""
    if coverage_pct < EARLY_COVERAGE_PCT or first_attempt_count < EARLY_ATTEMPT_FLOOR:
        return "Early data"
    if mastery is not None and accuracy is not None and mastery >= 80 and accuracy >= 80:
        return "Strong"
    return "Developing"


def topic_is_qualified(coverage_pct, first_attempt_count, total_kpis=1):
    return bool(total_kpis) and coverage_pct >= EARLY_COVERAGE_PCT and first_attempt_count >= EARLY_ATTEMPT_FLOOR
