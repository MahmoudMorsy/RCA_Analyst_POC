from pathlib import Path
import zipfile

import pytest

from rca_app.test_bundle import (
    extract_case_id,
    load_test_bundle_zip,
    natural_sort_key,
    safe_case_alias,
)


def _write_zip(path: Path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in members:
            zf.writestr(name, text)


def test_extract_case_id_prefers_ticket_id():
    raw = "CURRENT TICKET\nTicket ID: TEST-042\nTitle:\nExample\n"
    assert extract_case_id(raw, "fallback.txt") == "TEST-042"


def test_natural_sort_orders_numeric_test_names():
    names = ["TEST-10.txt", "TEST-2.txt", "TEST-1.txt"]
    assert sorted(names, key=natural_sort_key) == ["TEST-1.txt", "TEST-2.txt", "TEST-10.txt"]


def test_safe_case_alias_maps_test_ids():
    assert safe_case_alias("TEST-004") == "TC4"
    assert safe_case_alias("My case / A") == "My_case_A"


def test_bundle_loader_reads_txt_recursively_and_ignores_other_files(tmp_path):
    bundle = tmp_path / "bundle.zip"
    _write_zip(
        bundle,
        [
            ("pack/README.md", "ignore"),
            ("pack/examples/TEST-010.txt", "CURRENT TICKET\nTicket ID: TEST-010\n"),
            ("pack/examples/TEST-004.txt", "CURRENT TICKET\nTicket ID: TEST-004\n"),
            ("pack/manifest.json", "{}"),
        ],
    )
    cases = load_test_bundle_zip(bundle)
    assert [x.case_id for x in cases] == ["TEST-004", "TEST-010"]
    assert cases[0].source_name.endswith("examples/TEST-004.txt")


def test_bundle_loader_falls_back_to_filename_stem(tmp_path):
    bundle = tmp_path / "bundle.zip"
    _write_zip(bundle, [("cases/custom_case.txt", "CURRENT TICKET\nTitle:\nNo ID\n")])
    cases = load_test_bundle_zip(bundle)
    assert cases[0].case_id == "custom_case"


def test_bundle_loader_rejects_duplicate_ticket_ids(tmp_path):
    bundle = tmp_path / "bundle.zip"
    _write_zip(
        bundle,
        [
            ("a.txt", "Ticket ID: TEST-004\n"),
            ("b.txt", "Ticket ID: test-004\n"),
        ],
    )
    with pytest.raises(ValueError, match="Duplicate Ticket ID"):
        load_test_bundle_zip(bundle)


def test_bundle_loader_rejects_zip_without_txt(tmp_path):
    bundle = tmp_path / "bundle.zip"
    _write_zip(bundle, [("README.md", "nothing")])
    with pytest.raises(ValueError, match="no .txt test cases"):
        load_test_bundle_zip(bundle)


def test_bundle_loader_reads_expected_results_manifest(tmp_path):
    from rca_app.test_bundle import load_expected_results_manifest
    bundle = tmp_path / "bundle.zip"
    _write_zip(bundle, [
        ("examples/TEST-001.txt", "Ticket ID: TEST-001\n"),
        ("expected_results_manifest.json", '{"cases":[{"case":"TEST-001","expected":{"REQ-1":{"evaluation_status":"SATISFIED"}}}]}'),
    ])
    manifest = load_expected_results_manifest(bundle)
    assert manifest["TEST-001"]["expected"]["REQ-1"]["evaluation_status"] == "SATISFIED"


def test_semantic_acceptance_separates_execution_from_expected_verdict():
    from types import SimpleNamespace
    from rca_app.models import Applicability, EvaluationStatus, NormativeType, RequirementAnalysis, RequirementResult, Sufficiency, ValidatedAnalysis, SemanticAnalysis
    from rca_app.test_bundle import evaluate_semantic_acceptance

    analysis = RequirementAnalysis(
        requirement_id="REQ-1",
        requirement_text="If A is ON, B shall be ON.",
        faithful_meaning="If A is ON, B must be ON.",
        relevance="x",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.APPLICABLE,
        applicability_evidence_ids=[],
        applicability_condition="A is ON",
        required_behavior="B shall be ON",
        evaluation_sufficiency=Sufficiency.SUFFICIENT_CONFORMANCE,
    )
    semantic = SemanticAnalysis(affected_functionality="x", evidence_inventory=[], requirements=[analysis])
    validated = ValidatedAnalysis(
        semantic=semantic,
        requirement_results=[RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.SATISFIED)],
    )
    result = SimpleNamespace(validated=validated)
    expected = {"case":"TEST-X", "expected":{"REQ-1":{"applicability":"APPLICABLE","evaluation_status":"VIOLATED"}}}
    acceptance = evaluate_semantic_acceptance(result, expected)
    assert acceptance["status"] == "FAIL"
    assert any(x["check"] == "REQ-1.evaluation_status" and not x["pass"] for x in acceptance["checks"])
