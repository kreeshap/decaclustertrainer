import json
import re
import uuid

from .config import BASE_DIR, SUPABASE_SERVICE_ROLE_KEY
from .db import supabase_rest_request

KPI_DIR = BASE_DIR / "performance indicator jsons"

# Maps (folder_name, file_stem) -> event metadata dict, or None to skip the file.
_EVENT_META: dict[tuple[str, str], dict | None] = {
    # Legacy file — still holds the KPI data; maps to the TDM event.
    ("finance", "Finance"): {
        "event_id": "financial_services_tdm",
        "name": "Financial Services Team Decision Making",
        "cluster": "Finance",
    },
    # The properly-named file is a pointer note only — skip it.
    ("finance", "Financial Services Team Decision Making"): None,
}

# ── Module-level KPI cache ─────────────────────────────────────────────────────
# Loaded once per process; cleared if the underlying files change (restart server).
_KPI_CACHE: tuple[list[dict], list[dict]] | None = None


def _load_all_kpis(force_reload: bool = False) -> tuple[list[dict], list[dict]]:
    """Load all KPIs from JSON files.  Returns (kpis, events).
    Results are cached in-process so disk is only read once per server start."""
    global _KPI_CACHE
    if _KPI_CACHE is not None and not force_reload:
        return _KPI_CACHE

    all_kpis: list[dict] = []
    events: list[dict] = []
    seen_event_ids: set[str] = set()

    for json_file in sorted(KPI_DIR.rglob("*.json")):
        folder_name = json_file.parent.name
        file_stem = json_file.stem
        map_key = (folder_name, file_stem)

        # Determine event metadata ───────────────────────────────────────────
        if map_key in _EVENT_META:
            meta = _EVENT_META[map_key]
            if meta is None:
                continue  # explicitly skipped
            event_id = meta["event_id"]
            event_name = meta["name"]
            cluster_label = meta["cluster"]
        else:
            event_id = file_stem.lower().replace(" ", "_")
            event_name = file_stem
            cluster_label = folder_name.replace("_", " ").title()

        if json_file.stat().st_size == 0:
            continue

        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        # ── Accept both "tiers" and any top-level key that looks like a tier dict
        # This handles files that use "tier3_accounting_pathway" etc. directly
        tiers = data.get("tiers")
        if tiers is None:
            # Fall back: collect any top-level dict whose key starts with "tier"
            tiers = {
                k: v for k, v in data.items()
                if isinstance(v, dict) and k.lower().startswith("tier")
            }
        if not isinstance(tiers, dict) or not tiers:
            continue

        # Count real indicators before registering the event ─────────────────
        has_indicators = any(
            isinstance(cd, dict) and cd.get("indicators")
            for td in tiers.values()
            if isinstance(td, dict)
            for cd in td.values()
            if isinstance(cd, dict)
        )
        if not has_indicators:
            continue

        if event_id not in seen_event_ids:
            seen_event_ids.add(event_id)
            events.append(
                {
                    "id": event_id,
                    "name": event_name,
                    "cluster": cluster_label,
                    "folder": folder_name,
                }
            )

        for tier_key, tier_data in tiers.items():
            tier_label = "Tier 1" if "tier1" in tier_key else (
                "Tier 2" if "tier2" in tier_key else
                "Tier 3" if "tier3" in tier_key else tier_key
            )
            if not isinstance(tier_data, dict):
                continue
            for kpi_cluster_name, cluster_data in tier_data.items():
                if not isinstance(cluster_data, dict):
                    continue
                standard = cluster_data.get("standard", "")
                for indicator in cluster_data.get("indicators", []):
                    all_kpis.append(
                        {
                            "code": indicator.get("code", ""),
                            "text": indicator.get("text", ""),
                            "level": indicator.get("level", ""),
                            "cluster": kpi_cluster_name,
                            "standard": standard,
                            "event": event_id,
                            "event_name": event_name,
                            "deca_cluster": cluster_label,
                            "folder": folder_name,
                            "tier": tier_label,
                        }
                    )

    _KPI_CACHE = (all_kpis, events)
    return _KPI_CACHE


