from __future__ import annotations

import json
import time
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from rca_app.case_parser import DeterministicCaseParser
from rca_app.models import (
    EvidenceAnnotationBatch,
    EvidenceScopeAnnotation,
    EvidenceSemanticAnnotation,
    EvidenceSemanticFact,
    HypothesisAnalysis,
    HypothesisSupportBasis,
    PredicateOperator,
    RCASynthesisReasoning,
    RequirementCompilationBatch,
    RequirementSemanticClause,
    RequirementStructuralPatch,
    RequirementStructuralPatchBatch,
    SemanticAnalysis,
    SemanticPreparation,
    SemanticResolution,
    ScopeResolution,
    TemporalSemantics,
    ValidatedAnalysis,
    ValidationIssue,
    ValidationSeverity,
)
from rca_app.pipeline import RCAPipeline
from rca_app.prompts import (
    REQUIREMENT_COMPILATION_V086_PROMPT,
    REQUIREMENT_SEMANTIC_VERIFICATION_PROMPT,
    REQUIREMENT_STRUCTURAL_COMPLETION_V086_PROMPT,
)
from rca_app.semantic_ir import SemanticIntegrityChecker
from rca_app.test_bundle import evaluate_semantic_acceptance
from rca_server.app import create_app
from tests.test_v080 import (
    FIX,
    FakeStructuredClient,
    split_semantic_preparation,
    tc17_preparation,
    verified_semantic_verification,
)
from tests.test_web_backend import make_stack, wait_terminal


def test_v188_source_grounding_accepts_layout_bullets_and_explicit_ellipsis_only():
    source = (
        "Before test:\n- DTC C101 Low supply voltage was present.\n"
        "- DTC U2200 Brake booster communication timeout was not present.\n"
        "After failure:\n- DTC U2200 Brake booster communication timeout was present."
    )
    assert SemanticIntegrityChecker._span_supported(
        source, "Before test: DTC C101 Low supply voltage was present"
    )
    assert SemanticIntegrityChecker._span_supported(
        source,
        "Before test ... DTC U2200 Brake booster communication timeout was not present",
    )
    assert not SemanticIntegrityChecker._span_supported(
        source, "FunctionStatus became ACTIVE within approximately 250 ms"
    )


def test_v188_narrative_related_requirement_id_does_not_become_material_by_signal_or_link_alone():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    # Add an unresolved ticket-description fact and explicitly link it to
    # REQ-1701. CURRENT_TICKET narrative still must not block deterministic
    # compliance unless it is explicit scope metadata or carries a material
    # semantic role.
    prep.evidence_annotations.append(EvidenceSemanticAnnotation(
        evidence_id="EVID-DESCRIPTION",
        resolution=SemanticResolution.PARTIALLY_RESOLVED,
        facts=[EvidenceSemanticFact(
            fact_id="FACT-DESC-MATERIALITY",
            source_phrase="StarterEnable is FALSE",
            subject="StarterEnable",
            operator=PredicateOperator.EQ,
            value="FALSE",
            temporal_semantics=TemporalSemantics.POINT_STATE,
            scope=EvidenceScopeAnnotation(resolution=ScopeResolution.NOT_APPLICABLE),
            resolution=SemanticResolution.UNRESOLVED,
            related_requirement_ids=["REQ-1701"],
        )],
    ))
    issues = SemanticIntegrityChecker.material_issues(
        SemanticIntegrityChecker.validate(canonical, prep)
    )
    assert not any(x.evidence_id == "EVID-DESCRIPTION" for x in issues)


def test_v188_structural_completion_can_replace_complete_source_clause_inventory():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    clean = tc17_preparation(canonical)
    prep = clean.model_copy(deep=True)
    prep.requirement_irs[0].source_clauses = []
    issues = SemanticIntegrityChecker.structural_requirement_issues(prep)
    targets = RCAPipeline._structural_completion_targets(prep, issues)
    assert "source_clauses" in targets["REQ-1701"]

    patch = RequirementStructuralPatch(
        requirement_id="REQ-1701",
        source_clauses=[x.model_copy(deep=True) for x in clean.requirement_irs[0].source_clauses],
    )
    batch = RequirementStructuralPatchBatch(patches=[patch])
    RCAPipeline._validate_structural_patches(batch, {"REQ-1701": ["source_clauses"]})
    repaired = RCAPipeline._apply_structural_patches(
        prep, batch, {"REQ-1701": ["source_clauses"]}
    )
    assert repaired.requirement_irs[0].source_clauses
    assert not any(
        "source-clause audit" in x.description
        for x in SemanticIntegrityChecker.structural_requirement_issues(repaired)
    )


