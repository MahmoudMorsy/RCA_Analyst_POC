from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")




def _coerce_none_strings(data, fields):
    """Normalize JSON null to the model's existing empty-string sentinel.

    This is a schema-envelope normalization only.  It does not invent semantic
    content: fields whose contract already uses ``""`` to mean not supplied are
    allowed to arrive from an LLM as JSON ``null`` and are normalized before
    field validation.  Material omissions are still caught by semantic integrity
    checks (for example a missing signal/semantic_id).
    """
    if isinstance(data, dict):
        out = dict(data)
        for field in fields:
            if out.get(field) is None:
                out[field] = ""
        return out
    return data

class EvidenceClass(str, Enum):
    SYSTEM_REQUIREMENT = "SYSTEM_REQUIREMENT"
    CURRENT_TICKET = "CURRENT_TICKET"
    TEST_INSTRUCTION = "TEST_INSTRUCTION"
    REPORTED_OBSERVATION = "REPORTED_OBSERVATION"
    DIRECT_OBSERVATION = "DIRECT_OBSERVATION"
    HISTORICAL_EVIDENCE = "HISTORICAL_EVIDENCE"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN_MISSING = "UNKNOWN_MISSING"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


class ObservationType(str, Enum):
    UNSPECIFIED = "UNSPECIFIED"
    STATE_SAMPLE = "STATE_SAMPLE"
    TRANSITION = "TRANSITION"
    INTERVAL_STATE = "INTERVAL_STATE"


class NormativeType(str, Enum):
    MANDATORY = "MANDATORY"
    PROHIBITIVE = "PROHIBITIVE"
    PERMISSIVE = "PERMISSIVE"
    ADVISORY = "ADVISORY"
    DESCRIPTIVE = "DESCRIPTIVE"
    AMBIGUOUS = "AMBIGUOUS"