def _supabase_svc(
    path: str,
    method: str = "GET",
    payload=None,
    params: dict | None = None,
    prefer: str = "",
):
    """Hit the PostgREST REST API with the service-role key (bypasses RLS)."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        return 500, {"detail": "SUPABASE_SERVICE_ROLE_KEY not set"}
    return supabase_rest_request(
        path,
        method=method,
        token=SUPABASE_SERVICE_ROLE_KEY,
        payload=payload,
        params=params,
        prefer=prefer or "return=representation",
    )


def _fetch_kpi_questions(kpi_code: str, event_id: str) -> list[dict]:
    """Fetch all questions for a KPI from Supabase (service role read)."""
    status, rows = _supabase_svc(
        "/kpi_questions",
        params={
            "kpi_code": f"eq.{kpi_code}",
            "event_id": f"eq.{event_id}",
            "select": "id,kpi_code,kpi_text,kpi_cluster,deca_cluster,event_id,question_text,choices,correct_index,explanation,question_type,question_slot,quality_state,answer_reveal",
            "order": "question_type.desc,question_slot.asc",
        },
    )
    if status == 200 and isinstance(rows, list):
        return rows
    return []


def _tokenize_text(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}


def _quality_band(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "strong"
    if score >= 55:
        return "usable"
    if score >= 40:
        return "weak"
    return "poor"


def _bounded(score: float) -> int:
    return max(0, min(100, int(round(score))))


def _build_answer_reveal(question_text: str, choices: list, correct_index: int, explanation: str,
                         distractor_quality: list[dict]) -> dict:
    correct_choice = choices[correct_index] if 0 <= correct_index < len(choices) else ""
    distractors = []
    for item in distractor_quality:
        if item.get("role") == "distractor":
            distractors.append(
                {
                    "index": item.get("index"),
                    "choice": item.get("choice", ""),
                    "role": "distractor",
                    "why_it_isnt_right": item.get("why_it_isnt_right", ""),
                    "plausibility": item.get("score", 0),
                }
            )
    return {
        "correct_index": correct_index,
        "correct_choice": correct_choice,
        "prompt": question_text,
        "explanation": explanation or "",
        "distractors": distractors,
    }


def _compute_quality_state(question_text: str, choices: list, correct_index: int,
                           explanation: str, question_type: str) -> dict:
    """Heuristic MCQ + distractor quality state stored with each question."""
    clean_choices = [str(choice or "").strip() for choice in (choices or [])[:4]]
    while len(clean_choices) < 4:
        clean_choices.append("")

    correct_choice = clean_choices[correct_index] if 0 <= correct_index < 4 else ""
    choice_tokens = [_tokenize_text(choice) for choice in clean_choices]
    correct_tokens = choice_tokens[correct_index] if 0 <= correct_index < 4 else set()
    unique_count = len({c.lower() for c in clean_choices if c})
    non_empty = sum(1 for c in clean_choices if c)

    stem_words = len(_tokenize_text(question_text))
    stem_target = 18 if question_type == "application" else 12
    stem_upper = 42 if question_type == "application" else 28
    if stem_words < 6:
        stem_score = 25
    elif stem_words < stem_target:
        stem_score = 55 + ((stem_words - 6) / max(stem_target - 6, 1)) * 30
    elif stem_words <= stem_upper:
        stem_score = 90
    else:
        stem_score = max(45, 90 - (stem_words - stem_upper) * 2)

    explanation_words = len(_tokenize_text(explanation))
    explanation_score = 35
    if explanation_words >= 16:
        explanation_score += 25
    if explanation_words >= 30:
        explanation_score += 20
    if "because" in (explanation or "").lower():
        explanation_score += 10
    if "wrong" in (explanation or "").lower():
        explanation_score += 10

    uniqueness_score = 100 if non_empty == 0 else (unique_count / max(non_empty, 1)) * 100
    balance_score = 50
    if non_empty >= 2:
        lengths = [len(choice) for choice in clean_choices if choice]
        avg_len = sum(lengths) / len(lengths)
        spread = sum(abs(length - avg_len) for length in lengths) / len(lengths)
        balance_score = max(0, 100 - spread * 2.5)

    distractor_state = []
    distractor_scores = []
    for idx, choice in enumerate(clean_choices):
        tokens = choice_tokens[idx]
        length = len(choice)
        if idx == correct_index:
            distractor_state.append(
                {
                    "index": idx,
                    "choice": choice,
                    "role": "correct",
                    "score": 100,
                    "level": "correct",
                    "why_it_isnt_right": "",
                }
            )
            continue

        overlap = 0.0
        if correct_tokens or tokens:
            union = len(correct_tokens | tokens) or 1
            overlap = len(correct_tokens & tokens) / union
        length_ratio = min(length, len(correct_choice) or 1) / max(max(length, len(correct_choice)), 1)
        plausibility = 100 - (abs(overlap - 0.25) * 130) - (abs(length_ratio - 0.80) * 40)
        plausibility -= 10 if not choice else 0
        plausibility = _bounded(plausibility)
        level = _quality_band(plausibility)
        distractor_state.append(
            {
                "index": idx,
                "choice": choice,
                "role": "distractor",
                "score": plausibility,
                "level": level,
                "why_it_isnt_right": (
                    "Too vague to compete with the correct answer"
                    if plausibility < 40
                    else "Plausible but weaker than the keyed answer"
                ),
            }
        )
        distractor_scores.append(plausibility)

    mcq_score = (
        stem_score * 0.30
        + uniqueness_score * 0.15
        + balance_score * 0.15
        + explanation_score * 0.15
        + (sum(distractor_scores) / max(len(distractor_scores), 1)) * 0.25
    )
    mcq_score = _bounded(mcq_score)

    return {
        "mcq_quality": {
            "score": mcq_score,
            "level": _quality_band(mcq_score),
            "signals": {
                "stem_score": _bounded(stem_score),
                "uniqueness_score": _bounded(uniqueness_score),
                "balance_score": _bounded(balance_score),
                "explanation_score": _bounded(explanation_score),
            },
        },
        "distractor_quality": distractor_state,
        "answer_reveal": _build_answer_reveal(
            question_text, clean_choices, correct_index, explanation, distractor_state
        ),
    }


def _ensure_quality_state(row: dict) -> dict:
    quality_state = row.get("quality_state") or {}
    answer_reveal = row.get("answer_reveal") or {}
    if quality_state and answer_reveal:
        return quality_state

    computed = _compute_quality_state(
        row.get("question_text", ""),
        row.get("choices", []),
        int(row.get("correct_index", 0)),
        row.get("explanation", ""),
        row.get("question_type", "recognition"),
    )
    if not quality_state:
        row["quality_state"] = computed
    if not answer_reveal:
        row["answer_reveal"] = computed["answer_reveal"]
    return row["quality_state"]


def _normalise_db_question(row: dict) -> dict:
    """Map a kpi_questions DB row to the shape the frontend expects."""
    _ensure_quality_state(row)
    return {
        "id": row.get("id", ""),
        "text": row.get("question_text", ""),
        "choices": row.get("choices", []),
        "correct": row.get("correct_index", 0),
        "explanation": row.get("explanation", ""),
        "kpi_code": row.get("kpi_code", ""),
        "kpi_text": row.get("kpi_text", ""),
        "cluster": row.get("kpi_cluster", ""),
        "deca_cluster": row.get("deca_cluster", ""),
        "event_id": row.get("event_id", ""),
        "question_type": row.get("question_type", "recognition"),
        "quality_state": row.get("quality_state", {}) or {},
        "answer_reveal": row.get("answer_reveal", {}) or {},
    }


def _select_final_practice_questions(rows: list[dict]) -> list[dict]:
    """Return the app's final 3-question shape: Check, Apply, DECA Challenge."""
    recognition = [r for r in rows if r.get("question_type") == "recognition"]
    application = [r for r in rows if r.get("question_type") == "application"]
    if len(recognition) < 2 or len(application) < 1:
        return []
    return [*[_normalise_db_question(r) for r in recognition[:2]], _normalise_db_question(application[0])]


