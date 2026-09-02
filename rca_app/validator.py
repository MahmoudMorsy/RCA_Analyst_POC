from __future__ import annotations

import copy
import re
from collections import OrderedDict

from typing import Optional

from .models import (
    Applicability,
    AtomicTimingAssessment,
    CanonicalCase,
    EvaluationStatus,
    EvidenceClass,
    EvidenceConflict,
    EvidenceNeed,
    HypothesisSupportBasis,
    NormativeType,
    ObservationType,
    PredicateOperator,
    RequirementElementType,
    RequirementResult,
    SemanticAnalysis,
    Sufficiency,
    TimingFact,
    TimingOutcome,
    ValidatedAnalysis,
    ValidationIssue,
    ValidationSeverity,
)


OBSERVATION_CLASSES = {
    EvidenceClass.REPORTED_OBSERVATION,
    EvidenceClass.DIRECT_OBSERVATION,
}


class DeterministicValidator:
    """Mechanical enforcement layer for the RCA analysis contract.

    v0.5.5 preserves the v0.5.2 state/interval/event-coverage baseline and extends the asymmetric evidence model: a point counterexample can prove nonconformance (including prohibitive/persistence obligations), while a point match cannot prove interval-wide conformance. It also enforces source accounting for supplied historical/relationship context and derives explicit deterministic evidence conflicts. It treats source boundaries as
    authoritative, verifies requirement decomposition completeness, checks that
    relevant observations are actually mapped, verifies timing/persistence
    evidence buckets, and derives Section-10 evidence by dependency closure.
    """

    forbidden_process_terms = (
        "processed",
        "validated",
        "blocked",
        "handled",
        "acknowledged",
        "approved",
    )
    causal_terms = (
        "prevented",
        "caused by",
        "because of",
        "due to",
        "resulted from",
        "root cause",
        "possible cause",
        "potential mechanism",
        "alternative explanation",
        "could explain",
        "rule out",
        "appears to contradict",
        "rather than because",
        "rather than a failure",
        "could be a correct response",
        "explain",
        "explains",
        "explained",
        "explaining",
        "explanation",
    )
    internal_rule_pattern = re.compile(r"\b(?:INV|EV|NT|AP|EC|HG|HT|DX)-\d", re.I)
    timing_wording = re.compile(r"\bwithin\s+\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds?|minutes?|min)\b", re.I)
    persistence_wording = re.compile(r"\bremain\b|\bthroughout\b|\bshall\s+not\b|\bmust\s+not\b|\bnever\b", re.I)
    if_wording = re.compile(r"\bif\b", re.I)
    trigger_wording = re.compile(r"\bwhen\b|\bupon\b", re.I)

    @staticmethod
    def _has_true_persistence_semantics(req) -> bool:
        """Return True only when the requirement itself imposes persistence/non-occurrence.

        A timed transition such as "shall become ACTIVE within 500 ms" also
        requires interval coverage, but it is *not* a persistence requirement.
        v0.3 incorrectly treated any non-empty observation_interval_requirement
        as persistence, which produced false closure errors for timed transitions.
        """
        text = " ".join([
            req.requirement_text or "",
            req.required_behavior or "",
        ]).lower()
        return bool(re.search(
            r"\bremain(?:s|ed|ing)?\b|\bstay(?:s|ed|ing)?\b|\bpersist(?:s|ed|ing|ence)?\b|"
            r"\bthroughout\b|\bshall\s+not\b|\bmust\s+not\b|\bnever\b",
            text,
            re.I,
        ))

    @staticmethod
    def _needs_interval_coverage(req) -> bool:
        """Whether evaluation needs coverage over an interval for any reason."""
        return bool(req.timing_constraint.strip() or req.observation_interval_requirement.strip())

    def normalize_and_validate(self, semantic: SemanticAnalysis, canonical_case: Optional[CanonicalCase] = None) -> ValidatedAnalysis:
        data = copy.deepcopy(semantic)
        issues: list[ValidationIssue] = []

        if canonical_case is not None:
            # Source classification is not an LLM decision in v0.2.
            data.evidence_inventory = copy.deepcopy(canonical_case.evidence_inventory)
            self._validate_canonical_source_boundaries(canonical_case, issues)

        evidence = {e.id: e for e in data.evidence_inventory}
        if len(evidence) != len(data.evidence_inventory):
            issues.append(self._issue("DUPLICATE_EVIDENCE_ID", "semantic.evidence_inventory", "Duplicate evidence IDs were returned."))

        if canonical_case is not None:
            self._normalize_and_validate_source_accounting(data, canonical_case, evidence, issues)

        expected_requirements = {
            r.requirement_id: r.requirement_text for r in (canonical_case.requirements if canonical_case else [])
        }
        returned_ids = [r.requirement_id for r in data.requirements]
        if expected_requirements:
            missing = [rid for rid in expected_requirements if rid not in returned_ids]
            extra = [rid for rid in returned_ids if rid not in expected_requirements]
            for rid in missing:
                issues.append(self._issue("MISSING_REQUIREMENT_ANALYSIS", "semantic.requirements", f"Required analysis for {rid} is missing."))
            for rid in extra:
                issues.append(self._issue("UNKNOWN_REQUIREMENT_ANALYSIS", "semantic.requirements", f"Analysis contains unknown requirement {rid}."))

        req_ids: set[str] = set()
        results: list[RequirementResult] = []

        for idx, req in enumerate(data.requirements):
            path = f"semantic.requirements[{idx}]"
            if req.requirement_id in req_ids:
                issues.append(self._issue("DUPLICATE_REQUIREMENT_ID", path, f"Duplicate requirement ID {req.requirement_id}."))
            req_ids.add(req.requirement_id)

            if req.requirement_id in expected_requirements:
                authoritative = expected_requirements[req.requirement_id]
                if req.requirement_text.strip() != authoritative.strip():
                    issues.append(self._warn(
                        "REQUIREMENT_TEXT_RESTORED",
                        f"{path}.requirement_text",
                        "LLM requirement text differed from canonical input and was restored to the authoritative source text.",
                    ))
                req.requirement_text = authoritative

            forced_type = self._deterministic_normative_type(req.requirement_text)
            if forced_type is not None and req.normative_type != forced_type:
                issues.append(self._warn(
                    "NORMATIVE_TYPE_CORRECTED",
                    f"{path}.normative_type",
                    f"Corrected {req.normative_type.value} to {forced_type.value} from explicit requirement wording.",
                ))
                req.normative_type = forced_type

            self._normalize_empty_semantic_sentinels(req, path, issues)
            self._validate_decomposition(req, path, issues)

            req.applicability_evidence_ids = self._existing_ids(
                req.applicability_evidence_ids, evidence, issues, f"{path}.applicability_evidence_ids"
            )
            req.evaluation_evidence_ids = self._existing_ids(
                req.evaluation_evidence_ids, evidence, issues, f"{path}.evaluation_evidence_ids"
            )

            valid_app_ids: list[str] = []
            for eid in req.applicability_evidence_ids:
                item = evidence[eid]
                allowed = item.evidence_class in OBSERVATION_CLASSES or (
                    item.evidence_class == EvidenceClass.CURRENT_TICKET and item.scope_metadata
                )
                if allowed:
                    valid_app_ids.append(eid)
                else:
                    issues.append(self._warn(
                        "INVALID_APPLICABILITY_SOURCE_REMOVED",
                        f"{path}.applicability_evidence_ids",
                        f"Removed {eid} ({item.evidence_class.value}); it cannot establish applicability.",
                    ))
            req.applicability_evidence_ids = valid_app_ids

            # v0.4.3: a state sample showing the target value is not equivalent to
            # observing a transition event. Trigger wording such as "becomes ACTIVE"
            # requires an explicitly parsed TRANSITION observation before APPLICABLE
            # can be preserved. The sample may remain as partial evidence for UNKNOWN.
            if (
                req.applicability == Applicability.APPLICABLE
                and self._requires_transition_semantics(req.trigger)
                and not any(
                    self._transition_matches_text(evidence[eid], req.trigger)
                    for eid in req.applicability_evidence_ids
                    if eid in evidence
                )
            ):
                req.applicability = Applicability.UNKNOWN
                issues.append(self._warn(
                    "TRIGGER_TRANSITION_NOT_ESTABLISHED",
                    f"{path}.applicability",
                    "APPLICABLE was based on state/context evidence, but the requirement trigger is a transition event and no canonical TRANSITION observation establishes that event; corrected to APPLICABILITY UNKNOWN.",
                ))

            # A transition-trigger requirement cannot be declared NOT APPLICABLE
            # merely because the trace starts with the target state already present.
            # Even event_coverage_complete only excludes omitted events *inside* the
            # supplied trace scope; it does not prove that the trigger did not occur
            # before that scope began. Preserve NOT APPLICABLE only when an explicit
            # parent/scope relationship is itself established as absent.
            if (
                req.applicability == Applicability.NOT_APPLICABLE
                and self._requires_transition_semantics(req.trigger)
                and not self._has_trigger_not_applicable_scope_evidence(req, evidence)
            ):
                req.applicability = Applicability.UNKNOWN
                if req.evaluation_sufficiency == Sufficiency.NOT_REQUIRED:
                    req.evaluation_sufficiency = Sufficiency.INSUFFICIENT
                issues.append(self._warn(
                    "TRIGGER_NOT_APPLICABLE_SCOPE_NOT_ESTABLISHED",
                    f"{path}.applicability",
                    "NOT APPLICABLE was not preserved for a transition-trigger requirement because no authoritative parent/scope evidence proves the trigger was outside the applicable case scope. A target-state sample, even with complete event capture inside the trace, does not establish that a 'becomes' trigger never occurred before the trace began; corrected to APPLICABILITY UNKNOWN.",
                ))

            # v0.5.5: if a simple single-signal IF condition is positively
            # observed in the already-bound applicability evidence, UNKNOWN is
            # over-conservative. This promotes only an observed point occurrence;
            # it never converts point evidence into interval persistence or
            # case-wide absence evidence.
            self._promote_positive_condition_applicability(req, evidence, path, issues)

            # v0.5.0: positive point evidence can establish that a condition occurred,
            # but multiple point-valued preconditions must be demonstrably co-observed.
            # Textual proximity is not simultaneity; use a shared Snapshot ID /
            # Observation Group or aligned timestamps. INTERVAL_STATE/scope evidence
            # is compatible with any point inside its declared scope.
            if (
                req.applicability == Applicability.APPLICABLE
                and req.applicability_condition.strip()
                and not req.trigger.strip()
                and not self._applicability_point_samples_correlated(req, evidence)
            ):
                req.applicability = Applicability.UNKNOWN
                issues.append(self._warn(
                    "APPLICABILITY_POINT_CORRELATION_MISSING",
                    f"{path}.applicability",
                    "APPLICABLE depended on multiple point observations that are not explicitly correlated by a shared observation group/snapshot or aligned timestamp; corrected to APPLICABILITY UNKNOWN.",
                ))

            # v0.4.3: a single state sample proves a value only at that instant.
            # It cannot prove that a condition-only requirement was NOT APPLICABLE
            # throughout the evaluated case. Preserve NOT APPLICABLE only when the
            # binding includes explicit interval-state evidence (or authoritative
            # scope metadata). Generic/event coverage flags do not convert a sample
            # into an interval-state assertion.
            if (
                req.applicability == Applicability.NOT_APPLICABLE
                and req.applicability_condition.strip()
                and not req.trigger.strip()
                and not self._has_not_applicable_scope_evidence(req, evidence)
            ):
                req.applicability = Applicability.UNKNOWN
                if req.evaluation_sufficiency == Sufficiency.NOT_REQUIRED:
                    req.evaluation_sufficiency = Sufficiency.INSUFFICIENT
                issues.append(self._warn(
                    "NOT_APPLICABLE_SCOPE_NOT_ESTABLISHED",
                    f"{path}.applicability",
                    "NOT APPLICABLE was supported only by point/state evidence. A condition-only requirement needs explicit interval-state evidence or authoritative scope metadata to establish that its condition was absent across the evaluated case; corrected to APPLICABILITY UNKNOWN.",
                ))

            if req.applicability != Applicability.UNKNOWN and not valid_app_ids:
                issues.append(self._warn(
                    "UNSUPPORTED_APPLICABILITY_CORRECTED",
                    f"{path}.applicability",
                    f"{req.applicability.value} had no explicit valid current-case evidence binding; corrected to APPLICABILITY UNKNOWN.",
                ))
                req.applicability = Applicability.UNKNOWN

            # v0.4.0: once applicability is explicitly resolved and backed by valid
            # current-case evidence IDs, applicability evidence is no longer missing.
            if req.applicability != Applicability.UNKNOWN and req.applicability_evidence_ids and req.missing_applicability_evidence:
                req.missing_applicability_evidence = []
                issues.append(self._warn(
                    "RESOLVED_APPLICABILITY_NEEDS_REMOVED",
                    f"{path}.missing_applicability_evidence",
                    "Removed missing-applicability requests because applicability is already resolved by explicitly bound current-case evidence.",
                ))

            valid_eval_ids: list[str] = []
            for eid in req.evaluation_evidence_ids:
                item = evidence[eid]
                allowed = item.evidence_class in OBSERVATION_CLASSES or (
                    item.evidence_class == EvidenceClass.CURRENT_TICKET and item.scope_metadata
                )
                if allowed:
                    valid_eval_ids.append(eid)
                else:
                    issues.append(self._warn(
                        "INVALID_EVALUATION_SOURCE_REMOVED",
                        f"{path}.evaluation_evidence_ids",
                        f"Removed {eid} ({item.evidence_class.value}) from requirement evidence.",
                    ))
            req.evaluation_evidence_ids = valid_eval_ids

            # Keep applicability and response evidence buckets distinct. If the
            # same item is cited in both places but it does not mechanically match
            # the required behavior, it belongs only to applicability. Timing
            # arithmetic still reads the trigger timestamp from applicability evidence.
            overlap = set(req.applicability_evidence_ids) & set(req.evaluation_evidence_ids)
            if overlap:
                kept_eval: list[str] = []
                removed_overlap: list[str] = []
                behavior_signals = self._signal_names_in_text(req.required_behavior, evidence)
                for eid in req.evaluation_evidence_ids:
                    item = evidence[eid]
                    exact_signal_mismatch = bool(
                        eid in overlap
                        and item.signal_name
                        and behavior_signals
                        and item.signal_name.lower() not in behavior_signals
                    )
                    if eid in overlap and (exact_signal_mismatch or not self._observation_matches_required_behavior(req.required_behavior, item.text)):
                        removed_overlap.append(eid)
                        continue
                    kept_eval.append(eid)
                if removed_overlap:
                    req.evaluation_evidence_ids = kept_eval
                    issues.append(self._warn(
                        "APPLICABILITY_EVIDENCE_DUPLICATE_REMOVED",
                        f"{path}.evaluation_evidence_ids",
                        "Removed applicability-only evidence duplicated in the evaluation bucket: " + ", ".join(removed_overlap) + ".",
                    ))

            if req.applicability == Applicability.NOT_APPLICABLE:
                # A non-applicable requirement has no current-case compliance evaluation.
                # Preserve the applicability evidence that proves the condition is false,
                # but detach response evidence/needs from the requirement evaluation.
                if req.evaluation_evidence_ids:
                    req.evaluation_evidence_ids = []
                    issues.append(self._warn(
                        "NOT_APPLICABLE_EVALUATION_EVIDENCE_REMOVED",
                        f"{path}.evaluation_evidence_ids",
                        "Removed evaluation evidence because the requirement is not applicable in the current case.",
                    ))
                if req.missing_evaluation_evidence:
                    req.missing_evaluation_evidence = []
                    issues.append(self._warn(
                        "NOT_APPLICABLE_EVALUATION_NEEDS_REMOVED",
                        f"{path}.missing_evaluation_evidence",
                        "Removed evaluation-evidence requests because the requirement is not applicable in the current case.",
                    ))
                if req.evaluation_sufficiency != Sufficiency.NOT_REQUIRED:
                    req.evaluation_sufficiency = Sufficiency.NOT_REQUIRED
                    issues.append(self._warn(
                        "NOT_APPLICABLE_SUFFICIENCY_NORMALIZED",
                        f"{path}.evaluation_sufficiency",
                        "Normalized evaluation_sufficiency to NOT_REQUIRED because the requirement is not applicable.",
                    ))

            if req.normative_type == NormativeType.PERMISSIVE:
                # v0.3.5: a permissive requirement has no mandatory response to
                # evaluate in the current contract. Downstream symptom/state
                # observations must not be attached merely because they share a
                # signal token with the permissive behavior. Keep applicability
                # evidence separate and make the no-verdict semantics explicit.
                if req.evaluation_evidence_ids:
                    issues.append(self._warn(
                        "PERMISSIVE_EVALUATION_EVIDENCE_REMOVED",
                        f"{path}.evaluation_evidence_ids",
                        "Removed evaluation observations from a permissive requirement; optional behavior has no compliance-evaluation evidence bucket in this POC.",
                    ))
                    req.evaluation_evidence_ids = []
                if req.missing_evaluation_evidence:
                    issues.append(self._warn(
                        "PERMISSIVE_EVALUATION_NEEDS_REMOVED",
                        f"{path}.missing_evaluation_evidence",
                        "Removed evaluation-evidence requests for optional behavior; permissive requirements cannot yield a compliance verdict.",
                    ))
                    req.missing_evaluation_evidence = []
                if req.evaluation_sufficiency != Sufficiency.NOT_REQUIRED:
                    issues.append(self._warn(
                        "PERMISSIVE_SUFFICIENCY_NORMALIZED",
                        f"{path}.evaluation_sufficiency",
                        "Permissive requirements do not yield SATISFIED/VIOLATED compliance sufficiency; normalized evaluation_sufficiency to NOT_REQUIRED.",
                    ))
                    req.evaluation_sufficiency = Sufficiency.NOT_REQUIRED
            elif (
                req.normative_type in {NormativeType.MANDATORY, NormativeType.PROHIBITIVE}
                and req.applicability != Applicability.NOT_APPLICABLE
                and req.evaluation_sufficiency == Sufficiency.NOT_REQUIRED
            ):
                issues.append(self._issue(
                    "OBLIGATORY_SUFFICIENCY_NOT_REQUIRED_INVALID",
                    f"{path}.evaluation_sufficiency",
                    "MANDATORY/PROHIBITIVE requirements can use NOT_REQUIRED only when the requirement is NOT APPLICABLE.",
                ))

            # v0.2.1: Missing applicability evidence is partly mechanical once the
            # requirement decomposition is known. Do not spend an expensive LLM
            # repair pass merely because the model labelled an `if` condition as
            # TRIGGER or omitted the need object altogether. Normalize/synthesize
            # the bucket from the already-validated condition/trigger semantics.
            self._normalize_missing_applicability_needs(req, path, issues)
            self._normalize_evaluation_bucket_structure(req, path, issues)
            self._normalize_relevant_observation_mapping(req, evidence, path, issues)
            self._derive_correlated_point_state_conformance(req, evidence, path, issues)
            self._reconcile_point_observation_correlation(req, evidence, path, issues)
            self._reconcile_interval_scoped_state_conformance(req, evidence, path, issues)
            if canonical_case is not None and canonical_case.requirement_language:
                self._remove_evaluation_evidence_from_false_applicability_context(
                    req, evidence, canonical_case, path, issues
                )

            timing_fact = self._derive_deterministic_timing_fact(req, evidence, path, issues)
            if timing_fact is None:
                self._normalize_missing_evaluation_needs(req, path, issues)
                self._normalize_resolved_evaluation_needs(req, evidence, path, issues)
                self._normalize_late_timing_coverage_need(req, evidence, path, issues)
            self._reconcile_persistence_sufficiency(req, evidence, path, issues)
            self._reconcile_timing_sufficiency_and_needs(req, timing_fact, path, issues)
            self._enforce_sufficiency_missing_evidence_consistency(req, path, issues)

            self._validate_missing_evidence_structure(req, evidence, path, issues)
            self._validate_missing_evidence_semantic_targets(req, evidence, path, issues, canonical_case)
            self._validate_relevant_observation_mapping(req, evidence, path, issues)
            self._normalize_relevance(req, path, issues)
            self._normalize_timing_relevance_claim(req, evidence, path, issues)
            self._validate_prose(req, path, issues)

            status = self._derive_evaluation_status(req, evidence, path, issues, timing_fact=timing_fact)
            results.append(RequirementResult(
                analysis=req,
                evaluation_status=status,
                evidence_ids=list(req.evaluation_evidence_ids),
                timing_fact=timing_fact,
            ))

        hypotheses = self._validate_hypotheses(data, evidence, results, issues)
        compliance = self._derive_minimum_compliance_evidence(results, evidence)
        self._validate_minimum_evidence_closure(results, compliance, issues)
        case_validity = self._normalize_case_validity_needs(data, canonical_case, issues)
        conflicts = self._derive_evidence_conflicts(results, evidence, issues, canonical_case)

        return ValidatedAnalysis(
            semantic=data,
            requirement_results=results,
            issues=issues,
            compliance_evidence=compliance,
            case_validity_evidence=case_validity,
            hypotheses=hypotheses,
            evidence_conflicts=conflicts,
        )

    def critical_issues(self, validated: ValidatedAnalysis) -> list[ValidationIssue]:
        return [i for i in validated.issues if i.severity == ValidationSeverity.ERROR]

    def _validate_canonical_source_boundaries(self, case: CanonicalCase, issues: list[ValidationIssue]) -> None:
        reported = [e for e in case.evidence_inventory if e.source.lower() == "reported test result"]
        for e in reported:
            if e.evidence_class != EvidenceClass.REPORTED_OBSERVATION:
                issues.append(self._issue(
                    "REPORTED_RESULT_SOURCE_CLASS_INVALID",
                    f"canonical_case.evidence_inventory[{e.id}]",
                    "Reported Test Result must deterministically be REPORTED_OBSERVATION.",
                ))
        descriptions = [e for e in case.evidence_inventory if e.source.lower() == "ticket description"]
        for e in descriptions:
            if e.evidence_class == EvidenceClass.REPORTED_OBSERVATION:
                issues.append(self._issue(
                    "TICKET_DESCRIPTION_PROMOTED_TO_OBSERVATION",
                    f"canonical_case.evidence_inventory[{e.id}]",
                    "Ticket Description must not be auto-promoted to REPORTED_OBSERVATION when a dedicated reported-result source exists.",
                ))

    def _normalize_and_validate_source_accounting(self, data, case: CanonicalCase, evidence, issues: list[ValidationIssue]) -> None:
        """Ensure supplied non-requirement context cannot silently disappear.

        The LLM is allowed to interpret historical precedent semantically, but it
        is not allowed to pretend the source was absent. Diagnostics are simpler:
        their evidence IDs are deterministically restored because the source
        boundary itself is authoritative. Explicit relationship prose in a
        canonical requirement must also be represented in explicit_relationships.
        """
        historical_source = (case.historical_text or "").strip()
        if historical_source:
            expected_ids = self._historical_ticket_ids(historical_source)
            returned_ids = {x.ticket_id.strip().lower() for x in data.historical_tickets if x.ticket_id.strip()}
            if expected_ids:
                for hid in expected_ids:
                    if hid.lower() not in returned_ids:
                        issues.append(self._issue(
                            "HISTORICAL_SOURCE_UNACCOUNTED",
                            "semantic.historical_tickets",
                            f"Supplied historical ticket {hid} was not represented in historical_tickets. Historical precedent may be non-causal, but it must be explicitly accounted for rather than silently dropped.",
                        ))
            elif not data.historical_tickets:
                issues.append(self._issue(
                    "HISTORICAL_SOURCE_UNACCOUNTED",
                    "semantic.historical_tickets",
                    "Historical source material was supplied but historical_tickets is empty. The source must be explicitly summarized/compared even when it does not support a root-cause hypothesis.",
                ))

            # Reject invented historical ticket IDs when canonical IDs are
            # available. This is a source-integrity warning rather than a hard
            # failure because some source exports may use descriptive names.
            if expected_ids:
                expected_lower = {x.lower() for x in expected_ids}
                for item in data.historical_tickets:
                    if item.ticket_id.strip() and item.ticket_id.strip().lower() not in expected_lower:
                        issues.append(self._warn(
                            "UNKNOWN_HISTORICAL_TICKET_REFERENCE",
                            "semantic.historical_tickets",
                            f"Historical analysis referenced {item.ticket_id}, which was not one of the canonical historical ticket IDs {sorted(expected_ids)}.",
                        ))

        diagnostic_ids = [
            e.id for e in case.evidence_inventory
            if e.source == "Current BZD / Diagnostics"
        ]
        missing_diag = [eid for eid in diagnostic_ids if eid not in data.diagnostic_evidence_ids]
        if missing_diag:
            data.diagnostic_evidence_ids = sorted(set(data.diagnostic_evidence_ids) | set(missing_diag))
            issues.append(self._warn(
                "DIAGNOSTIC_SOURCE_AUTO_ACCOUNTED",
                "semantic.diagnostic_evidence_ids",
                "Restored supplied diagnostic/BZD evidence IDs that were omitted by the semantic model: " + ", ".join(missing_diag) + ".",
            ))

        by_id = {r.requirement_id: r for r in data.requirements}
        for source_req in case.requirements:
            if not re.search(r"\bRelationship\s*:", source_req.requirement_text, re.I):
                continue
            semantic_req = by_id.get(source_req.requirement_id)
            if semantic_req is None:
                continue
            if not semantic_req.explicit_relationships:
                issues.append(self._issue(
                    "EXPLICIT_RELATIONSHIP_UNACCOUNTED",
                    f"semantic.requirements[{data.requirements.index(semantic_req)}].explicit_relationships",
                    f"{source_req.requirement_id} contains an explicit supplied relationship, but explicit_relationships is empty.",
                ))
                continue
            parent_match = re.search(r"\bchild\s+of\s+([A-Za-z0-9_-]+)", source_req.requirement_text, re.I)
            if parent_match:
                parent_id = parent_match.group(1)
                if not any(parent_id.lower() in rel.lower() for rel in semantic_req.explicit_relationships):
                    issues.append(self._issue(
                        "EXPLICIT_RELATIONSHIP_UNACCOUNTED",
                        f"semantic.requirements[{data.requirements.index(semantic_req)}].explicit_relationships",
                        f"Canonical relationship names parent {parent_id}, but the semantic relationship list does not account for that parent scope.",
                    ))

    @staticmethod
    def _historical_ticket_ids(text: str) -> list[str]:
        ids: list[str] = []
        for line in (text or "").splitlines():
            token = line.strip().rstrip(":")
            if re.fullmatch(r"HIST[-_A-Za-z0-9]+", token, re.I):
                ids.append(token)
        return list(dict.fromkeys(ids))

    def _promote_positive_condition_applicability(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        """Promote UNKNOWN to APPLICABLE for a safely observed simple IF state.

        This deliberately handles only a single deterministically known signal in
        the applicability condition. It fixes the common over-conservative case
        where one or many STATE_SAMPLE observations already show the positive
        condition. Compound/numeric/negated conditions remain model-owned unless
        they were already resolved by the LLM.
        """
        if req.applicability != Applicability.UNKNOWN:
            return
        if not req.applicability_condition.strip() or req.trigger.strip():
            return
        condition_signals = self._signal_names_in_text(req.applicability_condition, evidence)
        if len(condition_signals) != 1:
            return
        signal = next(iter(condition_signals))
        matches = []
        for eid in req.applicability_evidence_ids:
            item = evidence.get(eid)
            if item is None or item.evidence_class not in OBSERVATION_CLASSES:
                continue
            if not item.signal_name or item.signal_name.lower() != signal:
                continue
            if item.observation_type not in {ObservationType.STATE_SAMPLE, ObservationType.INTERVAL_STATE, ObservationType.TRANSITION}:
                continue
            if self._condition_explicitly_matches_value(req.applicability_condition, item.signal_value):
                matches.append(eid)
        if not matches:
            return
        req.applicability = Applicability.APPLICABLE
        req.missing_applicability_evidence = []
        issues.append(self._warn(
            "POSITIVE_APPLICABILITY_OBSERVED",
            f"{path}.applicability",
            "Promoted APPLICABILITY UNKNOWN to APPLICABLE because the already-bound current-case evidence explicitly observes the simple positive IF-condition. This establishes occurrence at an observed point only; it does not imply interval persistence.",
        ))

    @staticmethod
    def _condition_explicitly_matches_value(condition: str, value: str) -> bool:
        value = (value or "").strip()
        if not value:
            return False
        # Numeric comparators and negated prose are intentionally not evaluated
        # here. For enum/state values, token boundaries prevent AVAILABLE from
        # falsely matching inside NOT_AVAILABLE.
        if re.search(r"\b(?:below|above|less\s+than|greater\s+than|under|over)\b", condition, re.I):
            return False
        if re.search(r"\bnot\s+" + re.escape(value) + r"\b", condition, re.I):
            return False
        return bool(re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(value)}(?![A-Za-z0-9_])",
            condition,
            re.I,
        ))

    def _has_trigger_not_applicable_scope_evidence(self, req, evidence) -> bool:
        """Whether trigger NOT APPLICABLE is established by explicit outer scope.

        ``event_coverage_complete`` is intentionally not enough: it describes the
        supplied event stream, not what happened before the trace began. The main
        supported case is an explicitly supplied parent/child relationship whose
        parent scope is disproved by interval/scope evidence (TEST-019).
        """
        if not req.explicit_relationships:
            return False
        for eid in req.applicability_evidence_ids:
            item = evidence.get(eid)
            if item is None:
                continue
            if item.evidence_class == EvidenceClass.CURRENT_TICKET and item.scope_metadata:
                return True
            if item.evidence_class == EvidenceClass.DIRECT_OBSERVATION and item.observation_type == ObservationType.INTERVAL_STATE:
                return True
        return False

    @staticmethod
    def _point_items_correlated(a, b) -> bool:
        if a.observation_group and b.observation_group and a.observation_group == b.observation_group:
            return True
        if a.timestamped and b.timestamped and a.timestamp_seconds is not None and b.timestamp_seconds is not None:
            same_clock = (not a.clock_id and not b.clock_id) or (a.clock_id and a.clock_id == b.clock_id)
            return bool(same_clock and abs(a.timestamp_seconds - b.timestamp_seconds) <= 1e-9)
        return False

    def _derive_correlated_point_state_conformance(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        """Derive conformance for a non-persistent IF/state rule at one observed point.

        This is deliberately narrower than persistence conformance. For a simple
        condition-state obligation, a positive condition observation and matching
        required-state observation at the same snapshot/timestamp prove the rule at
        that observed point. If applicability is interval-scoped, or the requirement
        says remain/never/shall-not, interval semantics still control and this method
        does nothing.
        """
        if req.normative_type not in {NormativeType.MANDATORY, NormativeType.PROHIBITIVE}:
            return
        if req.applicability != Applicability.APPLICABLE:
            return
        if not req.applicability_condition.strip() or req.trigger.strip():
            return
        if req.timing_constraint.strip() or self._has_true_persistence_semantics(req):
            return
        app_items = [evidence[eid] for eid in req.applicability_evidence_ids if eid in evidence]
        if any(
            x.evidence_class == EvidenceClass.DIRECT_OBSERVATION and x.observation_type == ObservationType.INTERVAL_STATE
            for x in app_items
        ):
            return
        app_points = [
            x for x in app_items
            if x.evidence_class == EvidenceClass.DIRECT_OBSERVATION
            and x.observation_type in {ObservationType.STATE_SAMPLE, ObservationType.TRANSITION}
            and x.signal_name
        ]
        if not app_points:
            return
        by_signal: dict[str, list] = {}
        for item in app_points:
            by_signal.setdefault(item.signal_name.lower(), []).append(item)

        eval_points = [
            evidence[eid] for eid in req.evaluation_evidence_ids
            if eid in evidence
            and evidence[eid].evidence_class == EvidenceClass.DIRECT_OBSERVATION
            and evidence[eid].observation_type in {ObservationType.STATE_SAMPLE, ObservationType.TRANSITION}
            and self._observation_matches_required_behavior(req.required_behavior, evidence[eid].text)
        ]
        matching = None
        for candidate in eval_points:
            if all(any(self._point_items_correlated(a, candidate) for a in items) for items in by_signal.values()):
                matching = candidate
                break
        if matching is None:
            return

        changed = req.evaluation_sufficiency != Sufficiency.SUFFICIENT_CONFORMANCE or bool(req.missing_evaluation_evidence)
        req.evaluation_sufficiency = Sufficiency.SUFFICIENT_CONFORMANCE
        req.missing_evaluation_evidence = []
        if changed:
            issues.append(self._warn(
                "CORRELATED_POINT_STATE_CONFORMANCE_DERIVED",
                f"{path}.evaluation_sufficiency",
                "Derived SUFFICIENT_CONFORMANCE for a non-persistent condition/state obligation because positive applicability evidence and a matching required-state observation are explicitly correlated at the same snapshot/timestamp. This proves conformance only at that observed applicable point and does not create interval persistence evidence.",
            ))

    def _normalize_resolved_evaluation_needs(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        """Remove evaluation-bucket asks that are already resolved or belong to applicability."""
        if not req.missing_evaluation_evidence:
            return
        original = list(req.missing_evaluation_evidence)
        kept = [n for n in original if n.element != RequirementElementType.APPLICABILITY]

        if req.trigger.strip():
            trigger_supplied = any(
                eid in evidence
                and evidence[eid].timestamped
                and evidence[eid].timestamp_seconds is not None
                and self._transition_matches_text(evidence[eid], req.trigger)
                for eid in req.applicability_evidence_ids
            )
            if trigger_supplied:
                kept = [n for n in kept if n.element != RequirementElementType.TRIGGER]

        if [n.model_dump() for n in kept] != [n.model_dump() for n in original]:
            req.missing_evaluation_evidence = kept
            issues.append(self._warn(
                "RESOLVED_OR_MISBUCKETED_EVALUATION_NEEDS_REMOVED",
                f"{path}.missing_evaluation_evidence",
                "Removed evaluation-evidence needs that belonged to applicability or requested a trigger timestamp already supplied by canonical transition evidence.",
            ))

    def _timing_gap_is_only_event_coverage(self, req, evidence) -> bool:
        """Return True when trigger/response timing is known and only event completeness is missing."""
        if not req.timing_constraint.strip() or req.applicability != Applicability.APPLICABLE:
            return False
        needs = list(req.missing_evaluation_evidence or [])
        if not needs or any(n.element != RequirementElementType.RESPONSE for n in needs):
            return False
        if not all("coverage" in (n.description or "").lower() for n in needs):
            return False
        app_items = [evidence[eid] for eid in req.applicability_evidence_ids if eid in evidence]
        eval_items = [evidence[eid] for eid in req.evaluation_evidence_ids if eid in evidence]
        triggers = [
            x for x in app_items
            if x.timestamped and x.timestamp_seconds is not None and self._transition_matches_text(x, req.trigger)
        ]
        if not triggers:
            return False
        trigger = min(triggers, key=lambda x: x.timestamp_seconds)
        responses = [
            x for x in eval_items
            if x.timestamped and x.timestamp_seconds is not None
            and x.timestamp_seconds >= trigger.timestamp_seconds
            and self._transition_matches_text(x, req.required_behavior)
        ]
        if not responses:
            return False
        response = min(responses, key=lambda x: x.timestamp_seconds)
        if trigger.source != response.source and (not trigger.clock_id or trigger.clock_id != response.clock_id):
            return False
        if trigger.clock_id and response.clock_id and trigger.clock_id != response.clock_id:
            return False
        return True

    def _normalize_late_timing_coverage_need(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        """For a visible late transition with incomplete event capture, request only coverage.

        Trigger/response timestamps are already known in this situation; the sole
        reason the deterministic timing verdict is suppressed is that an earlier
        omitted response transition cannot be excluded.
        """
        if not req.timing_constraint.strip() or req.applicability != Applicability.APPLICABLE:
            return
        limit_s = self._timing_limit_seconds(req.timing_constraint)
        if limit_s is None:
            return
        app_items = [evidence[eid] for eid in req.applicability_evidence_ids if eid in evidence]
        eval_items = [evidence[eid] for eid in req.evaluation_evidence_ids if eid in evidence]
        triggers = [
            x for x in app_items
            if x.timestamped and x.timestamp_seconds is not None and self._transition_matches_text(x, req.trigger)
        ]
        if not triggers:
            return
        trigger = min(triggers, key=lambda x: x.timestamp_seconds)
        responses = [
            x for x in eval_items
            if x.timestamped and x.timestamp_seconds is not None
            and x.timestamp_seconds >= trigger.timestamp_seconds
            and self._transition_matches_text(x, req.required_behavior)
        ]
        if not responses:
            return
        response = min(responses, key=lambda x: x.timestamp_seconds)
        if response.timestamp_seconds - trigger.timestamp_seconds <= limit_s + 1e-12:
            return
        if trigger.source != response.source and (not trigger.clock_id or trigger.clock_id != response.clock_id):
            return
        if trigger.clock_id and response.clock_id and trigger.clock_id != response.clock_id:
            return
        if trigger.event_coverage_complete and response.event_coverage_complete:
            return
        req.missing_evaluation_evidence = [EvidenceNeed(
            element=RequirementElementType.RESPONSE,
            description=(
                f"Complete transition-event coverage on the aligned trace from the trigger through at least the {req.timing_constraint.strip()} deadline, "
                "so an earlier omitted required-response transition can be excluded."
            ),
        )]
        issues.append(self._warn(
            "TIMING_COVERAGE_GAP_NEED_NORMALIZED",
            f"{path}.missing_evaluation_evidence",
            "Normalized the remaining timing evidence need to complete transition-event coverage only; trigger and visible response timestamps are already supplied.",
        ))

    @staticmethod
    def _normalize_empty_semantic_sentinels(req, path: str, issues: list[ValidationIssue]) -> None:
        """Normalize model prose placeholders such as ``None (not applicable)`` to empty fields."""
        fields = (
            "applicability_condition",
            "trigger",
            "timing_constraint",
            "observation_interval_requirement",
        )
        for field in fields:
            value = getattr(req, field, "") or ""
            if re.match(r"^\s*(?:none\b|n/?a\b|not\s+applicable\b|no\s+explicit\b)", value, re.I):
                setattr(req, field, "")
                issues.append(ValidationIssue(
                    code="EMPTY_SEMANTIC_SENTINEL_NORMALIZED",
                    severity=ValidationSeverity.WARNING,
                    path=f"{path}.{field}",
                    message=f"Normalized placeholder text in {field} to an empty semantic field.",
                ))

    def _validate_decomposition(self, req, path: str, issues: list[ValidationIssue]) -> None:
        text = " ".join(req.requirement_text.split())
        normative = req.normative_type in {NormativeType.MANDATORY, NormativeType.PROHIBITIVE, NormativeType.PERMISSIVE}

        if normative and not req.required_behavior.strip():
            issues.append(self._issue(
                "MISSING_REQUIRED_BEHAVIOR",
                f"{path}.required_behavior",
                f"{req.requirement_id} is normative but required_behavior is empty.",
            ))

        if self.if_wording.search(text) and not req.applicability_condition.strip():
            issues.append(self._issue(
                "MISSING_APPLICABILITY_CONDITION",
                f"{path}.applicability_condition",
                "Requirement contains an explicit 'if' condition but applicability_condition is empty.",
            ))

        if self.trigger_wording.search(text) and not req.trigger.strip():
            issues.append(self._issue(
                "MISSING_TRIGGER_DECOMPOSITION",
                f"{path}.trigger",
                "Requirement contains an explicit when/upon trigger but trigger is empty.",
            ))

        if self.timing_wording.search(text) and not req.timing_constraint.strip():
            issues.append(self._issue(
                "MISSING_TIMING_DECOMPOSITION",
                f"{path}.timing_constraint",
                "Requirement contains an explicit timing limit but timing_constraint is empty.",
            ))

        if self.persistence_wording.search(text) and not req.observation_interval_requirement.strip():
            issues.append(self._issue(
                "MISSING_PERSISTENCE_DECOMPOSITION",
                f"{path}.observation_interval_requirement",
                "Requirement has persistence/non-occurrence semantics but observation_interval_requirement is empty.",
            ))

    def _normalize_missing_applicability_needs(self, req, path: str, issues: list[ValidationIssue]) -> None:
        """Normalize applicability evidence needs from already-decomposed semantics.

        The requirement's own condition/trigger determines the bucket and element
        type. Fixing a label or synthesizing a neutral evidence request is
        mechanical and must not consume a second LLM call. This applies to
        permissive requirements too because applicability may still be reported
        even though no compliance verdict is possible.
        """
        if req.applicability != Applicability.UNKNOWN:
            return

        needs = req.missing_applicability_evidence

        # For a pure IF-condition requirement, every need in the applicability
        # bucket refers to applicability, regardless of a mistaken RESPONSE/TRIGGER
        # label returned by the model.
        if req.applicability_condition.strip() and not req.trigger.strip():
            corrected = False
            for need in needs:
                if need.element != RequirementElementType.APPLICABILITY:
                    need.element = RequirementElementType.APPLICABILITY
                    corrected = True
            if corrected:
                issues.append(self._warn(
                    "CONDITION_NEED_TYPE_CORRECTED",
                    f"{path}.missing_applicability_evidence",
                    "Normalized applicability-bucket element labels to APPLICABILITY for an explicit condition-only requirement.",
                ))

        # For a pure event-trigger requirement, the applicability bucket is about
        # establishing occurrence of that trigger.
        if req.trigger.strip() and not req.applicability_condition.strip():
            corrected = False
            for need in needs:
                if need.element != RequirementElementType.TRIGGER:
                    need.element = RequirementElementType.TRIGGER
                    corrected = True
            if corrected:
                issues.append(self._warn(
                    "TRIGGER_NEED_TYPE_CORRECTED",
                    f"{path}.missing_applicability_evidence",
                    "Normalized applicability-bucket element labels to TRIGGER for an explicit trigger-only requirement.",
                ))

        app_types = {n.element for n in needs}
        if req.applicability_condition.strip() and RequirementElementType.APPLICABILITY not in app_types:
            needs.append(EvidenceNeed(
                element=RequirementElementType.APPLICABILITY,
                description=f"Current-case observation establishing whether {req.applicability_condition.strip()}.",
            ))
            issues.append(self._warn(
                "CONDITION_APPLICABILITY_NEED_DERIVED",
                f"{path}.missing_applicability_evidence",
                "Derived missing applicability-condition evidence from the decomposed requirement condition.",
            ))
            app_types.add(RequirementElementType.APPLICABILITY)

        if req.trigger.strip() and RequirementElementType.TRIGGER not in app_types:
            desc = f"Current-case observation establishing whether the trigger occurred: {req.trigger.strip()}."
            if req.timing_constraint.strip():
                desc = f"Timestamped current-case observation establishing whether the trigger occurred: {req.trigger.strip()}."
            needs.append(EvidenceNeed(element=RequirementElementType.TRIGGER, description=desc))
            issues.append(self._warn(
                "TRIGGER_APPLICABILITY_NEED_DERIVED",
                f"{path}.missing_applicability_evidence",
                "Derived missing trigger evidence from the decomposed requirement trigger.",
            ))

        # v0.5.0 asymmetric scope rule: to establish APPLICABLE we only need
        # evidence that the positive condition occurred at a relevant evaluation
        # point. INTERVAL_STATE is required for case-wide absence/NOT APPLICABLE,
        # not merely to prove that the condition happened once.
        if req.applicability_condition.strip() and not req.trigger.strip() and any(
            re.search(r"INTERVAL_STATE|case[- ]scope|throughout|full interval|complete evaluated interval|lone STATE_SAMPLE", n.description, re.I)
            for n in needs
        ):
            condition = req.applicability_condition.strip()
            correlation = " If several point observations are needed for a compound condition, correlate them using a shared Snapshot ID / Observation Group or aligned timestamps." if re.search(r"\band\b|&&", condition, re.I) else ""
            req.missing_applicability_evidence = [EvidenceNeed(
                element=RequirementElementType.APPLICABILITY,
                description=f"Current-case observation establishing that {condition} is true at the relevant evaluation point.{correlation}",
            )]
            issues.append(self._warn(
                "POSITIVE_APPLICABILITY_SCOPE_NEED_NORMALIZED",
                f"{path}.missing_applicability_evidence",
                "Removed an over-strict interval/case-scope request from positive applicability evidence. Interval scope is required to prove case-wide absence, not to prove that a condition occurred at an observed point.",
            ))

    def _normalize_missing_evaluation_needs(self, req, path: str, issues: list[ValidationIssue]) -> None:
        """Derive and compact mechanically implied evaluation-evidence needs.

        The LLM owns requirement semantics; Python owns evidence bookkeeping.
        A correctly decomposed timed requirement must not trigger another model
        call merely because timestamp/window/timebase needs were labelled as
        RESPONSE instead of TIMING, or because the same acquisition need was
        expressed several times.
        """
        if req.normative_type not in {NormativeType.MANDATORY, NormativeType.PROHIBITIVE}:
            return
        if req.applicability == Applicability.NOT_APPLICABLE:
            return

        if req.timing_constraint.strip():
            original = list(req.missing_evaluation_evidence)
            has_trigger_ts = any(
                n.element == RequirementElementType.TRIGGER and self._mentions_timestamp(n.description)
                for n in original
            )
            has_clock_need = any(
                re.search(r"\btimebase\b|\bclock\b|align", n.description, re.I)
                for n in original
            )

            # Preserve only non-timing-specific asks; replace the repeated timing
            # fragments with a canonical three-part evidence bundle.
            unrelated: list[EvidenceNeed] = []
            for n in original:
                text = n.description.lower()
                timing_like = bool(re.search(
                    r"timestamp|time\s*stamp|\b500\s*ms\b|timing|timebase|clock|align|window|elapsed|deadline|coverage",
                    text,
                    re.I,
                ))
                if not timing_like and n.element not in {RequirementElementType.TRIGGER, RequirementElementType.TIMING}:
                    unrelated.append(n)

            canonical: list[EvidenceNeed] = []
            if req.trigger.strip():
                canonical.append(EvidenceNeed(
                    element=RequirementElementType.TRIGGER,
                    description=f"Timestamped observation establishing the trigger occurrence: {req.trigger.strip()}.",
                ))

            behavior = self._clean_behavior(req.required_behavior) or "the required response/state"
            canonical.append(EvidenceNeed(
                element=RequirementElementType.RESPONSE,
                description=(
                    f'Timestamped observation of the required response/state ("{behavior}") with coverage spanning the full timing window '
                    f"({req.timing_constraint.strip()})."
                ),
            ))

            if has_clock_need:
                timing_desc = "Alignable/common timebase between trigger and response observations if they originate from different clocks/sources."
            else:
                timing_desc = f"Timing information sufficient to compare trigger and response against the requirement ({req.timing_constraint.strip()})."
            canonical.append(EvidenceNeed(
                element=RequirementElementType.TIMING,
                description=timing_desc,
            ))

            new_needs = unrelated + canonical
            if [n.model_dump() for n in new_needs] != [n.model_dump() for n in original]:
                req.missing_evaluation_evidence = new_needs
                issues.append(self._warn(
                    "TIMING_EVALUATION_NEEDS_NORMALIZED",
                    f"{path}.missing_evaluation_evidence",
                    "Normalized duplicate/mislabelled timing evidence into trigger, response-window, and timing/timebase needs.",
                ))

        if self._has_true_persistence_semantics(req):
            original = list(req.missing_evaluation_evidence)
            # For a true persistence requirement, response-state observation and
            # interval coverage are one acquisition obligation. Keep unrelated
            # trigger/timing asks, but collapse duplicate RESPONSE /
            # OBSERVATION_INTERVAL prose into one canonical interval need.
            retained = [
                n for n in original
                if n.element not in {RequirementElementType.RESPONSE, RequirementElementType.OBSERVATION_INTERVAL}
            ]
            behavior = self._clean_behavior(req.required_behavior) or "the required response/state"
            basis = req.applicability_condition.strip() or req.trigger.strip() or "the applicable condition"
            retained.append(EvidenceNeed(
                element=RequirementElementType.OBSERVATION_INTERVAL,
                description=(
                    f'Sustained observation of the required response/state ("{behavior}") throughout the applicable interval '
                    f'({basis}), sufficient to assess persistence; a single instant is insufficient.'
                ),
            ))
            if [n.model_dump() for n in retained] != [n.model_dump() for n in original]:
                had_interval = any(n.element == RequirementElementType.OBSERVATION_INTERVAL for n in original)
                req.missing_evaluation_evidence = retained
                if had_interval:
                    issues.append(self._warn(
                        "PERSISTENCE_EVALUATION_NEEDS_NORMALIZED",
                        f"{path}.missing_evaluation_evidence",
                        "Normalized duplicate response/persistence evidence into one observation-interval acquisition need.",
                    ))
                else:
                    issues.append(self._warn(
                        "PERSISTENCE_EVALUATION_NEED_DERIVED",
                        f"{path}.missing_evaluation_evidence",
                        "Derived and normalized the persistence-interval evidence need from the decomposed requirement semantics.",
                    ))

    def _normalize_evaluation_bucket_structure(self, req, path: str, issues: list[ValidationIssue]) -> None:
        """Enforce enum-declared evidence buckets without interpreting prose.

        A need explicitly labelled APPLICABILITY cannot remain in the evaluation
        bucket. If applicability is unresolved, move it to the applicability
        bucket; if applicability is already resolved, drop it as no longer
        missing. This is structural normalization of model output, not language
        understanding.
        """
        if not req.missing_evaluation_evidence:
            return
        kept = []
        moved = []
        dropped = 0
        existing = {(n.element, n.description) for n in req.missing_applicability_evidence}
        for need in req.missing_evaluation_evidence:
            if need.element != RequirementElementType.APPLICABILITY:
                kept.append(need)
                continue
            if req.applicability == Applicability.UNKNOWN:
                key = (need.element, need.description)
                if key not in existing:
                    req.missing_applicability_evidence.append(copy.deepcopy(need))
                    existing.add(key)
                    moved.append(need.description)
            else:
                dropped += 1
        if len(kept) != len(req.missing_evaluation_evidence):
            req.missing_evaluation_evidence = kept
            issues.append(self._warn(
                "EVALUATION_BUCKET_APPLICABILITY_NORMALIZED",
                f"{path}.missing_evaluation_evidence",
                (
                    f"Moved {len(moved)} applicability-labelled need(s) to the applicability bucket"
                    if moved else
                    f"Removed {dropped} applicability-labelled need(s) because applicability is already resolved"
                ) + ".",
            ))

    def _normalize_relevant_observation_mapping(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        """Auto-map supplied observations that mechanically match obligatory behavior.

        Whether the evidence is sufficient remains a semantic/evaluation
        question; including an already supplied relevant observation is only
        deterministic evidence bookkeeping and should not trigger an LLM repair.
        PERMISSIVE requirements are intentionally excluded: a downstream symptom
        is not evidence that an optional permission itself was or was not exercised.
        """
        if req.normative_type == NormativeType.PERMISSIVE or req.applicability == Applicability.NOT_APPLICABLE:
            return
        if not req.required_behavior.strip():
            return
        mapped = set(req.evaluation_evidence_ids)
        added: list[str] = []
        for eid, item in evidence.items():
            if item.evidence_class not in OBSERVATION_CLASSES or eid in mapped:
                continue
            if self._observation_matches_required_behavior(req.required_behavior, item.text):
                req.evaluation_evidence_ids.append(eid)
                mapped.add(eid)
                added.append(eid)
        if added:
            issues.append(self._warn(
                "RELEVANT_OBSERVATION_AUTO_MAPPED",
                f"{path}.evaluation_evidence_ids",
                "Automatically mapped supplied response-relevant observation(s): " + ", ".join(added) + ".",
            ))

    def _validate_missing_evidence_structure(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        if req.normative_type not in {NormativeType.MANDATORY, NormativeType.PROHIBITIVE}:
            return
        if req.applicability == Applicability.NOT_APPLICABLE:
            return

        app_types = {n.element for n in req.missing_applicability_evidence}
        eval_types = {n.element for n in req.missing_evaluation_evidence}

        if req.applicability == Applicability.UNKNOWN:
            if req.trigger.strip() and RequirementElementType.TRIGGER not in app_types and not req.applicability_evidence_ids:
                issues.append(self._issue(
                    "MISSING_TRIGGER_APPLICABILITY_NEED",
                    f"{path}.missing_applicability_evidence",
                    "Trigger-based requirement is applicability-unknown but no missing trigger evidence is specified.",
                ))
            if req.applicability_condition.strip() and RequirementElementType.APPLICABILITY not in app_types and not req.applicability_evidence_ids:
                issues.append(self._issue(
                    "MISSING_CONDITION_APPLICABILITY_NEED",
                    f"{path}.missing_applicability_evidence",
                    "Conditional requirement is applicability-unknown but no missing applicability-condition evidence is specified.",
                ))

        for i, need in enumerate(req.missing_evaluation_evidence):
            if need.element == RequirementElementType.APPLICABILITY:
                issues.append(self._issue(
                    "APPLICABILITY_NEED_IN_EVALUATION_BUCKET",
                    f"{path}.missing_evaluation_evidence[{i}]",
                    "An applicability condition was placed in Evaluation Evidence; keep applicability and evaluation buckets separate.",
                ))
            if need.element == RequirementElementType.TRIGGER and not req.trigger.strip():
                issues.append(self._issue(
                    "NONEXISTENT_TRIGGER_IN_EVALUATION_BUCKET",
                    f"{path}.missing_evaluation_evidence[{i}]",
                    "Evaluation Evidence asks for a trigger, but this requirement has no decomposed trigger. The condition belongs to applicability.",
                ))

        if req.required_behavior.strip() and not req.evaluation_evidence_ids and RequirementElementType.RESPONSE not in eval_types:
            # A persistence-only observation need can also cover the response state when worded appropriately.
            if RequirementElementType.OBSERVATION_INTERVAL not in eval_types:
                issues.append(self._issue(
                    "MISSING_RESPONSE_EVALUATION_NEED",
                    f"{path}.missing_evaluation_evidence",
                    "Mandatory/prohibitive behavior lacks supplied evaluation evidence and no missing response evidence is specified.",
                ))

        if req.timing_constraint.strip() and req.evaluation_sufficiency == Sufficiency.INSUFFICIENT:
            coverage_only_gap = self._timing_gap_is_only_event_coverage(req, evidence)
            if RequirementElementType.TIMING not in eval_types and not coverage_only_gap:
                issues.append(self._issue(
                    "MISSING_TIMING_EVALUATION_NEED",
                    f"{path}.missing_evaluation_evidence",
                    "Timed requirement is missing TIMING evidence needed to evaluate the required window.",
                ))
            # A trigger timestamp is a dependent need. If trigger decomposition
            # itself is still missing, let MISSING_TRIGGER_DECOMPOSITION be
            # repaired first; revalidation will then derive the timestamp need.
            if req.trigger.strip():
                trigger_timestamp_already_supplied = any(
                    evidence.get(eid) is not None and evidence[eid].timestamped
                    for eid in req.applicability_evidence_ids
                )
                if (not trigger_timestamp_already_supplied and
                        not any(n.element == RequirementElementType.TRIGGER and self._mentions_timestamp(n.description) for n in req.missing_evaluation_evidence)):
                    # Timing evaluation needs the trigger timestamp, distinct from merely proving occurrence.
                    issues.append(self._issue(
                        "MISSING_TRIGGER_TIMESTAMP_NEED",
                        f"{path}.missing_evaluation_evidence",
                        "Timed requirement lacks a supplied or requested trigger timestamp.",
                    ))

        if (
            self._has_true_persistence_semantics(req)
            and req.evaluation_sufficiency == Sufficiency.INSUFFICIENT
            and RequirementElementType.OBSERVATION_INTERVAL not in eval_types
        ):
            issues.append(self._issue(
                "MISSING_PERSISTENCE_EVALUATION_NEED",
                f"{path}.missing_evaluation_evidence",
                "True persistence/non-occurrence requirement lacks an OBSERVATION_INTERVAL evidence need.",
            ))

    @staticmethod
    def _signal_names_in_text(text: str, evidence) -> set[str]:
        """Return deterministically known signal names explicitly mentioned in text.

        Signal names come only from the canonical evidence inventory; Python does
        not infer new automotive concepts from prose. Matching is case-insensitive
        and token-boundary aware.
        """
        found: set[str] = set()
        source = text or ""
        for item in evidence.values():
            name = (item.signal_name or "").strip()
            if not name:
                continue
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", source, re.I):
                found.add(name.lower())
        return found

    @staticmethod
    def _evaluation_target_zone(description: str) -> str:
        """Focus on the evidence being requested, not trailing purpose clauses.

        Phrases such as ``... before evaluating WarningIndicator`` name the
        downstream purpose, not the signal for which interval evidence is being
        requested. Trimming those clauses prevents a condition signal from being
        mistaken for the response target merely because the response is mentioned
        later in the sentence.
        """
        text = description or ""
        m = re.search(r"\b(?:before|prior\s+to)\s+(?:evaluating|assessing|checking|verifying)\b", text, re.I)
        return text[:m.start()] if m else text

    def _validate_missing_evidence_semantic_targets(self, req, evidence, path: str, issues: list[ValidationIssue], canonical_case: Optional[CanonicalCase] = None) -> None:
        """Reject missing-evaluation requests aimed at already-satisfied applicability evidence.

        v1.8 closes a repair-loop hole exposed by TCF02. A patch could remove an
        invalid TRIGGER label yet still ask for more interval evidence for the
        applicability condition even though that condition already had explicit
        INTERVAL_STATE coverage. The structural schema was valid, so earlier
        validators accepted it.

        This check remains mechanical:
        - target signal names are taken only from deterministically parsed evidence;
        - applicability/evaluation ownership comes from the already-decomposed
          RequirementAnalysis;
        - existing interval coverage comes from ObservationType.INTERVAL_STATE.
        No new requirement meaning is inferred here.
        """
        if req.normative_type not in {NormativeType.MANDATORY, NormativeType.PROHIBITIVE}:
            return
        if req.applicability == Applicability.NOT_APPLICABLE:
            return
        if not req.missing_evaluation_evidence:
            return

        condition_signals = self._signal_names_in_text(req.applicability_condition, evidence)
        trigger_signals = self._signal_names_in_text(req.trigger, evidence)
        behavior_signals = self._signal_names_in_text(req.required_behavior, evidence)

        # v0.7.1: when the required behavior has no current observation, its
        # signal name may not exist in the evidence inventory at all. Supplement
        # the target sets from the 4B-normalized structured requirement contract;
        # Python does not infer these names from raw requirement prose.
        if canonical_case is not None:
            hint = next((x for x in canonical_case.requirement_language if x.requirement_id == req.requirement_id), None)
            if hint is not None:
                if hint.required_behavior_signal.strip():
                    behavior_signals.add(hint.required_behavior_signal.strip().lower())
                if hint.trigger_signal.strip() and hint.trigger_event.strip():
                    trigger_signals.add(hint.trigger_signal.strip().lower())
                for group in hint.applicability_any_of:
                    for pred in group.predicates:
                        if pred.signal.strip():
                            condition_signals.add(pred.signal.strip().lower())

        # Explicitly bound response observations are a stronger deterministic
        # indication of the evaluation target than prose alone.
        for eid in req.evaluation_evidence_ids:
            item = evidence.get(eid)
            if item is None or not item.signal_name:
                continue
            if self._observation_matches_required_behavior(req.required_behavior, item.text):
                behavior_signals.add(item.signal_name.lower())

        app_interval_by_signal: dict[str, list[str]] = {}
        for eid in req.applicability_evidence_ids:
            item = evidence.get(eid)
            if item is None or not item.signal_name:
                continue
            if item.observation_type == ObservationType.INTERVAL_STATE:
                app_interval_by_signal.setdefault(item.signal_name.lower(), []).append(eid)

        for i, need in enumerate(req.missing_evaluation_evidence):
            if need.element not in {RequirementElementType.RESPONSE, RequirementElementType.OBSERVATION_INTERVAL}:
                continue
            zone = self._evaluation_target_zone(need.description)
            target_signals = self._signal_names_in_text(zone, evidence)
            if canonical_case is not None:
                hint = next((x for x in canonical_case.requirement_language if x.requirement_id == req.requirement_id), None)
                if hint is not None:
                    structured_names = set()
                    if hint.required_behavior_signal.strip():
                        structured_names.add(hint.required_behavior_signal.strip())
                    if hint.trigger_signal.strip() and hint.trigger_event.strip():
                        structured_names.add(hint.trigger_signal.strip())
                    for group in hint.applicability_any_of:
                        for pred in group.predicates:
                            if pred.signal.strip():
                                structured_names.add(pred.signal.strip())
                    for name in structured_names:
                        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", zone, re.I):
                            target_signals.add(name.lower())
            if not target_signals:
                # Generic wording such as "the required response/state" is not
                # rejected; only explicit wrong-signal requests are actionable.
                continue

            behavior_hit = bool(target_signals & behavior_signals)
            applicability_targets = target_signals & (condition_signals | trigger_signals)
            already_satisfied = sorted(sig for sig in applicability_targets if sig in app_interval_by_signal)

            if already_satisfied and not behavior_hit:
                detail = []
                for sig in already_satisfied:
                    detail.extend(app_interval_by_signal.get(sig, []))
                behavior_label = ", ".join(sorted(behavior_signals)) or self._clean_behavior(req.required_behavior) or "the required behavior"
                issues.append(self._issue(
                    "EVALUATION_NEED_TARGET_MISMATCH",
                    f"{path}.missing_evaluation_evidence[{i}]",
                    "Evaluation Evidence requests additional interval/response evidence for applicability signal(s) "
                    + ", ".join(sorted(already_satisfied))
                    + (f" even though interval evidence is already supplied by {', '.join(detail)}." if detail else ".")
                    + f" The unresolved evaluation need must target the required behavior ({behavior_label}) rather than re-requesting already-established applicability evidence.",
                ))
                continue

            # Even when the applicability evidence is not complete, an explicit
            # RESPONSE/OBSERVATION_INTERVAL request that names only condition/
            # trigger signals is in the wrong bucket. Keep this narrower than a
            # general NLP check: it fires only when both sides have known parsed
            # signal names and no required-behavior signal is named in the target
            # clause.
            if applicability_targets and behavior_signals and not behavior_hit:
                issues.append(self._issue(
                    "EVALUATION_NEED_TARGET_MISMATCH",
                    f"{path}.missing_evaluation_evidence[{i}]",
                    "Evaluation Evidence targets applicability/trigger signal(s) "
                    + ", ".join(sorted(applicability_targets))
                    + f" instead of the required behavior signal(s) {', '.join(sorted(behavior_signals))}.",
                ))

    def _validate_relevant_observation_mapping(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        if req.normative_type == NormativeType.PERMISSIVE or req.applicability == Applicability.NOT_APPLICABLE:
            return
        if not req.required_behavior.strip():
            return
        mapped = set(req.evaluation_evidence_ids)
        for eid, item in evidence.items():
            if item.evidence_class not in OBSERVATION_CLASSES:
                continue
            if eid in mapped:
                continue
            if self._observation_matches_required_behavior(req.required_behavior, item.text):
                issues.append(self._issue(
                    "RELEVANT_OBSERVATION_NOT_MAPPED",
                    f"{path}.evaluation_evidence_ids",
                    f"{eid} ({item.source}) directly concerns the required response but was not mapped as evaluation evidence.",
                ))

    @staticmethod
    def _observation_matches_required_behavior(required_behavior: str, observation: str) -> bool:
        rb = required_behavior or ""
        ob = observation or ""

        # Prefer exact signal-like identifiers, including dotted namespaces.
        # This prevents VariantA.FunctionRequest from being mistaken for
        # VariantA.FunctionStatus merely because both share the VariantA prefix.
        def identifiers(text: str) -> set[str]:
            vals = re.findall(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_.]*)(?![A-Za-z0-9_])", text)
            out = set()
            for token in vals:
                if "." in token or "_" in token or re.search(r"[a-z][A-Z]", token):
                    out.add(token.lower())
            return out

        rb_ids = identifiers(rb)
        ob_ids = identifiers(ob)
        if rb_ids and ob_ids and not (rb_ids & ob_ids):
            return False
        if not rb_ids and not ob_ids:
            # Without any signal-like identifier there is no deterministic
            # mechanical basis to auto-map the observation.
            return False

        state_tokens = {
            x for x in re.findall(r"\b[A-Z][A-Z0-9_]{1,}\b", rb)
            if x.upper() not in {"SHALL", "MUST", "MAY", "NOT", "TRUE", "FALSE"}
        }
        # TRUE/FALSE are legitimate state values; add them only when they appear
        # in a state-like clause rather than as general words.
        for boolean in ("TRUE", "FALSE"):
            if re.search(rf"\b{boolean}\b", rb, re.I):
                state_tokens.add(boolean)

        if state_tokens:
            def token_present(token: str, text: str) -> bool:
                return bool(re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", text, re.I))
            if not any(token_present(x, ob) for x in state_tokens):
                return False

        # Avoid treating "did not become ACTIVE" as evidence for "remain INACTIVE".
        if "remain" in rb.lower() and "remain" not in ob.lower() and "remained" not in ob.lower():
            # Point observations can still be relevant counterexamples to a
            # persistence obligation; the caller/validator decides sufficiency.
            # If the point explicitly names the exact signal, keep it relevant.
            if not (rb_ids & ob_ids):
                return False
        return True

    @staticmethod
    def _points_correlated(items) -> bool:
        """Return True when point observations explicitly share one evaluation instant."""
        points = [x for x in items if x.observation_type == ObservationType.STATE_SAMPLE]
        if len(points) <= 1:
            return True
        groups = [x.observation_group.strip() for x in points]
        if groups and all(groups) and len(set(groups)) == 1:
            return True
        if all(x.timestamped and x.timestamp_seconds is not None for x in points):
            clocks = {x.clock_id for x in points if x.clock_id}
            if len(clocks) <= 1:
                base = points[0].timestamp_seconds
                return all(abs(x.timestamp_seconds - base) <= 1e-9 for x in points[1:])
        return False

    def _applicability_point_samples_correlated(self, req, evidence) -> bool:
        point_items = [
            evidence[eid] for eid in req.applicability_evidence_ids
            if eid in evidence
            and evidence[eid].evidence_class == EvidenceClass.DIRECT_OBSERVATION
            and evidence[eid].observation_type == ObservationType.STATE_SAMPLE
        ]
        # Repeated samples of the same condition signal are alternatives in time,
        # not separate conjuncts that must all be simultaneous. Correlation is
        # required only when the applicability decision depends on distinct
        # point-valued signals.
        by_signal: dict[str, list] = {}
        for item in point_items:
            key = (item.signal_name or item.id).lower()
            by_signal.setdefault(key, []).append(item)
        if len(by_signal) <= 1:
            return True

        groups = [
            {x.observation_group for x in items if x.observation_group}
            for items in by_signal.values()
        ]
        if all(groups) and set.intersection(*groups):
            return True

        # Otherwise look for an aligned timestamp/timebase that is represented
        # by at least one sample from every distinct signal.
        common_keys = None
        for items in by_signal.values():
            keys = set()
            for x in items:
                if x.timestamped and x.timestamp_seconds is not None:
                    keys.add((x.clock_id or "", round(x.timestamp_seconds, 9)))
            common_keys = keys if common_keys is None else (common_keys & keys)
        return bool(common_keys)

    def _reconcile_point_observation_correlation(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        """Suppress point-state verdicts that rely on uncorrelated observations.

        A point failure can prove a nonconformance only when the point-valued
        applicability evidence and the response observation are known to describe
        the same evaluation instant. INTERVAL_STATE/scope applicability evidence
        does not need point correlation because it explicitly covers an interval.
        """
        if req.applicability != Applicability.APPLICABLE:
            return
        if req.timing_constraint.strip() or self._has_true_persistence_semantics(req):
            return
        if req.evaluation_sufficiency not in {Sufficiency.SUFFICIENT_CONFORMANCE, Sufficiency.SUFFICIENT_NONCONFORMANCE}:
            return

        app_points = [
            evidence[eid] for eid in req.applicability_evidence_ids
            if eid in evidence
            and evidence[eid].evidence_class == EvidenceClass.DIRECT_OBSERVATION
            and evidence[eid].observation_type == ObservationType.STATE_SAMPLE
        ]
        if not app_points:
            return
        eval_points = [
            evidence[eid] for eid in req.evaluation_evidence_ids
            if eid in evidence
            and evidence[eid].evidence_class == EvidenceClass.DIRECT_OBSERVATION
            and evidence[eid].observation_type == ObservationType.STATE_SAMPLE
        ]
        if not eval_points:
            req.evaluation_sufficiency = Sufficiency.INSUFFICIENT
            self._ensure_correlation_need(req)
            issues.append(self._warn(
                "POINT_OBSERVATION_CORRELATION_MISSING",
                f"{path}.evaluation_sufficiency",
                "Point-valued applicability evidence exists, but no directly observed response sample is available to correlate to the same evaluation instant; sufficiency was downgraded.",
            ))
            return

        def correlated(a, b):
            if a.observation_group and b.observation_group and a.observation_group == b.observation_group:
                return True
            if a.timestamped and b.timestamped and a.timestamp_seconds is not None and b.timestamp_seconds is not None:
                same_clock = (not a.clock_id and not b.clock_id) or (a.clock_id and a.clock_id == b.clock_id)
                return bool(same_clock and abs(a.timestamp_seconds - b.timestamp_seconds) <= 1e-9)
            return False

        if not any(all(correlated(a, e) for a in app_points) for e in eval_points):
            req.evaluation_sufficiency = Sufficiency.INSUFFICIENT
            self._ensure_correlation_need(req)
            issues.append(self._warn(
                "POINT_OBSERVATION_CORRELATION_MISSING",
                f"{path}.evaluation_sufficiency",
                "Point-valued applicability and response observations were not explicitly correlated by a shared Snapshot ID / Observation Group or aligned timestamp; sufficiency was downgraded to INSUFFICIENT.",
            ))

    def _reconcile_interval_scoped_state_conformance(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        """Prevent a point match from proving conformance over an interval-scoped condition.

        v0.5.2 makes conformance/nonconformance intentionally asymmetric.  If a
        condition-only state requirement is applicable over an explicit
        INTERVAL_STATE, one correlated response STATE_SAMPLE that contradicts the
        required state can still prove nonconformance.  The inverse is not true:
        one matching response sample cannot prove that the required state held for
        the whole interval in which the condition held.

        This rule is mechanical and therefore validator-owned.  It does not infer
        requirement meaning beyond the already decomposed condition/behavior and
        the deterministic observation types supplied in the canonical case.
        """
        if req.applicability != Applicability.APPLICABLE:
            return
        if req.evaluation_sufficiency != Sufficiency.SUFFICIENT_CONFORMANCE:
            return
        if not req.applicability_condition.strip() or req.trigger.strip():
            return
        if req.timing_constraint.strip() or self._has_true_persistence_semantics(req):
            return

        app_items = [evidence[eid] for eid in req.applicability_evidence_ids if eid in evidence]
        if not any(
            x.evidence_class == EvidenceClass.DIRECT_OBSERVATION
            and x.observation_type == ObservationType.INTERVAL_STATE
            for x in app_items
        ):
            return

        eval_items = [evidence[eid] for eid in req.evaluation_evidence_ids if eid in evidence]
        behavior_items = [
            x for x in eval_items
            if self._observation_matches_required_behavior(req.required_behavior, x.text)
        ]
        if not behavior_items:
            return

        if any(
            x.evidence_class == EvidenceClass.DIRECT_OBSERVATION
            and x.observation_type == ObservationType.INTERVAL_STATE
            for x in behavior_items
        ):
            return

        # Generic coverage/event-coverage flags and repeated point samples do not
        # convert point observations into a persistent state observation.
        if not any(
            x.evidence_class == EvidenceClass.DIRECT_OBSERVATION
            and x.observation_type == ObservationType.STATE_SAMPLE
            for x in behavior_items
        ):
            return

        req.evaluation_sufficiency = Sufficiency.INSUFFICIENT
        if not any(n.element == RequirementElementType.OBSERVATION_INTERVAL for n in req.missing_evaluation_evidence):
            behavior = self._clean_behavior(req.required_behavior) or "the required response/state"
            basis = req.applicability_condition.strip() or "the applicable condition"
            req.missing_evaluation_evidence.append(EvidenceNeed(
                element=RequirementElementType.OBSERVATION_INTERVAL,
                description=(
                    f'Sustained observation of the required response/state ("{behavior}") throughout the interval '
                    f'in which the applicability condition holds ({basis}); a matching STATE_SAMPLE proves only one instant.'
                ),
            ))
        issues.append(self._warn(
            "STATE_CONFORMANCE_COVERAGE_INSUFFICIENT",
            f"{path}.evaluation_sufficiency",
            "Conformance was downgraded to INSUFFICIENT because applicability is established over an INTERVAL_STATE but the required response/state is supported only by point STATE_SAMPLE evidence. A point match cannot prove interval-wide conformance; a point contradiction may still prove nonconformance.",
        ))

    @staticmethod
    def _ensure_correlation_need(req) -> None:
        if any(re.search(r"snapshot|observation group|correlat|same evaluation", n.description, re.I) for n in req.missing_evaluation_evidence):
            return
        req.missing_evaluation_evidence.append(EvidenceNeed(
            element=RequirementElementType.RESPONSE,
            description="Correlated point observation of the required response/state at the same evaluation instant as the point-valued applicability evidence, using a shared Snapshot ID / Observation Group or aligned timestamp.",
        ))

    @staticmethod
    def _has_not_applicable_scope_evidence(req, evidence) -> bool:
        """Whether a condition-only NOT APPLICABLE decision has case-scope evidence.

        v0.4.3 intentionally does not infer an interval from a STATE_SAMPLE, even
        when generic or event coverage metadata exists. An explicit INTERVAL_STATE
        observation (or authoritative CURRENT_TICKET scope metadata) is required.
        This keeps ``value at t`` distinct from ``value throughout interval``.
        """
        for eid in req.applicability_evidence_ids:
            item = evidence.get(eid)
            if item is None:
                continue
            if item.evidence_class == EvidenceClass.CURRENT_TICKET and item.scope_metadata:
                return True
            if item.evidence_class == EvidenceClass.DIRECT_OBSERVATION and item.observation_type == ObservationType.INTERVAL_STATE:
                return True
        return False

    @staticmethod
    def _requires_transition_semantics(text: str) -> bool:
        if not text or not text.strip():
            return False
        return bool(re.search(r"\bbecome(?:s)?\b|\btransition(?:s|ed|ing)?\b|\bchange(?:s|d)?\s+to\b", text, re.I))

    @staticmethod
    def _transition_matches_text(item, semantic_text: str) -> bool:
        """Mechanical match between an explicit transition atom and decomposed text.

        No engineering meaning is inferred here: the check only requires the
        deterministically parsed signal name and transition target to be named in
        the LLM-owned trigger/required-behavior text.
        """
        if item.observation_type != ObservationType.TRANSITION:
            return False
        if not item.signal_name or not item.transition_to:
            return False
        text = semantic_text or ""
        if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(item.signal_name)}(?![A-Za-z0-9_])", text, re.I):
            return False
        target = item.transition_to.strip()
        if target and not re.search(rf"(?<![A-Za-z0-9_]){re.escape(target)}(?![A-Za-z0-9_])", text, re.I):
            return False
        return True

    @staticmethod
    def _timing_limit_seconds(timing_constraint: str) -> Optional[float]:
        m = re.search(
            r"\bwithin\s+(\d+(?:\.\d+)?)\s*(ms|millisecond|milliseconds|s|sec|secs|second|seconds|min|mins|minute|minutes)\b",
            timing_constraint or "",
            re.I,
        )
        if not m:
            return None
        value = float(m.group(1))
        unit = m.group(2).lower()
        if unit in {"ms", "millisecond", "milliseconds"}:
            return value / 1000.0
        if unit in {"min", "mins", "minute", "minutes"}:
            return value * 60.0
        return value

    def _derive_deterministic_timing_fact(self, req, evidence, path: str, issues: list[ValidationIssue]) -> Optional[TimingFact]:
        """Compute a timing fact only from explicit transition events.

        STATE_SAMPLE observations are deliberately insufficient to timestamp a
        transition. A qualitative REPORTED_OBSERVATION is never used to bridge a
        quantitative gap. For a late-response verdict, complete event coverage is
        required so an earlier unobserved response transition cannot be assumed away.
        """
        if not req.timing_constraint.strip() or req.applicability != Applicability.APPLICABLE:
            return None
        limit_s = self._timing_limit_seconds(req.timing_constraint)
        if limit_s is None:
            issues.append(self._warn(
                "TIMING_LIMIT_NOT_MACHINE_READABLE",
                f"{path}.timing_constraint",
                "Timing constraint could not be converted to a deterministic numeric limit; timing verdict remains semantic-only and is suppressed.",
            ))
            return None

        app_items = [evidence[eid] for eid in req.applicability_evidence_ids if eid in evidence]
        eval_items = [evidence[eid] for eid in req.evaluation_evidence_ids if eid in evidence]

        trigger_candidates = [
            x for x in app_items
            if x.timestamped and x.timestamp_seconds is not None and self._transition_matches_text(x, req.trigger)
        ]
        if not trigger_candidates:
            issues.append(self._warn(
                "TIMING_TRIGGER_TRANSITION_MISSING",
                path,
                "Timing fact not derived: the trigger is transition-based but no timestamped TRANSITION evidence explicitly establishes that transition.",
            ))
            return None
        trigger_item = min(trigger_candidates, key=lambda x: x.timestamp_seconds)

        response_candidates = [
            x for x in eval_items
            if x.timestamped
            and x.timestamp_seconds is not None
            and x.timestamp_seconds >= trigger_item.timestamp_seconds
            and self._transition_matches_text(x, req.required_behavior)
        ]
        if not response_candidates:
            issues.append(self._warn(
                "TIMING_RESPONSE_TRANSITION_MISSING",
                path,
                "Timing fact not derived: no timestamped TRANSITION evidence establishes the required response transition after the trigger.",
            ))
            return None
        response_item = min(response_candidates, key=lambda x: x.timestamp_seconds)

        if trigger_item.source != response_item.source:
            if not trigger_item.clock_id or trigger_item.clock_id != response_item.clock_id:
                issues.append(self._warn(
                    "TIMEBASE_NOT_ALIGNED",
                    path,
                    "Timing fact not derived: trigger and response come from different sources without an explicitly common clock/timebase.",
                ))
                return None
        elif trigger_item.clock_id and response_item.clock_id and trigger_item.clock_id != response_item.clock_id:
            issues.append(self._warn(
                "TIMEBASE_NOT_ALIGNED",
                path,
                "Timing fact not derived: trigger and response timestamps use different clock IDs.",
            ))
            return None

        elapsed_s = response_item.timestamp_seconds - trigger_item.timestamp_seconds
        # Round at the presentation boundary to avoid binary-float artifacts such
        # as 550.0000000000007 ms.
        elapsed_ms = round(elapsed_s * 1000.0, 6)
        limit_ms = round(limit_s * 1000.0, 6)
        margin_ms = round(elapsed_ms - limit_ms, 6)

        if elapsed_s <= limit_s + 1e-12:
            return TimingFact(
                trigger_evidence_id=trigger_item.id,
                response_evidence_id=response_item.id,
                trigger_timestamp_seconds=trigger_item.timestamp_seconds,
                response_timestamp_seconds=response_item.timestamp_seconds,
                elapsed_ms=elapsed_ms,
                limit_ms=limit_ms,
                margin_ms=margin_ms,
                outcome=TimingOutcome.WITHIN_LIMIT,
                clock_id=trigger_item.clock_id or response_item.clock_id,
                complete_event_coverage=bool(trigger_item.event_coverage_complete and response_item.event_coverage_complete),
            )

        complete_event_coverage = bool(trigger_item.event_coverage_complete and response_item.event_coverage_complete)
        if not complete_event_coverage:
            issues.append(self._warn(
                "TIMING_LATE_TRANSITION_COVERAGE_INCOMPLETE",
                path,
                "A response transition was observed after the deadline, but complete event coverage is not established; an earlier unobserved response transition cannot be excluded, so violation is suppressed.",
            ))
            return None

        return TimingFact(
            trigger_evidence_id=trigger_item.id,
            response_evidence_id=response_item.id,
            trigger_timestamp_seconds=trigger_item.timestamp_seconds,
            response_timestamp_seconds=response_item.timestamp_seconds,
            elapsed_ms=elapsed_ms,
            limit_ms=limit_ms,
            margin_ms=margin_ms,
            outcome=TimingOutcome.EXCEEDS_LIMIT,
            clock_id=trigger_item.clock_id or response_item.clock_id,
            complete_event_coverage=True,
        )

    def _reconcile_persistence_sufficiency(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        """Require interval proof for conformance, but preserve point counterexamples.

        A persistence/non-occurrence obligation is asymmetric: proving that the
        required state held for the whole interval needs INTERVAL_STATE evidence,
        while one positively observed contradictory/prohibited state inside an
        established applicable scope is already enough to prove nonconformance.
        """
        if not self._has_true_persistence_semantics(req) or req.applicability == Applicability.NOT_APPLICABLE:
            return

        if self._has_persistence_point_counterexample(req, evidence):
            changed = req.evaluation_sufficiency != Sufficiency.SUFFICIENT_NONCONFORMANCE
            req.evaluation_sufficiency = Sufficiency.SUFFICIENT_NONCONFORMANCE
            if req.missing_evaluation_evidence:
                req.missing_evaluation_evidence = []
            issues.append(self._warn(
                "PERSISTENCE_POINT_COUNTEREXAMPLE_DERIVED" if changed else "PERSISTENCE_POINT_COUNTEREXAMPLE_PRESERVED",
                f"{path}.evaluation_sufficiency",
                "Derived/preserved SUFFICIENT_NONCONFORMANCE because a point observation inside the established applicable scope directly contradicts the required persistent/non-occurrence state. Interval coverage is required to prove conformance, not to prove a witnessed counterexample.",
            ))
            return

        if req.evaluation_sufficiency not in {Sufficiency.SUFFICIENT_CONFORMANCE, Sufficiency.SUFFICIENT_NONCONFORMANCE}:
            return

        eval_items = [evidence[eid] for eid in req.evaluation_evidence_ids if eid in evidence]
        has_interval_state = any(
            x.evidence_class == EvidenceClass.DIRECT_OBSERVATION and x.observation_type == ObservationType.INTERVAL_STATE
            for x in eval_items
        )
        if has_interval_state:
            remaining = [
                n for n in req.missing_evaluation_evidence
                if n.element != RequirementElementType.OBSERVATION_INTERVAL
            ]
            if len(remaining) != len(req.missing_evaluation_evidence):
                req.missing_evaluation_evidence = remaining
                issues.append(self._warn(
                    "RESOLVED_PERSISTENCE_NEEDS_REMOVED",
                    f"{path}.missing_evaluation_evidence",
                    "Removed persistence-interval evidence requests because an explicit INTERVAL_STATE observation already covers the required state across the applicable interval.",
                ))
            return
        req.evaluation_sufficiency = Sufficiency.INSUFFICIENT
        issues.append(self._warn(
            "PERSISTENCE_SUFFICIENCY_DOWNGRADED",
            f"{path}.evaluation_sufficiency",
            "Persistence conformance sufficiency was downgraded to INSUFFICIENT because no explicit INTERVAL_STATE observation covers the applicable interval. STATE_SAMPLE and coverage metadata do not establish persistence.",
        ))

    def _has_persistence_point_counterexample(self, req, evidence) -> bool:
        """Whether one direct point observation conclusively breaks a persistent rule."""
        constraint = self._persistent_state_constraint(req.required_behavior)
        if constraint is None:
            return False
        mode, target = constraint
        behavior_signals = self._signal_names_in_text(req.required_behavior, evidence)
        if not behavior_signals:
            return False

        app_items = [evidence[eid] for eid in req.applicability_evidence_ids if eid in evidence]
        app_interval = any(
            x.evidence_class == EvidenceClass.DIRECT_OBSERVATION
            and x.observation_type == ObservationType.INTERVAL_STATE
            for x in app_items
        )
        app_points = [
            x for x in app_items
            if x.evidence_class == EvidenceClass.DIRECT_OBSERVATION
            and x.observation_type in {ObservationType.STATE_SAMPLE, ObservationType.TRANSITION}
        ]

        def correlated(a, b) -> bool:
            if a.observation_group and b.observation_group and a.observation_group == b.observation_group:
                return True
            if a.timestamped and b.timestamped and a.timestamp_seconds is not None and b.timestamp_seconds is not None:
                same_clock = (not a.clock_id and not b.clock_id) or (a.clock_id and a.clock_id == b.clock_id)
                return bool(same_clock and abs(a.timestamp_seconds - b.timestamp_seconds) <= 1e-9)
            return False

        for eid in req.evaluation_evidence_ids:
            item = evidence.get(eid)
            if item is None or item.evidence_class != EvidenceClass.DIRECT_OBSERVATION:
                continue
            if item.observation_type not in {ObservationType.STATE_SAMPLE, ObservationType.TRANSITION}:
                continue
            if not item.signal_name or item.signal_name.lower() not in behavior_signals:
                continue
            value = (item.signal_value or item.transition_to or "").strip()
            if not value:
                continue
            if mode == "PROHIBIT":
                contradicts = value.lower() == target.lower()
            else:
                contradicts = value.lower() != target.lower()
            if not contradicts:
                continue
            if app_interval:
                return True
            if app_points and all(correlated(a, item) for a in app_points):
                return True
        return False

    @staticmethod
    def _persistent_state_constraint(required_behavior: str):
        text = " ".join((required_behavior or "").split())
        m = re.search(r"\b(?:shall|must)\s+not\s+(?:be\s+)?([A-Za-z0-9_.+\-]+)", text, re.I)
        if m:
            return ("PROHIBIT", m.group(1))
        m = re.search(r"\b(?:shall|must)\s+(?:remain|stay)\s+([A-Za-z0-9_.+\-]+)", text, re.I)
        if m:
            return ("REQUIRE", m.group(1))
        return None

    def _reconcile_timing_sufficiency_and_needs(self, req, timing_fact: Optional[TimingFact], path: str, issues: list[ValidationIssue]) -> None:
        if not req.timing_constraint.strip() or req.applicability == Applicability.NOT_APPLICABLE:
            return

        if timing_fact is None:
            if req.evaluation_sufficiency in {Sufficiency.SUFFICIENT_CONFORMANCE, Sufficiency.SUFFICIENT_NONCONFORMANCE}:
                req.evaluation_sufficiency = Sufficiency.INSUFFICIENT
                issues.append(self._warn(
                    "TIMING_SUFFICIENCY_DOWNGRADED",
                    f"{path}.evaluation_sufficiency",
                    "Timing sufficiency was downgraded to INSUFFICIENT because deterministic transition/timestamp evidence does not support a conclusive numeric timing fact. Qualitative reported wording cannot bridge that gap.",
                ))
            return

        expected = (
            Sufficiency.SUFFICIENT_CONFORMANCE
            if timing_fact.outcome == TimingOutcome.WITHIN_LIMIT
            else Sufficiency.SUFFICIENT_NONCONFORMANCE
        )
        if req.evaluation_sufficiency != expected:
            req.evaluation_sufficiency = expected
            issues.append(self._warn(
                "TIMING_SUFFICIENCY_DERIVED",
                f"{path}.evaluation_sufficiency",
                f"Normalized timing sufficiency from deterministic transition timestamps: {timing_fact.elapsed_ms:g} ms observed against {timing_fact.limit_ms:g} ms allowed.",
            ))

        if req.missing_evaluation_evidence:
            req.missing_evaluation_evidence = []
            issues.append(self._warn(
                "RESOLVED_TIMING_NEEDS_REMOVED",
                f"{path}.missing_evaluation_evidence",
                "Removed timing evidence requests because deterministic trigger/response transition timestamps and required coverage already resolve the timing evaluation.",
            ))

    def _enforce_sufficiency_missing_evidence_consistency(self, req, path: str, issues: list[ValidationIssue]) -> None:
        if req.evaluation_sufficiency not in {Sufficiency.SUFFICIENT_CONFORMANCE, Sufficiency.SUFFICIENT_NONCONFORMANCE}:
            return
        if not req.missing_evaluation_evidence:
            return
        req.evaluation_sufficiency = Sufficiency.INSUFFICIENT
        issues.append(self._warn(
            "SUFFICIENCY_DOWNGRADED_MISSING_EVIDENCE",
            f"{path}.evaluation_sufficiency",
            "A requirement cannot be simultaneously evaluation-sufficient and still list required evaluation evidence; sufficiency was downgraded to INSUFFICIENT.",
        ))

    def _derive_evaluation_status(self, req, evidence, path: str, issues: list[ValidationIssue], timing_fact: Optional[TimingFact] = None) -> EvaluationStatus:
        nt = req.normative_type
        app = req.applicability

        if nt in {NormativeType.PERMISSIVE, NormativeType.ADVISORY, NormativeType.DESCRIPTIVE}:
            return EvaluationStatus.NO_COMPLIANCE_VERDICT
        if nt == NormativeType.AMBIGUOUS:
            return EvaluationStatus.NOT_EVALUABLE
        if app == Applicability.UNKNOWN:
            return EvaluationStatus.NOT_EVALUABLE
        if app == Applicability.NOT_APPLICABLE:
            return EvaluationStatus.NO_COMPLIANCE_VERDICT
        if req.evaluation_sufficiency == Sufficiency.INSUFFICIENT:
            return EvaluationStatus.NOT_EVALUABLE

        eval_items = [evidence[eid] for eid in req.evaluation_evidence_ids if eid in evidence]
        app_items = [evidence[eid] for eid in req.applicability_evidence_ids if eid in evidence]

        if req.timing_constraint.strip():
            if not req.trigger.strip():
                issues.append(self._issue("TIMING_WITHOUT_TRIGGER", f"{path}.trigger", "Timing constraint exists but the trigger was not decomposed."))
                return EvaluationStatus.NOT_EVALUABLE
            if timing_fact is None:
                # v0.4.3: a timed compliance verdict requires a deterministic timing
                # fact built from explicit transition events. Timestamped STATE_SAMPLE
                # observations and qualitative report wording are not enough.
                return EvaluationStatus.NOT_EVALUABLE

        if self._has_true_persistence_semantics(req) and not any(
            x.evidence_class == EvidenceClass.DIRECT_OBSERVATION and x.observation_type == ObservationType.INTERVAL_STATE
            for x in eval_items
        ):
            if (
                req.evaluation_sufficiency == Sufficiency.SUFFICIENT_NONCONFORMANCE
                and self._has_persistence_point_counterexample(req, evidence)
            ):
                return EvaluationStatus.VIOLATED
            issues.append(self._warn(
                "PERSISTENCE_INTERVAL_STATE_MISSING",
                path,
                "Persistence conformance verdict suppressed: no explicit INTERVAL_STATE observation establishes the required state across the applicable interval. A STATE_SAMPLE or generic coverage flag is insufficient unless it is a witnessed counterexample proving nonconformance.",
            ))
            return EvaluationStatus.NOT_EVALUABLE

        if req.evaluation_sufficiency == Sufficiency.SUFFICIENT_CONFORMANCE:
            return EvaluationStatus.SATISFIED
        if req.evaluation_sufficiency == Sufficiency.SUFFICIENT_NONCONFORMANCE:
            return EvaluationStatus.VIOLATED
        return EvaluationStatus.NOT_EVALUABLE

    @staticmethod
    def _source_has_explicit_reverse_condition(text: str) -> bool:
        """Whether the source itself explicitly states necessity/exclusivity.

        The generic converse guard must not erase semantics from requirements
        that genuinely say ``only if``, ``only when`` or ``if and only if``.
        """
        patterns = (
            r"\bif\s+and\s+only\s+if\b",
            r"\biff\b",
            r"\bonly\s+(?:if|when|under|while|during)\b",
        )
        return any(re.search(p, text, re.I) for p in patterns)

    @classmethod
    def _is_one_way_conditional_source(cls, text: str) -> bool:
        """Return True for one-way IF/WHEN/UPON source requirements.

        ``If A, B`` and ``When A, B`` establish A -> B. They do not establish
        B -> A unless the source explicitly adds reverse/exclusive wording.
        """
        has_condition = bool(re.search(r"\b(?:if|when|upon)\b", text, re.I))
        return has_condition and not cls._source_has_explicit_reverse_condition(text)

    @staticmethod
    def _conditional_converse_risk(text: str) -> bool:
        """Detect paraphrases that reverse a one-way conditional requirement."""
        patterns = (
            r"\bonly\s+(?:if|when|under|while|during)\b",
            r"\b(?:is|are|was|were)\s+(?:a\s+)?(?:necessary|required)\s+(?:condition\s+)?for\b",
            r"\b(?:necessary|required)\s+for\b",
            r"\bis\s+required\s+before\b|\bare\s+required\s+before\b",
            r"\bprerequisite\b",
            r"\bmust\s+hold\s+(?:for|before)\b",
        )
        return any(re.search(p, text, re.I) for p in patterns)

    @staticmethod
    def _permissive_relevance_has_converse_risk(text: str) -> bool:
        """Detect soft necessity/exclusivity wording in permissive relevance prose.

        A one-way permission such as ``If A, B may occur`` must not become a
        gate, prerequisite, or statement that B is allowed *only* when A.
        This catches softer paraphrases that avoid the literal phrase
        ``only if`` but still reverse the logical direction.
        """
        patterns = (
            r"\bdefines?\s+whether\b",
            r"\bwhether\b.{0,100}\b(?:allowed|permitted|enabled)\b",
            r"\b(?:allowed|permitted|enabled)\b.{0,80}\bat\s+all\b",
            r"\bpermission\s+gate\b|\bgating\b|\bgate\b",
            r"\bprerequisite\b|\bnecessary\b",
            r"\bis\s+required\s+for\b|\brequired\s+before\b",
            r"\bonly\s+(?:if|when|under)\b",
            r"\bdepends?\s+on\b.{0,100}\b(?:permission|accept|process|enable)\b",
        )
        return any(re.search(p, text, re.I) for p in patterns)

    @staticmethod
    def _relevance_has_causal_alternative(text: str) -> bool:
        """Detect hypothesis-like alternative explanations inside relevance prose."""
        patterns = (
            r"\b(?:alternative|possible)\s+explanation\b",
            r"\bcould\s+explain\b",
            r"\bcould\s+be\s+(?:a\s+)?correct\s+response\b",
            r"\brather\s+than\s+(?:a\s+)?failure\b",
            r"\brule\s+out\b",
            r"\broot\s+cause\b|\bpossible\s+cause\b|\bpotential\s+mechanism\b",
            r"\bexplain(?:s|ed|ing)?\b|\bexplanation\b",
            # v0.3.5: relevance must not become a precondition for attributing
            # the symptom/failure to another requirement or activation path.
            r"\b(?:exclude|excluded|excluding|confirm|confirmed|confirming)\b.{0,100}\bbefore\s+attribut(?:e|ed|ing)\b",
            r"\battribut(?:e|ed|ing)\b.{0,120}\b(?:failure|violation|root\s+cause|cause)\b",
        )
        return any(re.search(p, text, re.I) for p in patterns)

    @staticmethod
    def _is_safe_evidence_limitation_relevance(req, text: str) -> bool:
        """Allow descriptive evidence-limit wording that is not a failure mechanism.

        Phrases such as ``timing remains unevaluable due to absent timestamps``
        use causal grammar linguistically, but they do not hypothesize an
        engineering cause. v0.3.4 treated the literal phrase ``due to`` as unsafe
        and replaced otherwise-correct timed-requirement relevance prose.
        """
        if not req.timing_constraint.strip():
            return False
        lower = text.lower()
        says_unevaluable = bool(re.search(
            r"(?:timing|constraint|window|deadline).{0,100}(?:unevaluable|not\s+evaluable|cannot\s+be\s+evaluated|can't\s+be\s+evaluated)",
            lower,
            re.I,
        ))
        mentions_evidence_gap = any(token in lower for token in (
            "timestamp", "timebase", "coverage", "trigger confirmation", "trigger/response", "evidence",
        ))
        return says_unevaluable and mentions_evidence_gap

    def _normalize_relevance(self, req, path: str, issues: list[ValidationIssue]) -> None:
        relevance = req.relevance.strip()
        label = relevance.upper()

        cross_req_ref = any(
            rid.upper() != req.requirement_id.upper()
            for rid in re.findall(r"\bREQ[-_ ]?\d+\b", relevance, re.I)
        )
        permissive_converse_risk = (
            req.normative_type == NormativeType.PERMISSIVE
            and self._permissive_relevance_has_converse_risk(relevance)
        )
        conditional_converse_risk = (
            self._is_one_way_conditional_source(req.requirement_text)
            and self._conditional_converse_risk(relevance)
        )
        causal_alternative = self._relevance_has_causal_alternative(relevance)
        causal_term_hit = any(term in relevance.lower() for term in self.causal_terms)
        if causal_term_hit and self._is_safe_evidence_limitation_relevance(req, relevance):
            causal_term_hit = False

        unsafe = (
            label in {"PRIMARY", "SECONDARY", "PERIPHERAL"}
            or causal_term_hit
            or causal_alternative
            or permissive_converse_risk
            or conditional_converse_risk
            or cross_req_ref
        )
        if not unsafe:
            return

        # Relevance is presentation metadata, not a place for cross-requirement
        # dependency inference, compliance verdicts, causal alternatives, or a
        # converse/necessity reading of a one-way permissive requirement.
        if req.normative_type == NormativeType.PERMISSIVE:
            if req.applicability_condition.strip():
                req.relevance = (
                    f"This permissive requirement permits its stated behavior when {req.applicability_condition.strip()}; "
                    "it makes no statement about whether the same behavior is permitted under other conditions."
                )
            else:
                req.relevance = "This permissive requirement defines permitted behavior relevant to the affected functionality; it does not create a compliance obligation."
        elif req.trigger.strip():
            req.relevance = "This requirement directly defines the required response to its own trigger and is relevant to evaluating the affected functionality."
        elif req.applicability_condition.strip():
            req.relevance = (
                f"This requirement defines the required behavior when {req.applicability_condition.strip()}; "
                "its applicability depends on whether that condition is established in the current case."
            )
        else:
            req.relevance = "This requirement defines behavior relevant to evaluating the affected functionality."

        issues.append(self._warn(
            "RELEVANCE_PROSE_NORMALIZED",
            f"{path}.relevance",
            "Replaced relevance wording that was only a label or introduced causal, cross-requirement, explanatory, or conditional-converse interpretation with neutral requirement-local prose.",
        ))

    def _normalize_timing_relevance_claim(self, req, evidence, path: str, issues: list[ValidationIssue]) -> None:
        """Prevent a non-timestamped observation from being described as proving a timing failure."""
        if not req.timing_constraint.strip() or not req.relevance.strip():
            return

        mapped = [evidence[eid] for eid in req.evaluation_evidence_ids if eid in evidence]
        app_mapped = [evidence[eid] for eid in req.applicability_evidence_ids if eid in evidence]
        has_trigger_transition = any(
            e.timestamped and self._transition_matches_text(e, req.trigger)
            for e in app_mapped
        )
        has_response_transition = any(
            e.timestamped and self._transition_matches_text(e, req.required_behavior)
            for e in mapped
        )

        # v0.4.3+: an explicit trigger + response transition is enough for an
        # observed within-limit response. If the observed response is after the
        # limit, relevance may call it a timing exceedance only when explicit
        # event completeness excludes an earlier omitted matching transition.
        has_complete_timing_evidence = False
        timing_pair = None
        if has_trigger_transition and has_response_transition:
            limit_s = self._timing_limit_seconds(req.timing_constraint)
            trigger_items = [
                e for e in app_mapped
                if e.timestamped and e.timestamp_seconds is not None and self._transition_matches_text(e, req.trigger)
            ]
            response_items = [
                e for e in mapped
                if e.timestamped and e.timestamp_seconds is not None and self._transition_matches_text(e, req.required_behavior)
            ]
            if limit_s is not None and trigger_items and response_items:
                trigger_item = min(trigger_items, key=lambda e: e.timestamp_seconds)
                after = [e for e in response_items if e.timestamp_seconds >= trigger_item.timestamp_seconds]
                if after:
                    response_item = min(after, key=lambda e: e.timestamp_seconds)
                    same_clock = not (
                        trigger_item.clock_id and response_item.clock_id and trigger_item.clock_id != response_item.clock_id
                    )
                    elapsed = response_item.timestamp_seconds - trigger_item.timestamp_seconds
                    timing_pair = (trigger_item, response_item, same_clock, elapsed, limit_s)
                    if same_clock:
                        if elapsed <= limit_s + 1e-12:
                            has_complete_timing_evidence = True
                        else:
                            has_complete_timing_evidence = bool(
                                trigger_item.event_coverage_complete and response_item.event_coverage_complete
                            )
        if has_complete_timing_evidence:
            return

        rel = req.relevance

        # v0.3.5: preserve already-correct prose that explicitly separates a
        # response observation from an unevaluable timing constraint. The older
        # proximity regex could see "within 500 ms" and "did not become ACTIVE"
        # in the same sentence and rewrite it even when the sentence itself
        # correctly said timing remained unevaluable.
        explicit_timing_limit = bool(re.search(
            r"(?:timing|constraint|window|deadline).{0,120}(?:remains?\s+)?(?:unevaluable|not\s+evaluable|cannot\s+be\s+evaluated|can't\s+be\s+evaluated)",
            rel,
            re.I,
        ))
        known_timing_wording_contradiction = bool(
            timing_pair is not None
            and re.search(
                r"without\s+trigger/response\s+timing|without\s+(?:the\s+)?trigger\s+(?:and|/)\s*response\s+timing|"
                r"trigger\s+(?:timestamp|timing).{0,60}(?:missing|not\s+available)|"
                r"response\s+(?:timestamp|timing).{0,60}(?:missing|not\s+available)",
                rel,
                re.I,
            )
        )
        if explicit_timing_limit and not known_timing_wording_contradiction:
            return

        timing_failure_claim = bool(re.search(
            r"(?:timing|\bms\b|deadline|bound|window).{0,120}(?:not achieved|not met|missed|violat|failed|exceed|did not occur|didn't occur|did not happen|not occur)|"
            r"(?:not achieved|not met|missed|violat|failed|exceed|did not occur|didn't occur|did not happen|not occur).{0,120}(?:timing|\bms\b|deadline|bound|window)",
            rel,
            re.I,
        ))
        if not timing_failure_claim and not known_timing_wording_contradiction:
            return

        behavior = self._clean_behavior(req.required_behavior) or "the required response/state"
        trigger = req.trigger.strip()
        if timing_pair is not None:
            trigger_item, response_item, same_clock, elapsed, limit_s = timing_pair
            elapsed_ms = elapsed * 1000.0
            limit_ms = limit_s * 1000.0
            if same_clock:
                req.relevance = (
                    f'This requirement defines the response "{behavior}" for the trigger "{trigger}" with a timing constraint '
                    f"of {req.timing_constraint.strip()}. Trigger and observed response timestamps are available on the same clock "
                    f"({elapsed_ms:g} ms visible separation versus {limit_ms:g} ms allowed), but complete transition-event coverage is unavailable, "
                    "so an earlier omitted matching response transition cannot be excluded and the timing constraint cannot be evaluated conclusively."
                )
            else:
                req.relevance = (
                    f'This requirement defines the response "{behavior}" for the trigger "{trigger}" with a timing constraint '
                    f"of {req.timing_constraint.strip()}. Trigger and response timestamps are available, but they use different clocks/sources; "
                    "an alignable timebase is required because the timing constraint cannot be evaluated across the current clocks."
                )
        elif trigger:
            req.relevance = (
                f'This requirement directly defines the response "{behavior}" for the trigger "{trigger}" and imposes a timing constraint '
                f"of {req.timing_constraint.strip()}. The timing constraint cannot be evaluated because the available evidence does not yet provide the complete trigger/response timing basis needed for a verdict."
            )
        else:
            req.relevance = (
                f"This requirement defines {behavior} with a timing constraint of {req.timing_constraint.strip()}. "
                "The supplied response observation is relevant, but the timing constraint cannot be evaluated from the available timing evidence."
            )
        issues.append(self._warn(
            "TIMING_RELEVANCE_CLAIM_NORMALIZED",
            f"{path}.relevance",
            "Removed wording that implied a timing failure without sufficient timestamped/covered evidence.",
        ))

    def _normalize_case_validity_needs(self, data, canonical_case, issues):
        """Keep case-validity requests only for explicitly tagged scope metadata.

        Ticket narrative and the authoritative Reported Test Result are accepted as
        their own evidence classes; they are not automatically converted into a
        second branch that asks for independent proof.
        """
        if canonical_case is None:
            return []
        eligible = [e for e in canonical_case.evidence_inventory if e.evidence_class == EvidenceClass.CURRENT_TICKET and e.scope_metadata]
        if not eligible:
            if data.case_validity_needs:
                issues.append(self._warn(
                    "CASE_VALIDITY_NEEDS_REMOVED",
                    "semantic.case_validity_needs",
                    "Removed case-validity requests because the canonical case contains no CURRENT_TICKET scope metadata marked for independent validation.",
                ))
            data.case_validity_needs = []
            return []

        kept = []
        eligible_text = "\n".join(e.text.lower() for e in eligible)
        for item in data.case_validity_needs:
            assertion = item.ticket_assertion.strip()
            if assertion and assertion.lower() in eligible_text and item.evidence_needed.strip():
                kept.append(item)
            else:
                issues.append(self._warn(
                    "CASE_VALIDITY_NEED_NOT_SCOPE_METADATA",
                    "semantic.case_validity_needs",
                    "Removed a case-validity request that was not tied to explicitly tagged ticket scope metadata.",
                ))
        data.case_validity_needs = kept
        return kept

    def _validate_prose(self, req, path: str, issues: list[ValidationIssue]) -> None:
        combined = f"{req.faithful_meaning}\n{req.relevance}".lower()
        req_text = req.requirement_text.lower()

        if self._is_one_way_conditional_source(req.requirement_text) and self._conditional_converse_risk(req.faithful_meaning):
            issues.append(self._issue(
                "CONDITIONAL_CONVERSE_RISK",
                f"{path}.faithful_meaning",
                "Faithful meaning reverses a one-way conditional/trigger into an only-if/necessary-condition claim not present in the source requirement.",
            ))

        if req.normative_type == NormativeType.PERMISSIVE:
            forbidden_patterns = [
                r"\bonly\s+if\b",
                r"\bonly\s+when\b",
                r"\bmust\s+hold\b",
                r"\bis\s+required\s+for\b",
                r"\bpreconditions?\s+that\s+must\b",
                r"\bdefines?\s+whether\b",
                r"\bpermission\s+gate\b|\bgating\b",
                r"\bprerequisite\b|\bnecessary\b",
                r"\b(?:allowed|permitted|enabled)\b.{0,80}\bat\s+all\b",
            ]
            if any(re.search(pat, combined, re.I) for pat in forbidden_patterns):
                issues.append(self._issue(
                    "PERMISSIVE_CONVERSE_RISK",
                    path,
                    "Permissive requirement prose introduces necessity/exclusivity not present in the one-way requirement.",
                ))

        for term in self.forbidden_process_terms:
            if term in combined and term not in req_text:
                issues.append(self._issue(
                    "INVENTED_PROCESS_CONCEPT",
                    path,
                    f"Prose introduced '{term}', which is not present in the requirement text.",
                ))
                break

        causal_term_hit = any(term in req.relevance.lower() for term in self.causal_terms)
        if causal_term_hit and not self._is_safe_evidence_limitation_relevance(req, req.relevance):
            issues.append(self._issue(
                "CAUSAL_RELEVANCE_LANGUAGE",
                f"{path}.relevance",
                "Requirement relevance contains causal/failure-mechanism language; relevance must stay descriptive.",
            ))

        if self.internal_rule_pattern.search(req.faithful_meaning) or self.internal_rule_pattern.search(req.relevance):
            issues.append(self._issue("INTERNAL_RULE_ID_LEAK", path, "Analyst-facing prose contains an internal control-rule identifier."))

    def _remove_evaluation_evidence_from_false_applicability_context(self, req, evidence, canonical_case, path, issues):
        """Use LLM-normalized predicates to reject response evidence from a known-false point context.

        Python does not parse requirement prose here. The fast requirement-language
        stage supplied DNF predicates; Python only evaluates those structured
        predicates against canonical same-snapshot/same-timestamp signal values.
        """
        normalized = next((x for x in canonical_case.requirement_language if x.requirement_id == req.requirement_id), None)
        if normalized is None or not normalized.applicability_any_of:
            return
        kept = []
        removed = []
        for eid in req.evaluation_evidence_ids:
            item = evidence.get(eid)
            if item is None or item.evidence_class != EvidenceClass.DIRECT_OBSERVATION:
                kept.append(eid)
                continue
            context = []
            for candidate in evidence.values():
                if candidate.evidence_class != EvidenceClass.DIRECT_OBSERVATION:
                    continue
                same_group = bool(item.observation_group and candidate.observation_group == item.observation_group)
                same_time = bool(
                    item.timestamped and candidate.timestamped
                    and item.timestamp_seconds is not None and candidate.timestamp_seconds is not None
                    and abs(item.timestamp_seconds - candidate.timestamp_seconds) < 1e-9
                    and (not item.clock_id or not candidate.clock_id or item.clock_id == candidate.clock_id)
                )
                if same_group or same_time:
                    context.append(candidate)
            if self._dnf_condition_definitely_false(normalized.applicability_any_of, context):
                removed.append(eid)
            else:
                kept.append(eid)
        if removed:
            req.evaluation_evidence_ids = kept
            issues.append(self._warn(
                "EVALUATION_CONTEXT_APPLICABILITY_FALSE_REMOVED",
                f"{path}.evaluation_evidence_ids",
                "Removed response evidence observed at a correlated point where the LLM-normalized applicability condition is deterministically false: " + ", ".join(removed) + ".",
            ))

    @staticmethod
    def _dnf_condition_definitely_false(groups, context_items) -> bool:
        if not groups:
            return False
        by_signal = {}
        for item in context_items:
            if item.signal_name:
                by_signal.setdefault(item.signal_name.strip().lower(), []).append(item.signal_value.strip())

        def pred_value(pred):
            values = by_signal.get((pred.signal or "").strip().lower(), [])
            if not values:
                return None
            target = (pred.value or "").strip().lower()
            if pred.operator == PredicateOperator.EQ:
                return any(v.lower() == target for v in values)
            if pred.operator == PredicateOperator.NEQ:
                return any(v.lower() != target for v in values)
            try:
                numeric_values = [float(v) for v in values]
                numeric_target = float(pred.value)
            except Exception:
                return None
            if pred.operator == PredicateOperator.LT:
                return any(v < numeric_target for v in numeric_values)
            if pred.operator == PredicateOperator.LTE:
                return any(v <= numeric_target for v in numeric_values)
            if pred.operator == PredicateOperator.GT:
                return any(v > numeric_target for v in numeric_values)
            if pred.operator == PredicateOperator.GTE:
                return any(v >= numeric_target for v in numeric_values)
            return None

        # DNF is false only if every OR alternative has at least one known-false predicate.
        group_states = []
        for group in groups:
            states = [pred_value(p) for p in group.predicates]
            if any(x is False for x in states):
                group_states.append(False)
            elif states and all(x is True for x in states):
                group_states.append(True)
            else:
                group_states.append(None)
        return bool(group_states) and all(x is False for x in group_states)

    def _validate_hypotheses(self, data, evidence, results, issues):
        """Validate positive hypothesis support without letting a hypothesis bypass an unresolved verdict.

        v0.6.5 adds an important asymmetry: when a timed requirement is NOT
        EVALUABLE because event coverage is incomplete, the same trigger/response
        observations that were already declared insufficient cannot be repackaged
        as a supported hypothesis that the actual response exceeded the limit.
        A hypothesis needs independent mechanism evidence (for example diagnostic
        or historical evidence, or some other current-case evidence not already
        consumed by the unresolved compliance evaluation) before it can survive.
        """
        valid = []
        for idx, hyp in enumerate(data.hypotheses):
            path = f"semantic.hypotheses[{idx}]"
            ids = [eid for eid in hyp.supporting_evidence_ids if eid in evidence]
            if not ids:
                issues.append(self._warn("UNSUPPORTED_HYPOTHESIS_REMOVED", path, "Hypothesis had no valid supporting evidence IDs and was removed."))
                continue
            classes = {evidence[eid].evidence_class for eid in ids}
            direct = EvidenceClass.DIRECT_OBSERVATION in classes
            reported = EvidenceClass.REPORTED_OBSERVATION in classes
            historical = EvidenceClass.HISTORICAL_EVIDENCE in classes

            ok = False
            if hyp.support_basis in {HypothesisSupportBasis.DIRECT_ABNORMALITY, HypothesisSupportBasis.DIAGNOSTIC_CHANGE}:
                ok = direct
            elif hyp.support_basis == HypothesisSupportBasis.CURRENT_CASE_MECHANISM_MATCH:
                ok = direct or reported
            elif hyp.support_basis == HypothesisSupportBasis.HISTORICAL_PLUS_CURRENT_MATCH:
                ok = historical and (direct or reported)

            if not ok:
                issues.append(self._warn("HYPOTHESIS_GATE_FAILED", path, "Hypothesis did not meet its declared positive-support basis and was removed."))
                continue

            unresolved_req = self._unresolved_timing_requirement_supported_only_by_same_evidence(ids, results, evidence)
            if unresolved_req is not None:
                issues.append(self._warn(
                    "UNRESOLVED_COMPLIANCE_HYPOTHESIS_REMOVED",
                    path,
                    f"Hypothesis was removed because {unresolved_req} is NOT EVALUABLE and the hypothesis relies only on the same trigger/response observations already declared insufficient for that unresolved timing proposition; no independent mechanism evidence is supplied.",
                ))
                continue

            hyp.supporting_evidence_ids = ids
            if hyp.confidence.upper() not in {"LOW", "MEDIUM", "HIGH"}:
                hyp.confidence = "LOW"
            valid.append(hyp)

        # Keep the authoritative semantic object consistent with the filtered
        # hypothesis list exposed by ValidatedAnalysis/session export.
        data.hypotheses = list(valid)
        return valid

    @staticmethod
    def _unresolved_timing_requirement_supported_only_by_same_evidence(ids, results, evidence):
        """Return a requirement ID when hypothesis support merely reuses unresolved timing evidence.

        This rule is deliberately structural rather than phrase-based. It does
        not attempt to recognize words such as "late" or "delayed". Instead it
        checks whether: (1) a timing requirement is NOT EVALUABLE, (2) the missing
        property is complete event/transition coverage, and (3) every positive
        hypothesis support item comes from that same mapped requirement evidence
        with no independent diagnostic/historical source.
        """
        support = set(ids)
        if not support:
            return None

        for rr in results:
            req = rr.analysis
            if rr.evaluation_status != EvaluationStatus.NOT_EVALUABLE:
                continue
            if not req.timing_constraint.strip() or rr.timing_fact is not None:
                continue
            coverage_gap = any(
                need.element in {RequirementElementType.RESPONSE, RequirementElementType.TIMING}
                and re.search(
                    r"transition-event coverage|event_coverage_complete|event coverage|earlier omitted|first response|required-response transition",
                    need.description or "",
                    re.I,
                )
                for need in req.missing_evaluation_evidence
            )
            if not coverage_gap:
                continue

            mapped = set(req.applicability_evidence_ids) | set(req.evaluation_evidence_ids)
            if not support.issubset(mapped):
                continue

            has_independent_mechanism_source = False
            for eid in support:
                item = evidence.get(eid)
                if item is None:
                    continue
                if item.evidence_class == EvidenceClass.HISTORICAL_EVIDENCE:
                    has_independent_mechanism_source = True
                    break
                if (item.source or "").strip().lower() == "current bzd / diagnostics":
                    has_independent_mechanism_source = True
                    break
            if has_independent_mechanism_source:
                continue

            return req.requirement_id
        return None

    def _derive_evidence_conflicts(self, results, evidence, issues, canonical_case=None) -> list[EvidenceConflict]:
        """Derive reported-vs-direct timing conflicts using atomic language claims when available.

        v0.7.0 delegates sentence decomposition (e.g. "PREPARED was timely, but
        ACTIVE was late") to the 4B atomic-claim stage. Python compares those
        structured claims to deterministic timing facts. Legacy whole-sentence
        regex handling remains only when no atomic claim metadata is available.
        """
        conflicts: list[EvidenceConflict] = []
        seen: set[tuple] = set()
        reported_items = [x for x in evidence.values() if x.evidence_class == EvidenceClass.REPORTED_OBSERVATION]
        claims_by_parent = {}
        if canonical_case is not None:
            for claim in canonical_case.atomic_claims:
                claims_by_parent.setdefault(claim.parent_evidence_id, []).append(claim)

        for rr in results:
            fact = rr.timing_fact
            if fact is None:
                continue
            response = evidence.get(fact.response_evidence_id)
            response_signal = (response.signal_name if response else "").strip().lower()
            response_value = (response.signal_value if response else "").strip().lower()
            for item in reported_items:
                atomic = claims_by_parent.get(item.id, [])
                if atomic:
                    relevant_claims = []
                    for claim in atomic:
                        subject_ok = not response_signal or not claim.subject.strip() or claim.subject.strip().lower() == response_signal
                        object_ok = not response_value or not claim.object_value.strip() or claim.object_value.strip().lower() == response_value
                        if subject_ok and object_ok:
                            relevant_claims.append(claim)
                    if not relevant_claims:
                        continue
                    numeric_conflict = any(
                        c.numeric_value is not None and c.numeric_unit.strip().lower() == "ms"
                        and abs(float(c.numeric_value) - fact.elapsed_ms) > 1e-6
                        for c in relevant_claims
                    )
                    outcome_conflict = any(
                        (fact.outcome == TimingOutcome.EXCEEDS_LIMIT and c.timing_assessment == AtomicTimingAssessment.WITHIN_LIMIT)
                        or (fact.outcome == TimingOutcome.WITHIN_LIMIT and c.timing_assessment == AtomicTimingAssessment.EXCEEDS_LIMIT)
                        for c in relevant_claims
                    )
                    reported_text = "; ".join(c.claim_text for c in relevant_claims if c.claim_text) or item.text
                else:
                    text = item.text or ""
                    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*ms\b", text, re.I)]
                    numeric_conflict = any(abs(x - fact.elapsed_ms) > 1e-6 for x in nums)
                    says_pass = bool(re.search(r"\b(?:pass(?:ed)?|within|timely|in\s+time)\b", text, re.I))
                    says_late = bool(re.search(r"\b(?:late|later\s+than|too\s+late|exceed)\b", text, re.I))
                    outcome_conflict = (
                        fact.outcome == TimingOutcome.EXCEEDS_LIMIT and says_pass
                    ) or (
                        fact.outcome == TimingOutcome.WITHIN_LIMIT and says_late
                    )
                    reported_text = text
                if not numeric_conflict and not outcome_conflict:
                    continue
                key = (rr.analysis.requirement_id, item.id, fact.trigger_evidence_id, fact.response_evidence_id)
                if key in seen:
                    continue
                seen.add(key)
                direct_desc = (
                    f"deterministic direct timing is {fact.elapsed_ms:g} ms against a {fact.limit_ms:g} ms limit "
                    f"({fact.outcome.value})"
                )
                conflicts.append(EvidenceConflict(
                    description=f'{rr.analysis.requirement_id}: reported claim "{reported_text.strip()}", while {direct_desc}.',
                    reported_evidence_ids=[item.id],
                    direct_evidence_ids=[fact.trigger_evidence_id, fact.response_evidence_id],
                    resolution="Requirement evaluation uses the deterministic direct transition timing; the conflicting reported claim is preserved but does not override the trace-derived fact.",
                ))
                issues.append(self._warn(
                    "EVIDENCE_SOURCE_CONFLICT_IDENTIFIED",
                    f"validated.requirement_results[{rr.analysis.requirement_id}]",
                    f"Reported timing/result conflicts with deterministic direct timing for {rr.analysis.requirement_id}; the conflict is surfaced explicitly in the final report.",
                ))
        return conflicts

    def _derive_minimum_compliance_evidence(self, results: list[RequirementResult], evidence: dict[str, EvidenceItem]) -> list[str]:
        """Build a concise deterministic evidence plan from validated semantics.

        This deliberately does not echo the model's verbose missing-evidence prose.
        It merges duplicate trigger/timestamp asks and carries conditional
        response/timing/persistence evidence forward for UNKNOWN applicability.
        """
        ordered: OrderedDict[str, None] = OrderedDict()
        for rr in results:
            req = rr.analysis
            if req.normative_type not in {NormativeType.MANDATORY, NormativeType.PROHIBITIVE}:
                continue
            if req.applicability == Applicability.NOT_APPLICABLE:
                continue
            # Only unresolved obligatory requirements need a next-evidence plan.
            # A deterministic SATISFIED/VIOLATED verdict is already closed.
            if rr.evaluation_status != EvaluationStatus.NOT_EVALUABLE:
                continue

            conditional = req.applicability == Applicability.UNKNOWN

            if req.applicability == Applicability.UNKNOWN:
                if req.trigger.strip():
                    trigger = re.sub(r"\s*\([^)]*transition event[^)]*\)\s*$", "", req.trigger.strip(), flags=re.I)
                    suffix = ", with timestamp" if req.timing_constraint.strip() else ""
                    ordered[f'{req.requirement_id} — Applicability: Observe whether {trigger}{suffix}.'] = None
                elif req.applicability_condition.strip():
                    ordered[f'{req.requirement_id} — Applicability: Observe the runtime condition ({req.applicability_condition.strip()}).'] = None
                else:
                    for need in req.missing_applicability_evidence:
                        if need.description.strip():
                            ordered[self._format_need(req.requirement_id, need, conditional=False)] = None

            cond_text = " (if applicable)" if conditional else ""
            added_eval = False
            if req.timing_constraint.strip():
                coverage_only_needs = [
                    n.description.strip() for n in req.missing_evaluation_evidence
                    if n.description.strip() and re.search(r"transition-event coverage|event_coverage_complete|earlier omitted|required-response transition", n.description, re.I)
                ]
                if coverage_only_needs:
                    ordered[
                        f'{req.requirement_id} — Evaluation{cond_text}: Provide complete transition-event coverage from the trigger through the required response deadline, so an earlier omitted matching response transition can be excluded. This is the remaining evidence needed to evaluate the timing constraint ({req.timing_constraint.strip()}).'
                    ] = None
                else:
                    ordered[
                        f'{req.requirement_id} — Evaluation{cond_text}: Observe the response/state defined by the requirement ("{self._clean_behavior(req.required_behavior)}") with timestamps and coverage sufficient to evaluate the timing constraint ({req.timing_constraint.strip()}).'
                    ] = None
                added_eval = True
                explicit_alignment_need = any(
                    n.element == RequirementElementType.TIMING
                    and re.search(r"\btimebase\b|\bclock\b|alignable|common timebase|different clocks", n.description, re.I)
                    for n in req.missing_evaluation_evidence
                )
                if explicit_alignment_need and self._timing_evidence_requires_alignment(req, evidence):
                    ordered[f'{req.requirement_id} — Timing{cond_text}: Trigger and response currently use different clocks/sources; provide an alignable timebase.'] = None

            if self._has_true_persistence_semantics(req):
                basis = req.applicability_condition.strip() or req.trigger.strip() or "the applicable condition"
                ordered[
                    f'{req.requirement_id} — Persistence{cond_text}: Observe the response/state defined by the requirement ("{self._clean_behavior(req.required_behavior)}") throughout the applicable interval ({basis}), with a sufficient observation interval to assess persistence.'
                ] = None
                added_eval = True

            if not added_eval and req.required_behavior.strip() and req.missing_evaluation_evidence:
                missing_text = " ".join(n.description for n in req.missing_evaluation_evidence)
                behavior = self._clean_behavior(req.required_behavior)
                if re.search(r"INTERVAL_STATE|throughout|full interval|complete evaluated interval|interval coverage", missing_text, re.I):
                    basis = req.applicability_condition.strip() or "the applicable interval"
                    ordered[f'{req.requirement_id} — Evaluation{cond_text}: Provide INTERVAL_STATE / interval coverage showing the required response/state ("{behavior}") throughout the applicable interval ({basis}).'] = None
                elif re.search(r"snapshot|observation group|correlat|same evaluation", missing_text, re.I):
                    ordered[f'{req.requirement_id} — Evaluation{cond_text}: Observe the required response/state ("{behavior}") in the same Snapshot ID / Observation Group or at the same aligned timestamp as the point-valued applicability evidence.'] = None
                else:
                    ordered[f'{req.requirement_id} — Evaluation{cond_text}: Observe the response/state defined by the requirement ("{behavior}").'] = None

        return list(ordered.keys())


    @staticmethod
    def _timing_evidence_requires_alignment(req: RequirementAnalysis, evidence: dict[str, EvidenceItem]) -> bool:
        """Return True only when supplied timing evidence actually spans incompatible clocks/sources.

        Minimum-next-evidence must stay minimal. Merely mentioning an "aligned"
        trace or a generic timebase in a normalized need is not enough to request
        clock alignment when trigger and response are already on the same clock.
        """
        ids = list(dict.fromkeys(list(req.applicability_evidence_ids) + list(req.evaluation_evidence_ids)))
        items = [evidence[x] for x in ids if x in evidence and evidence[x].timestamped]
        if len(items) < 2:
            return False

        clocks = {x.clock_id.strip() for x in items if x.clock_id and x.clock_id.strip()}
        if len(clocks) > 1:
            return True

        sources = {x.source.strip() for x in items if x.source and x.source.strip()}
        # Different source streams need alignment only when they do not already
        # declare one shared clock ID.
        return len(sources) > 1 and len(clocks) != 1

    def _validate_minimum_evidence_closure(self, results, compliance, issues) -> None:
        text = "\n".join(compliance).lower()
        for rr in results:
            req = rr.analysis
            if req.normative_type not in {NormativeType.MANDATORY, NormativeType.PROHIBITIVE}:
                continue
            # Only NOT EVALUABLE requirements need a "minimum next evidence" plan.
            # SATISFIED, VIOLATED and NOT APPLICABLE requirements are already resolved.
            if rr.evaluation_status != EvaluationStatus.NOT_EVALUABLE:
                continue
            rid = req.requirement_id.lower()
            if rid not in text:
                issues.append(self._issue(
                    "MINIMUM_EVIDENCE_REQUIREMENT_MISSING",
                    "validated.compliance_evidence",
                    f"Minimum-evidence plan does not contain any item for {req.requirement_id}.",
                ))
                continue
            if req.timing_constraint.strip() and not any(req.requirement_id in x and ("timing window" in x.lower() or "timing constraint" in x.lower()) for x in compliance):
                issues.append(self._issue(
                    "MINIMUM_EVIDENCE_TIMING_CLOSURE_FAILED",
                    "validated.compliance_evidence",
                    f"Minimum-evidence plan does not cover the timing evaluation for {req.requirement_id}.",
                ))
            if self._has_true_persistence_semantics(req) and not any(req.requirement_id in x and "persistence" in x.lower() for x in compliance):
                issues.append(self._issue(
                    "MINIMUM_EVIDENCE_PERSISTENCE_CLOSURE_FAILED",
                    "validated.compliance_evidence",
                    f"Minimum-evidence plan does not cover persistence evaluation for {req.requirement_id}.",
                ))

    @staticmethod
    def _clean_behavior(text: str) -> str:
        return re.sub(r"\s*\((?:persistence|permission)[^)]*\)\s*$", "", text.strip(), flags=re.I)

    @staticmethod
    def _format_need(req_id: str, need, conditional: bool = False) -> str:
        cond = " (if applicable)" if conditional else ""
        return f"{req_id} — {need.element.value}{cond}: {need.description.strip()}"

    @staticmethod
    def _mentions_timestamp(text: str) -> bool:
        return bool(re.search(r"\btimestamp(?:ed)?\b|\btime\s*stamp\b", text, re.I))

    @staticmethod
    def _existing_ids(ids, evidence, issues, path):
        result = []
        for eid in ids:
            if eid in evidence:
                result.append(eid)
            else:
                issues.append(ValidationIssue(
                    code="UNKNOWN_EVIDENCE_ID_REMOVED",
                    severity=ValidationSeverity.WARNING,
                    path=path,
                    message=f"Removed unknown evidence ID {eid}.",
                ))
        return result

    @staticmethod
    def _deterministic_normative_type(text: str):
        t = " ".join(text.lower().split())
        if re.search(r"\bshall\s+not\b|\bmust\s+not\b|\bis\s+prohibited\b|\bnot\s+permitted\b", t):
            return NormativeType.PROHIBITIVE
        if re.search(r"\bshall\b|\bmust\b|\bis\s+required\s+to\b", t):
            return NormativeType.MANDATORY
        if re.search(r"\bmay\b|\bis\s+permitted\s+to\b", t):
            return NormativeType.PERMISSIVE
        if re.search(r"\bshould\b", t):
            return NormativeType.ADVISORY
        return None

    @staticmethod
    def _issue(code: str, path: str, message: str):
        return ValidationIssue(code=code, severity=ValidationSeverity.ERROR, path=path, message=message)

    @staticmethod
    def _warn(code: str, path: str, message: str):
        return ValidationIssue(code=code, severity=ValidationSeverity.WARNING, path=path, message=message)
