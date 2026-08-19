"""Deterministic study activity definitions and evidence-gated selection."""

ACTIVITIES = {
    "learn": {
        "activity_type": "learn",
        "display_name": "Learn Mode",
        "description": "Build coverage with a guided KPI lesson.",
        "target_learning_problem": "low_coverage",
        "supported_skill_types": ["concept", "decision", "communication", "process", "calculation_data", "analysis"],
        "supported_learner_actions": ["classify", "choose", "respond", "sequence", "calculate", "diagnose"],
        "minimum_evidence": 0,
        "recommended_duration": 6,
        "requires_multiple_kpis": False,
        "requires_questions": False,
        "requires_prior_learning": False,
        "supports_timer": False,
        "difficulty": "foundation",
    },
    "personal_connection": {
        "activity_type": "personal_connection",
        "display_name": "Personal Connection",
        "description": "Explain a recently learned KPI in your own words and connect it to a familiar situation.",
        "target_learning_problem": "thin_comprehension_evidence",
        "supported_skill_types": ["concept", "communication"],
        "supported_learner_actions": ["classify", "explain", "respond"],
        "minimum_evidence": 1,
        "recommended_duration": 5,
        "requires_multiple_kpis": False,
        "requires_questions": False,
        "requires_prior_learning": True,
        "supports_timer": False,
        "difficulty": "understand",
    },
    "pi_compare_apply": {
        "activity_type": "pi_compare_apply",
        "display_name": "PI Compare & Apply",
        "description": "Distinguish two related PIs, then apply each to the same business situation.",
        "target_learning_problem": "related_kpi_confusion",
        "supported_skill_types": ["concept", "decision", "analysis"],
        "supported_learner_actions": ["classify", "choose", "diagnose"],
        "minimum_evidence": 10,
        "recommended_duration": 6,
        "requires_multiple_kpis": True,
        "requires_questions": True,
        "requires_prior_learning": True,
        "supports_timer": False,
        "difficulty": "connect",
    },
    "scenario_sprint": {
        "activity_type": "scenario_sprint",
        "display_name": "Scenario Sprint",
        "description": "Retrieve the right KPI and business response quickly in a short scenario.",
        "target_learning_problem": "slow_application_retrieval",
        "supported_skill_types": ["decision", "communication", "process", "analysis"],
        "supported_learner_actions": ["choose", "respond", "sequence", "diagnose"],
        "minimum_evidence": 10,
        "recommended_duration": 5,
        "requires_multiple_kpis": True,
        "requires_questions": True,
        "requires_prior_learning": True,
        "supports_timer": True,
        "difficulty": "mix",
    },
    "pi_fluency": {
        "activity_type": "pi_fluency",
        "display_name": "PI Fluency",
        "description": "Retrieve and explain several learned PIs before adding competition pressure.",
        "target_learning_problem": "untested_retrieval",
        "supported_skill_types": ["concept", "decision", "communication", "process", "calculation_data", "analysis"],
        "supported_learner_actions": ["classify", "choose", "respond", "sequence", "calculate", "diagnose"],
        "minimum_evidence": 10,
        "recommended_duration": 6,
        "requires_multiple_kpis": True,
        "requires_questions": True,
        "requires_prior_learning": True,
        "supports_timer": False,
        "difficulty": "fluency",
    },
    "focused_questions": {
        "activity_type": "focused_questions",
        "display_name": "Focused Questions",
        "description": "Practice recent misses and low-evidence areas with first-attempt feedback.",
        "target_learning_problem": "weak_first_attempts",
        "supported_skill_types": ["concept", "decision", "communication", "process", "calculation_data", "analysis"],
        "supported_learner_actions": ["classify", "choose", "respond", "sequence", "calculate", "diagnose"],
        "minimum_evidence": 1,
        "recommended_duration": 5,
        "requires_multiple_kpis": False,
        "requires_questions": True,
        "requires_prior_learning": False,
        "supports_timer": False,
        "difficulty": "remediate",
    },
}


def _activity(name, reason, topic=None):
    selected = dict(ACTIVITIES[name])
    selected["reason"] = reason
    if topic:
        selected["topic"] = topic
    return selected


def select_activity(state):
    """Choose the next learning format from current evidence, never labels."""
    coverage = state.get("coverage") or {}
    studied = int(coverage.get("studied") or 0)
    total = int(coverage.get("total") or 0)
    coverage_pct = float(coverage.get("percent") or 0)
    attempts = int(state.get("practice_attempt_count") or 0)
    qualified_weakness = state.get("qualified_weakest_topic")
    application_attempts = int(state.get("application_attempt_count") or 0)
    application_accuracy = state.get("application_accuracy")
    recognition_attempts = int(state.get("recognition_attempt_count") or 0)
    timing_samples = int(state.get("question_timing_sample_count") or 0)

    if state.get("unfinished_practice"):
        return _activity("focused_questions", "You have unfinished practice that is still the most relevant next step.", qualified_weakness.get("topic") if qualified_weakness else None)
    if coverage_pct < 50 or not studied:
        return _activity("learn", f"You have studied {studied} of {total} KPIs, so more guided coverage is needed before timed practice.")
    if qualified_weakness and application_attempts >= 3 and application_accuracy is not None and float(application_accuracy) < 70:
        return _activity("scenario_sprint", f"Your {qualified_weakness['topic']} evidence is stronger on recall than application; use a short scenario to practice choosing a response.", qualified_weakness["topic"])
    if qualified_weakness and attempts >= 10:
        return _activity("focused_questions", f"You missed recent first attempts in {qualified_weakness['topic']}; targeted questions can address the gap without inflating mastery.", qualified_weakness["topic"])
    if studied >= 2 and recognition_attempts >= 3 and application_attempts == 0:
        return _activity("personal_connection", "You have learned several KPIs but have little application evidence; explain one in your own words before more questions.")
    if studied >= 4 and attempts >= 10 and timing_samples < 10:
        return _activity("pi_fluency", "Coverage and first-attempt evidence are established, but retrieval speed has not been measured yet.")
    if studied >= 4 and attempts >= 20:
        return _activity("scenario_sprint", "You have broad coverage and evidence; mix KPIs in a short DECA-style scenario.")
    return _activity("personal_connection", "Evidence is not yet specific enough to distinguish recall from application, so build comprehension with one short explanation.")