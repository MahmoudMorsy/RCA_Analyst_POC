from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from rca_app.case_parser import DeterministicCaseParser
from rca_app.compliance_engine import DeterministicComplianceEngine
from rca_app.intake import IntakeCanonicalizer
from rca_app.models import (
    Applicability,
    EvidenceScopeAnnotation,
    EvidenceSemanticAnnotation,
    EvidenceSemanticFact,
    EvidenceSemanticRole,
    EvaluationStatus,
    LogicExpression,
    LogicKind,
    NormativeType,
    PredicateOperator,
    RCAEvidencePacket,
    RCARouteDecision,
    RequirementBehaviorIR,
    RequirementEventIR,
    RequirementIR,
    RequirementCompilationBatch,
    RequirementStructuralPatch,
    RequirementStructuralPatchBatch,
    EvidenceAnnotationBatch,
    RequirementSemanticFingerprint,
    RequirementSemanticVerificationItem,
    RequirementSemanticVerificationBatch,
    RequirementPersistenceIR,
    RequirementSemanticClause,
    RequirementTimingIR,
    ScopeResolution,
    SemanticClauseRole,
    SemanticArbitrationResponse,
    SemanticPreparation,
    SemanticResolution,
    TemporalSemantics,
    ApiStats,
    RCASynthesisReasoning,
)
from rca_app.lmstudio_client import StructuredResponse
from rca_app.pipeline import RCAPipeline
from rca_app.rca_routing import RCAEvidencePacketBuilder
from rca_app.semantic_ir import SemanticIntegrityChecker


FIX = Path(__file__).resolve().parent / "fixtures" / "v080"


def pred(signal, op, value, semantic_id=""):
    return LogicExpression(kind=LogicKind.PREDICATE, semantic_id=semantic_id, signal=signal, operator=op, value=value)


def behavior(signal, value, *, op=PredicateOperator.EQ, semantic_id="", event=""):
    return RequirementBehaviorIR(semantic_id=semantic_id, signal=signal, operator=op, value=value, event=event)


def trigger(signal, value, semantic_id=""):
    return RequirementEventIR(semantic_id=semantic_id, signal=signal, event="BECOMES", value=value)


def interval_annotation(evidence_id, fact_id, source_phrase, subject, value, related, *, numeric=None):
    return EvidenceSemanticAnnotation(
        evidence_id=evidence_id,
        facts=[EvidenceSemanticFact(
            fact_id=fact_id,
            source_phrase=source_phrase,
            subject=subject,
            operator=PredicateOperator.EQ,
            value=value,
            numeric_value=numeric,
            temporal_semantics=TemporalSemantics.PERSISTENT_STATE,
            scope=EvidenceScopeAnnotation(
                source_phrase="throughout the complete evaluated interval",
                resolution=ScopeResolution.RESOLVED,
                scope_id="EVALUATED_INTERVAL",
            ),
            resolution=SemanticResolution.VERIFIED,
            possible_roles=[EvidenceSemanticRole.APPLICABILITY, EvidenceSemanticRole.RESPONSE],
            related_requirement_ids=related,
        )],
    )


def tc17_preparation(canonical):
    req1 = RequirementIR(
        requirement_id="REQ-1701",
        normative_type=NormativeType.MANDATORY,
        condition=LogicExpression(kind=LogicKind.AND, children=[
            pred("IgnitionState", PredicateOperator.EQ, "ON", "1701-C1"),
            LogicExpression(kind=LogicKind.OR, children=[
                pred("GearPosition", PredicateOperator.EQ, "P", "1701-C2"),
                pred("GearPosition", PredicateOperator.EQ, "N", "1701-C3"),
            ]),
            pred("ServiceMode", PredicateOperator.NEQ, "ACTIVE", "1701-C4"),
        ]),
        required_behavior=behavior("StarterEnable", "TRUE", semantic_id="1701-B1"),
        source_clauses=[
            RequirementSemanticClause(semantic_id="1701-C1", role=SemanticClauseRole.CONDITION, source_phrase="IgnitionState = ON"),
            RequirementSemanticClause(semantic_id="1701-C2", role=SemanticClauseRole.CONDITION, source_phrase="GearPosition = P"),
            RequirementSemanticClause(semantic_id="1701-C3", role=SemanticClauseRole.CONDITION, source_phrase="GearPosition = N"),
            RequirementSemanticClause(semantic_id="1701-C4", role=SemanticClauseRole.CONDITION, source_phrase="ServiceMode is not ACTIVE"),
            RequirementSemanticClause(semantic_id="1701-B1", role=SemanticClauseRole.REQUIRED_BEHAVIOR, source_phrase="StarterEnable shall be TRUE"),
        ],
    )
    req2 = RequirementIR(
        requirement_id="REQ-1702",
        normative_type=NormativeType.MANDATORY,
        condition=pred("BatteryVoltage", PredicateOperator.LT, "9.5 V", "1702-C1"),
        required_behavior=behavior("StarterEnable", "FALSE", semantic_id="1702-B1"),
        source_clauses=[
            RequirementSemanticClause(semantic_id="1702-C1", role=SemanticClauseRole.CONDITION, source_phrase="BatteryVoltage is below 9.5 V"),
            RequirementSemanticClause(semantic_id="1702-B1", role=SemanticClauseRole.REQUIRED_BEHAVIOR, source_phrase="StarterEnable shall be FALSE"),
        ],
    )
    req3 = RequirementIR(
        requirement_id="REQ-1703",
        normative_type=NormativeType.MANDATORY,
        condition=pred("ServiceMode", PredicateOperator.EQ, "ACTIVE", "1703-C1"),
        required_behavior=behavior("StarterEnable", "FALSE", semantic_id="1703-B1"),
        persistence=RequirementPersistenceIR(semantic_id="1703-P1", required=True, scope="WHILE_CONDITION"),
        source_clauses=[
            RequirementSemanticClause(semantic_id="1703-C1", role=SemanticClauseRole.CONDITION, source_phrase="ServiceMode = ACTIVE"),
            RequirementSemanticClause(semantic_id="1703-B1", role=SemanticClauseRole.REQUIRED_BEHAVIOR, source_phrase="StarterEnable shall remain FALSE"),
            RequirementSemanticClause(semantic_id="1703-P1", role=SemanticClauseRole.PERSISTENCE, source_phrase="shall remain FALSE"),
        ],
    )
    by_text = {e.text: e.id for e in canonical.evidence_inventory}
    battery_text = "BatteryVoltage remained 12.2 throughout the complete evaluated interval."
    service_text = "ServiceMode remained INACTIVE throughout the complete evaluated interval."
    return SemanticPreparation(
        affected_functionality="Starter-enable logic",
        requirement_irs=[req1, req2, req3],
        evidence_annotations=[
            interval_annotation(by_text[battery_text], "F-BAT", battery_text, "BatteryVoltage", "12.2", ["REQ-1702"], numeric=12.2),
            interval_annotation(by_text[service_text], "F-SVC", service_text, "ServiceMode", "INACTIVE", ["REQ-1701", "REQ-1703"]),
        ],
    )


