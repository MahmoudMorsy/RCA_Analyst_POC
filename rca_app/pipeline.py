from __future__ import annotations

import copy
import json
import re
import time
from typing import Callable, Optional

from .cancellation import CancellationToken
from .case_parser import DeterministicCaseParser
from .formatter import FinalReportFormatter
from .intake import IntakeCanonicalizer, IntakeRouter
from .model_protocol import ModelClient, ModelGatewayError

# Legacy injection hook retained for frozen pre-v1 unit adapters. Production
# clients use the provider-neutral ModelClient.clone() contract.
LMStudioClient = None
from .models import (
    AtomicClaimExtractionSet,
    CanonicalCase,
    HypothesisReviewResponse,
    IntakeContentClassification,
    IntakeNormalization,
    LinguisticReviewResponse,
    PipelineAttempt,
    PipelineResult,
    RepairEvent,
    RepairRoute,
    RCASynthesisReasoning,
    RequirementLanguageNormalizationSet,
    RequirementPatchResponse,
    RequirementReasoningPhase,
    RequirementRepairResponse,
    SemanticAnalysis,
    SemanticReasoning,
    SourceAvailabilityNormalization,
    SemanticPreparation,
    RequirementCompilationBatch,
    RequirementStructuralPatchBatch,
    EvidenceAnnotationBatch,
    RequirementSemanticVerificationBatch,
    SemanticIntegrityIssue,
    SemanticResolution,
    SemanticArbitrationResponse,
    RCARouteDecision,
    RCAEvidencePacket,
    ValidatedAnalysis,
    ValidationIssue,
    ValidationSeverity,
)
from . import RCA_CORE_VERSION
from .prompts import (
    FAST_ATOMIC_CLAIM_PROMPT,
    FAST_CONTENT_CLASSIFIER_PROMPT,
    FAST_FINAL_REVIEW_PROMPT,
    FAST_HYPOTHESIS_REVIEW_PROMPT,
    FAST_INTAKE_NORMALIZER_PROMPT,
    FAST_PATCH_REPAIR_PROMPT,
    FAST_REQUIREMENT_LANGUAGE_PROMPT,
    FAST_SOURCE_AVAILABILITY_PROMPT,
    RCA_SYNTHESIS_PROMPT,
    REPAIR_PROMPT,
    REQUIREMENT_REASONING_PROMPT,
    SEMANTIC_ANALYZER_PROMPT,
    TARGETED_REQUIREMENT_REPAIR_PROMPT,
    REQUIREMENT_COMPILATION_V086_PROMPT,
    REQUIREMENT_STRUCTURAL_COMPLETION_V086_PROMPT,
    EVIDENCE_ANNOTATION_V086_PROMPT,
    REQUIREMENT_SEMANTIC_VERIFICATION_PROMPT,
    SEMANTIC_ARBITRATION_PROMPT,
    RCA_SYNTHESIS_V080_PROMPT,
)
from .hypothesis_review import HypothesisEpistemicGate
from .repair import DeterministicRepairEngine, RepairRouter, RepairTask
from .review import LinguisticReviewGate
from .semantic_preprocessing import FastSemanticPreprocessor
from .validator import DeterministicValidator
from .semantic_ir import SemanticIntegrityChecker, SemanticArbitrationMerger
from .compliance_engine import DeterministicComplianceEngine
from .rca_routing import RCARouter, RCAEvidencePacketBuilder


ProgressCallback = Callable[[str, str], None]
TraceCallback = Callable[[dict], None]
MAX_REPAIR_ACTIONS_PER_ROUND = 12


class PipelineValidationError(RuntimeError):
    def __init__(self, message: str, validated=None, canonical_case=None, attempts=None, stats=None, repair_log=None):
        super().__init__(message)
        self.validated = validated
        self.canonical_case = canonical_case
        self.attempts = attempts or []
        self.stats = stats or []
        self.repair_log = repair_log or []


