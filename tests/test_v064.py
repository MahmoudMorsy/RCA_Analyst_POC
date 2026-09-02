from __future__ import annotations

import re
from pathlib import Path

from rca_app.config import AppConfig
from rca_app.models import (
    CanonicalCase,
    LinguisticReviewResponse,
    RequirementLinguisticReview,
    RequirementSource,
    ReviewClaimedEvaluationStatus,
    ReviewEvidenceRelevance,
    ReviewEvidenceSufficiency,
    ReviewVerdictConsistency,
)
from rca_app.prompts import FAST_FINAL_REVIEW_PROMPT
from rca_app.review import LinguisticReviewGate
from rca_app.validator import DeterministicValidator
from tests.test_v060 import _tc5_style_validated


REQ_TEXT = "When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms."


def _canonical_from_validated(validated):
    return CanonicalCase(
        ticket_id="TEST-005",
        title="Late activation",
        description="coverage incomplete",
        evidence_inventory=list(validated.semantic.evidence_inventory),
        requirements=[RequirementSource(requirement_id="REQ-401", requirement_text=REQ_TEXT)],
    )


def test_v064_final_review_prompt_requires_claim_extraction_and_valid_combo():
    assert "evidence_relevance" in FAST_FINAL_REVIEW_PROMPT
    assert "evidence_sufficiency" in FAST_FINAL_REVIEW_PROMPT
    assert "claimed_evaluation_status" in FAST_FINAL_REVIEW_PROMPT
    assert "RELEVANT + INSUFFICIENT + NOT_EVALUABLE is a VALID combination" in FAST_FINAL_REVIEW_PROMPT
    assert "missing_evaluation_evidence.element=\"RESPONSE\"" in FAST_FINAL_REVIEW_PROMPT


def test_v064_final_review_has_independent_settings_from_repair():
    cfg = AppConfig()
    assert cfg.fast_repair_thinking_mode == "off"
    assert hasattr(cfg, "fast_final_review_reasoning_effort")
    assert hasattr(cfg, "fast_final_review_thinking_mode")
    assert hasattr(cfg, "fast_final_review_transport")


def test_v064_tc5_relevant_insufficient_not_evaluable_false_contradiction_is_rejected():
    validated = _tc5_style_validated(
        "The observed response is relevant to the timing requirement while the timing constraint remains unevaluable because complete transition-event coverage is unavailable."
    )
    review = LinguisticReviewResponse(requirement_reviews=[RequirementLinguisticReview(
        requirement_id="REQ-401",
        evidence_relevance=ReviewEvidenceRelevance.RELEVANT,
        evidence_sufficiency=ReviewEvidenceSufficiency.INSUFFICIENT,
        claimed_evaluation_status=ReviewClaimedEvaluationStatus.NOT_EVALUABLE,
        verdict_consistency=ReviewVerdictConsistency.INCONSISTENT,
        wording_issue=True,
        issue_message="Relevant and insufficient are contradictory.",
        replacement_relevance="The response is not relevant because evidence is incomplete.",
    )])
    gated, accepted, rejected = LinguisticReviewGate.apply(
        validated, review, _canonical_from_validated(validated), DeterministicValidator()
    )
    assert accepted == []
    assert any("false-positive wording contradiction" in item for item in rejected)
    assert gated.requirement_results[0].analysis.relevance == validated.requirement_results[0].analysis.relevance


def test_v064_actual_extracted_verdict_conflict_can_propose_relevance_rewrite():
    validated = _tc5_style_validated(
        "Timing remains unevaluable because complete event coverage is unavailable."
    )
    review = LinguisticReviewResponse(requirement_reviews=[RequirementLinguisticReview(
        requirement_id="REQ-401",
        evidence_relevance=ReviewEvidenceRelevance.RELEVANT,
        evidence_sufficiency=ReviewEvidenceSufficiency.SUFFICIENT,
        claimed_evaluation_status=ReviewClaimedEvaluationStatus.VIOLATED,
        verdict_consistency=ReviewVerdictConsistency.INCONSISTENT,
        wording_issue=True,
        issue_message="The wording claims a violation and sufficient timing evidence.",
        replacement_relevance="The visible response timing is relevant, but complete transition-event coverage is unavailable, so the timing constraint remains not evaluable.",
    )])
    gated, accepted, rejected = LinguisticReviewGate.apply(
        validated, review, _canonical_from_validated(validated), DeterministicValidator()
    )
    assert accepted == ["REQ-401"]
    assert rejected == []
    rr = gated.requirement_results[0]
    assert rr.evaluation_status.value == "NOT EVALUABLE"
    assert "not evaluable" in rr.analysis.relevance.lower()


def test_v064_compact_payload_exposes_authoritative_review_classification():
    validated = _tc5_style_validated(
        "The response is relevant while the timing requirement remains unevaluable because event coverage is incomplete."
    )
    payload = LinguisticReviewGate.compact_payload(validated)
    req = payload["authoritative_requirements"][0]
    assert req["expected_review_classification"] == {
        "evidence_relevance": "RELEVANT",
        "evidence_sufficiency": "INSUFFICIENT",
        "evaluation_status": "NOT_EVALUABLE",
    }
    assert any("RELEVANT + INSUFFICIENT + NOT_EVALUABLE" in x for x in payload["valid_logic_combinations"])


def test_v064_version_history_contains_every_changelog_release_in_chronological_transitions():
    root = Path(__file__).resolve().parent.parent
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    history = (root / "VERSION_HISTORY.md").read_text(encoding="utf-8")
    versions = re.findall(r"(?m)^##\s+([0-9][^\n]*)$", changelog)
    assert versions[0] == "1.8.8"
    for version in versions:
        assert f"v{version}" in history
    assert "## v0.6.3 → v0.6.4" in history
    assert "Current release:** v1.8.8" in history
