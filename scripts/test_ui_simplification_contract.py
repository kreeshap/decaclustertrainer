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

    def test_styles_do_not_use_gradients(self) -> None:
        pattern = re.compile(r"(?:linear|radial|conic)-gradient", re.IGNORECASE)
        for stylesheet in (ROOT / "static" / "styles").glob("*.css"):
            self.assertIsNone(pattern.search(stylesheet.read_text(encoding="utf-8")), stylesheet.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
