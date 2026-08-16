"""Background lesson generation for the Admin 20-KPI adversarial audit."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from .content_ops import catalog_id, utc_now
from .learn_helpers import _load_all_kpis, _supabase_svc
from .lesson_design import build_lesson_prompt, classify_kpi
from .lesson_generation import generate_valid_lesson


def select_audit_kpis(limit: int = 20) -> list[tuple[dict, dict]]:
    status, approved_rows = _supabase_svc(
        "/kpi_classifications",
        params={
            "review_status": "in.(auto_approved,approved)",
            "select": "kpi_id,skill_type,complexity,primary_archetype,learner_action,deca_action,recommended_interactions",
            "limit": "10000",
        },
    )
    approved = {row["kpi_id"]: row for row in approved_rows} if status == 200 and isinstance(approved_rows, list) else {}
    candidates = []
    for kpi in _load_all_kpis()[0]:
        plan = approved.get(catalog_id(kpi)) or classify_kpi(kpi["text"])
        complexity = plan["complexity"]
        plan = {
            **plan,
            "target_minutes": {"quick": "2-3", "standard": "3-5", "deep": "5-7"}[complexity],
            "required_block_count": {"quick": 2, "standard": 3, "deep": 4}[complexity],
            "vocab_mode": "embedded" if complexity == "quick" else "preteach",
            "vocab_count": {"quick": 3, "standard": 4, "deep": 5}[complexity],
        }
        candidates.append((kpi, plan))
    targets = {"quick": 5, "standard": 10, "deep": 5}
    selected: list[tuple[dict, dict]] = []
    for complexity, target in targets.items():
        pool = [item for item in candidates if item[1]["complexity"] == complexity]
        used_skills: set[str] = set()
        used_clusters: set[str] = set()
        while pool and sum(1 for _, plan in selected if plan["complexity"] == complexity) < target:
            item = min(
                pool,
                key=lambda candidate: (
                    candidate[1]["skill_type"] in used_skills,
                    candidate[0].get("cluster", "") in used_clusters,
                ),
            )
            pool.remove(item)
            selected.append(item)
            used_skills.add(item[1]["skill_type"])
            used_clusters.add(item[0].get("cluster", ""))
    if len(selected) < limit:
        chosen = {catalog_id(kpi) for kpi, _ in selected}
        selected.extend(item for item in candidates if catalog_id(item[0]) not in chosen)
    return selected[:limit]


def _generate_audit_item(item: dict, kpi: dict, plan: dict) -> str:
    _supabase_svc(
        "/lesson_content_audits", method="PATCH",
        payload={"generation_status": "processing", "updated_at": utc_now()},
        params={"id": f"eq.{item['id']}"}, prefer="return=minimal",
    )
    prompt = build_lesson_prompt(
        code=kpi["code"], text=kpi["text"], cluster=kpi["cluster"],
        standard=kpi["standard"], deca_cluster=kpi.get("deca_cluster", ""),
        lesson_design=plan,
    )
    lesson, errors = generate_valid_lesson(prompt, plan)
    if lesson is None:
        _supabase_svc(
            "/lesson_content_audits", method="PATCH",
            payload={"generation_status": "failed", "failure_reason": " | ".join(errors)[:1500], "updated_at": utc_now()},
            params={"id": f"eq.{item['id']}"}, prefer="return=minimal",
        )
        return "failed"
    _supabase_svc(
        "/lesson_content_audits", method="PATCH",
        payload={"generation_status": "ready", "generated_lesson": lesson, "failure_reason": None, "updated_at": utc_now()},
        params={"id": f"eq.{item['id']}"}, prefer="return=minimal",
    )
    return "ready"


def process_audit_batch(batch_id: str, selected: list[tuple[dict, dict]]) -> None:
    _supabase_svc(
        "/lesson_audit_batches", method="PATCH",
        payload={"status": "processing", "started_at": utc_now()},
        params={"id": f"eq.{batch_id}"}, prefer="return=minimal",
    )
    _, items = _supabase_svc(
        "/lesson_content_audits",
        params={"batch_id": f"eq.{batch_id}", "select": "id,kpi_id", "order": "created_at.asc"},
    )
    item_by_kpi = {item["kpi_id"]: item for item in items or []}
    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_generate_audit_item, item_by_kpi[catalog_id(kpi)], kpi, plan)
            for kpi, plan in selected if catalog_id(kpi) in item_by_kpi
        ]
        outcomes.extend(future.result() for future in as_completed(futures))
    failed = outcomes.count("failed") + max(0, len(selected) - len(outcomes))
    _supabase_svc(
        "/lesson_audit_batches", method="PATCH",
        payload={
            "status": "failed" if failed else "complete",
            "processed_count": len(outcomes), "failed_count": failed,
            "completed_at": utc_now(),
        },
        params={"id": f"eq.{batch_id}"}, prefer="return=minimal",
    )


def launch_audit_batch(batch_id: str, selected: list[tuple[dict, dict]]) -> None:
    threading.Thread(
        target=process_audit_batch, args=(batch_id, selected), daemon=True,
        name=f"lesson-audit-{batch_id[:8]}",
    ).start()
