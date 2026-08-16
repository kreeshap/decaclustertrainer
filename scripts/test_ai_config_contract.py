import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AI_SOURCE = (ROOT / "app" / "ai.py").read_text(encoding="utf-8")
CONFIG_SOURCE = (ROOT / "app" / "config.py").read_text(encoding="utf-8")


class AiConfigurationContractTests(unittest.TestCase):
    def test_gemini_uses_configurable_supported_model(self) -> None:
        self.assertNotIn("gemini-2.0-flash", AI_SOURCE)
        self.assertIn('GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")', CONFIG_SOURCE)
        self.assertIn("model: str = GEMINI_MODEL", AI_SOURCE)

    def test_google_api_key_alias_is_supported(self) -> None:
        self.assertIn('first_env_value("GEMINI_API_KEY", "GOOGLE_API_KEY")', CONFIG_SOURCE)

    def test_provider_timeouts_are_applied_to_sdk_clients(self) -> None:
        self.assertIn("timeout=GROQ_API_TIMEOUT", AI_SOURCE)
        self.assertIn("max_retries=0", AI_SOURCE)
        self.assertIn("timeout=int(GEMINI_API_TIMEOUT * 1000)", AI_SOURCE)

    def test_default_provider_timeouts_fit_inside_web_request_budget(self) -> None:
        self.assertIn('GROQ_API_TIMEOUT = float(os.environ.get("GROQ_API_TIMEOUT", "60"))', CONFIG_SOURCE)
        self.assertIn('GEMINI_API_TIMEOUT = float(os.environ.get("GEMINI_API_TIMEOUT", "60"))', CONFIG_SOURCE)

    def test_gemini_can_retry_malformed_json_for_structured_lessons(self) -> None:
        self.assertIn("retry_invalid_json: bool = False", AI_SOURCE)
        self.assertIn("Gemini returned malformed JSON after", AI_SOURCE)

    def test_all_configured_providers_have_adapters(self) -> None:
        for provider in ("mistral", "cloudflare"):
            self.assertIn(f"def call_{provider}", AI_SOURCE)
        for key in ("MISTRAL_API_KEY", "CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID"):
            self.assertIn(key, CONFIG_SOURCE)

    def test_provider_failover_is_coordinated(self) -> None:
        coordinator = (ROOT / "app" / "ai_coordinator.py").read_text(encoding="utf-8")
        self.assertIn('"student": 0', coordinator)
        self.assertIn('"audit": 3', coordinator)
        self.assertIn('"classification": 4', coordinator)
        self.assertIn("AI_MAX_CONCURRENT_REQUESTS", coordinator)
        self.assertIn("temporarily cooling down", coordinator)


if __name__ == "__main__":
    unittest.main(verbosity=2)
