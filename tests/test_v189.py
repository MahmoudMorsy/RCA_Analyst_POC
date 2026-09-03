from __future__ import annotations

from pathlib import Path

import pytest

from rca_app.case_parser import DeterministicCaseParser
from rca_app.compliance_engine import DeterministicComplianceEngine, FactRecord
from rca_app.models import (
    Applicability,
    EvidenceClass,
    EvidenceItem,
    EvidenceScopeAnnotation,
    EvidenceSemanticAnnotation,
    EvidenceSemanticFact,
    EvaluationStatus,
    HypothesisAnalysis,
    HypothesisSupportBasis,
    PredicateOperator,
    RCARouteDecision,
    RCASynthesisReasoning,
    RequirementBehaviorIR,
    RequirementStructuralPatch,
    RequirementStructuralPatchBatch,
    SemanticAnalysis,
    SemanticArbitrationResponse,
    SemanticIntegrityIssue,
    SemanticPreparation,
    SemanticResolution,
    ScopeResolution,
    TemporalSemantics,
    ValidatedAnalysis,
)
from rca_app.pipeline import RCAPipeline
from rca_app.rca_routing import RCAEvidencePacketBuilder
from rca_app.semantic_ir import SemanticArbitrationMerger, SemanticIntegrityChecker
from tests.test_v080 import FIX, tc17_preparation


def test_v189_verified_fact_related_ids_are_not_execution_whitelist():
    fact = FactRecord(
        evidence_id="EVID-SVC",
        signal="ServiceMode",
        value="INACTIVE",
        interval_scope=True,
        scope_id="CASE_EVALUATED_INTERVAL",
        related_requirement_ids=("REQ-1703",),
    )
    assert DeterministicComplianceEngine._fact_allowed_for_requirement(fact, "REQ-1701") is True


def test_v189_tc17_fact_reuse_restores_expected_deterministic_result():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    # Reproduce the 27B rerun linkage: the ServiceMode interval fact is linked
    # only to REQ-1703, although it also satisfies REQ-1701's NEQ predicate.
    for ann in prep.evidence_annotations:
        for fact in ann.facts:
            if fact.subject == "ServiceMode":
                fact.related_requirement_ids = ["REQ-1703"]
    out = DeterministicComplianceEngine().evaluate(canonical, prep)
    by_id = {x.analysis.requirement_id: x for x in out.requirement_results}
    assert by_id["REQ-1701"].analysis.applicability == Applicability.APPLICABLE
    assert by_id["REQ-1701"].evaluation_status == EvaluationStatus.VIOLATED
    assert by_id["REQ-1702"].analysis.applicability == Applicability.NOT_APPLICABLE
    assert by_id["REQ-1703"].analysis.applicability == Applicability.NOT_APPLICABLE


def test_v189_structural_completion_rejects_partial_target_set():
    patch = RequirementStructuralPatch(
        requirement_id="REQ-2102",
        required_behavior=RequirementBehaviorIR(
            semantic_id="rb", signal="DriverSeatHeatingStatus",
            operator=PredicateOperator.EQ, value="ACTIVE",
            source_phrase="DriverSeatHeatingStatus shall become ACTIVE",
        ),
    )
    batch = RequirementStructuralPatchBatch(patches=[patch])
    with pytest.raises(ValueError, match="omitted targeted fields"):
        RCAPipeline._validate_structural_patches(
            batch,
            {"REQ-2102": ["trigger", "required_behavior", "timing"]},
        )


def test_v189_arbitration_full_ir_is_merged_only_into_targeted_fields():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    original = prep.requirement_irs[0].model_copy(deep=True)
    replacement_condition = prep.requirement_irs[1].condition.model_copy(deep=True)
    arb = SemanticArbitrationResponse(requirement_patches=[RequirementStructuralPatch(
        requirement_id="REQ-1701", condition=replacement_condition
    )])
    merged = SemanticArbitrationMerger.apply(prep, arb, {"REQ-1701": ["condition"]})
    req = merged.requirement_irs[0]
    assert req.condition == replacement_condition
    assert req.required_behavior.value == original.required_behavior.value


def test_v189_case_level_free_text_ambiguity_is_advisory_not_global_blocker():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    prep.unresolved_case_semantics = ["Title does not repeat the timing threshold."]
    issues = SemanticIntegrityChecker.validate(canonical, prep)
    note = next(x for x in issues if "Case-level semantic ambiguity" in x.description)
    assert note.material_to_compliance is False


