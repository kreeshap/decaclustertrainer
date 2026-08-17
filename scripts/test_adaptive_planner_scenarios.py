import unittest

from app.adaptive_planner import build_plan


def student(studied=0, total=408, attempts=0, due=0, weak=None, unfinished=None):
    return {
        "coverage": {"studied": studied, "total": total, "percent": round(100 * studied / total) if total else 0},
        "practice_attempt_count": attempts,
        "practice_correct_count": 0,
        "due_review_count": due,
        "due_reviews_by_topic": {weak["topic"]: due} if weak and due else {},
        "qualified_weakest_topic": weak,
        "unfinished_practice": unfinished,
        "median_kpi_minutes": 6,
        "median_question_seconds": 45,
    }


class AdaptivePlannerScenarioTests(unittest.TestCase):
    def test_brand_new_student_builds_coverage_without_inventing_a_weakness(self):
        plan = build_plan(student(), "financial_services_tdm", 20)
        labels = " ".join(item["label"] for item in plan["tasks"])
        self.assertIn("Learn", labels)
        self.assertIn("introductory questions", labels)
        self.assertNotIn("weak", labels.lower())
        self.assertIn("NO_QUALIFIED_WEAKNESS", plan["reason_codes"])
        self.assertIn("LOW_CURRICULUM_COVERAGE", plan["reason_codes"])

    def test_low_topic_coverage_cannot_become_a_qualified_weakness(self):
        plan = build_plan(student(studied=5, total=408, attempts=30), "financial_services_tdm", 20)
        labels = " ".join(item["label"] for item in plan["tasks"])
        self.assertNotIn("Business Law", labels)
        self.assertNotIn("QUALIFIED_WEAKNESS", plan["reason_codes"])

    def test_established_weakness_drives_review_learning_and_questions(self):
        weak = {"topic": "Business Law", "kpis_studied": 14, "kpis_total": 19,
                "attempts": 31, "accuracy": 58, "coverage_pct": 74}
        plan = build_plan(student(studied=170, attempts=66, due=3, weak=weak), "financial_services_tdm", 18)
        self.assertEqual([item["id"] for item in plan["tasks"]], ["review", "learn", "questions"])
        self.assertTrue(all("Business Law" in item["label"] for item in plan["tasks"]))
        self.assertIn("QUALIFIED_WEAKNESS", plan["reason_codes"])
        self.assertIn("DUE_REVIEW_PRIORITY", plan["reason_codes"])

    def test_large_review_load_still_balances_retention_coverage_and_practice(self):
        plan = build_plan(student(studied=180, attempts=50, due=17), "financial_services_tdm", 15)
        self.assertEqual([item["id"] for item in plan["tasks"]], ["review", "learn", "questions"])
        self.assertIn("Review 5", plan["tasks"][0]["label"])

    def test_unfinished_practice_is_always_first(self):
        active = {"id": "set-1", "title": "10-question practice", "current_index": 4, "question_count": 10}
        plan = build_plan(student(studied=20, attempts=20, unfinished=active), "financial_services_tdm", 20)
        self.assertEqual(plan["tasks"][0]["id"], "resume_practice")
        self.assertEqual(plan["tasks"][0]["remaining_questions"], 6)
        self.assertIn("UNFINISHED_WORK_PRIORITY", plan["reason_codes"])

    def test_time_budget_repacks_priorities_instead_of_truncating(self):
        five = build_plan(student(studied=20, attempts=20, due=8), "financial_services_tdm", 5)
        ten = build_plan(student(studied=20, attempts=20, due=8), "financial_services_tdm", 10)
        twenty = build_plan(student(studied=20, attempts=20, due=8), "financial_services_tdm", 20)
        self.assertEqual([x["id"] for x in five["tasks"]], ["review", "questions"])
        self.assertEqual(five["tasks"][1]["target"], 3)
        self.assertEqual([x["id"] for x in ten["tasks"]], ["review", "learn", "questions"])
        self.assertEqual([x["id"] for x in twenty["tasks"]], ["review", "learn", "questions"])
        self.assertEqual(twenty["tasks"][-1]["target"], 10)


if __name__ == "__main__":
    unittest.main()
