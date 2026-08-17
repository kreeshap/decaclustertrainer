"""Pure deterministic plan packing; intentionally independent of Flask and storage."""

from datetime import date
from urllib.parse import quote


def task(task_id, label, minutes, href, baseline, target, **extra):
    return {"id": task_id, "label": label, "minutes": minutes, "href": href,
            "baseline": baseline, "target": target, "progress": 0, "done": False, **extra}


def build_plan(state, event_id, budget):
    budget = max(3, min(90, int(budget)))
    remaining = budget
    tasks = []
    reasons = []
    details = []
    coverage = state["coverage"]
    due = int(state.get("due_review_count") or 0)
    weak = state.get("qualified_weakest_topic")
    active = state.get("unfinished_practice")
    kpi_minutes = max(3, min(12, round(float(state.get("median_kpi_minutes") or 6))))
    question_seconds = max(20, min(120, round(float(state.get("median_question_seconds") or 45))))

    if active:
        remaining_questions = max(1, int(active["question_count"]) - int(active["current_index"]))
        minutes = max(2, min(remaining, round(remaining_questions * question_seconds / 60)))
        tasks.append(task("resume_practice", f"Continue {active.get('title') or 'practice questions'}", minutes,
                          f"/app/practicequestions.html?resume={active['id']}", active["current_index"],
                          remaining_questions, remaining_questions=remaining_questions))
        reasons.append("UNFINISHED_WORK_PRIORITY")
        details.append(f"An active practice set has {remaining_questions} questions remaining.")
        remaining -= minutes

    if weak:
        reasons.append("QUALIFIED_WEAKNESS")
        details.append(f"{weak['topic']} qualifies with {weak['kpis_studied']} of {weak['kpis_total']} KPIs covered and {weak['attempts']} attempts at {weak['accuracy']}% accuracy.")
    elif coverage["percent"] < 50:
        reasons.extend(["LOW_CURRICULUM_COVERAGE", "NO_QUALIFIED_WEAKNESS"])
        details.append(f"Only {coverage['studied']} of {coverage['total']} KPIs are completed; no topic weakness is used without enough evidence.")
    else:
        reasons.append("NO_QUALIFIED_WEAKNESS")

    if due and remaining >= 2:
        weak_due = int((state.get("due_reviews_by_topic") or {}).get(weak["topic"], 0)) if weak else 0
        count = min(due, 5 if budget >= 15 else 2)
        if weak_due:
            count = min(count, weak_due)
        minutes = min(remaining, max(2, count))
        topic_text = f" {weak['topic']}" if weak and weak_due else ""
        tasks.append(task("review", f"Review {count} due{topic_text} concept{'s' if count != 1 else ''}", minutes,
                          "/app/learn.html?review=due", due, count))
        reasons.append("DUE_REVIEW_PRIORITY")
        details.append(f"{due} spaced-repetition reviews are currently due.")
        remaining -= minutes

    # Preserve room for a few questions. A five-minute plan deliberately skips new content.
    reserve_for_questions = 2 if remaining >= 2 else 0
    if budget > 5 and remaining - reserve_for_questions >= kpi_minutes:
        count = 2 if not due and coverage["percent"] < 20 and remaining - reserve_for_questions >= kpi_minutes * 2 else 1
        minutes = min(remaining - reserve_for_questions, count * kpi_minutes)
        topic_text = f" uncovered {weak['topic']}" if weak else " new"
        tasks.append(task("learn", f"Learn {count}{topic_text} KPI{'s' if count != 1 else ''}", minutes,
                          "/app/learn.html", coverage["studied"], count))
        reasons.append("NEW_LEARNING_PRIORITY")
        remaining -= minutes

    if remaining >= 2 and not active:
        count = 3 if budget <= 5 else max(3, min(10, int(remaining * 60 / question_seconds)))
        topic = weak["topic"] if weak else None
        label = f"Practice {count} {topic + ' ' if topic else 'introductory '}questions"
        href = f"/app/practicequestions.html?topic={quote(topic)}" if topic else "/app/practicequestions.html"
        tasks.append(task("questions", label, remaining, href, state["practice_attempt_count"], count))
        reasons.append("QUALIFIED_WEAKNESS_PRACTICE" if topic else "BROAD_EVIDENCE_BUILDING")
        remaining = 0

    if not tasks:
        tasks.append(task("questions", "Practice 3 introductory questions", budget,
                          "/app/practicequestions.html", state["practice_attempt_count"], 3))
        reasons.append("BROAD_EVIDENCE_BUILDING")

    return {"date": date.today().isoformat(), "eventId": event_id, "started": False,
            "finished": False, "time_budget_minutes": budget, "tasks": tasks,
            "reason_codes": list(dict.fromkeys(reasons)), "reason_details": details}


def refresh_progress(plan, state):
    for item in plan.get("tasks", []):
        if item["id"] == "learn":
            item["progress"] = max(0, state["coverage"]["studied"] - int(item.get("baseline", 0)))
        elif item["id"] == "questions":
            item["progress"] = max(0, state["practice_attempt_count"] - int(item.get("baseline", 0)))
        elif item["id"] == "review":
            item["progress"] = max(0, int(item.get("baseline", 0)) - state["due_review_count"])
        elif item["id"] == "resume_practice":
            active = state.get("unfinished_practice")
            item["progress"] = int(item.get("target", 1)) if not active else max(0, int(active["current_index"]) - int(item.get("baseline", 0)))
        item["done"] = item["progress"] >= int(item.get("target", 1))
    plan["finished"] = bool(plan.get("tasks")) and all(item.get("done") for item in plan["tasks"])
    plan["started"] = any(int(item.get("progress", 0)) > 0 for item in plan.get("tasks", []))
    return plan
