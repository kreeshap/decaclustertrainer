import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.content_ops import (  # noqa: E402
    apply_review_choice,
    build_review_decision,
    resolve_classification,
    retryable_failed_kpi_ids,
    sanitize_reviewer,
)


BASE = {
    "skill_type": "concept",
    "complexity": "quick",
    "primary_archetype": "concept_discovery",
    "secondary_archetype": None,
    "learner_action": "identify",
    "deca_action": "explain",
    "recommended_interactions": ["predict", "classify"],
    "classification_reason": "The KPI asks the learner to identify a defined concept in a structured way.",
    "certainty": "medium",
    "ambiguity_reason": None,
    "alternative_archetype": None,
    "field_confidence": {field: 0.2 for field in ("skill_type", "complexity", "primary_archetype", "learner_action", "deca_action")},
}


class AdminReviewLogicTests(unittest.TestCase):
    def test_same_archetype_recommendation_is_rejected(self):
        reviewer = sanitize_reviewer({
            "verdict": "correct",
            "issues": ["The concept discovery archetype is insufficient for this KPI."],
            "corrected": {"primary_archetype": "concept_discovery", "learner_action": "identify", "deca_action": "explain"},
            "confidence": 0.99,
            "reason": "The concept discovery archetype is insufficient for this KPI.",
        }, BASE)
        self.assertEqual(reviewer["verdict"], "uncertain")
        self.assertIsNone(reviewer["recommended_archetype"])
        self.assertTrue(any("same values" in item for item in reviewer["issues"]))
        _final, _validator, needs_review = resolve_classification(BASE, reviewer)
        self.assertTrue(needs_review)
        decision = build_review_decision({**BASE, "reviewer_result": reviewer, "deterministic_check": {}})
        self.assertIsNone(decision["recommended"])
        self.assertFalse(decision["auto_resolvable"])

    def test_malformed_reviewer_stays_in_manual_queue(self):
        reviewer = sanitize_reviewer("not-json", BASE)
        self.assertEqual(reviewer["verdict"], "uncertain")
        _final, _validator, needs_review = resolve_classification(BASE, reviewer)
        self.assertTrue(needs_review)

    def test_valid_repair_auto_resolves_without_confidence_threshold(self):
        reviewer = {
            "verdict": "correct",
            "issues": ["This KPI requires structured explanation."],
            "corrected": {
                "skill_type": "concept",
                "complexity": "quick",
                "primary_archetype": "build_process",
                "learner_action": "sequence",
                "deca_action": "demonstrate",
                "recommended_interactions": ["sequence", "predict"],
            },
            "confidence": 0.1,
            "reason": "Describe requires the learner to explain how the system is structured.",
        }
        final, validator, needs_review = resolve_classification(BASE, reviewer)
        self.assertFalse(needs_review)
        self.assertTrue(validator["repaired"])
        self.assertEqual(final["primary_archetype"], "build_process")
        self.assertEqual(final["learner_action"], "sequence")

    def test_reviewer_pass_auto_resolves_even_with_low_field_confidence(self):
        reviewer = {"verdict": "pass", "issues": [], "corrected": None, "confidence": 0.4, "reason": "Classification matches the KPI verb and cognitive demand."}
        _final, _validator, needs_review = resolve_classification(BASE, reviewer)
        self.assertFalse(needs_review)

    def test_admin_approve_applies_recommended_fields(self):
        row = {
            **BASE,
            "reviewer_result": {
                "verdict": "correct",
                "issues": ["needs a human look at archetype fit"],
                "corrected": {
                    "primary_archetype": "communication_coach",
                    "learner_action": "respond",
                    "deca_action": "demonstrate",
                    "recommended_interactions": ["choose", "respond"],
                    "classification_reason": "The learner must handle a customer response, not merely identify a term.",
                    "certainty": "medium",
                    "skill_type": "communication",
                    "complexity": "standard",
                },
                "confidence": 0.5,
                "reason": "The learner must handle a customer response, not merely identify a term.",
            },
            "deterministic_check": {},
        }
        payload = apply_review_choice(row, "recommended")
        self.assertEqual(payload["primary_archetype"], "communication_coach")
        self.assertEqual(payload["learner_action"], "respond")
        self.assertTrue(payload["manual_override"])
        keep = apply_review_choice(row, "current")
        self.assertEqual(keep, {"manual_override": True})

    def test_retry_uses_latest_job_only(self):
        jobs = [
            {"kpi_id": "a", "status": "failed", "created_at": "2026-01-01T00:00:00Z"},
            {"kpi_id": "a", "status": "auto_approved", "created_at": "2026-01-02T00:00:00Z"},
            {"kpi_id": "b", "status": "failed", "created_at": "2026-01-03T00:00:00Z"},
            {"kpi_id": "c", "status": "failed", "created_at": "2026-01-01T00:00:00Z"},
            {"kpi_id": "c", "status": "queued", "created_at": "2026-01-04T00:00:00Z"},
        ]
        self.assertEqual(retryable_failed_kpi_ids(jobs), ["b"])

    def test_keep_with_null_correction_auto_resolves(self):
        reviewer = {"verdict": "keep", "correction": None, "reason": "The current classification is appropriate for this KPI."}
        final, validator, needs_review = resolve_classification(BASE, reviewer)
        self.assertFalse(needs_review)
        self.assertEqual(final["primary_archetype"], "concept_discovery")
        self.assertEqual(validator["routing_reason"], "reviewer_keep")
        decision = build_review_decision({**BASE, "reviewer_result": reviewer, "deterministic_check": {}})
        self.assertTrue(decision["auto_resolvable"])
        self.assertNotIn("reviewer correction was missing", decision["problem"])

    def test_auto_resolved_pass_does_not_remain_in_manual_queue(self):
        decision = build_review_decision({
            **BASE,
            "reviewer_result": {"verdict": "pass", "issues": [], "corrected": None, "confidence": 0.9, "reason": "Looks right for this KPI and action pair."},
            "deterministic_check": {"issues": []},
        })
        self.assertTrue(decision["auto_resolvable"])
        self.assertEqual(decision["choice_ids"], ["current"])
        self.assertEqual(decision["reviewer"]["verdict"], "keep")

    def test_missing_correction_does_not_imply_uncertainty_on_keep(self):
        reviewer = sanitize_reviewer({
            "verdict": "keep",
            "correction": None,
            "issues": [],
            "reason": "No correction is needed because the current classification is appropriate.",
        }, BASE)
        self.assertEqual(reviewer["verdict"], "keep")
        self.assertIsNone(reviewer["correction"])
        _final, _validator, needs_review = resolve_classification(BASE, reviewer)
        self.assertFalse(needs_review)

    def test_change_with_valid_correction_auto_applies(self):
        reviewer = {
            "verdict": "change",
            "correction": {"complexity": "standard"},
            "reason": "This KPI needs more than a quick treatment because the learner must apply the concept.",
        }
        final, validator, needs_review = resolve_classification(BASE, reviewer)
        self.assertFalse(needs_review)
        self.assertTrue(validator["repaired"])
        self.assertEqual(final["complexity"], "standard")
        self.assertEqual(validator["routing_reason"], "reviewer_change")
        decision = build_review_decision({**BASE, "reviewer_result": reviewer, "deterministic_check": {}})
        self.assertTrue(decision["auto_resolvable"])
        self.assertTrue(decision["applied_correction"])

    def test_uncertain_stays_in_manual_review(self):
        reviewer = {"verdict": "uncertain", "reason": "Reviewer is uncertain whether this KPI is Decision Lab or Concept Discovery."}
        _final, validator, needs_review = resolve_classification(BASE, reviewer)
        self.assertTrue(needs_review)
        self.assertEqual(validator["routing_reason"], "reviewer_uncertain")
        decision = build_review_decision({**BASE, "reviewer_result": reviewer, "deterministic_check": {}})
        self.assertFalse(decision["auto_resolvable"])
        self.assertIn("uncertain", decision["problem"].lower())
        self.assertEqual(decision["choice_ids"], ["current", "skip"])
        self.assertIsNone(decision["recommended"])

    def test_invalid_change_goes_to_manual_review(self):
        reviewer = {
            "verdict": "change",
            "correction": {"learner_action": "not-a-real-action"},
            "reason": "The learner action should change, but the suggested value is not allowed.",
        }
        _final, validator, needs_review = resolve_classification(BASE, reviewer)
        self.assertTrue(needs_review)
        self.assertEqual(validator["routing_reason"], "invalid_correction")

    def test_same_value_correction_never_auto_applies(self):
        reviewer = sanitize_reviewer({
            "verdict": "change",
            "issues": ["The concept discovery archetype is insufficient for this KPI."],
            "correction": {"primary_archetype": "concept_discovery"},
            "reason": "The concept discovery archetype is insufficient for this KPI.",
        }, BASE)
        self.assertEqual(reviewer["verdict"], "uncertain")
        self.assertEqual(reviewer["routing_reason"], "same_value_correction")
        _final, _validator, needs_review = resolve_classification(BASE, reviewer)
        self.assertTrue(needs_review)

    def test_soft_heuristic_disagreement_does_not_force_review(self):
        reviewer = {
            "verdict": "keep",
            "correction": None,
            "reason": "Standard complexity is more appropriate than the deterministic quick label.",
        }
        classification = {**BASE, "complexity": "standard"}
        _final, validator, needs_review = resolve_classification(classification, reviewer)
        self.assertFalse(needs_review)
        self.assertEqual(validator["routing_reason"], "reviewer_keep")
        decision = build_review_decision({
            **classification,
            "reviewer_result": reviewer,
            "deterministic_check": {
                "complexity": "quick",
                "disagreements": ["complexity"],
                "disagreement_severity": "soft",
            },
        })
        self.assertTrue(decision["auto_resolvable"])
        self.assertTrue(decision["soft_heuristic_disagreement"])
        self.assertNotIn("disagree", decision["problem"].lower())

    def test_hard_contradiction_on_keep_requires_review(self):
        broken = {**BASE, "learner_action": "choose", "deca_action": "explain"}
        reviewer = {"verdict": "keep", "correction": None, "reason": "The current classification is appropriate."}
        _final, validator, needs_review = resolve_classification(broken, reviewer)
        self.assertTrue(needs_review)
        self.assertEqual(validator["routing_reason"], "action_conflict")

    def test_legacy_keep_from_missing_correction_bug(self):
        stored = {
            "verdict": "uncertain",
            "issues": ["reviewer correction was missing"],
            "corrected": None,
            "confidence": 0.8,
            "reason": "The current classification is appropriate. The deterministic alternative oversimplifies the KPI.",
        }
        reviewer = sanitize_reviewer(stored, BASE)
        self.assertEqual(reviewer["verdict"], "keep")
        self.assertEqual(reviewer["routing_reason"], "legacy_keep_inferred")
        self.assertNotIn("reviewer correction was missing", reviewer["issues"])
        _final, validator, needs_review = resolve_classification(BASE, stored)
        self.assertFalse(needs_review)
        self.assertEqual(validator["routing_reason"], "legacy_keep_inferred")

    def test_legacy_correct_token_with_keep_reason(self):
        stored = {
            "verdict": "correct",
            "corrected": None,
            "reason": "The original AI classification better aligns with the KPI than the heuristic.",
        }
        reviewer = sanitize_reviewer(stored, BASE)
        self.assertEqual(reviewer["verdict"], "keep")
        _final, _validator, needs_review = resolve_classification(BASE, stored)
        self.assertFalse(needs_review)

    def test_legacy_ambiguous_stays_in_review(self):
        stored = {
            "verdict": "correct",
            "corrected": None,
            "reason": "There may be another way to frame this task.",
        }
        reviewer = sanitize_reviewer(stored, BASE)
        self.assertEqual(reviewer["verdict"], "uncertain")
        self.assertEqual(reviewer["routing_reason"], "legacy_ambiguous")
        _final, _validator, needs_review = resolve_classification(BASE, stored)
        self.assertTrue(needs_review)
        decision = build_review_decision({**BASE, "reviewer_result": stored, "deterministic_check": {}})
        self.assertFalse(decision["auto_resolvable"])
        self.assertNotEqual(decision["problem"], "reviewer correction was missing")

    def test_keep_problem_text_is_not_missing_correction(self):
        decision = build_review_decision({
            **BASE,
            "reviewer_result": {
                "verdict": "uncertain",
                "issues": ["reviewer correction was missing"],
                "reason": "The existing archetype correctly represents the task.",
            },
            "deterministic_check": {"disagreements": ["complexity"]},
        })
        self.assertTrue(decision["auto_resolvable"])
        self.assertEqual(decision["problem"], "")



if __name__ == "__main__":
    unittest.main()