class Applicability(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT APPLICABLE"
    UNKNOWN = "APPLICABILITY UNKNOWN"


class EvaluationStatus(str, Enum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    NOT_EVALUABLE = "NOT EVALUABLE"
    NO_COMPLIANCE_VERDICT = "NO COMPLIANCE VERDICT"


class Sufficiency(str, Enum):
    SUFFICIENT_CONFORMANCE = "SUFFICIENT_CONFORMANCE"
    SUFFICIENT_NONCONFORMANCE = "SUFFICIENT_NONCONFORMANCE"
    INSUFFICIENT = "INSUFFICIENT"
    NOT_REQUIRED = "NOT_REQUIRED"


class RequirementElementType(str, Enum):
    APPLICABILITY = "APPLICABILITY"
    TRIGGER = "TRIGGER"
    RESPONSE = "RESPONSE"
    TIMING = "TIMING"
    OBSERVATION_INTERVAL = "OBSERVATION_INTERVAL"
    RELATIONSHIP = "RELATIONSHIP"


class SourceAvailability(str, Enum):
    """Semantic availability of an input source as understood by fast intake.

    The language model owns the natural-language classification. Python only
    enforces the structural consequence: unavailable/unknown/unmentioned
    sources cannot silently become engineering evidence blocks.
    """

    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    NOT_MENTIONED = "NOT_MENTIONED"


class ContentKind(str, Enum):
    ENGINEERING_DATA = "ENGINEERING_DATA"
    SOURCE_ABSENCE = "SOURCE_ABSENCE"
    SOURCE_UNCERTAINTY = "SOURCE_UNCERTAINTY"
    USER_INSTRUCTION = "USER_INSTRUCTION"
    SECTION_HEADER = "SECTION_HEADER"
    METADATA = "METADATA"
    OTHER = "OTHER"


class AtomicClaimKind(str, Enum):
    STATE = "STATE"
    TRANSITION = "TRANSITION"
    TIMING = "TIMING"
    DIAGNOSTIC = "DIAGNOSTIC"
    CAUSAL = "CAUSAL"
    AVAILABILITY = "AVAILABILITY"
    OTHER = "OTHER"


class AtomicTimingAssessment(str, Enum):
    WITHIN_LIMIT = "WITHIN_LIMIT"
    EXCEEDS_LIMIT = "EXCEEDS_LIMIT"
    UNSPECIFIED = "UNSPECIFIED"


class PredicateOperator(str, Enum):
    EQ = "EQ"
    NEQ = "NEQ"
    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    OTHER = "OTHER"




class SemanticResolution(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    UNRESOLVED = "UNRESOLVED"


class LogicKind(str, Enum):
    TRUE = "TRUE"
    PREDICATE = "PREDICATE"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class TemporalSemantics(str, Enum):
    POINT_STATE = "POINT_STATE"
    PERSISTENT_STATE = "PERSISTENT_STATE"
    TRANSITION = "TRANSITION"
    TIMING = "TIMING"
    DIAGNOSTIC = "DIAGNOSTIC"
    OTHER = "OTHER"


class ScopeResolution(str, Enum):
    RESOLVED = "RESOLVED"
    PARTIAL = "PARTIAL"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SemanticClauseRole(str, Enum):
    CONDITION = "CONDITION"
    TRIGGER = "TRIGGER"
    REQUIRED_BEHAVIOR = "REQUIRED_BEHAVIOR"
    TIMING = "TIMING"
    PERSISTENCE = "PERSISTENCE"
    RELATIONSHIP = "RELATIONSHIP"
    EXCEPTION = "EXCEPTION"
    OTHER = "OTHER"


class EvidenceSemanticRole(str, Enum):
    APPLICABILITY = "APPLICABILITY"
    TRIGGER = "TRIGGER"
    RESPONSE = "RESPONSE"
    TIMING = "TIMING"
    DIAGNOSTIC = "DIAGNOSTIC"
    HISTORICAL = "HISTORICAL"
    RCA_CONTEXT = "RCA_CONTEXT"
    MECHANISM = "MECHANISM"
    OTHER = "OTHER"


class HypothesisSemanticType(str, Enum):
    MECHANISM_CANDIDATE = "MECHANISM_CANDIDATE"
    COMPLIANCE_RESTATEMENT = "COMPLIANCE_RESTATEMENT"
    ROOT_CAUSE_CLAIM = "ROOT_CAUSE_CLAIM"
    EVIDENCE_SUMMARY = "EVIDENCE_SUMMARY"
    OTHER = "OTHER"


class EpistemicStrength(str, Enum):
    POSSIBLE = "POSSIBLE"
    SUPPORTED_CANDIDATE = "SUPPORTED_CANDIDATE"
    CAUSALLY_ESTABLISHED = "CAUSALLY_ESTABLISHED"
    UNDETERMINED = "UNDETERMINED"


class HypothesisReviewAction(str, Enum):
    KEEP = "KEEP"
    REWRITE = "REWRITE"
    DROP = "DROP"


class HypothesisSupportBasis(str, Enum):
    DIRECT_ABNORMALITY = "DIRECT_ABNORMALITY"
    DIAGNOSTIC_CHANGE = "DIAGNOSTIC_CHANGE"
    CURRENT_CASE_MECHANISM_MATCH = "CURRENT_CASE_MECHANISM_MATCH"
    HISTORICAL_PLUS_CURRENT_MATCH = "HISTORICAL_PLUS_CURRENT_MATCH"


class EvidenceItem(StrictModel):
    id: str = Field(description="Unique evidence ID")
    evidence_class: EvidenceClass
    text: str
    source: str = Field(description="Human-readable source name/field")
    anchor: str = Field(default="", description="Timestamp/log index/ticket field when supplied")
    scope_metadata: bool = Field(default=False, description="True only when current-ticket metadata defines scope/applicability")
    timestamped: bool = False
    timestamp_seconds: Optional[float] = Field(default=None, description="Numeric timestamp in seconds when deterministically parsed from the source")
    coverage_complete: bool = Field(
        default=False,
        description="Legacy/generic coverage declaration. It does not imply complete transition-event capture and must not be used to convert a state sample into interval evidence.",
    )
    event_coverage_complete: bool = Field(
        default=False,
        description="True only when the source explicitly declares complete transition/event capture for the supplied trace scope.",
    )
    clock_id: str = Field(default="", description="Clock/timebase identifier if explicitly supplied")
    signal_name: str = Field(default="", description="Atomic observed signal/variable name when deterministically parsed")
    signal_value: str = Field(default="", description="Atomic observed signal/variable value when deterministically parsed")
    observation_type: ObservationType = Field(default=ObservationType.UNSPECIFIED, description="Deterministic observation semantics: state sample, explicit transition event, interval state, or unspecified")
    transition_from: str = Field(default="", description="Explicit prior state/value when the source states a transition from X to Y")
    transition_to: str = Field(default="", description="Explicit target state/value when the source states a transition/became/changed to Y")
    observation_group: str = Field(default="", description="Explicit snapshot/observation-group identifier used to correlate point observations captured at the same evaluation instant")
    raw_source_text: str = Field(default="", description="Optional verbatim source span retained when a fast intake normalizer produced the human-readable text field")


class RequirementSource(StrictModel):
    requirement_id: str
    requirement_text: str
    raw_source_text: str = Field(default="", description="Optional verbatim source span retained when requirement extraction used the fast intake normalizer")


class IntakeField(StrictModel):
    """One normalized intake field with its verbatim supporting source span."""

    value: str = ""
    source_span: str = ""


class IntakeRequirement(StrictModel):
    requirement_id: str
    requirement_text: str
    source_span: str


class IntakeSourceSection(StrictModel):
    """Semantic source-availability classification plus source-backed content."""

    availability: SourceAvailability = SourceAvailability.NOT_MENTIONED
    blocks: List[IntakeField] = Field(default_factory=list)
    availability_statement: IntakeField = Field(
        default_factory=IntakeField,
        description="Verbatim source-backed statement explaining ABSENT/UNKNOWN availability when explicitly stated.",
    )

    @model_validator(mode="after")
    def validate_availability_shape(self):
        if self.availability == SourceAvailability.PRESENT and not self.blocks:
            raise ValueError("PRESENT source availability requires at least one content block")
        if self.availability != SourceAvailability.PRESENT and self.blocks:
            raise ValueError("Only PRESENT source availability may contain content blocks")
        if self.availability in {SourceAvailability.ABSENT, SourceAvailability.UNKNOWN} and not self.availability_statement.source_span.strip():
            raise ValueError(f"{self.availability.value} source availability requires a source-backed availability_statement")
        if self.availability == SourceAvailability.NOT_MENTIONED and self.availability_statement.source_span.strip():
            raise ValueError("NOT_MENTIONED source availability must not contain an availability_statement")
        return self


class IntakeRequirementSection(StrictModel):
    """Requirement-source availability plus verbatim requirement items."""

    availability: SourceAvailability = SourceAvailability.NOT_MENTIONED
    items: List[IntakeRequirement] = Field(default_factory=list)
    availability_statement: IntakeField = Field(default_factory=IntakeField)

    @model_validator(mode="after")
    def validate_availability_shape(self):
        if self.availability == SourceAvailability.PRESENT and not self.items:
            raise ValueError("PRESENT requirement availability requires at least one requirement item")
        if self.availability != SourceAvailability.PRESENT and self.items:
            raise ValueError("Only PRESENT requirement availability may contain requirement items")
        if self.availability in {SourceAvailability.ABSENT, SourceAvailability.UNKNOWN} and not self.availability_statement.source_span.strip():
            raise ValueError(f"{self.availability.value} requirement availability requires a source-backed availability_statement")
        if self.availability == SourceAvailability.NOT_MENTIONED and self.availability_statement.source_span.strip():
            raise ValueError("NOT_MENTIONED requirement availability must not contain an availability_statement")
        return self


class IntakeNormalization(StrictModel):
    """Shallow 4B normalization of inconsistent human testcase formatting.

    This is not canonical evidence. Python must validate source spans, assign
    evidence IDs, parse timestamps/trace mechanics and construct CanonicalCase.
    """

    ticket_id: IntakeField = Field(default_factory=IntakeField)
    title: IntakeField = Field(default_factory=IntakeField)
    description: IntakeField = Field(default_factory=IntakeField)
    test_steps: List[IntakeField] = Field(default_factory=list)
    reported_results: List[IntakeField] = Field(default_factory=list)
    requirements: IntakeRequirementSection = Field(default_factory=IntakeRequirementSection)
    historical: IntakeSourceSection = Field(default_factory=IntakeSourceSection)
    diagnostics: IntakeSourceSection = Field(default_factory=IntakeSourceSection)
    trace: IntakeSourceSection = Field(default_factory=IntakeSourceSection)
    user_instructions: List[IntakeField] = Field(
        default_factory=list,
        description="User/operator instructions about how to analyze or handle the case; these are metadata/instructions, never engineering evidence.",
    )
    unclassified_spans: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class SourceAvailabilityDecision(StrictModel):
    availability: SourceAvailability = SourceAvailability.NOT_MENTIONED
    availability_statement: IntakeField = Field(default_factory=IntakeField)

    @model_validator(mode="before")
    @classmethod
    def coerce_statement_envelope(cls, data):
        """Accept the fast model's common compact string form without changing meaning.

        This is a schema-envelope normalization only: the exact returned string is
        copied into both value/source_span and is still verified against the raw
        user input before canonicalization.
        """
        if isinstance(data, dict):
            out = dict(data)
            statement = out.get("availability_statement")
            if isinstance(statement, str):
                out["availability_statement"] = {
                    "value": statement,
                    "source_span": statement,
                }
            return out
        return data

    @model_validator(mode="after")
    def validate_statement_shape(self):
        if self.availability in {SourceAvailability.ABSENT, SourceAvailability.UNKNOWN} and not self.availability_statement.source_span.strip():
            raise ValueError(f"{self.availability.value} availability requires a source-backed availability_statement")
        if self.availability in {SourceAvailability.PRESENT, SourceAvailability.NOT_MENTIONED} and self.availability_statement.source_span.strip():
            raise ValueError(f"{self.availability.value} availability must not carry an absence/uncertainty availability_statement")
        return self


class SourceAvailabilityNormalization(StrictModel):
    """Dedicated 4B source-availability interpretation.

    This stage decides only whether each source is present, absent, uncertain,
    or unmentioned. Python verifies source spans and enforces the resulting
    structural consequences; it does not interpret the language itself.
    """

    requirements: SourceAvailabilityDecision = Field(default_factory=SourceAvailabilityDecision)
    historical: SourceAvailabilityDecision = Field(default_factory=SourceAvailabilityDecision)
    diagnostics: SourceAvailabilityDecision = Field(default_factory=SourceAvailabilityDecision)
    trace: SourceAvailabilityDecision = Field(default_factory=SourceAvailabilityDecision)


class IntakeContentClassification(StrictModel):
    """Dedicated 4B content/section classification without availability decisions."""

    ticket_id: IntakeField = Field(default_factory=IntakeField)
    title: IntakeField = Field(default_factory=IntakeField)
    description: IntakeField = Field(default_factory=IntakeField)
    test_steps: List[IntakeField] = Field(default_factory=list)
    reported_results: List[IntakeField] = Field(default_factory=list)
    requirements: List[IntakeRequirement] = Field(default_factory=list)
    historical_blocks: List[IntakeField] = Field(default_factory=list)
    diagnostic_blocks: List[IntakeField] = Field(default_factory=list)
    trace_blocks: List[IntakeField] = Field(default_factory=list)
    user_instructions: List[IntakeField] = Field(default_factory=list)
    ignored_headers_or_metadata: List[IntakeField] = Field(default_factory=list)
    unclassified_spans: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class AtomicClaimExtraction(StrictModel):
    source_category: str
    source_span: str
    claim_text: str
    claim_kind: AtomicClaimKind = AtomicClaimKind.OTHER
    subject: str = ""
    predicate: str = ""
    object_value: str = ""
    numeric_value: Optional[float] = None
    numeric_unit: str = ""
    timing_assessment: AtomicTimingAssessment = AtomicTimingAssessment.UNSPECIFIED
    causal_strength: EpistemicStrength = EpistemicStrength.UNDETERMINED


class AtomicClaimExtractionSet(StrictModel):
    claims: List[AtomicClaimExtraction] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_bare_list_envelope(cls, data):
        """Accept a bare list as the semantically identical single-field envelope."""
        if isinstance(data, list):
            return {"claims": data}
        return data


class CanonicalAtomicClaim(StrictModel):
    claim_id: str
    parent_evidence_id: str
    source_category: str
    source_span: str
    claim_text: str
    claim_kind: AtomicClaimKind = AtomicClaimKind.OTHER
    subject: str = ""
    predicate: str = ""
    object_value: str = ""
    numeric_value: Optional[float] = None
    numeric_unit: str = ""
    timing_assessment: AtomicTimingAssessment = AtomicTimingAssessment.UNSPECIFIED
    causal_strength: EpistemicStrength = EpistemicStrength.UNDETERMINED


class RequirementPredicate(StrictModel):
    signal: str = ""
    operator: PredicateOperator = PredicateOperator.OTHER
    value: str = ""
    source_phrase: str = ""


class RequirementPredicateGroup(StrictModel):
    """One AND group. The outer list is OR across groups (DNF)."""

    predicates: List[RequirementPredicate] = Field(default_factory=list)


class RequirementLanguageNormalization(StrictModel):
    requirement_id: str
    normative_type_hint: NormativeType = NormativeType.AMBIGUOUS
    applicability_any_of: List[RequirementPredicateGroup] = Field(default_factory=list)
    trigger_signal: str = ""
    trigger_event: str = ""
    trigger_value: str = ""
    required_behavior_signal: str = ""
    required_behavior_operator: PredicateOperator = PredicateOperator.OTHER
    required_behavior_value: str = ""
    timing_limit_ms: Optional[float] = None
    persistence_required: bool = False
    explicit_relationship_ids: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class RequirementLanguageNormalizationSet(StrictModel):
    requirements: List[RequirementLanguageNormalization] = Field(default_factory=list)




class LogicExpression(StrictModel):
    """Declarative Boolean expression produced by the semantic compiler.

    Python executes this structure; it never reconstructs logic from the original
    German/English requirement wording. ``semantic_id`` links the expression back
    to the compiler's source-clause inventory for completeness validation.
    """

    kind: LogicKind
    semantic_id: str = ""
    source_phrase: str = ""
    signal: str = ""
    operator: PredicateOperator = PredicateOperator.OTHER
    value: str = ""
    children: List["LogicExpression"] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"semantic_id", "source_phrase", "signal", "value"})

    @model_validator(mode="after")
    def preserve_transport_shape(self):
        """Keep compiler transport tolerant; executability is validated downstream.

        Local LLMs can return a semantically useful partial IR that satisfies the
        JSON schema but omits a field enforced only by a Pydantic cross-field
        validator (for example ``signal`` on a PREDICATE). Rejecting the object
        here aborts the entire batch before the semantic verifier/arbitrator can
        repair it. v0.8.3 therefore separates *transport-valid* IR from
        *executable* IR: this model preserves the partial structure, while
        ``SemanticIntegrityChecker`` blocks execution and the arbitration model
        applies the strict executable contract.
        """
        return self


class RequirementEventIR(StrictModel):
    semantic_id: str = ""
    signal: str = ""
    event: str = ""
    value: str = ""
    source_phrase: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"semantic_id", "signal", "event", "value", "source_phrase"})


