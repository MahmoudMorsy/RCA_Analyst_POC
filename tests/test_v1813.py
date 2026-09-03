from __future__ import annotations

from rca_app.case_parser import DeterministicCaseParser
from rca_app.compliance_engine import DeterministicComplianceEngine
from rca_app.models import (
    CanonicalCase,
    EvidenceClass,
    EvidenceItem,
    EvidenceScopeAnnotation,
    EvidenceSemanticAnnotation,
    EvidenceSemanticFact,
    LogicExpression,
    LogicKind,
    NormativeType,
    ObservationType,
    PredicateOperator,
    RCARouteDecision,
    RequirementBehaviorIR,
    RequirementIR,
    RequirementPersistenceIR,
    RequirementRelationshipIR,
    RequirementSource,
    RequirementStructuralPatch,
    RequirementStructuralPatchBatch,
    ScopeResolution,
    SemanticArbitrationResponse,
    SemanticIntegrityIssue,
    SemanticPreparation,
    SemanticResolution,
    TemporalSemantics,
)
from rca_app.pipeline import RCAPipeline
from rca_app.rca_routing import RCAEvidencePacketBuilder
from rca_app.semantic_ir import SemanticArbitrationMerger
from tests.test_v080 import FIX, tc17_preparation


def _pred(signal: str, value: str, sid: str) -> LogicExpression:
    return LogicExpression(
        kind=LogicKind.PREDICATE,
        semantic_id=sid,
        source_phrase=f"{signal} is {value}",
        signal=signal,
        operator=PredicateOperator.EQ,
        value=value,
    )


def test_v1813_explicit_verifier_target_fields_override_explanatory_description_words():
    prep = SemanticPreparation(requirement_irs=[RequirementIR(
        requirement_id="REQ-1902",
        normative_type=NormativeType.MANDATORY,
        required_behavior=RequirementBehaviorIR(
            semantic_id="B1902", signal="ChildStatus", operator=PredicateOperator.EQ, value="READY"
        ),
        relationships=[RequirementRelationshipIR(
            semantic_id="REL1902", relationship_type="", target_requirement_id="",
            source_phrase="REQ-1902 is a child of REQ-1901",
        )],
    )])
    issue = SemanticIntegrityIssue(
        issue_id="VERIFY-1902",
        requirement_id="REQ-1902",
        description=(
            "The trigger, behavior, and timing are correctly captured. However, "
            "the relationship field is incomplete."
        ),
        material_to_compliance=True,
        target_fields=["relationships"],
    )
    assert RCAPipeline._structural_completion_targets(prep, [issue]) == {
        "REQ-1902": ["relationships"]
    }
    assert RCAPipeline._arbitration_requirement_targets(prep, [issue]) == {
        "REQ-1902": ["relationships"]
    }


def test_v1813_structural_completion_admits_valid_fields_and_leaves_omitted_sibling_unresolved():
    targets = {
        "REQ-301": ["required_behavior"],
        "REQ-302": ["required_behavior", "persistence"],
    }
    batch = RequirementStructuralPatchBatch(patches=[
        RequirementStructuralPatch(
            requirement_id="REQ-301",
            required_behavior=RequirementBehaviorIR(
                semantic_id="B301", signal="FunctionStatus", operator=PredicateOperator.EQ, value="ACTIVE"
            ),
        ),
        RequirementStructuralPatch(
            requirement_id="REQ-302",
            persistence=RequirementPersistenceIR(
                semantic_id="P302", required=True, scope="WHILE_CONDITION"
            ),
        ),
    ])
    admitted, notes = RCAPipeline._admit_structural_patches(batch, targets)
    by_id = {patch.requirement_id: patch for patch in admitted.patches}
    assert by_id["REQ-301"].required_behavior.value == "ACTIVE"
    assert by_id["REQ-302"].persistence.required is True
    assert by_id["REQ-302"].required_behavior is None
    assert any("REQ-302" in note and "required_behavior" in note and "unresolved" in note for note in notes)


