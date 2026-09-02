from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import zipfile
from typing import Any, Dict, List, Tuple, Optional


_TICKET_ID_RE = re.compile(r"^\s*Ticket\s+ID\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_NATURAL_SPLIT_RE = re.compile(r"(\d+)")
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_EXPECTED_MANIFEST_NAME = "expected_results_manifest.json"


@dataclass(frozen=True)
class BundleCase:
    case_id: str
    raw_text: str
    source_name: str


def natural_sort_key(value: str) -> Tuple[object, ...]:
    """Sort TEST-9 before TEST-10 while remaining deterministic for arbitrary names."""
    parts = _NATURAL_SPLIT_RE.split(value.replace("\\", "/").lower())
    key = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part)
    return tuple(key)


def extract_case_id(raw_text: str, fallback_name: str) -> str:
    match = _TICKET_ID_RE.search(raw_text)
    if match:
        value = match.group(1).strip()
        if value:
            return value
    fallback = Path(fallback_name).stem.strip()
    return fallback or "UNNAMED-CASE"


def safe_filename_component(value: str, fallback: str = "case") -> str:
    cleaned = _SAFE_FILENAME_RE.sub("_", value.strip()).strip("._-")
    return cleaned or fallback


def safe_case_alias(case_id: str) -> str:
    match = re.fullmatch(r"TEST-(\d+)", case_id.strip(), re.IGNORECASE)
    if match:
        return f"TC{int(match.group(1))}"
    return safe_filename_component(case_id, "case")


def _open_bundle(path: Path) -> zipfile.ZipFile:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Test bundle does not exist: {path}")
    if path.suffix.lower() != ".zip":
        raise ValueError("Test bundle must be a .zip file containing one or more .txt cases.")
    try:
        return zipfile.ZipFile(path, "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError(f"Could not open test bundle ZIP: {exc}") from exc


def load_test_bundle_zip(zip_path: Path) -> List[BundleCase]:
    """Load every UTF-8 .txt test case inside a ZIP, recursively, in natural filename order.

    Non-.txt files (README, expected-result manifests, parser preflight files, etc.) are
    intentionally ignored. Case IDs are read from ``Ticket ID:`` when present, otherwise
    the text filename stem is used. Duplicate case IDs are rejected because they would
    make result attribution and output filenames ambiguous.
    """
    archive = _open_bundle(Path(zip_path))
    with archive:
        entries = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and info.filename.lower().endswith(".txt")
            and not Path(info.filename).name.startswith(".")
            and "__macosx" not in {part.lower() for part in Path(info.filename).parts}
        ]
        entries.sort(key=lambda info: natural_sort_key(info.filename))
        if not entries:
            raise ValueError("The selected ZIP contains no .txt test cases.")

        cases: List[BundleCase] = []
        seen = {}
        for info in entries:
            try:
                raw = archive.read(info).decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError(f"Test case is not UTF-8 text: {info.filename}") from exc
            if not raw.strip():
                raise ValueError(f"Test case is empty: {info.filename}")

            case_id = extract_case_id(raw, info.filename)
            normalized_id = case_id.casefold()
            if normalized_id in seen:
                raise ValueError(
                    f"Duplicate Ticket ID '{case_id}' in bundle files:\n"
                    f"- {seen[normalized_id]}\n- {info.filename}"
                )
            seen[normalized_id] = info.filename
            cases.append(BundleCase(case_id=case_id, raw_text=raw, source_name=info.filename))

    return cases