class RequirementBehaviorIR(StrictModel):
    semantic_id: str = ""
    signal: str = ""
    operator: PredicateOperator = PredicateOperator.OTHER
    value: str = ""
    event: str = ""
    process_description: str = ""
    source_phrase: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"semantic_id", "signal", "value", "event", "process_description", "source_phrase"})


class RequirementTimingIR(StrictModel):
    semantic_id: str = ""
    limit_ms: Optional[float] = None
    relation: str = "AFTER_TRIGGER"
    source_phrase: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"semantic_id", "relation", "source_phrase"})


class RequirementPersistenceIR(StrictModel):
    semantic_id: str = ""
    required: bool = False
    scope: str = "WHILE_CONDITION"
    source_phrase: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"semantic_id", "scope", "source_phrase"})


class RequirementRelationshipIR(StrictModel):
    semantic_id: str = ""
    relationship_type: str = ""
    target_requirement_id: str = ""
    source_phrase: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"semantic_id", "relationship_type", "target_requirement_id", "source_phrase"})


class RequirementSemanticClause(StrictModel):
    semantic_id: str
    role: SemanticClauseRole
    source_phrase: str
    resolution: SemanticResolution = SemanticResolution.VERIFIED
    notes: str = ""


class RequirementIR(StrictModel):
    """LLM-compiled intermediate representation of one natural-language requirement."""

    requirement_id: str
    faithful_meaning: str = ""
    normative_type: NormativeType = NormativeType.AMBIGUOUS
    condition: Optional[LogicExpression] = None
    trigger: Optional[RequirementEventIR] = None
    required_behavior: Optional[RequirementBehaviorIR] = None
    timing: Optional[RequirementTimingIR] = None
    persistence: Optional[RequirementPersistenceIR] = None
    relationships: List[RequirementRelationshipIR] = Field(default_factory=list)
    source_clauses: List[RequirementSemanticClause] = Field(default_factory=list)
    unresolved_semantics: List[str] = Field(default_factory=list)
    unmapped_source_spans: List[str] = Field(default_factory=list)


