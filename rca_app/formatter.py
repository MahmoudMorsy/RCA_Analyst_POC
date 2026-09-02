from __future__ import annotations

from .models import (
    Applicability,
    EvaluationStatus,
    EvidenceClass,
    NormativeType,
    ValidatedAnalysis,
)


class FinalReportFormatter:
    def format(self, validated: ValidatedAnalysis) -> str:
        s = validated.semantic
        evidence = {e.id: e for e in s.evidence_inventory}
        lines: list[str] = []

        lines += ["# 1. Affected Functionality", "", s.affected_functionality.strip() or "Not explicitly established from the supplied information.", ""]

        lines += ["# 2. Relevant Requirements", ""]
        for rr in validated.requirement_results:
            r = rr.analysis
            lines += [f"**{r.requirement_id}**", r.requirement_text.strip(), "", f"Faithful meaning: {r.faithful_meaning.strip()}", "", f"Relevance: {r.relevance.strip()}", ""]

        lines += ["# 3. Expected System Behavior", ""]
        if validated.requirement_results:
            for rr in validated.requirement_results:
                r = rr.analysis
                lines.append(f"- **{r.requirement_id}:** {r.requirement_text.strip()}")
        else:
            lines.append("No relevant system requirements were supplied or selected.")
        lines.append("")

        lines += ["# 4. Relevant Historical Tickets", ""]
        if not s.historical_tickets:
            lines.append("No historical tickets were supplied for comparison.")
        else:
            for h in s.historical_tickets:
                lines.append(f"**{h.ticket_id}** — {h.summary.strip()}")
                if h.similarities:
                    lines.append("- Similarities: " + "; ".join(x.strip() for x in h.similarities if x.strip()))
                if h.differences:
                    lines.append("- Differences: " + "; ".join(x.strip() for x in h.differences if x.strip()))
        lines.append("")

        lines += ["# 5. Diagnostic Evidence", ""]
        diagnostic_items = [evidence[eid] for eid in s.diagnostic_evidence_ids if eid in evidence]
        if not diagnostic_items:
            lines.append("No diagnostic or BZD evidence was supplied.")
        else:
            for item in diagnostic_items:
                lines.append(f"- {self._evidence_line(item)}")
            temporal = self._diagnostic_temporal_summary(diagnostic_items)
            if temporal:
                lines += ["", "**Temporal diagnostic comparison:**"]
                for item in temporal:
                    lines.append(f"- {item}")
        lines.append("")

        lines += ["# 6. Confirmed Findings", ""]
        confirmed = [e for e in s.evidence_inventory if e.evidence_class in {EvidenceClass.REPORTED_OBSERVATION, EvidenceClass.DIRECT_OBSERVATION}]
        if not confirmed:
            lines.append("No confirmed findings are available from the supplied evidence.")
        else:
            for item in confirmed:
                prefix = "Reported observation" if item.evidence_class == EvidenceClass.REPORTED_OBSERVATION else "Direct observation"
                anchor = f", {item.anchor}" if item.anchor else ""
                lines.append(f"- {prefix} — {item.text.strip()} Source: {item.source}{anchor}.")
        if validated.evidence_conflicts:
            lines += ["", "**Evidence conflicts:**"]
            for conflict in validated.evidence_conflicts:
                lines.append(f"- {conflict.description.strip()} {conflict.resolution.strip()}")
        lines.append("")

        lines += ["# 7. Requirement Evaluation", ""]
        lines.append("| Requirement ID | Normative Type | Applicability | Evaluation Status | Applicability Evidence | Evaluation Evidence | Missing Evidence |")
        lines.append("|---|---|---|---|---|---|---|")
        for rr in validated.requirement_results:
            r = rr.analysis
            app_ev_text = self._requirement_evidence_text(r.applicability_evidence_ids, evidence)
            eval_ev_text = self._requirement_evidence_text(r.evaluation_evidence_ids, evidence)
            if rr.timing_fact is not None:
                timing_text = self._timing_fact_text(rr.timing_fact)
                eval_ev_text = f"{eval_ev_text}; Deterministic timing: {timing_text}" if eval_ev_text else f"Deterministic timing: {timing_text}"
            missing = self._missing_evidence_cell(r)
            lines.append(
                f"| {self._esc(r.requirement_id)} | {r.normative_type.value} | {r.applicability.value} | {rr.evaluation_status.value} | {self._esc(app_ev_text)} | {self._esc(eval_ev_text)} | {self._esc(missing)} |"
            )
        lines.append("")

        lines += ["# 8. Evidence-Backed Hypotheses", ""]
        if not validated.hypotheses:
            lines.append("No evidence-backed failure hypothesis can currently be established.")
        else:
            for h in validated.hypotheses:
                support = ", ".join(h.supporting_evidence_ids)
                weakening = ", ".join(h.weakening_evidence_ids) if h.weakening_evidence_ids else "None supplied"
                refs = ", ".join(h.source_references) if h.source_references else support
                lines += [
                    f"**Hypothesis:** {h.hypothesis.strip()}",
                    f"- Positive supporting evidence: {support}",
                    f"- Weakening or contradicting evidence: {weakening}",
                    f"- Source references: {refs}",
                    f"- Confidence: {h.confidence.upper()}",
                    "",
                ]

        lines += ["# 9. Missing Information", ""]
        for rr in validated.requirement_results:
            r = rr.analysis
            lines.append(f"**{r.requirement_id}**")
            if r.applicability == Applicability.NOT_APPLICABLE:
                app_text = "None additionally required; applicability is resolved as NOT APPLICABLE by supplied current-case evidence."
                eval_text = "Not required because the requirement is not applicable in the current case."
            else:
                app_text = self._needs_text(r.missing_applicability_evidence)
                if r.normative_type == NormativeType.PERMISSIVE:
                    eval_text = "None additionally required for a compliance verdict (permissive requirement)."
                else:
                    eval_text = self._needs_text(r.missing_evaluation_evidence)
            lines.append(f"- **Applicability Evidence:** {app_text}")
            lines.append(f"- **Evaluation Evidence:** {eval_text}")
            lines.append("")

        lines += ["# 10. Minimum Next Evidence Required", "", "**Compliance Evidence**", ""]
        if validated.compliance_evidence:
            for item in validated.compliance_evidence:
                lines.append(f"- {item}")
        else:
            lines.append("No additional compliance evidence is currently selected as a minimum next step.")
        if validated.case_validity_evidence:
            lines += ["", "**Case-Validity Evidence**", ""]
            for item in validated.case_validity_evidence:
                lines.append(f"- Ticket assertion: {item.ticket_assertion.strip()} — Evidence needed: {item.evidence_needed.strip()}")
        lines.append("")

        lines += ["# 11. Overall Assessment", ""]
        established = [e.text.strip() for e in confirmed]
        if established:
            lines.append("**Established:**")
            for item in established:
                lines.append(f"- {item}")
            lines.append("")
        else:
            lines.append("**Established:** No confirmed current-case findings are available from the supplied evidence.")

        states = []
        for rr in validated.requirement_results:
            states.append(f"{rr.analysis.requirement_id}: {rr.evaluation_status.value} ({rr.analysis.applicability.value})")
        if states:
            lines.append("**Requirement status:** " + "; ".join(states) + ".")

        timing_summaries = [
            f"{rr.analysis.requirement_id}: {self._timing_fact_text(rr.timing_fact)}"
            for rr in validated.requirement_results
            if rr.timing_fact is not None
        ]
        if timing_summaries:
            lines.append("**Deterministic timing:** " + "; ".join(timing_summaries) + ".")

        if validated.evidence_conflicts:
            lines.append("**Evidence conflicts:** " + "; ".join(c.description.strip() for c in validated.evidence_conflicts) + ".")

        if validated.hypotheses:
            clean_hypotheses = [h.hypothesis.strip().rstrip(".; ") for h in validated.hypotheses]
            lines.append("**Supported hypotheses:** " + "; ".join(clean_hypotheses) + ".")
        else:
            lines.append("**Supported hypotheses:** None.")

        if validated.compliance_evidence:
            lines.append("**Minimum evidence needed next:** " + "; ".join(x.rstrip(".; ") for x in validated.compliance_evidence) + ".")
        else:
            lines.append("**Minimum evidence needed next:** No additional compliance evidence is currently selected.")

        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _diagnostic_temporal_summary(items) -> list[str]:
        """Derive non-causal before/after DTC status labels from supplied text."""
        import re

        before: dict[str, bool] = {}
        after: dict[str, bool] = {}
        descriptions: dict[str, str] = {}

        phase_re = re.compile(
            r"(?P<label>Before\s+(?:test|failure)|After\s+(?:failure|test))\s*:\s*(?P<body>.*?)(?=(?:Before\s+(?:test|failure)|After\s+(?:failure|test))\s*:|$)",
            re.I | re.S,
        )
        dtc_re = re.compile(
            r"DTC\s+(?P<code>[A-Za-z0-9_-]+)\s*(?P<desc>.*?)(?:\bwas\s+(?P<not>not\s+)?(?:still\s+)?present\b)",
            re.I | re.S,
        )

        combined = "\n".join(getattr(x, "text", "") or "" for x in items)
        for phase in phase_re.finditer(combined):
            label = phase.group("label").lower()
            target = before if label.startswith("before") else after
            body = phase.group("body")
            for m in dtc_re.finditer(body):
                code = m.group("code").upper()
                target[code] = not bool(m.group("not"))
                desc = " ".join((m.group("desc") or "").replace("\n", " ").split()).strip(" .-:")
                if desc:
                    descriptions.setdefault(code, desc)

        # Fallback for blocks that contain an after-only heading but no regex
        # phase match because prose follows on separate bullet lines.
        if not before and not after:
            lower = combined.lower()
            phase = "after" if "after failure only" in lower or "after failure:" in lower else ""
            if phase:
                for m in dtc_re.finditer(combined):
                    code = m.group("code").upper()
                    after[code] = not bool(m.group("not"))
                    desc = " ".join((m.group("desc") or "").replace("\n", " ").split()).strip(" .-:")
                    if desc:
                        descriptions.setdefault(code, desc)

        codes = sorted(set(before) | set(after))
        out: list[str] = []
        for code in codes:
            label = f"DTC {code}"
            if descriptions.get(code):
                label += f" {descriptions[code]}"
            b = before.get(code)
            a = after.get(code)
            if b is True and a is True:
                status = "present before and after (pre-existing / unchanged)."
            elif b is False and a is True:
                status = "absent before and present after (newly present after the failure)."
            elif b is True and a is False:
                status = "present before and absent after (cleared after the test/failure)."
            elif b is False and a is False:
                status = "absent before and after."
            elif a is True and b is None:
                status = "present in the after snapshot; pre-test state is unknown, so it cannot be classified as newly introduced."
            elif a is False and b is None:
                status = "absent in the after snapshot; pre-test state is unknown."
            elif b is True and a is None:
                status = "present in the before snapshot; no after-state comparison is available."
            elif b is False and a is None:
                status = "absent in the before snapshot; no after-state comparison is available."
            else:
                continue
            out.append(f"{label} — {status}")
        return out

    @staticmethod
    def _timing_fact_text(fact) -> str:
        relation = "within" if fact.outcome.value == "WITHIN_LIMIT" else "exceeds"
        if fact.outcome.value == "WITHIN_LIMIT":
            margin = abs(fact.margin_ms)
            detail = f"{margin:g} ms inside the limit"
        else:
            detail = f"{fact.margin_ms:g} ms beyond the limit"
        clock = f", clock {fact.clock_id}" if fact.clock_id else ""
        return (
            f"{fact.elapsed_ms:g} ms observed vs {fact.limit_ms:g} ms allowed "
            f"({relation} limit; {detail}){clock}"
        )

    @staticmethod
    def _needs_text(needs) -> str:
        vals = [FinalReportFormatter._humanize_need(n.description) for n in needs if n.description.strip()]
        vals = [v for v in vals if v]
        return "; ".join(vals) if vals else "None additionally required."

    @staticmethod
    def _humanize_need(text: str) -> str:
        """Remove internal taxonomy/debug phrasing from analyst-facing evidence asks."""
        import re
        t = " ".join(text.strip().split())
        t = re.sub(r"\s*\((?:e\.g\.,?\s*)?(?:DIRECT_OBSERVATION|REPORTED_OBSERVATION)(?:\s+or\s+(?:DIRECT_OBSERVATION|REPORTED_OBSERVATION))*\)", "", t, flags=re.I)
        t = re.sub(r"\bDIRECT_OBSERVATION\b", "direct observation", t, flags=re.I)
        t = re.sub(r"\bREPORTED_OBSERVATION\b", "reported observation", t, flags=re.I)
        # Internal comments about why TEST_INSTRUCTION is insufficient belong in
        # validation diagnostics, not the final analyst report.
        t = re.sub(r"\s*No supplied current-case evidence \(other than the TEST_INSTRUCTION.*$", "", t, flags=re.I)
        t = re.sub(r"\bTEST_INSTRUCTION\b", "test instruction", t, flags=re.I)
        return t.strip().rstrip(";.")

    @staticmethod
    def _requirement_evidence_text(ids, evidence) -> str:
        vals = []
        for eid in ids:
            item = evidence.get(eid)
            if not item:
                continue
            anchor = f" [{item.anchor}]" if item.anchor else ""
            vals.append(f"{item.text.strip()} (Source: {item.source}{anchor})")
        return "; ".join(vals) if vals else "None observed."

    @staticmethod
    def _missing_evidence_cell(r) -> str:
        if r.applicability == Applicability.NOT_APPLICABLE:
            return "Applicability: None additionally required; resolved as NOT APPLICABLE. Evaluation: Not required for this case."
        app = FinalReportFormatter._needs_text(r.missing_applicability_evidence).rstrip(".")
        if r.normative_type == NormativeType.PERMISSIVE:
            ev = "None additionally required for a compliance verdict (permissive requirement)"
        else:
            ev = FinalReportFormatter._needs_text(r.missing_evaluation_evidence).rstrip(".")
        return f"Applicability: {app}. Evaluation: {ev}"

    @staticmethod
    def _evidence_line(item) -> str:
        anchor = f", {item.anchor}" if item.anchor else ""
        return f"{item.text.strip()} Source: {item.source}{anchor}."

    @staticmethod
    def _esc(text: str) -> str:
        return text.replace("|", "\\|").replace("\n", " ")
