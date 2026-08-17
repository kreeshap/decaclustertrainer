import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEARN_HTML = (ROOT / "templates" / "learn.html").read_text(encoding="utf-8")
LEARN_JS = (ROOT / "static" / "js" / "learn.js").read_text(encoding="utf-8")
LESSON_DESIGN = (ROOT / "app" / "lesson_design.py").read_text(encoding="utf-8")


class LearnPipelineContractTests(unittest.TestCase):
    def test_content_learning_is_default_without_recall_typing(self) -> None:
        self.assertIn('let currentLearnMode = "standard"', LEARN_JS)
        self.assertNotIn('data-learn-mode="standard"', LEARN_HTML)
        self.assertNotIn('data-learn-mode="activeRecall"', LEARN_HTML)
        self.assertNotIn('id="active-recall-text"', LEARN_HTML)
        self.assertNotIn('id="recall-input"', LEARN_HTML)

    def test_skip_advances_without_marking_kpi_complete(self) -> None:
        self.assertIn('id="skip-kpi-btn"', LEARN_HTML)
        self.assertIn("function skipCurrentKpi()", LEARN_JS)
        skip_body = LEARN_JS.split("function skipCurrentKpi()", 1)[1].split("}", 1)[0]
        self.assertIn("sessionIdx++", skip_body)
        self.assertNotIn("completedKpiCodes.add", skip_body)

    def test_ai_copy_is_knowledge_dense_and_concise(self) -> None:
        self.assertIn("concise but substantive", LESSON_DESIGN)
        self.assertIn("maximum 120 words", LESSON_DESIGN)
        self.assertIn("maximum 70 words", LESSON_DESIGN)
        self.assertIn("Generate exactly {required_block_count} learning_blocks", LESSON_DESIGN)
        self.assertIn("Generate exactly {vocab_count} vocabulary terms", LESSON_DESIGN)

    def test_mission_and_feedback_are_part_of_the_pipeline(self) -> None:
        self.assertIn('id="state-mission"', LEARN_HTML)
        self.assertIn('id="state-kpi-feedback"', LEARN_HTML)
        self.assertIn("function startMission(kpi)", LEARN_JS)
        self.assertIn('showState("kpi-feedback")', LEARN_JS)
        self.assertIn("const LESSON_VERSION = 4", LEARN_JS)

    def test_vocabulary_interaction_changes_direction(self) -> None:
        self.assertIn("const definitionFirst = vocabIdx % 2 === 1", LEARN_JS)
        self.assertIn('"Choose the matching term"', LEARN_JS)
        self.assertIn('btn.dataset.correct = c.correct ? "1" : "0"', LEARN_JS)

    def test_lesson_ui_adapts_to_complexity(self) -> None:
        self.assertIn("const vocabLimit = { quick: 3, standard: 4, deep: 5 }", LEARN_JS)
        self.assertIn('complexity === "quick"', LEARN_JS)
        self.assertIn("[practiceQuestions[0], practiceQuestions[2]]", LEARN_JS)

    def test_failure_and_feedback_language_preserve_student_agency(self) -> None:
        self.assertIn('id="error-skip-btn"', LEARN_HTML)
        self.assertIn("Your progress is safe", LEARN_JS)
        self.assertIn("Strong initial understanding", LEARN_JS)
        self.assertIn("First-attempt lesson performance", LEARN_HTML)
        self.assertIn("Mastery history", LEARN_HTML)


if __name__ == "__main__":
    unittest.main(verbosity=2)