class EvidenceScopeAnnotation(StrictModel):
    source_phrase: str = ""
    resolution: ScopeResolution = ScopeResolution.NOT_APPLICABLE
    scope_id: str = ""
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"source_phrase", "scope_id", "notes"})


class EvidenceSemanticFact(StrictModel):
    fact_id: str
    source_phrase: str
    subject: str = ""
    operator: PredicateOperator = PredicateOperator.OTHER
    value: str = ""
    numeric_value: Optional[float] = None
    numeric_unit: str = ""
    temporal_semantics: TemporalSemantics = TemporalSemantics.OTHER
    scope: EvidenceScopeAnnotation = Field(default_factory=EvidenceScopeAnnotation)
    resolution: SemanticResolution = SemanticResolution.VERIFIED
    possible_roles: List[EvidenceSemanticRole] = Field(default_factory=list)
    related_requirement_ids: List[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"subject", "value", "numeric_unit", "notes"})


class EvidenceSemanticAnnotation(StrictModel):
    evidence_id: str
    resolution: SemanticResolution = SemanticResolution.VERIFIED
    facts: List[EvidenceSemanticFact] = Field(default_factory=list)
    unresolved_semantics: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_transport_envelope(cls, data):
        """Normalize schema-envelope mistakes without interpreting evidence language.

        Small local models sometimes return the annotation payload nested under
        ``resolution`` (for example ``resolution={facts:[...], ...}``) or emit an
        annotation-level ``scope_id`` even though scope belongs to individual
        facts.  v0.8.4 preserves the explicit fact objects and unresolved markers
        while repairing only this transport shape.  It never derives a signal,
        value, temporal meaning, scope referent, or requirement relationship from
        prose.
        """
        if not isinstance(data, dict):
            return data
        out = dict(data)
        wrapped = out.get("resolution")
        if isinstance(wrapped, dict):
            wrapped = dict(wrapped)
            if "facts" not in out and "facts" in wrapped:
                out["facts"] = wrapped.get("facts") or []
            if "unresolved_semantics" not in out and "unresolved_semantics" in wrapped:
                out["unresolved_semantics"] = wrapped.get("unresolved_semantics") or []

            explicit = wrapped.get("resolution")
            if explicit in {x.value for x in SemanticResolution}:
                out["resolution"] = explicit
            else:
                facts = out.get("facts") or []
                unresolved = out.get("unresolved_semantics") or []
                statuses = [
                    x.get("resolution") for x in facts
                    if isinstance(x, dict) and x.get("resolution") in {y.value for y in SemanticResolution}
                ]
                # This is an aggregation of already-explicit structured status,
                # not a semantic interpretation of the source text.
                if unresolved and not facts:
                    out["resolution"] = SemanticResolution.UNRESOLVED.value
                elif unresolved:
                    out["resolution"] = SemanticResolution.PARTIALLY_RESOLVED.value
                elif facts and statuses and all(x == SemanticResolution.VERIFIED.value for x in statuses):
                    out["resolution"] = SemanticResolution.VERIFIED.value
                else:
                    out["resolution"] = SemanticResolution.PARTIALLY_RESOLVED.value

        # Annotation-level scope is not part of the semantic contract because one
        # annotation may contain multiple facts/scopes.  Do not guess which fact
        # it belongs to.  Empty stray values are discarded; non-empty values are
        # preserved as unresolved transport information so they cannot silently
        # become executable coverage.
        stray_scope = out.pop("scope_id", None)
        if stray_scope not in (None, ""):
            notes = list(out.get("unresolved_semantics") or [])
            notes.append(f"Unassigned annotation-level scope_id: {stray_scope}")
            out["unresolved_semantics"] = notes
            if out.get("resolution") == SemanticResolution.VERIFIED.value:
                out["resolution"] = SemanticResolution.PARTIALLY_RESOLVED.value
        return out


