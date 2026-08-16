#!/usr/bin/env python3
"""Offline contract checks for the Phase 3 Learn Mode reliability boundary."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("learn_validation", ROOT / "app" / "learn_validation.py")
validation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(validation)


def question(index: int = 0) -> dict:
    stems = [
        "Which statement accurately defines customer segmentation?",
        "Which customer group should the school store target first?",
        "What recommendation should you present to the marketing director?",
    ]
    return {
        "text": stems[index],
        "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
        "correct": index,
        "explanation": "This choice correctly applies the relevant finance principle.",
    }


def lesson() -> dict:
    return {
        "lesson_design": {
            "complexity": "standard",
            "skill_type": "concept",
            "target_minutes": "3-5",
        },
        "instructional_plan": {
            "primary_archetype": "concept_discovery",
            "learner_action": "classify",
            "deca_action": "explain",
            "recommended_interactions": ["predict", "classify", "choose"],
        },
        "mission": {
            "title": "Find the right customer",
            "brief": "A school store has one advertising budget and several customer groups with different reasons for buying.",
            "opening_interaction": {
                "question": "Which group should receive the first targeted message?",
                "choices": ["Every student", "The group most likely to value the offer", "No one"],
                "correct": 1,
                "explanation": "Targeting works when the message fits a defined customer group.",
                "choice_feedback": [
                    "Reaching everyone usually weakens the relevance of the message.",
                    "You chose the group whose needs best match the offer.",
                    "Avoiding the audience does not solve the targeting decision.",
                ],
                "aha": "This is why strong marketing starts by deciding who the offer is for.",
            },
        },
        "hook": "You are helping a school store decide how to sell to different student groups.",
        "vocab": [
            {"term": f"Term {i}", "definition": f"Definition for finance term number {i}."}
            for i in range(4)
        ],
        "learning_blocks": [
            {"title": "The idea", "body": "This block explains the concept in plain English with enough detail for a student to understand it."},
            {"title": "Why it matters", "body": "This block connects the concept to a realistic DECA business decision the student might face."},
            {"title": "Use the evidence", "body": "This block shows how customer evidence supports a focused recommendation instead of a broad assumption."},
        ],
        "concept": {
            "summary": "A concise finance summary.",
            "explanation": "A sufficiently detailed explanation of the finance concept and how it is applied in a DECA setting.",
            "bullets": ["First concept", "Second concept", "Third concept"],
        },
        "interactive_check": {
            "question": "Which action best matches the concept?",
            "choices": ["Guess randomly", "Use the concept", "Ignore the data"],
            "correct": 1,
            "explanation": "Using the concept is the action that fits the lesson.",
        },
        "realistic_example": {
            "story": "A student-run hoodie shop notices athletes and theater students buy for different reasons, so it changes messages for each group.",
            "flow": ["Observation", "Customer groups", "Different offer"],
        },
        "mini_roleplay": {
            "role": "Store manager",
            "setup": "A customer group is not responding to your usual promotion.",
            "decisions": [
                {
                    "situation": "Sales are slow with one group.",
                    "question": "What should you do?",
                    "choices": ["Ignore them", "Learn what they need", "Raise every price"],
                    "correct": 1,
                    "explanation": "Learning what they need lets you adapt the business decision.",
                    "consequence": "You find the group values convenience more than discounts.",
                },
                {
                    "situation": "You now know what the group values.",
                    "question": "What comes next?",
                    "choices": ["Adjust the offer", "Stop selling", "Use the old ad"],
                    "correct": 0,
                    "explanation": "The offer should match the customer insight.",
                    "consequence": "The promotion becomes more relevant.",
                },
            ],
            "why_it_matters": "The roleplay shows how the KPI changes a real business choice.",
        },
        "key_takeaways": ["Use the concept in context", "Look for business evidence", "Choose the best action"],
        "practice_questions": [question(0), question(1), question(2)],
    }


class Phase3ContractTests(unittest.TestCase):
    def test_complete_lesson_is_normalized(self) -> None:
        clean = validation.validate_lesson(lesson())
        self.assertEqual(len(clean["vocab"]), 4)
        self.assertEqual(len(clean["practice_questions"]), 3)
        self.assertEqual(len(clean["recognition_questions"]), 2)
        self.assertEqual(len(clean["application_questions"]), 1)
        self.assertEqual(len(clean["concepts"]), 3)

    def test_malformed_lessons_are_rejected_before_persistence(self) -> None:
        cases = []
        missing_vocab = lesson(); missing_vocab["vocab"] = []
        cases.append(missing_vocab)
        duplicate_choices = lesson(); duplicate_choices["practice_questions"][0]["choices"][1] = "Choice A"
        cases.append(duplicate_choices)
        invalid_answer = lesson(); invalid_answer["practice_questions"][1]["correct"] = 4
        cases.append(invalid_answer)
        missing_application = lesson(); missing_application["practice_questions"] = []
        cases.append(missing_application)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(validation.LearnContentError):
                validation.validate_lesson(case)

    def test_only_three_beta_event_sources_are_authoritative(self) -> None:
        event_ids = {
            "accounting_application_series": "Accounting Application Series.json",
            "business_finance_series": "Business Finance Series.json",
            "financial_services_tdm": "Financial Services Team Decision Making.json",
        }
        events_source = (ROOT / "app" / "events.py").read_text(encoding="utf-8")
        for event_id, filename in event_ids.items():
            self.assertIn(event_id, events_source)
            payload = json.loads((ROOT / "performance indicator jsons" / "finance" / filename).read_text(encoding="utf-8"))
            self.assertTrue(payload)

    def test_answer_and_session_writes_are_atomic_and_server_authoritative(self) -> None:
        sql = (ROOT / "supabase" / "migrations" / "0014_atomic_learn_transactions.sql").read_text(encoding="utf-8").lower()
        route = (ROOT / "app" / "routes" / "learn.py").read_text(encoding="utf-8")
        for token in (
            "security invoker", "auth.uid()", "p_selected_index=v_question.correct_index",
            "insert into public.responses", "insert into public.user_srs_state",
            "insert into public.user_kpi_mastery", "insert into public.user_timing_profile",
            "insert into public.kpi_inference_state", "insert into public.learning_evaluation_log",
            "update public.user_study_sessions", "pg_advisory_xact_lock",
        ):
            self.assertIn(token, sql)
        self.assertIn('"/rpc/record_beta_answer"', route)
        self.assertIn('"/rpc/finish_beta_session"', route)

    def test_clients_send_attempt_selected_answer_and_session(self) -> None:
        for path in (ROOT / "static" / "js" / "learn.js", ROOT / "static" / "js" / "practicequestions.js"):
            source = path.read_text(encoding="utf-8")
            self.assertIn("attempt_id:", source)
            self.assertIn("selected_index:", source)
            self.assertIn("session_id:", source)
        self.assertNotIn("correct: ok", (ROOT / "static" / "js" / "learn.js").read_text(encoding="utf-8"))

    def test_search_has_one_event_scoped_owner(self) -> None:
        learn = (ROOT / "static" / "js" / "learn.js").read_text(encoding="utf-8")
        extra = (ROOT / "static" / "js" / "learn_extra.js").read_text(encoding="utf-8")
        self.assertIn("renderSearchResults", learn)
        self.assertNotIn("fetch('/api/kpis')", extra)


if __name__ == "__main__":
    unittest.main(verbosity=2)