def _save_questions_supabase(
    questions: list,
    kpi_code: str,
    kpi_text: str,
    kpi_cluster: str,
    deca_cluster: str,
    event_id: str,
) -> list[dict]:
    """
    Persist generated questions to kpi_questions.
    If questions already exist for this KPI (>= 3 rows, at least 2 recognition
    and 1 application row) returns existing rows. Otherwise inserts missing
    stable slots and returns the first three normalized rows.
    returns existing rows. Otherwise inserts new ones and returns them with UUIDs.
    """
    existing = _fetch_kpi_questions(kpi_code, event_id)
    recognition_count = sum(r.get("question_type") == "recognition" for r in existing)
    application_count = sum(r.get("question_type") == "application" for r in existing)
    if len(existing) >= 3 and recognition_count >= 2 and application_count >= 1:
        return _select_final_practice_questions(existing)

    rows = []
    type_slots = {"recognition": 0, "application": 0}
    for q in questions:
        if not q.get("text"):
            continue
        question_type = q.get("question_type", "recognition")
        question_slot = type_slots.get(question_type, 0)
        type_slots[question_type] = question_slot + 1
        stable_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"deca-cluster-trainer:{event_id}:{kpi_code}:{question_type}:{question_slot}",
        )
        rows.append(
            {
                "id": str(stable_id),
                "kpi_code": kpi_code,
                "kpi_text": kpi_text,
                "kpi_cluster": kpi_cluster,
                "deca_cluster": deca_cluster,
                "event_id": event_id,
                "question_text": q.get("text", ""),
                "choices": q.get("choices", []),
                "correct_index": int(q.get("correct", 0)),
                "explanation": q.get("explanation", ""),
                "question_type": question_type,
                "question_slot": question_slot,
            }
        )
    if not rows:
        return []

    enriched_rows = []
    for row, q in zip(rows, [q for q in questions if q.get("text")]):
        quality_state = _compute_quality_state(
            row["question_text"],
            row["choices"],
            row["correct_index"],
            row["explanation"],
            row["question_type"],
        )
        row["quality_state"] = quality_state
        row["answer_reveal"] = quality_state["answer_reveal"]
        enriched_rows.append(row)

    status, _ = _supabase_svc(
        "/kpi_questions", method="POST", payload=enriched_rows,
        params={"on_conflict": "event_id,kpi_code,question_type,question_slot"},
        prefer="resolution=ignore-duplicates,return=minimal",
    )
    if status in (200, 201, 204):
        saved = _fetch_kpi_questions(kpi_code, event_id)
        recognition_count = sum(r.get("question_type") == "recognition" for r in saved)
        application_count = sum(r.get("question_type") == "application" for r in saved)
        if len(saved) >= 3 and recognition_count >= 2 and application_count >= 1:
            return _select_final_practice_questions(saved)
    return []


