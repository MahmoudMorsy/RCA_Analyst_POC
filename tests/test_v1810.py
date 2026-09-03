from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from rca_app.case_parser import DeterministicCaseParser
from rca_app.models import (
    LogicExpression,
    LogicKind,
    NormativeType,
    PredicateOperator,
    RequirementBehaviorIR,
    RequirementIR,
    RequirementPersistenceIR,
    RequirementSemanticFingerprint,
    RequirementStructuralPatch,
    SemanticArbitrationResponse,
    SemanticIntegrityIssue,
)
from rca_app.pipeline import RCAPipeline
from tests.test_v080 import (
    FIX,
    FakeStructuredClient,
    mismatch_semantic_verification,
    split_semantic_preparation,
    tc17_preparation,
)
from rca_server.api_models import RunCreateRequest, RunState, RunSummary
from rca_server.run_manager import RuntimeRun
from tests.test_web_backend import make_stack, wait_terminal


def test_v1810_verifier_required_behavior_ignores_descriptive_process_text():
    compiler = RequirementIR(
        requirement_id="REQ-X",
        normative_type=NormativeType.MANDATORY,
        required_behavior=RequirementBehaviorIR(
            signal="CentralLockStatus",
            operator=PredicateOperator.EQ,
            value="READY",
            process_description="CentralLockStatus shall be READY",
            source_phrase="CentralLockStatus shall be READY",
        ),
    )
    verifier = RequirementSemanticFingerprint(
        normative_type=NormativeType.MANDATORY,
        required_behavior=RequirementBehaviorIR(
            signal="CentralLockStatus",
            operator=PredicateOperator.EQ,
            value="READY",
            process_description="",
            source_phrase="READY state is required",
        ),
    )
    assert RCAPipeline._ir_semantic_signature(compiler)["required_behavior"] == RCAPipeline._semantic_fingerprint_signature(verifier)["required_behavior"]


def test_v1810_persistence_scope_fingerprint_normalizes_structural_equivalents():
    compiler = RequirementIR(
        requirement_id="REQ-X",
        normative_type=NormativeType.MANDATORY,
        required_behavior=RequirementBehaviorIR(signal="X", operator=PredicateOperator.EQ, value="Y"),
        persistence=RequirementPersistenceIR(required=True, scope="while ActiveVariant is MANUAL"),
    )
    verifier = RequirementSemanticFingerprint(
        normative_type=NormativeType.MANDATORY,
        required_behavior=RequirementBehaviorIR(signal="X", operator=PredicateOperator.EQ, value="Y"),
        persistence=RequirementPersistenceIR(required=True, scope="WHILE_CONDITION"),
    )
    assert RCAPipeline._ir_semantic_signature(compiler)["persistence"] == RCAPipeline._semantic_fingerprint_signature(verifier)["persistence"]


def test_v1810_arbitration_may_omit_field_only_when_all_field_issues_explicitly_unresolved():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    issue = SemanticIntegrityIssue(
        issue_id="VERIFY-001",
        requirement_id="REQ-1701",
        description="Independent source-semantic reconstruction disagrees with compiled IR in: condition.",
        material_to_compliance=True,
        target_fields=["condition"],
    )
    response = SemanticArbitrationResponse(
        requirement_patches=[RequirementStructuralPatch(requirement_id="REQ-1701")],
        unresolved_issue_ids=["VERIFY-001"],
    )
    RCAPipeline._validate_arbitration_response(
        response,
        {"REQ-1701": ["condition"]},
        set(),
        [issue],
        prep,
    )


