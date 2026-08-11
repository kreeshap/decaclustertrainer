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
    return {
        "text": "Which finance choice best applies to this situation?",
        "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
        "correct": index,
        "explanation": "This choice correctly applies the relevant finance principle.",
    }


def lesson() -> dict:
    return {
        "vocab": [
            {"term": f"Term {i}", "definition": f"Definition for finance term number {i}."}
            for i in range(6)
        ],
        "concept": {
            "summary": "A concise finance summary.",
            "explanation": "A sufficiently detailed explanation of the finance concept and how it is applied in a DECA setting.",
            "bullets": ["First concept", "Second concept", "Third concept"],
        },
        "recognition_questions": [question(i % 4) for i in range(5)],
        "application_question": question(2),
    }


class Phase3ContractTests(unittest.TestCase):
    def test_complete_lesson_is_normalized(self) -> None:
        clean = validation.validate_lesson(lesson())
        self.assertEqual(len(clean["vocab"]), 6)
        self.assertEqual(len(clean["recognition_questions"]), 5)
        self.assertEqual(len(clean["concepts"]), 3)

    def test_malformed_lessons_are_rejected_before_persistence(self) -> None:
        cases = []
        missing_vocab = lesson(); missing_vocab["vocab"] = []
        cases.append(missing_vocab)
        duplicate_choices = lesson(); duplicate_choices["recognition_questions"][0]["choices"][1] = "Choice A"
        cases.append(duplicate_choices)
        invalid_answer = lesson(); invalid_answer["application_question"]["correct"] = 4
        cases.append(invalid_answer)
        missing_application = lesson(); missing_application["application_question"] = None
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
