from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from .case_parser import DeterministicCaseParser
from .models import (
    CanonicalCase,
    EvidenceClass,
    EvidenceItem,
    IntakeField,
    IntakeNormalization,
    IntakeRequirement,
    IntakeRequirementSection,
    IntakeSourceSection,
    RequirementSource,
    SourceAvailability,
)


@dataclass(frozen=True)
class IntakeRouteDecision:
    use_fast_model: bool
    reason: str
    deterministic_preview: CanonicalCase


class IntakeRouter:
    """Choose whether raw input needs shallow 4B section normalization.

    The router is intentionally deterministic. A testcase that already follows
    the supported template bypasses 4B entirely. Free-form input can be routed
    through the fast model, after which Python still constructs CanonicalCase.
    """

    def __init__(self, parser: DeterministicCaseParser) -> None:
        self.parser = parser

    def decide(self, raw_case: str, mode: str = "auto", fast_available: bool = False) -> IntakeRouteDecision:
        preview = self.parser.parse(raw_case)
        mode = (mode or "auto").strip().lower()
        if mode == "off" or not fast_available:
            return IntakeRouteDecision(False, "Fast intake normalization is disabled or no fast model is available.", preview)
        if mode == "always":
            return IntakeRouteDecision(True, "Fast intake normalization is forced by configuration.", preview)

        lines = {line.strip().upper() for line in raw_case.replace("\r", "\n").splitlines() if line.strip()}
        has_requirement_heading = "SYSTEM REQUIREMENTS" in lines
        known_headings = sum(1 for h in self.parser.major_headings if h in lines)
        has_known_fields = bool(re.search(
            r"(?im)^\s*(?:Ticket\s+ID|Title|Description|Test\s+Steps|Reported\s+Test\s+Result)\s*:",
            raw_case,
        ))

        if preview.requirements and has_requirement_heading and (known_headings >= 2 or has_known_fields):
            return IntakeRouteDecision(False, "Input already matches the deterministic testcase structure.", preview)
        if not preview.requirements:
            return IntakeRouteDecision(True, "No explicit requirement block could be parsed deterministically.", preview)
        return IntakeRouteDecision(True, "Input contains requirements but does not reliably match the supported section layout.", preview)


