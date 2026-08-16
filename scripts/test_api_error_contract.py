import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
LEARN_SOURCE = (ROOT / "app" / "routes" / "learn.py").read_text(encoding="utf-8")


class ApiErrorContractTests(unittest.TestCase):
    def test_unexpected_api_errors_are_json(self) -> None:
        self.assertIn('@app.errorhandler(Exception)', MAIN_SOURCE)
        self.assertIn('request.path.startswith("/api/")', MAIN_SOURCE)
        self.assertIn('jsonify({"error": "Internal server error"})', MAIN_SOURCE)

    def test_generation_deadlines_return_gateway_timeout_json(self) -> None:
        self.assertIn('"Lesson generation timed out. Please try again."', LEARN_SOURCE)
        self.assertIn("}), 504", LEARN_SOURCE)

    def test_generation_output_is_bounded_for_web_requests(self) -> None:
        self.assertEqual(LEARN_SOURCE.count("max_tokens=4000"), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
