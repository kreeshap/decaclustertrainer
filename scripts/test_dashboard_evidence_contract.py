from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DashboardEvidenceContractTests(unittest.TestCase):
    def test_first_attempts_are_order_independent(self):
        from app.student_evidence import first_attempts

        result = first_attempts([
            {"question_id": "q1", "correct": True, "answered_at": "2026-01-02T00:00:00Z"},
            {"question_id": "q1", "correct": False, "answered_at": "2026-01-01T00:00:00Z"},
        ])
        self.assertEqual(result["correct"], 0)
        self.assertEqual(result["retry_count"], 1)

    def test_overview_separates_coverage_mastery_and_accuracy(self):
        html = (ROOT / "templates/dashboard.html").read_text(encoding="utf-8")
        js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
        self.assertIn("First-attempt accuracy", html)
        self.assertIn("Knowledge coverage", html)
        self.assertIn("Mastery of studied material", html)
        self.assertIn('"Early data"', js)
        self.assertNotIn("Measured areas average", js)

    def test_focus_labels_require_coverage_and_attempt_gates(self):
        practice = (ROOT / "app/routes/practice.py").read_text(encoding="utf-8")
        dashboard = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
        self.assertIn("topic_is_qualified", practice)
        self.assertIn("first_attempts", practice)
        self.assertIn("Limited data", dashboard)
        self.assertIn('x.status||"Limited data"', dashboard)

    def test_analytics_returns_curriculum_denominator(self):
        learn = (ROOT / "app/routes/learn.py").read_text(encoding="utf-8")
        self.assertIn('"total_kpis_available"', learn)
        self.assertIn('"kpis_studied"', learn)
        self.assertIn('"coverage_pct"', learn)

    def test_learn_tracks_first_pass_and_restores_saved_resume(self):
        js = (ROOT / "static/js/learn.js").read_text(encoding="utf-8")
        self.assertIn("kpiFirstPassAnswered++", js)
        self.assertIn("if (!q._isRetry)", js)
        self.assertIn("ct_learn_resume_${currentEventId}", js)

    def test_practice_resume_is_event_scoped(self):
        practice = (ROOT / "app/routes/practice.py").read_text(encoding="utf-8")
        js = (ROOT / "static/js/practiceplatform.js").read_text(encoding="utf-8")
        self.assertIn('request.args.get("event_id")', practice)
        self.assertIn("?event_id=${encodeURIComponent(state.eventId)}", js)


if __name__ == "__main__":
    unittest.main()
