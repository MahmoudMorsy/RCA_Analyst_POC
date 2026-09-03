from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from rca_app.case_parser import DeterministicCaseParser
from rca_app.compliance_engine import DeterministicComplianceEngine
from rca_app.models import (
    LogicExpression,
    LogicKind,
    NormativeType,
    PredicateOperator,
    RCARouteDecision,
    RequirementBehaviorIR,
    RequirementIR,
    RequirementPersistenceIR,
    RequirementPersistenceScope,
    RequirementRelationshipIR,
    RequirementSemanticClause,
    RequirementSemanticFingerprint,
    RequirementSemanticVerificationItem,
    RequirementStructuralPatch,
    SemanticArbitrationResponse,
    SemanticClauseRole,
    SemanticIntegrityIssue,
    SemanticPreparation,
    SemanticResolution,
)
from rca_app.pipeline import RCAPipeline
from rca_app.rca_routing import RCAEvidencePacketBuilder
from tests.test_v080 import FIX, tc17_preparation


def _pred(signal: str, value: str, sid: str = "C1") -> LogicExpression:
    return LogicExpression(
        kind=LogicKind.PREDICATE,
        semantic_id=sid,
        source_phrase=f"{signal} is {value}",
        signal=signal,
        operator=PredicateOperator.EQ,
        value=value,
    )


def test_v1811_verified_verifier_fingerprint_rejects_incomplete_required_behavior():
    # Exact TEST-016 failure class: verifier prose said VERIFIED but structured
    # behavior omitted operator/value, which v1.8.10 misread as disagreement.
    with pytest.raises(ValidationError, match="required_behavior is missing executable operator"):
        RequirementSemanticVerificationItem(
            requirement_id="REQ-1601",
            resolution=SemanticResolution.VERIFIED,
            independent_semantics=RequirementSemanticFingerprint(
                normative_type=NormativeType.MANDATORY,
                required_behavior=RequirementBehaviorIR(
                    signal="FunctionStatus",
                    event="BECOMES",
                    process_description="transition to state",
                ),
            ),
        )


def test_v1811_partial_verifier_may_remain_structurally_incomplete():
    item = RequirementSemanticVerificationItem(
        requirement_id="REQ-X",
        resolution=SemanticResolution.PARTIALLY_RESOLVED,
        independent_semantics=RequirementSemanticFingerprint(
            normative_type=NormativeType.MANDATORY,
            required_behavior=RequirementBehaviorIR(signal="FunctionStatus", event="BECOMES"),
        ),
        missing_or_misrepresented_source_spans=["ACTIVE"],
    )
    assert item.resolution == SemanticResolution.PARTIALLY_RESOLVED


def test_v1811_requirement_persistence_scope_is_canonical_and_rejects_evidence_domain():
    assert RequirementPersistenceIR(required=True, scope="WHILE_CONDITION_ACTIVE").scope == RequirementPersistenceScope.WHILE_CONDITION
    assert RequirementPersistenceIR(required=True, scope="while ActiveVariant is MANUAL").scope == RequirementPersistenceScope.WHILE_CONDITION
    assert RequirementPersistenceIR(required=True, scope="CASE_EVALUATED_INTERVAL").scope == RequirementPersistenceScope.CASE_EVALUATED_INTERVAL
    with pytest.raises(ValidationError):
        RequirementPersistenceIR(required=True, scope="INTERVAL_STATE")


def test_v1811_persistence_aliases_have_identical_semantic_fingerprint():
    a = RequirementIR(
        requirement_id="REQ-X", normative_type=NormativeType.MANDATORY,
        required_behavior=RequirementBehaviorIR(signal="WarningIndicator", operator=PredicateOperator.EQ, value="OFF"),
        persistence=RequirementPersistenceIR(required=True, scope="WHILE_CONDITION_ACTIVE"),
    )
    b = RequirementSemanticFingerprint(
        normative_type=NormativeType.MANDATORY,
        required_behavior=RequirementBehaviorIR(signal="WarningIndicator", operator=PredicateOperator.EQ, value="OFF"),
        persistence=RequirementPersistenceIR(required=True, scope="WHILE_CONDITION"),
    )
    assert RCAPipeline._ir_semantic_signature(a)["persistence"] == RCAPipeline._semantic_fingerprint_signature(b)["persistence"]


