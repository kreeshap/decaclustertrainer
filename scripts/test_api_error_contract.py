import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = (ROOT / "app" / "main.py").read_text(encoding="utf-8")


class ApiErrorContractTests(unittest.TestCase):
    def test_unexpected_api_errors_are_json(self) -> None:
        self.assertIn('@app.errorhandler(Exception)', MAIN_SOURCE)
        self.assertIn('request.path.startswith("/api/")', MAIN_SOURCE)
        self.assertIn('jsonify({"error": "Internal server error"})', MAIN_SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
