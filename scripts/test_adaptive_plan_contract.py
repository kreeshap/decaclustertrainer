import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AdaptivePlanContractTests(unittest.TestCase):
    def test_private_adaptive_tables_have_owner_rls(self):
        sql = (ROOT / "supabase/migrations/20260816223000_adaptive_state_today_plans.sql").read_text(encoding="utf-8")
        for table in ("user_adaptive_state", "user_today_plans"):
            self.assertIn(f"create table if not exists public.{table}", sql)
            self.assertIn(f"alter table public.{table} enable row level security", sql)
        self.assertIn("using ((select auth.uid()) = user_id)", sql)
        self.assertIn("with check ((select auth.uid()) = user_id)", sql)
        self.assertIn("revoke all", sql)

    def test_planner_is_deterministic_and_evidence_gated(self):
        source = (ROOT / "app/routes/adaptive.py").read_text(encoding="utf-8")
        planner = (ROOT / "app/adaptive_planner.py").read_text(encoding="utf-8")
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("gemini", source.lower())
        self.assertIn('"qualified_weakest_topic"', source)
        self.assertIn('x for x in topic_analysis if x.get("qualified")', source)
        self.assertIn('"topic_question_attempts": 10', source)
        self.assertIn('@adaptive_bp.route("/api/adaptive/today"', source)
        self.assertIn('"reason_codes"', planner)

    def test_plan_uses_existing_aggregated_learning_evidence(self):
        source = (ROOT / "app/routes/adaptive.py").read_text(encoding="utf-8")
        for signal in ("user_lesson_completions", "user_kpi_mastery", "user_study_sessions", "due_reviews", "study_goal_minutes"):
            self.assertIn(signal, source)
        for invasive_signal in ("mouse", "keystroke", "fingerprint", "exact_location"):
            self.assertNotIn(invasive_signal, source.lower())

    def test_cached_state_is_factual_and_time_can_repack_the_plan(self):
        route = (ROOT / "app/routes/adaptive.py").read_text(encoding="utf-8")
        dashboard = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")
        html = (ROOT / "templates/dashboard.html").read_text(encoding="utf-8")
        for fact in ("median_session_active_minutes", "recent_session_completion_rate", "median_question_seconds", "due_review_count"):
            self.assertIn(fact, route)
        self.assertNotIn('"study_pattern"', route)
        self.assertIn("time_available_today", route)
        self.assertIn("time_available_today", dashboard)
        self.assertIn("Short on time?", html)


if __name__ == "__main__":
    unittest.main()
