import json

from .config import BASE_DIR, SUPABASE_SERVICE_ROLE_KEY
from .db import supabase_rest_request

KPI_DIR = BASE_DIR / "performance indicator jsons"

# Maps (folder_name, file_stem) -> event metadata dict, or None to skip the file.
# Add a new entry here whenever a new event JSON is added.
_EVENT_META: dict[tuple[str, str], dict | None] = {
    # Finance cluster ─────────────────────────────────────────────────────────
    # Files are now named exactly like their DECA events (e.g.
    # "Financial Services Team Decision Making.json").
    # The fallback logic uses the file stem as the event name and the
    # capitalised folder name as the DECA cluster, so no entry is needed
    # for files whose stem already matches the event name exactly.
    #
    # Legacy file — still holds the KPI data; maps to the TDM event.
    ("finance", "Finance"): {
        "event_id": "financial_services_tdm",
        "name": "Financial Services Team Decision Making",
        "cluster": "Finance",
    },
    # The properly-named file is a pointer note only — skip it so the
    # legacy Finance.json is the sole source of KPIs for this event.
    ("finance", "Financial Services Team Decision Making"): None,
}


def _load_all_kpis() -> tuple[list[dict], list[dict]]:
    """Load all KPIs from JSON files.  Returns (kpis, events)."""
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
                continue  # explicitly skipped (pointer / note file)
            event_id = meta["event_id"]
            event_name = meta["name"]
            cluster_label = meta["cluster"]
        else:
            # Fallback: file stem IS the event name (files are now named
            # after their DECA event exactly), and the folder name is the
            # DECA cluster (title-cased, underscores replaced with spaces).
            event_id = file_stem.lower().replace(" ", "_")
            event_name = file_stem  # already human-readable
            cluster_label = folder_name.replace("_", " ").title()

        # Skip empty files ───────────────────────────────────────────────────
        if json_file.stat().st_size == 0:
            continue

        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        tiers = data.get("tiers", {})
        if not isinstance(tiers, dict) or not tiers:
            continue  # no actual KPI data

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
            tier_label = "Tier 1" if "tier1" in tier_key else "Tier 2"
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

    return all_kpis, events


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


def _fetch_kpi_questions(kpi_code: str) -> list[dict]:
    """Fetch all questions for a KPI from Supabase (service role read)."""
    status, rows = _supabase_svc(
        "/kpi_questions",
        params={
            "kpi_code": f"eq.{kpi_code}",
            "select": "id,kpi_code,kpi_text,kpi_cluster,deca_cluster,event_id,question_text,choices,correct_index,explanation",
            "order": "created_at.asc",
        },
    )
    if status == 200 and isinstance(rows, list):
        return rows
    return []


def _normalise_db_question(row: dict) -> dict:
    """Map a kpi_questions DB row to the shape the frontend expects."""
    return {
        "id": row.get("id", ""),  # Supabase UUID (used for answer recording)
        "text": row.get("question_text", ""),
        "choices": row.get("choices", []),
        "correct": row.get("correct_index", 0),
        "explanation": row.get("explanation", ""),
        "kpi_code": row.get("kpi_code", ""),
        "kpi_text": row.get("kpi_text", ""),
        "cluster": row.get("kpi_cluster", ""),
        "deca_cluster": row.get("deca_cluster", ""),
        "event_id": row.get("event_id", ""),
    }


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
    If questions already exist for this KPI (>=30 rows) returns existing rows,
    otherwise inserts new ones and returns the inserted rows with UUIDs.
    """
    existing = _fetch_kpi_questions(kpi_code)
    if len(existing) >= 30:
        return [_normalise_db_question(r) for r in existing]

    rows = [
        {
            "kpi_code": kpi_code,
            "kpi_text": kpi_text,
            "kpi_cluster": kpi_cluster,
            "deca_cluster": deca_cluster,
            "event_id": event_id,
            "question_text": q.get("text", ""),
            "choices": q.get("choices", []),
            "correct_index": int(q.get("correct", 0)),
            "explanation": q.get("explanation", ""),
        }
        for q in questions
        if q.get("text")
    ]
    if not rows:
        return []

    status, saved = _supabase_svc(
        "/kpi_questions", method="POST", payload=rows, prefer="return=representation"
    )
    if status in (200, 201) and isinstance(saved, list):
        return [_normalise_db_question(r) for r in saved]
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
        params={"kpi_code": f"eq.{kpi_code}", "select": "id"},
    )
    total_q = len(q_rows) if isinstance(q_rows, list) else 0

    # Fetch all SRS states for this user + kpi
    _, srs_rows = supabase_rest_request(
        "/user_srs_state",
        token=token,
        params={
            "user_id": f"eq.{user_id}",
            "select": "question_id,interval_days,correct_attempts,total_attempts,next_review",
        },
        prefer="",
    )

    # Filter to questions belonging to this KPI
    kpi_q_ids = {r["id"] for r in (q_rows or [])}
    kpi_srs = [r for r in (srs_rows or []) if r.get("question_id") in kpi_q_ids]

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
        prefer="resolution=merge-duplicates,return=minimal",
    )
    return payload


def _upsert_daily_activity(
    user_id: str,
    token: str,
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
            "select": "*",
        },
        prefer="",
    )
    existing = rows[0] if isinstance(rows, list) and rows else {}

    payload = {
        "user_id": user_id,
        "activity_date": today,
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
        kpis, _ = _load_all_kpis()
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

    _, mastery_rows = supabase_rest_request(
        "/user_kpi_mastery", token=token,
        params={
            "user_id":  f"eq.{user_id}",
            "event_id": f"eq.{event_id}",
            "select":   "kpi_code,mastery_score,next_review",
        },
        prefer="",
    )
    mastery_map = {r["kpi_code"]: r for r in (mastery_rows or [])}

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