def compute_sm2(
    ease_factor: float,
    interval_days: int,
    repetitions: int,
    quality: int,  # 0=blackout 1=wrong 2=almost 3=hard-correct 4=correct 5=perfect
) -> tuple:
    """
    Returns (new_ease_factor, new_interval_days, new_repetitions, next_review_iso_utc).
    Implements the SM-2 algorithm with a minimum ease factor of 1.3.
    """
    from datetime import datetime, timedelta

    if quality < 3:  # wrong or near-miss → reset
        new_reps = 0
        new_interval = 1
    else:  # correct
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = max(1, round(interval_days * ease_factor))
        new_reps = repetitions + 1

    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    new_ef = max(1.3, round(ease_factor + delta, 2))

    next_dt = datetime.utcnow() + timedelta(days=new_interval)
    return new_ef, new_interval, new_reps, next_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_mastery_score(
    questions_seen: int,
    questions_mastered: int,  # interval_days >= 7
    total_questions: int,
    avg_interval: float,
) -> float:
    """
    Mastery score 0-100.
    Weights: accuracy 45%, coverage 40%, SRS stability 15%.
    """
    if total_questions == 0 or questions_seen == 0:
        return 0.0
    coverage = min(questions_seen / max(total_questions, 1), 1.0)
    accuracy = questions_mastered / max(questions_seen, 1)
    stability = min(avg_interval / 21.0, 1.0)  # 21-day intervals → full stability
    return round(
        min((accuracy * 0.45 + coverage * 0.40 + stability * 0.15) * 100, 100.0), 1
    )


