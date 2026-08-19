"""Contract and adversarial checks for Practice Corpus v1."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.practice_corpus import exam_review_flags, parse_roleplay, readiness, suggest_metadata, text_fingerprint  # noqa: E402


def main():
    text = """2026 ICDC ACT DECA
PARTICIPANT INSTRUCTIONS
You are to assume the role of financial consultant. Recommend a financing approach and explain FI:001.
THE SITUATION
A retailer needs inventory financing while protecting cash flow and managing risk.
JUDGE INSTRUCTIONS
You are the owner. Evaluate the recommendation.
JUDGE QUESTIONS
1. Why is this option appropriate?
2. What risk should the business monitor?
EVALUATION CRITERIA
Applies the performance indicators to the business problem.
"""
    suggestions = suggest_metadata(text, "2026_ACT_ICDC.pdf", "roleplay")
    assert suggestions["event_codes"] == ["ACT"]
    assert suggestions["competition_level"] == "icdc"
    parsed = parse_roleplay(text, suggestions)
    assert parsed["event_code"] == "ACT"
    assert parsed["performance_indicators"] == ["FI:001"]
    assert parsed["official_tasks"] and len(parsed["judge_questions"]) == 2
    assert parsed["raw_sections"]["situation"]
    assert parsed["field_confidence"]["event_code"] == "high"
    assert "roleplay_section_boundary" not in parsed["review_flags"]
    assert text_fingerprint(text) == text_fingerprint(text)
    contaminated = {"question_text": "A manager needs to decide how", "choices": ["A", "B", "C", "D Copyright © 2026 Test 1324 FINANCE EXAM 2"], "correct_index": 1}
    assert set(exam_review_flags(contaminated)) == {"exam_choice_split", "header_contamination"}

    docs = [{"id": str(i), "content_type": "exam", "processing_state": "verified_reference",
             "benchmark_eligible": True, "event_codes": ["ACT"], "cluster": "Finance",
             "competitive_year": str(2020 + i), "competition_level": "icdc"} for i in range(5)]
    items = [{"document_id": str(i % 5), "human_verified": True, "pi_code": None} for i in range(20)]
    assert readiness("exam", docs, items, cluster="Finance")["status"] == "generator_ready"
    assert readiness("exam", docs[:2], items, cluster="Finance")["status"] == "insufficient"

    roleplay_docs = [{"id": str(i), "content_type": "roleplay", "processing_state": "verified_reference",
                      "benchmark_eligible": True, "event_codes": ["ACT"], "cluster": "Finance",
                      "competitive_year": "2026-27", "competition_level": "association"} for i in range(15)]
    roleplays = [{"document_id": str(i), "human_verified": True} for i in range(15)]
    assert readiness("roleplay", roleplay_docs, roleplays, event_code="ACT", cluster="Finance")["status"] == "generator_ready"

    migration = (ROOT / "supabase" / "migrations" / "20260817013000_practice_corpus_v1.sql").read_text(encoding="utf-8").lower()
    for requirement in ("practice-corpus-private", "enable row level security", "revoke all", "benchmark_eligible", "student_publishable", "normalized_text_hash", "parser_version", "verified_reference"):
        assert requirement in migration
    admin = (ROOT / "app" / "routes" / "admin.py").read_text(encoding="utf-8")
    learn = (ROOT / "app" / "routes" / "learn.py").read_text(encoding="utf-8")
    assert "Original question generation is disabled during Practice Corpus v1" in admin
    assert "Generated roleplays are disabled" in learn
    template = (ROOT / "templates" / "adminpanel.html").read_text(encoding="utf-8")
    assert ">Practice Corpus<" in template
    assert "Roleplays / Case Studies" in template
    assert "AI generation locked" in template
    assert "Approve clean questions" not in template
    assert "Learn enrichment proposals" not in template
    assert "Career cluster" in template and "Event code" in template
    assert "data-corpus-type" not in template
    assert 'name="source_name"' not in template
    assert 'name="source_url"' not in template
    assert "all exams are free" not in template.lower()  # behavior belongs in the server contract, not UI copy
    assert 'rights = "licensed_for_student_use" if content_type == "exam"' in admin
    css = (ROOT / "static" / "styles" / "adminpanel.css").read_text(encoding="utf-8")
    assert "[hidden] { display:none !important; }" in css
    admin_js = (ROOT / "static" / "js" / "adminpanel.js").read_text(encoding="utf-8")
    assert "data-question-filter" in admin_js
    assert "corpus-source" not in admin_js and "corpus-url" not in admin_js
    assert "const form = event.currentTarget;" in admin_js
    assert "event.currentTarget.reset()" not in admin_js
    assert "data-corpus-choice" in template
    assert '"stem": stem, "choices": choices' in admin
    assert "corpus_parse_attempts" in admin
    assert "corpus-parse-log" in template
    assert "corpus-exam-review-count" in template
    parse_attempt_migration = (ROOT / "supabase" / "migrations" / "20260818010000_corpus_parse_attempts.sql").read_text(encoding="utf-8").lower()
    for requirement in ("enable row level security", "revoke all", "status", "error_message", "document_id"):
        assert requirement in parse_attempt_migration
    pilot_migration = (ROOT / "supabase" / "migrations" / "20260817015000_real_corpus_pilot.sql").read_text(encoding="utf-8").lower()
    for requirement in ("corpus_parser_failures", "field_confidence", "review_priority", "gold_reference", "stability_delta"):
        assert requirement in pilot_migration
    print("Practice Corpus v1 tests passed.")


if __name__ == "__main__":
    main()
