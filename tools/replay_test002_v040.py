from __future__ import annotations

"""Offline v0.4.0 compatibility replay for the real v0.3.6 TEST-002 LLM output.

The old response schema did not require ``applicability_evidence_ids``. v0.4.0 does.
For this one-off replay only, the migration binds each old applicability decision to
atomic DIRECT_OBSERVATION items whose ``signal_name`` is explicitly named in the
already-returned applicability condition/trigger. It does not change the LLM's
APPLICABLE / NOT APPLICABLE decision or evaluate signal values in Python.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rca_app.case_parser import DeterministicCaseParser
from rca_app.formatter import FinalReportFormatter
from rca_app.models import EvidenceClass, SemanticReasoning
from rca_app.pipeline import RCAPipeline
from rca_app.validator import DeterministicValidator


def migrate_legacy_applicability_bindings(raw: dict, canonical) -> dict:
    migrated = json.loads(json.dumps(raw))
    atoms = [
        e for e in canonical.evidence_inventory
        if e.evidence_class == EvidenceClass.DIRECT_OBSERVATION and e.signal_name
    ]
    for req in migrated.get("requirements", []):
        if "applicability_evidence_ids" in req:
            continue
        scope = " ".join([str(req.get("applicability_condition", "")), str(req.get("trigger", ""))])
        ids = []
        for e in atoms:
            if re.search(rf"\b{re.escape(e.signal_name)}\b", scope, re.I):
                ids.append(e.id)
        req["applicability_evidence_ids"] = ids
    return migrated


def main(session_path: Path, output_path: Path) -> None:
    case_text = (ROOT / "examples" / "TEST-002.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser().parse(case_text)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    raw = json.loads(session["attempts"][0]["raw_llm_json"])
    migrated = migrate_legacy_applicability_bindings(raw, canonical)
    reasoning = SemanticReasoning.model_validate(migrated)
    semantic = RCAPipeline._merge_canonical_and_reasoning(canonical, reasoning)
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    report = FinalReportFormatter().format(validated)

    statuses = {x.analysis.requirement_id: x.evaluation_status.value for x in validated.requirement_results}
    expected = {
        "REQ-101": "VIOLATED",
        "REQ-102": "SATISFIED",
        "REQ-103": "NO COMPLIANCE VERDICT",
    }
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]

    header = [
        "# RCA Analyst POC v0.4.0 — TEST-002 Offline Replay",
        "",
        "This replays the real v0.3.6 TEST-002 first-pass semantic decisions through v0.4.0.",
        "The legacy response omitted `applicability_evidence_ids`; the replay migration binds only atomic direct observations whose signal name is explicitly present in the LLM-returned applicability condition/trigger. It does not change applicability verdicts or evaluate signal values.",
        "",
        f"Critical errors: {len(errors)}",
        f"Expected statuses reached: {statuses == expected}",
        f"Statuses: {json.dumps(statuses, ensure_ascii=False)}",
        f"Minimum-next-evidence items: {len(validated.compliance_evidence)}",
        "",
        "## Migrated applicability bindings",
        "",
    ]
    by_id = {r.requirement_id: r for r in validated.semantic.requirements}
    for rid in ("REQ-101", "REQ-102", "REQ-103"):
        header.append(f"- {rid}: {', '.join(by_id[rid].applicability_evidence_ids) or 'NONE'}")
    header += ["", "## Final report", "", report]
    output_path.write_text("\n".join(header), encoding="utf-8")

    if errors or statuses != expected or validated.compliance_evidence:
        raise SystemExit(
            f"Replay failed: errors={len(errors)}, statuses={statuses}, compliance={validated.compliance_evidence}"
        )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: replay_test002_v040.py <v0.3.6-session.json> <output.md>")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