def tc12_preparation(canonical):
    irs = [
        RequirementIR(requirement_id="REQ-1201", normative_type=NormativeType.MANDATORY,
                      condition=pred("IgnitionState", PredicateOperator.EQ, "ON"),
                      required_behavior=behavior("CentralLockStatus", "READY")),
        RequirementIR(requirement_id="REQ-1202", normative_type=NormativeType.PROHIBITIVE,
                      condition=pred("VehicleSpeed", PredicateOperator.GT, "0"),
                      required_behavior=behavior("TailgateRequest", "OPEN", op=PredicateOperator.NEQ)),
        RequirementIR(requirement_id="REQ-1203", normative_type=NormativeType.MANDATORY,
                      trigger=trigger("DriverDoorRequest", "OPEN"),
                      required_behavior=behavior("DriverDoorStatus", "OPEN", event="BECOMES"),
                      timing=RequirementTimingIR(limit_ms=300)),
        RequirementIR(requirement_id="REQ-1204", normative_type=NormativeType.MANDATORY,
                      trigger=trigger("TailgateRequest", "OPEN"),
                      required_behavior=behavior("TailgateStatus", "OPEN", event="BECOMES"),
                      timing=RequirementTimingIR(limit_ms=800)),
        RequirementIR(requirement_id="REQ-1205", normative_type=NormativeType.MANDATORY,
                      trigger=trigger("RearLeftDoorRequest", "OPEN"),
                      required_behavior=behavior("RearLeftDoorStatus", "OPEN", event="BECOMES"),
                      timing=RequirementTimingIR(limit_ms=300)),
        RequirementIR(requirement_id="REQ-1206", normative_type=NormativeType.MANDATORY,
                      condition=LogicExpression(kind=LogicKind.AND, children=[
                          pred("ActiveVariant", PredicateOperator.EQ, "MANUAL"),
                          pred("VehicleSpeed", PredicateOperator.GT, "0"),
                      ]),
                      required_behavior=behavior("TailgateStatus", "CLOSED"),
                      persistence=RequirementPersistenceIR(required=True, scope="WHILE_CONDITION")),
        RequirementIR(requirement_id="REQ-1207", normative_type=NormativeType.MANDATORY,
                      condition=pred("ActiveVariant", PredicateOperator.EQ, "POWER"),
                      required_behavior=behavior("TailgateMotorAvailability", "AVAILABLE")),
        RequirementIR(requirement_id="REQ-1208", normative_type=NormativeType.MANDATORY,
                      condition=pred("ChildLockState", PredicateOperator.EQ, "ON"),
                      required_behavior=behavior("RearRightDoorStatus", "CLOSED"),
                      persistence=RequirementPersistenceIR(required=True, scope="WHILE_CONDITION")),
        RequirementIR(requirement_id="REQ-1209", normative_type=NormativeType.MANDATORY,
                      trigger=trigger("BonnetRequest", "OPEN"),
                      required_behavior=behavior("BonnetStatus", "OPEN", event="BECOMES"),
                      timing=RequirementTimingIR(limit_ms=500)),
        RequirementIR(requirement_id="REQ-1210", normative_type=NormativeType.MANDATORY,
                      trigger=trigger("ComfortClosing", "ACTIVE"),
                      required_behavior=behavior("WindowStatus", "CLOSED", event="BECOMES"),
                      timing=RequirementTimingIR(limit_ms=2000)),
    ]
    by_text = {e.text: e.id for e in canonical.evidence_inventory}
    data = [
        ("IgnitionState remained ON throughout the complete evaluated interval.", "IgnitionState", "ON", ["REQ-1201"], None),
        ("ActiveVariant remained POWER throughout the complete evaluated interval.", "ActiveVariant", "POWER", ["REQ-1206", "REQ-1207"], None),
        ("VehicleSpeed remained 0 throughout the complete evaluated interval.", "VehicleSpeed", "0", ["REQ-1202", "REQ-1206"], 0.0),
        ("TailgateMotorAvailability remained AVAILABLE throughout the complete evaluated interval.", "TailgateMotorAvailability", "AVAILABLE", ["REQ-1207"], None),
    ]
    anns = [interval_annotation(by_text[text], f"F-{i}", text, signal, value, rel, numeric=num)
            for i, (text, signal, value, rel, num) in enumerate(data, 1)]
    return SemanticPreparation(affected_functionality="Power tailgate", requirement_irs=irs, evidence_annotations=anns)




