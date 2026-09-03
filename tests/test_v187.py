from __future__ import annotations

import json
from pathlib import Path

from rca_app.lmstudio_client import LMStudioClient
from rca_app.models import (
    RequirementBehaviorIR,
    RequirementCompilationBatch,
    RequirementPersistenceIR,
    RequirementStructuralPatch,
    RequirementStructuralPatchBatch,
    SemanticPreparation,
    PredicateOperator,
)
from rca_app.pipeline import RCAPipeline
from rca_app.prompts import (
    EVIDENCE_ANNOTATION_V085_PROMPT,
    REQUIREMENT_COMPILATION_V085_PROMPT,
    REQUIREMENT_STRUCTURAL_COMPLETION_V086_PROMPT,
    SEMANTIC_ARBITRATION_PROMPT,
)
from rca_app.semantic_ir import SemanticIntegrityChecker


FIX = Path(__file__).parent / "fixtures" / "v086"


class _FakeHTTPResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.text = json.dumps(data)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


def test_v187_thinking_off_is_propagated_per_request_and_reasoning_content_is_observable(monkeypatch):
    calls = []
    response = {
        "choices": [{
            "message": {"content": '{"patches":[]}', "reasoning_content": "provider still reasoned"},
            "finish_reason": "stop",
        }],
        # Reproduce the live llama.cpp/Qwen behavior: reasoning text exists but
        # completion_tokens_details.reasoning_tokens is absent.
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return _FakeHTTPResponse(response)

    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", fake_post)
    client = LMStudioClient(
        "http://127.0.0.1:8003/v1",
        "qwen3.8-27b",
        thinking_mode="off",
        reasoning_effort="provider_default",
        max_tokens=2000,
    )
    out = client.structured_chat(
        "sys", "user", RequirementStructuralPatchBatch, "structural_patch"
    )

    assert calls[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert out.stats.reasoning_tokens == 0
    assert out.stats.reasoning_content_present is True
    assert out.stats.reasoning_content_chars == len("provider still reasoned")
    assert out.stats.thinking_requested == "off"
    assert any("despite thinking_mode=off" in x for x in out.retry_diagnostics)


def test_v187_live_tc17_compiler_output_targets_only_broken_fields():
    batch = RequirementCompilationBatch.model_validate_json(
        (FIX / "TC17_v186_live_requirement_compiler.json").read_text(encoding="utf-8")
    )
    prep = SemanticPreparation(requirement_irs=batch.requirement_irs)
    issues = SemanticIntegrityChecker.structural_requirement_issues(prep)
    targets = RCAPipeline._structural_completion_targets(prep, issues)

    assert targets == {
        "REQ-1701": ["required_behavior"],
        "REQ-1702": ["required_behavior"],
        "REQ-1703": ["persistence", "required_behavior", "source_clauses"],
    }
    # The live compiler's correct nested condition must not be regenerated just
    # because its required_behavior transport shell was incomplete.
    assert "condition" not in targets["REQ-1701"]


def test_v187_targeted_structural_patch_repairs_live_tc17_shells_without_overwriting_condition():
    batch = RequirementCompilationBatch.model_validate_json(
        (FIX / "TC17_v186_live_requirement_compiler.json").read_text(encoding="utf-8")
    )
    prep = SemanticPreparation(requirement_irs=batch.requirement_irs)
    original_condition = prep.requirement_irs[0].condition.model_dump(mode="json")
    issues = SemanticIntegrityChecker.structural_requirement_issues(prep)
    targets = RCAPipeline._structural_completion_targets(prep, issues)

    patches = RequirementStructuralPatchBatch(patches=[
        RequirementStructuralPatch(
            requirement_id="REQ-1701",
            required_behavior=RequirementBehaviorIR(
                semantic_id="REQ-1701.behavior", source_phrase="StarterEnable shall be TRUE",
                signal="StarterEnable", operator=PredicateOperator.EQ, value="TRUE",
            ),
        ),
        RequirementStructuralPatch(
            requirement_id="REQ-1702",
            required_behavior=RequirementBehaviorIR(
                semantic_id="REQ-1702.behavior", source_phrase="StarterEnable shall be FALSE",
                signal="StarterEnable", operator=PredicateOperator.EQ, value="FALSE",
            ),
        ),
        RequirementStructuralPatch(
            requirement_id="REQ-1703",
            required_behavior=RequirementBehaviorIR(
                semantic_id="REQ-1703.behavior", source_phrase="StarterEnable shall remain FALSE",
                signal="StarterEnable", operator=PredicateOperator.EQ, value="FALSE",
            ),
            persistence=RequirementPersistenceIR(
                semantic_id="REQ-1703.persistence", source_phrase="StarterEnable shall remain FALSE",
                required=True, scope="WHILE_CONDITION",
            ),
            source_clauses=prep.requirement_irs[2].source_clauses,
        ),
    ])

    RCAPipeline._validate_structural_patches(patches, targets)
    repaired = RCAPipeline._apply_structural_patches(prep, patches, targets)
    assert repaired.requirement_irs[0].condition.model_dump(mode="json") == original_condition
    assert not SemanticIntegrityChecker.structural_requirement_issues(repaired)


def test_v187_structural_patch_rejects_untargeted_semantic_overwrite():
    targets = {"REQ-1701": ["required_behavior"]}
    patch = RequirementStructuralPatch(
        requirement_id="REQ-1701",
        required_behavior=RequirementBehaviorIR(
            semantic_id="B", source_phrase="StarterEnable shall be TRUE",
            signal="StarterEnable", operator=PredicateOperator.EQ, value="TRUE",
        ),
        # Supplying persistence here would broaden semantics beyond the target.
        persistence=RequirementPersistenceIR(semantic_id="P", required=True),
    )
    try:
        RCAPipeline._validate_structural_patches(RequirementStructuralPatchBatch(patches=[patch]), targets)
    except ValueError as exc:
        assert "untargeted fields" in str(exc)
    else:
        raise AssertionError("untargeted structural overwrite was accepted")


def test_v187_prompts_encode_live_tc17_contract_fixes():
    assert "required_behavior MUST contain semantic_id" in REQUIREMENT_COMPILATION_V085_PROMPT
    assert "operator=NEQ" in REQUIREMENT_COMPILATION_V085_PROMPT
    assert "target_fields" in REQUIREMENT_STRUCTURAL_COMPLETION_V086_PROMPT
    assert "Do not regenerate the full Requirement IR" in REQUIREMENT_STRUCTURAL_COMPLETION_V086_PROMPT
    assert "scope.scope_id=CASE_EVALUATED_INTERVAL" in EVIDENCE_ANNOTATION_V085_PROMPT
    assert "every returned PREDICATE must explicitly populate semantic_id" in SEMANTIC_ARBITRATION_PROMPT
    assert "do not return anonymous executable nodes" in SEMANTIC_ARBITRATION_PROMPT


def test_v187_live_tc17_narrative_ambiguity_is_not_material_without_role_or_structured_dependency():
    from rca_app.case_parser import DeterministicCaseParser
    from rca_app.models import EvidenceAnnotationBatch
    from tests.test_v080 import tc17_preparation

    raw = (Path(__file__).parent / "fixtures" / "v080" / "TEST-017.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser(language_interval_parsing_enabled=False).parse(raw)
    prep = tc17_preparation(canonical)
    live = EvidenceAnnotationBatch.model_validate_json(
        (FIX / "TC17_v186_live_evidence_annotations.json").read_text(encoding="utf-8")
    )
    prep.evidence_annotations = live.evidence_annotations
    issues = SemanticIntegrityChecker.validate(canonical, prep)
    material = SemanticIntegrityChecker.material_issues(issues)

    # Ticket-title ambiguity, the hedged "appears to satisfy" narrative and an
    # un-timestamped textual "verification point" must not block compliance by
    # themselves. They carry no material evidence role and no structured signal
    # dependency that Python can execute.
    blocked = {x.evidence_id for x in material}
    assert "EVID-TITLE" not in blocked
    assert "EVID-DESCRIPTION" not in blocked
    assert "EVID-REPORTED-001" not in blocked

    # The two persistent direct observations *are* material and non-executable in
    # the v1.8.6 live output because scope was NOT_APPLICABLE/empty. v0.8.6 must
    # route them to targeted evidence completion instead of silently accepting or
    # ignoring them.
    assert "EVID-DIRECT-001" in blocked
    assert "EVID-DIRECT-002" in blocked
