import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "supabase" / "migrations" / "20260816194340_content_operations.sql").read_text(encoding="utf-8")
PIPELINE = (ROOT / "app" / "content_ops.py").read_text(encoding="utf-8")
ADMIN = (ROOT / "app" / "routes" / "admin.py").read_text(encoding="utf-8")
LEARN = (ROOT / "app" / "routes" / "learn.py").read_text(encoding="utf-8")
HTML = (ROOT / "templates" / "adminpanel.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "js" / "adminpanel.js").read_text(encoding="utf-8")


class ContentOperationsContractTests(unittest.TestCase):
    def test_migration_has_persistent_pipeline_tables_and_server_only_access(self):
        tables = (
            "kpi_catalog",
            "kpi_classification_batches",
            "kpi_classifications",
            "kpi_classification_jobs",
        )
        for table in tables:
            self.assertIn(f"create table public.{table}", MIGRATION)
            self.assertIn(f"alter table public.{table} enable row level security", MIGRATION)
            self.assertIn(f"revoke all on table public.{table} from anon, authenticated", MIGRATION)
            self.assertIn(f"grant select, insert, update, delete on table public.{table} to service_role", MIGRATION)

    def test_classification_records_are_versioned_and_reviewable(self):
        for field in (
            "classifier_version", "classifier_model", "classification_schema_version",
            "classification_version", "review_status", "manual_override", "reviewed_by",
        ):
            self.assertRegex(MIGRATION, rf"\b{field}\b")
        self.assertIn("auto_approved", MIGRATION)
        self.assertIn("needs_review", MIGRATION)

    def test_pipeline_has_all_four_decision_layers(self):
        self.assertIn("def classify_with_ai", PIPELINE)
        self.assertIn("def _validate_classification", PIPELINE)
        self.assertIn("def deterministic_disagreements", PIPELINE)
        self.assertIn("def skeptical_review", PIPELINE)
        self.assertIn("ThreadPoolExecutor(max_workers=3)", PIPELINE)

    def test_admin_batch_is_bounded_and_admin_protected(self):
        self.assertIn('@admin_bp.post("/api/admin/content-operations/process")', ADMIN)
        self.assertIn("min(int(body.get(\"limit\") or 20), 20)", ADMIN)
        self.assertIn("A classification batch is already running", ADMIN)
        route = re.search(r"def admin_process_classifications\(\):(.+?)\n\n@admin_bp", ADMIN, re.S).group(1)
        self.assertIn("require_admin()", route)

    def test_admin_review_is_fast_and_keyboard_driven(self):
        self.assertIn('id="review-panel"', HTML)
        self.assertIn('id="process-kpis"', HTML)
        self.assertIn('event.key.toLowerCase() === "a"', JS)
        self.assertIn('["1", "2"].includes(event.key)', JS)
        self.assertIn('event.key.toLowerCase() === "s"', JS)

    def test_approved_classification_drives_lessons_with_fallback(self):
        self.assertIn("get_approved_instructional_plan(catalog_id(kpi)) or classify_kpi(text)", LEARN)


if __name__ == "__main__":
    unittest.main()
