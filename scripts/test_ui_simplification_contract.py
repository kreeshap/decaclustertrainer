import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UiSimplificationContractTests(unittest.TestCase):
    def test_saved_concepts_and_notes_are_removed(self) -> None:
        source = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in ("templates/learn.html", "static/js/learn.js")
        ).lower()
        for token in (
            "saved-concepts",
            "saved-notes",
            "ct_saved_concepts",
            "ct_saved_notes",
            "save-concept",
            "concept-note",
        ):
            self.assertNotIn(token, source)

    def test_advanced_controls_are_not_visible(self) -> None:
        learn = (ROOT / "templates/learn.html").read_text(encoding="utf-8")
        practice = (ROOT / "templates/practicequestions.html").read_text(encoding="utf-8")
        self.assertNotIn("admin-tools-panel", learn)
        self.assertRegex(learn, r'<details class="special-modes-dropdown"[^>]*\bhidden\b')
        self.assertRegex(practice, r'<details class="panel practice-panel practice-accordion"[^>]*\bhidden\b')

    def test_visual_map_is_removed(self) -> None:
        source = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in ("templates/learn.html", "static/js/learn.js", "static/styles/learn.css")
        ).lower()
        for token in ("visual map", "knowledge-graph", "renderknowledgemap", "graph-row"):
            self.assertNotIn(token, source)

    def test_learn_dashboard_is_compact_and_left_aligned(self) -> None:
        template = (ROOT / "templates/learn.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/learn.js").read_text(encoding="utf-8")
        styles = (ROOT / "static/styles/learn.css").read_text(encoding="utf-8")
        self.assertIn("Next 3 KPIs to learn", template)
        for removed_text in (
            "Current event",
            "Recommended for you",
            "Continue where you left off",
            "hero-topic-count",
            "hero-mode-chip",
            "hero-progress-chip",
        ):
            self.assertNotIn(removed_text, template)
        for removed_status in ("Start here", '"Ready"', '"2 min"'):
            self.assertNotIn(removed_status, script)
        self.assertIn("source.length >= 3", script)
        self.assertIn('<span class="study-row-score">Learn</span>', script)
        self.assertIn('class="progress-title">Your progress</div>', template)
        self.assertIn("max-width: 1240px", styles)
        self.assertIn("--radius-sm: 6px", styles)
        self.assertIn("--radius-md: 10px", styles)
        self.assertIn("--radius-lg: 14px", styles)
        self.assertIn("min-height: 72px", styles)
        self.assertIn(".mastery-summary-row", styles)
        self.assertIn("display: none !important", styles)

    def test_quiz_dashboard_is_compact_without_duplicate_cards(self) -> None:
        template = (ROOT / "templates/practicequestions.html").read_text(encoding="utf-8")
        styles = (ROOT / "static/styles/practicequestions.css").read_text(encoding="utf-8")
        self.assertIn('<h1 class="dash-title">Quiz</h1>', template)
        self.assertEqual(template.count('id="practice-status"'), 1)
        for removed_text in ("Recommended", "practice-hero-title", "practice-hero-subtitle"):
            self.assertNotIn(removed_text, template)
        self.assertNotIn('id="practice-estimated-time"', template)
        self.assertIn("/* Compact quiz layout */", styles)
        self.assertRegex(
            styles,
            r"\.dashboard-overview,\s*\.dashboard-row,\s*\.tracking-panel\s*\{\s*display: none;",
        )
        self.assertRegex(
            styles,
            re.compile(r"\.dashboard-hero\s*\{[^}]*border-radius: 0;[^}]*background: transparent;", re.DOTALL),
        )
        self.assertRegex(styles, re.compile(r"\.choice-btn\s*\{[^}]*border-radius: 6px;", re.DOTALL))

    def test_styles_do_not_use_gradients(self) -> None:
        pattern = re.compile(r"(?:linear|radial|conic)-gradient", re.IGNORECASE)
        for stylesheet in (ROOT / "static" / "styles").glob("*.css"):
            self.assertIsNone(pattern.search(stylesheet.read_text(encoding="utf-8")), stylesheet.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
