from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from rca_app.cancellation import CancellationToken
from rca_app.case_parser import DeterministicCaseParser
from rca_app.config import AppConfig
from rca_app.intake import IntakeCanonicalizer
from rca_app.lmstudio_client import LMStudioClient
from rca_app.models import (
    IntakeField,
    IntakeNormalization,
    IntakeRequirement,
    IntakeRequirementSection,
    IntakeSourceSection,
    SourceAvailability,
)
from rca_app.prompts import FAST_FINAL_REVIEW_PROMPT, FAST_INTAKE_NORMALIZER_PROMPT
from rca_app.review import LinguisticReviewGate
from rca_app.validator import DeterministicValidator
from tests.test_validator import make_test001


class _TinyResponse(BaseModel):
    value: str


class _ByteStreamResponse:
    def __init__(self, lines: list[bytes]):
        self.lines = lines
        self.closed = False
        self.status_code = 200

    def raise_for_status(self):
        return None

    def iter_lines(self, chunk_size=1, decode_unicode=False):
        assert decode_unicode is False
        yield from self.lines

    def close(self):
        self.closed = True


def _tc5_raw() -> str:
    bundle = Path('/mnt/data/testbundle/RCA_Overnight_Realistic_Test_Bundle_v1.1/examples/TEST-005.txt')
    if bundle.exists():
        return bundle.read_text(encoding='utf-8')
    return """CURRENT TICKET
Ticket ID: TEST-005
Title:
Apparent late activation with incomplete transition-event coverage.
Description:
Function X appears to activate later than the allowed response time, but the trace does not declare complete transition-event coverage.
SYSTEM REQUIREMENTS
REQ-401
When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.
HISTORICAL TICKETS
None provided.
CURRENT BZD / DIAGNOSTICS
Not available.
CURRENT TRACE / DIRECT OBSERVATIONS
Clock ID: TRACE_B
29.900 s FunctionRequest = INACTIVE
30.000 s FunctionRequest = ACTIVE
TASK
Analyze the current ticket strictly using the supplied engineering evidence.
"""


def test_v063_absence_is_semantic_metadata_not_diagnostic_evidence():
    raw = _tc5_raw()
    intake = IntakeNormalization(
        ticket_id=IntakeField(value='TEST-005', source_span='Ticket ID: TEST-005'),
        requirements=IntakeRequirementSection(
            availability=SourceAvailability.PRESENT,
            items=[IntakeRequirement(
                requirement_id='REQ-401',
                requirement_text='When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.',
                source_span='REQ-401\nWhen FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.',
            )],
        ),
        historical=IntakeSourceSection(
            availability=SourceAvailability.ABSENT,
            availability_statement=IntakeField(value='None provided.', source_span='None provided.'),
        ),
        diagnostics=IntakeSourceSection(
            availability=SourceAvailability.ABSENT,
            availability_statement=IntakeField(value='Not available.', source_span='Not available.'),
        ),
        trace=IntakeSourceSection(
            availability=SourceAvailability.PRESENT,
            blocks=[IntakeField(
                value='',
                source_span='Clock ID: TRACE_B\n29.900 s FunctionRequest = INACTIVE\n30.000 s FunctionRequest = ACTIVE',
            )],
        ),
        user_instructions=[IntakeField(
            value='Analyze the current ticket strictly using the supplied engineering evidence.',
            source_span='Analyze the current ticket strictly using the supplied engineering evidence.',
        )],
    )

    canonical = IntakeCanonicalizer(DeterministicCaseParser()).build(raw, intake)

    assert canonical.diagnostics_text == ''
    assert not any(e.source == 'Current BZD / Diagnostics' for e in canonical.evidence_inventory)
    assert canonical.source_availability['diagnostics'] == SourceAvailability.ABSENT
    assert canonical.source_availability_raw['diagnostics'] == 'Not available.'
    assert canonical.source_availability['historical'] == SourceAvailability.ABSENT
    assert canonical.user_instructions == ['Analyze the current ticket strictly using the supplied engineering evidence.']


def test_v063_multilingual_absence_and_present_no_faults_are_distinct_structures():
    absent = IntakeSourceSection(
        availability=SourceAvailability.ABSENT,
        availability_statement=IntakeField(value='nicht verfügbar', source_span='nicht verfügbar'),
    )
    present = IntakeSourceSection(
        availability=SourceAvailability.PRESENT,
        blocks=[IntakeField(value='Keine Fehler im Fehlerspeicher.', source_span='Keine Fehler im Fehlerspeicher.')],
    )
    assert absent.availability == SourceAvailability.ABSENT
    assert absent.blocks == []
    assert present.availability == SourceAvailability.PRESENT
    assert present.blocks[0].value == 'Keine Fehler im Fehlerspeicher.'