class SemanticPreparation(StrictModel):
    """Merged normal 4B semantic-preparation response for the v0.8 architecture."""

    affected_functionality: str = ""
    requirement_irs: List[RequirementIR] = Field(default_factory=list)
    evidence_annotations: List[EvidenceSemanticAnnotation] = Field(default_factory=list)
    unresolved_case_semantics: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"affected_functionality"})


class RequirementCompilationBatch(StrictModel):
    """One bounded semantic-model requirement compilation batch."""

    affected_functionality: str = ""
    requirement_irs: List[RequirementIR] = Field(default_factory=list)
    unresolved_case_semantics: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"affected_functionality"})


class RequirementStructuralPatch(StrictModel):
    """Explicit model-authored patch for targeted Requirement IR fields.

    Python supplies the exact target-field list and rejects patches that modify
    untargeted fields. Python merges only these structured objects; it never
    derives their semantics from prose. ``source_clauses`` is a complete
    replacement audit inventory when targeted; it is not appended piecemeal.
    """

    requirement_id: str
    normative_type: Optional[NormativeType] = None
    condition: Optional[LogicExpression] = None
    trigger: Optional[RequirementEventIR] = None
    required_behavior: Optional[RequirementBehaviorIR] = None
    timing: Optional[RequirementTimingIR] = None
    persistence: Optional[RequirementPersistenceIR] = None
    relationships: Optional[List[RequirementRelationshipIR]] = None
    source_clauses: Optional[List[RequirementSemanticClause]] = None


class RequirementStructuralPatchBatch(StrictModel):
    patches: List[RequirementStructuralPatch] = Field(default_factory=list)


class EvidenceAnnotationBatch(StrictModel):
    """One bounded fast-model evidence-language annotation batch."""

    evidence_annotations: List[EvidenceSemanticAnnotation] = Field(default_factory=list)
    unresolved_case_semantics: List[str] = Field(default_factory=list)


class RequirementSemanticFingerprint(StrictModel):
    """Source-derived semantic structure reconstructed independently by the verifier.

    Python compares this structured fingerprint with the compiler IR; Python does
    not derive the fingerprint from natural-language requirement text.
    """

    normative_type: NormativeType = NormativeType.AMBIGUOUS
    condition: Optional[LogicExpression] = None
    trigger: Optional[RequirementEventIR] = None
    required_behavior: Optional[RequirementBehaviorIR] = None
    timing: Optional[RequirementTimingIR] = None
    persistence: Optional[RequirementPersistenceIR] = None
    relationships: List[RequirementRelationshipIR] = Field(default_factory=list)


