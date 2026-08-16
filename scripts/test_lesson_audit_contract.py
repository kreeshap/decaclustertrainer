import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase" / "migrations" / "20260816210032_lesson_content_audits.sql").read_text(encoding="utf-8")
OPS = (ROOT / "app" / "audit_ops.py").read_text(encoding="utf-8")
ADMIN = (ROOT / "app" / "routes" / "admin.py").read_text(encoding="utf-8")
HTML = (ROOT / "templates" / "adminpanel.html").read_text(encoding="utf-8")
ADMIN_JS = (ROOT / "static" / "js" / "adminpanel.js").read_text(encoding="utf-8")
LEARN_JS = (ROOT / "static" / "js" / "learn.js").read_text(encoding="utf-8")
HELPERS = (ROOT / "app" / "learn_helpers.py").read_text(encoding="utf-8")
READY_SQL = (ROOT / "supabase" / "migrations" / "20260816210853_generated_kpi_lessons.sql").read_text(encoding="utf-8")


class LessonAuditContractTests(unittest.TestCase):
    def test_audit_and_failure_tables_are_server_only(self):
        for table in ("lesson_audit_batches", "lesson_content_audits", "lesson_generation_failures"):
            self.assertIn(f"create table public.{table}", SQL)
            self.assertIn(f"alter table public.{table} enable row level security", SQL)
            self.assertIn(f"revoke all on table public.{table} from anon, authenticated", SQL)
            self.assertIn(f"grant select, insert, update, delete on table public.{table} to service_role", SQL)

    def test_sample_is_bounded_and_stratified(self):
        self.assertIn('targets = {"quick": 5, "standard": 10, "deep": 5}', OPS)
        self.assertIn("return selected[:limit]", OPS)
        self.assertIn("ThreadPoolExecutor(max_workers=2)", OPS)
        self.assertIn('if catalog_id(kpi) in ready_ids:', OPS)

    def test_admin_scores_the_six_usability_questions(self):
        fields = (
            "mission_clarity", "choice_matters", "vocabulary_quality",
            "learning_value", "difficulty_progression", "pacing_quality",
        )
        for field in fields:
            self.assertIn(field, SQL)
            self.assertIn(field, ADMIN_JS)
        self.assertIn('id="lesson-audit-preview"', HTML)
        self.assertIn('@admin_bp.patch("/api/admin/content-audits/<audit_id>")', ADMIN)

    def test_repeated_student_failures_become_an_ops_signal(self):
        self.assertIn("lesson_generation_failures", ADMIN)
        self.assertIn("failureCount >= 2", LEARN_JS)
        self.assertIn('classList.toggle("prominent"', LEARN_JS)

    def test_generated_lessons_are_the_student_readiness_gate(self):
        self.assertIn("create table public.generated_kpi_lessons", READY_SQL)
        self.assertIn("alter table public.generated_kpi_lessons enable row level security", READY_SQL)
        self.assertIn("def get_ready_kpi_ids", HELPERS)
        self.assertIn('"status": "eq.ready"', HELPERS)

    def test_admin_exposes_generated_content_percentage(self):
        self.assertIn('id="generated-percent"', HTML)
        self.assertIn('id="generated-progress-fill"', HTML)
        self.assertIn("generated_content", ADMIN)


if __name__ == "__main__":
    unittest.main()
