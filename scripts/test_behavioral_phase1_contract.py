import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BehavioralPhaseOneContractTests(unittest.TestCase):
    def test_dashboard_exposes_a_finite_resumable_session(self):
        html = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")

        for phrase in ("Today's session", "session-modal", 'id="session-finish"'):
            self.assertIn(phrase, html)
        self.assertNotIn("Why this?", html)
        for behavior in ("/api/adaptive/today", "nextTask", 'session-dialog-title'):
            self.assertIn(behavior, js)
        self.assertNotIn("localStorage", js)

    def test_plan_progress_uses_measured_work_not_clicks(self):
        js = (ROOT / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")
        planner = (ROOT / "app" / "adaptive_planner.py").read_text(encoding="utf-8")

        self.assertIn('state["coverage"]["studied"] - int(item.get("baseline", 0))', planner)
        self.assertIn('state["practice_attempt_count"] - int(item.get("baseline", 0))', planner)
        self.assertIn('int(item.get("baseline", 0)) - state["due_review_count"]', planner)
        self.assertNotIn("writePlan", js)
        self.assertNotIn("hours studied", js.lower())

    def test_consistency_uses_a_forgiving_seven_day_window(self):
        html = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn("of 7 days", html)
        self.assertIn("activeDays", js)


if __name__ == "__main__":
    unittest.main()
