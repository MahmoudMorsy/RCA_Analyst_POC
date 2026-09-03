from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .models import (
    Applicability,
    CanonicalCase,
    EvaluationStatus,
    EvidenceClass,
    EvidenceConflict,
    EvidenceNeed,
    EvidenceSemanticAnnotation,
    LogicExpression,
    LogicKind,
    NormativeType,
    ObservationType,
    PredicateOperator,
    RequirementAnalysis,
    RequirementElementType,
    RequirementIR,
    RequirementResult,
    ScopeResolution,
    SemanticAnalysis,
    SemanticIntegrityIssue,
    SemanticPreparation,
    SemanticResolution,
    Sufficiency,
    TemporalSemantics,
    TimingFact,
    TimingOutcome,
    ValidatedAnalysis,
    ValidationIssue,
    ValidationSeverity,
)


class Truth(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FactRecord:
    evidence_id: str
    signal: str
    value: str = ""
    numeric_value: Optional[float] = None
    observation_type: ObservationType = ObservationType.UNSPECIFIED
    timestamp_seconds: Optional[float] = None
    clock_id: str = ""
    observation_group: str = ""
    transition_from: str = ""
    transition_to: str = ""
    event_coverage_complete: bool = False
    interval_scope: bool = False
    scope_id: str = ""
    related_requirement_ids: Tuple[str, ...] = ()

    @property
    def context_key(self) -> str:
        if self.observation_group:
            return "GROUP:" + self.observation_group
        if self.timestamp_seconds is not None:
            return f"TIME:{self.clock_id}:{self.timestamp_seconds:.9f}"
        return ""


@dataclass
class ExprEvaluation:
    truth: Truth
    evidence_ids: List[str]


@dataclass
class ApplicabilityEvaluation:
    applicability: Applicability
    evidence_ids: List[str]
    applicable_contexts: Set[str]
    reason: str = ""


class DeterministicComplianceEngine:
    """Execute verified Requirement IR against canonical/verified evidence.

    The engine never parses requirement prose. Every logical/temporal operation
    comes from the Requirement IR or canonical trace structure. Natural-language
    evidence participates only after an LLM annotation has been verified and its
    scope resolved.
    """

    def evaluate(
        self,
        canonical: CanonicalCase,
        preparation: SemanticPreparation,
        integrity_issues: Sequence[SemanticIntegrityIssue] = (),
    ) -> ValidatedAnalysis:
        ir_by_id = {x.requirement_id: x for x in preparation.requirement_irs}
        source_by_id = {x.requirement_id: x for x in canonical.requirements}
        facts = self._build_facts(canonical, preparation.evidence_annotations)
        evidence_by_id = {x.id: x for x in canonical.evidence_inventory}

        validation_issues: List[ValidationIssue] = [
            ValidationIssue(
                code="SEMANTIC_INTEGRITY_UNRESOLVED" if issue.material_to_compliance else "SEMANTIC_INTEGRITY_WARNING",
                severity=ValidationSeverity.ERROR if issue.material_to_compliance else ValidationSeverity.WARNING,
                path=issue.requirement_id or issue.evidence_id or "semantic_preparation",
                message=issue.description,
            )
            for issue in integrity_issues
        ]
        material_req_issues: Dict[str, List[SemanticIntegrityIssue]] = {}
        global_material = []
        for issue in integrity_issues:
            if not issue.material_to_compliance:
                continue
            if issue.requirement_id:
                material_req_issues.setdefault(issue.requirement_id, []).append(issue)
            elif issue.evidence_id:
                # Evidence ambiguity blocks only requirements explicitly linked
                # through structured semantic metadata. It must not become a
                # case-wide blocker merely because the same signal name appears
                # elsewhere in Requirement IRs.
                impacted = self._requirements_linked_to_evidence(preparation, issue.evidence_id, ir_by_id)
                for rid in impacted:
                    material_req_issues.setdefault(rid, []).append(issue)
            else:
                global_material.append(issue)

        analyses: Dict[str, RequirementAnalysis] = {}
        results: Dict[str, RequirementResult] = {}
        compliance_evidence: List[str] = []

        # Resolve explicit parent/child dependencies in bounded passes. Unknown
        # relationship targets remain conservative rather than being guessed.
        pending = [x.requirement_id for x in canonical.requirements]
        for _ in range(max(1, len(pending) + 1)):
            if not pending:
                break
            progressed = False
            for rid in list(pending):
                ir = ir_by_id.get(rid)
                src = source_by_id[rid]
                if ir is None:
                    rr = self._unresolved_requirement(src.requirement_id, src.requirement_text, "No verified Requirement IR is available.")
                    analyses[rid] = rr.analysis
                    results[rid] = rr
                    pending.remove(rid)
                    progressed = True
                    continue

                parent_state = self._relationship_parent_state(ir, results)
                if parent_state == "WAIT":
                    continue

                blocked = bool(material_req_issues.get(rid)) or bool(global_material)
                rr = self._evaluate_requirement(
                    rid, src.requirement_text, ir, facts, evidence_by_id,
                    parent_state=parent_state,
                    semantically_blocked=blocked,
                )
                analyses[rid] = rr.analysis
                results[rid] = rr
                pending.remove(rid)
                progressed = True
                compliance_evidence.extend(self._needs_to_strings(rr.analysis))
            if not progressed:
                break

        for rid in pending:
            src = source_by_id[rid]
            rr = self._unresolved_requirement(rid, src.requirement_text, "Explicit requirement relationship could not be resolved from the supplied Requirement IR set.")
            analyses[rid] = rr.analysis
            results[rid] = rr
            compliance_evidence.extend(self._needs_to_strings(rr.analysis))

        ordered_analyses = [analyses[x.requirement_id] for x in canonical.requirements]
        ordered_results = [results[x.requirement_id] for x in canonical.requirements]
        semantic = SemanticAnalysis(
            affected_functionality=preparation.affected_functionality or canonical.title or "Affected functionality not explicitly named.",
            evidence_inventory=list(canonical.evidence_inventory),
            requirements=ordered_analyses,
            historical_tickets=[],
            diagnostic_evidence_ids=[e.id for e in canonical.evidence_inventory if e.source == "Current BZD / Diagnostics"],
            hypotheses=[],
            case_validity_needs=[],
        )

        conflicts = self._derive_evidence_conflicts(canonical, preparation, ordered_results)
        return ValidatedAnalysis(
            semantic=semantic,
            requirement_results=ordered_results,
            issues=validation_issues,
            compliance_evidence=self._dedupe(compliance_evidence),
            case_validity_evidence=[],
            hypotheses=[],
            evidence_conflicts=conflicts,
        )

    def _evaluate_requirement(
        self,
        rid: str,
        requirement_text: str,
        ir: RequirementIR,
        facts: Sequence[FactRecord],
        evidence_by_id,
        *,
        parent_state: str,
        semantically_blocked: bool,
    ) -> RequirementResult:
        analysis = RequirementAnalysis(
            requirement_id=rid,
            requirement_text=requirement_text,
            faithful_meaning=ir.faithful_meaning or "Semantic meaning is represented by the verified Requirement IR.",
            relevance="DIRECT",
            normative_type=ir.normative_type,
            applicability=Applicability.UNKNOWN,
            applicability_evidence_ids=[],
            applicability_condition=self._render_logic(ir.condition),
            trigger=self._render_trigger(ir),
            required_behavior=self._render_behavior(ir),
            timing_constraint=self._render_timing(ir),
            observation_interval_requirement=self._render_persistence(ir),
            explicit_relationships=[r.target_requirement_id for r in ir.relationships if r.target_requirement_id],
            evaluation_evidence_ids=[],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
            missing_applicability_evidence=[],
            missing_evaluation_evidence=[],
        )

        if semantically_blocked:
            analysis.missing_applicability_evidence = [EvidenceNeed(
                element=RequirementElementType.APPLICABILITY,
                description="Resolve the material semantic ambiguity identified during requirement/evidence compilation before deterministic compliance evaluation.",
            )]
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE)

        if parent_state == "NOT_APPLICABLE":
            analysis.applicability = Applicability.NOT_APPLICABLE
            analysis.evaluation_sufficiency = Sufficiency.NOT_REQUIRED
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NO_COMPLIANCE_VERDICT)
        if parent_state == "UNKNOWN":
            analysis.missing_applicability_evidence = [EvidenceNeed(
                element=RequirementElementType.RELATIONSHIP,
                description="Establish the applicability of the explicitly related parent/scope requirement.",
            )]
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE)

        app = self._evaluate_applicability(rid, ir, facts)
        analysis.applicability = app.applicability
        analysis.applicability_evidence_ids = app.evidence_ids

        if ir.normative_type in {NormativeType.PERMISSIVE, NormativeType.ADVISORY, NormativeType.DESCRIPTIVE}:
            if app.applicability == Applicability.UNKNOWN:
                analysis.missing_applicability_evidence = [self._app_need(ir)]
            analysis.evaluation_sufficiency = Sufficiency.NOT_REQUIRED
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NO_COMPLIANCE_VERDICT)

        if app.applicability == Applicability.NOT_APPLICABLE:
            analysis.evaluation_sufficiency = Sufficiency.NOT_REQUIRED
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NO_COMPLIANCE_VERDICT)
        if app.applicability == Applicability.UNKNOWN:
            analysis.missing_applicability_evidence = [self._app_need(ir)]
            analysis.missing_evaluation_evidence = self._evaluation_needs(ir)
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE)

        if ir.timing is not None:
            return self._evaluate_timed_requirement(analysis, rid, ir, facts)
        return self._evaluate_state_requirement(analysis, rid, ir, facts, app.applicable_contexts)

    def _evaluate_applicability(self, rid: str, ir: RequirementIR, facts: Sequence[FactRecord]) -> ApplicabilityEvaluation:
        # Explicit inherited relationship is handled before this function.
        if ir.condition is None:
            if ir.trigger is None:
                return ApplicabilityEvaluation(Applicability.APPLICABLE, [], {"CASE"}, "Unconditional obligation")
            trigger_matches = self._matching_trigger_facts(rid, ir, facts)
            if trigger_matches:
                return ApplicabilityEvaluation(Applicability.APPLICABLE, self._ids(trigger_matches), {x.context_key or "EVENT" for x in trigger_matches}, "Trigger observed")
            # Frozen semantics: lack of a visible transition does not automatically
            # prove NOT APPLICABLE, even when the supplied trace says event coverage
            # is complete. The evaluated trigger scope may still be incomplete.
            return ApplicabilityEvaluation(Applicability.UNKNOWN, [], set(), "Trigger transition not established")

        contexts = sorted({f.context_key for f in facts if f.context_key})
        true_contexts: Set[str] = set()
        evidence_ids: List[str] = []
        for ctx in contexts:
            ev = self._eval_logic(ir.condition, rid, facts, ctx)
            if ev.truth == Truth.TRUE:
                true_contexts.add(ctx)
                evidence_ids.extend(ev.evidence_ids)
        interval_eval = self._eval_logic(ir.condition, rid, facts, "__INTERVAL_ONLY__")
        if interval_eval.truth == Truth.TRUE:
            true_contexts.add("INTERVAL")
            evidence_ids.extend(interval_eval.evidence_ids)
        if true_contexts:
            return ApplicabilityEvaluation(Applicability.APPLICABLE, self._dedupe(evidence_ids), true_contexts)
        if interval_eval.truth == Truth.FALSE:
            return ApplicabilityEvaluation(Applicability.NOT_APPLICABLE, self._dedupe(interval_eval.evidence_ids), set())
        return ApplicabilityEvaluation(Applicability.UNKNOWN, self._dedupe(interval_eval.evidence_ids), set())

    def _eval_logic(self, node: LogicExpression, rid: str, facts: Sequence[FactRecord], context: str) -> ExprEvaluation:
        if node.kind == LogicKind.TRUE:
            return ExprEvaluation(Truth.TRUE, [])
        if node.kind == LogicKind.PREDICATE:
            candidates = [
                f for f in facts
                if f.signal.lower() == node.signal.lower()
                and self._fact_allowed_for_requirement(f, rid)
                and (
                    f.interval_scope
                    or (context != "__INTERVAL_ONLY__" and f.context_key == context)
                )
            ]
            if context == "__INTERVAL_ONLY__":
                candidates = [f for f in candidates if f.interval_scope]
            if not candidates:
                return ExprEvaluation(Truth.UNKNOWN, [])
            outcomes: List[Tuple[Truth, FactRecord]] = []
            for fact in candidates:
                truth = self._compare_predicate(node.operator, node.value, fact)
                outcomes.append((truth, fact))
            truths = {x[0] for x in outcomes if x[0] != Truth.UNKNOWN}
            ids = self._ids([x[1] for x in outcomes])
            if Truth.TRUE in truths and Truth.FALSE in truths:
                return ExprEvaluation(Truth.UNKNOWN, ids)
            if Truth.TRUE in truths:
                return ExprEvaluation(Truth.TRUE, ids)
            if Truth.FALSE in truths:
                return ExprEvaluation(Truth.FALSE, ids)
            return ExprEvaluation(Truth.UNKNOWN, ids)
        if node.kind == LogicKind.NOT:
            child = self._eval_logic(node.children[0], rid, facts, context)
            if child.truth == Truth.TRUE:
                return ExprEvaluation(Truth.FALSE, child.evidence_ids)
            if child.truth == Truth.FALSE:
                return ExprEvaluation(Truth.TRUE, child.evidence_ids)
            return child

        children = [self._eval_logic(x, rid, facts, context) for x in node.children]
        ids = self._dedupe([eid for x in children for eid in x.evidence_ids])
        if node.kind == LogicKind.AND:
            if any(x.truth == Truth.FALSE for x in children):
                return ExprEvaluation(Truth.FALSE, ids)
            if all(x.truth == Truth.TRUE for x in children):
                return ExprEvaluation(Truth.TRUE, ids)
            return ExprEvaluation(Truth.UNKNOWN, ids)
        if node.kind == LogicKind.OR:
            if any(x.truth == Truth.TRUE for x in children):
                return ExprEvaluation(Truth.TRUE, ids)
            if all(x.truth == Truth.FALSE for x in children):
                return ExprEvaluation(Truth.FALSE, ids)
            return ExprEvaluation(Truth.UNKNOWN, ids)
        return ExprEvaluation(Truth.UNKNOWN, ids)

    def _evaluate_timed_requirement(self, analysis: RequirementAnalysis, rid: str, ir: RequirementIR, facts: Sequence[FactRecord]) -> RequirementResult:
        trigger_matches = self._matching_trigger_facts(rid, ir, facts)
        if not trigger_matches:
            analysis.missing_applicability_evidence = [self._app_need(ir)]
            analysis.missing_evaluation_evidence = self._evaluation_needs(ir)
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE)
        trigger = sorted(trigger_matches, key=lambda x: x.timestamp_seconds if x.timestamp_seconds is not None else math.inf)[0]
        analysis.applicability_evidence_ids = self._ids([trigger])

        behavior = ir.required_behavior
        if behavior is None or not behavior.signal or ir.timing is None or ir.timing.limit_ms is None:
            analysis.missing_evaluation_evidence = self._evaluation_needs(ir)
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE)

        responses = []
        for f in facts:
            if f.signal.lower() != behavior.signal.lower() or not self._fact_allowed_for_requirement(f, rid):
                continue
            if f.observation_type != ObservationType.TRANSITION:
                continue
            target = f.transition_to or f.value
            if not self._value_matches_operator(behavior.operator, behavior.value, target, f.numeric_value):
                continue
            if trigger.timestamp_seconds is None or f.timestamp_seconds is None:
                continue
            same_clock = (not trigger.clock_id and not f.clock_id) or trigger.clock_id == f.clock_id
            if same_clock and f.timestamp_seconds >= trigger.timestamp_seconds:
                responses.append(f)
        responses.sort(key=lambda x: x.timestamp_seconds if x.timestamp_seconds is not None else math.inf)
        limit = float(ir.timing.limit_ms)

        if responses:
            response = responses[0]
            elapsed = (response.timestamp_seconds - trigger.timestamp_seconds) * 1000.0
            complete = bool(trigger.event_coverage_complete and response.event_coverage_complete)
            outcome = TimingOutcome.WITHIN_LIMIT if elapsed <= limit + 1e-9 else TimingOutcome.EXCEEDS_LIMIT
            fact = TimingFact(
                trigger_evidence_id=trigger.evidence_id,
                response_evidence_id=response.evidence_id,
                trigger_timestamp_seconds=trigger.timestamp_seconds,
                response_timestamp_seconds=response.timestamp_seconds,
                elapsed_ms=elapsed,
                limit_ms=limit,
                margin_ms=(limit - elapsed) if outcome == TimingOutcome.WITHIN_LIMIT else (elapsed - limit),
                outcome=outcome,
                clock_id=trigger.clock_id or response.clock_id,
                complete_event_coverage=complete,
            )
            analysis.evaluation_evidence_ids = self._ids([response])
            if outcome == TimingOutcome.WITHIN_LIMIT:
                analysis.evaluation_sufficiency = Sufficiency.SUFFICIENT_CONFORMANCE
                return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.SATISFIED, evidence_ids=analysis.evaluation_evidence_ids, timing_fact=fact)
            if complete:
                analysis.evaluation_sufficiency = Sufficiency.SUFFICIENT_NONCONFORMANCE
                return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.VIOLATED, evidence_ids=analysis.evaluation_evidence_ids, timing_fact=fact)
            analysis.missing_evaluation_evidence = [EvidenceNeed(
                element=RequirementElementType.OBSERVATION_INTERVAL,
                description="Complete transition-event coverage from the trigger through the timing deadline is required to exclude an earlier omitted response transition.",
            )]
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE, evidence_ids=analysis.evaluation_evidence_ids)

        # No response transition. A conclusive timeout violation requires complete
        # event coverage and a visible same-clock observation after the deadline.
        same_clock_times = [
            f.timestamp_seconds for f in facts
            if f.timestamp_seconds is not None
            and ((not trigger.clock_id and not f.clock_id) or f.clock_id == trigger.clock_id)
            and f.event_coverage_complete
        ]
        if trigger.timestamp_seconds is not None and same_clock_times and max(same_clock_times) * 1000.0 >= trigger.timestamp_seconds * 1000.0 + limit:
            analysis.evaluation_sufficiency = Sufficiency.SUFFICIENT_NONCONFORMANCE
            analysis.missing_evaluation_evidence = []
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.VIOLATED)

        analysis.missing_evaluation_evidence = self._evaluation_needs(ir)
        return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE)

    def _evaluate_state_requirement(
        self,
        analysis: RequirementAnalysis,
        rid: str,
        ir: RequirementIR,
        facts: Sequence[FactRecord],
        applicable_contexts: Set[str],
    ) -> RequirementResult:
        behavior = ir.required_behavior
        if behavior is None or not behavior.signal or behavior.operator == PredicateOperator.OTHER:
            analysis.missing_evaluation_evidence = self._evaluation_needs(ir)
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE)

        candidates = [f for f in facts if f.signal.lower() == behavior.signal.lower() and self._fact_allowed_for_requirement(f, rid)]
        relevant: List[FactRecord] = []
        for f in candidates:
            if f.interval_scope:
                relevant.append(f)
            elif "INTERVAL" in applicable_contexts or "CASE" in applicable_contexts:
                relevant.append(f)
            elif f.context_key and f.context_key in applicable_contexts:
                relevant.append(f)
        if not relevant:
            analysis.missing_evaluation_evidence = self._evaluation_needs(ir)
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE)

        matching = [f for f in relevant if self._value_matches_operator(behavior.operator, behavior.value, f.transition_to or f.value, f.numeric_value)]
        contradicting = [f for f in relevant if self._value_contradicts_operator(behavior.operator, behavior.value, f.transition_to or f.value, f.numeric_value)]

        # A witnessed counterexample is enough for nonconformance even when the
        # obligation is persistent; interval completeness is asymmetric and is
        # required for positive persistence conformance, not for a contradiction.
        if contradicting:
            analysis.evaluation_evidence_ids = self._ids(contradicting)
            analysis.evaluation_sufficiency = Sufficiency.SUFFICIENT_NONCONFORMANCE
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.VIOLATED, evidence_ids=analysis.evaluation_evidence_ids)

        persistence = bool(ir.persistence and ir.persistence.required)
        if persistence:
            interval_matches = [f for f in matching if f.interval_scope]
            if interval_matches:
                analysis.evaluation_evidence_ids = self._ids(interval_matches)
                analysis.evaluation_sufficiency = Sufficiency.SUFFICIENT_CONFORMANCE
                return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.SATISFIED, evidence_ids=analysis.evaluation_evidence_ids)
            analysis.evaluation_evidence_ids = self._ids(matching)
            analysis.missing_evaluation_evidence = [EvidenceNeed(
                element=RequirementElementType.OBSERVATION_INTERVAL,
                description="Observe the required response state across the complete applicable interval; point samples cannot prove persistence conformance.",
            )]
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE, evidence_ids=analysis.evaluation_evidence_ids)

        if matching:
            analysis.evaluation_evidence_ids = self._ids(matching)
            analysis.evaluation_sufficiency = Sufficiency.SUFFICIENT_CONFORMANCE
            return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.SATISFIED, evidence_ids=analysis.evaluation_evidence_ids)

        analysis.missing_evaluation_evidence = self._evaluation_needs(ir)
        return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE)

    def _matching_trigger_facts(self, rid: str, ir: RequirementIR, facts: Sequence[FactRecord]) -> List[FactRecord]:
        if ir.trigger is None:
            return []
        target = ir.trigger.value.strip()
        out = []
        for f in facts:
            if f.signal.lower() != ir.trigger.signal.lower() or not self._fact_allowed_for_requirement(f, rid):
                continue
            if f.observation_type != ObservationType.TRANSITION:
                continue
            to_value = (f.transition_to or f.value).strip()
            if target and to_value.lower() != target.lower():
                continue
            out.append(f)
        return out

    def _build_facts(self, canonical: CanonicalCase, annotations: Sequence[EvidenceSemanticAnnotation]) -> List[FactRecord]:
        out: List[FactRecord] = []
        for item in canonical.evidence_inventory:
            if item.evidence_class != EvidenceClass.DIRECT_OBSERVATION:
                continue
            if item.observation_type not in {ObservationType.STATE_SAMPLE, ObservationType.TRANSITION, ObservationType.INTERVAL_STATE}:
                continue
            out.append(FactRecord(
                evidence_id=item.id,
                signal=item.signal_name,
                value=item.signal_value,
                numeric_value=self._numeric(item.signal_value),
                observation_type=item.observation_type,
                timestamp_seconds=item.timestamp_seconds,
                clock_id=item.clock_id,
                observation_group=item.observation_group,
                transition_from=item.transition_from,
                transition_to=item.transition_to,
                event_coverage_complete=item.event_coverage_complete,
                interval_scope=item.observation_type == ObservationType.INTERVAL_STATE,
                scope_id="STRUCTURAL_INTERVAL" if item.observation_type == ObservationType.INTERVAL_STATE else "",
            ))

        for ann in annotations:
            if ann.resolution == SemanticResolution.UNRESOLVED:
                continue
            for fact in ann.facts:
                if fact.resolution != SemanticResolution.VERIFIED or not fact.subject:
                    continue
                interval = (
                    fact.temporal_semantics == TemporalSemantics.PERSISTENT_STATE
                    and fact.scope.resolution == ScopeResolution.RESOLVED
                    and bool(fact.scope.scope_id.strip())
                )
                # Persistent language with unresolved scope is intentionally not
                # downgraded into point evidence. It remains non-executable.
                if fact.temporal_semantics == TemporalSemantics.PERSISTENT_STATE and not interval:
                    continue
                obs = ObservationType.INTERVAL_STATE if interval else ObservationType.STATE_SAMPLE
                if fact.temporal_semantics == TemporalSemantics.TRANSITION:
                    obs = ObservationType.TRANSITION
                out.append(FactRecord(
                    evidence_id=ann.evidence_id,
                    signal=fact.subject,
                    value=fact.value,
                    numeric_value=fact.numeric_value if fact.numeric_value is not None else self._numeric(fact.value),
                    observation_type=obs,
                    transition_to=fact.value if obs == ObservationType.TRANSITION else "",
                    interval_scope=interval,
                    scope_id=fact.scope.scope_id,
                    related_requirement_ids=tuple(fact.related_requirement_ids),
                ))
        return out

    @staticmethod
    def _fact_allowed_for_requirement(fact: FactRecord, rid: str) -> bool:
        # ``related_requirement_ids`` is semantic linkage/materiality metadata,
        # not an execution whitelist. Once a fact is VERIFIED and executable,
        # any Requirement IR may use it when the structured signal/operator/
        # value/scope actually match.
        return True

    def _compare_predicate(self, operator: PredicateOperator, expected: str, fact: FactRecord) -> Truth:
        if operator in {PredicateOperator.LT, PredicateOperator.LTE, PredicateOperator.GT, PredicateOperator.GTE}:
            left = fact.numeric_value if fact.numeric_value is not None else self._numeric(fact.value)
            right = self._numeric(expected)
            if left is None or right is None:
                return Truth.UNKNOWN
            if operator == PredicateOperator.LT:
                return Truth.TRUE if left < right else Truth.FALSE
            if operator == PredicateOperator.LTE:
                return Truth.TRUE if left <= right else Truth.FALSE
            if operator == PredicateOperator.GT:
                return Truth.TRUE if left > right else Truth.FALSE
            return Truth.TRUE if left >= right else Truth.FALSE
        actual = (fact.transition_to or fact.value).strip()
        if operator == PredicateOperator.EQ:
            return Truth.TRUE if actual.lower() == expected.strip().lower() else Truth.FALSE
        if operator == PredicateOperator.NEQ:
            return Truth.TRUE if actual.lower() != expected.strip().lower() else Truth.FALSE
        if operator == PredicateOperator.PRESENT:
            return Truth.TRUE if actual else Truth.FALSE
        if operator == PredicateOperator.ABSENT:
            return Truth.FALSE if actual else Truth.TRUE
        return Truth.UNKNOWN

    def _value_matches_operator(self, operator: PredicateOperator, expected: str, actual: str, numeric_value: Optional[float]) -> bool:
        return self._compare_predicate(operator, expected, FactRecord("", "", actual, numeric_value)) == Truth.TRUE

    def _value_contradicts_operator(self, operator: PredicateOperator, expected: str, actual: str, numeric_value: Optional[float]) -> bool:
        return self._compare_predicate(operator, expected, FactRecord("", "", actual, numeric_value)) == Truth.FALSE

    @staticmethod
    def _numeric(value: str) -> Optional[float]:
        m = re.search(r"[-+]?\d+(?:\.\d+)?", (value or "").replace(",", "."))
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None

    @classmethod
    def _render_logic(cls, node: Optional[LogicExpression]) -> str:
        if node is None:
            return ""
        if node.kind == LogicKind.TRUE:
            return "TRUE"
        if node.kind == LogicKind.PREDICATE:
            op = {
                PredicateOperator.EQ: "=", PredicateOperator.NEQ: "!=",
                PredicateOperator.LT: "<", PredicateOperator.LTE: "<=",
                PredicateOperator.GT: ">", PredicateOperator.GTE: ">=",
                PredicateOperator.PRESENT: "PRESENT", PredicateOperator.ABSENT: "ABSENT",
            }.get(node.operator, node.operator.value)
            return f"{node.signal} {op} {node.value}".strip()
        if node.kind == LogicKind.NOT:
            return f"NOT ({cls._render_logic(node.children[0])})"
        sep = f" {node.kind.value} "
        return "(" + sep.join(cls._render_logic(x) for x in node.children) + ")"

    @staticmethod
    def _render_trigger(ir: RequirementIR) -> str:
        if ir.trigger is None:
            return ""
        value = f" {ir.trigger.value}" if ir.trigger.value else ""
        return f"{ir.trigger.signal} {ir.trigger.event}{value}".strip()

    @staticmethod
    def _render_behavior(ir: RequirementIR) -> str:
        b = ir.required_behavior
        if b is None:
            return ""
        if b.process_description:
            return b.process_description
        op = {
            PredicateOperator.EQ: "=", PredicateOperator.NEQ: "!=",
            PredicateOperator.LT: "<", PredicateOperator.LTE: "<=",
            PredicateOperator.GT: ">", PredicateOperator.GTE: ">=",
        }.get(b.operator, b.operator.value)
        event = f" {b.event}" if b.event else ""
        return f"{b.signal}{event} {op} {b.value}".strip()

    @staticmethod
    def _render_timing(ir: RequirementIR) -> str:
        if ir.timing is None or ir.timing.limit_ms is None:
            return ""
        return f"within {ir.timing.limit_ms:g} ms"

    @staticmethod
    def _render_persistence(ir: RequirementIR) -> str:
        if ir.persistence is None or not ir.persistence.required:
            return ""
        return f"Persist across scope: {getattr(ir.persistence.scope, 'value', ir.persistence.scope)}"

    @staticmethod
    def _app_need(ir: RequirementIR) -> EvidenceNeed:
        if ir.trigger is not None:
            return EvidenceNeed(
                element=RequirementElementType.TRIGGER,
                description=f"Observe the required trigger transition {ir.trigger.signal} {ir.trigger.event} {ir.trigger.value}.".strip(),
            )
        return EvidenceNeed(
            element=RequirementElementType.APPLICABILITY,
            description="Observe or resolve the runtime condition represented by the verified Requirement IR.",
        )

    @staticmethod
    def _evaluation_needs(ir: RequirementIR) -> List[EvidenceNeed]:
        needs: List[EvidenceNeed] = []
        if ir.required_behavior is not None:
            needs.append(EvidenceNeed(
                element=RequirementElementType.RESPONSE,
                description="Observe the response/state represented by the verified Requirement IR during the applicable context.",
            ))
        if ir.timing is not None:
            needs.append(EvidenceNeed(
                element=RequirementElementType.TIMING,
                description="Provide trigger/response transition timestamps and sufficient event coverage to evaluate the timing limit.",
            ))
        if ir.persistence is not None and ir.persistence.required:
            needs.append(EvidenceNeed(
                element=RequirementElementType.OBSERVATION_INTERVAL,
                description="Provide resolved interval evidence covering the full applicable persistence scope.",
            ))
        return needs

    @staticmethod
    def _relationship_parent_state(ir: RequirementIR, results: Dict[str, RequirementResult]) -> str:
        # Tolerate explicit parent/inherited-scope relationship labels without
        # interpreting natural-language requirement text.
        parents = []
        for rel in ir.relationships:
            typ = rel.relationship_type.upper()
            if rel.target_requirement_id and (typ == "CHILD_OF" or typ == "INHERITS_APPLICABILITY_FROM" or "PARENT" in typ):
                parents.append(rel.target_requirement_id)
        if not parents:
            return "NONE"
        for pid in parents:
            if pid not in results:
                return "WAIT"
            app = results[pid].analysis.applicability
            if app == Applicability.NOT_APPLICABLE:
                return "NOT_APPLICABLE"
            if app == Applicability.UNKNOWN:
                return "UNKNOWN"
        return "APPLICABLE"

    @staticmethod
    def _unresolved_requirement(rid: str, text: str, reason: str) -> RequirementResult:
        analysis = RequirementAnalysis(
            requirement_id=rid, requirement_text=text, faithful_meaning="Semantic compilation unresolved.", relevance="DIRECT",
            normative_type=NormativeType.AMBIGUOUS, applicability=Applicability.UNKNOWN,
            applicability_evidence_ids=[], evaluation_sufficiency=Sufficiency.INSUFFICIENT,
            missing_applicability_evidence=[EvidenceNeed(element=RequirementElementType.APPLICABILITY, description=reason)],
        )
        return RequirementResult(analysis=analysis, evaluation_status=EvaluationStatus.NOT_EVALUABLE)

    @staticmethod
    def _needs_to_strings(analysis: RequirementAnalysis) -> List[str]:
        out = []
        for need in analysis.missing_applicability_evidence:
            out.append(f"{analysis.requirement_id} — Applicability: {need.description}")
        for need in analysis.missing_evaluation_evidence:
            out.append(f"{analysis.requirement_id} — {need.element.value.title()}: {need.description}")
        return out

    @staticmethod
    def _ids(facts: Iterable[FactRecord]) -> List[str]:
        return DeterministicComplianceEngine._dedupe([x.evidence_id for x in facts if x.evidence_id])

    @staticmethod
    def _dedupe(values: Iterable[str]) -> List[str]:
        out = []
        seen = set()
        for value in values:
            if value not in seen:
                seen.add(value)
                out.append(value)
        return out

    @staticmethod
    def _requirements_linked_to_evidence(preparation: SemanticPreparation, evidence_id: str, ir_by_id: Dict[str, RequirementIR]) -> Set[str]:
        out: Set[str] = set()
        for ann in preparation.evidence_annotations:
            if ann.evidence_id != evidence_id:
                continue
            for fact in ann.facts:
                out.update(r for r in fact.related_requirement_ids if r in ir_by_id)
        return out

    @staticmethod
    def _collect_ir_signals(ir: RequirementIR, out: Set[str]) -> None:
        def walk(node):
            if node is None:
                return
            if node.kind == LogicKind.PREDICATE and node.signal:
                out.add(node.signal.lower())
            for child in node.children:
                walk(child)
        walk(ir.condition)
        if ir.trigger and ir.trigger.signal:
            out.add(ir.trigger.signal.lower())
        if ir.required_behavior and ir.required_behavior.signal:
            out.add(ir.required_behavior.signal.lower())

    def _derive_evidence_conflicts(self, canonical: CanonicalCase, preparation: SemanticPreparation, results: Sequence[RequirementResult]) -> List[EvidenceConflict]:
        # v0.8 keeps conflict detection deterministic where both sides have been
        # converted into structured facts. Natural-language disagreement itself is
        # not parsed here.
        conflicts: List[EvidenceConflict] = []
        timing_by_req = {r.analysis.requirement_id: r.timing_fact for r in results if r.timing_fact is not None}
        for ann in preparation.evidence_annotations:
            for fact in ann.facts:
                if fact.resolution != SemanticResolution.VERIFIED or fact.temporal_semantics != TemporalSemantics.TIMING:
                    continue
                if fact.numeric_value is None:
                    continue
                for rid in fact.related_requirement_ids:
                    tf = timing_by_req.get(rid)
                    if tf is None:
                        continue
                    if abs(tf.elapsed_ms - fact.numeric_value) > 1e-6:
                        conflicts.append(EvidenceConflict(
                            description=f"Reported semantic timing for {rid} conflicts with deterministic trace timing ({fact.numeric_value:g} ms reported vs {tf.elapsed_ms:g} ms measured).",
                            reported_evidence_ids=[ann.evidence_id],
                            direct_evidence_ids=[tf.trigger_evidence_id, tf.response_evidence_id],
                            resolution="Deterministic timestamped trace timing remains authoritative for the compliance result.",
                        ))
        return conflicts