def _update_kpi_mastery(
    user_id: str,
    token: str,
    kpi_code: str,
    kpi_cluster: str,
    deca_cluster: str,
    event_id: str,
) -> dict:
    """
    Re-compute and upsert the user_kpi_mastery row for one KPI.
    Pulls live SRS state from user_srs_state joined with kpi_questions.
    Returns the new mastery row.
    """
    from datetime import datetime

    # How many questions exist for this KPI?
    _, q_rows = _supabase_svc(
        "/kpi_questions",
        params={"kpi_code": f"eq.{kpi_code}", "event_id": f"eq.{event_id}", "select": "id"},
    )
    total_q = len(q_rows) if isinstance(q_rows, list) else 0

    # Fetch all SRS states for this user + kpi
    _, srs_rows = supabase_rest_request(
        "/user_srs_state",
        token=token,
        params={
            "user_id": f"eq.{user_id}",
            "event_id": f"eq.{event_id}",
            "select": "question_id,interval_days,correct_attempts,total_attempts,next_review",
        },
        prefer="",
    )

    # Filter to questions belonging to this KPI
    kpi_q_ids = {r["id"] for r in (q_rows if isinstance(q_rows, list) else [])}
    kpi_srs = [r for r in (srs_rows if isinstance(srs_rows, list) else []) if r.get("question_id") in kpi_q_ids]

    seen = len(kpi_srs)
    mastered = sum(1 for r in kpi_srs if r.get("interval_days", 0) >= 7)
    avg_iv = (sum(r.get("interval_days", 0) for r in kpi_srs) / seen) if seen else 0.0
    score = compute_mastery_score(seen, mastered, total_q, avg_iv)

    # Earliest next_review among open questions
    reviews = [r["next_review"] for r in kpi_srs if r.get("next_review")]
    next_rev = min(reviews) if reviews else None

    payload = {
        "user_id": user_id,
        "kpi_code": kpi_code,
        "kpi_cluster": kpi_cluster,
        "deca_cluster": deca_cluster,
        "event_id": event_id,
        "mastery_score": score,
        "questions_seen": seen,
        "questions_mastered": mastered,
        "total_questions": total_q,
        "last_studied": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "next_review": next_rev,
    }
    supabase_rest_request(
        "/user_kpi_mastery",
        method="POST",
        token=token,
        payload=payload,
        params={"on_conflict": "user_id,event_id,kpi_code"},
        prefer="resolution=merge-duplicates,return=minimal",
    )
    return payload


def _upsert_daily_activity(
    user_id: str,
    token: str,
    event_id: str,
    q_answered: int = 0,
    q_correct: int = 0,
    kpis_delta: int = 0,
    minutes: int = 0,
) -> None:
    """Atomically increment today's daily activity row."""
    from datetime import date

    today = date.today().isoformat()

    # Fetch existing row
    _, rows = supabase_rest_request(
        "/user_daily_activity",
        token=token,
        params={
            "user_id": f"eq.{user_id}",
            "activity_date": f"eq.{today}",
            "event_id": f"eq.{event_id}",
            "select": "*",
        },
        prefer="",
    )
    existing = rows[0] if isinstance(rows, list) and rows else {}

    payload = {
        "user_id": user_id,
        "activity_date": today,
        "event_id": event_id,
        "questions_answered": existing.get("questions_answered", 0) + q_answered,
        "questions_correct": existing.get("questions_correct", 0) + q_correct,
        "kpis_studied": existing.get("kpis_studied", 0) + kpis_delta,
        "minutes_studied": existing.get("minutes_studied", 0) + minutes,
    }
    supabase_rest_request(
        "/user_daily_activity",
        method="POST",
        token=token,
        payload=payload,
        params={"on_conflict": "user_id,event_id,activity_date"},
        prefer="resolution=merge-duplicates,return=minimal",
    )


def _compute_streak(daily_rows: list) -> int:
    """Given rows ordered newest-first, return the current consecutive-day streak."""
    from datetime import date, timedelta

    if not daily_rows:
        return 0
    today = date.today()
    streak = 0
    expected = today
    for row in sorted(
        daily_rows, key=lambda r: r.get("activity_date", ""), reverse=True
    ):
        try:
            d = date.fromisoformat(row["activity_date"])
        except Exception:
            continue
        if d == expected and (
            row.get("questions_answered", 0) > 0 or row.get("kpis_studied", 0) > 0
        ):
            streak += 1
            expected = d - timedelta(days=1)
        elif d < expected:
            break
    return streak
