"""Regression contracts for password recovery and dark-only settings."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUTH_PY = (ROOT / "app" / "routes" / "auth.py").read_text(encoding="utf-8")
AUTH_JS = (ROOT / "static" / "js" / "auth.js").read_text(encoding="utf-8")
COMMON_JS = (ROOT / "static" / "js" / "common.js").read_text(encoding="utf-8")
SETTINGS_JS = (ROOT / "static" / "js" / "settings.js").read_text(encoding="utf-8")
SETTINGS_HTML = (ROOT / "templates" / "settings.html").read_text(encoding="utf-8")
SETTINGS_CSS = (ROOT / "static" / "styles" / "settings.css").read_text(
    encoding="utf-8"
)


class PasswordRecoveryContracts(unittest.TestCase):
    def test_recovery_uses_canonical_reset_route(self):
        self.assertIn('f"{app_base_url()}/reset-password"', AUTH_PY)

    def test_token_hash_recovery_is_verified_server_side(self):
        self.assertIn('@auth_bp.post("/auth/password-reset/verify")', AUTH_PY)
        self.assertIn('payload={"token_hash": token_hash, "type": "recovery"}', AUTH_PY)
        self.assertIn("url.searchParams.get('token_hash')", AUTH_JS)
        self.assertIn("fetch('/auth/password-reset/verify'", AUTH_JS)

    def test_invalid_recovery_link_stays_on_reset_form(self):
        self.assertIn("url.pathname === '/reset-password'", AUTH_JS)
        self.assertIn("showPage('reset')", AUTH_JS)


class DarkOnlySettingsContracts(unittest.TestCase):
    def test_global_theme_is_forced_to_dark(self):
        self.assertIn("root.classList.add('theme-dark')", COMMON_JS)
        self.assertIn("root.style.colorScheme = 'dark'", COMMON_JS)
        self.assertNotIn("prefers-color-scheme", COMMON_JS)

    def test_appearance_controls_are_removed(self):
        combined = SETTINGS_HTML + SETTINGS_JS + SETTINGS_CSS
        for marker in (
            'id="appearance"',
            'href="#appearance"',
            "selectTheme",
            "theme-options",
            "theme-light-preview",
        ):
            self.assertNotIn(marker, combined)

    def test_settings_descriptions_are_removed(self):
        for marker in (
            "comp-desc",
            "Choose the DECA cluster",
            "Set daily targets",
            "Affects question pools",
            "Saved event is loaded",
            "Track your daily progress",
        ):
            self.assertNotIn(marker, SETTINGS_HTML)


if __name__ == "__main__":
    unittest.main()
