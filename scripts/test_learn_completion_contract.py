from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LearnCompletionContractTests(unittest.TestCase):
    def test_current_lesson_completion_is_separate_from_mastery_history(self):
        migration = (ROOT / "supabase/migrations/20260816220000_user_lesson_completions.sql").read_text(encoding="utf-8")
        routes = (ROOT / "app/routes/learn.py").read_text(encoding="utf-8")
        script = (ROOT / "static/js/learn.js").read_text(encoding="utf-8")
        self.assertIn("create table if not exists public.user_lesson_completions", migration)
        self.assertIn("primary key (user_id, event_id, kpi_code, lesson_version)", migration)
        self.assertIn('/api/learn/kpis/<kpi_code>/complete', routes)
        self.assertIn("completed_codes", routes)
        self.assertIn("current_lesson_completed", routes)
        self.assertIn('/api/learn/kpis/${encodeURIComponent(completedKpi.code)}/complete', script)

    def test_landing_separates_coverage_retention_curriculum_and_review(self):
        html = (ROOT / "templates/learn.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/learn.js").read_text(encoding="utf-8")
        for label in ("Learning progress", "Continue learning", "Curriculum", "Review", "Mastery of learned material"):
            self.assertIn(label, html)
        self.assertIn("Search KPIs, topics, or concepts", html)
        self.assertNotIn("30-Day Activity", html)
        self.assertNotIn("Day Streak", html)
        self.assertIn("Previous performance", script)
        self.assertIn("not completed in current Learn Mode", script)


if __name__ == "__main__":
    unittest.main()
