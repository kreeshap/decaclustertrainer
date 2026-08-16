import unittest
from pathlib import Path
from unittest.mock import patch

from app.question_ingestion import assess_item, build_style_profile, extract_pdf_questions, parse_reference_citation, question_hash


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase" / "migrations" / "20260816213000_question_pdf_ingestion.sql").read_text(encoding="utf-8")
KNOWLEDGE_SQL = (ROOT / "supabase" / "migrations" / "20260816213500_clustered_question_knowledge.sql").read_text(encoding="utf-8")
SOURCES_SQL = (ROOT / "supabase" / "migrations" / "20260816214000_sources_library.sql").read_text(encoding="utf-8")
ADMIN = (ROOT / "app" / "routes" / "admin.py").read_text(encoding="utf-8")
HTML = (ROOT / "templates" / "adminpanel.html").read_text(encoding="utf-8")


class _Page:
    def __init__(self, text): self.text = text
    def extract_text(self, **_): return self.text


class _Pdf:
    def __init__(self, text): self.pages = [_Page(text)]
    def __enter__(self): return self
    def __exit__(self, *_): return None


class QuestionIngestionContractTests(unittest.TestCase):
    def test_parser_separates_questions_and_descriptive_key(self):
        text = """1. A manager needs to choose a target market. What should happen first?
A. Define customer needs
B. Lower every price
C. Eliminate research
D. Target everyone
2. Which action protects cash flow?
A. Ignore receivables
B. Monitor collections
C. Increase waste
D. Stop forecasting

DESCRIPTIVE KEY
1. B
The manager must identify a useful segment before targeting it.
SOURCE: MK:001
SOURCE: Marketing textbook, p. 10.
2. B
Monitoring collections improves the timing of cash receipts.
SOURCE: FI:002
SOURCE: Finance textbook, p. 22.
"""
        with patch("app.question_ingestion.pdfplumber.open", return_value=_Pdf(text)):
            questions, stats = extract_pdf_questions(b"fake-pdf")
        self.assertEqual(stats["page_count"], 1)
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["correct_index"], 1)
        self.assertEqual(questions[0]["kpi_code"], "MK:001")
        self.assertIn("Marketing textbook", questions[0]["source_references"][0])
        self.assertNotIn("SOURCE:", questions[0]["explanation"])
        self.assertEqual(len(questions[0]["choices"]), 4)

    def test_rights_and_duplicates_are_review_gates(self):
        item = {"question_text": "Which option is correct?", "choices": ["a", "b", "c", "d"],
                "correct_index": 0, "kpi_code": "FI:001", "normalized_hash": question_hash("Which option is correct?")}
        assessed = assess_item(item, [{"id": "old", "question_text": item["question_text"], "normalized_hash": item["normalized_hash"]}], [], False)
        self.assertIn("reference_only", assessed["review_reasons"])
        self.assertIn("exact_duplicate", assessed["review_reasons"])
        self.assertEqual(assessed["review_status"], "pending")

    def test_staging_is_server_only_and_admin_guarded(self):
        for table in ("question_source_documents", "question_import_items"):
            self.assertIn(f"alter table public.{table} enable row level security", SQL)
            self.assertIn(f"revoke all on table public.question_source_documents, public.question_import_items from anon, authenticated", SQL)
        self.assertIn('@admin_bp.post("/api/admin/question-imports")', ADMIN)
        self.assertIn('document.get("usage_rights") != "licensed_for_student_use"', ADMIN)
        self.assertIn('id="question-import-form"', HTML)

    def test_questions_and_knowledge_are_cluster_addressable(self):
        self.assertIn("idx_question_import_cluster", KNOWLEDGE_SQL)
        self.assertIn("create table if not exists public.kpi_knowledge_items", KNOWLEDGE_SQL)
        self.assertIn('question["kpi_cluster"]', ADMIN)
        self.assertIn('"cluster_breakdown"', ADMIN)
        self.assertIn('id="question-cluster-breakdown"', HTML)

    def test_style_profile_contains_patterns_not_source_text(self):
        profile = build_style_profile([{"question_text": "A manager helps a customer select a service.", "correct_index": 1}])
        self.assertEqual(profile["corpus_size"], 1)
        self.assertEqual(profile["scenario_percentage"], 100)
        self.assertNotIn("questions", profile)
        self.assertIn('@admin_bp.post("/api/admin/questions/generate-original")', ADMIN)

    def test_sources_are_deduplicated_without_losing_page_links(self):
        first = parse_reference_citation("McAdams, T. (2007). Law, business, and society (8th ed.) [pp. 199-200]. Boston: McGraw-Hill.")
        second = parse_reference_citation("McAdams, T. (2007). Law, business, and society (8th ed.) [pp. 214-216]. Boston: McGraw-Hill.")
        self.assertEqual(first["canonical_key"], second["canonical_key"])
        self.assertNotEqual(first["pages"], second["pages"])
        self.assertIn("Law, business, and society", first["title"])

    def test_sources_library_is_server_only_and_never_scrapes(self):
        for table in ("reference_sources", "question_source_links"):
            self.assertIn(f"alter table public.{table} enable row level security", SOURCES_SQL)
        self.assertIn("revoke all on table public.reference_sources, public.question_source_links from anon, authenticated", SOURCES_SQL)
        self.assertIn('@admin_bp.get("/api/admin/sources")', ADMIN)
        self.assertIn('id="sources-list"', HTML)
        self.assertNotIn("requests.get", ADMIN)


if __name__ == "__main__":
    unittest.main()
