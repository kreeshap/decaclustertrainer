"""Regression contracts for password recovery and dark-only settings."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUTH_PY = (ROOT / "app" / "routes" / "auth.py").read_text(encoding="utf-8")
AUTH_JS = (ROOT / "static" / "js" / "auth.js").read_text(encoding="utf-8")
COMMON_JS = (ROOT / "static" / "js" / "common.js").read_text(encoding="utf-8")
CLUSTERS_JS = (ROOT / "static" / "js" / "clusters.js").read_text(encoding="utf-8")
SETTINGS_JS = (ROOT / "static" / "js" / "settings.js").read_text(encoding="utf-8")
SETTINGS_HTML = (ROOT / "templates" / "settings.html").read_text(encoding="utf-8")
SETTINGS_CSS = (ROOT / "static" / "styles" / "settings.css").read_text(
    encoding="utf-8"
)
SIGNON_HTML = (ROOT / "templates" / "signon.html").read_text(encoding="utf-8")
AUTH_CSS = (ROOT / "static" / "styles" / "auth.css").read_text(encoding="utf-8")
OPENING_HTML = (ROOT / "templates" / "opening.html").read_text(encoding="utf-8")
OPENING_JS = (ROOT / "static" / "js" / "opening.js").read_text(encoding="utf-8")
OPENING_CSS = (ROOT / "static" / "styles" / "opening.css").read_text(
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


class EmailPasswordOnlySignInContracts(unittest.TestCase):
    def test_google_and_apple_sign_in_controls_are_removed(self):
        combined = SIGNON_HTML + AUTH_JS + AUTH_CSS
        for marker in (
            "Sign in with Google",
            "Sign in with Apple",
            "btn-google",
            "btn-apple",
            "handleSocialLogin",
            "social-login",
            "social-google",
            "social-apple",
        ):
            self.assertNotIn(marker, combined)


class OnboardingContracts(unittest.TestCase):
    def test_onboarding_quick_tips_are_removed(self):
        combined = OPENING_HTML + OPENING_JS + OPENING_CSS
        for marker in (
            "Quick tip",
            "opening-tip",
            "showOpeningTip",
            "hideOpeningTip",
            "hasSeenOpeningTour",
            "markOpeningTourSeen",
            "ct_openingTourSeen",
        ):
            self.assertNotIn(marker, combined)

    def test_onboarding_displays_all_clusters_and_events(self):
        self.assertNotIn("supportedBetaEvents(cluster).forEach", OPENING_JS)
        self.assertNotIn("supported events", OPENING_JS)
        self.assertIn("CLUSTERS.forEach((c, i) =>", OPENING_JS)
        self.assertIn("const eventCount = c.events.length", OPENING_JS)
        self.assertIn("cluster.events.forEach((ev) =>", OPENING_JS)

    def test_non_beta_onboarding_event_does_not_invent_server_event_id(self):
        self.assertIn('body: JSON.stringify({\n              default_event:', COMMON_JS)
        self.assertIn('profile_patch["default_event_id"] = None', AUTH_PY)
        self.assertIn('elif "default_event" in payload:', AUTH_PY)

    def test_onboarding_welcome_copy_is_not_tier_or_event_based(self):
        self.assertIn('welcomeSubEl.textContent = "Welcome back"', OPENING_JS)
        self.assertIn(
            'welcomeSubEl.textContent = "Welcome to Cluster Trainer,"',
            OPENING_JS,
        )
        self.assertIn("transitionPhase(fromPhase, phWelcome, 160)", OPENING_JS)
        for marker in (
            "Studying for",
            "Ready to study",
            "Good to see you again",
            "forceWelcomeBack",
        ):
            self.assertNotIn(marker, OPENING_JS)


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

    def test_competition_level_auto_saves_without_status_row(self):
        self.assertNotIn("Currently set to:", SETTINGS_HTML)
        self.assertNotIn("btn-save-comp", SETTINGS_HTML + SETTINGS_JS)
        self.assertIn("void saveComp(el, previous)", SETTINGS_JS)
        self.assertIn('competition_tier: competitionTier', SETTINGS_JS)
        self.assertIn('sel.dataset.level === "states" ? "scdc"', SETTINGS_JS)

    def test_event_dropdown_uses_canonical_ids_and_auto_saves(self):
        self.assertNotIn("event-current-label", SETTINGS_HTML + SETTINGS_JS)
        self.assertNotIn("btn-save-event", SETTINGS_HTML + SETTINGS_JS)
        self.assertIn('opt.value = getEventIdByName(evName)', SETTINGS_JS)
        self.assertIn('void saveEventSelection()', SETTINGS_JS)
        self.assertIn('const resolvedEventId = UserPrefs.getEventId()', SETTINGS_JS)
        self.assertIn('const resolvedEventName = UserPrefs.getEventName()', SETTINGS_JS)
        self.assertNotIn('const resolvedEvent   = UserPrefs.getEvent()', SETTINGS_JS)
        self.assertIn('function getEventNameById(eventId)', CLUSTERS_JS)
        self.assertIn('eventName = getEventNameById(eventId) || eventName', COMMON_JS)


if __name__ == "__main__":
    unittest.main()