def split_semantic_preparation(prep: SemanticPreparation):
    return (
        RequirementCompilationBatch(
            affected_functionality=prep.affected_functionality,
            requirement_irs=[x.model_copy(deep=True) for x in prep.requirement_irs],
            unresolved_case_semantics=list(prep.unresolved_case_semantics),
        ),
        EvidenceAnnotationBatch(
            evidence_annotations=[x.model_copy(deep=True) for x in prep.evidence_annotations],
            unresolved_case_semantics=[],
        ),
    )

def result_map(validated):
    return {x.analysis.requirement_id: x for x in validated.requirement_results}


def verification_fingerprint_from_ir(ir):
    return RequirementSemanticFingerprint(
        normative_type=ir.normative_type,
        condition=copy.deepcopy(ir.condition),
        trigger=copy.deepcopy(ir.trigger),
        required_behavior=copy.deepcopy(ir.required_behavior),
        timing=copy.deepcopy(ir.timing),
        persistence=copy.deepcopy(ir.persistence),
        relationships=copy.deepcopy(ir.relationships),
    )


def verified_semantic_verification(canonical, source_preparation):
    by_id = {x.requirement_id: x for x in source_preparation.requirement_irs}
    return RequirementSemanticVerificationBatch(requirements=[
        RequirementSemanticVerificationItem(
            requirement_id=req.requirement_id,
            resolution=SemanticResolution.VERIFIED,
            independent_semantics=verification_fingerprint_from_ir(by_id[req.requirement_id]),
        )
        for req in canonical.requirements
    ])


def mismatch_semantic_verification(canonical, source_preparation, requirement_id, source_span):
    by_id = {x.requirement_id: x for x in source_preparation.requirement_irs}
    items = []
    for req in canonical.requirements:
        kwargs = dict(
            requirement_id=req.requirement_id,
            independent_semantics=verification_fingerprint_from_ir(by_id[req.requirement_id]),
        )
        if req.requirement_id == requirement_id:
            items.append(RequirementSemanticVerificationItem(
                **kwargs,
                resolution=SemanticResolution.PARTIALLY_RESOLVED,
                missing_or_misrepresented_source_spans=[source_span],
            ))
        else:
            items.append(RequirementSemanticVerificationItem(**kwargs, resolution=SemanticResolution.VERIFIED))
    return RequirementSemanticVerificationBatch(requirements=items)


def test_v080_decimal_timestamps_are_not_stripped_as_numbered_list_prefixes():
    assert IntakeCanonicalizer._strip_label("99.900 s TailgateRequest = CLOSED") == "99.900 s TailgateRequest = CLOSED"
    assert IntakeCanonicalizer._strip_label("100.000 s TailgateRequest = OPEN") == "100.000 s TailgateRequest = OPEN"
    assert IntakeCanonicalizer._strip_label("1. Set IgnitionState to ON.") == "Set IgnitionState to ON."