def test_v063_present_no_dtc_statement_becomes_diagnostic_observation():
    raw = 'Diagnostics checked; no DTCs present.'
    intake = IntakeNormalization(
        diagnostics=IntakeSourceSection(
            availability=SourceAvailability.PRESENT,
            blocks=[IntakeField(value=raw, source_span=raw)],
        )
    )
    canonical = IntakeCanonicalizer(DeterministicCaseParser()).build(raw, intake)
    diag = [e for e in canonical.evidence_inventory if e.source == 'Current BZD / Diagnostics']
    assert len(diag) == 1
    assert diag[0].text == raw
    assert canonical.source_availability['diagnostics'] == SourceAvailability.PRESENT


def test_v063_absent_source_cannot_contain_evidence_blocks():
    with pytest.raises(ValidationError):
        IntakeSourceSection(
            availability=SourceAvailability.ABSENT,
            blocks=[IntakeField(value='U1123 present', source_span='U1123 present')],
            availability_statement=IntakeField(value='not available', source_span='not available'),
        )


def test_v063_intake_prompt_teaches_semantic_availability_and_instruction_separation():
    assert 'ABSENT means' in FAST_INTAKE_NORMALIZER_PROMPT
    assert 'Diagnostics checked; no DTCs present.' in FAST_INTAKE_NORMALIZER_PROMPT
    assert 'BZD: nicht verfügbar' in FAST_INTAKE_NORMALIZER_PROMPT
    assert 'user_instructions' in FAST_INTAKE_NORMALIZER_PROMPT
    assert 'not engineering evidence' in FAST_INTAKE_NORMALIZER_PROMPT.lower()
    assert AppConfig().fast_repair_thinking_mode == 'off'


def test_v063_final_review_prompt_explicitly_separates_relevance_from_sufficiency():
    assert 'Relevance and evidentiary sufficiency are independent' in FAST_FINAL_REVIEW_PROMPT
    assert '700 ms' in FAST_FINAL_REVIEW_PROMPT
    validated = DeterministicValidator().normalize_and_validate(make_test001())
    payload = LinguisticReviewGate.compact_payload(validated)
    assert payload['instruction'] == 'Review wording only. Do not alter authoritative facts or verdicts.'


def test_v063_cancellable_chat_stream_preserves_utf8(monkeypatch):
    token = CancellationToken()
    desired = 'FunctionRequest → FunctionStatus – äöüß'
    chunk = {
        'choices': [{'delta': {'content': json.dumps({'value': desired}, ensure_ascii=False)}, 'finish_reason': 'stop'}]
    }
    usage = {'choices': [], 'usage': {'prompt_tokens': 2, 'completion_tokens': 2, 'total_tokens': 4}}
    lines = [
        ('data: ' + json.dumps(chunk, ensure_ascii=False)).encode('utf-8'),
        ('data: ' + json.dumps(usage, ensure_ascii=False)).encode('utf-8'),
        b'data: [DONE]',
    ]
    fake = _ByteStreamResponse(lines)
    monkeypatch.setattr('rca_app.lmstudio_client.requests.post', lambda *a, **k: fake)
    client = LMStudioClient('http://127.0.0.1:1234/v1', 'fake-model', cancellation_token=token)

    result = client.structured_chat('system', 'user', _TinyResponse, 'tiny')

    assert result.parsed.value == desired
    assert 'â' not in result.raw_json
    assert fake.closed is True


def test_v063_cancellable_manual_4b_stream_preserves_utf8(monkeypatch):
    token = CancellationToken()
    desired = 'BZD nicht verfügbar – Prüfung'
    chunk = {'choices': [{'text': json.dumps({'value': desired}, ensure_ascii=False), 'finish_reason': 'stop'}]}
    usage = {'choices': [], 'usage': {'prompt_tokens': 2, 'completion_tokens': 2, 'total_tokens': 4}}
    lines = [
        ('data: ' + json.dumps(chunk, ensure_ascii=False)).encode('utf-8'),
        ('data: ' + json.dumps(usage, ensure_ascii=False)).encode('utf-8'),
        b'data: [DONE]',
    ]
    fake = _ByteStreamResponse(lines)
    monkeypatch.setattr('rca_app.lmstudio_client.requests.post', lambda *a, **k: fake)
    client = LMStudioClient(
        'http://127.0.0.1:1234/v1', 'qwen3.5-4b', thinking_mode='off',
        transport='qwen35-manual', cancellation_token=token,
    )

    result = client.structured_repair('system', 'user', _TinyResponse, 'tiny')

    assert result.parsed.value == desired
    assert 'verfügbar' in result.raw_json
    assert fake.closed is True