def test_v188_missing_compiler_ids_receive_one_bounded_recovery_call():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    req_batch, ev_batch = split_semantic_preparation(prep)
    first = RequirementCompilationBatch(requirement_irs=req_batch.requirement_irs[:2])
    recovery = RequirementCompilationBatch(requirement_irs=[req_batch.requirement_irs[2]])
    verifier = verified_semantic_verification(canonical, prep)
    fast = FakeStructuredClient([first, recovery, ev_batch, verifier], model="27b")
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
    assert [x.requirement_id for x in result.semantic_preparation.requirement_irs] == [
        "REQ-1701", "REQ-1702", "REQ-1703"
    ]
    assert fast.calls == 4
    assert any(a.model_role == "SEMANTIC_REQUIREMENT_COMPILER_RECOVERY" for a in result.attempts)


def test_v188_prompts_make_provenance_and_normative_polarity_explicit():
    assert "Never return source_clauses=[]" in REQUIREMENT_COMPILATION_V086_PROMPT
    assert "PROHIBITIVE" in REQUIREMENT_COMPILATION_V086_PROMPT
    assert "COMPLETE replacement source_clauses inventory" in REQUIREMENT_STRUCTURAL_COMPLETION_V086_PROMPT
    assert 'normative_type=PROHIBITIVE' in REQUIREMENT_SEMANTIC_VERIFICATION_PROMPT
    assert "Return exactly one verification item" in REQUIREMENT_SEMANTIC_VERIFICATION_PROMPT


def test_v188_verified_semantic_fact_ids_are_valid_rca_hypothesis_references():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    fact_id = prep.evidence_annotations[0].facts[0].fact_id
    validated = ValidatedAnalysis(
        semantic=SemanticAnalysis(
            affected_functionality="Starter enable",
            evidence_inventory=canonical.evidence_inventory,
            requirements=[],
        ),
        requirement_results=[],
    )
    synthesis = RCASynthesisReasoning(
        affected_functionality="Starter enable",
        hypotheses=[HypothesisAnalysis(
            hypothesis="Mechanism candidate",
            support_basis=HypothesisSupportBasis.CURRENT_CASE_MECHANISM_MATCH,
            supporting_evidence_ids=[fact_id],
            source_references=[fact_id],
            confidence="LOW",
        )],
    )
    merged = RCAPipeline._merge_v080_rca(validated, canonical, prep, synthesis)
    assert len(merged.hypotheses) == 1
    assert merged.hypotheses[0].supporting_evidence_ids == [fact_id]


def test_v188_semantic_acceptance_fails_when_internal_error_produced_expected_conservative_verdict():
    class V:
        requirement_results = []
        issues = [ValidationIssue(
            code="SEMANTIC_INTEGRITY_UNRESOLVED",
            severity=ValidationSeverity.ERROR,
            path="REQ-X",
            message="compiler failed",
        )]
    class R:
        validated = V()
    out = evaluate_semantic_acceptance(R(), {"case": "X", "expected": {}})
    assert out["status"] == "FAIL"
    check = next(x for x in out["checks"] if x["check"] == "semantic_integrity.internal_error_count")
    assert check["actual"] == 1 and check["pass"] is False


def test_v188_single_run_exposes_running_case_lifecycle_before_completion(tmp_path):
    app, _, _ = make_stack(tmp_path)
    client = TestClient(app)
    run_id = client.post(
        "/api/v1/runs",
        json={"run_type": "single", "raw_case": "Ticket ID: TEST-LIVE-SINGLE\nSLOW"},
    ).json()["run_id"]
    deadline = time.time() + 2.0
    live = None
    while time.time() < deadline:
        wrapper = client.get(f"/api/v1/runs/{run_id}/result").json()
        rows = wrapper.get("case_lifecycle") or []
        if rows and rows[0].get("execution_status") == "RUNNING":
            live = rows[0]
            break
        time.sleep(0.01)
    assert live is not None
    assert live["case_id"] == "TEST-LIVE-SINGLE"
    wait_terminal(client, run_id)
    final = client.get(f"/api/v1/runs/{run_id}/result").json()["case_lifecycle"][0]
    assert final["execution_status"] == "PASS"


def test_v188_batch_exposes_current_running_case_before_it_finishes(tmp_path):
    app, _, _ = make_stack(tmp_path)
    client = TestClient(app)
    bio = BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("01.txt", "Ticket ID: TEST-LIVE-BATCH\nSLOW")
        z.writestr("02.txt", "Ticket ID: TEST-NEXT\nhello")
    up = client.post(
        "/api/v1/files",
        files={"file": ("batch.zip", bio.getvalue(), "application/zip")},
    ).json()
    run_id = client.post(
        "/api/v1/runs",
        json={"run_type": "bundle", "file_id": up["file_id"]},
    ).json()["run_id"]
    deadline = time.time() + 2.0
    seen = False
    while time.time() < deadline:
        wrapper = client.get(f"/api/v1/runs/{run_id}/result").json()
        result = wrapper.get("result") or {}
        rows = result.get("cases") or []
        if rows and rows[0].get("execution_status") == "RUNNING":
            assert result.get("count") == 0
            seen = True
            break
        time.sleep(0.01)
    assert seen
    wait_terminal(client, run_id)