def test_v1813_arbitration_admits_valid_sibling_repairs_when_one_target_field_is_omitted():
    prep = SemanticPreparation(requirement_irs=[
        RequirementIR(requirement_id="REQ-301", normative_type=NormativeType.MANDATORY),
        RequirementIR(requirement_id="REQ-302", normative_type=NormativeType.MANDATORY),
    ])
    issues = [
        SemanticIntegrityIssue(
            issue_id="V301", requirement_id="REQ-301", description="behavior mismatch",
            material_to_compliance=True, target_fields=["required_behavior"],
        ),
        SemanticIntegrityIssue(
            issue_id="V302B", requirement_id="REQ-302", description="behavior mismatch",
            material_to_compliance=True, target_fields=["required_behavior"],
        ),
        SemanticIntegrityIssue(
            issue_id="V302P", requirement_id="REQ-302", description="persistence mismatch",
            material_to_compliance=True, target_fields=["persistence"],
        ),
    ]
    targets = {"REQ-301": ["required_behavior"], "REQ-302": ["required_behavior", "persistence"]}
    response = SemanticArbitrationResponse(requirement_patches=[
        RequirementStructuralPatch(
            requirement_id="REQ-301",
            required_behavior=RequirementBehaviorIR(
                semantic_id="B301", signal="FunctionStatus", operator=PredicateOperator.EQ, value="ACTIVE"
            ),
        ),
        RequirementStructuralPatch(
            requirement_id="REQ-302",
            persistence=RequirementPersistenceIR(
                semantic_id="P302", required=True, scope="WHILE_CONDITION"
            ),
        ),
    ])
    notes = RCAPipeline._validate_arbitration_response(response, targets, set(), issues, prep)
    assert any("REQ-302.required_behavior" in note and "remains unresolved" in note for note in notes)
    merged = SemanticArbitrationMerger.apply(prep, response, targets, set())
    by_id = {ir.requirement_id: ir for ir in merged.requirement_irs}
    assert by_id["REQ-301"].required_behavior.value == "ACTIVE"
    assert by_id["REQ-302"].persistence.required is True
    assert by_id["REQ-302"].required_behavior is None


def test_v1813_rca_packet_closes_selected_current_snapshot_by_group_and_aligned_timestamp():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    validated = DeterministicComplianceEngine().evaluate(canonical, prep, [])

    # EVID-DIRECT-003 is already referenced by deterministic TEST-017 results.
    seed = next(item for item in canonical.evidence_inventory if item.id == "EVID-DIRECT-003")
    seed.observation_group = "FAIL_POINT"
    seed.timestamped = True
    seed.timestamp_seconds = 42.0
    seed.clock_id = "TRACE_A"
    canonical.evidence_inventory.extend([
        EvidenceItem(
            id="EVID-DIRECT-GROUP-PEER",
            evidence_class=EvidenceClass.DIRECT_OBSERVATION,
            text="ActuatorCommunication = LOST",
            source="Direct Observations / Trace",
            signal_name="ActuatorCommunication",
            signal_value="LOST",
            observation_type=ObservationType.STATE_SAMPLE,
            observation_group="FAIL_POINT",
        ),
        EvidenceItem(
            id="EVID-DIRECT-TIME-PEER",
            evidence_class=EvidenceClass.DIRECT_OBSERVATION,
            text="CommunicationWarning = ON",
            source="Direct Observations / Trace",
            signal_name="CommunicationWarning",
            signal_value="ON",
            observation_type=ObservationType.STATE_SAMPLE,
            timestamped=True,
            timestamp_seconds=42.0,
            clock_id="TRACE_A",
        ),
        EvidenceItem(
            id="EVID-DIRECT-UNRELATED",
            evidence_class=EvidenceClass.DIRECT_OBSERVATION,
            text="Unrelated = X",
            source="Direct Observations / Trace",
            signal_name="Unrelated",
            signal_value="X",
            observation_type=ObservationType.STATE_SAMPLE,
            observation_group="OTHER_POINT",
        ),
    ])

    packet = RCAEvidencePacketBuilder().build(
        canonical, prep, validated,
        RCARouteDecision(run_rca=True, reasons=["test"], supporting_evidence_ids=[]),
    )
    ids = {item.get("evidence_id") for item in packet.verified_evidence}
    assert "EVID-DIRECT-GROUP-PEER" in ids
    assert "EVID-DIRECT-TIME-PEER" in ids
    assert "EVID-DIRECT-UNRELATED" not in ids


