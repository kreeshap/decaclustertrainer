import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lesson_design", ROOT / "app" / "lesson_design.py")
lesson_design = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(lesson_design)


class LessonDesignContractTests(unittest.TestCase):
    def test_cognitive_demand_selects_the_archetype(self) -> None:
        cases = {
            "Explain the nature of customer loyalty": "concept_discovery",
            "Determine factors affecting a pricing decision": "decision_lab",
            "Demonstrate procedures for handling customer complaints": "communication_coach",
            "Explain the steps in resolving a workplace conflict": "build_process",
            "Calculate a business's break-even point": "numbers_lab",
            "Analyze company financial information": "diagnose_problem",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(lesson_design.classify_kpi(text)["primary_archetype"], expected)

    def test_every_plan_has_actions_and_interactions(self) -> None:
        plan = lesson_design.classify_kpi("Evaluate alternatives for a business expansion")
        self.assertTrue(plan["learner_action"])
        self.assertTrue(plan["deca_action"])
        self.assertGreaterEqual(len(plan["recommended_interactions"]), 2)

    def test_complexity_owns_duration_and_section_counts(self) -> None:
        quick = lesson_design.classify_kpi("Explain the nature of customer loyalty")
        deep = lesson_design.classify_kpi("Analyze company financial information")
        self.assertEqual(quick["target_minutes"], "2-3")
        self.assertEqual(quick["required_block_count"], 2)
        self.assertEqual(quick["vocab_mode"], "embedded")
        self.assertEqual(deep["target_minutes"], "5-7")
        self.assertEqual(deep["required_block_count"], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