def test_v189_rca_packet_uses_canonical_source_class_for_diagnostics_and_history():
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(
        "Ticket ID: X\nTitle: x\nDescription: x\nDiagnostics:\nDTC U1123 present\nHistorical Tickets:\nHIST-A communication issue"
    )
    # Create minimal canonical evidence explicitly to avoid parser-format coupling.
    canonical.evidence_inventory.extend([
        EvidenceItem(id="EVID-DIAG-X", evidence_class=EvidenceClass.DIRECT_OBSERVATION, text="DTC U1123 present", source="Current BZD / Diagnostics"),
        EvidenceItem(id="EVID-HIST-X", evidence_class=EvidenceClass.HISTORICAL_EVIDENCE, text="HIST-A communication issue", source="Historical Tickets"),
    ])
    prep = SemanticPreparation(evidence_annotations=[
        EvidenceSemanticAnnotation(evidence_id="EVID-DIAG-X", resolution=SemanticResolution.VERIFIED, facts=[
            EvidenceSemanticFact(fact_id="D-F1", source_phrase="DTC U1123 present", subject="U1123", operator=PredicateOperator.PRESENT, value="present", temporal_semantics=TemporalSemantics.POINT_STATE, scope=EvidenceScopeAnnotation(resolution=ScopeResolution.NOT_APPLICABLE), resolution=SemanticResolution.VERIFIED)
        ]),
        EvidenceSemanticAnnotation(evidence_id="EVID-HIST-X", resolution=SemanticResolution.VERIFIED, facts=[
            EvidenceSemanticFact(fact_id="H-F1", source_phrase="HIST-A communication issue", subject="HIST-A", operator=PredicateOperator.PRESENT, value="communication issue", temporal_semantics=TemporalSemantics.POINT_STATE, scope=EvidenceScopeAnnotation(resolution=ScopeResolution.NOT_APPLICABLE), resolution=SemanticResolution.VERIFIED)
        ]),
    ])
    validated = ValidatedAnalysis(semantic=SemanticAnalysis(affected_functionality="test", evidence_inventory=canonical.evidence_inventory, requirements=[]), requirement_results=[])
    packet = RCAEvidencePacketBuilder().build(canonical, prep, validated, RCARouteDecision(run_rca=True))
    assert [x["fact_id"] for x in packet.diagnostics] == ["D-F1"]
    assert [x["fact_id"] for x in packet.historical] == ["H-F1"]


def test_v189_hypothesis_display_source_references_do_not_invalidate_machine_ids():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    fact_id = prep.evidence_annotations[0].facts[0].fact_id
    validated = ValidatedAnalysis(semantic=SemanticAnalysis(affected_functionality="test", evidence_inventory=canonical.evidence_inventory, requirements=[]), requirement_results=[])
    synthesis = RCASynthesisReasoning(affected_functionality="test", hypotheses=[HypothesisAnalysis(
        hypothesis="Communication interruption candidate",
        support_basis=HypothesisSupportBasis.CURRENT_CASE_MECHANISM_MATCH,
        supporting_evidence_ids=[fact_id],
        source_references=[f"{fact_id} (human readable label)"],
        confidence="LOW",
    )])
    merged = RCAPipeline._merge_v080_rca(validated, canonical, prep, synthesis)
    assert len(merged.hypotheses) == 1


def test_v189_materially_unresolved_requirement_stays_visible_in_rca_packet():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    canonical.semantic_integrity_issues = [SemanticIntegrityIssue(
        issue_id="X", requirement_id="REQ-1701", semantic_id="C1",
        description="trigger incomplete", material_to_compliance=True,
    )]
    validated = ValidatedAnalysis(semantic=SemanticAnalysis(affected_functionality="test", evidence_inventory=canonical.evidence_inventory, requirements=[]), requirement_results=[])
    packet = RCAEvidencePacketBuilder().build(canonical, prep, validated, RCARouteDecision(run_rca=True))
    assert any(x.requirement_id == "REQ-1701" for x in packet.requirement_irs)
    assert packet.unresolved_requirement_context[0]["requirement_id"] == "REQ-1701"


def test_v189_web_reconnect_and_pipeline_tree_state_contracts_are_present():
    js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
    html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    assert "reconcileActiveRuns" in js
    assert "['QUEUED','INITIALIZING','RUNNING','CANCELLING']" in js
    assert "activeRunSelect" in js and 'id="activeRunSelect"' in html
    assert "captureStructuredState" in js
    assert "data-tree-path" in js or "dataset.treePath" in js
    assert "expandedPaths" in js
    assert "persistRunView" in js and "restoreRunView" in js