def test_v1813_historical_semantic_facts_never_enter_deterministic_compliance_evidence():
    canonical = CanonicalCase(
        ticket_id="TEST-HIST-GATE",
        requirements=[RequirementSource(
            requirement_id="REQ-1",
            requirement_text="If PowerMode is ON, ActuatorStatus shall be NOT_READY.",
        )],
        evidence_inventory=[
            EvidenceItem(
                id="EVID-DIRECT-1", evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text="PowerMode = ON", source="Direct Observations / Trace",
                signal_name="PowerMode", signal_value="ON",
                observation_type=ObservationType.STATE_SAMPLE, observation_group="P1",
            ),
            EvidenceItem(
                id="EVID-DIRECT-2", evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text="ActuatorStatus = NOT_READY", source="Direct Observations / Trace",
                signal_name="ActuatorStatus", signal_value="NOT_READY",
                observation_type=ObservationType.STATE_SAMPLE, observation_group="P1",
            ),
            EvidenceItem(
                id="EVID-HIST-1", evidence_class=EvidenceClass.HISTORICAL_EVIDENCE,
                text="PowerMode ON and ActuatorStatus NOT_READY in an older ticket.", source="Historical Tickets",
            ),
        ],
    )
    prep = SemanticPreparation(
        requirement_irs=[RequirementIR(
            requirement_id="REQ-1",
            normative_type=NormativeType.MANDATORY,
            condition=_pred("PowerMode", "ON", "C1"),
            required_behavior=RequirementBehaviorIR(
                semantic_id="B1", signal="ActuatorStatus", operator=PredicateOperator.EQ, value="NOT_READY"
            ),
        )],
        evidence_annotations=[EvidenceSemanticAnnotation(
            evidence_id="EVID-HIST-1",
            resolution=SemanticResolution.VERIFIED,
            facts=[
                EvidenceSemanticFact(
                    fact_id="H1", source_phrase="PowerMode ON", subject="PowerMode",
                    operator=PredicateOperator.EQ, value="ON",
                    temporal_semantics=TemporalSemantics.POINT_STATE,
                    scope=EvidenceScopeAnnotation(resolution=ScopeResolution.NOT_APPLICABLE),
                    resolution=SemanticResolution.VERIFIED,
                    related_requirement_ids=["REQ-1"],
                ),
                EvidenceSemanticFact(
                    fact_id="H2", source_phrase="ActuatorStatus NOT_READY", subject="ActuatorStatus",
                    operator=PredicateOperator.EQ, value="NOT_READY",
                    temporal_semantics=TemporalSemantics.POINT_STATE,
                    scope=EvidenceScopeAnnotation(resolution=ScopeResolution.NOT_APPLICABLE),
                    resolution=SemanticResolution.VERIFIED,
                    related_requirement_ids=["REQ-1"],
                ),
            ],
        )],
    )

    validated = DeterministicComplianceEngine().evaluate(canonical, prep, [])
    result = validated.requirement_results[0]
    assert result.analysis.applicability.value == "APPLICABLE"
    assert result.evaluation_status.value == "SATISFIED"
    assert "EVID-HIST-1" not in result.analysis.applicability_evidence_ids
    assert "EVID-HIST-1" not in result.analysis.evaluation_evidence_ids
    assert set(result.analysis.applicability_evidence_ids) == {"EVID-DIRECT-1"}
    assert set(result.analysis.evaluation_evidence_ids) == {"EVID-DIRECT-2"}