class IntakeCanonicalizer:
    """Convert non-authoritative 4B intake extraction into authoritative canonical data.

    Only source-backed spans are accepted. Evidence IDs, evidence classes,
    trace event semantics, timestamps and transition inference are all assigned
    by Python. The 4B model never owns those fields.
    """

    _label_prefix = re.compile(
        r"^\s*(?:ticket\s*id|title|description|reported\s+test\s+result|result|actual|expected|"
        r"test\s+step(?:s)?|requirements?|system\s+requirements?|historical\s+tickets?|"
        r"diagnostics?|bzd|trace|direct\s+observations?)\s*[:\-]\s*",
        re.I,
    )

    def __init__(self, parser: DeterministicCaseParser) -> None:
        self.parser = parser

    def build(self, raw_case: str, normalized: IntakeNormalization) -> CanonicalCase:
        notes: list[str] = ["FAST_INTAKE_NORMALIZER_USED: Qwen3.5-class intake sectioning preceded deterministic canonicalization."]

        ticket_id = self._field_value(raw_case, normalized.ticket_id, notes, "ticket_id")
        title = self._field_value(raw_case, normalized.title, notes, "title")
        description = self._field_value(raw_case, normalized.description, notes, "description")

        evidence: list[EvidenceItem] = []
        if title:
            evidence.append(EvidenceItem(
                id="EVID-TITLE", evidence_class=EvidenceClass.CURRENT_TICKET,
                text=title, source="Ticket Title", raw_source_text=normalized.title.source_span.strip(),
            ))
        if description:
            evidence.append(EvidenceItem(
                id="EVID-DESCRIPTION", evidence_class=EvidenceClass.CURRENT_TICKET,
                text=description, source="Ticket Description", raw_source_text=normalized.description.source_span.strip(),
            ))

        step_index = 1
        for field in normalized.test_steps:
            text = self._field_value(raw_case, field, notes, f"test_steps[{step_index - 1}]")
            if not text:
                continue
            evidence.append(EvidenceItem(
                id=f"EVID-TEST-{step_index:03d}", evidence_class=EvidenceClass.TEST_INSTRUCTION,
                text=text, source=f"Test Step {step_index}", raw_source_text=field.source_span.strip(),
            ))
            step_index += 1

        reported_values: list[tuple[str, str]] = []
        for idx, field in enumerate(normalized.reported_results):
            text = self._field_value(raw_case, field, notes, f"reported_results[{idx}]")
            if text:
                reported_values.append((text, field.source_span.strip()))
        for idx, (text, source_span) in enumerate(reported_values, start=1):
            evidence.append(EvidenceItem(
                id=f"EVID-REPORTED-{idx:03d}", evidence_class=EvidenceClass.REPORTED_OBSERVATION,
                text=text, source="Reported Test Result", raw_source_text=source_span,
            ))

        requirements: list[RequirementSource] = []
        seen_req_ids: set[str] = set()
        for idx, req in enumerate(normalized.requirements.items):
            parsed = self._requirement_from_extraction(raw_case, req, notes, idx)
            if parsed is None or parsed.requirement_id.lower() in seen_req_ids:
                if parsed is not None:
                    notes.append(f"Duplicate fast-intake requirement ID ignored: {parsed.requirement_id}.")
                continue
            seen_req_ids.add(parsed.requirement_id.lower())
            requirements.append(parsed)
            evidence.append(EvidenceItem(
                id=f"EVID-REQ-{len(requirements):03d}",
                evidence_class=EvidenceClass.SYSTEM_REQUIREMENT,
                text=parsed.requirement_text,
                source=f"System Requirement {parsed.requirement_id}",
                raw_source_text=parsed.raw_source_text,
            ))

        historical_chunks, historical_raw = self._source_section(
            raw_case, normalized.historical, notes, "historical"
        )
        historical_text = "\n\n".join(x[0] for x in historical_chunks).strip()
        if historical_text:
            evidence.append(EvidenceItem(
                id="EVID-HIST-001", evidence_class=EvidenceClass.HISTORICAL_EVIDENCE,
                text=historical_text, source="Historical Tickets",
                raw_source_text="\n\n".join(x[1] for x in historical_chunks),
            ))

        diagnostic_chunks, diagnostics_raw = self._source_section(
            raw_case, normalized.diagnostics, notes, "diagnostics"
        )
        diagnostics_text = "\n\n".join(x[0] for x in diagnostic_chunks).strip()
        if diagnostics_text:
            evidence.append(EvidenceItem(
                id="EVID-DIAG-001", evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text=diagnostics_text, source="Current BZD / Diagnostics",
                raw_source_text="\n\n".join(x[1] for x in diagnostic_chunks),
            ))

        direct_seq = 1
        trace_chunks, trace_raw = self._source_section(raw_case, normalized.trace, notes, "trace")
        for idx, (_, source_span) in enumerate(trace_chunks):
            # Trace mechanics intentionally use the verbatim source span, not an
            # LLM-normalized trace rendering. This prevents the intake model from
            # inventing timestamps, transitions, clocks or coverage semantics.
            trace_text = self._strip_label(source_span.strip())
            for item in self.parser.parse_direct_observations(trace_text):
                item.id = f"EVID-DIRECT-{direct_seq:03d}"
                item.raw_source_text = item.text
                evidence.append(item)
                direct_seq += 1

        user_instructions: list[str] = []
        for idx, field in enumerate(normalized.user_instructions):
            text = self._field_value(raw_case, field, notes, f"user_instructions[{idx}]")
            if text:
                user_instructions.append(text)

        for span in normalized.unclassified_spans:
            if span.strip() and self._span_supported(raw_case, span):
                notes.append("Unclassified source span retained by intake normalizer: " + " ".join(span.split())[:280])
        notes.extend(x.strip() for x in normalized.notes if x.strip())
        if not requirements:
            notes.append("No source-backed requirements survived fast intake canonicalization.")

        return CanonicalCase(
            ticket_id=ticket_id,
            title=title,
            description=description,
            evidence_inventory=evidence,
            requirements=requirements,
            historical_text=historical_text,
            diagnostics_text=diagnostics_text,
            source_availability={
                "requirements": normalized.requirements.availability,
                "historical": normalized.historical.availability,
                "diagnostics": normalized.diagnostics.availability,
                "trace": normalized.trace.availability,
            },
            source_availability_raw={
                key: value
                for key, value in {
                    "requirements": self._availability_raw(raw_case, normalized.requirements.availability_statement, notes, "requirements"),
                    "historical": historical_raw,
                    "diagnostics": diagnostics_raw,
                    "trace": trace_raw,
                }.items()
                if value
            },
            user_instructions=user_instructions,
            parser_notes=notes,
        )

    def _source_section(
        self,
        raw_case: str,
        section: IntakeSourceSection,
        notes: list[str],
        label: str,
    ) -> tuple[list[tuple[str, str]], str]:
        """Enforce model-classified availability without interpreting language.

        Qwen owns whether a natural-language statement means PRESENT/ABSENT/
        UNKNOWN/NOT_MENTIONED. Python only enforces the normalized contract:
        non-PRESENT sources do not become engineering evidence.
        """
        availability_raw = self._availability_raw(
            raw_case, section.availability_statement, notes, label
        )
        if section.availability != SourceAvailability.PRESENT:
            if section.blocks:
                # This should normally be rejected already by Pydantic, but keep
                # the canonicalizer defensive against deserialized legacy data.
                notes.append(
                    f"Ignored {len(section.blocks)} {label} block(s) because intake classified the source as {section.availability.value}."
                )
            notes.append(f"Fast intake classified {label} source availability as {section.availability.value}.")
            return [], availability_raw
        return self._supported_blocks(raw_case, section.blocks, notes, f"{label}.blocks"), availability_raw

    def _availability_raw(
        self,
        raw_case: str,
        field: IntakeField,
        notes: list[str],
        label: str,
    ) -> str:
        span = (field.source_span or "").strip()
        if not span:
            return ""
        if not self._span_supported(raw_case, span):
            notes.append(f"Rejected unsupported source_span for {label}.availability_statement.")
            return ""
        return span

    def _supported_blocks(
        self,
        raw_case: str,
        fields: Iterable[IntakeField],
        notes: list[str],
        label: str,
    ) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for idx, field in enumerate(fields):
            value = self._field_value(raw_case, field, notes, f"{label}[{idx}]")
            if value:
                out.append((value, field.source_span.strip()))
        return out

    def _field_value(self, raw_case: str, field: IntakeField, notes: list[str], path: str) -> str:
        span = (field.source_span or "").strip()
        if not span:
            return ""
        if not self._span_supported(raw_case, span):
            notes.append(f"Rejected unsupported source_span for {path}.")
            return ""
        # The fast model identifies the category; Python prefers source wording.
        # A model-provided value is accepted only when it is textually contained
        # in the cited span after whitespace normalization.
        value = (field.value or "").strip()
        if value and self._normalized(value) in self._normalized(span):
            return value
        return self._strip_label(span)

    def _requirement_from_extraction(
        self,
        raw_case: str,
        req: IntakeRequirement,
        notes: list[str],
        index: int,
    ) -> Optional[RequirementSource]:
        span = (req.source_span or "").strip()
        if not self._span_supported(raw_case, span):
            notes.append(f"Rejected unsupported source_span for requirements[{index}].")
            return None
        rid = (req.requirement_id or "").strip()
        if not rid or rid.lower() not in span.lower():
            notes.append(f"Rejected requirement extraction {index}: requirement_id is not present in its cited source span.")
            return None
        proposed = (req.requirement_text or "").strip()
        if proposed and self._normalized(proposed) in self._normalized(span):
            text = proposed
        else:
            text = re.sub(re.escape(rid), "", span, count=1, flags=re.I).strip(" \t:-—")
            text = self._strip_label(text)
        if not text:
            notes.append(f"Rejected requirement extraction {rid}: no source-backed requirement text remained.")
            return None
        return RequirementSource(requirement_id=rid, requirement_text=text, raw_source_text=span)

    @classmethod
    def _strip_label(cls, text: str) -> str:
        out = cls._label_prefix.sub("", text.strip(), count=1)
        out = re.sub(r"^\s*\d+[\.)]\s+", "", out)
        return out.strip()

    @staticmethod
    def _normalized(text: str) -> str:
        return " ".join((text or "").split()).strip().lower()

    @classmethod
    def _span_supported(cls, raw_case: str, span: str) -> bool:
        if not span.strip():
            return False
        if span.strip() in raw_case:
            return True
        return cls._normalized(span) in cls._normalized(raw_case)