# ── KPI meta cache (used by the answer route) ──────────────────────────────────

_KPI_META_CACHE: dict[str, dict] = {}


def _get_kpi_meta(kpi_code: str) -> dict:
    """Return cluster/deca_cluster/event_id for a KPI code (cached)."""
    global _KPI_META_CACHE
    if not _KPI_META_CACHE:
        kpis, _ = _load_all_kpis()  # uses module-level cache
        _KPI_META_CACHE = {
            k["code"]: {
                "cluster":      k["cluster"],
                "deca_cluster": k["deca_cluster"],
                "event_id":     k["event"],
            }
            for k in kpis
        }
    return _KPI_META_CACHE.get(kpi_code, {})


def get_due_kpis(user_id: str, token: str, event_id: str) -> list[dict]:
    """Return KPIs for an event that are due for review (or never started)."""
    from datetime import datetime

    all_kpis = [k for k in _load_all_kpis()[0] if k["event"] == event_id]

    mastery_status, mastery_rows = supabase_rest_request(
        "/user_kpi_mastery", token=token,
        params={
            "user_id":  f"eq.{user_id}",
            "event_id": f"eq.{event_id}",
            "select":   "kpi_code,mastery_score,next_review",
        },
        prefer="",
    )
    # mastery_rows must be a list of dicts; on error Supabase returns a dict
    if not isinstance(mastery_rows, list):
        mastery_rows = []
    mastery_map = {r["kpi_code"]: r for r in mastery_rows}

    now = datetime.utcnow().isoformat() + "Z"
    due = []
    for kpi in all_kpis:
        code = kpi["code"]
        m    = mastery_map.get(code)
        if m is None:                              # never studied
            due.append(kpi)
            continue
        if m.get("mastery_score", 0) < 80 or (m.get("next_review") or "") <= now:
            due.append(kpi)                        # not mastered or review due
    return due


def get_ready_kpi_ids() -> set[str]:
    status, rows = _supabase_svc(
        "/generated_kpi_lessons",
        params={"status": "eq.ready", "select": "kpi_id", "limit": "10000"},
    )
    if status != 200 or not isinstance(rows, list):
        raise RuntimeError("Generated lesson readiness could not be loaded")
    return {row["kpi_id"] for row in rows}


def get_kpi_catalog(user_id: str, token: str, event_id: str) -> dict:
    """Return student-ready KPIs for an event, classified for Learn/Resume UI."""
    from datetime import datetime, timezone

    kpis = [dict(k) for k in _load_all_kpis()[0] if k["event"] == event_id]
    ready_ids = get_ready_kpi_ids()
    kpis = [kpi for kpi in kpis if f"{kpi['event']}:{kpi['code']}" in ready_ids]
    status, rows = supabase_rest_request(
        "/user_kpi_mastery", token=token,
        params={"user_id": f"eq.{user_id}", "event_id": f"eq.{event_id}", "select": "kpi_code,mastery_score,next_review"},
        prefer="",
    )
    if status != 200 or not isinstance(rows, list):
        raise RuntimeError("KPI mastery state could not be loaded")
    mastery = {row["kpi_code"]: row for row in rows}
    now = datetime.now(timezone.utc)
    groups = {"unstarted": [], "due": [], "mastered": [], "in_progress": []}
    for kpi in kpis:
        row = mastery.get(kpi["code"])
        if row is None:
            label = "unstarted"
            kpi["mastery_score"] = 0
            kpi["next_review"] = None
        else:
            score = float(row.get("mastery_score") or 0)
            next_review = row.get("next_review")
            is_due = False
            if next_review:
                try:
                    is_due = datetime.fromisoformat(next_review.replace("Z", "+00:00")) <= now
                except (TypeError, ValueError):
                    is_due = True
            label = "due" if is_due else ("mastered" if score >= 80 else "in_progress")
            kpi["mastery_score"] = score
            kpi["next_review"] = next_review
        kpi["learning_status"] = label
        groups[label].append(kpi)
    ordered = groups["due"] + groups["unstarted"] + groups["in_progress"] + groups["mastered"]
    return {"kpis": ordered, **groups}
