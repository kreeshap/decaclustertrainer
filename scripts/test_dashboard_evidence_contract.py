from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DashboardEvidenceContractTests(unittest.TestCase):
    def test_overview_separates_coverage_mastery_and_accuracy(self):
        html = (ROOT / "templates/dashboard.html").read_text(encoding="utf-8")
        js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
        for label in (
            "Knowledge coverage",
            "Mastery of studied material",
            "Practice accuracy",
            "Evidence status",
        ):
            self.assertIn(label, html)
        self.assertIn('"Early data"', js)
        self.assertNotIn("Measured areas average", js)

    def test_focus_labels_require_coverage_and_attempt_gates(self):
        practice = (ROOT / "app/routes/practice.py").read_text(encoding="utf-8")
        dashboard = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
        self.assertIn("coverage >= 50", practice)
        self.assertIn('data["attempts"] >= 10', practice)
        self.assertIn("Limited data", dashboard)
        self.assertIn('x.status||"Limited data"', dashboard)

    def test_analytics_returns_curriculum_denominator(self):
        learn = (ROOT / "app/routes/learn.py").read_text(encoding="utf-8")
        self.assertIn('"total_kpis_available"', learn)
        self.assertIn('"kpis_studied"', learn)
        self.assertIn('"coverage_pct"', learn)


if __name__ == "__main__":
    unittest.main()
