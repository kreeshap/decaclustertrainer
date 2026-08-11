"""Regression contracts for mutually exclusive onboarding phase navigation."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
OPENING_JS = (ROOT / "static" / "js" / "opening.js").read_text(encoding="utf-8")


class OpeningNavigationContracts(unittest.TestCase):
    def test_phase_activation_deactivates_other_active_phases(self):
        self.assertIn('document.querySelectorAll(".phase.active")', OPENING_JS)
        self.assertIn('phase.classList.remove("active")', OPENING_JS)

    def test_back_buttons_cancel_stale_phase_transitions(self):
        self.assertIn("transitionPhase(phEvents, phGrid, 800)", OPENING_JS)
        self.assertIn("transitionPhase(phLevel, phGrid, 800)", OPENING_JS)
        self.assertIn("window.clearTimeout(phaseTransitionTimer)", OPENING_JS)

    def test_async_selections_cannot_navigate_after_back(self):
        self.assertGreaterEqual(
            OPENING_JS.count("selectionVersion === phaseNavigationVersion"),
            2,
        )
        self.assertIn('phEvents.classList.contains("active")', OPENING_JS)
        self.assertIn('phLevel.classList.contains("active")', OPENING_JS)


if __name__ == "__main__":
    unittest.main()
