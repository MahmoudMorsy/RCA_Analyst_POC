from __future__ import annotations

import copy
from typing import Iterable

from .models import (
    AtomicClaimExtractionSet,
    CanonicalAtomicClaim,
    CanonicalCase,
    IntakeContentClassification,
    IntakeField,
    IntakeNormalization,
    IntakeRequirementSection,
    IntakeSourceSection,
    RequirementLanguageNormalizationSet,
    PredicateOperator,
    SemanticAnalysis,
    SourceAvailability,
    SourceAvailabilityDecision,
    SourceAvailabilityNormalization,
)


class FastSemanticPreprocessor:
    """Python glue around the v0.7.0 small 4B language stages.

    The model stages interpret language. This class does not infer semantic
    meaning from phrases. It only verifies verbatim source spans, combines the
    independent structured outputs, assigns canonical claim IDs/parent evidence
    links, and enforces the already-normalized source-availability contract.
    """

    @staticmethod
    def _normalized(text: str) -> str:
        return " ".join((text or "").split()).strip().lower()

    @classmethod
    def span_supported(cls, raw_case: str, span: str) -> bool:
        span = (span or "").strip()
        if not span:
            return False
        if span in raw_case:
            return True
        return cls._normalized(span) in cls._normalized(raw_case)

    @classmethod
    def _verified_field(cls, raw_case: str, field: IntakeField) -> IntakeField:
        if not cls.span_supported(raw_case, field.source_span):
            return IntakeField()
        return copy.deepcopy(field)

    @classmethod
    def _verified_fields(cls, raw_case: str, fields: Iterable[IntakeField]) -> list[IntakeField]:
        return [x for x in (cls._verified_field(raw_case, f) for f in fields) if x.source_span.strip()]

    @classmethod
    def combine_intake(
        cls,
        raw_case: str,
        availability: SourceAvailabilityNormalization,
        content: IntakeContentClassification,
    ) -> IntakeNormalization:
        """Combine two independent 4B outputs without reinterpreting language.

        Availability owns whether a source may contain engineering content.
        Content classification owns the extracted source-backed blocks. Python
        simply discards blocks for any source the availability stage classified
        as non-PRESENT.
        """

        def section(decision: SourceAvailabilityDecision, blocks: Iterable[IntakeField]) -> IntakeSourceSection:
            verified_statement = cls._verified_field(raw_case, decision.availability_statement)
            verified_blocks = cls._verified_fields(raw_case, blocks) if decision.availability == SourceAvailability.PRESENT else []
            if decision.availability in {SourceAvailability.ABSENT, SourceAvailability.UNKNOWN} and not verified_statement.source_span.strip():
                # Preserve structural honesty rather than inventing an absence phrase.
                # UNKNOWN is safer when a model classification lacks a source-backed statement.
                return IntakeSourceSection(availability=SourceAvailability.NOT_MENTIONED)
            return IntakeSourceSection(
                availability=decision.availability,
                blocks=verified_blocks,
                availability_statement=verified_statement,
            )

        req_decision = availability.requirements
        req_items = []
        if req_decision.availability == SourceAvailability.PRESENT:
            for req in content.requirements:
                if cls.span_supported(raw_case, req.source_span):
                    req_items.append(copy.deepcopy(req))
        req_statement = cls._verified_field(raw_case, req_decision.availability_statement)
        if req_decision.availability in {SourceAvailability.ABSENT, SourceAvailability.UNKNOWN} and not req_statement.source_span.strip():
            req_availability = SourceAvailability.NOT_MENTIONED
        else:
            req_availability = req_decision.availability
        requirements = IntakeRequirementSection(
            availability=req_availability,
            items=req_items if req_availability == SourceAvailability.PRESENT else [],
            availability_statement=req_statement if req_availability != SourceAvailability.NOT_MENTIONED else IntakeField(),
        )

        return IntakeNormalization(
            ticket_id=cls._verified_field(raw_case, content.ticket_id),
            title=cls._verified_field(raw_case, content.title),
            description=cls._verified_field(raw_case, content.description),
            test_steps=cls._verified_fields(raw_case, content.test_steps),
            reported_results=cls._verified_fields(raw_case, content.reported_results),
            requirements=requirements,
            historical=section(availability.historical, content.historical_blocks),
            diagnostics=section(availability.diagnostics, content.diagnostic_blocks),
            trace=section(availability.trace, content.trace_blocks),
            user_instructions=cls._verified_fields(raw_case, content.user_instructions),
            unclassified_spans=[x for x in content.unclassified_spans if cls.span_supported(raw_case, x)],
            notes=list(content.notes),
        )

    @classmethod
    def attach_atomic_claims(
        cls,
        raw_case: str,
        canonical: CanonicalCase,
        extracted: AtomicClaimExtractionSet,
    ) -> CanonicalCase:
        out = copy.deepcopy(canonical)
        claims: list[CanonicalAtomicClaim] = []
        for item in extracted.claims:
            span = (item.source_span or "").strip()
            if not cls.span_supported(raw_case, span):
                continue
            parent = cls._find_parent_evidence(canonical, span, item.source_category)
            if not parent:
                continue
            claims.append(CanonicalAtomicClaim(
                claim_id=f"CLAIM-{len(claims) + 1:03d}",
                parent_evidence_id=parent,
                source_category=item.source_category,
                source_span=span,
                claim_text=item.claim_text.strip(),
                claim_kind=item.claim_kind,
                subject=item.subject.strip(),
                predicate=item.predicate.strip(),
                object_value=item.object_value.strip(),
                numeric_value=item.numeric_value,
                numeric_unit=item.numeric_unit.strip(),
                timing_assessment=item.timing_assessment,
                causal_strength=item.causal_strength,
            ))
        out.atomic_claims = claims
        if claims:
            out.parser_notes.append(f"FAST_ATOMIC_CLAIMS_ATTACHED: {len(claims)} source-backed atomic claim(s) were linked to canonical evidence.")
        return out

    @classmethod
    def attach_requirement_language(
        cls,
        canonical: CanonicalCase,
        normalized: RequirementLanguageNormalizationSet,
    ) -> CanonicalCase:
        out = copy.deepcopy(canonical)
        known = {r.requirement_id: r for r in canonical.requirements}
        accepted = []
        for item in normalized.requirements:
            source = known.get(item.requirement_id)
            if source is None:
                continue
            # Source phrases are optional model annotations. When supplied they
            # must be grounded in the authoritative requirement text.
            valid = True
            for group in item.applicability_any_of:
                for pred in group.predicates:
                    phrase = (pred.source_phrase or "").strip()
                    if phrase and cls._normalized(phrase) not in cls._normalized(source.requirement_text):
                        valid = False
                        break
                if not valid:
                    break
            if valid:
                cleaned = copy.deepcopy(item)
                # The 4B stage owns language interpretation, but Python enforces
                # the normalized field contract. Applicability groups may contain
                # only conditional/scope predicates, never the separately-declared
                # trigger or required-behavior signal.
                trigger_signal = cleaned.trigger_signal.strip().lower()
                behavior_signal = cleaned.required_behavior_signal.strip().lower()
                cleaned_groups = []
                for group in cleaned.applicability_any_of:
                    predicates = []
                    for pred in group.predicates:
                        signal = pred.signal.strip().lower()
                        if behavior_signal and signal == behavior_signal:
                            continue
                        if trigger_signal and signal == trigger_signal:
                            continue
                        predicates.append(copy.deepcopy(pred))
                    if predicates:
                        new_group = copy.deepcopy(group)
                        new_group.predicates = predicates
                        cleaned_groups.append(new_group)
                cleaned.applicability_any_of = cleaned_groups
                accepted.append(cleaned)
        out.requirement_language = accepted
        if accepted:
            out.parser_notes.append(f"FAST_REQUIREMENT_LANGUAGE_ATTACHED: {len(accepted)} requirement-language normalization object(s) were retained as non-authoritative semantic hints.")
        return out

    @staticmethod
    def _format_ms(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(value)

    @classmethod
    def apply_requirement_language_hints(
        cls,
        semantic: SemanticAnalysis,
        canonical: CanonicalCase,
    ) -> SemanticAnalysis:
        """Project already-normalized 4B language fields into missing Phase-A fields.

        This performs no natural-language interpretation. It only formats
        structured trigger/timing/persistence fields already supplied by the
        language-normalization stage, while leaving non-empty 27B fields intact
        except that an explicit numeric timing hint is canonicalized to the
        machine-readable ``within N ms`` form.
        """
        out = copy.deepcopy(semantic)
        hints = {x.requirement_id: x for x in canonical.requirement_language}
        for req in out.requirements:
            hint = hints.get(req.requirement_id)
            if hint is None:
                continue

            if not req.trigger.strip() and hint.trigger_signal.strip() and hint.trigger_event.strip():
                if hint.trigger_value.strip():
                    req.trigger = f"{hint.trigger_signal.strip()} becomes {hint.trigger_value.strip()}"
                else:
                    req.trigger = hint.trigger_signal.strip()

            if hint.timing_limit_ms is not None:
                req.timing_constraint = f"within {cls._format_ms(hint.timing_limit_ms)} ms"

            if not req.required_behavior.strip() and hint.required_behavior_signal.strip():
                signal = hint.required_behavior_signal.strip()
                value = hint.required_behavior_value.strip()
                op = hint.required_behavior_operator
                if op == PredicateOperator.EQ and value:
                    req.required_behavior = f"{signal} shall be {value}"
                elif op == PredicateOperator.NEQ and value:
                    req.required_behavior = f"{signal} shall not be {value}"
                elif value:
                    req.required_behavior = f"{signal} {value}"
                else:
                    req.required_behavior = signal

            if hint.persistence_required and not req.observation_interval_requirement.strip():
                signal = hint.required_behavior_signal.strip() or "the required behavior"
                value = hint.required_behavior_value.strip()
                if value:
                    req.observation_interval_requirement = (
                        f"{signal} must be observed continuously in the required {value} state throughout the applicable interval."
                    )
                else:
                    req.observation_interval_requirement = (
                        f"{signal} must be observed continuously throughout the applicable interval."
                    )
        return out

    @classmethod
    def _find_parent_evidence(cls, canonical: CanonicalCase, span: str, source_category: str) -> str:
        normalized_span = cls._normalized(span)
        category = (source_category or "").upper()
        preferred = []
        if "REPORTED" in category:
            preferred = [e for e in canonical.evidence_inventory if e.evidence_class.value == "REPORTED_OBSERVATION"]
        elif "DIAGNOSTIC" in category or "BZD" in category:
            preferred = [e for e in canonical.evidence_inventory if e.source == "Current BZD / Diagnostics"]
        elif "HISTOR" in category:
            preferred = [e for e in canonical.evidence_inventory if e.evidence_class.value == "HISTORICAL_EVIDENCE"]
        elif "DESCRIPTION" in category or "TICKET" in category:
            preferred = [e for e in canonical.evidence_inventory if e.evidence_class.value == "CURRENT_TICKET"]
        candidates = preferred or list(canonical.evidence_inventory)
        for evidence in candidates:
            haystacks = [evidence.raw_source_text, evidence.text]
            if any(normalized_span in cls._normalized(x) or cls._normalized(x) in normalized_span for x in haystacks if x):
                return evidence.id
        return ""
