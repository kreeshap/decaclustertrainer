import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "supabase" / "migrations" / "20260816210012_content_operations.sql").read_text(encoding="utf-8")
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

    def test_catalog_sync_upserts_parent_events_before_kpis(self):
        event_sync = PIPELINE.index('"/deca_events"')
        catalog_sync = PIPELINE.index('"/kpi_catalog"')
        self.assertLess(event_sync, catalog_sync)
        self.assertIn("kpis, events = _load_all_kpis()", PIPELINE)
        self.assertIn('"is_beta": True', PIPELINE)

    def test_classification_polling_does_not_refresh_unrelated_admin_panels(self):
        self.assertIn("async function loadClassificationDashboard()", JS)
        start_batch = re.search(r"async function startBatch\(\) \{(.+?)\n\}", JS, re.S).group(1)
        self.assertIn("await loadClassificationDashboard()", start_batch)
        self.assertNotIn("await loadDashboard()", start_batch)

    def test_common_model_action_synonyms_are_normalized(self):
        self.assertIn('"comply": "demonstrate"', PIPELINE)
        self.assertIn("DECA_ACTION_ALIASES.get(value, value)", PIPELINE)

    def test_adversarial_review_repairs_confident_results_before_escalating(self):
        self.assertIn("Act as an adversarial instructional reviewer", PIPELINE)
        self.assertIn('"verdict":"pass|correct|uncertain"', PIPELINE)
        self.assertIn("def resolve_classification", PIPELINE)
        self.assertIn("classifier_floor >= 0.80", PIPELINE)
        self.assertIn("reviewer.get(\"confidence\", 0) >= 0.85", PIPELINE)
        self.assertIn("final_result, validation, needs_review", PIPELINE)
        self.assertIn("learner_action and deca_action are incompatible", PIPELINE)

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
        self.assertIn("function escHtml(value)", JS)

    def test_approved_classification_drives_lessons_with_fallback(self):
        audit_ops = (ROOT / "app" / "audit_ops.py").read_text(encoding="utf-8")
        self.assertIn('approved.get(catalog_id(kpi)) or classify_kpi(kpi["text"])', audit_ops)
        self.assertIn('"/generated_kpi_lessons"', LEARN)

    def test_admin_tools_are_grouped_into_internal_tabs(self):
        for tab in ("overview", "study", "questions", "sources"):
            self.assertIn(f'data-admin-tab="{tab}"', HTML)
            self.assertIn(f'data-admin-group="{tab}"', HTML)
        self.assertIn("function showAdminTab(tabName)", JS)
        self.assertIn("ct_admin_active_tab", JS)


if __name__ == "__main__":
    unittest.main()
