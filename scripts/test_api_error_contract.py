import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
LEARN_SOURCE = (ROOT / "app" / "routes" / "learn.py").read_text(encoding="utf-8")
GENERATION_SOURCE = (ROOT / "app" / "lesson_generation.py").read_text(encoding="utf-8")


class ApiErrorContractTests(unittest.TestCase):
    def test_unexpected_api_errors_are_json(self) -> None:
        self.assertIn('@app.errorhandler(Exception)', MAIN_SOURCE)
        self.assertIn('request.path.startswith("/api/")', MAIN_SOURCE)
        self.assertIn('jsonify({"error": "Internal server error"})', MAIN_SOURCE)

    def test_learn_serves_only_pregenerated_lessons(self) -> None:
        self.assertIn('"/generated_kpi_lessons"', LEARN_SOURCE)
        self.assertIn('"status": "eq.ready"', LEARN_SOURCE)
        self.assertIn('"This KPI is not ready for Learn Mode yet."', LEARN_SOURCE)
        self.assertNotIn("generate_valid_lesson(prompt, lesson_design)", LEARN_SOURCE)

    def test_admin_generation_remains_bounded(self) -> None:
        self.assertEqual(GENERATION_SOURCE.count("max_tokens=4000"), 1)
        self.assertIn("max_tokens=6000", GENERATION_SOURCE)
        self.assertIn("retry_invalid_json=True", GENERATION_SOURCE)

    def test_generation_providers_run_concurrently(self) -> None:
        self.assertIn("ThreadPoolExecutor", GENERATION_SOURCE)
        self.assertIn("as_completed(futures)", GENERATION_SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
