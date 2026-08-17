from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PracticePlatformContract(unittest.TestCase):
    def test_persistent_schema_is_user_scoped(self):
        sql = (ROOT / "supabase/migrations/20260816215000_practice_platform.sql").read_text(encoding="utf-8")
        for table in ("practice_sets", "practice_set_questions", "question_flags"):
            self.assertIn(table, sql)
        self.assertIn("enable row level security", sql)
        self.assertIn("auth.uid())=user_id", sql)
        self.assertIn("unique(practice_set_id,question_id)", sql)

    def test_platform_routes_cover_builder_resume_results_and_flags(self):
        source = (ROOT / "app/routes/practice.py").read_text(encoding="utf-8")
        for route in (
            '/api/practice/platform', '/api/practice/sets/preview',
            '/api/practice/sets', '/progress', '/complete', '/api/practice/flags/',
        ):
            self.assertIn(route, source)
        self.assertIn('Only {len(candidates)} unique questions match', source)
        self.assertIn('time_limit_seconds":5400', source)

    def test_student_ui_has_three_paths_and_distinct_modes(self):
        html = (ROOT / "templates/practicequestions.html").read_text(encoding="utf-8")
        js = (ROOT / "static/js/practiceplatform.js").read_text(encoding="utf-8")
        for text in ("Smart Practice Questions", "Build a Practice Question Set", "Mock Exam", "Tutor", "Exam"):
            self.assertIn(text, html)
        for behavior in ("startTimer", "Question review", "runner-previous", "practice/sets/preview"):
            self.assertIn(behavior, html + js)
        self.assertIn('state.set.mode==="tutor"', js)

    def test_home_explains_recommendation_readiness_and_limited_data(self):
        html = (ROOT / "templates/practicequestions.html").read_text(encoding="utf-8")
        js = (ROOT / "static/js/practiceplatform.js").read_text(encoding="utf-8")
        css = (ROOT / "static/styles/practicequestions.css").read_text(encoding="utf-8")
        for text in ("platform-smart-signals", "platform-mock-progress", "platform-insights"):
            self.assertIn(text, html)
        for text in ("KPIs studied", "Limited data", "answered so far"):
            self.assertIn(text, js)
        self.assertIn("max-width: 1500px", css)
        self.assertIn(".platform-shell{width:100%;max-width:none;margin:0}", css)


if __name__ == "__main__":
    unittest.main()