class RCAPipeline:
    """v0.8.8 adaptive semantic-compiler RCA architecture.

    Production v0.8 performs bounded semantic preparation that compiles
    free-form requirements into Requirement IR and annotates language-derived
    evidence. Python executes only verified IR/facts and owns compliance truth.
    The 27B is conditional: one batched semantic-arbitration call when material
    ambiguity blocks compliance, and one RCA synthesis call only when actual
    mechanism-oriented evidence justifies it.

    A compatibility-only v0.7.1 execution path is retained for old unit-test/API
    adapters that do not opt into semantic preparation.
    """

    def __init__(
        self,
        client: ModelClient,
        max_repair_passes: int = 1,
        repair_client: Optional[ModelClient] = None,
        intake_client: Optional[ModelClient] = None,
        final_review_client: Optional[ModelClient] = None,
        source_availability_client: Optional[ModelClient] = None,
        content_classification_client: Optional[ModelClient] = None,
        atomic_claim_client: Optional[ModelClient] = None,
        requirement_language_client: Optional[ModelClient] = None,
        hypothesis_review_client: Optional[ModelClient] = None,
        deterministic_repair_enabled: bool = True,
        fallback_to_primary_repair: bool = True,
        fast_intake_enabled: bool = False,
        fast_intake_mode: str = "auto",
        fast_atomic_claim_enabled: bool = False,
        fast_requirement_language_enabled: bool = False,
        fast_hypothesis_review_enabled: bool = False,
        fast_final_review_enabled: bool = False,
        primary_large_case_max_tokens: int = 16000,
        primary_large_case_requirement_threshold: int = 8,
        primary_phase_a_chunk_size: int = 6,
        semantic_preparation_client: Optional[ModelClient] = None,
        semantic_preparation_enabled: bool = False,
        semantic_verification_client: Optional[ModelClient] = None,
        semantic_arbitration_client: Optional[ModelClient] = None,
        semantic_arbitration_enabled: bool = True,
        rca_synthesis_enabled: bool = True,
        cancellation_token: Optional[CancellationToken] = None,
    ):
        self.client = client
        self.repair_client = repair_client
        self.intake_client = intake_client or repair_client
        self.final_review_client = final_review_client or repair_client
        self.source_availability_client = source_availability_client or self.intake_client
        self.content_classification_client = content_classification_client or self.intake_client
        self.atomic_claim_client = atomic_claim_client or self.intake_client
        self.requirement_language_client = requirement_language_client or self.intake_client
        self.hypothesis_review_client = hypothesis_review_client or self.final_review_client or self.intake_client
        self.semantic_preparation_client = semantic_preparation_client
        self.semantic_preparation_enabled = bool(semantic_preparation_enabled and semantic_preparation_client is not None)
        self.semantic_verification_client = semantic_verification_client or semantic_preparation_client
        self.semantic_arbitration_client = semantic_arbitration_client or client
        self.semantic_arbitration_enabled = bool(semantic_arbitration_enabled)
        self.rca_synthesis_enabled = bool(rca_synthesis_enabled)
        self.max_repair_passes = max(0, max_repair_passes)
        self.deterministic_repair_enabled = deterministic_repair_enabled
        self.fallback_to_primary_repair = fallback_to_primary_repair
        self.fast_intake_enabled = fast_intake_enabled
        self.fast_intake_mode = fast_intake_mode
        self.fast_atomic_claim_enabled = fast_atomic_claim_enabled
        self.fast_requirement_language_enabled = fast_requirement_language_enabled
        self.fast_hypothesis_review_enabled = fast_hypothesis_review_enabled
        self.fast_final_review_enabled = fast_final_review_enabled
        self.primary_large_case_max_tokens = max(1024, int(primary_large_case_max_tokens))
        self.primary_large_case_requirement_threshold = max(1, int(primary_large_case_requirement_threshold))
        self.primary_phase_a_chunk_size = max(1, int(primary_phase_a_chunk_size))
        self.cancellation_token = cancellation_token
        self.parser = DeterministicCaseParser(language_interval_parsing_enabled=not self.semantic_preparation_enabled)
        self.intake_router = IntakeRouter(self.parser)
        self.intake_canonicalizer = IntakeCanonicalizer(self.parser)
        self.fast_semantic_preprocessor = FastSemanticPreprocessor()
        self.linguistic_review_gate = LinguisticReviewGate()
        self.hypothesis_review_gate = HypothesisEpistemicGate()
        self.validator = DeterministicValidator()
        self.formatter = FinalReportFormatter()
        self.repair_engine = DeterministicRepairEngine()
        self.repair_router = RepairRouter()
        self.semantic_integrity_checker = SemanticIntegrityChecker()
        self.semantic_arbitration_merger = SemanticArbitrationMerger()
        self.compliance_engine = DeterministicComplianceEngine()
        self.rca_router = RCARouter()
        self.rca_packet_builder = RCAEvidencePacketBuilder()

    def _check_cancelled(self, stage: str) -> None:
        if self.cancellation_token is not None:
            self.cancellation_token.throw_if_cancelled(stage)

    def _build_nonthinking_final_review_fallback(self, exc: ModelGatewayError) -> Optional[ModelClient]:
        """Create a bounded non-thinking recovery client for failed Qwen3.5 chat review.

        v0.6.4 showed that Low-thinking Qwen3.5 can spend the complete output
        budget in reasoning and return empty assistant content. The final review
        is optional and narrow, so when an OpenAI-chat structured-output failure
        occurs we recover once through the proven manual non-thinking path.
        Network/request failures are not retried through another transport.
        """
        client = self.final_review_client
        if client is None or "qwen3.5" not in (getattr(client, "model", "") or "").lower():
            return None
        if getattr(exc, "transport", "") != "openai-chat":
            return None
        text = str(exc).lower()
        if "invalid structured response" not in text and "assistant content is empty" not in text:
            return None
        if client.resolve_transport() == "qwen35-manual":
            return None
        clone = getattr(client, "clone", None)
        if callable(clone):
            return clone(
                reasoning_effort="provider_default",
                thinking_mode="off",
                transport="qwen35-manual",
                cancellation_token=self.cancellation_token,
            )
        # Compatibility only for frozen adapters that predate ModelClient.clone.
        factory = globals().get("LMStudioClient")
        if callable(factory):
            return factory(
                base_url=client.base_url,
                model=client.model,
                temperature=client.temperature,
                reasoning_effort="provider_default",
                max_tokens=client.max_tokens,
                timeout_seconds=client.timeout_seconds,
                api_token=client.api_token,
                thinking_mode="off",
                transport="qwen35-manual",
                cancellation_token=self.cancellation_token,
            )
        return None

    def cancel(self, reason: str = "Stopped by user.") -> None:
        """Request cooperative cancellation and close any active model stream."""
        if self.cancellation_token is not None:
            self.cancellation_token.cancel(reason)
        seen = set()
        for client in (
            self.client, self.intake_client, self.repair_client, self.final_review_client,
            self.source_availability_client, self.content_classification_client,
            self.atomic_claim_client, self.requirement_language_client, self.hypothesis_review_client,
            self.semantic_preparation_client, self.semantic_arbitration_client,
        ):
            if client is None or id(client) in seen:
                continue
            seen.add(id(client))
            cancel_request = getattr(client, "cancel_active_request", None)
            if callable(cancel_request):
                cancel_request()

    def run(
        self,
        raw_case: str,
        progress: Optional[ProgressCallback] = None,
        trace: Optional[TraceCallback] = None,
    ) -> PipelineResult:
        """Run the v0.8 architecture when semantic preparation is configured.

        The legacy branch exists only for frozen adapters/tests. GUI/CLI v0.8
        always configure ``semantic_preparation_client``.
        """
        if self.semantic_preparation_enabled:
            return self._run_v080(raw_case, progress=progress, trace=trace)
        return self._run_v071_legacy(raw_case, progress=progress, trace=trace)

    def _run_v080(
        self,
        raw_case: str,
        progress: Optional[ProgressCallback] = None,
        trace: Optional[TraceCallback] = None,
    ) -> PipelineResult:
        if not raw_case.strip():
            raise ValueError("Test case is empty.")
        self._check_cancelled("startup")
        progress = progress or (lambda stage, detail: None)
        trace = trace or (lambda event: None)
        stats = []
        attempts: list[PipelineAttempt] = []
        repair_log: list[RepairEvent] = []
        intake_normalization = None
        source_availability_normalization = None
        content_classification = None
        semantic_preparation = None
        semantic_arbitration = None
        rca_route_decision = None
        rca_evidence_packet = None
        rca_synthesis = None
        hypothesis_epistemic_review = None
        final_linguistic_review = None
        raw_llm_json = ""
        raw_requirement_reasoning_json = ""
        raw_rca_synthesis_json = ""

        self._emit_trace(trace, "01_user_input", "User Input", "complete",
                         "Raw case received and retained as immutable provenance.",
                         input_value=raw_case, output_value="Input captured.")

        # 02-05: structural routing/canonicalization. Fast source/content calls
        # happen only for genuinely free-form input.
        progress("Input routing", "Checking whether structural section normalization is required...")
        fast_intake_available = self.source_availability_client is not None and self.content_classification_client is not None
        decision = self.intake_router.decide(
            raw_case,
            mode=self.fast_intake_mode if self.fast_intake_enabled else "off",
            fast_available=fast_intake_available,
        )
        canonical = decision.deterministic_preview
        self._emit_trace(trace, "02_intake_routing", "Input Classification", "complete", decision.reason,
                         input_value=raw_case,
                         output_value={"route": "4B_SECTIONING" if decision.use_fast_model else "PYTHON_STRUCTURAL", "reason": decision.reason})

        if decision.use_fast_model:
            self._check_cancelled("4B source availability")
            availability_prompt = self._source_availability_user_prompt(raw_case)
            self._emit_trace(trace, "03_source_availability", "4B Source Availability", "running",
                             "Language interpretation is used only because the source structure is not reliable.",
                             input_value={"system_prompt": FAST_SOURCE_AVAILABILITY_PROMPT, "user_prompt": availability_prompt})
            try:
                response = self.source_availability_client.structured_repair(
                    system_prompt=FAST_SOURCE_AVAILABILITY_PROMPT,
                    user_prompt=availability_prompt,
                    response_model=SourceAvailabilityNormalization,
                    schema_name="rca_fast_source_availability_v080",
                )
                stats.append(response.stats)
                attempts.append(self._make_aux_attempt(len(attempts)+1, "fast_source_availability", "FAST_SOURCE_AVAILABILITY", response))
                source_availability_normalization = response.parsed
                self._emit_trace(trace, "03_source_availability", "4B Source Availability", "complete",
                                 "Source availability was semantically classified.", output_value=response.parsed)
            except (ModelGatewayError, ValueError) as exc:
                if isinstance(exc, ModelGatewayError):
                    stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts)+1, "fast_source_availability", "FAST_SOURCE_AVAILABILITY", exc))
                if not canonical.requirements:
                    raise PipelineValidationError("Source-availability classification failed and deterministic parsing found no requirements.", canonical_case=canonical, attempts=attempts, stats=stats) from exc

            if source_availability_normalization is not None:
                self._check_cancelled("4B content classification")
                content_prompt = self._content_classification_user_prompt(raw_case, source_availability_normalization)
                self._emit_trace(trace, "04_content_classification", "4B Content Classification", "running",
                                 "Free-form source blocks are classified; known structured templates skip this call.",
                                 input_value={"system_prompt": FAST_CONTENT_CLASSIFIER_PROMPT, "user_prompt": content_prompt})
                try:
                    response = self.content_classification_client.structured_repair(
                        system_prompt=FAST_CONTENT_CLASSIFIER_PROMPT,
                        user_prompt=content_prompt,
                        response_model=IntakeContentClassification,
                        schema_name="rca_fast_content_classification_v080",
                    )
                    stats.append(response.stats)
                    attempts.append(self._make_aux_attempt(len(attempts)+1, "fast_content_classification", "FAST_CONTENT_CLASSIFIER", response))
                    content_classification = response.parsed
                    intake_normalization = self.fast_semantic_preprocessor.combine_intake(raw_case, source_availability_normalization, content_classification)
                    canonical = self.intake_canonicalizer.build(raw_case, intake_normalization)
                    self._emit_trace(trace, "04_content_classification", "4B Content Classification", "complete",
                                     "Source-backed blocks were classified; Python rebuilt canonical provenance.", output_value=response.parsed)
                except (ModelGatewayError, ValueError) as exc:
                    if isinstance(exc, ModelGatewayError):
                        stats.append(exc.stats)
                        attempts.append(self._make_failed_attempt(len(attempts)+1, "fast_content_classification", "FAST_CONTENT_CLASSIFIER", exc))
                    if not canonical.requirements:
                        raise PipelineValidationError("Content classification failed and deterministic parsing found no requirements.", canonical_case=canonical, attempts=attempts, stats=stats) from exc
        else:
            self._emit_trace(trace, "03_source_availability", "4B Source Availability", "skipped",
                             "Structured input does not require a language call for source availability.", output_value="Skipped.")
            self._emit_trace(trace, "04_content_classification", "4B Content Classification", "skipped",
                             "Structured input does not require a language call for section classification.", output_value="Skipped.")

        self._check_cancelled("canonicalization")
        if not canonical.requirements:
            raise PipelineValidationError("No authoritative requirements could be canonicalized.", canonical_case=canonical, attempts=attempts, stats=stats)
        self._emit_trace(trace, "05_canonicalization", "Python Structural Canonicalization", "complete",
                         f"Canonical case contains {len(canonical.requirements)} requirement(s) and {len(canonical.evidence_inventory)} evidence item(s).",
                         output_value=canonical)

        # 06: independent fast-model semantic components. v0.8.4 never
        # combines Requirement IR compilation and evidence annotation in one
        # response model, even for small cases. This isolates transport/schema
        # failures so one malformed evidence object cannot discard valid IRs.
        self._check_cancelled("4B requirement semantic compilation")
        requirement_batches = self._semantic_requirement_batches(canonical)
        language_evidence = self._compact_language_evidence(canonical)
        progress(
            "Semantic preparation",
            f"Compiling {len(canonical.requirements)} requirement(s) in {len(requirement_batches)} bounded batch(es)"
            + (" then annotating language evidence..." if language_evidence else "..."),
        )
        self._emit_trace(
            trace, "06_semantic_preparation", "Semantic Preparation", "running",
            "Requirement compilation and evidence annotation are isolated components; failures/retries are component-specific and no compliance decision is made.",
            input_value={
                "model_client": self._client_trace_descriptor(self.semantic_preparation_client, "semantic_preparation"),
                "verification_client": self._client_trace_descriptor(self.semantic_verification_client, "semantic_verification"),
                "requirement_batches": [[x.requirement_id for x in batch] for batch in requirement_batches],
                "language_evidence_count": len(language_evidence),
                "combined_small_case_call": False,
            },
        )

        compiled_batches: list[RequirementCompilationBatch] = []
        raw_parts: list[str] = []
        for batch_index, batch in enumerate(requirement_batches, start=1):
            self._check_cancelled(f"4B requirement compilation batch {batch_index}")
            batch_prompt = self._semantic_requirement_batch_prompt(canonical, batch)
            batch_stage_id = f"06_req_{batch_index:02d}"
            self._emit_trace(
                trace, batch_stage_id, f"Requirement Compilation / Batch {batch_index}", "running",
                f"Compiling {len(batch)} requirement(s) into executable Requirement IR.",
                input_value={
                    "model_client": self._client_trace_descriptor(self.semantic_preparation_client, "semantic_preparation"),
                    "requirement_ids": [x.requirement_id for x in batch],
                    "request": json.loads(batch_prompt),
                },
            )
            try:
                try:
                    response = self.semantic_preparation_client.structured_repair(
                        system_prompt=REQUIREMENT_COMPILATION_V086_PROMPT,
                        user_prompt=batch_prompt,
                        response_model=RequirementCompilationBatch,
                        schema_name="rca_requirement_compilation_v086",
                    )
                except AttributeError:
                    response = self.semantic_preparation_client.structured_chat(
                        system_prompt=REQUIREMENT_COMPILATION_V086_PROMPT,
                        user_prompt=batch_prompt,
                        response_model=RequirementCompilationBatch,
                        schema_name="rca_requirement_compilation_v086",
                    )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(
                    len(attempts) + 1,
                    f"semantic_preparation_requirements_{batch_index}",
                    "SEMANTIC_REQUIREMENT_COMPILER",
                    exc,
                ))
                self._emit_trace(
                    trace, batch_stage_id, f"Requirement Compilation / Batch {batch_index}", "failed",
                    "Requirement compilation failed after bounded structured-output handling.",
                    output_value={"error": str(exc), "finish_reason": exc.finish_reason, "retry_diagnostics": exc.retry_diagnostics},
                )
                raise PipelineValidationError(
                    "Semantic requirement compilation failed; v0.8 does not fall back to raw-language Python interpretation.\n" + str(exc),
                    canonical_case=canonical, attempts=attempts, stats=stats,
                ) from exc
            stats.append(response.stats)
            attempts.append(self._make_aux_attempt(
                len(attempts) + 1,
                f"semantic_preparation_requirements_{batch_index}",
                "SEMANTIC_REQUIREMENT_COMPILER",
                response,
            ))
            raw_parts.append(response.raw_json)

            expected_ids = [x.requirement_id for x in batch]
            expected_set = set(expected_ids)
            first_rows = [x for x in response.parsed.requirement_irs if x.requirement_id in expected_set]
            first_by_id = {}
            duplicate_ids = set()
            for row in first_rows:
                if row.requirement_id in first_by_id:
                    duplicate_ids.add(row.requirement_id)
                first_by_id[row.requirement_id] = row
            missing_ids = [rid for rid in expected_ids if rid not in first_by_id or rid in duplicate_ids]
            recovery_response = None
            if missing_ids:
                missing_batch = [x for x in batch if x.requirement_id in set(missing_ids)]
                recovery_prompt = self._semantic_requirement_batch_prompt(canonical, missing_batch, missing_recovery=True)
                recovery_stage_id = f"{batch_stage_id}_recovery"
                self._emit_trace(
                    trace, recovery_stage_id, f"Requirement Compilation Recovery / Batch {batch_index}", "running",
                    f"Previous compiler output omitted/duplicated {len(missing_ids)} authoritative requirement ID(s); recompiling only those IDs.",
                    input_value={
                        "model_client": self._client_trace_descriptor(self.semantic_preparation_client, "semantic_preparation"),
                        "requirement_ids": missing_ids,
                        "request": json.loads(recovery_prompt),
                    },
                )
                try:
                    try:
                        recovery_response = self.semantic_preparation_client.structured_repair(
                            system_prompt=REQUIREMENT_COMPILATION_V086_PROMPT,
                            user_prompt=recovery_prompt,
                            response_model=RequirementCompilationBatch,
                            schema_name="rca_requirement_compilation_recovery_v087",
                        )
                    except AttributeError:
                        recovery_response = self.semantic_preparation_client.structured_chat(
                            system_prompt=REQUIREMENT_COMPILATION_V086_PROMPT,
                            user_prompt=recovery_prompt,
                            response_model=RequirementCompilationBatch,
                            schema_name="rca_requirement_compilation_recovery_v087",
                        )
                    stats.append(recovery_response.stats)
                    attempts.append(self._make_aux_attempt(
                        len(attempts) + 1,
                        f"semantic_preparation_requirements_{batch_index}_missing_recovery",
                        "SEMANTIC_REQUIREMENT_COMPILER_RECOVERY",
                        recovery_response,
                    ))
                    raw_parts.append(recovery_response.raw_json)
                    for row in recovery_response.parsed.requirement_irs:
                        if row.requirement_id in set(missing_ids):
                            first_by_id[row.requirement_id] = row
                    still_missing = [rid for rid in expected_ids if rid not in first_by_id]
                    self._emit_trace(
                        trace, recovery_stage_id, f"Requirement Compilation Recovery / Batch {batch_index}",
                        "attention" if still_missing else "complete",
                        f"Recovery completed; {len(still_missing)} authoritative requirement ID(s) remain without IR.",
                        output_value={
                            "compiled": recovery_response.parsed,
                            "still_missing_requirement_ids": still_missing,
                            "model_call": recovery_response.stats,
                            "finish_reason": recovery_response.finish_reason,
                        },
                    )
                except ModelGatewayError as exc:
                    stats.append(exc.stats)
                    attempts.append(self._make_failed_attempt(
                        len(attempts) + 1,
                        f"semantic_preparation_requirements_{batch_index}_missing_recovery",
                        "SEMANTIC_REQUIREMENT_COMPILER_RECOVERY",
                        exc,
                    ))
                    self._emit_trace(
                        trace, recovery_stage_id, f"Requirement Compilation Recovery / Batch {batch_index}", "attention",
                        "Bounded missing-ID recovery failed; missing IRs remain explicit semantic integrity issues.",
                        output_value={"error": str(exc)},
                    )

            merged_irs = [first_by_id[rid] for rid in expected_ids if rid in first_by_id]
            merged_batch = RequirementCompilationBatch(
                affected_functionality=response.parsed.affected_functionality,
                requirement_irs=merged_irs,
                unresolved_case_semantics=list(response.parsed.unresolved_case_semantics),
            )
            compiled_batches.append(merged_batch)
            self._emit_trace(
                trace, batch_stage_id, f"Requirement Compilation / Batch {batch_index}",
                "attention" if len(merged_irs) != len(expected_ids) else "complete",
                f"Compiled {len(merged_irs)}/{len(expected_ids)} authoritative Requirement IR object(s).",
                output_value={
                    "compiled": merged_batch,
                    "expected_requirement_ids": expected_ids,
                    "returned_requirement_ids": [x.requirement_id for x in merged_irs],
                    "initial_duplicate_requirement_ids": sorted(duplicate_ids),
                    "model_call": response.stats,
                    "finish_reason": response.finish_reason,
                    "transport": response.transport,
                },
            )

        # Merge requirement compilation first so Requirement IR structural
        # completion can run independently before the evidence component.
        semantic_preparation = self._merge_semantic_preparation(compiled_batches, None)
        raw_llm_json = "\n\n".join(x for x in raw_parts if x)

        # 06a: up to two bounded targeted structural-completion passes. The
        # first pass repairs executable shells and/or creates the complete
        # source-clause audit. A second pass is allowed only when that newly
        # explicit audit reveals another missing executable field (for example a
        # timing clause that the original compiler omitted entirely). Python
        # still identifies only structured target fields and never interprets
        # requirement language itself.
        structural_issues = self.semantic_integrity_checker.structural_requirement_issues(semantic_preparation)
        structural_pass_ran = False
        for structural_pass in (1, 2):
            if not structural_issues:
                break
            targets = self._structural_completion_targets(semantic_preparation, structural_issues)
            if not targets:
                break
            structural_pass_ran = True
            repair_ids = sorted(targets)
            self._check_cancelled(f"semantic structural IR completion pass {structural_pass}")
            structural_prompt = self._semantic_structural_repair_prompt(
                canonical, semantic_preparation, structural_issues, targets
            )
            stage_id = f"06a_structural_ir_completion_{structural_pass}"
            stage_title = (
                "Semantic Structural IR Completion" if structural_pass == 1
                else "Semantic Structural IR Completion / Follow-up"
            )
            self._emit_trace(
                trace, stage_id, stage_title, "running",
                f"Completing exact executable/provenance IR fields for {len(repair_ids)} requirement(s) before semantic verification.",
                input_value={
                    "model_client": self._client_trace_descriptor(self.semantic_preparation_client, "semantic_preparation"),
                    "requirement_ids": repair_ids,
                    "target_fields": targets,
                    "issues": [x.model_dump(mode="json") for x in structural_issues],
                    "request": json.loads(structural_prompt),
                },
            )
            try:
                completion_budget = min(
                    int(getattr(self.semantic_preparation_client, "max_tokens", 3500) or 3500), 3500
                )
                try:
                    completion_client = self.semantic_preparation_client.clone(
                        max_tokens=max(1200, completion_budget)
                    )
                except AttributeError:
                    completion_client = self.semantic_preparation_client
                structural_response = completion_client.structured_repair(
                    system_prompt=REQUIREMENT_STRUCTURAL_COMPLETION_V086_PROMPT,
                    user_prompt=structural_prompt,
                    response_model=RequirementStructuralPatchBatch,
                    schema_name=f"rca_requirement_structural_patch_v088_p{structural_pass}",
                )
                stats.append(structural_response.stats)
                attempts.append(self._make_aux_attempt(
                    len(attempts) + 1,
                    f"semantic_structural_completion_{structural_pass}",
                    "SEMANTIC_STRUCTURAL_COMPLETION",
                    structural_response,
                ))
                self._validate_structural_patches(structural_response.parsed, targets)
                semantic_preparation = self._apply_structural_patches(
                    semantic_preparation, structural_response.parsed, targets
                )
                structural_issues = self.semantic_integrity_checker.structural_requirement_issues(
                    semantic_preparation
                )
                self._emit_trace(
                    trace, stage_id, stage_title,
                    "attention" if structural_issues else "complete",
                    f"Structural completion pass {structural_pass} finished; {len(structural_issues)} structured defect(s) remain.",
                    output_value={
                        "patches": structural_response.parsed,
                        "remaining_issues": [x.model_dump(mode="json") for x in structural_issues],
                        "model_call": structural_response.stats,
                        "finish_reason": structural_response.finish_reason,
                    },
                )
            except (ModelGatewayError, ValueError) as exc:
                if isinstance(exc, ModelGatewayError):
                    stats.append(exc.stats)
                    attempts.append(self._make_failed_attempt(
                        len(attempts) + 1,
                        f"semantic_structural_completion_{structural_pass}",
                        "SEMANTIC_STRUCTURAL_COMPLETION",
                        exc,
                    ))
                self._emit_trace(
                    trace, stage_id, stage_title, "attention",
                    "The bounded targeted structural completion did not yield an admissible patch; current IR is retained and the verifier/arbitration path remains authoritative.",
                    output_value={"error": str(exc)},
                )
                break
        if not structural_pass_ran:
            self._emit_trace(
                trace, "06a_structural_ir_completion", "Semantic Structural IR Completion", "skipped",
                "No structured Requirement IR defect requires targeted completion.", output_value="Skipped."
            )

        # 06b: independent evidence semantic annotation. This call is always
        # separate from Requirement IR compilation so schema failure remains
        # local to the evidence component.
        if language_evidence:
            self._check_cancelled("evidence semantic annotation")
            evidence_prompt = self._semantic_evidence_batch_prompt(canonical)
            self._emit_trace(
                trace, "06b_evidence_annotation", "Evidence Semantic Annotation", "running",
                f"Interpreting {len(language_evidence)} language evidence item(s) into structured facts.",
                input_value={
                    "model_client": self._client_trace_descriptor(self.semantic_preparation_client, "semantic_preparation"),
                    "request": json.loads(evidence_prompt),
                },
            )
            try:
                try:
                    response = self.semantic_preparation_client.structured_repair(
                        system_prompt=EVIDENCE_ANNOTATION_V086_PROMPT,
                        user_prompt=evidence_prompt,
                        response_model=EvidenceAnnotationBatch,
                        schema_name="rca_evidence_annotation_v086",
                    )
                except AttributeError:
                    response = self.semantic_preparation_client.structured_chat(
                        system_prompt=EVIDENCE_ANNOTATION_V086_PROMPT,
                        user_prompt=evidence_prompt,
                        response_model=EvidenceAnnotationBatch,
                        schema_name="rca_evidence_annotation_v086",
                    )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(
                    len(attempts) + 1, "semantic_preparation_evidence", "SEMANTIC_EVIDENCE_ANNOTATOR", exc
                ))
                self._emit_trace(
                    trace, "06b_evidence_annotation", "Evidence Semantic Annotation", "failed",
                    "Evidence annotation failed after bounded structured-output handling.",
                    output_value={"error": str(exc), "finish_reason": exc.finish_reason, "retry_diagnostics": exc.retry_diagnostics},
                )
                raise PipelineValidationError(
                    "Semantic evidence annotation failed; unresolved natural-language evidence is not converted by Python.\n" + str(exc),
                    canonical_case=canonical, attempts=attempts, stats=stats,
                ) from exc
            stats.append(response.stats)
            attempts.append(self._make_aux_attempt(
                len(attempts) + 1, "semantic_preparation_evidence", "SEMANTIC_EVIDENCE_ANNOTATOR", response
            ))
            semantic_preparation.evidence_annotations = copy.deepcopy(response.parsed.evidence_annotations)
            for note in response.parsed.unresolved_case_semantics:
                if note not in semantic_preparation.unresolved_case_semantics:
                    semantic_preparation.unresolved_case_semantics.append(note)
            raw_parts.append(response.raw_json)
            raw_llm_json = "\n\n".join(x for x in raw_parts if x)
            self._emit_trace(
                trace, "06b_evidence_annotation", "Evidence Semantic Annotation", "complete",
                f"Produced {len(response.parsed.evidence_annotations)} evidence annotation object(s).",
                output_value={
                    "annotations": response.parsed,
                    "model_call": response.stats,
                    "finish_reason": response.finish_reason,
                    "transport": response.transport,
                },
            )
        else:
            self._emit_trace(
                trace, "06b_evidence_annotation", "Evidence Semantic Annotation", "skipped",
                "No language-derived evidence requires semantic annotation.",
                output_value="Skipped.",
            )

        # 06c: component-specific evidence repair. Transport/envelope
        # normalization is handled by the Pydantic model; remaining structured
        # defects such as RESOLVED persistent scope without scope_id receive one
        # targeted cheap 4B reannotation before any 27B arbitration.
        evidence_structural_issues = self.semantic_integrity_checker.structural_evidence_issues(semantic_preparation, canonical)
        if evidence_structural_issues:
            repair_evidence_ids = sorted({x.evidence_id for x in evidence_structural_issues if x.evidence_id})
            self._check_cancelled("4B evidence semantic completion")
            evidence_repair_prompt = self._semantic_evidence_repair_prompt(
                canonical, repair_evidence_ids, evidence_structural_issues
            )
            self._emit_trace(
                trace, "06c_evidence_completion", "Evidence Semantic Completion", "running",
                f"Reannotating {len(repair_evidence_ids)} evidence item(s) with structured semantic defects; no requirement recompilation is repeated.",
                input_value={
                    "evidence_ids": repair_evidence_ids,
                    "issues": [x.model_dump(mode="json") for x in evidence_structural_issues],
                },
            )
            try:
                try:
                    evidence_completion_budget = min(int(getattr(self.semantic_preparation_client, "max_tokens", 4000) or 4000), 4000)
                    try:
                        evidence_completion_client = self.semantic_preparation_client.clone(
                            max_tokens=max(1600, evidence_completion_budget)
                        )
                    except AttributeError:
                        evidence_completion_client = self.semantic_preparation_client
                    evidence_repair_response = evidence_completion_client.structured_repair(
                        system_prompt=EVIDENCE_ANNOTATION_V086_PROMPT,
                        user_prompt=evidence_repair_prompt,
                        response_model=EvidenceAnnotationBatch,
                        schema_name="rca_evidence_structural_completion_v086",
                    )
                except AttributeError:
                    evidence_repair_response = self.semantic_preparation_client.structured_chat(
                        system_prompt=EVIDENCE_ANNOTATION_V086_PROMPT,
                        user_prompt=evidence_repair_prompt,
                        response_model=EvidenceAnnotationBatch,
                        schema_name="rca_evidence_structural_completion_v086",
                    )
                stats.append(evidence_repair_response.stats)
                attempts.append(self._make_aux_attempt(
                    len(attempts) + 1, "semantic_evidence_completion",
                    "SEMANTIC_EVIDENCE_COMPLETION", evidence_repair_response
                ))
                semantic_preparation = self._replace_evidence_annotations(
                    semantic_preparation, evidence_repair_response.parsed.evidence_annotations, repair_evidence_ids
                )
                remaining_evidence_structural = self.semantic_integrity_checker.structural_evidence_issues(semantic_preparation, canonical)
                self._emit_trace(
                    trace, "06c_evidence_completion", "Evidence Semantic Completion",
                    "attention" if remaining_evidence_structural else "complete",
                    f"Evidence completion finished; {len(remaining_evidence_structural)} structured evidence defect(s) remain for conservative integrity/arbitration handling.",
                    output_value=evidence_repair_response.parsed,
                )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(
                    len(attempts) + 1, "semantic_evidence_completion",
                    "SEMANTIC_EVIDENCE_COMPLETION", exc
                ))
                self._emit_trace(
                    trace, "06c_evidence_completion", "Evidence Semantic Completion", "attention",
                    "Targeted evidence completion failed; partial annotations are retained and Python will not promote unresolved persistence to executable interval evidence.",
                    output_value={"error": str(exc)},
                )
        else:
            self._emit_trace(
                trace, "06c_evidence_completion", "Evidence Semantic Completion", "skipped",
                "No structured evidence annotation defect requires targeted reannotation.", output_value="Skipped."
            )

        canonical.requirement_irs = copy.deepcopy(semantic_preparation.requirement_irs)
        canonical.evidence_annotations = copy.deepcopy(semantic_preparation.evidence_annotations)
        self._emit_trace(
            trace, "06_semantic_preparation", "Semantic Preparation", "complete",
            f"Compiled {len(semantic_preparation.requirement_irs)} Requirement IR(s) across {len(requirement_batches)} bounded batch(es); "
            f"evidence annotation ran as a separate component and retained {len(semantic_preparation.evidence_annotations)} annotation object(s).",
            output_value=semantic_preparation,
        )

        # 06d: independent language-level semantic verification. This is a
        # compact fast-model audit, not a second compiler and not a compliance
        # decision. It exists because a compiler can otherwise omit a source
        # clause from both its IR and its own self-audit inventory.
        self._check_cancelled("semantic verification")
        verify_prompt = self._semantic_verification_user_prompt(canonical, semantic_preparation)
        self._emit_trace(
            trace, "06d_semantic_verification", "Requirement Semantic Verification", "running",
            "Original requirements are independently reconstructed and structurally compared with compiled IRs before Python execution.",
            input_value={
                "model_client": self._client_trace_descriptor(self.semantic_verification_client, "semantic_verification"),
                "requirement_count": len(canonical.requirements),
                "verification_request": json.loads(verify_prompt),
            },
        )
        try:
            verify_response = self.semantic_verification_client.structured_repair(
                system_prompt=REQUIREMENT_SEMANTIC_VERIFICATION_PROMPT,
                user_prompt=verify_prompt,
                response_model=RequirementSemanticVerificationBatch,
                schema_name="rca_requirement_semantic_verification_v085",
            )
        except AttributeError:
            verify_response = self.semantic_verification_client.structured_chat(
                system_prompt=REQUIREMENT_SEMANTIC_VERIFICATION_PROMPT,
                user_prompt=verify_prompt,
                response_model=RequirementSemanticVerificationBatch,
                schema_name="rca_requirement_semantic_verification_v085",
            )
        except ModelGatewayError as exc:
            stats.append(exc.stats)
            attempts.append(self._make_failed_attempt(
                len(attempts) + 1, "semantic_verification", "SEMANTIC_VERIFIER", exc
            ))
            raise PipelineValidationError(
                "Independent semantic verification failed; unverified Requirement IR is not executed.\n" + str(exc),
                canonical_case=canonical, attempts=attempts, stats=stats,
            ) from exc
        stats.append(verify_response.stats)
        attempts.append(self._make_aux_attempt(
            len(attempts) + 1, "semantic_verification", "SEMANTIC_VERIFIER", verify_response
        ))
        verification_issues = self._semantic_verification_issues(canonical, semantic_preparation, verify_response.parsed)
        self._emit_trace(
            trace, "06d_semantic_verification", "Requirement Semantic Verification",
            "attention" if verification_issues else "complete",
            f"Independent verifier identified {len(verification_issues)} material semantic mismatch(es).",
            output_value={
                "verification": verify_response.parsed,
                "issues": [x.model_dump(mode="json") for x in verification_issues],
                "model_call": verify_response.stats,
                "finish_reason": verify_response.finish_reason,
                "transport": verify_response.transport,
            },
        )

        # 07: structural integrity/materiality analysis. Python never reads the
        # requirement prose to repair meaning.
        integrity_issues = self.semantic_integrity_checker.validate(canonical, semantic_preparation) + verification_issues
        material = self.semantic_integrity_checker.material_issues(integrity_issues)
        canonical.semantic_integrity_issues = copy.deepcopy(integrity_issues)
        self._emit_trace(trace, "07_semantic_integrity", "Python Semantic Integrity / Materiality", "attention" if material else "complete",
                         f"Found {len(integrity_issues)} semantic integrity issue(s), {len(material)} material to compliance.",
                         output_value=[x.model_dump(mode="json") for x in integrity_issues])

        # 08: at most one case-level 27B semantic arbitration call.
        if material and self.semantic_arbitration_enabled and self.semantic_arbitration_client is not None:
            arbitrated_requirement_ids = sorted({x.requirement_id for x in material if x.requirement_id})
            arbitration_requirement_targets = self._arbitration_requirement_targets(semantic_preparation, material)
            arbitration_evidence_targets = {x.evidence_id for x in material if x.evidence_id}
            self._check_cancelled("27B semantic arbitration")
            progress("Semantic arbitration", f"Resolving {len(material)} material semantic issue(s) in one primary-model call...")
            arb_prompt = self._semantic_arbitration_user_prompt(
                canonical, semantic_preparation, material, arbitration_requirement_targets, arbitration_evidence_targets
            )
            self._emit_trace(trace, "08_semantic_arbitration", "27B Semantic Arbitration", "running",
                             "All material unresolved semantic issues are batched into one source-authoritative call. Existing Requirement IRs are repairable only through exact field-level targets.",
                             input_value={
                                 "system_prompt": SEMANTIC_ARBITRATION_PROMPT,
                                 "user_prompt": arb_prompt,
                                 "requirement_patch_targets": arbitration_requirement_targets,
                                 "evidence_replacement_targets": sorted(arbitration_evidence_targets),
                             })
            try:
                arb_response = self.semantic_arbitration_client.structured_chat(
                    system_prompt=SEMANTIC_ARBITRATION_PROMPT,
                    user_prompt=arb_prompt,
                    response_model=SemanticArbitrationResponse,
                    schema_name="rca_semantic_arbitration_v088",
                )
                stats.append(arb_response.stats)
                attempts.append(self._make_aux_attempt(len(attempts)+1, "semantic_arbitration", "PRIMARY_SEMANTIC_ARBITRATION", arb_response))
                semantic_arbitration = arb_response.parsed
                self._validate_arbitration_response(
                    semantic_arbitration, arbitration_requirement_targets, arbitration_evidence_targets, material, semantic_preparation
                )
                semantic_preparation = self.semantic_arbitration_merger.apply(
                    semantic_preparation, semantic_arbitration, arbitration_requirement_targets, arbitration_evidence_targets
                )
                canonical.requirement_irs = copy.deepcopy(semantic_preparation.requirement_irs)
                canonical.evidence_annotations = copy.deepcopy(semantic_preparation.evidence_annotations)

                # Re-run the compact fast semantic verifier on repaired IRs. The
                # 27B is not called again even if material ambiguity remains.
                post_verify_prompt = self._semantic_verification_user_prompt(canonical, semantic_preparation)
                self._emit_trace(
                    trace, "08b_post_arbitration_verification", "Post-Arbitration Semantic Verification", "running",
                    "Reconstructing requirement semantics independently after arbitration before deterministic execution.",
                    input_value={
                        "model_client": self._client_trace_descriptor(self.semantic_verification_client, "semantic_verification"),
                        "verification_request": json.loads(post_verify_prompt),
                    },
                )
                try:
                    try:
                        post_verify_response = self.semantic_verification_client.structured_repair(
                            system_prompt=REQUIREMENT_SEMANTIC_VERIFICATION_PROMPT,
                            user_prompt=post_verify_prompt,
                            response_model=RequirementSemanticVerificationBatch,
                            schema_name="rca_requirement_semantic_verification_post_arbitration_v085",
                        )
                    except AttributeError:
                        post_verify_response = self.semantic_verification_client.structured_chat(
                            system_prompt=REQUIREMENT_SEMANTIC_VERIFICATION_PROMPT,
                            user_prompt=post_verify_prompt,
                            response_model=RequirementSemanticVerificationBatch,
                            schema_name="rca_requirement_semantic_verification_post_arbitration_v085",
                        )
                    stats.append(post_verify_response.stats)
                    attempts.append(self._make_aux_attempt(
                        len(attempts) + 1, "semantic_verification_post_arbitration",
                        "SEMANTIC_VERIFIER", post_verify_response
                    ))
                    post_verification_issues = self._semantic_verification_issues(canonical, semantic_preparation, post_verify_response.parsed)
                    self._emit_trace(
                        trace, "08b_post_arbitration_verification", "Post-Arbitration Semantic Verification",
                        "attention" if post_verification_issues else "complete",
                        f"Verifier identified {len(post_verification_issues)} material mismatch(es) after arbitration.",
                        output_value={
                            "verification": post_verify_response.parsed,
                            "issues": [x.model_dump(mode="json") for x in post_verification_issues],
                            "model_call": post_verify_response.stats,
                        },
                    )
                except ModelGatewayError as verify_exc:
                    stats.append(verify_exc.stats)
                    attempts.append(self._make_failed_attempt(
                        len(attempts) + 1, "semantic_verification_post_arbitration",
                        "SEMANTIC_VERIFIER", verify_exc
                    ))
                    self._emit_trace(
                        trace, "08b_post_arbitration_verification", "Post-Arbitration Semantic Verification", "failed",
                        "Post-arbitration semantic verification failed; repaired IR remains unverified.",
                        output_value={"error": str(verify_exc), "finish_reason": verify_exc.finish_reason, "retry_diagnostics": verify_exc.retry_diagnostics},
                    )
                    post_verification_issues = [
                        SemanticIntegrityIssue(
                            issue_id=f"VERIFY-POST-{idx:03d}",
                            requirement_id=rid,
                            description="Post-arbitration semantic verification failed; repaired IR remains unverified.",
                            material_to_compliance=True,
                        )
                        for idx, rid in enumerate(arbitrated_requirement_ids, start=1)
                    ]
                integrity_issues = self.semantic_integrity_checker.validate(canonical, semantic_preparation) + post_verification_issues
                material = self.semantic_integrity_checker.material_issues(integrity_issues)
                canonical.semantic_integrity_issues = copy.deepcopy(integrity_issues)
                raw_llm_json = arb_response.raw_json
                raw_requirement_reasoning_json = arb_response.raw_json
                self._emit_trace(trace, "08_semantic_arbitration", "27B Semantic Arbitration", "attention" if material else "complete",
                                 f"Arbitration completed; {len(material)} material issue(s) remain unresolved. No further 27B semantic retry is allowed.",
                                 output_value=semantic_arbitration)
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts)+1, "semantic_arbitration", "PRIMARY_SEMANTIC_ARBITRATION", exc))
                self._emit_trace(trace, "08_semantic_arbitration", "27B Semantic Arbitration", "attention",
                                 "The single bounded arbitration call failed; unresolved semantics remain conservative.", output_value={"error": str(exc)})
        else:
            self._emit_trace(trace, "08_semantic_arbitration", "27B Semantic Arbitration", "skipped",
                             "No material semantic ambiguity requires primary-model arbitration." if not material else "Semantic arbitration is disabled/unavailable; unresolved items remain UNKNOWN.", output_value="Skipped.")

        # 09-10: verified semantic case -> deterministic compliance.
        self._check_cancelled("Python compliance engine")
        progress("Deterministic compliance", "Executing verified Requirement IR against structured/verified evidence...")
        validated = self.compliance_engine.evaluate(canonical, semantic_preparation, integrity_issues)
        self._emit_trace(trace, "09_verified_semantics", "Verified Semantic Representation", "complete",
                         "Original sources remain provenance; only verified semantic objects are executable.",
                         output_value={"requirement_irs": semantic_preparation.requirement_irs, "evidence_annotations": semantic_preparation.evidence_annotations, "unresolved": [x.model_dump(mode="json") for x in integrity_issues if x.material_to_compliance]})
        self._emit_trace(trace, "10_python_compliance", "Python Deterministic Compliance Engine", "complete",
                         "Python executed the Requirement IR and owns applicability, timing and compliance results.",
                         output_value={"requirement_results": [x.model_dump(mode="json") for x in validated.requirement_results]})

        # 11: mechanism-evidence router. Bare violation != reason to spend 27B.
        rca_route_decision = self.rca_router.decide(canonical, semantic_preparation, validated)
        self._emit_trace(trace, "11_rca_routing", "RCA Router", "complete",
                         "Deep RCA is conditional on mechanism-oriented evidence, not on requirement failure alone.", output_value=rca_route_decision)

        if self.rca_synthesis_enabled and rca_route_decision.run_rca:
            self._check_cancelled("27B RCA synthesis")
            rca_evidence_packet = self.rca_packet_builder.build(canonical, semantic_preparation, validated, rca_route_decision)
            rca_prompt = self._rca_v080_user_prompt(rca_evidence_packet)
            progress("RCA synthesis", "Calling the primary model with a compact verified RCA Evidence Packet...")
            self._emit_trace(trace, "12_rca_synthesis", "27B RCA Synthesis", "running",
                             "The RCA model does not receive the full raw case or original natural-language requirements.",
                             input_value={"system_prompt": RCA_SYNTHESIS_V080_PROMPT, "rca_evidence_packet": rca_evidence_packet})
            try:
                rca_response = self.client.structured_chat(
                    system_prompt=RCA_SYNTHESIS_V080_PROMPT,
                    user_prompt=rca_prompt,
                    response_model=RCASynthesisReasoning,
                    schema_name="rca_synthesis_v080",
                )
                stats.append(rca_response.stats)
                attempts.append(self._make_aux_attempt(len(attempts)+1, "rca_synthesis", "PRIMARY_RCA_SYNTHESIS", rca_response, validated.semantic, validated))
                rca_synthesis = rca_response.parsed
                raw_rca_synthesis_json = rca_response.raw_json
                raw_llm_json = rca_response.raw_json
                validated = self._merge_v080_rca(validated, canonical, semantic_preparation, rca_synthesis)
                self._emit_trace(trace, "12_rca_synthesis", "27B RCA Synthesis", "complete",
                                 "RCA synthesis completed without a schema path capable of modifying requirement truth.", output_value=rca_synthesis)
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts)+1, "rca_synthesis", "PRIMARY_RCA_SYNTHESIS", exc, validated.semantic, validated))
                self._emit_trace(trace, "12_rca_synthesis", "27B RCA Synthesis", "attention",
                                 "RCA synthesis failed; authoritative compliance results are retained and the report continues without hypotheses.", output_value={"error": str(exc)})
        else:
            self._emit_trace(trace, "12_rca_synthesis", "27B RCA Synthesis", "skipped",
                             "No mechanism-oriented evidence justifies a deep RCA call." if not rca_route_decision.run_rca else "RCA synthesis is disabled.", output_value="Skipped.")

        # 13: optional 4B epistemic hypothesis review. It may only rewrite/drop
        # hypothesis language and cannot invoke the legacy compliance validator.
        if self.fast_hypothesis_review_enabled and self.hypothesis_review_client is not None and validated.hypotheses:
            hyp_payload = self.hypothesis_review_gate.payload(validated)
            hyp_prompt = self._hypothesis_review_user_prompt(hyp_payload)
            self._emit_trace(trace, "13_hypothesis_review", "4B Hypothesis Epistemic Review", "running",
                             "Review is limited to hypothesis epistemic language.", input_value=hyp_payload)
            try:
                hyp_response = self.hypothesis_review_client.structured_repair(
                    system_prompt=FAST_HYPOTHESIS_REVIEW_PROMPT,
                    user_prompt=hyp_prompt,
                    response_model=HypothesisReviewResponse,
                    schema_name="rca_hypothesis_review_v080",
                )
                stats.append(hyp_response.stats)
                attempts.append(self._make_aux_attempt(len(attempts)+1, "hypothesis_review", "FAST_HYPOTHESIS_REVIEW", hyp_response, validated.semantic, validated))
                hypothesis_epistemic_review = hyp_response.parsed
                validated, _, _ = self.hypothesis_review_gate.apply_v080(validated, hypothesis_epistemic_review)
                self._emit_trace(trace, "13_hypothesis_review", "4B Hypothesis Epistemic Review", "complete",
                                 "Hypothesis language review applied without re-evaluating compliance.", output_value=hypothesis_epistemic_review)
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts)+1, "hypothesis_review", "FAST_HYPOTHESIS_REVIEW", exc, validated.semantic, validated))
                self._emit_trace(trace, "13_hypothesis_review", "4B Hypothesis Epistemic Review", "attention",
                                 "Optional hypothesis review failed; structurally validated hypotheses are retained.", output_value={"error": str(exc)})
        else:
            self._emit_trace(trace, "13_hypothesis_review", "4B Hypothesis Epistemic Review", "skipped", "No hypotheses require review.", output_value="Skipped.")

        # 14: optional wording review is audit-only in v0.8. It cannot patch
        # applicability/sufficiency/verdict fields.
        if self.fast_final_review_enabled and self.final_review_client is not None:
            review_payload = self.linguistic_review_gate.compact_payload(validated)
            review_prompt = self._final_review_user_prompt(review_payload)
            self._emit_trace(trace, "14_wording_review", "4B Wording Audit", "running",
                             "Audit-only linguistic review; output has zero semantic authority.", input_value=review_payload)
            try:
                review_response = self.final_review_client.structured_repair(
                    system_prompt=FAST_FINAL_REVIEW_PROMPT,
                    user_prompt=review_prompt,
                    response_model=LinguisticReviewResponse,
                    schema_name="rca_wording_audit_v080",
                )
                stats.append(review_response.stats)
                attempts.append(self._make_aux_attempt(len(attempts)+1, "wording_audit", "FAST_FINAL_REVIEW", review_response, validated.semantic, validated))
                final_linguistic_review = review_response.parsed
                self._emit_trace(trace, "14_wording_review", "4B Wording Audit", "complete",
                                 "Wording audit recorded; no semantic fields were modified.", output_value=final_linguistic_review)
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts)+1, "wording_audit", "FAST_FINAL_REVIEW", exc, validated.semantic, validated))
                self._emit_trace(trace, "14_wording_review", "4B Wording Audit", "attention", "Optional wording audit failed.", output_value={"error": str(exc)})
        else:
            self._emit_trace(trace, "14_wording_review", "4B Wording Audit", "skipped", "Wording audit disabled or unavailable.", output_value="Skipped.")

        # 15-17: structural final gate + deterministic formatter.
        final_issues = self._v080_final_consistency_issues(validated, canonical, semantic_preparation)
        if final_issues:
            validated.issues.extend(final_issues)
            critical = [x for x in final_issues if x.severity == ValidationSeverity.ERROR]
            if critical:
                raise PipelineValidationError("v0.8 Python final consistency gate rejected the RCA output.\n" + "\n".join(x.message for x in critical), validated=validated, canonical_case=canonical, attempts=attempts, stats=stats)
        self._emit_trace(trace, "15_python_final_gate", "Python Final Consistency Gate", "complete",
                         "Structural consistency passed; no downstream model can overwrite compliance truth.", output_value={"issues": [x.model_dump(mode="json") for x in final_issues]})
        progress("Final report formatter", "Generating the 11-section analyst report from authoritative structured data...")
        report = self.formatter.format(validated)
        self._emit_trace(trace, "16_report_formatter", "11-Section Report Formatter", "complete", "Deterministic report generated.", output_value=report)
        self._emit_trace(trace, "17_final_output", "Final Output", "complete",
                         "Validated v0.8.8 analysis is ready for session export.",
                         output_value=report)
        progress("Complete", "v0.8.8 analysis completed.")

        return PipelineResult(
            canonical_case=canonical,
            intake_normalization=intake_normalization,
            source_availability_normalization=source_availability_normalization,
            content_classification=content_classification,
            semantic_preparation=semantic_preparation,
            semantic_arbitration=semantic_arbitration,
            rca_route_decision=rca_route_decision,
            rca_evidence_packet=rca_evidence_packet,
            rca_synthesis=rca_synthesis,
            hypothesis_epistemic_review=hypothesis_epistemic_review,
            final_linguistic_review=final_linguistic_review,
            validated=validated,
            final_report=report,
            raw_semantic_json=json.dumps(validated.semantic.model_dump(mode="json"), indent=2, ensure_ascii=False),
            raw_llm_json=raw_llm_json,
            raw_requirement_reasoning_json=raw_requirement_reasoning_json,
            raw_rca_synthesis_json=raw_rca_synthesis_json,
            stats=stats,
            repair_performed=semantic_arbitration is not None,
            attempts=attempts,
            repair_log=repair_log,
        )

    @staticmethod
    def _compact_requirement_reference(req) -> dict:
        return {
            "requirement_id": req.requirement_id,
            "requirement_text": req.requirement_text,
        }

    @staticmethod
    def _compact_language_evidence(canonical: CanonicalCase) -> list[dict]:
        out = []
        for item in canonical.evidence_inventory:
            if item.evidence_class.value in {"SYSTEM_REQUIREMENT", "TEST_INSTRUCTION"}:
                continue
            if (
                item.evidence_class.value == "DIRECT_OBSERVATION"
                and item.observation_type.value in {"STATE_SAMPLE", "TRANSITION", "INTERVAL_STATE"}
                and item.signal_name
            ):
                continue
            row = {
                "evidence_id": item.id,
                "evidence_class": item.evidence_class.value,
                "text": item.text,
                "source": item.source,
            }
            raw = (item.raw_source_text or "").strip()
            if raw and raw != (item.text or "").strip():
                row["raw_source_text"] = raw
            out.append(row)
        return out

    @staticmethod
    def _compact_structured_trace(canonical: CanonicalCase) -> list[dict]:
        out = []
        for item in canonical.evidence_inventory:
            if not (
                item.evidence_class.value == "DIRECT_OBSERVATION"
                and item.observation_type.value in {"STATE_SAMPLE", "TRANSITION", "INTERVAL_STATE"}
                and item.signal_name
            ):
                continue
            out.append({
                "evidence_id": item.id,
                "observation_type": item.observation_type.value,
                "signal": item.signal_name,
                "value": item.signal_value,
                "timestamp_seconds": item.timestamp_seconds,
                "transition_from": item.transition_from,
                "transition_to": item.transition_to,
                "observation_group": item.observation_group,
                "event_coverage_complete": item.event_coverage_complete,
            })
        return out

    @classmethod
    def _semantic_requirement_batches(cls, canonical: CanonicalCase) -> list[list]:
        """Create bounded fast-model batches without splitting individual requirements.

        The batch limit is an output-size guard for small local model contexts, not
        a semantic routing decision and never causes a 27B call.  Every batch still
        receives all requirement texts as read-only references so explicit
        cross-requirement relationships can be compiled without losing context.
        """
        reqs = list(canonical.requirements)
        if not reqs:
            return []
        # Five ordinary requirements fit comfortably with the narrower
        # RequirementCompilationBatch schema in an 8k Qwen3.5 context. Very long
        # source text is further bounded by a conservative character budget.
        batches = []
        current = []
        source_chars = 0
        for req in reqs:
            cost = max(300, len(req.requirement_text or ""))
            if current and (len(current) >= 5 or source_chars + cost > 6500):
                batches.append(current)
                current = []
                source_chars = 0
            current.append(req)
            source_chars += cost
        if current:
            batches.append(current)
        return batches

    @classmethod
    def _semantic_requirement_batch_prompt(
        cls, canonical: CanonicalCase, batch: list, *, missing_recovery: bool = False
    ) -> str:
        expected_ids = [x.requirement_id for x in batch]
        instruction = (
            "Compile exactly requirements_to_compile. reference_requirements are context only; "
            "do not return IRs for them unless they are also in requirements_to_compile. "
            "Return exactly one RequirementIR for every ID in expected_requirement_ids, no omissions and no duplicates."
        )
        if missing_recovery:
            instruction += (
                " This is a bounded recovery call because the previous compiler response omitted one or more authoritative IDs. "
                "Return all and only the missing IDs listed here."
            )
        payload = {
            "ticket_context": {
                "ticket_id": canonical.ticket_id,
                "title": canonical.title,
                "description": canonical.description,
            },
            "expected_requirement_ids": expected_ids,
            "requirements_to_compile": [cls._compact_requirement_reference(x) for x in batch],
            "reference_requirements": [cls._compact_requirement_reference(x) for x in canonical.requirements],
            "user_instructions": canonical.user_instructions,
            "instruction": instruction,
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _logic_contains_semantic_id(node, semantic_id: str) -> bool:
        if node is None or not semantic_id:
            return False
        if node.semantic_id == semantic_id:
            return True
        return any(RCAPipeline._logic_contains_semantic_id(child, semantic_id) for child in node.children)

    @classmethod
    def _structural_completion_targets(cls, preparation: SemanticPreparation, issues) -> dict[str, list[str]]:
        by_id = {x.requirement_id: x for x in preparation.requirement_irs}
        targets: dict[str, set[str]] = {}
        for issue in issues:
            ir = by_id.get(issue.requirement_id)
            if ir is None:
                continue
            sid = issue.semantic_id
            description = issue.description
            fields: set[str] = set()

            # Provenance/audit defects are explicit structural targets.  The
            # patch replaces the complete source-clause inventory; Python does
            # not derive clause text or roles itself.
            if "source-clause" in description or "source clause" in description or "compiler source-clause audit inventory" in description:
                fields.add("source_clauses")

            if ir.required_behavior is not None and sid and ir.required_behavior.semantic_id == sid:
                fields.add("required_behavior")
            elif ir.trigger is not None and sid and ir.trigger.semantic_id == sid:
                fields.add("trigger")
            elif ir.timing is not None and sid and ir.timing.semantic_id == sid:
                fields.add("timing")
            elif ir.persistence is not None and sid and ir.persistence.semantic_id == sid:
                fields.add("persistence")
            elif sid and cls._logic_contains_semantic_id(ir.condition, sid):
                fields.add("condition")
            else:
                # Missing top-level objects can be targeted from their explicit
                # source-clause semantic IDs. This is structured linkage, not
                # interpretation of the requirement prose.
                clause = next((c for c in ir.source_clauses if c.semantic_id == sid), None)
                role = clause.role.value if clause is not None else ""
                field = {
                    "CONDITION": "condition",
                    "TRIGGER": "trigger",
                    "REQUIRED_BEHAVIOR": "required_behavior",
                    "TIMING": "timing",
                    "PERSISTENCE": "persistence",
                }.get(role, "")
                if field:
                    fields.add(field)

            # Missing semantic IDs on timing/persistence/trigger/behavior need
            # the executable object repaired as well as the audit inventory.
            lowered = description.casefold()
            if "requirement timing" in lowered:
                fields.add("timing")
                fields.add("source_clauses")
            if "requirement persistence" in lowered:
                fields.add("persistence")
                fields.add("source_clauses")
            if "requirement trigger" in lowered:
                fields.add("trigger")
            if "required_behavior" in lowered or "required behavior" in lowered:
                fields.add("required_behavior")
            # Independent-verifier mismatch descriptions are field-scoped too.
            # Parse only canonical IR field names emitted by our own verifier,
            # never requirement prose.
            if "condition" in lowered:
                fields.add("condition")
            if "trigger" in lowered:
                fields.add("trigger")
            if "timing" in lowered:
                fields.add("timing")
            if "persistence" in lowered:
                fields.add("persistence")
            if "normative_type" in lowered or "normative type" in lowered:
                fields.add("normative_type")
            if "relationship" in lowered:
                fields.add("relationships")

            if fields:
                targets.setdefault(ir.requirement_id, set()).update(fields)
        return {rid: sorted(fields) for rid, fields in targets.items()}

    @staticmethod
    def _compact_ir_for_structural_completion(ir) -> dict:
        """Read-only compact IR used only to target model-authored completion."""
        def logic(node):
            if node is None:
                return None
            return {
                "kind": node.kind.value,
                "semantic_id": node.semantic_id,
                "source_phrase": node.source_phrase,
                "signal": node.signal,
                "operator": node.operator.value,
                "value": node.value,
                "children": [logic(x) for x in node.children],
            }
        return {
            "normative_type": ir.normative_type.value,
            "condition": logic(ir.condition),
            "trigger": ir.trigger.model_dump(mode="json") if ir.trigger else None,
            "required_behavior": ir.required_behavior.model_dump(mode="json") if ir.required_behavior else None,
            "timing": ir.timing.model_dump(mode="json") if ir.timing else None,
            "persistence": ir.persistence.model_dump(mode="json") if ir.persistence else None,
            "relationships": [x.model_dump(mode="json") for x in ir.relationships],
            "source_clauses": [x.model_dump(mode="json") for x in ir.source_clauses],
        }

    @classmethod
    def _semantic_structural_repair_prompt(cls, canonical: CanonicalCase, preparation: SemanticPreparation, issues, targets) -> str:
        ir_by_id = {x.requirement_id: x for x in preparation.requirement_irs}
        req_by_id = {x.requirement_id: x for x in canonical.requirements}
        rows = []
        for rid, fields in sorted(targets.items()):
            ir = ir_by_id.get(rid)
            req = req_by_id.get(rid)
            if ir is None or req is None:
                continue
            field_context = {}
            for field in fields:
                value = getattr(ir, field, None)
                if hasattr(value, "model_dump"):
                    field_context[field] = value.model_dump(mode="json")
                elif isinstance(value, list):
                    field_context[field] = [
                        x.model_dump(mode="json") if hasattr(x, "model_dump") else x
                        for x in value
                    ]
                else:
                    field_context[field] = value
            semantic_ids = sorted({x.semantic_id for x in issues if x.requirement_id == rid and x.semantic_id})
            rows.append({
                "requirement_id": rid,
                "original_requirement": req.requirement_text,
                "target_fields": fields,
                "target_semantic_ids": semantic_ids,
                "current_target_values": field_context,
                "current_ir_read_only": cls._compact_ir_for_structural_completion(ir),
                "defects": [x.description for x in issues if x.requirement_id == rid],
            })
        payload = {
            "requirements": rows,
            "instruction": (
                "Return compact patches for only target_fields. Do not regenerate or repeat already-valid IR fields. "
                "When source_clauses is targeted, return the COMPLETE source-clause audit inventory for every material "
                "semantic element in current_ir_read_only and every explicit material clause in the original requirement. "
                "The returned source_clauses list replaces the existing list; it is not appended."
            ),
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _validate_structural_patches(batch: RequirementStructuralPatchBatch, targets: dict[str, list[str]]) -> None:
        allowed_patch_fields = {"condition", "trigger", "required_behavior", "timing", "persistence", "source_clauses"}
        seen = set()
        for patch in batch.patches:
            if patch.requirement_id not in targets:
                raise ValueError(f"Structural completion returned untargeted requirement {patch.requirement_id}")
            if patch.requirement_id in seen:
                raise ValueError(f"Structural completion returned duplicate patch for {patch.requirement_id}")
            seen.add(patch.requirement_id)
            supplied = {name for name in allowed_patch_fields if name in patch.model_fields_set and getattr(patch, name) is not None}
            expected = set(targets[patch.requirement_id])
            unexpected = supplied - expected
            if unexpected:
                raise ValueError(
                    f"Structural completion attempted untargeted fields for {patch.requirement_id}: {sorted(unexpected)}"
                )
            missing = expected - supplied
            if missing:
                raise ValueError(
                    f"Structural completion omitted targeted fields for {patch.requirement_id}: {sorted(missing)}"
                )
        missing_requirements = set(targets) - seen
        if missing_requirements:
            raise ValueError(
                "Structural completion omitted required requirement patches: " + ", ".join(sorted(missing_requirements))
            )

    @staticmethod
    def _apply_structural_patches(preparation: SemanticPreparation, batch: RequirementStructuralPatchBatch, targets: dict[str, list[str]]) -> SemanticPreparation:
        out = copy.deepcopy(preparation)
        patches = {x.requirement_id: x for x in batch.patches}
        for ir in out.requirement_irs:
            patch = patches.get(ir.requirement_id)
            if patch is None:
                continue
            for field in targets.get(ir.requirement_id, []):
                if field in patch.model_fields_set:
                    value = getattr(patch, field)
                    if value is not None:
                        setattr(ir, field, copy.deepcopy(value))
        return out

    @staticmethod
    def _replace_requirement_irs(preparation: SemanticPreparation, replacements: list, allowed_ids: list[str]) -> SemanticPreparation:
        """Replace only explicitly targeted IRs; no semantic inference or field merging."""
        out = copy.deepcopy(preparation)
        allowed = set(allowed_ids)
        repl = {x.requirement_id: copy.deepcopy(x) for x in replacements if x.requirement_id in allowed}
        out.requirement_irs = [repl.get(x.requirement_id, x) for x in out.requirement_irs]
        known = {x.requirement_id for x in out.requirement_irs}
        for rid in allowed_ids:
            if rid in repl and rid not in known:
                out.requirement_irs.append(repl[rid])
        return out

    @staticmethod
    def _replace_evidence_annotations(preparation: SemanticPreparation, replacements: list, allowed_ids: list[str]) -> SemanticPreparation:
        """Replace only targeted evidence annotations; do not merge semantic fields."""
        out = copy.deepcopy(preparation)
        allowed = set(allowed_ids)
        repl = {x.evidence_id: copy.deepcopy(x) for x in replacements if x.evidence_id in allowed}
        out.evidence_annotations = [repl.get(x.evidence_id, x) for x in out.evidence_annotations]
        known = {x.evidence_id for x in out.evidence_annotations}
        for eid in allowed_ids:
            if eid in repl and eid not in known:
                out.evidence_annotations.append(repl[eid])
        return out

    @classmethod
    def _semantic_evidence_repair_prompt(cls, canonical: CanonicalCase, evidence_ids: list[str], issues) -> str:
        allowed = set(evidence_ids)
        evidence_rows = [
            row for row in cls._compact_language_evidence(canonical)
            if row.get("evidence_id") in allowed
        ]
        payload = {
            "ticket_context": {
                "ticket_id": canonical.ticket_id,
                "title": canonical.title,
                "description": canonical.description,
            },
            "reference_requirements": [cls._compact_requirement_reference(x) for x in canonical.requirements],
            "evidence_requiring_language_interpretation": evidence_rows,
            "structured_trace_facts_read_only": cls._compact_structured_trace(canonical),
            "structural_defects_from_previous_transport": [x.model_dump(mode="json") for x in issues],
            "user_instructions": canonical.user_instructions,
            "instruction": (
                "Reannotate exactly the listed evidence items from their ORIGINAL source text. "
                "Do not repeat requirement compilation. Return complete EvidenceSemanticAnnotation objects. "
                "Persistent facts marked scope.resolution=RESOLVED must include a concrete non-empty scope.scope_id; "
                "otherwise use PARTIAL/UNRESOLVED rather than guessing."
            ),
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def _semantic_evidence_batch_prompt(cls, canonical: CanonicalCase) -> str:
        payload = {
            "ticket_context": {
                "ticket_id": canonical.ticket_id,
                "title": canonical.title,
                "description": canonical.description,
            },
            "requirements_to_compile": [],
            "reference_requirements": [cls._compact_requirement_reference(x) for x in canonical.requirements],
            "evidence_requiring_language_interpretation": cls._compact_language_evidence(canonical),
            "structured_trace_facts_read_only": cls._compact_structured_trace(canonical),
            "historical_source_present": bool(canonical.historical_text.strip()),
            "diagnostic_source_present": bool(canonical.diagnostics_text.strip()),
            "user_instructions": canonical.user_instructions,
            "instruction": "Annotate only the supplied language evidence. Do not compile Requirement IRs in this batch.",
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def _semantic_preparation_user_prompt(cls, canonical: CanonicalCase) -> str:
        """Compatibility helper used by tests/debugging; production uses bounded batches."""
        payload = {
            "requirements_to_compile": [cls._compact_requirement_reference(x) for x in canonical.requirements],
            "reference_requirements": [cls._compact_requirement_reference(x) for x in canonical.requirements],
            "evidence_requiring_language_interpretation": cls._compact_language_evidence(canonical),
            "structured_trace_facts_read_only": cls._compact_structured_trace(canonical),
            "user_instructions": canonical.user_instructions,
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _merge_semantic_preparation(
        requirement_batches: list[RequirementCompilationBatch],
        evidence_batch: Optional[EvidenceAnnotationBatch],
    ) -> SemanticPreparation:
        affected = ""
        irs = []
        annotations = []
        unresolved = []
        for batch in requirement_batches:
            if not affected and batch.affected_functionality.strip():
                affected = batch.affected_functionality.strip()
            irs.extend(copy.deepcopy(batch.requirement_irs))
            unresolved.extend(x for x in batch.unresolved_case_semantics if x not in unresolved)
        if evidence_batch is not None:
            annotations.extend(copy.deepcopy(evidence_batch.evidence_annotations))
            unresolved.extend(x for x in evidence_batch.unresolved_case_semantics if x not in unresolved)
        return SemanticPreparation(
            affected_functionality=affected,
            requirement_irs=irs,
            evidence_annotations=annotations,
            unresolved_case_semantics=unresolved,
        )

    @staticmethod
    def _compact_ir_for_verification(ir) -> dict:
        def logic(node):
            if node is None:
                return None
            return {
                "kind": node.kind.value,
                "signal": node.signal,
                "operator": node.operator.value,
                "value": node.value,
                "source_phrase": node.source_phrase,
                "children": [logic(x) for x in node.children],
            }
        return {
            "requirement_id": ir.requirement_id,
            "faithful_meaning": ir.faithful_meaning,
            "normative_type": ir.normative_type.value,
            "condition": logic(ir.condition),
            "trigger": ir.trigger.model_dump(mode="json") if ir.trigger else None,
            "required_behavior": ir.required_behavior.model_dump(mode="json") if ir.required_behavior else None,
            "timing": ir.timing.model_dump(mode="json") if ir.timing else None,
            "persistence": ir.persistence.model_dump(mode="json") if ir.persistence else None,
            "relationships": [x.model_dump(mode="json") for x in ir.relationships],
        }

    @classmethod
    def _semantic_verification_user_prompt(cls, canonical: CanonicalCase, preparation: SemanticPreparation) -> str:
        by_id = {x.requirement_id: x for x in preparation.requirement_irs}
        payload = {
            "requirements": [
                {
                    "requirement_id": req.requirement_id,
                    "original_requirement": req.requirement_text,
                    "compiled_ir": cls._compact_ir_for_verification(by_id[req.requirement_id]) if req.requirement_id in by_id else None,
                }
                for req in canonical.requirements
            ],
            "instruction": "Verify each compiled IR independently against its original requirement. The IR is untrusted and must not anchor the decision.",
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _normalized_semantic_value(value) -> str:
        return str(value or "").strip().casefold()

    @classmethod
    def _logic_signature(cls, node):
        if node is None:
            return None
        kind = node.kind.value
        if kind == "PREDICATE":
            return (kind, cls._normalized_semantic_value(node.signal), node.operator.value, cls._normalized_semantic_value(node.value))
        children = [cls._logic_signature(x) for x in node.children]
        if kind in {"AND", "OR"}:
            children = sorted(children, key=repr)
        return (kind, tuple(children))

    @classmethod
    def _semantic_fingerprint_signature(cls, fp) -> dict:
        def event(x):
            return None if x is None else (cls._normalized_semantic_value(x.signal), cls._normalized_semantic_value(x.event), cls._normalized_semantic_value(x.value))
        def behavior(x):
            return None if x is None else (cls._normalized_semantic_value(x.signal), x.operator.value, cls._normalized_semantic_value(x.value), cls._normalized_semantic_value(x.event), cls._normalized_semantic_value(x.process_description))
        def timing(x):
            return None if x is None else (x.limit_ms, cls._normalized_semantic_value(x.relation))
        def persistence(x):
            return None if x is None else (bool(x.required), cls._normalized_semantic_value(x.scope))
        rels = sorted((cls._normalized_semantic_value(x.relationship_type), cls._normalized_semantic_value(x.target_requirement_id)) for x in fp.relationships)
        return {
            "normative_type": fp.normative_type.value,
            "condition": cls._logic_signature(fp.condition),
            "trigger": event(fp.trigger),
            "required_behavior": behavior(fp.required_behavior),
            "timing": timing(fp.timing),
            "persistence": persistence(fp.persistence),
            "relationships": rels,
        }

    @classmethod
    def _ir_semantic_signature(cls, ir) -> dict:
        class View:
            pass
        view = View()
        for name in ("normative_type", "condition", "trigger", "required_behavior", "timing", "persistence", "relationships"):
            setattr(view, name, getattr(ir, name))
        return cls._semantic_fingerprint_signature(view)

    @staticmethod
    def _client_trace_descriptor(client, role: str) -> dict:
        if client is None:
            return {"role": role, "configured": False}
        resolved_transport = ""
        try:
            resolved_transport = client.resolve_transport()
        except Exception:
            resolved_transport = getattr(client, "transport", "")
        return {
            "role": role,
            "configured": True,
            "endpoint": getattr(client, "base_url", ""),
            "model": getattr(client, "model", ""),
            "transport": resolved_transport,
            "thinking": getattr(client, "thinking_mode", ""),
            "reasoning": getattr(client, "reasoning_effort", ""),
            "temperature": getattr(client, "temperature", None),
            "max_tokens": getattr(client, "max_tokens", None),
        }

    @classmethod
    def _semantic_verification_issues(cls, canonical: CanonicalCase, preparation: SemanticPreparation, verification: RequirementSemanticVerificationBatch) -> list[SemanticIntegrityIssue]:
        expected = {x.requirement_id for x in canonical.requirements}
        returned = {x.requirement_id for x in verification.requirements}
        candidates = {x.requirement_id: x for x in preparation.requirement_irs}
        issues = []
        seq = 1
        for rid in sorted(expected - returned):
            issues.append(SemanticIntegrityIssue(
                issue_id=f"VERIFY-{seq:03d}", requirement_id=rid,
                description="Independent semantic verifier returned no result for this requirement.",
                material_to_compliance=True,
            ))
            seq += 1
        for item in verification.requirements:
            if item.requirement_id not in expected:
                issues.append(SemanticIntegrityIssue(
                    issue_id=f"VERIFY-{seq:03d}", requirement_id=item.requirement_id,
                    description="Independent semantic verifier returned an unknown requirement ID.",
                    material_to_compliance=True,
                ))
                seq += 1
                continue
            candidate = candidates.get(item.requirement_id)
            if candidate is None:
                issues.append(SemanticIntegrityIssue(
                    issue_id=f"VERIFY-{seq:03d}", requirement_id=item.requirement_id,
                    description="Independent semantic verifier returned semantics for a requirement with no compiler IR candidate.",
                    material_to_compliance=True,
                ))
                seq += 1
                continue
            independent_signature = cls._semantic_fingerprint_signature(item.independent_semantics)
            candidate_signature = cls._ir_semantic_signature(candidate)
            mismatched_fields = [k for k in independent_signature if independent_signature[k] != candidate_signature[k]]
            if mismatched_fields:
                issues.append(SemanticIntegrityIssue(
                    issue_id=f"VERIFY-{seq:03d}", requirement_id=item.requirement_id,
                    description=(
                        "Independent source-semantic reconstruction disagrees with compiled IR in: "
                        + ", ".join(mismatched_fields)
                        + ". Compiler/verifier prose agreement cannot override this structured mismatch."
                    ),
                    material_to_compliance=True,
                    target_fields=sorted(mismatched_fields),
                ))
                seq += 1
            if item.resolution.value != "VERIFIED":
                detail = "; ".join(item.missing_or_misrepresented_source_spans) or item.notes or item.resolution.value
                issues.append(SemanticIntegrityIssue(
                    issue_id=f"VERIFY-{seq:03d}", requirement_id=item.requirement_id,
                    description=f"Independent semantic verification is {item.resolution.value}: {detail}",
                    material_to_compliance=True,
                    target_fields=sorted(mismatched_fields),
                ))
                seq += 1
        return issues

    @classmethod
    def _arbitration_requirement_targets(cls, preparation: SemanticPreparation, issues) -> dict[str, list[str]]:
        """Return exact existing-IR fields arbitration may repair.

        Targets come only from structured defect classes / verifier target_fields.
        Python never derives a repair target from requirement prose.
        """
        existing = {x.requirement_id for x in preparation.requirement_irs}
        targets = {rid: set(fields) for rid, fields in cls._structural_completion_targets(preparation, issues).items()}
        supported = {
            "normative_type", "condition", "trigger", "required_behavior",
            "timing", "persistence", "relationships", "source_clauses",
        }
        for issue in issues:
            if issue.requirement_id not in existing:
                continue
            explicit = set(issue.target_fields) & supported
            if explicit:
                targets.setdefault(issue.requirement_id, set()).update(explicit)
        return {rid: sorted(fields) for rid, fields in targets.items() if fields}

    @staticmethod
    def _validate_arbitration_response(
        response: SemanticArbitrationResponse,
        requirement_targets: dict[str, list[str]],
        evidence_targets: set[str],
        material_issues,
        preparation: SemanticPreparation,
    ) -> None:
        """Validate one issue-scoped arbitration response before any merge.

        Existing IRs are repaired atomically by field patch. Full RequirementIR
        replacement is reserved for a requirement for which the compiler returned
        no candidate at all. Every targeted field must be supplied or explicitly
        left unresolved; partial silent repair is rejected.
        """
        issue_ids = {x.issue_id for x in material_issues}
        unknown_unresolved = set(response.unresolved_issue_ids) - issue_ids
        if unknown_unresolved:
            raise ValueError(f"Arbitration returned unknown unresolved issue IDs: {sorted(unknown_unresolved)}")

        unresolved = set(response.unresolved_issue_ids)
        issues_by_req: dict[str, set[str]] = {}
        issues_by_evidence: dict[str, set[str]] = {}
        for issue in material_issues:
            if issue.requirement_id:
                issues_by_req.setdefault(issue.requirement_id, set()).add(issue.issue_id)
            if issue.evidence_id:
                issues_by_evidence.setdefault(issue.evidence_id, set()).add(issue.issue_id)

        existing_ids = {x.requirement_id for x in preparation.requirement_irs}
        allowed_fields = {
            "normative_type", "condition", "trigger", "required_behavior",
            "timing", "persistence", "relationships", "source_clauses",
        }
        seen_patches = set()
        for patch in response.requirement_patches:
            rid = patch.requirement_id
            if rid in seen_patches:
                raise ValueError(f"Arbitration returned duplicate requirement patch for {rid}")
            seen_patches.add(rid)
            if rid not in existing_ids:
                raise ValueError(f"Arbitration field patch targets requirement without existing compiler IR: {rid}")
            if rid not in requirement_targets:
                raise ValueError(f"Arbitration returned untargeted requirement patch for {rid}")
            supplied = {
                name for name in allowed_fields
                if name in patch.model_fields_set and getattr(patch, name) is not None
            }
            expected = set(requirement_targets[rid])
            unexpected = supplied - expected
            if unexpected:
                raise ValueError(f"Arbitration patch attempted untargeted fields for {rid}: {sorted(unexpected)}")
            missing = expected - supplied
            if missing:
                raise ValueError(f"Arbitration patch omitted targeted fields for {rid}: {sorted(missing)}")

        # A targeted existing requirement may omit a field patch only when a
        # legacy full IR supplies the target fields or all current material
        # issues are explicitly kept unresolved.
        legacy_full_ids = {x.requirement_id for x in response.requirement_irs}
        for rid in requirement_targets:
            if rid in seen_patches or rid in legacy_full_ids:
                continue
            req_issues = issues_by_req.get(rid, set())
            if not req_issues or not req_issues.issubset(unresolved):
                raise ValueError(f"Arbitration omitted required field patch for {rid}")

        seen_full = set()
        for ir in response.requirement_irs:
            rid = ir.requirement_id
            if rid in seen_full:
                raise ValueError(f"Arbitration returned duplicate full RequirementIR for {rid}")
            seen_full.add(rid)
            if rid not in issues_by_req:
                raise ValueError(f"Arbitration returned untargeted full RequirementIR for {rid}")
            if rid in existing_ids:
                if rid not in requirement_targets:
                    raise ValueError(f"Arbitration returned full IR for existing requirement without field targets: {rid}")
                missing = [f for f in requirement_targets[rid] if not hasattr(ir, f) or getattr(ir, f) is None]
                if missing:
                    raise ValueError(f"Arbitration legacy full IR omitted targeted fields for {rid}: {missing}")
                # Count this as a supplied repair. The merger will still copy
                # only the Python-approved target fields, never the full IR.
                seen_patches.add(rid)

        # Requirements with no existing compiler candidate require a full IR or
        # an explicit unresolved decision.
        for rid, req_issues in issues_by_req.items():
            if rid in existing_ids:
                if rid not in requirement_targets and rid not in seen_patches and not req_issues.issubset(unresolved):
                    raise ValueError(f"Arbitration has no admissible repair target for material requirement {rid}")
                continue
            if rid not in seen_full and not req_issues.issubset(unresolved):
                raise ValueError(f"Arbitration omitted full recovery IR for missing compiler requirement {rid}")

        seen_evidence = set()
        for ann in response.evidence_annotations:
            if ann.evidence_id in seen_evidence:
                raise ValueError(f"Arbitration returned duplicate evidence replacement for {ann.evidence_id}")
            seen_evidence.add(ann.evidence_id)
            if ann.evidence_id not in evidence_targets:
                raise ValueError(f"Arbitration returned untargeted evidence replacement for {ann.evidence_id}")
        for eid in evidence_targets:
            if eid in seen_evidence:
                continue
            ev_issues = issues_by_evidence.get(eid, set())
            if not ev_issues or not ev_issues.issubset(unresolved):
                raise ValueError(f"Arbitration omitted targeted evidence replacement for {eid}")

    @classmethod
    def _semantic_arbitration_user_prompt(
        cls,
        canonical: CanonicalCase,
        preparation: SemanticPreparation,
        issues,
        requirement_targets: dict[str, list[str]],
        evidence_targets: set[str],
    ) -> str:
        """Build an authoritative source-first, field-scoped arbitration packet."""
        req_ids = {x.requirement_id for x in issues if x.requirement_id}
        evidence_ids = set(evidence_targets)
        if not req_ids and not evidence_ids:
            req_ids = {x.requirement_id for x in canonical.requirements}
            evidence_ids = {x.id for x in canonical.evidence_inventory}
        ir_by_id = {x.requirement_id: x for x in preparation.requirement_irs}
        payload = {
            "material_issues": [x.model_dump(mode="json") for x in issues],
            "requirement_patch_targets": requirement_targets,
            "evidence_replacement_targets": sorted(evidence_targets),
            "authoritative_ticket_context": {
                "ticket_id": canonical.ticket_id,
                "title": canonical.title,
                "description": canonical.description,
            },
            "authoritative_requirements": [
                {
                    "requirement_id": x.requirement_id,
                    "requirement_text": x.raw_source_text or x.requirement_text,
                }
                for x in canonical.requirements if x.requirement_id in req_ids
            ],
            "authoritative_evidence": [
                {
                    "evidence_id": x.id,
                    "evidence_class": x.evidence_class.value,
                    "source": x.source,
                    "text": x.raw_source_text or x.text,
                    "anchor": x.anchor,
                    "observation_type": x.observation_type.value,
                    "signal_name": x.signal_name,
                    "signal_value": x.signal_value,
                    "transition_from": x.transition_from,
                    "transition_to": x.transition_to,
                    "observation_group": x.observation_group,
                }
                for x in canonical.evidence_inventory if x.id in evidence_ids
            ],
            "current_ir_integration_context": [
                {
                    "requirement_id": rid,
                    "target_fields": requirement_targets[rid],
                    "current_ir_read_only": cls._compact_ir_for_structural_completion(ir_by_id[rid]),
                }
                for rid in sorted(requirement_targets) if rid in ir_by_id
            ],
            "user_instructions": list(canonical.user_instructions),
            "instruction": (
                "Resolve the listed material issues independently from the exact authoritative source. "
                "For every EXISTING compiler IR in requirement_patch_targets, return one requirement_patches entry "
                "containing ALL and ONLY its target fields. Untargeted fields must not be repeated or changed. "
                "current_ir_integration_context is read-only integration context, not semantic authority. "
                "Return a complete requirement_irs entry only when that requirement has NO existing compiler candidate. "
                "For each evidence_replacement_target, return one complete VERIFIED evidence annotation replacement. "
                "If a requested repair cannot be resolved faithfully from source, do not guess: list every corresponding "
                "material issue_id in unresolved_issue_ids."
            ),
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _rca_v080_user_prompt(packet: RCAEvidencePacket) -> str:
        return "Perform RCA synthesis using only this verified RCA Evidence Packet.\n\n" + json.dumps(packet.model_dump(mode="json"), indent=2, ensure_ascii=False)

    @staticmethod
    def _valid_rca_reference_ids(canonical: CanonicalCase, preparation: SemanticPreparation) -> set[str]:
        """Return canonical evidence IDs plus VERIFIED semantic fact IDs.

        The RCA packet exposes both ``evidence_id`` and ``fact_id``.  A hypothesis
        may therefore cite either namespace, but a fact ID is admissible only
        when it exists in a VERIFIED semantic annotation.
        """
        valid = {e.id for e in canonical.evidence_inventory}
        valid.update(
            fact.fact_id
            for ann in preparation.evidence_annotations
            for fact in ann.facts
            if fact.resolution == SemanticResolution.VERIFIED and fact.fact_id
        )
        return valid

    @classmethod
    def _merge_v080_rca(
        cls, validated: ValidatedAnalysis, canonical: CanonicalCase,
        preparation: SemanticPreparation, synthesis: RCASynthesisReasoning
    ) -> ValidatedAnalysis:
        out = copy.deepcopy(validated)
        evidence_ids = {e.id for e in canonical.evidence_inventory}
        valid_refs = cls._valid_rca_reference_ids(canonical, preparation)
        clean_hypotheses = []
        for hyp in synthesis.hypotheses:
            if not set(hyp.supporting_evidence_ids).issubset(valid_refs):
                continue
            if not set(hyp.weakening_evidence_ids).issubset(valid_refs):
                continue
            clean_hypotheses.append(copy.deepcopy(hyp))
        out.semantic.affected_functionality = synthesis.affected_functionality or out.semantic.affected_functionality
        out.semantic.historical_tickets = copy.deepcopy(synthesis.historical_tickets)
        out.semantic.diagnostic_evidence_ids = [x for x in synthesis.diagnostic_evidence_ids if x in valid_refs]
        out.semantic.hypotheses = clean_hypotheses
        out.semantic.case_validity_needs = copy.deepcopy(synthesis.case_validity_needs)
        out.hypotheses = copy.deepcopy(clean_hypotheses)
        out.case_validity_evidence = copy.deepcopy(synthesis.case_validity_needs)
        return out

    @classmethod
    def _v080_final_consistency_issues(
        cls, validated: ValidatedAnalysis, canonical: CanonicalCase, preparation: SemanticPreparation
    ):
        issues = []
        expected = [x.requirement_id for x in canonical.requirements]
        returned = [x.analysis.requirement_id for x in validated.requirement_results]
        if expected != returned:
            issues.append(ValidationIssue(code="V080_REQUIREMENT_ORDER_MISMATCH", severity=ValidationSeverity.ERROR, path="validated.requirement_results", message="Final requirement result IDs/order differ from authoritative canonical requirements."))
        valid_refs = cls._valid_rca_reference_ids(canonical, preparation)
        for idx, hyp in enumerate(validated.hypotheses):
            refs = set(hyp.supporting_evidence_ids) | set(hyp.weakening_evidence_ids)
            missing = sorted(refs - valid_refs)
            if missing:
                issues.append(ValidationIssue(code="V080_HYPOTHESIS_UNKNOWN_EVIDENCE", severity=ValidationSeverity.ERROR, path=f"validated.hypotheses[{idx}]", message="Hypothesis references unknown canonical evidence/fact IDs: " + ", ".join(missing)))
        return issues

    def _run_v071_legacy(
        self,
        raw_case: str,
        progress: Optional[ProgressCallback] = None,
        trace: Optional[TraceCallback] = None,
    ) -> PipelineResult:
        if not raw_case.strip():
            raise ValueError("Test case is empty.")

        self._check_cancelled("startup")
        progress = progress or (lambda stage, detail: None)
        trace = trace or (lambda event: None)
        stats = []
        attempts: list[PipelineAttempt] = []
        repair_log: list[RepairEvent] = []

        intake_normalization = None
        source_availability_normalization = None
        content_classification = None
        atomic_claim_extraction = None
        requirement_language_normalization = None
        rca_synthesis = None
        hypothesis_epistemic_review = None
        final_linguistic_review = None
        raw_requirement_reasoning_json = ""
        raw_rca_synthesis_json = ""
        raw_llm_json = ""

        self._emit_trace(
            trace, "01_user_input", "User Input", "complete",
            "Raw case received. Exact text is preserved for provenance.",
            input_value=raw_case, output_value="Input captured without semantic modification.",
        )

        self._check_cancelled("input routing")
        progress("Input routing", "Classifying whether source section normalization is required...")
        decision = self.intake_router.decide(
            raw_case,
            mode=self.fast_intake_mode if self.fast_intake_enabled else "off",
            fast_available=self.source_availability_client is not None and self.content_classification_client is not None,
        )
        self._emit_trace(
            trace, "02_intake_routing", "Input Classification", "complete", decision.reason,
            input_value=raw_case,
            output_value={
                "route": "DECOMPOSED_4B_INTAKE" if decision.use_fast_model else "DETERMINISTIC_DIRECT",
                "reason": decision.reason,
                "deterministic_preview_requirements": len(decision.deterministic_preview.requirements),
                "deterministic_preview_evidence": len(decision.deterministic_preview.evidence_inventory),
            },
        )

        canonical = decision.deterministic_preview
        legacy_combined_intake = False
        if decision.use_fast_model:
            # ---- 4B stage 1: source availability only ----
            self._check_cancelled("4B source availability")
            progress("4B source availability", "Classifying source presence/absence/uncertainty independently from content extraction...")
            availability_prompt = self._source_availability_user_prompt(raw_case)
            self._emit_trace(
                trace, "03_source_availability", "4B Source Availability", "running",
                "The fast model decides only PRESENT/ABSENT/UNKNOWN/NOT_MENTIONED for each source. It does not extract engineering evidence.",
                input_value={"model": getattr(self.source_availability_client, "model", ""), "system_prompt": FAST_SOURCE_AVAILABILITY_PROMPT, "user_prompt": availability_prompt},
            )
            try:
                availability_response = self.source_availability_client.structured_repair(
                    system_prompt=FAST_SOURCE_AVAILABILITY_PROMPT,
                    user_prompt=availability_prompt,
                    response_model=SourceAvailabilityNormalization,
                    schema_name="rca_fast_source_availability_v070",
                )
                stats.append(availability_response.stats)
                attempts.append(self._make_aux_attempt(
                    len(attempts) + 1, "fast_source_availability", "FAST_SOURCE_AVAILABILITY", availability_response
                ))
                if isinstance(availability_response.parsed, IntakeNormalization):
                    # Unit-test / old-client compatibility. Live v0.7 calls are schema-validated as SourceAvailabilityNormalization.
                    intake_normalization = availability_response.parsed
                    legacy_combined_intake = True
                else:
                    source_availability_normalization = availability_response.parsed
                self._emit_trace(
                    trace, "03_source_availability", "4B Source Availability", "complete",
                    "Source availability language was normalized successfully.",
                    input_value=raw_case, output_value=availability_response.parsed,
                )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts) + 1, "fast_source_availability", "FAST_SOURCE_AVAILABILITY", exc))
                if decision.deterministic_preview.requirements:
                    self._emit_trace(
                        trace, "03_source_availability", "4B Source Availability", "attention",
                        "Availability normalization failed; deterministic structured parsing remains usable and is retained.",
                        input_value=raw_case, output_value={"error": str(exc), "fallback": "deterministic preview"},
                    )
                    canonical = decision.deterministic_preview
                else:
                    raise PipelineValidationError(
                        "4B source-availability normalization failed and no deterministic requirement parse is available.\n" + str(exc),
                        canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log,
                    ) from exc

            # ---- 4B stage 2: content classification only ----
            if source_availability_normalization is not None and not legacy_combined_intake:
                self._check_cancelled("4B content classification")
                progress("4B content classification", "Extracting source-backed content while keeping headings/absence statements out of evidence blocks...")
                content_prompt = self._content_classification_user_prompt(raw_case, source_availability_normalization)
                self._emit_trace(
                    trace, "04_content_classification", "4B Content Classification", "running",
                    "The fast model extracts source-backed content categories only; source availability was already decided in the prior call.",
                    input_value={"model": getattr(self.content_classification_client, "model", ""), "system_prompt": FAST_CONTENT_CLASSIFIER_PROMPT, "user_prompt": content_prompt},
                )
                try:
                    content_response = self.content_classification_client.structured_repair(
                        system_prompt=FAST_CONTENT_CLASSIFIER_PROMPT,
                        user_prompt=content_prompt,
                        response_model=IntakeContentClassification,
                        schema_name="rca_fast_content_classification_v070",
                    )
                    stats.append(content_response.stats)
                    attempts.append(self._make_aux_attempt(
                        len(attempts) + 1, "fast_content_classification", "FAST_CONTENT_CLASSIFIER", content_response
                    ))
                    if isinstance(content_response.parsed, IntakeNormalization):
                        intake_normalization = content_response.parsed
                        legacy_combined_intake = True
                    else:
                        content_classification = content_response.parsed
                        intake_normalization = self.fast_semantic_preprocessor.combine_intake(
                            raw_case, source_availability_normalization, content_classification
                        )
                    self._emit_trace(
                        trace, "04_content_classification", "4B Content Classification", "complete",
                        "Source-backed content classification completed. Python will now assign canonical provenance and trace semantics.",
                        input_value={"availability": source_availability_normalization, "raw_case": raw_case},
                        output_value=content_response.parsed,
                    )
                except (ModelGatewayError, ValueError) as exc:
                    if isinstance(exc, ModelGatewayError):
                        stats.append(exc.stats)
                        attempts.append(self._make_failed_attempt(len(attempts) + 1, "fast_content_classification", "FAST_CONTENT_CLASSIFIER", exc))
                    if decision.deterministic_preview.requirements:
                        canonical = decision.deterministic_preview
                        self._emit_trace(
                            trace, "04_content_classification", "4B Content Classification", "attention",
                            "Content classification failed; deterministic structured parsing is retained.",
                            input_value=raw_case, output_value={"error": str(exc), "fallback": "deterministic preview"},
                        )
                    else:
                        raise PipelineValidationError(
                            "4B content classification failed and no deterministic requirement parse is available.\n" + str(exc),
                            canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log,
                        ) from exc
            else:
                self._emit_trace(
                    trace, "04_content_classification", "4B Content Classification", "skipped",
                    "Skipped because a legacy combined-intake object was supplied or source availability did not complete.",
                    input_value={"legacy_combined_intake": legacy_combined_intake}, output_value="Skipped.",
                )

            if intake_normalization is not None:
                canonical = self.intake_canonicalizer.build(raw_case, intake_normalization)
                if not canonical.requirements and decision.deterministic_preview.requirements:
                    fallback = decision.deterministic_preview
                    fallback.parser_notes.append("FAST_INTAKE_FALLBACK: decomposed 4B intake produced no source-backed requirements; deterministic parse retained.")
                    canonical = fallback
                    self._emit_trace(
                        trace, "04_content_classification", "4B Content Classification", "attention",
                        "Decomposed fast intake produced no source-backed requirements; the valid deterministic requirement preview was retained instead.",
                        input_value=intake_normalization,
                        output_value={"fallback_to_deterministic": True, "retained_requirements": len(canonical.requirements)},
                    )
        else:
            self._emit_trace(
                trace, "03_source_availability", "4B Source Availability", "skipped",
                "Input is structured enough for deterministic parsing; no source-availability language call is required.",
                input_value={"route_reason": decision.reason}, output_value="Skipped.",
            )
            self._emit_trace(
                trace, "04_content_classification", "4B Content Classification", "skipped",
                "Input is structured enough for deterministic parsing; no content-classification call is required.",
                input_value={"route_reason": decision.reason}, output_value="Skipped.",
            )

        # ---- Python canonical source/evidence construction ----
        self._check_cancelled("canonicalization")
        progress("Canonicalization", "Assigning source classes, evidence IDs, timestamps, transitions, intervals, clocks and provenance deterministically...")
        self._emit_trace(
            trace, "05_canonicalization", "Python Canonicalization", "complete",
            f"Canonical case contains {len(canonical.requirements)} requirement(s) and {len(canonical.evidence_inventory)} evidence item(s).",
            input_value=intake_normalization if intake_normalization is not None else raw_case,
            output_value=canonical,
        )
        if not canonical.requirements:
            raise PipelineValidationError(
                "No system requirements could be canonicalized. Supply explicit requirement IDs/text or enable/configure the decomposed fast intake.",
                canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log,
            )

        # ---- 4B stage 3: atomic natural-language claims ----
        if self.fast_atomic_claim_enabled and self.atomic_claim_client is not None:
            self._check_cancelled("4B atomic claim extraction")
            claim_prompt = self._atomic_claim_user_prompt(canonical)
            self._emit_trace(
                trace, "06_atomic_claims", "4B Atomic Claim Extraction", "running",
                "Natural-language observations are decomposed into atomic propositions. Python will only attach claims whose source spans map back to canonical evidence.",
                input_value={"model": getattr(self.atomic_claim_client, "model", ""), "system_prompt": FAST_ATOMIC_CLAIM_PROMPT, "user_prompt": claim_prompt},
            )
            try:
                claim_response = self.atomic_claim_client.structured_repair(
                    system_prompt=FAST_ATOMIC_CLAIM_PROMPT,
                    user_prompt=claim_prompt,
                    response_model=AtomicClaimExtractionSet,
                    schema_name="rca_fast_atomic_claims_v070",
                )
                stats.append(claim_response.stats)
                attempts.append(self._make_aux_attempt(len(attempts) + 1, "fast_atomic_claims", "FAST_ATOMIC_CLAIMS", claim_response))
                atomic_claim_extraction = claim_response.parsed
                canonical = self.fast_semantic_preprocessor.attach_atomic_claims(raw_case, canonical, atomic_claim_extraction)
                self._emit_trace(
                    trace, "06_atomic_claims", "4B Atomic Claim Extraction", "complete",
                    f"Attached {len(canonical.atomic_claims)} source-backed atomic claim(s).",
                    input_value=claim_prompt, output_value={"raw": atomic_claim_extraction, "canonical_claims": canonical.atomic_claims},
                )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts) + 1, "fast_atomic_claims", "FAST_ATOMIC_CLAIMS", exc))
                self._emit_trace(
                    trace, "06_atomic_claims", "4B Atomic Claim Extraction", "attention",
                    "Optional claim decomposition failed; canonical evidence remains unchanged.",
                    input_value=claim_prompt, output_value={"error": str(exc), "fallback": "canonical evidence retained"},
                )
        else:
            self._emit_trace(trace, "06_atomic_claims", "4B Atomic Claim Extraction", "skipped", "Atomic claim extraction is disabled or no fast model is configured.", output_value="Skipped.")

        # ---- 4B stage 4: requirement-language normalization ----
        if self.fast_requirement_language_enabled and self.requirement_language_client is not None:
            self._check_cancelled("4B requirement language normalization")
            req_lang_prompt = self._requirement_language_user_prompt(canonical)
            self._emit_trace(
                trace, "07_requirement_language", "4B Requirement Language Normalization", "running",
                "Requirement grammar is normalized into structured predicate/trigger/behavior hints. Original requirement text remains authoritative.",
                input_value={"model": getattr(self.requirement_language_client, "model", ""), "system_prompt": FAST_REQUIREMENT_LANGUAGE_PROMPT, "user_prompt": req_lang_prompt},
            )
            try:
                req_lang_response = self.requirement_language_client.structured_repair(
                    system_prompt=FAST_REQUIREMENT_LANGUAGE_PROMPT,
                    user_prompt=req_lang_prompt,
                    response_model=RequirementLanguageNormalizationSet,
                    schema_name="rca_fast_requirement_language_v070",
                )
                stats.append(req_lang_response.stats)
                attempts.append(self._make_aux_attempt(len(attempts) + 1, "fast_requirement_language", "FAST_REQUIREMENT_LANGUAGE", req_lang_response))
                requirement_language_normalization = req_lang_response.parsed
                canonical = self.fast_semantic_preprocessor.attach_requirement_language(canonical, requirement_language_normalization)
                self._emit_trace(
                    trace, "07_requirement_language", "4B Requirement Language Normalization", "complete",
                    f"Retained {len(canonical.requirement_language)} grounded requirement-language normalization object(s).",
                    input_value=req_lang_prompt, output_value={"raw": requirement_language_normalization, "canonical_hints": canonical.requirement_language},
                )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts) + 1, "fast_requirement_language", "FAST_REQUIREMENT_LANGUAGE", exc))
                self._emit_trace(
                    trace, "07_requirement_language", "4B Requirement Language Normalization", "attention",
                    "Optional requirement-language normalization failed; Phase A will reason from authoritative requirement text directly.",
                    input_value=req_lang_prompt, output_value={"error": str(exc), "fallback": "original requirement text"},
                )
        else:
            self._emit_trace(trace, "07_requirement_language", "4B Requirement Language Normalization", "skipped", "Requirement-language normalization is disabled or no fast model is configured.", output_value="Skipped.")

        # ---- 27B Phase A: requirement reasoning, chunked for large cases ----
        self._check_cancelled("27B Phase A requirement reasoning")
        chunks = self._build_requirement_chunks(canonical)
        large_case = len(canonical.requirements) >= self.primary_large_case_requirement_threshold
        phase_a_budget = self.primary_large_case_max_tokens if large_case else None
        self._emit_trace(
            trace, "08_phase_a_requirement_reasoning", "27B Phase A — Requirement Reasoning", "running",
            f"Analyzing requirement meaning/applicability/evidence only in {len(chunks)} chunk(s). RCA hypotheses and historical synthesis are excluded from this phase.",
            input_value={
                "model": getattr(self.client, "model", ""),
                "system_prompt": REQUIREMENT_REASONING_PROMPT,
                "chunks": chunks,
                "large_case": large_case,
                "max_tokens_override": phase_a_budget,
            },
        )
        phase_a_requirements = []
        phase_a_raw = []
        legacy_synthesis = None
        for chunk_index, req_ids in enumerate(chunks, start=1):
            self._check_cancelled(f"27B Phase A chunk {chunk_index}")
            chunk_prompt = self._phase_a_user_prompt(canonical, req_ids)
            chunk_id = f"08_phase_a_chunk_{chunk_index}"
            self._emit_trace(
                trace, chunk_id, f"27B Phase A / Chunk {chunk_index}", "running",
                f"Reasoning over {len(req_ids)} requirement(s): {', '.join(req_ids)}.",
                input_value={"system_prompt": REQUIREMENT_REASONING_PROMPT, "user_prompt": chunk_prompt, "max_tokens_override": phase_a_budget},
            )
            try:
                response = self.client.structured_chat(
                    system_prompt=REQUIREMENT_REASONING_PROMPT,
                    user_prompt=chunk_prompt,
                    response_model=RequirementReasoningPhase,
                    schema_name="rca_requirement_reasoning_phase_a_v070",
                    max_tokens_override=phase_a_budget,
                )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts) + 1, f"phase_a_chunk_{chunk_index}", "PRIMARY_REQUIREMENT_REASONING", exc))
                self._emit_trace(
                    trace, chunk_id, f"27B Phase A / Chunk {chunk_index}", "failed",
                    "Primary requirement-reasoning structured output failed after bounded recovery.",
                    input_value=chunk_prompt,
                    output_value={"error": str(exc), "finish_reason": exc.finish_reason, "reasoning_content": exc.reasoning_content, "raw_response": exc.raw_api_response or exc.raw_json},
                )
                raise PipelineValidationError(
                    "27B Phase A requirement reasoning failed after structured-output recovery attempts.\n" + str(exc),
                    canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log,
                ) from exc
            stats.append(response.stats)
            attempts.append(self._make_aux_attempt(len(attempts) + 1, f"phase_a_chunk_{chunk_index}", "PRIMARY_REQUIREMENT_REASONING", response))
            raw_llm_json = response.raw_json
            phase_a_raw.append(response.raw_json)
            if isinstance(response.parsed, SemanticReasoning):
                # Compatibility for existing unit-test clients / saved adapters.
                parsed_requirements = response.parsed.requirements
                if legacy_synthesis is None:
                    legacy_synthesis = RCASynthesisReasoning(
                        affected_functionality=response.parsed.affected_functionality,
                        historical_tickets=response.parsed.historical_tickets,
                        diagnostic_evidence_ids=response.parsed.diagnostic_evidence_ids,
                        hypotheses=response.parsed.hypotheses,
                        case_validity_needs=response.parsed.case_validity_needs,
                    )
            else:
                parsed_requirements = response.parsed.requirements
            returned = {r.requirement_id for r in parsed_requirements}
            expected = set(req_ids)
            if returned != expected:
                raise PipelineValidationError(
                    f"27B Phase A chunk {chunk_index} returned wrong requirement IDs: missing={sorted(expected-returned)}, extra={sorted(returned-expected)}",
                    canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log,
                )
            phase_a_requirements.extend(copy.deepcopy(parsed_requirements))
            self._emit_trace(
                trace, chunk_id, f"27B Phase A / Chunk {chunk_index}", "complete",
                f"Requirement reasoning chunk completed in {response.stats.elapsed_seconds:.1f} s.",
                input_value=chunk_prompt,
                output_value={"structured_json": response.raw_json, "reasoning_content": response.reasoning_content, "finish_reason": response.finish_reason, "stats": response.stats.model_dump(mode="json")},
            )

        raw_requirement_reasoning_json = "[" + ",\n".join(phase_a_raw) + "]" if len(phase_a_raw) > 1 else (phase_a_raw[0] if phase_a_raw else "")
        phase_a_semantic = self._merge_phase_a_requirements(canonical, phase_a_requirements)
        phase_a_semantic = self.fast_semantic_preprocessor.apply_requirement_language_hints(
            phase_a_semantic, canonical
        )
        self._emit_trace(
            trace, "08_phase_a_requirement_reasoning", "27B Phase A — Requirement Reasoning", "complete",
            "All Phase-A requirement chunks completed. No RCA hypothesis has been accepted yet.",
            input_value={"chunks": chunks}, output_value=phase_a_semantic,
        )

        # Requirement validation deliberately defers historical-ticket accounting to Phase B.
        phase_a_canonical = copy.deepcopy(canonical)
        phase_a_canonical.historical_text = ""
        self._check_cancelled("requirement validation")
        progress("Requirement validation", "Validating applicability, evidence mapping, state/transition/interval semantics and deterministic timing...")
        phase_a_validated = self.validator.normalize_and_validate(phase_a_semantic, canonical_case=phase_a_canonical)
        # Preserve the v0.6.x observability contract: the primary requirement-reasoning
        # attempts carry the validation issues discovered immediately after Phase A.
        for attempt in attempts:
            if attempt.stage.startswith("phase_a_chunk_"):
                attempt.semantic_before_validation_json = json.dumps(phase_a_semantic.model_dump(mode="json"), indent=2, ensure_ascii=False)
                attempt.normalized_semantic_json = json.dumps(phase_a_validated.semantic.model_dump(mode="json"), indent=2, ensure_ascii=False)
                attempt.validation_issues = copy.deepcopy(phase_a_validated.issues)
        phase_a_critical = self.validator.critical_issues(phase_a_validated)
        self._emit_trace(
            trace, "09_requirement_validation", "Python Requirement Validation", "complete" if not phase_a_critical else "attention",
            f"Phase-A validation produced {len(phase_a_validated.issues)} issue(s), including {len(phase_a_critical)} critical error(s).",
            input_value=phase_a_semantic, output_value=phase_a_validated,
        )

        phase_a_validated, phase_a_repaired, repair_raw = self._run_requirement_repair_loop(
            phase_a_validated, phase_a_canonical, progress, trace, attempts, stats, repair_log,
            stage_id="10_requirement_repair", stage_title="Requirement Repair / 27B Arbitration",
        )
        if repair_raw:
            raw_llm_json = repair_raw
        repair_performed = phase_a_repaired

        authoritative_requirements = phase_a_validated
        self._emit_trace(
            trace, "11_authoritative_compliance", "Authoritative Compliance State", "complete",
            "Requirement applicability/verdicts and deterministic timing facts are now authoritative inputs to RCA synthesis.",
            input_value=authoritative_requirements.semantic,
            output_value={
                "requirement_results": [x.model_dump(mode="json") for x in authoritative_requirements.requirement_results],
                "compliance_evidence": authoritative_requirements.compliance_evidence,
                "evidence_conflicts": [x.model_dump(mode="json") for x in authoritative_requirements.evidence_conflicts],
            },
        )

        # ---- 27B Phase B: RCA synthesis only ----
        if legacy_synthesis is not None:
            rca_synthesis = legacy_synthesis
            self._emit_trace(
                trace, "12_phase_b_rca_synthesis", "27B Phase B — RCA Synthesis", "skipped",
                "Legacy test/client response already carried Phase-B fields; reused only for backward-compatible tests/adapters.",
                input_value=legacy_synthesis, output_value=legacy_synthesis,
            )
        else:
            self._check_cancelled("27B Phase B RCA synthesis")
            progress("RCA synthesis", "Calling the primary model for historical/diagnostic comparison and evidence-backed candidate mechanisms only...")
            phase_b_prompt = self._phase_b_user_prompt(canonical, authoritative_requirements)
            self._emit_trace(
                trace, "12_phase_b_rca_synthesis", "27B Phase B — RCA Synthesis", "running",
                "The primary model receives Python-validated requirement results as read-only facts and may only synthesize RCA context/hypotheses.",
                input_value={"model": getattr(self.client, "model", ""), "system_prompt": RCA_SYNTHESIS_PROMPT, "user_prompt": phase_b_prompt},
            )
            try:
                phase_b_response = self.client.structured_chat(
                    system_prompt=RCA_SYNTHESIS_PROMPT,
                    user_prompt=phase_b_prompt,
                    response_model=RCASynthesisReasoning,
                    schema_name="rca_phase_b_synthesis_v070",
                )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts) + 1, "phase_b_rca_synthesis", "PRIMARY_RCA_SYNTHESIS", exc, authoritative_requirements.semantic, authoritative_requirements))
                self._emit_trace(
                    trace, "12_phase_b_rca_synthesis", "27B Phase B — RCA Synthesis", "failed",
                    "Primary RCA synthesis structured output failed after bounded recovery.",
                    input_value=phase_b_prompt, output_value={"error": str(exc), "raw_response": exc.raw_api_response or exc.raw_json, "reasoning_content": exc.reasoning_content},
                )
                raise PipelineValidationError(
                    "27B Phase B RCA synthesis failed after structured-output recovery attempts.\n" + str(exc),
                    validated=authoritative_requirements, canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log,
                ) from exc
            stats.append(phase_b_response.stats)
            attempts.append(self._make_aux_attempt(len(attempts) + 1, "phase_b_rca_synthesis", "PRIMARY_RCA_SYNTHESIS", phase_b_response, authoritative_requirements.semantic, authoritative_requirements))
            rca_synthesis = phase_b_response.parsed
            raw_rca_synthesis_json = phase_b_response.raw_json
            raw_llm_json = phase_b_response.raw_json
            self._emit_trace(
                trace, "12_phase_b_rca_synthesis", "27B Phase B — RCA Synthesis", "complete",
                f"Case-level RCA synthesis completed in {phase_b_response.stats.elapsed_seconds:.1f} s without modifying requirement truth.",
                input_value=phase_b_prompt,
                output_value={"structured_json": phase_b_response.raw_json, "reasoning_content": phase_b_response.reasoning_content, "stats": phase_b_response.stats.model_dump(mode="json")},
            )

        combined_semantic = self._merge_rca_synthesis(authoritative_requirements.semantic, canonical, rca_synthesis)
        validated = self.validator.normalize_and_validate(combined_semantic, canonical_case=canonical)
        validated, phase_b_repaired, phase_b_repair_raw, rca_synthesis = self._run_phase_b_repair_loop(
            validated, authoritative_requirements, canonical, rca_synthesis, progress, trace, attempts, stats, repair_log
        )
        repair_performed = repair_performed or phase_b_repaired
        if phase_b_repair_raw:
            raw_llm_json = phase_b_repair_raw
            raw_rca_synthesis_json = phase_b_repair_raw

        # ---- 4B hypothesis epistemic review ----
        if self.fast_hypothesis_review_enabled and self.hypothesis_review_client is not None and validated.semantic.hypotheses:
            self._check_cancelled("4B hypothesis epistemic review")
            hyp_payload = self.hypothesis_review_gate.payload(validated)
            hyp_prompt = self._hypothesis_review_user_prompt(hyp_payload)
            self._emit_trace(
                trace, "14_hypothesis_review", "4B Hypothesis Epistemic Review", "running",
                "The fast model classifies hypothesis language as mechanism candidate, compliance restatement, root-cause claim, or evidence summary. Python applies only index-matched actions.",
                input_value={"model": getattr(self.hypothesis_review_client, "model", ""), "system_prompt": FAST_HYPOTHESIS_REVIEW_PROMPT, "user_prompt": hyp_prompt},
            )
            try:
                hyp_response = self.hypothesis_review_client.structured_repair(
                    system_prompt=FAST_HYPOTHESIS_REVIEW_PROMPT,
                    user_prompt=hyp_prompt,
                    response_model=HypothesisReviewResponse,
                    schema_name="rca_fast_hypothesis_epistemic_review_v070",
                )
                stats.append(hyp_response.stats)
                attempts.append(self._make_aux_attempt(len(attempts) + 1, "fast_hypothesis_epistemic_review", "FAST_HYPOTHESIS_REVIEW", hyp_response, validated.semantic, validated))
                hypothesis_epistemic_review = hyp_response.parsed
                validated, accepted_hyp_actions, rejected_hyp_actions = self.hypothesis_review_gate.apply(
                    validated, hypothesis_epistemic_review, self.validator, canonical
                )
                self._emit_trace(
                    trace, "14_hypothesis_review", "4B Hypothesis Epistemic Review", "complete" if not rejected_hyp_actions else "attention",
                    f"Hypothesis review completed; {len(accepted_hyp_actions)} action(s) accepted by Python.",
                    input_value=hyp_payload,
                    output_value={"review": hypothesis_epistemic_review, "accepted_actions": accepted_hyp_actions, "rejected_actions": rejected_hyp_actions},
                )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts) + 1, "fast_hypothesis_epistemic_review", "FAST_HYPOTHESIS_REVIEW", exc, validated.semantic, validated))
                self._emit_trace(
                    trace, "14_hypothesis_review", "4B Hypothesis Epistemic Review", "attention",
                    "Optional hypothesis-language review failed; deterministic validated hypotheses are retained.",
                    input_value=hyp_payload, output_value={"error": str(exc), "fallback": "validated hypotheses retained"},
                )
        else:
            self._emit_trace(
                trace, "14_hypothesis_review", "4B Hypothesis Epistemic Review", "skipped",
                "No hypotheses require review, the review is disabled, or no fast model is configured.",
                input_value={"hypothesis_count": len(validated.semantic.hypotheses), "enabled": self.fast_hypothesis_review_enabled}, output_value="Skipped.",
            )

        # ---- existing structured final requirement wording review ----
        if self.fast_final_review_enabled and self.final_review_client is not None:
            self._check_cancelled("4B final consistency review")
            review_payload = self.linguistic_review_gate.compact_payload(validated)
            review_prompt = self._final_review_user_prompt(review_payload)
            self._emit_trace(
                trace, "15_final_wording_review", "4B Final Wording Review", "running",
                "The fast model extracts relevance/sufficiency/verdict claims from analyst-facing requirement wording. It cannot change facts.",
                input_value={"model": getattr(self.final_review_client, "model", ""), "system_prompt": FAST_FINAL_REVIEW_PROMPT, "user_prompt": review_prompt, "authoritative_payload": review_payload},
            )
            try:
                review_response = self.final_review_client.structured_repair(
                    system_prompt=FAST_FINAL_REVIEW_PROMPT,
                    user_prompt=review_prompt,
                    response_model=LinguisticReviewResponse,
                    schema_name="rca_fast_final_linguistic_review_v070",
                )
                stats.append(review_response.stats)
                final_linguistic_review = review_response.parsed
                attempts.append(self._make_aux_attempt(len(attempts) + 1, "fast_final_linguistic_review", "FAST_FINAL_REVIEW", review_response, validated.semantic, validated))
                reviewed, accepted_patches, rejected_patches = self.linguistic_review_gate.apply(validated, final_linguistic_review, canonical, self.validator)
                validated = reviewed
                self._emit_trace(
                    trace, "15_final_wording_review", "4B Final Wording Review", "complete" if not rejected_patches else "attention",
                    f"Structured wording review completed; {len(accepted_patches)} relevance patch(es) accepted by Python.",
                    input_value=review_payload,
                    output_value={"review": final_linguistic_review, "accepted_relevance_patches": accepted_patches, "rejected_patches": rejected_patches},
                )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts) + 1, "fast_final_linguistic_review", "FAST_FINAL_REVIEW", exc, validated.semantic, validated))
                fallback_client = self._build_nonthinking_final_review_fallback(exc)
                if fallback_client is not None:
                    try:
                        fallback_response = fallback_client.structured_repair(
                            system_prompt=FAST_FINAL_REVIEW_PROMPT,
                            user_prompt=review_prompt,
                            response_model=LinguisticReviewResponse,
                            schema_name="rca_fast_final_linguistic_review_v070_fallback",
                        )
                        stats.append(fallback_response.stats)
                        final_linguistic_review = fallback_response.parsed
                        attempts.append(self._make_aux_attempt(len(attempts) + 1, "fast_final_linguistic_review_fallback", "FAST_FINAL_REVIEW_FALLBACK", fallback_response, validated.semantic, validated))
                        validated, accepted_patches, rejected_patches = self.linguistic_review_gate.apply(validated, final_linguistic_review, canonical, self.validator)
                        self._emit_trace(
                            trace, "15_final_wording_review", "4B Final Wording Review", "complete" if not rejected_patches else "attention",
                            "Configured review exhausted structured output; recovered once through the proven non-thinking Qwen3.5 path.",
                            input_value=review_payload,
                            output_value={"initial_error": str(exc), "review": final_linguistic_review, "accepted_relevance_patches": accepted_patches, "rejected_patches": rejected_patches},
                        )
                    except ModelGatewayError as fallback_exc:
                        stats.append(fallback_exc.stats)
                        attempts.append(self._make_failed_attempt(len(attempts) + 1, "fast_final_linguistic_review_fallback", "FAST_FINAL_REVIEW_FALLBACK", fallback_exc, validated.semantic, validated))
                        self._emit_trace(
                            trace, "15_final_wording_review", "4B Final Wording Review", "attention",
                            "Both configured review and bounded non-thinking recovery failed; validated semantics are retained.",
                            input_value=review_payload, output_value={"initial_error": str(exc), "fallback_error": str(fallback_exc)},
                        )
                else:
                    self._emit_trace(
                        trace, "15_final_wording_review", "4B Final Wording Review", "attention",
                        "Optional wording review failed; validated semantics are retained.",
                        input_value=review_payload, output_value={"error": str(exc)},
                    )
        else:
            self._emit_trace(trace, "15_final_wording_review", "4B Final Wording Review", "skipped", "Final wording review is disabled or no fast model is configured.", output_value="Skipped.")

        # ---- Python final gate + deterministic report ----
        self._check_cancelled("Python final gate")
        final_gated = self.validator.normalize_and_validate(validated.semantic, canonical_case=canonical)
        final_critical = self.validator.critical_issues(final_gated)
        if final_critical:
            self._emit_trace(
                trace, "16_python_final_gate", "Python Final Gate", "failed",
                f"Final gate found {len(final_critical)} critical error(s); no report will be emitted.",
                input_value=validated, output_value={"critical_issues": [x.model_dump(mode="json") for x in final_critical]},
            )
            details = "\n".join(f"[{x.code}] {x.path}: {x.message}" for x in final_critical)
            raise PipelineValidationError(
                "Python final gate rejected the post-review structured result.\n" + details,
                validated=final_gated, canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log,
            )
        validated = final_gated
        self._emit_trace(
            trace, "16_python_final_gate", "Python Final Gate", "complete",
            "Final deterministic revalidation passed; no LLM owns the compliance truth.",
            input_value=validated.semantic,
            output_value={"requirement_results": [x.model_dump(mode="json") for x in validated.requirement_results], "hypotheses": [x.model_dump(mode="json") for x in validated.hypotheses]},
        )

        self._check_cancelled("final report formatter")
        progress("Final report formatter", "Generating the 11-section analyst report from validated structured data...")
        self._emit_trace(trace, "17_report_formatter", "11-Section Report Formatter", "running", "Formatting only validated structured data; no additional model reasoning occurs.", input_value=validated)
        report = self.formatter.format(validated)
        self._emit_trace(trace, "17_report_formatter", "11-Section Report Formatter", "complete", "The deterministic 11-section RCA report has been generated.", input_value=validated, output_value=report)
        progress("Complete", "Analysis completed and passed deterministic validation.")
        self._emit_trace(
            trace, "18_final_output", "Final Output", "complete",
            "Validated v0.7.1 RCA analysis is ready for session export.",
            input_value={"validated_requirements": len(validated.requirement_results), "repair_performed": repair_performed, "llm_calls": len(stats)},
            output_value=report,
        )
        self._check_cancelled("final output")

        return PipelineResult(
            canonical_case=canonical,
            intake_normalization=intake_normalization,
            source_availability_normalization=source_availability_normalization,
            content_classification=content_classification,
            atomic_claim_extraction=atomic_claim_extraction,
            requirement_language_normalization=requirement_language_normalization,
            rca_synthesis=rca_synthesis,
            hypothesis_epistemic_review=hypothesis_epistemic_review,
            final_linguistic_review=final_linguistic_review,
            validated=validated,
            final_report=report,
            raw_semantic_json=json.dumps(validated.semantic.model_dump(mode="json"), indent=2, ensure_ascii=False),
            raw_llm_json=raw_llm_json,
            raw_requirement_reasoning_json=raw_requirement_reasoning_json,
            raw_rca_synthesis_json=raw_rca_synthesis_json,
            stats=stats,
            repair_performed=repair_performed,
            attempts=attempts,
            repair_log=repair_log,
        )

    def _run_requirement_repair_loop(self, validated, canonical, progress, trace, attempts, stats, repair_log, *, stage_id: str, stage_title: str):
        """Preserve the v0.6.x deterministic/4B/27B repair architecture for Phase A only."""
        critical = self.validator.critical_issues(validated)
        repair_performed = False
        last_raw = ""
        force_primary: set[tuple] = set()
        if not critical:
            self._emit_trace(trace, stage_id, stage_title, "skipped", "No critical requirement-validation errors require repair.", input_value={"critical_issues": []}, output_value="No repair performed.")
            return validated, False, ""
        if self.max_repair_passes == 0:
            self._emit_trace(trace, stage_id, stage_title, "skipped", "Critical errors exist, but repair rounds are disabled.", input_value={"critical_issues": [x.model_dump(mode="json") for x in critical]}, output_value="No repair attempted.")
        for repair_round in range(1, self.max_repair_passes + 1):
            if not critical:
                break
            actions = 0
            round_start_signature = self._critical_signature(critical)
            while critical and actions < MAX_REPAIR_ACTIONS_PER_ROUND:
                self._check_cancelled(f"requirement repair round {repair_round}")
                actionable = [x for x in critical if not x.path.startswith("validated.")]
                if not actionable:
                    break
                plan = self.repair_router.build_plan(validated.semantic, actionable, fast_model_available=self.repair_client is not None)
                if not plan:
                    break
                task = plan[0]
                native_primary_batch = list(plan) if task.route == RepairRoute.PRIMARY_MODEL else []
                if task.route == RepairRoute.DETERMINISTIC and not self.deterministic_repair_enabled:
                    task = RepairTask(requirement_id=task.requirement_id, route=RepairRoute.PRIMARY_MODEL, allowed_fields=[], issues=task.issues, instructions=["Deterministic repair is disabled; escalate to 27B semantic arbitration."])
                elif task.route == RepairRoute.DETERMINISTIC and task.signature in force_primary:
                    task = RepairTask(requirement_id=task.requirement_id, route=RepairRoute.PRIMARY_MODEL, allowed_fields=[], issues=task.issues, instructions=["Deterministic repair could not mechanically change the target; escalate the same defect to 27B semantic arbitration."])
                elif task.route == RepairRoute.FAST_MODEL and task.signature in force_primary:
                    task = RepairTask(requirement_id=task.requirement_id, route=RepairRoute.PRIMARY_MODEL, allowed_fields=[], issues=task.issues, instructions=["Fast repair did not clear the same defect; escalate to 27B semantic arbitration."])
                actions += 1
                repair_performed = True
                trace_id = f"{stage_id}_r{repair_round}_a{actions}"
                self._emit_trace(trace, trace_id, f"{stage_title} / Round {repair_round} Action {actions}", "running", f"Route: {task.route.value}; target={task.requirement_id or 'global'}; issues={', '.join(task.issue_codes)}.", input_value={"task": {"route": task.route.value, "requirement_id": task.requirement_id, "issue_codes": task.issue_codes, "allowed_fields": task.allowed_fields}})
                before_semantic = copy.deepcopy(validated.semantic)
                before_signature = task.signature
                try:
                    if task.route == RepairRoute.DETERMINISTIC:
                        validated, critical, event = self._run_deterministic_task(task, validated, canonical, repair_round, actions, progress)
                        response = None
                        if event.outcome == "NO_CHANGE" and self.fallback_to_primary_repair:
                            force_primary.add(before_signature)
                    elif task.route == RepairRoute.FAST_MODEL and self.repair_client is not None:
                        validated, critical, response, event = self._run_fast_patch_task(task, validated, canonical, repair_round, actions, progress, attempts, stats)
                        if self._task_still_present(task, validated.semantic, critical) and self.fallback_to_primary_repair:
                            force_primary.add(before_signature)
                    else:
                        if native_primary_batch:
                            validated, critical, response, event = self._run_primary_tasks(native_primary_batch, validated, canonical, repair_round, actions, progress, attempts, stats)
                        else:
                            validated, critical, response, event = self._run_primary_task(task, validated, canonical, repair_round, actions, progress, attempts, stats)
                    if response is not None:
                        last_raw = response.raw_json
                except ModelGatewayError as exc:
                    stats.append(exc.stats)
                    attempts.append(self._make_failed_attempt(len(attempts) + 1, f"{stage_id}_r{repair_round}_a{actions}", "REPAIR_MODEL", exc, validated.semantic, validated))
                    raise PipelineValidationError(
                        f"{stage_title} model call failed after structured-output recovery attempts.\n{exc}",
                        validated=validated, canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log,
                    ) from exc
                repair_log.append(event)
                self._emit_trace(trace, trace_id, f"{stage_title} / Round {repair_round} Action {actions}", "complete" if not critical else "attention", f"{event.route.value} repair finished; {len(critical)} critical issue(s) remain.", output_value={"repair_event": event.model_dump(mode="json"), "remaining_critical_issues": [x.model_dump(mode="json") for x in critical]})
                if not critical:
                    break
                if (
                    before_semantic.model_dump(mode="json") == validated.semantic.model_dump(mode="json")
                    and self._critical_signature(critical) == self._critical_signature(actionable)
                    and before_signature not in force_primary
                ):
                    break
            if not critical:
                break
            if self._critical_signature(critical) == round_start_signature and actions == 0:
                break
        critical = self.validator.critical_issues(validated)
        if critical:
            self._emit_trace(trace, stage_id, stage_title, "failed", f"{len(critical)} critical requirement error(s) remain after repair/arbitration.", input_value=validated.semantic, output_value={"critical_issues": [x.model_dump(mode="json") for x in critical]})
            details = "\n".join(f"[{x.code}] {x.path}: {x.message}" for x in critical)
            raise PipelineValidationError(
                "Critical requirement validation errors remain after configured repair rounds.\n" + details,
                validated=validated, canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log,
            )
        self._emit_trace(trace, stage_id, stage_title, "complete", "All critical requirement errors are cleared. Any 27B call here acts as conditional semantic arbitration, not a new RCA synthesis.", input_value=validated.semantic, output_value={"requirement_results": [x.model_dump(mode="json") for x in validated.requirement_results]})
        return validated, repair_performed, last_raw

    def _run_phase_b_repair_loop(self, validated, authoritative_requirements, canonical, synthesis, progress, trace, attempts, stats, repair_log):
        """Repair Phase-B-only RCA synthesis without allowing requirement mutation."""
        critical = self.validator.critical_issues(validated)
        repaired = False
        last_raw = ""
        if not critical:
            self._emit_trace(trace, "13_rca_validation_repair", "Python RCA Validation / Phase-B Repair", "complete", "RCA synthesis passed deterministic source/hypothesis validation without repair.", input_value=validated.semantic, output_value=validated)
            return validated, False, "", synthesis
        if self.max_repair_passes == 0:
            details = "\n".join(f"[{x.code}] {x.path}: {x.message}" for x in critical)
            raise PipelineValidationError("Critical Phase-B validation errors remain and repair is disabled.\n" + details, validated=validated, canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log)
        for repair_round in range(1, self.max_repair_passes + 1):
            if not critical:
                break
            self._check_cancelled(f"Phase-B repair round {repair_round}")
            repaired = True
            repair_prompt = self._phase_b_repair_user_prompt(canonical, authoritative_requirements, synthesis, critical)
            trace_id = f"13_rca_repair_r{repair_round}"
            self._emit_trace(trace, trace_id, f"27B Phase-B Repair / Round {repair_round}", "running", "Repairing only historical/diagnostic/hypothesis/case-validity synthesis fields; authoritative requirements are read-only.", input_value=repair_prompt)
            try:
                response = self.client.structured_chat(
                    system_prompt=RCA_SYNTHESIS_PROMPT + "\n\nREPAIR MODE: Correct only the Phase-B synthesis fields implicated by the supplied validation errors. Authoritative requirement results are immutable.",
                    user_prompt=repair_prompt,
                    response_model=RCASynthesisReasoning,
                    schema_name="rca_phase_b_synthesis_repair_v070",
                )
            except ModelGatewayError as exc:
                stats.append(exc.stats)
                attempts.append(self._make_failed_attempt(len(attempts) + 1, f"phase_b_repair_r{repair_round}", "PRIMARY_RCA_SYNTHESIS_REPAIR", exc, validated.semantic, validated))
                raise PipelineValidationError("Phase-B RCA synthesis repair failed.\n" + str(exc), validated=validated, canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log) from exc
            stats.append(response.stats)
            attempts.append(self._make_aux_attempt(len(attempts) + 1, f"phase_b_repair_r{repair_round}", "PRIMARY_RCA_SYNTHESIS_REPAIR", response, validated.semantic, validated))
            synthesis = response.parsed
            last_raw = response.raw_json
            semantic = self._merge_rca_synthesis(authoritative_requirements.semantic, canonical, synthesis)
            validated = self.validator.normalize_and_validate(semantic, canonical_case=canonical)
            critical = self.validator.critical_issues(validated)
            repair_log.append(RepairEvent(
                pass_index=repair_round, route=RepairRoute.PRIMARY_MODEL,
                issue_codes=sorted({x.code for x in critical}) if critical else [], requirement_ids=[],
                model=response.stats.model, elapsed_seconds=response.stats.elapsed_seconds,
                outcome="PASS" if not critical else "REVALIDATED",
                details="27B Phase-B synthesis repair; requirement analyses were not writable.",
            ))
            self._emit_trace(trace, trace_id, f"27B Phase-B Repair / Round {repair_round}", "complete" if not critical else "attention", f"Phase-B revalidation completed; {len(critical)} critical issue(s) remain.", output_value={"synthesis": synthesis, "critical_issues": [x.model_dump(mode="json") for x in critical]})
        if critical:
            self._emit_trace(trace, "13_rca_validation_repair", "Python RCA Validation / Phase-B Repair", "failed", f"{len(critical)} critical Phase-B error(s) remain.", output_value={"critical_issues": [x.model_dump(mode="json") for x in critical]})
            details = "\n".join(f"[{x.code}] {x.path}: {x.message}" for x in critical)
            raise PipelineValidationError("Critical Phase-B validation errors remain after configured repair rounds.\n" + details, validated=validated, canonical_case=canonical, attempts=attempts, stats=stats, repair_log=repair_log)
        self._emit_trace(trace, "13_rca_validation_repair", "Python RCA Validation / Phase-B Repair", "complete", "RCA synthesis is source-accounted and hypothesis-safe; authoritative requirement results remain unchanged.", input_value=validated.semantic, output_value=validated)
        return validated, repaired, last_raw, synthesis

    @staticmethod
    def _source_availability_user_prompt(raw_case: str) -> str:
        return (
            "Classify source availability only. For ABSENT/UNKNOWN copy the exact supporting phrase into availability_statement.source_span. "
            "Do not extract content or perform RCA reasoning.\n\nRAW INPUT:\n" + raw_case
        )

    @staticmethod
    def _content_classification_user_prompt(raw_case: str, availability: SourceAvailabilityNormalization) -> str:
        return (
            "Extract source-backed content according to the already-decided availability metadata. Exclude bare section headings and do not turn absence/uncertainty statements into engineering blocks. "
            "Every source_span must be verbatim.\n\nSOURCE AVAILABILITY:\n"
            + json.dumps(availability.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
            + "\n\nRAW INPUT:\n" + raw_case
        )

    @staticmethod
    def _atomic_claim_user_prompt(canonical: CanonicalCase) -> str:
        natural = []
        for e in canonical.evidence_inventory:
            if e.evidence_class.value in {"REPORTED_OBSERVATION", "HISTORICAL_EVIDENCE", "CURRENT_TICKET"} or e.source == "Current BZD / Diagnostics":
                natural.append({
                    "source_category": e.evidence_class.value if e.source != "Current BZD / Diagnostics" else "DIAGNOSTIC",
                    "text": e.text,
                    "raw_source_text": e.raw_source_text or e.text,
                })
        return (
            "Decompose only the supplied natural-language sources into faithful atomic claims. Do not process deterministic trace assignments. "
            "source_span must be verbatim from the supplied source text.\n\nSOURCES:\n"
            + json.dumps(natural, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _requirement_language_user_prompt(canonical: CanonicalCase) -> str:
        return (
            "Normalize each requirement into non-authoritative structured language hints. Preserve nested logic in DNF and do not make applicability/compliance decisions.\n\nREQUIREMENTS:\n"
            + json.dumps([r.model_dump(mode="json") for r in canonical.requirements], ensure_ascii=False, separators=(",", ":"))
        )

    def _build_requirement_chunks(self, canonical: CanonicalCase) -> list[list[str]]:
        ids = [r.requirement_id for r in canonical.requirements]
        if len(ids) < self.primary_large_case_requirement_threshold:
            return [ids]
        # Structural relation graph only: if one canonical requirement explicitly
        # names another requirement ID, keep that connected component together.
        parent = {rid: rid for rid in ids}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        id_set = set(ids)
        by_id = {r.requirement_id: r for r in canonical.requirements}
        for rid, req in by_id.items():
            for token in re.findall(r"\b[A-Za-z]+-\d+[A-Za-z0-9_-]*\b", req.requirement_text or ""):
                if token in id_set and token != rid:
                    union(rid, token)
        components = []
        seen_roots = []
        for rid in ids:
            root = find(rid)
            if root not in seen_roots:
                seen_roots.append(root)
                components.append([x for x in ids if find(x) == root])
        chunks: list[list[str]] = []
        current: list[str] = []
        for comp in components:
            if current and len(current) + len(comp) > self.primary_phase_a_chunk_size:
                chunks.append(current)
                current = []
            if len(comp) > self.primary_phase_a_chunk_size:
                if current:
                    chunks.append(current)
                    current = []
                chunks.append(comp)
            else:
                current.extend(comp)
        if current:
            chunks.append(current)
        return chunks or [ids]

    @staticmethod
    def _phase_a_user_prompt(canonical: CanonicalCase, req_ids: list[str]) -> str:
        wanted = set(req_ids)
        payload = {
            "requirements": [r.model_dump(mode="json") for r in canonical.requirements if r.requirement_id in wanted],
            "evidence_inventory": [e.model_dump(mode="json") for e in canonical.evidence_inventory if e.evidence_class.value != "HISTORICAL_EVIDENCE"],
            "atomic_claims": [c.model_dump(mode="json") for c in canonical.atomic_claims],
            "fast_requirement_language": [x.model_dump(mode="json") for x in canonical.requirement_language if x.requirement_id in wanted],
            "source_availability": {k: v.value if hasattr(v, "value") else str(v) for k, v in canonical.source_availability.items()},
            "user_instructions": list(canonical.user_instructions),
        }
        return (
            "Analyze ONLY the listed requirements. Return one RequirementAnalysis for each listed requirement ID and no others. "
            "Do not synthesize hypotheses/history/diagnostics; those are Phase B.\n\nPHASE-A INPUT:\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _merge_phase_a_requirements(canonical: CanonicalCase, requirements) -> SemanticAnalysis:
        by_id = {r.requirement_id: copy.deepcopy(r) for r in requirements}
        ordered = []
        for source in canonical.requirements:
            if source.requirement_id not in by_id:
                continue
            item = by_id[source.requirement_id]
            item.requirement_text = source.requirement_text
            ordered.append(item)
        return SemanticAnalysis(
            affected_functionality=canonical.title or canonical.description or "Current analyzed functionality",
            evidence_inventory=copy.deepcopy(canonical.evidence_inventory),
            requirements=ordered,
            historical_tickets=[],
            diagnostic_evidence_ids=[],
            hypotheses=[],
            case_validity_needs=[],
        )

    @staticmethod
    def _phase_b_user_prompt(canonical: CanonicalCase, authoritative) -> str:
        payload = {
            "authoritative_compliance_state": {
                "requirement_results": [x.model_dump(mode="json") for x in authoritative.requirement_results],
                "compliance_evidence": list(authoritative.compliance_evidence),
                "evidence_conflicts": [x.model_dump(mode="json") for x in authoritative.evidence_conflicts],
            },
            "current_case_evidence": [e.model_dump(mode="json") for e in canonical.evidence_inventory],
            "atomic_claims": [x.model_dump(mode="json") for x in canonical.atomic_claims],
            "historical_text": canonical.historical_text,
            "diagnostics_text": canonical.diagnostics_text,
            "source_availability": {k: v.value if hasattr(v, "value") else str(v) for k, v in canonical.source_availability.items()},
            "user_instructions": list(canonical.user_instructions),
        }
        return (
            "Synthesize RCA context only. Treat authoritative_compliance_state as immutable. Return no requirement analyses.\n\nPHASE-B INPUT:\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _merge_rca_synthesis(authoritative_semantic: SemanticAnalysis, canonical: CanonicalCase, synthesis: RCASynthesisReasoning) -> SemanticAnalysis:
        return SemanticAnalysis(
            affected_functionality=synthesis.affected_functionality or authoritative_semantic.affected_functionality,
            evidence_inventory=copy.deepcopy(canonical.evidence_inventory),
            requirements=copy.deepcopy(authoritative_semantic.requirements),
            historical_tickets=copy.deepcopy(synthesis.historical_tickets),
            diagnostic_evidence_ids=sorted(
                set(synthesis.diagnostic_evidence_ids)
                | {e.id for e in canonical.evidence_inventory if e.source == "Current BZD / Diagnostics"}
            ),
            hypotheses=copy.deepcopy(synthesis.hypotheses),
            case_validity_needs=copy.deepcopy(synthesis.case_validity_needs),
        )

    @staticmethod
    def _phase_b_repair_user_prompt(canonical: CanonicalCase, authoritative, synthesis: RCASynthesisReasoning, critical) -> str:
        payload = {
            "validation_errors": [{"code": x.code, "path": x.path, "message": x.message} for x in critical],
            "authoritative_requirement_results": [x.model_dump(mode="json") for x in authoritative.requirement_results],
            "current_phase_b_synthesis": synthesis.model_dump(mode="json"),
            "historical_text": canonical.historical_text,
            "diagnostics_text": canonical.diagnostics_text,
            "evidence_inventory": [e.model_dump(mode="json") for e in canonical.evidence_inventory],
            "atomic_claims": [x.model_dump(mode="json") for x in canonical.atomic_claims],
        }
        return (
            "Repair only the Phase-B synthesis fields implicated by validation_errors. Requirement results are immutable.\n\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _hypothesis_review_user_prompt(payload: dict) -> str:
        return (
            "Review every supplied hypothesis by index. Distinguish a real mechanism candidate from a compliance restatement or over-strong root-cause claim. "
            "Return KEEP/REWRITE/DROP only; do not invent mechanisms.\n\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _trace_data(value):
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {str(k): RCAPipeline._trace_data(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [RCAPipeline._trace_data(v) for v in value]
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @classmethod
    def _trace_value(cls, value) -> str:
        data = cls._trace_data(value)
        if data is None:
            return ""
        if isinstance(data, str):
            return data
        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except TypeError:
            return str(data)

    @classmethod
    def _emit_trace(
        cls,
        callback: TraceCallback,
        stage_id: str,
        title: str,
        status: str,
        summary: str,
        *,
        input_value=None,
        output_value=None,
    ) -> None:
        """Emit a UI/debug trace event without making observability part of correctness.

        The callback is deliberately best-effort: a GUI rendering problem must
        never change the RCA result or repair behavior.
        """
        try:
            callback({
                "stage_id": stage_id,
                "title": title,
                "status": status,
                "summary": summary,
                "input_text": cls._trace_value(input_value),
                "output_text": cls._trace_value(output_value),
                "input_data": cls._trace_data(input_value),
                "output_data": cls._trace_data(output_value),
            })
        except Exception:
            pass

    def _run_deterministic_task(self, task, validated, canonical, repair_round, action_index, progress):
        start = time.perf_counter()
        repaired_semantic, changed_fields = self.repair_engine.apply_task(validated.semantic, task)
        if not changed_fields:
            # Do not claim success if the deterministic preconditions were not met.
            event = RepairEvent(
                pass_index=repair_round,
                route=RepairRoute.DETERMINISTIC,
                issue_codes=task.issue_codes,
                requirement_ids=[task.requirement_id] if task.requirement_id else [],
                elapsed_seconds=time.perf_counter() - start,
                outcome="NO_CHANGE",
                details="Deterministic repair preconditions were not mechanically satisfied; no field was changed.",
            )
            return validated, self.validator.critical_issues(validated), event

        progress(
            "Deterministic repair",
            f"Round {repair_round}, action {action_index}: {task.requirement_id or '<global>'} — "
            f"{', '.join(task.issue_codes)}; changed {', '.join(changed_fields)}.",
        )
        repaired_validated = self.validator.normalize_and_validate(repaired_semantic, canonical_case=canonical)
        remaining = self.validator.critical_issues(repaired_validated)
        event = RepairEvent(
            pass_index=repair_round,
            route=RepairRoute.DETERMINISTIC,
            issue_codes=task.issue_codes,
            requirement_ids=[task.requirement_id] if task.requirement_id else [],
            elapsed_seconds=time.perf_counter() - start,
            outcome="PASS" if not remaining else "REVALIDATED",
            details="Field-level deterministic patch; no LLM call. Changed field(s): " + ", ".join(changed_fields),
        )
        return repaired_validated, remaining, event

    def _run_fast_patch_task(self, task, validated, canonical, repair_round, action_index, progress, attempts, stats):
        progress(
            "Fast field repair",
            f"Round {repair_round}, action {action_index}: {task.requirement_id} — "
            f"{', '.join(task.issue_codes)}; writable field(s): {', '.join(task.allowed_fields)}.",
        )
        user_prompt = self._patch_user_prompt(canonical, validated.semantic, task)
        response = self.repair_client.structured_repair(
            system_prompt=FAST_PATCH_REPAIR_PROMPT,
            user_prompt=user_prompt,
            response_model=RequirementPatchResponse,
            schema_name="rca_fast_field_patch_v060",
        )
        stats.append(response.stats)
        patched_semantic, supplied_fields = self._apply_patch_response(
            validated.semantic,
            response.parsed,
            task.requirement_id,
            task.allowed_fields,
        )
        progress("Deterministic validation", "Revalidating the fast-model field patch...")
        repaired_validated = self.validator.normalize_and_validate(patched_semantic, canonical_case=canonical)
        remaining = self.validator.critical_issues(repaired_validated)
        attempts.append(self._make_attempt(
            call_index=len(attempts) + 1,
            stage=f"fast_patch_r{repair_round}_a{action_index}",
            model_role="FAST_REPAIR_PATCH",
            response=response,
            semantic_before=patched_semantic,
            validated=repaired_validated,
        ))
        tier0 = "; ".join(
            f"{x.get('path')}: {x.get('before')} -> {x.get('after')}" for x in response.tier0_adjustments
        ) or "none"
        event = RepairEvent(
            pass_index=repair_round,
            route=RepairRoute.FAST_MODEL,
            issue_codes=task.issue_codes,
            requirement_ids=[task.requirement_id],
            model=response.stats.model,
            elapsed_seconds=response.stats.elapsed_seconds,
            outcome="PASS" if not remaining else "REVALIDATED",
            details=(
                f"Field-level patch via {response.transport}; allowed={task.allowed_fields}; supplied={supplied_fields}; "
                f"raw_schema={'PASS' if response.raw_schema_valid else 'RECOVERED'}; Tier-0={tier0}."
            ),
        )
        return repaired_validated, remaining, response, event

    def _run_primary_tasks(self, tasks, validated, canonical, repair_round, action_index, progress, attempts, stats):
        req_ids = []
        issues = []
        issue_codes = []
        for task in tasks:
            if task.requirement_id and task.requirement_id not in req_ids:
                req_ids.append(task.requirement_id)
            issues.extend(task.issues)
            issue_codes.extend(task.issue_codes)

        if req_ids and all(task.requirement_id for task in tasks):
            progress(
                "Primary semantic repair",
                f"Round {repair_round}, action {action_index}: batching {len(req_ids)} requirement object(s) / "
                f"{len(issues)} core semantic issue(s) into one primary-model repair call.",
            )
            response = self.client.structured_chat(
                system_prompt=TARGETED_REQUIREMENT_REPAIR_PROMPT,
                user_prompt=self._targeted_requirement_repair_user_prompt(canonical, validated.semantic, issues, req_ids),
                response_model=RequirementRepairResponse,
                schema_name="rca_primary_requirement_batch_repair_v060",
            )
            reasoning = self._semantic_to_reasoning(validated.semantic)
            repaired_by_id = {r.requirement_id: r for r in response.parsed.requirements}
            missing = set(req_ids) - set(repaired_by_id)
            extra = set(repaired_by_id) - set(req_ids)
            if missing or extra:
                raise ValueError(
                    "Primary targeted repair returned wrong requirement IDs. "
                    f"missing={sorted(missing)}, extra={sorted(extra)}"
                )
            reasoning.requirements = [copy.deepcopy(repaired_by_id.get(r.requirement_id, r)) for r in reasoning.requirements]
        else:
            progress(
                "Primary semantic repair",
                f"Round {repair_round}, action {action_index}: repairing {len(issues)} global/core semantic issue(s).",
            )
            response = self.client.structured_chat(
                system_prompt=REPAIR_PROMPT,
                user_prompt=self._repair_user_prompt(canonical, self._semantic_to_reasoning(validated.semantic), issues),
                response_model=SemanticReasoning,
                schema_name="rca_semantic_reasoning_batch_repair_v060",
            )
            reasoning = response.parsed

        stats.append(response.stats)
        semantic = self._merge_canonical_and_reasoning(canonical, reasoning)
        progress("Deterministic validation", "Revalidating primary semantic repair...")
        repaired_validated = self.validator.normalize_and_validate(semantic, canonical_case=canonical)
        remaining = self.validator.critical_issues(repaired_validated)
        attempts.append(self._make_attempt(
            call_index=len(attempts) + 1,
            stage=f"primary_batch_repair_r{repair_round}_a{action_index}",
            model_role="PRIMARY_REPAIR",
            response=response,
            semantic_before=semantic,
            validated=repaired_validated,
        ))
        event = RepairEvent(
            pass_index=repair_round,
            route=RepairRoute.PRIMARY_MODEL,
            issue_codes=sorted(set(issue_codes)),
            requirement_ids=req_ids,
            model=response.stats.model,
            elapsed_seconds=response.stats.elapsed_seconds,
            outcome="PASS" if not remaining else "REVALIDATED",
            details=f"Primary-model batch repair for {len(req_ids) if req_ids else 'global'} semantic target(s).",
        )
        return repaired_validated, remaining, response, event

    def _run_primary_task(self, task, validated, canonical, repair_round, action_index, progress, attempts, stats):
        req_ids = [task.requirement_id] if task.requirement_id else []
        if req_ids:
            progress(
                "Primary semantic repair",
                f"Round {repair_round}, action {action_index}: escalating {task.requirement_id} / "
                f"{', '.join(task.issue_codes)} to the primary model.",
            )
            response = self.client.structured_chat(
                system_prompt=TARGETED_REQUIREMENT_REPAIR_PROMPT,
                user_prompt=self._targeted_requirement_repair_user_prompt(
                    canonical, validated.semantic, task.issues, req_ids
                ),
                response_model=RequirementRepairResponse,
                schema_name="rca_primary_requirement_repair_v053",
            )
            reasoning = self._semantic_to_reasoning(validated.semantic)
            repaired_by_id = {r.requirement_id: r for r in response.parsed.requirements}
            missing = set(req_ids) - set(repaired_by_id)
            extra = set(repaired_by_id) - set(req_ids)
            if missing or extra:
                raise ValueError(
                    "Primary targeted repair returned wrong requirement IDs. "
                    f"missing={sorted(missing)}, extra={sorted(extra)}"
                )
            reasoning.requirements = [copy.deepcopy(repaired_by_id.get(r.requirement_id, r)) for r in reasoning.requirements]
        else:
            progress(
                "Primary semantic repair",
                f"Round {repair_round}, action {action_index}: repairing {len(task.issues)} global/core semantic issue(s).",
            )
            response = self.client.structured_chat(
                system_prompt=REPAIR_PROMPT,
                user_prompt=self._repair_user_prompt(canonical, self._semantic_to_reasoning(validated.semantic), task.issues),
                response_model=SemanticReasoning,
                schema_name="rca_semantic_reasoning_repair_v053",
            )
            reasoning = response.parsed

        stats.append(response.stats)
        semantic = self._merge_canonical_and_reasoning(canonical, reasoning)
        progress("Deterministic validation", "Revalidating primary semantic repair...")
        repaired_validated = self.validator.normalize_and_validate(semantic, canonical_case=canonical)
        remaining = self.validator.critical_issues(repaired_validated)
        attempts.append(self._make_attempt(
            call_index=len(attempts) + 1,
            stage=f"primary_repair_r{repair_round}_a{action_index}",
            model_role="PRIMARY_REPAIR",
            response=response,
            semantic_before=semantic,
            validated=repaired_validated,
        ))
        event = RepairEvent(
            pass_index=repair_round,
            route=RepairRoute.PRIMARY_MODEL,
            issue_codes=task.issue_codes,
            requirement_ids=req_ids,
            model=response.stats.model,
            elapsed_seconds=response.stats.elapsed_seconds,
            outcome="PASS" if not remaining else "REVALIDATED",
            details="Primary-model semantic repair for core or escalated defect.",
        )
        return repaired_validated, remaining, response, event

    @staticmethod
    def _apply_patch_response(
        semantic: SemanticAnalysis,
        response: RequirementPatchResponse,
        requirement_id: str,
        allowed_fields: list[str],
    ) -> tuple[SemanticAnalysis, list[str]]:
        if len(response.patches) != 1:
            raise ValueError(f"Expected exactly one fast-model patch, got {len(response.patches)}.")
        item = response.patches[0]
        if item.requirement_id != requirement_id:
            raise ValueError(f"Patch returned {item.requirement_id!r}, expected {requirement_id!r}.")
        supplied = sorted(item.patch.model_fields_set)
        unauthorized = sorted(set(supplied) - set(allowed_fields))
        if unauthorized:
            raise ValueError("Fast repair attempted unauthorized field(s): " + ", ".join(unauthorized))
        if not supplied:
            raise ValueError("Fast repair patch contained no fields.")

        out = copy.deepcopy(semantic)
        target = next((r for r in out.requirements if r.requirement_id == requirement_id), None)
        if target is None:
            raise ValueError(f"Requirement {requirement_id} not found for patch application.")
        for field in supplied:
            value = getattr(item.patch, field)
            if value is None:
                raise ValueError(f"Patch field {field} was explicitly null; null is not a valid repair value.")
            setattr(target, field, copy.deepcopy(value))
        out = SemanticAnalysis.model_validate(out.model_dump(mode="json"))
        return out, supplied

    def _patch_user_prompt(self, canonical: CanonicalCase, semantic: SemanticAnalysis, task: RepairTask) -> str:
        rid = task.requirement_id
        req = next(r for r in semantic.requirements if r.requirement_id == rid)
        source = next(r for r in canonical.requirements if r.requirement_id == rid)
        current = req.model_dump(mode="json")
        current_values = {field: current.get(field) for field in task.allowed_fields}
        payload = {
            "requirement_id": rid,
            "canonical_requirement": source.model_dump(mode="json"),
            "validation_errors": [
                {"code": i.code, "path": i.path, "message": i.message} for i in task.issues
            ],
            "repair_instructions": task.instructions,
            "allowed_patch_fields": list(task.allowed_fields),
            "current_values_of_allowed_fields": current_values,
            "current_requirement_context": current,
            "referenced_evidence": self._referenced_evidence_for_requirement(canonical, req),
        }
        examples = {
            "faithful_meaning": "<corrected faithful meaning>",
            "relevance": "<corrected relevance>",
            "normative_type": "MANDATORY",
            "applicability": "APPLICABLE",
            "applicability_evidence_ids": ["EVID-..."],
            "applicability_condition": "<condition>",
            "trigger": "<trigger>",
            "required_behavior": "<required behavior>",
            "timing_constraint": "<timing constraint>",
            "observation_interval_requirement": "<interval requirement>",
            "explicit_relationships": ["<relationship>"],
            "evaluation_evidence_ids": ["EVID-..."],
            "evaluation_sufficiency": "INSUFFICIENT",
            "missing_applicability_evidence": [{"element": "APPLICABILITY", "description": "<missing evidence>"}],
            "missing_evaluation_evidence": [{"element": "OBSERVATION_INTERVAL", "description": "<missing evidence>"}],
        }
        example_patch = {field: examples[field] for field in task.allowed_fields}
        return (
            "Apply a FIELD-LEVEL patch only. The validator has already identified the defective field(s). "
            "Do not re-analyze or rewrite any field outside allowed_patch_fields. Return exactly one patch for the listed requirement.\n"
            "Output JSON contract: "
            + json.dumps({"patches": [{"requirement_id": rid, "patch": example_patch}]}, ensure_ascii=False)
            + "\nINPUT:\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _referenced_evidence_for_requirement(canonical: CanonicalCase, req) -> list[dict]:
        referenced_ids = set(req.applicability_evidence_ids) | set(req.evaluation_evidence_ids)
        for need in list(req.missing_applicability_evidence) + list(req.missing_evaluation_evidence):
            referenced_ids.update(re.findall(r"EVID-[A-Z0-9-]+", need.description or ""))
        if referenced_ids:
            return [e.model_dump(mode="json") for e in canonical.evidence_inventory if e.id in referenced_ids]
        return [
            e.model_dump(mode="json") for e in canonical.evidence_inventory
            if e.evidence_class.value in {"REPORTED_OBSERVATION", "DIRECT_OBSERVATION"}
        ]

    def _task_still_present(self, task: RepairTask, semantic: SemanticAnalysis, critical) -> bool:
        current_plan = self.repair_router.build_plan(
            semantic,
            [x for x in critical if not x.path.startswith("validated.")],
            fast_model_available=self.repair_client is not None,
        )
        return any(x.signature == task.signature for x in current_plan)

    @staticmethod
    def _critical_signature(issues) -> tuple:
        return tuple(sorted((x.code, x.path, x.message) for x in issues))

    @staticmethod
    def _merge_canonical_and_reasoning(canonical: CanonicalCase, reasoning: SemanticReasoning) -> SemanticAnalysis:
        source_text = {r.requirement_id: r.requirement_text for r in canonical.requirements}
        reqs = copy.deepcopy(reasoning.requirements)
        for req in reqs:
            if req.requirement_id in source_text:
                req.requirement_text = source_text[req.requirement_id]

        return SemanticAnalysis(
            affected_functionality=reasoning.affected_functionality,
            evidence_inventory=copy.deepcopy(canonical.evidence_inventory),
            requirements=reqs,
            historical_tickets=reasoning.historical_tickets,
            diagnostic_evidence_ids=sorted(
                set(reasoning.diagnostic_evidence_ids)
                | {e.id for e in canonical.evidence_inventory if e.source == "Current BZD / Diagnostics"}
            ),
            hypotheses=reasoning.hypotheses,
            case_validity_needs=reasoning.case_validity_needs,
        )

    @staticmethod
    def _semantic_to_reasoning(semantic: SemanticAnalysis) -> SemanticReasoning:
        return SemanticReasoning(
            affected_functionality=semantic.affected_functionality,
            requirements=copy.deepcopy(semantic.requirements),
            historical_tickets=copy.deepcopy(semantic.historical_tickets),
            diagnostic_evidence_ids=list(semantic.diagnostic_evidence_ids),
            hypotheses=copy.deepcopy(semantic.hypotheses),
            case_validity_needs=copy.deepcopy(semantic.case_validity_needs),
        )

    @staticmethod
    def _make_attempt(call_index: int, stage: str, model_role: str, response, semantic_before: SemanticAnalysis, validated) -> PipelineAttempt:
        return PipelineAttempt(
            call_index=call_index,
            stage=stage,
            model_role=model_role,
            raw_llm_json=response.raw_json,
            reasoning_content=response.reasoning_content or "",
            semantic_before_validation_json=json.dumps(semantic_before.model_dump(mode="json"), indent=2, ensure_ascii=False),
            normalized_semantic_json=json.dumps(validated.semantic.model_dump(mode="json"), indent=2, ensure_ascii=False),
            validation_issues=copy.deepcopy(validated.issues),
            stats=response.stats,
            finish_reason=getattr(response, "finish_reason", "") or "",
            transport=getattr(response, "transport", "") or "",
            retry_diagnostics=list(getattr(response, "retry_diagnostics", []) or []),
            structured_attempts=copy.deepcopy(getattr(response, "structured_attempts", []) or []),
        )

    @staticmethod
    def _make_aux_attempt(call_index: int, stage: str, model_role: str, response, semantic_before=None, validated=None) -> PipelineAttempt:
        semantic_json = ""
        normalized_json = ""
        validation_issues = []
        if semantic_before is not None:
            semantic_json = json.dumps(semantic_before.model_dump(mode="json"), indent=2, ensure_ascii=False)
        if validated is not None:
            normalized_json = json.dumps(validated.semantic.model_dump(mode="json"), indent=2, ensure_ascii=False)
            validation_issues = copy.deepcopy(validated.issues)
        return PipelineAttempt(
            call_index=call_index,
            stage=stage,
            model_role=model_role,
            raw_llm_json=response.raw_json,
            reasoning_content=response.reasoning_content or "",
            semantic_before_validation_json=semantic_json,
            normalized_semantic_json=normalized_json,
            validation_issues=validation_issues,
            stats=response.stats,
            finish_reason=getattr(response, "finish_reason", "") or "",
            transport=getattr(response, "transport", "") or "",
            retry_diagnostics=list(getattr(response, "retry_diagnostics", []) or []),
            structured_attempts=copy.deepcopy(getattr(response, "structured_attempts", []) or []),
        )

    @staticmethod
    def _make_failed_attempt(call_index: int, stage: str, model_role: str, error: ModelGatewayError, semantic_before=None, validated=None) -> PipelineAttempt:
        semantic_json = ""
        normalized_json = ""
        validation_issues = []
        if semantic_before is not None:
            semantic_json = json.dumps(semantic_before.model_dump(mode="json"), indent=2, ensure_ascii=False)
        if validated is not None:
            normalized_json = json.dumps(validated.semantic.model_dump(mode="json"), indent=2, ensure_ascii=False)
            validation_issues = copy.deepcopy(validated.issues)
        raw = error.raw_json or error.raw_api_response or ""
        return PipelineAttempt(
            call_index=call_index,
            stage=stage,
            model_role=model_role,
            raw_llm_json=raw,
            reasoning_content=error.reasoning_content or "",
            semantic_before_validation_json=semantic_json,
            normalized_semantic_json=normalized_json,
            validation_issues=validation_issues,
            stats=error.stats,
            finish_reason=error.finish_reason or "",
            transport=error.transport or "",
            retry_diagnostics=list(error.retry_diagnostics or []),
            structured_attempts=copy.deepcopy(getattr(error, "structured_attempts", []) or []),
        )

    @staticmethod
    def _targeted_requirement_repair_user_prompt(canonical: CanonicalCase, semantic: SemanticAnalysis, critical, req_ids: list[str]) -> str:
        issues = [f"- {x.code} at {x.path}: {x.message}" for x in critical]
        canonical_req = [r.model_dump(mode="json") for r in canonical.requirements if r.requirement_id in req_ids]
        current_req = [r.model_dump(mode="json") for r in semantic.requirements if r.requirement_id in req_ids]
        usable_evidence = [
            e.model_dump(mode="json") for e in canonical.evidence_inventory
            if e.evidence_class.value in {"REPORTED_OBSERVATION", "DIRECT_OBSERVATION", "CURRENT_TICKET", "TEST_INSTRUCTION"}
        ]
        payload = {
            "repair_requirement_ids": req_ids,
            "validation_errors": issues,
            "canonical_requirements": canonical_req,
            "current_requirement_analysis": current_req,
            "evidence_inventory": usable_evidence,
        }
        return (
            "Repair only the listed requirement objects. Return complete RequirementAnalysis objects for those IDs only.\n\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _intake_user_prompt(raw_case: str) -> str:
        return (
            "Normalize this raw testcase into the intake schema. Classify source availability semantically as PRESENT, ABSENT, UNKNOWN, or NOT_MENTIONED; "
            "keep absence/uncertainty statements as availability metadata rather than evidence, and separate user/operator analysis instructions into user_instructions. "
            "Every source_span must be copied verbatim from RAW INPUT. Do not perform RCA reasoning, compliance evaluation, trace-event inference or evidence-ID assignment.\n\nRAW INPUT:\n"
            + raw_case
        )

    @staticmethod
    def _final_review_user_prompt(payload: dict) -> str:
        return (
            "Extract what the current relevance wording claims about evidence relevance, evidence sufficiency, and evaluation status. "
            "Then determine whether those claims conflict with the authoritative structured facts. "
            "Remember that RELEVANT + INSUFFICIENT + NOT_EVALUABLE is valid. Propose a replacement relevance sentence only for a real conflict.\n\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _analysis_user_prompt(canonical: CanonicalCase) -> str:
        payload = canonical.model_dump(mode="json")
        payload.pop("parser_notes", None)
        return (
            "Analyze this canonical current case. Evidence/source classification and requirement ID/text are authoritative. "
            "Reference only the supplied evidence IDs. Return only the semantic reasoning schema.\n\n"
            "CANONICAL CASE:\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _repair_user_prompt(canonical: CanonicalCase, reasoning: SemanticReasoning, critical) -> str:
        issue_text = "\n".join(f"- {x.code} at {x.path}: {x.message}" for x in critical)
        current = json.dumps(reasoning.model_dump(mode="json"), indent=2, ensure_ascii=False)
        canonical_json = json.dumps(canonical.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        return (
            "Correct only the semantic fields implicated by these deterministic validation errors.\n\n"
            "VALIDATION ERRORS:\n"
            f"{issue_text}\n\n"
            "CURRENT SEMANTIC REASONING:\n"
            f"{current}\n\n"
            "CANONICAL CASE (authoritative):\n"
            f"{canonical_json}"
        )
