from rca_app.formatter import FinalReportFormatter
from rca_app.validator import DeterministicValidator
from tests.test_validator import make_canonical, make_test001


def test_formatter_has_11_sections_clean_findings_and_closed_minimum_evidence():
    validated = DeterministicValidator().normalize_and_validate(make_test001(), canonical_case=make_canonical())
    report = FinalReportFormatter().format(validated)
    for n in range(1, 12):
        assert f"# {n}." in report
    confirmed = report.split("# 6. Confirmed Findings", 1)[1].split("# 7.", 1)[0]
    assert "Set FunctionRequest" not in confirmed
    assert "FunctionStatus did not become ACTIVE." in confirmed
    assert "The user activates Function X" not in confirmed

    minimum = report.split("# 10. Minimum Next Evidence Required", 1)[1].split("# 11.", 1)[0]
    assert "FunctionRequest" in minimum
    assert "FunctionStatus" in minimum
    assert "AvailabilityStatus" in minimum
    assert "500 ms" in minimum
    assert "sufficient observation interval" in minimum
    assert "IgnitionState" not in minimum
