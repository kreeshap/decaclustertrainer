import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BehavioralPhaseOneContractTests(unittest.TestCase):
    def test_dashboard_exposes_a_finite_resumable_session(self):
        html = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")

        for phrase in ("Today's session", "Why this?", "session-modal", "Finish session"):
            self.assertIn(phrase, html)
        for behavior in ("ct_today_session_v1", "makePlan", "updatePlan", "nextTask", "Good stopping point"):
            self.assertIn(behavior, js)

    def test_plan_progress_uses_measured_work_not_clicks(self):
        js = (ROOT / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn("seen-t.baseline", js)
        self.assertIn("answers-t.baseline", js)
        self.assertIn("t.baseline-due", js)
        self.assertNotIn("hours studied", js.lower())

    def test_consistency_uses_a_forgiving_seven_day_window(self):
        html = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn("of the last 7 days", html)
        self.assertIn("activeDays", js)


if __name__ == "__main__":
    unittest.main()
