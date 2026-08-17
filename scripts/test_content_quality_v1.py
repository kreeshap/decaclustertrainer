"""Deterministic tests for DECA Content Quality Pipeline v1."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.content_quality import (  # noqa: E402
    ContentQualityError,
    style_metrics,
    validate_demonstration_score,
    validate_exam_item,
    validate_knowledge_pack,
    validate_roleplay_spec,
)


def expect_error(callback):
    try:
        callback()
    except ContentQualityError:
        return
    raise AssertionError("expected ContentQualityError")


def main():
    pack = validate_knowledge_pack({"claims": [{"knowledge_type": "formula", "content": "Gross profit equals sales minus cost of goods sold.", "source_references": [{"document": "source", "page": 1}]}]}, "finance:FI:000")
    assert pack["claims"][0]["review_status"] == "pending"
    expect_error(lambda: validate_knowledge_pack({"claims": [{"knowledge_type": "rule", "content": "Unsupported claim", "source_references": []}]}, "x"))

    item = validate_exam_item({
        "stem": "A manager must calculate gross profit for the current month. What should the manager subtract from sales?",
        "choices": ["Cost of goods sold", "Total assets", "Owner equity", "Accounts receivable"],
        "correct_index": 0,
        "choice_rationales": ["This is the gross-profit formula.", "Assets are not subtracted from sales.", "Equity is not an expense.", "Receivables describe unpaid sales."],
        "cognitive_demand": "application", "instructional_area": "Financial Analysis", "source_claim_ids": ["claim-1"],
    }, kpi_code="FI:000", approved_claim_ids={"claim-1"})
    assert item["publish_status"] == "pending_review"
    expect_error(lambda: validate_exam_item({
        "stem": "A manager must calculate gross profit for the current month.",
        "choices": ["Cost of goods sold", "Total assets", "Owner equity", "Accounts receivable"],
        "correct_index": 0,
        "choice_rationales": ["This is the formula.", "Assets are unrelated.", "Equity is unrelated.", "Receivables are unrelated."],
        "cognitive_demand": "application", "instructional_area": "Financial Analysis",
        "source_claim_ids": ["invented-claim"],
    }, kpi_code="FI:000", approved_claim_ids={"claim-1"}))
    expect_error(lambda: validate_exam_item({"choices": []}, kpi_code="FI:000"))

    roleplay = validate_roleplay_spec({"business_skill": "Evaluate financing choices", "business_problem": "A growing retailer must finance inventory without creating an unsustainable cash burden.", "participant_role": "Financial consultant", "judge_role": "Owner", "judge_questions": ["Why is this financing choice appropriate?"], "kpis": [{"code": "FI:001"}]}, eligible_codes={"FI:001"})
    assert roleplay["kpis"][0]["code"] == "FI:001"
    expect_error(lambda: validate_roleplay_spec({"business_skill": "Choose financing", "business_problem": "A sufficiently detailed business problem that requires a decision.", "participant_role": "Advisor", "judge_role": "Owner", "judge_questions": ["Why choose it?"], "kpis": [{"code": "FI:999"}]}, eligible_codes={"FI:001"}))

    score = validate_demonstration_score({"demonstration_level": 4, "applied_to_situation": True, "justified_recommendation": True, "tied_to_business_outcome": True, "evidence": "Connected the recommendation to cash flow.", "feedback": "Quantify the expected benefit."}, "FI:001")
    assert score["demonstration_label"] == "applied_justified_outcome"
    vocabulary_only = validate_demonstration_score({"demonstration_level": 4, "applied_to_situation": False, "justified_recommendation": False, "tied_to_business_outcome": False, "evidence": "Repeated the KPI vocabulary.", "feedback": "Apply it to the scenario."}, "FI:001")
    assert vocabulary_only["demonstration_level"] <= 1
    assert style_metrics([{"stem": "A manager calculates a 20 percent margin."}])["calculation_frequency"] == 1

    migration = (ROOT / "supabase" / "migrations" / "20260817010000_deca_content_quality_v1.sql").read_text(encoding="utf-8").lower()
    for requirement in ("enable row level security", "revoke all", "grant select", "demonstration_level between 0 and 4", "source_claim_ids"):
        assert requirement in migration
    evidence_migration = (ROOT / "supabase" / "migrations" / "20260817012000_separate_factual_and_deca_evidence.sql").read_text(encoding="utf-8").lower()
    for requirement in ("factual_evidence", "deca_evidence", "review_checklist", "reverify_after", "alignment_or_style"):
        assert requirement in evidence_migration
    print("DECA Content Quality Pipeline v1 tests passed.")


if __name__ == "__main__":
    main()