def test_v080_production_parser_leaves_human_interval_language_unexecuted():
    raw = (FIX / "TEST-012.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    item = next(e for e in canonical.evidence_inventory if e.text.startswith("IgnitionState remained ON"))
    assert item.observation_type.value == "UNSPECIFIED"
    assert item.signal_name == ""
    timestamps = [(e.signal_name, e.timestamp_seconds) for e in canonical.evidence_inventory if e.timestamp_seconds is not None]
    assert ("TailgateRequest", 99.9) in timestamps
    assert ("TailgateRequest", 100.0) in timestamps
    assert ("TailgateStatus", 100.6) in timestamps
    assert ("TailgateStatus", 101.1) in timestamps


def test_v080_integrity_checker_detects_tc17_style_dropped_clause_without_reading_language():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    # Compiler self-audit says it identified 3 condition clauses, but AST only
    # maps two semantic IDs. Python catches the structural omission without
    # interpreting the German/English sentence itself.
    bad = RequirementIR(
        requirement_id="REQ-1701",
        normative_type=NormativeType.MANDATORY,
        condition=LogicExpression(kind=LogicKind.AND, children=[
            pred("IgnitionState", PredicateOperator.EQ, "ON", "C1"),
            pred("GearPosition", PredicateOperator.EQ, "N", "C2"),
        ]),
        required_behavior=behavior("StarterEnable", "TRUE", semantic_id="B1"),
        source_clauses=[
            RequirementSemanticClause(semantic_id="C1", role=SemanticClauseRole.CONDITION, source_phrase="IgnitionState = ON"),
            RequirementSemanticClause(semantic_id="C2", role=SemanticClauseRole.CONDITION, source_phrase="GearPosition = N"),
            RequirementSemanticClause(semantic_id="C3", role=SemanticClauseRole.CONDITION, source_phrase="ServiceMode is not ACTIVE"),
            RequirementSemanticClause(semantic_id="B1", role=SemanticClauseRole.REQUIRED_BEHAVIOR, source_phrase="StarterEnable shall be TRUE"),
        ],
    )
    # Supply valid placeholders for other authoritative requirements so the
    # assertion isolates the dropped-clause defect.
    good = tc17_preparation(canonical)
    prep = good.model_copy(deep=True)
    prep.requirement_irs[0] = bad
    issues = SemanticIntegrityChecker.validate(canonical, prep)
    assert any(i.requirement_id == "REQ-1701" and i.semantic_id == "C3" and i.material_to_compliance for i in issues)


def test_v080_tc17_exact_fixture_is_deterministically_violated_and_overrides_are_not_applicable():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    validated = DeterministicComplianceEngine().evaluate(canonical, prep, [])
    r = result_map(validated)
    assert r["REQ-1701"].analysis.applicability == Applicability.APPLICABLE
    assert r["REQ-1701"].evaluation_status == EvaluationStatus.VIOLATED
    assert r["REQ-1702"].analysis.applicability == Applicability.NOT_APPLICABLE
    assert r["REQ-1702"].evaluation_status == EvaluationStatus.NO_COMPLIANCE_VERDICT
    assert r["REQ-1703"].analysis.applicability == Applicability.NOT_APPLICABLE
    assert r["REQ-1703"].evaluation_status == EvaluationStatus.NO_COMPLIANCE_VERDICT


def test_v080_tc12_exact_fixture_computes_1100_vs_800_violation():
    raw = (FIX / "TEST-012.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc12_preparation(canonical)
    validated = DeterministicComplianceEngine().evaluate(canonical, prep, [])
    r = result_map(validated)
    assert r["REQ-1201"].analysis.applicability == Applicability.APPLICABLE
    assert r["REQ-1201"].evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert r["REQ-1202"].analysis.applicability == Applicability.NOT_APPLICABLE
    assert r["REQ-1204"].analysis.applicability == Applicability.APPLICABLE
    assert r["REQ-1204"].evaluation_status == EvaluationStatus.VIOLATED
    tf = r["REQ-1204"].timing_fact
    assert tf is not None
    assert round(tf.elapsed_ms) == 1100
    assert round(tf.limit_ms) == 800
    assert round(tf.margin_ms) == 300
    assert r["REQ-1206"].analysis.applicability == Applicability.NOT_APPLICABLE
    assert r["REQ-1207"].analysis.applicability == Applicability.APPLICABLE
    assert r["REQ-1207"].evaluation_status == EvaluationStatus.SATISFIED


def test_v080_rca_packet_does_not_resend_original_requirement_wording():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    validated = DeterministicComplianceEngine().evaluate(canonical, prep, [])
    route = RCARouteDecision(run_rca=True, reasons=["test"], supporting_evidence_ids=[])
    packet = RCAEvidencePacketBuilder().build(canonical, prep, validated, route)
    dumped = json.dumps(packet.model_dump(mode="json"), ensure_ascii=False)
    assert "Wenn IgnitionState" not in dumped
    assert "requirement_text" not in dumped
    assert packet.selected_source_excerpts == []


def test_v081_null_optional_behavior_event_normalizes_to_empty_string():
    obj = RequirementBehaviorIR.model_validate({
        "semantic_id": "B1",
        "signal": "CentralLockStatus",
        "operator": "EQ",
        "value": "READY",
        "event": None,
        "process_description": "CentralLockStatus shall be READY",
    })
    assert obj.event == ""


def test_v081_tc12_semantic_preparation_is_bounded_for_8k_fast_context():
    raw = (FIX / "TEST-012.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    batches = RCAPipeline._semantic_requirement_batches(canonical)
    assert [[x.requirement_id for x in b] for b in batches] == [
        ["REQ-1201", "REQ-1202", "REQ-1203", "REQ-1204", "REQ-1205"],
        ["REQ-1206", "REQ-1207", "REQ-1208", "REQ-1209", "REQ-1210"],
    ]
    assert len(RCAPipeline._semantic_preparation_user_prompt(canonical)) > 5000
    assert all(len(RCAPipeline._semantic_requirement_batch_prompt(canonical, b)) < 5000 for b in batches)


def test_v081_independent_verifier_flags_silent_condition_omission():
    raw = (FIX / "TEST-012.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    source_prep = tc12_preparation(canonical)
    verification = mismatch_semantic_verification(canonical, source_prep, "REQ-1201", "If IgnitionState is ON")
    issues = RCAPipeline._semantic_verification_issues(canonical, source_prep, verification)
    assert len(issues) == 1
    assert issues[0].requirement_id == "REQ-1201"
    assert issues[0].material_to_compliance is True


class FakeStructuredClient:
    def __init__(self, responses, model="fake"):
        self.responses = list(responses)
        self.calls = 0
        self.model = model

    def _next(self):
        if self.calls >= len(self.responses):
            raise AssertionError("Unexpected model call")
        obj = self.responses[self.calls]
        self.calls += 1
        return StructuredResponse(
            parsed=obj,
            raw_json=json.dumps(obj.model_dump(mode="json")),
            stats=ApiStats(elapsed_seconds=0.01, model=self.model),
        )

    def structured_repair(self, **kwargs):
        return self._next()

    def structured_chat(self, **kwargs):
        return self._next()


def test_v080_clean_tc17_pipeline_uses_one_semantic_prep_and_zero_27b_calls():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    assert not SemanticIntegrityChecker.material_issues(SemanticIntegrityChecker.validate(canonical, prep))
    req_batch, ev_batch = split_semantic_preparation(prep)
    fast = FakeStructuredClient([req_batch, ev_batch, verified_semantic_verification(canonical, prep)], model="4b")
    primary = FakeStructuredClient([], model="27b")
    pipeline = RCAPipeline(
        primary,
        semantic_preparation_client=fast,
        semantic_preparation_enabled=True,
        semantic_arbitration_client=primary,
        semantic_arbitration_enabled=True,
        rca_synthesis_enabled=True,
        fast_intake_enabled=False,
        fast_hypothesis_review_enabled=False,
        fast_final_review_enabled=False,
    )
    result = pipeline.run(raw)
    assert fast.calls == 3
    assert primary.calls == 0
    assert result.rca_route_decision is not None and result.rca_route_decision.run_rca is False
    assert result_map(result.validated)["REQ-1701"].evaluation_status == EvaluationStatus.VIOLATED


def test_v080_material_semantic_defect_triggers_exactly_one_batched_27b_arbitration():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    clean = tc17_preparation(canonical)
    bad = clean.model_copy(deep=True)
    # Drop ServiceMode predicate but retain the compiler audit clause, reproducing
    # the live v0.7.1 failure pattern.
    bad.requirement_irs[0].condition.children = bad.requirement_irs[0].condition.children[:2]
    repaired_req = clean.requirement_irs[0].model_copy(deep=True)
    arbitration = SemanticArbitrationResponse(requirement_irs=[repaired_req])
    bad_req_batch, bad_ev_batch = split_semantic_preparation(bad)
    fast = FakeStructuredClient([
        bad_req_batch,
        bad_ev_batch,
        mismatch_semantic_verification(canonical, clean, "REQ-1701", "ServiceMode is not ACTIVE"),
        verified_semantic_verification(canonical, clean),
    ], model="4b")
    primary = FakeStructuredClient([arbitration], model="27b")
    pipeline = RCAPipeline(
        primary,
        semantic_preparation_client=fast,
        semantic_preparation_enabled=True,
        semantic_arbitration_client=primary,
        semantic_arbitration_enabled=True,
        rca_synthesis_enabled=True,
        fast_intake_enabled=False,
        fast_hypothesis_review_enabled=False,
        fast_final_review_enabled=False,
    )
    result = pipeline.run(raw)
    assert fast.calls == 4
    assert primary.calls == 1
    assert result.semantic_arbitration is not None
    assert result.rca_route_decision is not None and result.rca_route_decision.run_rca is False
    assert result_map(result.validated)["REQ-1701"].evaluation_status == EvaluationStatus.VIOLATED


def test_v082_rca_context_or_output_symptom_does_not_trigger_27b_rca():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    # v0.8.0 live TC17 was incorrectly routed to deep RCA because a model
    # labelled contextual/symptom evidence as RCA_CONTEXT/DIAGNOSTIC. Neither
    # is positive mechanism evidence.
    prep.evidence_annotations[0].facts[0].possible_roles.append(EvidenceSemanticRole.RCA_CONTEXT)
    direct = next(e for e in canonical.evidence_inventory if e.signal_name == "StarterEnable")
    prep.evidence_annotations.append(EvidenceSemanticAnnotation(
        evidence_id=direct.id,
        facts=[EvidenceSemanticFact(
            fact_id="SYM-STARTER", source_phrase=direct.text, subject="StarterEnable",
            operator=PredicateOperator.EQ, value="FALSE", temporal_semantics=TemporalSemantics.POINT_STATE,
            scope=EvidenceScopeAnnotation(resolution=ScopeResolution.RESOLVED),
            resolution=SemanticResolution.VERIFIED,
            possible_roles=[EvidenceSemanticRole.DIAGNOSTIC, EvidenceSemanticRole.RCA_CONTEXT],
            related_requirement_ids=["REQ-1701"],
        )],
    ))
    req_batch, ev_batch = split_semantic_preparation(prep)
    fast = FakeStructuredClient([req_batch, ev_batch, verified_semantic_verification(canonical, prep)], model="4b")
    primary = FakeStructuredClient([], model="27b")
    pipeline = RCAPipeline(
        primary, semantic_preparation_client=fast, semantic_preparation_enabled=True,
        semantic_arbitration_client=primary, semantic_arbitration_enabled=True,
        rca_synthesis_enabled=True, fast_intake_enabled=False,
        fast_hypothesis_review_enabled=False, fast_final_review_enabled=False,
    )
    result = pipeline.run(raw)
    assert fast.calls == 3
    assert primary.calls == 0
    assert result.rca_route_decision is not None and result.rca_route_decision.run_rca is False
    assert result_map(result.validated)["REQ-1701"].evaluation_status == EvaluationStatus.VIOLATED


def test_v082_explicit_mechanism_role_can_trigger_one_27b_rca_call():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    prep.evidence_annotations[0].facts[0].possible_roles.append(EvidenceSemanticRole.MECHANISM)
    synthesis = RCASynthesisReasoning(
        affected_functionality="Starter-enable logic", historical_tickets=[],
        diagnostic_evidence_ids=[], hypotheses=[], case_validity_needs=[],
    )
    req_batch, ev_batch = split_semantic_preparation(prep)
    fast = FakeStructuredClient([req_batch, ev_batch, verified_semantic_verification(canonical, prep)], model="4b")
    primary = FakeStructuredClient([synthesis], model="27b")
    pipeline = RCAPipeline(
        primary, semantic_preparation_client=fast, semantic_preparation_enabled=True,
        semantic_arbitration_client=primary, semantic_arbitration_enabled=True,
        rca_synthesis_enabled=True, fast_intake_enabled=False,
        fast_hypothesis_review_enabled=False, fast_final_review_enabled=False,
    )
    result = pipeline.run(raw)
    assert primary.calls == 1
    assert result.rca_route_decision is not None and result.rca_route_decision.run_rca is True
    assert result.rca_evidence_packet is not None
    dumped = json.dumps(result.rca_evidence_packet.model_dump(mode="json"), ensure_ascii=False)
    assert "Wenn IgnitionState" not in dumped


def test_v082_arbitration_rejects_prose_only_pseudo_repair_ir():
    pseudo = RequirementIR(
        requirement_id="REQ-1701",
        normative_type=NormativeType.AMBIGUOUS,
        source_clauses=[RequirementSemanticClause(
            semantic_id="REQ-1701-COND", role=SemanticClauseRole.CONDITION,
            source_phrase="Wenn IgnitionState = ON",
            resolution=SemanticResolution.PARTIALLY_RESOLVED,
            notes="Understood in prose but not materialized into the AST.",
        )],
    )
    with pytest.raises(ValueError):
        SemanticArbitrationResponse(requirement_irs=[pseudo])


def test_v083_transport_partial_predicate_is_preserved_then_blocked_by_integrity():
    partial = RequirementIR(
        requirement_id="REQ-X",
        normative_type=NormativeType.MANDATORY,
        condition=LogicExpression(
            kind=LogicKind.PREDICATE,
            semantic_id="REQ-X-C1",
            source_phrase="ActiveVariant is POWER",
            signal="",
            operator=PredicateOperator.EQ,
            value="POWER",
        ),
        required_behavior=behavior("TailgateMotorAvailability", "AVAILABLE", semantic_id="REQ-X-B1"),
        source_clauses=[
            RequirementSemanticClause(
                semantic_id="REQ-X-C1", role=SemanticClauseRole.CONDITION,
                source_phrase="ActiveVariant is POWER", resolution=SemanticResolution.VERIFIED,
            ),
            RequirementSemanticClause(
                semantic_id="REQ-X-B1", role=SemanticClauseRole.REQUIRED_BEHAVIOR,
                source_phrase="TailgateMotorAvailability shall be AVAILABLE", resolution=SemanticResolution.VERIFIED,
            ),
        ],
    )
    prep = SemanticPreparation(requirement_irs=[partial])
    issues = SemanticIntegrityChecker.structural_requirement_issues(prep)
    assert len(issues) == 1
    assert issues[0].requirement_id == "REQ-X"
    assert "missing signal" in issues[0].description
    assert issues[0].material_to_compliance is True


def test_v083_arbitration_still_rejects_transport_partial_predicate():
    partial = RequirementIR(
        requirement_id="REQ-X",
        normative_type=NormativeType.MANDATORY,
        condition=LogicExpression(
            kind=LogicKind.PREDICATE,
            semantic_id="REQ-X-C1",
            source_phrase="ActiveVariant is POWER",
            signal="",
            operator=PredicateOperator.EQ,
            value="POWER",
        ),
        required_behavior=behavior("TailgateMotorAvailability", "AVAILABLE", semantic_id="REQ-X-B1"),
        source_clauses=[
            RequirementSemanticClause(
                semantic_id="REQ-X-C1", role=SemanticClauseRole.CONDITION,
                source_phrase="ActiveVariant is POWER", resolution=SemanticResolution.VERIFIED,
            ),
            RequirementSemanticClause(
                semantic_id="REQ-X-B1", role=SemanticClauseRole.REQUIRED_BEHAVIOR,
                source_phrase="TailgateMotorAvailability shall be AVAILABLE", resolution=SemanticResolution.VERIFIED,
            ),
        ],
    )
    with pytest.raises(ValueError, match="PREDICATE without signal"):
        SemanticArbitrationResponse(requirement_irs=[partial])


def test_v083_structural_completion_uses_fast_recompile_before_27b():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    clean = tc17_preparation(canonical)
    bad = clean.model_copy(deep=True)
    bad.requirement_irs[0].condition.children[0].signal = ""

    repaired_batch = RequirementStructuralPatchBatch(patches=[
        RequirementStructuralPatch(
            requirement_id="REQ-1701",
            condition=clean.requirement_irs[0].condition.model_copy(deep=True),
        )
    ])
    bad_req_batch, bad_ev_batch = split_semantic_preparation(bad)
    fast = FakeStructuredClient([
        bad_req_batch,
        repaired_batch,
        bad_ev_batch,
        verified_semantic_verification(canonical, clean),
    ], model="4b")
    primary = FakeStructuredClient([], model="27b")
    pipeline = RCAPipeline(
        primary,
        semantic_preparation_client=fast,
        semantic_preparation_enabled=True,
        semantic_arbitration_client=primary,
        semantic_arbitration_enabled=True,
        rca_synthesis_enabled=True,
        fast_intake_enabled=False,
        fast_hypothesis_review_enabled=False,
        fast_final_review_enabled=False,
    )
    result = pipeline.run(raw)
    assert fast.calls == 4
    assert primary.calls == 0
    assert result.semantic_arbitration is None
    assert result_map(result.validated)["REQ-1701"].evaluation_status == EvaluationStatus.VIOLATED
    assert result.semantic_preparation is not None
    assert not SemanticIntegrityChecker.structural_requirement_issues(result.semantic_preparation)


def test_v084_tc17_malformed_evidence_envelope_is_transport_normalized_without_semantic_inference():
    payload = json.loads((Path(__file__).resolve().parent / "fixtures" / "v084" / "TC17_v082_malformed_evidence_annotation.json").read_text(encoding="utf-8"))
    ann = EvidenceSemanticAnnotation.model_validate(payload)
    assert ann.resolution == SemanticResolution.VERIFIED
    assert len(ann.facts) == 1
    assert ann.facts[0].subject == "BatteryVoltage"
    assert ann.facts[0].scope.scope_id == "CASE_EVALUATED_INTERVAL"
    assert ann.unresolved_semantics == []


def test_v084_nonempty_annotation_level_scope_is_not_assigned_to_fact_by_python():
    payload = {
        "evidence_id": "EVID-X",
        "resolution": {
            "facts": [
                {
                    "fact_id": "F1",
                    "source_phrase": "Signal stayed ON.",
                    "subject": "Signal",
                    "operator": "EQ",
                    "value": "ON",
                    "temporal_semantics": "PERSISTENT_STATE",
                    "scope": {"resolution": "UNRESOLVED", "scope_id": ""},
                    "resolution": "VERIFIED",
                }
            ],
            "unresolved_semantics": [],
        },
        "scope_id": "SOME_TOP_LEVEL_SCOPE",
    }
    ann = EvidenceSemanticAnnotation.model_validate(payload)
    assert ann.resolution == SemanticResolution.PARTIALLY_RESOLVED
    assert ann.facts[0].scope.scope_id == ""
    assert any("Unassigned annotation-level scope_id" in x for x in ann.unresolved_semantics)


def test_v084_persistent_resolved_scope_requires_concrete_scope_id_before_execution():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    battery = prep.evidence_annotations[0]
    battery.facts[0].scope.scope_id = ""

    structural = SemanticIntegrityChecker.structural_evidence_issues(prep)
    assert any(x.evidence_id == battery.evidence_id and "no concrete scope_id" in x.description for x in structural)

    # Even if the semantic-integrity list were accidentally omitted, the
    # compliance engine itself must not promote the persistent prose into an
    # INTERVAL_STATE without a concrete scope identifier.
    validated = DeterministicComplianceEngine().evaluate(canonical, prep, [])
    r = result_map(validated)
    assert r["REQ-1702"].analysis.applicability == Applicability.UNKNOWN
    assert r["REQ-1702"].evaluation_status == EvaluationStatus.NOT_EVALUABLE


def test_v084_arbitration_rejects_persistent_evidence_repair_without_scope_id():
    ann = EvidenceSemanticAnnotation(
        evidence_id="EVID-X",
        facts=[EvidenceSemanticFact(
            fact_id="F1",
            source_phrase="Signal remained ON throughout the interval.",
            subject="Signal",
            operator=PredicateOperator.EQ,
            value="ON",
            temporal_semantics=TemporalSemantics.PERSISTENT_STATE,
            scope=EvidenceScopeAnnotation(
                source_phrase="throughout the interval",
                resolution=ScopeResolution.RESOLVED,
                scope_id="",
            ),
            resolution=SemanticResolution.VERIFIED,
        )],
    )
    with pytest.raises(ValueError, match="concrete resolved scope_id"):
        SemanticArbitrationResponse(evidence_annotations=[ann])


def test_v084_small_case_pipeline_always_splits_requirement_and_evidence_calls():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    req_batch, ev_batch = split_semantic_preparation(prep)
    fast = FakeStructuredClient([req_batch, ev_batch, verified_semantic_verification(canonical, prep)], model="4b")
    primary = FakeStructuredClient([], model="27b")
    pipeline = RCAPipeline(
        primary,
        semantic_preparation_client=fast,
        semantic_preparation_enabled=True,
        semantic_arbitration_client=primary,
        semantic_arbitration_enabled=True,
        rca_synthesis_enabled=False,
        fast_intake_enabled=False,
        fast_hypothesis_review_enabled=False,
        fast_final_review_enabled=False,
    )
    result = pipeline.run(raw)
    stages = [x.stage for x in result.attempts]
    assert stages[:3] == [
        "semantic_preparation_requirements_1",
        "semantic_preparation_evidence",
        "semantic_verification",
    ]
    assert "semantic_preparation" not in stages
    assert fast.calls == 3
    assert primary.calls == 0


def test_v084_targeted_evidence_completion_repairs_scope_without_recompiling_requirements():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    clean = tc17_preparation(canonical)
    bad = clean.model_copy(deep=True)
    bad.evidence_annotations[0].facts[0].scope.scope_id = ""

    bad_req_batch, bad_ev_batch = split_semantic_preparation(bad)
    repaired_ev = EvidenceAnnotationBatch(
        evidence_annotations=[clean.evidence_annotations[0].model_copy(deep=True)]
    )
    fast = FakeStructuredClient([
        bad_req_batch,
        bad_ev_batch,
        repaired_ev,
        verified_semantic_verification(canonical, clean),
    ], model="4b")
    primary = FakeStructuredClient([], model="27b")
    pipeline = RCAPipeline(
        primary,
        semantic_preparation_client=fast,
        semantic_preparation_enabled=True,
        semantic_arbitration_client=primary,
        semantic_arbitration_enabled=True,
        rca_synthesis_enabled=False,
        fast_intake_enabled=False,
        fast_hypothesis_review_enabled=False,
        fast_final_review_enabled=False,
    )
    result = pipeline.run(raw)
    stages = [x.stage for x in result.attempts]
    assert stages.count("semantic_preparation_requirements_1") == 1
    assert stages.count("semantic_preparation_evidence") == 1
    assert stages.count("semantic_evidence_completion") == 1
    assert fast.calls == 4
    assert primary.calls == 0
    assert result_map(result.validated)["REQ-1702"].analysis.applicability == Applicability.NOT_APPLICABLE


def test_v084_release_docs_are_packaged_in_source_tree():
    root = Path(__file__).resolve().parent.parent
    assert (root / "docs" / "ARCHITECTURE.md").exists()
    assert (root / "docs" / "V0.8.4_RELEASE_NOTES.md").exists()
    assert (root / "VERSION_HISTORY.md").exists()
    assert (root / "CHANGELOG.md").exists()
    history = (root / "VERSION_HISTORY.md").read_text(encoding="utf-8")
    assert "## v0.8.3 → v0.8.4" in history
    assert "Current release — v1.8.11" in history


def test_v085_verifier_structured_fingerprint_catches_live_tc17_boolean_regrouping_even_when_marked_verified():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    source = tc17_preparation(canonical)
    candidate = source.model_copy(deep=True)
    # Exact live failure shape: source A AND (B OR C) AND D was compiled as
    # A AND [B AND (C OR D)].  Prose looked correct and the old verifier said VERIFIED.
    a, or_bc, d = source.requirement_irs[0].condition.children
    b, c = or_bc.children
    candidate.requirement_irs[0].condition = LogicExpression(
        kind=LogicKind.AND,
        children=[
            copy.deepcopy(a),
            LogicExpression(
                kind=LogicKind.AND,
                children=[
                    copy.deepcopy(b),
                    LogicExpression(kind=LogicKind.OR, children=[copy.deepcopy(c), copy.deepcopy(d)]),
                ],
            ),
        ],
    )
    verification = verified_semantic_verification(canonical, source)
    # Intentionally keep resolution VERIFIED to prove Python compares the
    # independent structured reconstruction, not the verifier's label/prose.
    issues = RCAPipeline._semantic_verification_issues(canonical, candidate, verification)
    req1 = [x for x in issues if x.requirement_id == "REQ-1701"]
    assert len(req1) == 1
    assert "condition" in req1[0].description
    assert req1[0].material_to_compliance is True


def test_v085_arbitration_rejects_live_tc17_notes_only_compliance_evidence_pseudo_repair():
    ann = EvidenceSemanticAnnotation(
        evidence_id="EVID-TC17",
        resolution=SemanticResolution.VERIFIED,
        facts=[EvidenceSemanticFact(
            fact_id="F-TC17",
            source_phrase="ServiceMode remained INACTIVE throughout the complete evaluated interval.",
            subject="",
            operator=PredicateOperator.OTHER,
            value="",
            temporal_semantics=TemporalSemantics.OTHER,
            scope=EvidenceScopeAnnotation(resolution=ScopeResolution.UNRESOLVED),
            resolution=SemanticResolution.VERIFIED,
            possible_roles=[EvidenceSemanticRole.APPLICABILITY],
            related_requirement_ids=["REQ-1701"],
            notes="ServiceMode is INACTIVE for the evaluated interval, therefore the condition is satisfied.",
        )],
    )
    with pytest.raises(ValueError, match="temporal_semantics=OTHER"):
        SemanticArbitrationResponse(evidence_annotations=[ann])


def test_v085_evidence_prompt_constrains_live_invalid_operator_words_without_python_nlp_mapping():
    from rca_app.prompts import EVIDENCE_ANNOTATION_V085_PROMPT
    prompt = EVIDENCE_ANNOTATION_V085_PROMPT
    for allowed in ("EQ", "NEQ", "LT", "LTE", "GT", "GTE", "PRESENT", "ABSENT", "OTHER"):
        assert allowed in prompt
    for rejected in ("HAS", "REACHES", "WAS", "CONTAINS"):
        assert rejected in prompt