def test_v1811_arbitration_ignores_redundant_unchanged_untargeted_fields():
    clauses = [
        RequirementSemanticClause(semantic_id="REL1", role=SemanticClauseRole.RELATIONSHIP, source_phrase="REQ-1902 is a child of REQ-1901")
    ]
    prep = SemanticPreparation(requirement_irs=[RequirementIR(
        requirement_id="REQ-1902",
        normative_type=NormativeType.MANDATORY,
        required_behavior=RequirementBehaviorIR(semantic_id="B1", signal="X", operator=PredicateOperator.EQ, value="Y"),
        relationships=[RequirementRelationshipIR(semantic_id="REL1", relationship_type="", target_requirement_id="", source_phrase="REQ-1902 is a child of REQ-1901")],
        source_clauses=clauses,
    )])
    issue = SemanticIntegrityIssue(
        issue_id="VERIFY-001", requirement_id="REQ-1902",
        description="Independent source-semantic reconstruction disagrees with compiled IR in: relationships.",
        material_to_compliance=True, target_fields=["relationships"],
    )
    response = SemanticArbitrationResponse(requirement_patches=[RequirementStructuralPatch(
        requirement_id="REQ-1902",
        relationships=[RequirementRelationshipIR(semantic_id="REL1", relationship_type="CHILD", target_requirement_id="REQ-1901", source_phrase="REQ-1902 is a child of REQ-1901")],
        source_clauses=copy.deepcopy(clauses),  # redundant but unchanged TEST-019 shape
    )])
    notes = RCAPipeline._validate_arbitration_response(
        response, {"REQ-1902": ["relationships"]}, set(), [issue], prep,
    )
    assert any("redundant unchanged" in x for x in notes)


def test_v1811_arbitration_still_rejects_changed_untargeted_field():
    clauses = [RequirementSemanticClause(semantic_id="B1", role=SemanticClauseRole.REQUIRED_BEHAVIOR, source_phrase="X shall be Y")]
    prep = SemanticPreparation(requirement_irs=[RequirementIR(
        requirement_id="REQ-X", normative_type=NormativeType.MANDATORY,
        required_behavior=RequirementBehaviorIR(semantic_id="B1", signal="X", operator=PredicateOperator.EQ, value="Y"),
        source_clauses=clauses,
    )])
    issue = SemanticIntegrityIssue(issue_id="I1", requirement_id="REQ-X", description="condition mismatch", material_to_compliance=True, target_fields=["condition"])
    response = SemanticArbitrationResponse(requirement_patches=[RequirementStructuralPatch(
        requirement_id="REQ-X",
        condition=_pred("Mode", "ON"),
        source_clauses=[RequirementSemanticClause(semantic_id="B1", role=SemanticClauseRole.REQUIRED_BEHAVIOR, source_phrase="CHANGED")],
    )])
    with pytest.raises(ValueError, match="changed untargeted fields"):
        RCAPipeline._validate_arbitration_response(response, {"REQ-X": ["condition"]}, set(), [issue], prep)


def test_v1811_new_semantic_element_automatically_targets_source_clause_audit():
    prep = SemanticPreparation(requirement_irs=[RequirementIR(
        requirement_id="REQ-602",
        normative_type=NormativeType.PERMISSIVE,
        condition=_pred("ChildLockState", "OFF", "C602"),
        required_behavior=None,
        source_clauses=[RequirementSemanticClause(semantic_id="C602", role=SemanticClauseRole.CONDITION, source_phrase="If ChildLockState is OFF")],
    )])
    issue = SemanticIntegrityIssue(
        issue_id="VERIFY-602", requirement_id="REQ-602",
        description="Independent source-semantic reconstruction disagrees with compiled IR in: required_behavior.",
        material_to_compliance=True, target_fields=["required_behavior"],
    )
    targets = RCAPipeline._arbitration_requirement_targets(prep, [issue])
    assert targets["REQ-602"] == ["required_behavior", "source_clauses"]


def test_v1811_rca_packet_includes_referenced_canonical_structural_direct_observations():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    validated = DeterministicComplianceEngine().evaluate(canonical, prep, [])
    packet = RCAEvidencePacketBuilder().build(
        canonical, prep, validated,
        RCARouteDecision(run_rca=True, reasons=["test"], supporting_evidence_ids=[]),
    )
    by_id = {x.get("evidence_id"): x for x in packet.verified_evidence}
    assert by_id["EVID-DIRECT-003"]["source_kind"] == "CANONICAL_STRUCTURAL_DIRECT_OBSERVATION"
    assert by_id["EVID-DIRECT-003"]["subject"] == "IgnitionState"
    assert by_id["EVID-DIRECT-003"]["value"] == "ON"
    assert by_id["EVID-DIRECT-005"]["subject"] == "StarterEnable"


def test_v1811_rejected_arbitration_persists_contract_reason_in_attempt_audit():
    # Static contract check over the exact persistence path used by v1.8.10's
    # TEST-007 containment: raw response + explicit rejection reason are both kept.
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "rca_app" / "pipeline.py").read_text(encoding="utf-8")
    assert 'code="SEMANTIC_ARBITRATION_CONTRACT_REJECTED"' in source
    assert 'retry_diagnostics.append("Arbitration contract rejection: " + contract_message)' in source