class RequirementSemanticVerificationItem(StrictModel):
    requirement_id: str
    resolution: SemanticResolution = SemanticResolution.VERIFIED
    independent_semantics: RequirementSemanticFingerprint
    missing_or_misrepresented_source_spans: List[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_null_string_sentinels(cls, data):
        return _coerce_none_strings(data, {"notes"})


class RequirementSemanticVerificationBatch(StrictModel):
    """Independent fast-model check that compiled IR preserves source meaning."""

    requirements: List[RequirementSemanticVerificationItem] = Field(default_factory=list)


class SemanticIntegrityIssue(StrictModel):
    issue_id: str
    requirement_id: str = ""
    evidence_id: str = ""
    semantic_id: str = ""
    description: str
    material_to_compliance: bool = False
    target_fields: List[str] = Field(default_factory=list)


class SemanticArbitrationResponse(StrictModel):
    """One case-level 27B arbitration response containing issue-scoped repairs.

    v0.8.9 uses field-level RequirementStructuralPatch objects so arbitration
    cannot accidentally overwrite already-verified Requirement IR fields.
    ``requirement_irs`` remains accepted for missing-compiler-candidate recovery
    and backward-compatible session deserialization only.
    """

    requirement_patches: List[RequirementStructuralPatch] = Field(default_factory=list)
    requirement_irs: List[RequirementIR] = Field(default_factory=list)
    evidence_annotations: List[EvidenceSemanticAnnotation] = Field(default_factory=list)
    unresolved_issue_ids: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_executable_repair_irs(self):
        material_roles = {
            SemanticClauseRole.CONDITION,
            SemanticClauseRole.TRIGGER,
            SemanticClauseRole.REQUIRED_BEHAVIOR,
            SemanticClauseRole.TIMING,
            SemanticClauseRole.PERSISTENCE,
            SemanticClauseRole.RELATIONSHIP,
            SemanticClauseRole.EXCEPTION,
        }

        def logic_ids(node: Optional[LogicExpression]) -> set[str]:
            if node is None:
                return set()
            out = {node.semantic_id} if node.semantic_id else set()
            for child in node.children:
                out.update(logic_ids(child))
            return out

        def require_executable_logic(node: Optional[LogicExpression], requirement_id: str) -> None:
            if node is None:
                return
            if node.kind == LogicKind.PREDICATE:
                if not node.signal.strip():
                    raise ValueError(
                        f"Arbitration repair IR {requirement_id} contains PREDICATE without signal"
                    )
                if node.operator == PredicateOperator.OTHER:
                    raise ValueError(
                        f"Arbitration repair IR {requirement_id} contains PREDICATE without executable operator"
                    )
                if node.children:
                    raise ValueError(
                        f"Arbitration repair IR {requirement_id} contains PREDICATE with children"
                    )
            elif node.kind == LogicKind.NOT:
                if len(node.children) != 1:
                    raise ValueError(
                        f"Arbitration repair IR {requirement_id} contains NOT without exactly one child"
                    )
            elif node.kind in {LogicKind.AND, LogicKind.OR}:
                if len(node.children) < 2:
                    raise ValueError(
                        f"Arbitration repair IR {requirement_id} contains {node.kind.value} with fewer than two children"
                    )
            elif node.kind == LogicKind.TRUE and node.children:
                raise ValueError(
                    f"Arbitration repair IR {requirement_id} contains TRUE with children"
                )
            for child in node.children:
                require_executable_logic(child, requirement_id)

        for ir in self.requirement_irs:
            require_executable_logic(ir.condition, ir.requirement_id)
            if ir.normative_type == NormativeType.AMBIGUOUS:
                raise ValueError(
                    f"Arbitration repair IR {ir.requirement_id} may not remain AMBIGUOUS; "
                    "leave it unresolved instead."
                )
            if any(c.resolution != SemanticResolution.VERIFIED for c in ir.source_clauses):
                raise ValueError(
                    f"Arbitration repair IR {ir.requirement_id} contains non-VERIFIED source clauses; "
                    "leave genuinely unresolved issues in unresolved_issue_ids instead."
                )
            if ir.normative_type in {NormativeType.MANDATORY, NormativeType.PROHIBITIVE} and ir.required_behavior is None:
                raise ValueError(f"Arbitration repair IR {ir.requirement_id} requires required_behavior")

            represented = logic_ids(ir.condition)
            for item in (ir.trigger, ir.required_behavior, ir.timing, ir.persistence):
                if item is not None and item.semantic_id:
                    represented.add(item.semantic_id)
            represented.update(r.semantic_id for r in ir.relationships if r.semantic_id)

            for clause in ir.source_clauses:
                if clause.role in material_roles and clause.semantic_id not in represented:
                    raise ValueError(
                        f"Arbitration repair IR {ir.requirement_id} does not represent material clause "
                        f"{clause.semantic_id} in executable IR fields"
                    )

        # Evidence objects returned by arbitration are also replacement repairs.
        # A partially-resolved annotation belongs in unresolved_issue_ids instead
        # of masquerading as an executable repair.
        for ann in self.evidence_annotations:
            if ann.resolution != SemanticResolution.VERIFIED:
                raise ValueError(
                    f"Arbitration evidence repair {ann.evidence_id} remains {ann.resolution.value}; "
                    "leave the blocking issue unresolved instead."
                )
            if not ann.facts:
                raise ValueError(
                    f"Arbitration evidence repair {ann.evidence_id} contains no executable facts; "
                    "leave the blocking issue unresolved instead."
                )
            for fact in ann.facts:
                if fact.resolution != SemanticResolution.VERIFIED:
                    raise ValueError(
                        f"Arbitration evidence repair {ann.evidence_id}/{fact.fact_id} is not VERIFIED"
                    )
                material_roles = {
                    EvidenceSemanticRole.APPLICABILITY,
                    EvidenceSemanticRole.TRIGGER,
                    EvidenceSemanticRole.RESPONSE,
                    EvidenceSemanticRole.TIMING,
                }
                material_to_compliance = bool(fact.related_requirement_ids) or bool(set(fact.possible_roles) & material_roles)
                if material_to_compliance:
                    if fact.temporal_semantics == TemporalSemantics.OTHER:
                        raise ValueError(
                            f"Arbitration evidence repair {ann.evidence_id}/{fact.fact_id} is linked to compliance "
                            "but leaves temporal_semantics=OTHER"
                        )
                    if not fact.subject.strip():
                        raise ValueError(
                            f"Arbitration evidence repair {ann.evidence_id}/{fact.fact_id} is linked to compliance "
                            "but has no structured subject"
                        )
                    if fact.temporal_semantics in {TemporalSemantics.POINT_STATE, TemporalSemantics.PERSISTENT_STATE}:
                        if fact.operator == PredicateOperator.OTHER:
                            raise ValueError(
                                f"Arbitration evidence repair {ann.evidence_id}/{fact.fact_id} is a state fact "
                                "without an executable operator"
                            )
                        if fact.operator not in {PredicateOperator.PRESENT, PredicateOperator.ABSENT} and not fact.value.strip() and fact.numeric_value is None:
                            raise ValueError(
                                f"Arbitration evidence repair {ann.evidence_id}/{fact.fact_id} is a state fact "
                                "without a structured value"
                            )
                if fact.temporal_semantics == TemporalSemantics.PERSISTENT_STATE:
                    if fact.scope.resolution != ScopeResolution.RESOLVED or not fact.scope.scope_id.strip():
                        raise ValueError(
                            f"Arbitration evidence repair {ann.evidence_id}/{fact.fact_id} has persistent-state "
                            "semantics without a concrete resolved scope_id"
                        )
        return self


class RCARouteDecision(StrictModel):
    run_rca: bool
    reasons: List[str] = Field(default_factory=list)
    supporting_evidence_ids: List[str] = Field(default_factory=list)


class RCAEvidencePacket(StrictModel):
    ticket_id: str = ""
    affected_functionality: str = ""
    requirement_results: List[dict] = Field(default_factory=list)
    requirement_irs: List[RequirementIR] = Field(default_factory=list)
    verified_evidence: List[dict] = Field(default_factory=list)
    deterministic_facts: List[dict] = Field(default_factory=list)
    diagnostics: List[dict] = Field(default_factory=list)
    historical: List[dict] = Field(default_factory=list)
    unresolved_requirement_context: List[dict] = Field(default_factory=list)
    unresolved_rca_context: List[dict] = Field(default_factory=list)
    selected_source_excerpts: List[dict] = Field(default_factory=list)


class CanonicalCase(StrictModel):
    """Deterministically extracted source boundaries supplied to the LLM.

    These fields are authoritative. The LLM is not allowed to reclassify source
    categories or rewrite requirement text.
    """

    ticket_id: str = ""
    title: str = ""
    description: str = ""
    evidence_inventory: List[EvidenceItem] = Field(default_factory=list)
    requirements: List[RequirementSource] = Field(default_factory=list)
    historical_text: str = ""
    diagnostics_text: str = ""
    source_availability: Dict[str, SourceAvailability] = Field(default_factory=dict)
    source_availability_raw: Dict[str, str] = Field(default_factory=dict)
    user_instructions: List[str] = Field(default_factory=list)
    atomic_claims: List[CanonicalAtomicClaim] = Field(default_factory=list)
    requirement_language: List[RequirementLanguageNormalization] = Field(default_factory=list)
    requirement_irs: List[RequirementIR] = Field(default_factory=list)
    evidence_annotations: List[EvidenceSemanticAnnotation] = Field(default_factory=list)
    semantic_integrity_issues: List[SemanticIntegrityIssue] = Field(default_factory=list)
    parser_notes: List[str] = Field(default_factory=list)


class EvidenceNeed(StrictModel):
    element: RequirementElementType
    description: str


class RequirementAnalysis(StrictModel):
    requirement_id: str
    requirement_text: str
    faithful_meaning: str
    relevance: str
    normative_type: NormativeType
    applicability: Applicability
    applicability_evidence_ids: List[str] = Field(description="Explicit current-case evidence IDs supporting the applicability decision; required even when the list is empty")
    applicability_condition: str = ""
    trigger: str = ""
    required_behavior: str = ""
    timing_constraint: str = ""
    observation_interval_requirement: str = ""
    explicit_relationships: List[str] = Field(default_factory=list)
    evaluation_evidence_ids: List[str] = Field(default_factory=list)
    evaluation_sufficiency: Sufficiency = Sufficiency.INSUFFICIENT
    missing_applicability_evidence: List[EvidenceNeed] = Field(default_factory=list)
    missing_evaluation_evidence: List[EvidenceNeed] = Field(default_factory=list)


class HistoricalTicketAnalysis(StrictModel):
    ticket_id: str
    summary: str
    similarities: List[str] = Field(default_factory=list)
    differences: List[str] = Field(default_factory=list)


class HypothesisAnalysis(StrictModel):
    hypothesis: str
    support_basis: HypothesisSupportBasis
    supporting_evidence_ids: List[str]
    weakening_evidence_ids: List[str] = Field(default_factory=list)
    source_references: List[str] = Field(default_factory=list)
    confidence: str = Field(description="LOW, MEDIUM, or HIGH")


class CaseValidityNeed(StrictModel):
    ticket_assertion: str
    evidence_needed: str


class EvidenceConflict(StrictModel):
    """Deterministically identified disagreement between supplied evidence sources."""

    description: str
    reported_evidence_ids: List[str] = Field(default_factory=list)
    direct_evidence_ids: List[str] = Field(default_factory=list)
    resolution: str = ""


class RequirementReasoningPhase(StrictModel):
    """27B Phase A: requirement-centric reasoning only.

    Case-level RCA synthesis, historical comparison, diagnostics and hypotheses
    are intentionally excluded and happen only after deterministic compliance
    validation has established the authoritative requirement state.
    """

    requirements: List[RequirementAnalysis]


class RCASynthesisReasoning(StrictModel):
    """27B Phase B: case-level RCA synthesis over authoritative compliance facts."""

    affected_functionality: str
    historical_tickets: List[HistoricalTicketAnalysis] = Field(default_factory=list)
    diagnostic_evidence_ids: List[str] = Field(default_factory=list)
    hypotheses: List[HypothesisAnalysis] = Field(default_factory=list)
    case_validity_needs: List[CaseValidityNeed] = Field(default_factory=list)


class SemanticReasoning(StrictModel):
    """LLM-owned semantic fields only.

    Evidence inventory and requirement source text are deliberately excluded;
    those are supplied by CanonicalCase and merged deterministically.
    """

    affected_functionality: str
    requirements: List[RequirementAnalysis]
    historical_tickets: List[HistoricalTicketAnalysis] = Field(default_factory=list)
    diagnostic_evidence_ids: List[str] = Field(default_factory=list)
    hypotheses: List[HypothesisAnalysis] = Field(default_factory=list)
    case_validity_needs: List[CaseValidityNeed] = Field(default_factory=list)


class SemanticAnalysis(StrictModel):
    affected_functionality: str
    evidence_inventory: List[EvidenceItem]
    requirements: List[RequirementAnalysis]
    historical_tickets: List[HistoricalTicketAnalysis] = Field(default_factory=list)
    diagnostic_evidence_ids: List[str] = Field(default_factory=list)
    hypotheses: List[HypothesisAnalysis] = Field(default_factory=list)
    case_validity_needs: List[CaseValidityNeed] = Field(default_factory=list)


class RepairRoute(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    FAST_MODEL = "FAST_MODEL"
    PRIMARY_MODEL = "PRIMARY_MODEL"


class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ValidationIssue(StrictModel):
    code: str
    severity: ValidationSeverity
    path: str
    message: str


class TimingOutcome(str, Enum):
    WITHIN_LIMIT = "WITHIN_LIMIT"
    EXCEEDS_LIMIT = "EXCEEDS_LIMIT"


class TimingFact(StrictModel):
    trigger_evidence_id: str
    response_evidence_id: str
    trigger_timestamp_seconds: float
    response_timestamp_seconds: float
    elapsed_ms: float
    limit_ms: float
    margin_ms: float
    outcome: TimingOutcome
    clock_id: str = ""
    complete_event_coverage: bool = False


class RequirementResult(StrictModel):
    analysis: RequirementAnalysis
    evaluation_status: EvaluationStatus
    evidence_ids: List[str] = Field(default_factory=list)
    timing_fact: Optional[TimingFact] = None


class ValidatedAnalysis(StrictModel):
    semantic: SemanticAnalysis
    requirement_results: List[RequirementResult]
    issues: List[ValidationIssue] = Field(default_factory=list)
    compliance_evidence: List[str] = Field(default_factory=list)
    case_validity_evidence: List[CaseValidityNeed] = Field(default_factory=list)
    hypotheses: List[HypothesisAnalysis] = Field(default_factory=list)
    evidence_conflicts: List[EvidenceConflict] = Field(default_factory=list)


class ApiStats(StrictModel):
    elapsed_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    # Some OpenAI-compatible providers (notably llama.cpp with Qwen-family
    # templates) expose reasoning_content while omitting reasoning token detail.
    # Preserve that observable fact instead of misleadingly reporting only 0.
    reasoning_content_present: bool = False
    reasoning_content_chars: int = 0
    thinking_requested: str = "provider_default"
    retries: int = 0
    endpoint: str = ""
    model: str = ""




class RequirementRepairResponse(StrictModel):
    """Legacy targeted repair payload containing complete requirement objects."""

    requirements: List[RequirementAnalysis] = Field(default_factory=list)


class RequirementPatchFields(StrictModel):
    """Field-level repair payload.

    Every field is optional so the model can return only the exact field(s)
    allowlisted by the deterministic repair router. The harness inspects
    ``model_fields_set`` and rejects any patch field that was not explicitly
    authorized for the current validation issue. Requirement ID/text are
    intentionally not patchable.
    """

    faithful_meaning: Optional[str] = None
    relevance: Optional[str] = None
    normative_type: Optional[NormativeType] = None
    applicability: Optional[Applicability] = None
    applicability_evidence_ids: Optional[List[str]] = None
    applicability_condition: Optional[str] = None
    trigger: Optional[str] = None
    required_behavior: Optional[str] = None
    timing_constraint: Optional[str] = None
    observation_interval_requirement: Optional[str] = None
    explicit_relationships: Optional[List[str]] = None
    evaluation_evidence_ids: Optional[List[str]] = None
    evaluation_sufficiency: Optional[Sufficiency] = None
    missing_applicability_evidence: Optional[List[EvidenceNeed]] = None
    missing_evaluation_evidence: Optional[List[EvidenceNeed]] = None


class RequirementPatch(StrictModel):
    requirement_id: str
    patch: RequirementPatchFields


class RequirementPatchResponse(StrictModel):
    """Narrow fast-repair contract: only explicit field patches."""

    patches: List[RequirementPatch] = Field(default_factory=list)


class LinguisticReviewFinding(StrictModel):
    code: str
    requirement_id: str = ""
    field: str
    message: str


class RelevanceWordingPatch(StrictModel):
    requirement_id: str
    relevance: str


class ReviewEvidenceRelevance(str, Enum):
    RELEVANT = "RELEVANT"
    NOT_RELEVANT = "NOT_RELEVANT"
    UNDETERMINED = "UNDETERMINED"


class ReviewEvidenceSufficiency(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNDETERMINED = "UNDETERMINED"


class ReviewVerdictConsistency(str, Enum):
    CONSISTENT = "CONSISTENT"
    INCONSISTENT = "INCONSISTENT"
    UNDETERMINED = "UNDETERMINED"


class ReviewClaimedEvaluationStatus(str, Enum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    NO_COMPLIANCE_VERDICT = "NO_COMPLIANCE_VERDICT"
    NOT_STATED = "NOT_STATED"
    UNDETERMINED = "UNDETERMINED"


class RequirementLinguisticReview(StrictModel):
    """Structured per-requirement linguistic consistency classification.

    The reviewer must separate relevance from sufficiency before it can flag a
    wording defect. This prevents the TC5 false-positive pattern where
    RELEVANT + INSUFFICIENT was incorrectly treated as a contradiction.
    """

    requirement_id: str
    evidence_relevance: ReviewEvidenceRelevance
    evidence_sufficiency: ReviewEvidenceSufficiency
    claimed_evaluation_status: ReviewClaimedEvaluationStatus = ReviewClaimedEvaluationStatus.NOT_STATED
    verdict_consistency: ReviewVerdictConsistency
    wording_issue: bool = False
    issue_message: str = ""
    replacement_relevance: str = ""


class HypothesisEpistemicReview(StrictModel):
    hypothesis_index: int
    semantic_type: HypothesisSemanticType
    epistemic_strength: EpistemicStrength
    support_sufficiency: ReviewEvidenceSufficiency
    action: HypothesisReviewAction
    issue_message: str = ""
    replacement_hypothesis: str = ""


class HypothesisReviewResponse(StrictModel):
    reviews: List[HypothesisEpistemicReview] = Field(default_factory=list)


class LinguisticReviewResponse(StrictModel):
    """Non-authoritative 4B consistency review.

    v0.6.4 uses structured per-requirement classifications. The legacy
    findings/relevance_patches fields remain accepted for session/test
    compatibility, but new live calls are instructed to use requirement_reviews.
    Python revalidates every accepted wording patch and remains the final gate.
    """

    requirement_reviews: List[RequirementLinguisticReview] = Field(default_factory=list)
    findings: List[LinguisticReviewFinding] = Field(default_factory=list)
    relevance_patches: List[RelevanceWordingPatch] = Field(default_factory=list)


class StructuredOutputAttempt(StrictModel):
    """One transport-level structured-output attempt inside a bounded LLM call.

    A single pipeline call may contain one recovery retry. Keeping each transport
    attempt separately preserves the original response, reasoning, finish reason,
    usage/timing and retry reason instead of only the final recovered response.
    """

    attempt_index: int
    raw_llm_json: str = ""
    raw_api_response: str = ""
    reasoning_content: str = ""
    finish_reason: str = ""
    stats: ApiStats = Field(default_factory=ApiStats)
    error: str = ""
    retry_reason: str = ""


class PipelineAttempt(StrictModel):
    """Persisted audit record for every LLM call, including failed structured-output calls."""

    call_index: int
    stage: str
    model_role: str = ""
    raw_llm_json: str = ""
    reasoning_content: str = ""
    semantic_before_validation_json: str = ""
    normalized_semantic_json: str = ""
    validation_issues: List[ValidationIssue] = Field(default_factory=list)
    stats: ApiStats
    finish_reason: str = ""
    transport: str = ""
    retry_diagnostics: List[str] = Field(default_factory=list)
    structured_attempts: List[StructuredOutputAttempt] = Field(default_factory=list)

class RepairEvent(StrictModel):
    pass_index: int
    route: RepairRoute
    issue_codes: List[str] = Field(default_factory=list)
    requirement_ids: List[str] = Field(default_factory=list)
    model: str = ""
    elapsed_seconds: float = 0.0
    outcome: str = ""
    details: str = ""


class PipelineResult(StrictModel):
    canonical_case: CanonicalCase
    intake_normalization: Optional[IntakeNormalization] = None
    source_availability_normalization: Optional[SourceAvailabilityNormalization] = None
    content_classification: Optional[IntakeContentClassification] = None
    atomic_claim_extraction: Optional[AtomicClaimExtractionSet] = None
    requirement_language_normalization: Optional[RequirementLanguageNormalizationSet] = None
    semantic_preparation: Optional[SemanticPreparation] = None
    semantic_arbitration: Optional[SemanticArbitrationResponse] = None
    rca_route_decision: Optional[RCARouteDecision] = None
    rca_evidence_packet: Optional[RCAEvidencePacket] = None
    rca_synthesis: Optional[RCASynthesisReasoning] = None
    hypothesis_epistemic_review: Optional[HypothesisReviewResponse] = None
    final_linguistic_review: Optional[LinguisticReviewResponse] = None
    validated: ValidatedAnalysis
    final_report: str
    raw_semantic_json: str
    raw_llm_json: str = ""
    raw_requirement_reasoning_json: str = ""
    raw_rca_synthesis_json: str = ""
    stats: List[ApiStats] = Field(default_factory=list)
    repair_performed: bool = False
    attempts: List[PipelineAttempt] = Field(default_factory=list)
    repair_log: List[RepairEvent] = Field(default_factory=list)


LogicExpression.model_rebuild()
