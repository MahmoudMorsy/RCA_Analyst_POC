from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Set

from .models import CanonicalCase, EvidenceClass, EvidenceItem, ObservationType, RequirementSource


_NONE_MARKERS = {
    "none",
    "none provided",
    "not available",
    "n/a",
    "na",
    "no",
    "no data",
    "no evidence",
}


@dataclass
class _FieldSpan:
    label: str
    start: int
    end: int


class DeterministicCaseParser:
    """Parse the manual case template into authoritative source boundaries.

    The parser intentionally does not perform engineering interpretation. Its job
    is only to preserve where text came from: ticket metadata, test instructions,
    reported result, requirements, historical data, and diagnostics.

    v0.5.0 supports the current manual POC template, atomic direct observations, explicit observation semantics, event-coverage semantics, snapshot/observation-group correlation, and common minor formatting
    variations. Unrecognized material remains in parser notes instead of being
    promoted to an observation by the LLM.
    """

    major_headings = {
        "CURRENT TICKET",
        "TEST INFORMATION",
        "SYSTEM REQUIREMENTS",
        "HISTORICAL TICKETS",
        "CURRENT BZD / DIAGNOSTICS",
        "CURRENT BZD/DIAGNOSTICS",
        "BZD / DIAGNOSTICS",
        "BZD/DIAGNOSTICS",
        "CURRENT TRACE / DIRECT OBSERVATIONS",
        "CURRENT TRACE/DIRECT OBSERVATIONS",
        "DIRECT OBSERVATIONS",
        "TRACE / SIGNAL LOGS",
        "TRACE/SIGNAL LOGS",
        "TASK",
    }

    req_id_re = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*REQ[A-Za-z0-9_-]*|REQ[-_A-Za-z0-9]+)\s*:?[ \t]*$", re.I)
    numbered_step_re = re.compile(r"^\s*(\d+)[\.)]\s*(.+?)\s*$")

    def __init__(self, language_interval_parsing_enabled: bool = True) -> None:
        # v0.8 production disables natural-language interval promotion. The
        # compatibility default remains True for frozen parser/unit tests and
        # explicitly structured legacy inputs.
        self.language_interval_parsing_enabled = language_interval_parsing_enabled

    def parse(self, raw_case: str) -> CanonicalCase:
        raw = raw_case.replace("\r\n", "\n").replace("\r", "\n").strip()
        lines = raw.split("\n")

        ticket_id = self._single_line_value(lines, "Ticket ID")
        title = self._multiline_field(lines, "Title", stop_labels=("Description",))
        description = self._multiline_field(
            lines,
            "Description",
            stop_labels=("Test Steps", "Reported Test Result"),
            stop_headings=self.major_headings,
        )
        test_steps = self._extract_test_steps(lines)
        reported_result = self._multiline_field(
            lines,
            "Reported Test Result",
            stop_headings=self.major_headings,
        )
        requirements = self._extract_requirements(lines)
        historical_text = self._section_text(lines, ("HISTORICAL TICKETS",), self.major_headings)
        diagnostics_text = self._section_text(
            lines,
            ("CURRENT BZD / DIAGNOSTICS", "CURRENT BZD/DIAGNOSTICS", "BZD / DIAGNOSTICS", "BZD/DIAGNOSTICS"),
            self.major_headings,
        )
        direct_text = self._section_text(
            lines,
            ("CURRENT TRACE / DIRECT OBSERVATIONS", "CURRENT TRACE/DIRECT OBSERVATIONS", "DIRECT OBSERVATIONS", "TRACE / SIGNAL LOGS", "TRACE/SIGNAL LOGS"),
            self.major_headings,
        )

        evidence: list[EvidenceItem] = []
        if title:
            evidence.append(EvidenceItem(
                id="EVID-TITLE",
                evidence_class=EvidenceClass.CURRENT_TICKET,
                text=title,
                source="Ticket Title",
            ))
        if description:
            evidence.append(EvidenceItem(
                id="EVID-DESCRIPTION",
                evidence_class=EvidenceClass.CURRENT_TICKET,
                text=description,
                source="Ticket Description",
            ))
        for i, step in enumerate(test_steps, start=1):
            evidence.append(EvidenceItem(
                id=f"EVID-TEST-{i:03d}",
                evidence_class=EvidenceClass.TEST_INSTRUCTION,
                text=step,
                source=f"Test Step {i}",
            ))
        if reported_result:
            # This source label is authoritative: it is the current case's reported observation.
            evidence.append(EvidenceItem(
                id="EVID-REPORTED-001",
                evidence_class=EvidenceClass.REPORTED_OBSERVATION,
                text=reported_result,
                source="Reported Test Result",
            ))
        for i, req in enumerate(requirements, start=1):
            evidence.append(EvidenceItem(
                id=f"EVID-REQ-{i:03d}",
                evidence_class=EvidenceClass.SYSTEM_REQUIREMENT,
                text=req.requirement_text,
                source=f"System Requirement {req.requirement_id}",
            ))
        if historical_text and not self._is_none_block(historical_text):
            evidence.append(EvidenceItem(
                id="EVID-HIST-001",
                evidence_class=EvidenceClass.HISTORICAL_EVIDENCE,
                text=historical_text,
                source="Historical Tickets",
            ))
        if diagnostics_text and not self._is_none_block(diagnostics_text):
            evidence.append(EvidenceItem(
                id="EVID-DIAG-001",
                evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text=diagnostics_text,
                source="Current BZD / Diagnostics",
            ))
        if direct_text and not self._is_none_block(direct_text):
            evidence.extend(self._parse_direct_observations(direct_text))

        notes: list[str] = []
        if not requirements:
            notes.append("No SYSTEM REQUIREMENTS entries were deterministically parsed.")
        if not reported_result:
            notes.append("No Reported Test Result field was deterministically parsed; ticket prose is not auto-promoted to REPORTED_OBSERVATION.")
        if not title and not description:
            notes.append("No ticket Title/Description fields were deterministically parsed.")

        return CanonicalCase(
            ticket_id=ticket_id,
            title=title,
            description=description,
            evidence_inventory=evidence,
            requirements=requirements,
            historical_text="" if self._is_none_block(historical_text) else historical_text,
            diagnostics_text="" if self._is_none_block(diagnostics_text) else diagnostics_text,
            parser_notes=notes,
        )

    _direct_assignment_re = re.compile(
        r"^\s*(?:(?P<ts>\d+(?:\.\d+)?)\s*(?P<unit>ms|s|sec|secs|second|seconds)\s+)?"
        r"(?P<signal>[A-Za-z_][A-Za-z0-9_.]*)\s*=\s*(?P<value>.+?)\s*$",
        re.I,
    )
    _direct_transition_re = re.compile(
        r"^\s*(?:(?P<ts>\d+(?:\.\d+)?)\s*(?P<unit>ms|s|sec|secs|second|seconds)\s+)?"
        r"(?P<signal>[A-Za-z_][A-Za-z0-9_.]*)\s+"
        r"(?:"
        r"(?:transitioned|transitions|changed|changes)\s+(?:from\s+(?P<from>[A-Za-z0-9_.+\-]+)\s+)?to\s+(?P<to>[A-Za-z0-9_.+\-]+)"
        r"|became\s+(?P<became>[A-Za-z0-9_.+\-]+)"
        r")\s*\.?$",
        re.I,
    )
    _direct_remained_re = re.compile(
        r"^\s*(?P<signal>[A-Za-z_][A-Za-z0-9_.]*)\s+(?:remained|remains|was)\s+"
        r"(?P<value>[A-Za-z0-9_.+-]+)\s+throughout\s+(?:the\s+)?(?:complete|full)\s+"
        r"(?:evaluated\s+)?(?:observation\s+)?interval\.?\s*$",
        re.I,
    )
    _clock_meta_re = re.compile(r"^\s*(?:Clock(?:\s+ID)?|Timebase)\s*:\s*(.+?)\s*$", re.I)
    _event_coverage_meta_re = re.compile(r"^\s*Event\s+Coverage(?:\s+Complete)?\s*:\s*(true|yes|complete|full)\s*$", re.I)
    _coverage_meta_re = re.compile(r"^\s*Coverage(?:\s+Complete)?\s*:\s*(true|yes|complete|full)\s*$", re.I)
    _observation_group_meta_re = re.compile(r"^\s*(?:Snapshot(?:\s+ID)?|Observation\s+Group)\s*:\s*(.+?)\s*$", re.I)

    def parse_direct_observations(self, direct_text: str) -> list[EvidenceItem]:
        """Public deterministic trace parser used after optional 4B intake sectioning."""
        return self._parse_direct_observations(direct_text)

    def _parse_direct_observations(self, direct_text: str) -> list[EvidenceItem]:
        """Atomize conservative trace observations and explicit correlation metadata.

        v0.5.5 preserves the v0.5.x evidence semantics and adds assignment-only
        trace transition inference. The visible trace may stay in the natural
        ``timestamp Signal = Value`` form. When a later timestamped assignment for
        the same signal on the same clock changes value, the canonical metadata
        marks that later observation as TRANSITION and records transition_from /
        transition_to. The raw evidence text is never rewritten to "transitioned".

        ``Snapshot ID`` / ``Observation Group`` metadata remains explicit. The
        active observation group is attached to following evidence atoms until
        another group marker appears; textual proximity alone is not simultaneity.
        """
        lines = [line.strip() for line in direct_text.splitlines() if line.strip()]
        clock_id = ""
        block_coverage_complete = False
        block_event_coverage_complete = False

        # Clock and coverage declarations are block-wide even if written after a
        # group marker. Snapshot/group metadata is intentionally sequential.
        for line in lines:
            m_clock = self._clock_meta_re.match(line)
            if m_clock:
                clock_id = m_clock.group(1).strip()
            elif self._event_coverage_meta_re.match(line):
                block_event_coverage_complete = True
            elif self._coverage_meta_re.match(line):
                block_coverage_complete = True

        result: list[EvidenceItem] = []
        seq = 1
        observation_group = ""
        # Last timestamped value per signal is used only to derive transition
        # metadata from assignment-style event logs. The displayed/raw text stays
        # exactly as supplied (``Signal = Value``). A first sample never becomes
        # a transition merely because it has a timestamp.
        last_timestamped_value: dict[str, tuple[float, str, str]] = {}
        for line in lines:
            if self._clock_meta_re.match(line) or self._event_coverage_meta_re.match(line) or self._coverage_meta_re.match(line):
                continue
            m_group = self._observation_group_meta_re.match(line)
            if m_group:
                observation_group = m_group.group(1).strip()
                continue
            if re.match(r"^(?:during|over)\s+the\s+evaluated\s+observation\s+interval\s*:?$", line, re.I):
                continue

            m = self._direct_transition_re.match(line)
            if m:
                ts_raw = m.group("ts")
                unit = (m.group("unit") or "").lower()
                timestamp_seconds = None
                anchor = ""
                if ts_raw is not None:
                    val = float(ts_raw)
                    timestamp_seconds = val / 1000.0 if unit == "ms" else val
                    anchor = f"{ts_raw} {m.group('unit')}"
                target = (m.group("to") or m.group("became") or "").strip()
                signal = m.group("signal").strip()
                result.append(EvidenceItem(
                    id=f"EVID-DIRECT-{seq:03d}",
                    evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                    text=line,
                    source="Direct Observations / Trace",
                    anchor=anchor,
                    timestamped=ts_raw is not None,
                    timestamp_seconds=timestamp_seconds,
                    coverage_complete=block_coverage_complete,
                    event_coverage_complete=block_event_coverage_complete,
                    clock_id=clock_id,
                    signal_name=signal,
                    signal_value=target,
                    observation_type=ObservationType.TRANSITION,
                    transition_from=(m.group("from") or "").strip(),
                    transition_to=target,
                    observation_group=observation_group,
                ))
                if timestamp_seconds is not None:
                    last_timestamped_value[signal.lower()] = (timestamp_seconds, target, clock_id)
                seq += 1
                continue

            m = self._direct_assignment_re.match(line)
            if m:
                ts_raw = m.group("ts")
                unit = (m.group("unit") or "").lower()
                timestamp_seconds = None
                anchor = ""
                if ts_raw is not None:
                    val = float(ts_raw)
                    timestamp_seconds = val / 1000.0 if unit == "ms" else val
                    anchor = f"{ts_raw} {m.group('unit')}"

                signal = m.group("signal").strip()
                value = m.group("value").strip().rstrip(".")
                observation_type = ObservationType.STATE_SAMPLE
                transition_from = ""
                transition_to = ""

                # Assignment-only transition inference. It is deliberately
                # conservative: a prior timestamped value for the same signal is
                # required, timestamps must advance, clocks must be compatible,
                # and the value must actually change. Repeated cyclic samples stay
                # STATE_SAMPLE and therefore never become interval evidence.
                if timestamp_seconds is not None:
                    prev = last_timestamped_value.get(signal.lower())
                    if prev is not None:
                        prev_ts, prev_value, prev_clock = prev
                        same_clock = (not prev_clock and not clock_id) or (prev_clock == clock_id)
                        if same_clock and timestamp_seconds > prev_ts and prev_value != value:
                            observation_type = ObservationType.TRANSITION
                            transition_from = prev_value
                            transition_to = value
                    last_timestamped_value[signal.lower()] = (timestamp_seconds, value, clock_id)

                result.append(EvidenceItem(
                    id=f"EVID-DIRECT-{seq:03d}",
                    evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                    text=line,
                    source="Direct Observations / Trace",
                    anchor=anchor,
                    timestamped=ts_raw is not None,
                    timestamp_seconds=timestamp_seconds,
                    coverage_complete=block_coverage_complete,
                    event_coverage_complete=block_event_coverage_complete,
                    clock_id=clock_id,
                    signal_name=signal,
                    signal_value=value,
                    observation_type=observation_type,
                    transition_from=transition_from,
                    transition_to=transition_to,
                    observation_group=observation_group,
                ))
                seq += 1
                continue

            m = self._direct_remained_re.match(line)
            if m and self.language_interval_parsing_enabled:
                result.append(EvidenceItem(
                    id=f"EVID-DIRECT-{seq:03d}",
                    evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                    text=line,
                    source="Direct Observations / Trace",
                    timestamped=False,
                    coverage_complete=True,
                    event_coverage_complete=block_event_coverage_complete,
                    clock_id=clock_id,
                    signal_name=m.group("signal").strip(),
                    signal_value=m.group("value").strip(),
                    observation_type=ObservationType.INTERVAL_STATE,
                    observation_group=observation_group,
                ))
                seq += 1
                continue
            # v0.8 production path: human-language statements such as
            # "remained X throughout the interval" stay UNSPECIFIED here and
            # are interpreted by the semantic compiler with surrounding context.

            result.append(EvidenceItem(
                id=f"EVID-DIRECT-{seq:03d}",
                evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text=line,
                source="Direct Observations / Trace",
                coverage_complete=block_coverage_complete,
                event_coverage_complete=block_event_coverage_complete,
                clock_id=clock_id,
                observation_group=observation_group,
            ))
            seq += 1

        if not result:
            result.append(EvidenceItem(
                id="EVID-DIRECT-001",
                evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text=direct_text.strip(),
                source="Direct Observations / Trace",
                coverage_complete=block_coverage_complete,
                event_coverage_complete=block_event_coverage_complete,
                clock_id=clock_id,
                observation_group=observation_group,
            ))
        return result

    @staticmethod
    def _clean_lines(lines: Iterable[str]) -> str:
        vals = [x.strip() for x in lines]
        while vals and not vals[0]:
            vals.pop(0)
        while vals and not vals[-1]:
            vals.pop()
        return "\n".join(vals).strip()

    def _single_line_value(self, lines: list[str], label: str) -> str:
        pat = re.compile(rf"^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", re.I)
        for i, line in enumerate(lines):
            m = pat.match(line)
            if not m:
                continue
            if m.group(1).strip():
                return m.group(1).strip()
            for nxt in lines[i + 1 :]:
                if nxt.strip():
                    return nxt.strip()
        return ""

    def _multiline_field(
        self,
        lines: list[str],
        label: str,
        stop_labels: tuple[str, ...] = (),
        stop_headings: Optional[Set[str]] = None,
    ) -> str:
        pat = re.compile(rf"^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", re.I)
        start = None
        inline = ""
        for i, line in enumerate(lines):
            m = pat.match(line)
            if m:
                start = i + 1
                inline = m.group(1).strip()
                break
        if start is None:
            return ""

        collected: list[str] = [inline] if inline else []
        stop_label_patterns = [re.compile(rf"^\s*{re.escape(x)}\s*:\s*", re.I) for x in stop_labels]
        for line in lines[start:]:
            stripped = line.strip()
            if any(p.match(line) for p in stop_label_patterns):
                break
            if stop_headings and stripped.upper() in stop_headings:
                break
            # A new well-known field also ends Reported Test Result / Description.
            if re.match(r"^\s*(Ticket ID|Title|Description|Test Steps|Reported Test Result)\s*:\s*", line, re.I):
                break
            collected.append(line)
        return self._clean_lines(collected)

    def _extract_test_steps(self, lines: list[str]) -> list[str]:
        start = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*Test Steps\s*:\s*$", line, re.I):
                start = i + 1
                break
        if start is None:
            return []

        result: list[str] = []
        for line in lines[start:]:
            if re.match(r"^\s*Reported Test Result\s*:", line, re.I):
                break
            if line.strip().upper() in self.major_headings:
                break
            m = self.numbered_step_re.match(line)
            if m:
                result.append(m.group(2).strip())
            elif line.strip() and result:
                # Wrapped continuation of the previous step.
                result[-1] = f"{result[-1]} {line.strip()}".strip()
        return result

    def _extract_requirements(self, lines: list[str]) -> list[RequirementSource]:
        try:
            start = next(i for i, x in enumerate(lines) if x.strip().upper() == "SYSTEM REQUIREMENTS") + 1
        except StopIteration:
            start = 0  # fallback: scan the complete text for explicit REQ identifiers

        result: list[RequirementSource] = []
        current_id = ""
        current_lines: list[str] = []

        def flush():
            nonlocal current_id, current_lines
            text = self._clean_lines(current_lines)
            if current_id and text:
                result.append(RequirementSource(requirement_id=current_id, requirement_text=text))
            current_id = ""
            current_lines = []

        for line in lines[start:]:
            stripped = line.strip()
            if start > 0 and stripped.upper() in self.major_headings and stripped.upper() != "SYSTEM REQUIREMENTS":
                flush()
                break
            m = self.req_id_re.match(line)
            if m:
                flush()
                current_id = m.group(1).strip()
                continue
            if current_id:
                current_lines.append(line)
        flush()
        return result

    def _section_text(self, lines: list[str], headings: tuple[str, ...], all_headings: set[str]) -> str:
        heading_set = {x.upper() for x in headings}
        start = None
        for i, line in enumerate(lines):
            if line.strip().upper() in heading_set:
                start = i + 1
                break
        if start is None:
            return ""
        collected: list[str] = []
        for line in lines[start:]:
            stripped = line.strip()
            if stripped.upper() in all_headings:
                break
            collected.append(line)
        return self._clean_lines(collected)

    @staticmethod
    def _is_none_block(text: str) -> bool:
        normalized = " ".join(text.lower().strip().rstrip(".").split())
        return not normalized or normalized in _NONE_MARKERS