def test_v1810_rejected_arbitration_is_conservative_not_pipeline_fatal():
    raw = (FIX / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    clean = tc17_preparation(canonical)
    bad = clean.model_copy(deep=True)
    bad.requirement_irs[0].condition.children = bad.requirement_irs[0].condition.children[:2]
    req_batch, ev_batch = split_semantic_preparation(bad)
    fast = FakeStructuredClient([
        req_batch,
        ev_batch,
        mismatch_semantic_verification(canonical, clean, "REQ-1701", "ServiceMode is not ACTIVE"),
    ], model="27b")
    rejected = SemanticArbitrationResponse(
        requirement_patches=[RequirementStructuralPatch(requirement_id="REQ-1701")],
        unresolved_issue_ids=[],
    )
    primary = FakeStructuredClient([rejected], model="27b")
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
    assert result.semantic_arbitration is None
    assert any(x.stage == "semantic_arbitration" and x.raw_llm_json for x in result.attempts)
    assert any(x.material_to_compliance and x.requirement_id == "REQ-1701" for x in result.canonical_case.semantic_integrity_issues)


def _upload_bundle(client: TestClient, cases: list[tuple[str, str]]) -> str:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in cases:
            z.writestr(name, text)
    return client.post(
        "/api/v1/files",
        files={"file": ("batch.zip", bio.getvalue(), "application/zip")},
    ).json()["file_id"]


def test_v1810_unexpected_testcase_exception_isolated_and_batch_continues(tmp_path):
    app, _, storage = make_stack(tmp_path)
    client = TestClient(app)
    file_id = _upload_bundle(client, [
        ("01.txt", "Ticket ID: TEST-FAIL\nPROVIDER_FAIL"),
        ("02.txt", "Ticket ID: TEST-AFTER\nhello"),
    ])
    run_id = client.post("/api/v1/runs", json={"run_type": "bundle", "file_id": file_id}).json()["run_id"]
    terminal = wait_terminal(client, run_id)
    assert terminal["status"] == "COMPLETED"
    wrapper = client.get(f"/api/v1/runs/{run_id}/result").json()
    rows = wrapper["result"]["cases"]
    assert [r["case_id"] for r in rows] == ["TEST-FAIL", "TEST-AFTER"]
    assert [r["execution_status"] for r in rows] == ["FAILED", "PASS"]
    failure = rows[0]["failure"]
    assert failure["exception_type"] == "RuntimeError"
    assert "simulated provider failure" in failure["message"]
    assert "Traceback" in failure["traceback"]
    assert failure["partial_pipeline"]
    assert storage.path(f"runs/{run_id}/cases/TEST-FAIL/failure.json").exists()
    # COMPLETED is set just before autosave; wait for the session id rather than
    # racing the final persistence step.
    for _ in range(100):
        summary = client.get(f"/api/v1/runs/{run_id}/status").json()
        if summary.get("session_id"):
            break
        import time
        time.sleep(0.01)
    session = client.get(f"/api/v1/runs/{run_id}/session/download").json()
    assert session["payload"]["cases"][0]["failure"]["exception_type"] == "RuntimeError"


def test_v1810_web_failure_view_surfaces_exception_and_traceback():
    js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
    assert "function failureText" in js
    assert "failure.exception_type" in js
    assert "failure.traceback" in js


def test_v1810_session_preserves_partial_result_and_run_level_failure(tmp_path):
    app, manager, _ = make_stack(tmp_path)
    config = manager.config_store.load()
    runtime = RuntimeRun(
        summary=RunSummary(
            run_id="RUN-PARTIAL", run_type="bundle", label="partial",
            status=RunState.FAILED, created_at="2026-09-03T00:00:00+00:00",
        ),
        request=RunCreateRequest(run_type="bundle", file_id="unused"),
        config=config,
    )
    runtime.result = {"run_type": "bundle", "cases": [{"case_id": "A", "execution_status": "PASS"}], "count": 1, "total_cases": 2}
    runtime.failure = {"status": "FAILED", "message": "run-level storage failure"}
    manager._auto_session(runtime)
    envelope = manager.sessions.load("RUN-PARTIAL")
    assert envelope["payload"]["cases"][0]["case_id"] == "A"
    assert envelope["payload"]["run_failure"]["message"] == "run-level storage failure"