def load_expected_results_manifest(zip_path: Path) -> Dict[str, dict[str, Any]]:
    """Load case expectations embedded in a regression ZIP, if present.

    The runner intentionally treats absence of a manifest as ``NOT_CHECKED`` rather
    than inventing acceptance criteria. A malformed supplied manifest is an explicit
    bundle error because silently ignoring it would recreate the old execution-only
    PASS behavior.
    """
    archive = _open_bundle(Path(zip_path))
    with archive:
        candidates = [
            info for info in archive.infolist()
            if not info.is_dir() and Path(info.filename).name.lower() == _EXPECTED_MANIFEST_NAME
        ]
        if not candidates:
            return {}
        candidates.sort(key=lambda x: (len(Path(x.filename).parts), natural_sort_key(x.filename)))
        info = candidates[0]
        try:
            payload = json.loads(archive.read(info).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not parse {_EXPECTED_MANIFEST_NAME}: {exc}") from exc
        cases = payload.get("cases")
        if not isinstance(cases, list):
            raise ValueError(f"{_EXPECTED_MANIFEST_NAME} must contain a top-level 'cases' list.")
        out: Dict[str, dict[str, Any]] = {}
        for item in cases:
            if not isinstance(item, dict) or not str(item.get("case", "")).strip():
                raise ValueError(f"{_EXPECTED_MANIFEST_NAME} contains a case without a valid 'case' ID.")
            cid = str(item["case"]).strip()
            key = cid.casefold()
            if key in {x.casefold() for x in out}:
                raise ValueError(f"Duplicate case '{cid}' in {_EXPECTED_MANIFEST_NAME}.")
            out[cid] = item
        return out


def builtin_regression_expectations() -> Dict[str, dict[str, Any]]:
    """Frozen TC1-TC3 semantic guards used by the built-in sequential runner."""
    return {
        "TEST-001": {"case": "TEST-001", "expected": {
            "REQ-001": {"applicability": "APPLICABILITY UNKNOWN", "evaluation_status": "NO COMPLIANCE VERDICT", "timing_fact": None},
            "REQ-002": {"applicability": "APPLICABILITY UNKNOWN", "evaluation_status": "NOT EVALUABLE", "timing_fact": None},
            "REQ-003": {"applicability": "APPLICABILITY UNKNOWN", "evaluation_status": "NOT EVALUABLE", "timing_fact": None},
        }},
        "TEST-002": {"case": "TEST-002", "expected": {
            "REQ-101": {"applicability": "APPLICABLE", "evaluation_status": "VIOLATED", "timing_fact": None},
            "REQ-102": {"applicability": "APPLICABLE", "evaluation_status": "NOT EVALUABLE", "timing_fact": None},
            "REQ-103": {"applicability": "NOT APPLICABLE", "evaluation_status": "NO COMPLIANCE VERDICT", "timing_fact": None},
        }},
        "TEST-003": {"case": "TEST-003", "expected": {
            "REQ-201": {"applicability": "APPLICABLE", "evaluation_status": "VIOLATED", "timing": {"elapsed_ms": 550.0, "limit_ms": 500.0, "outcome": "EXCEEDS_LIMIT"}},
            "REQ-202": {"applicability": "NOT APPLICABLE", "evaluation_status": "NO COMPLIANCE VERDICT", "timing_fact": None},
        }},
    }


def evaluate_semantic_acceptance(result, expected_case: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Compare deterministic result fields against a supplied regression manifest.

    This checker intentionally limits itself to machine-verifiable contract fields:
    requirement presence, normative type, applicability, evaluation status, timing
    fact/value, and whether a hypothesis is required at all. Free-form ``must_not``
    prose remains visible as manual review criteria instead of pretending a brittle
    substring search is semantic validation.
    """
    if not expected_case:
        return {
            "status": "NOT_CHECKED",
            "checks": [],
            "manual_criteria": [],
        }

    by_id = {rr.analysis.requirement_id: rr for rr in result.validated.requirement_results}
    checks: list[dict[str, Any]] = []

    def add(name: str, expected: Any, actual: Any, passed: bool) -> None:
        checks.append({"check": name, "expected": expected, "actual": actual, "pass": bool(passed)})

    for key, exp in (expected_case.get("expected") or {}).items():
        if not str(key).upper().startswith("REQ-") or not isinstance(exp, dict):
            continue
        rr = by_id.get(key)
        add(f"{key}.present", True, rr is not None, rr is not None)
        if rr is None:
            continue
        if "normative_type" in exp:
            actual = rr.analysis.normative_type.value
            add(f"{key}.normative_type", exp["normative_type"], actual, actual == exp["normative_type"])
        if "applicability" in exp:
            actual = rr.analysis.applicability.value
            add(f"{key}.applicability", exp["applicability"], actual, actual == exp["applicability"])
        if "evaluation_status" in exp:
            actual = rr.evaluation_status.value
            add(f"{key}.evaluation_status", exp["evaluation_status"], actual, actual == exp["evaluation_status"])
        if "timing_fact" in exp and exp["timing_fact"] is None:
            add(f"{key}.timing_fact", None, rr.timing_fact.model_dump(mode="json") if rr.timing_fact else None, rr.timing_fact is None)
        if isinstance(exp.get("timing"), dict):
            timing = exp["timing"]
            if rr.timing_fact is None:
                add(f"{key}.timing.present", True, False, False)
            else:
                add(f"{key}.timing.present", True, True, True)
                for field in ("elapsed_ms", "limit_ms"):
                    if field in timing:
                        actual = float(getattr(rr.timing_fact, field))
                        expected = float(timing[field])
                        add(f"{key}.timing.{field}", expected, actual, abs(actual - expected) <= 1e-6)
                if "outcome" in timing:
                    actual = rr.timing_fact.outcome.value
                    add(f"{key}.timing.outcome", timing["outcome"], actual, actual == timing["outcome"])

    hyp = (expected_case.get("expected") or {}).get("hypothesis")
    if isinstance(hyp, dict) and "required" in hyp:
        actual = bool(result.validated.hypotheses)
        add("hypothesis.required", bool(hyp["required"]), actual, actual == bool(hyp["required"]))

    status = "PASS" if checks and all(x["pass"] for x in checks) else "FAIL"
    return {
        "status": status,
        "checks": checks,
        "manual_criteria": list(expected_case.get("must_not") or []),
        "purpose": list(expected_case.get("purpose") or []),
    }
