from __future__ import annotations

import copy
from typing import Iterable

from .models import (
    CanonicalCase,
    EvaluationStatus,
    LinguisticReviewResponse,
    ReviewClaimedEvaluationStatus,
    ReviewEvidenceRelevance,
    ReviewEvidenceSufficiency,
    Sufficiency,
    ValidatedAnalysis,
)
from .validator import DeterministicValidator


class LinguisticReviewGate:
    """Apply only non-authoritative relevance wording patches, then revalidate.

    v0.6.4 adds a structured claim check before accepting a reviewer patch. The
    4B reviewer extracts what the current wording claims about relevance,
    sufficiency and verdict; Python compares those claims to the authoritative
    validated structure. This keeps the LLM responsible for language
    understanding while preventing a false "RELEVANT + INSUFFICIENT is a
    contradiction" judgment from modifying correct prose.
    """

    @staticmethod
    def _expected_sufficiency(value: Sufficiency) -> ReviewEvidenceSufficiency:
        if value == Sufficiency.INSUFFICIENT:
            return ReviewEvidenceSufficiency.INSUFFICIENT
        if value == Sufficiency.NOT_REQUIRED:
            return ReviewEvidenceSufficiency.NOT_REQUIRED
        return ReviewEvidenceSufficiency.SUFFICIENT

    @staticmethod
    def _expected_eval_status(value: EvaluationStatus) -> ReviewClaimedEvaluationStatus:
        mapping = {
            EvaluationStatus.SATISFIED: ReviewClaimedEvaluationStatus.SATISFIED,
            EvaluationStatus.VIOLATED: ReviewClaimedEvaluationStatus.VIOLATED,
            EvaluationStatus.NOT_EVALUABLE: ReviewClaimedEvaluationStatus.NOT_EVALUABLE,
            EvaluationStatus.NO_COMPLIANCE_VERDICT: ReviewClaimedEvaluationStatus.NO_COMPLIANCE_VERDICT,
        }
        return mapping[value]

    @staticmethod
    def compact_payload(validated: ValidatedAnalysis) -> dict:
        evidence = {e.id: e for e in validated.semantic.evidence_inventory}
        requirements = []
        for rr in validated.requirement_results:
            req = rr.analysis
            app_items = [evidence[x] for x in req.applicability_evidence_ids if x in evidence]
            eval_items = [evidence[x] for x in req.evaluation_evidence_ids if x in evidence]
            timestamped_app = [x for x in app_items if x.timestamped and x.timestamp_seconds is not None]
            timestamped_eval = [x for x in eval_items if x.timestamped and x.timestamp_seconds is not None]
            clocks = {x.clock_id.strip() for x in timestamped_app + timestamped_eval if x.clock_id.strip()}
            same_clock = len(clocks) <= 1 if (timestamped_app and timestamped_eval) else None
            expected_relevance = (
                ReviewEvidenceRelevance.RELEVANT.value
                if req.evaluation_evidence_ids or req.applicability_evidence_ids
                else ReviewEvidenceRelevance.UNDETERMINED.value
            )
            requirements.append({
                "requirement_id": req.requirement_id,
                "requirement_text": req.requirement_text,
                "current_relevance": req.relevance,
                "normative_type": req.normative_type.value,
                "applicability": req.applicability.value,
                "evaluation_status": rr.evaluation_status.value,
                "evaluation_sufficiency": req.evaluation_sufficiency.value,
                "expected_review_classification": {
                    "evidence_relevance": expected_relevance,
                    "evidence_sufficiency": LinguisticReviewGate._expected_sufficiency(req.evaluation_sufficiency).value,
                    "evaluation_status": LinguisticReviewGate._expected_eval_status(rr.evaluation_status).value,
                },
                "trigger": req.trigger,
                "required_behavior": req.required_behavior,
                "timing_constraint": req.timing_constraint,
                "trigger_timestamp_known": bool(timestamped_app),
                "response_timestamp_known": bool(timestamped_eval),
                "same_clock": same_clock,
                "mapped_clocks": sorted(clocks),
                "mapped_timing_evidence": [
                    {
                        "id": x.id,
                        "timestamp_seconds": x.timestamp_seconds,
                        "clock_id": x.clock_id,
                        "observation_type": x.observation_type.value,
                        "event_coverage_complete": x.event_coverage_complete,
                        "signal_name": x.signal_name,
                        "signal_value": x.signal_value,
                    }
                    for x in timestamped_app + timestamped_eval
                ],
                "timing_fact": rr.timing_fact.model_dump(mode="json") if rr.timing_fact else None,
                "missing_applicability_evidence": [x.model_dump(mode="json") for x in req.missing_applicability_evidence],
                "missing_evaluation_evidence": [x.model_dump(mode="json") for x in req.missing_evaluation_evidence],
                "minimum_next_evidence": [x for x in validated.compliance_evidence if req.requirement_id in x],
            })
        return {
            "authoritative_requirements": requirements,
            "evidence_conflicts": [x.model_dump(mode="json") for x in validated.evidence_conflicts],
            "valid_logic_combinations": [
                "RELEVANT + INSUFFICIENT + NOT_EVALUABLE is valid and is not a contradiction.",
                "RELEVANT evidence can be useful for evaluation even when it is insufficient for a final verdict.",
            ],
            "instruction": "Review wording only. Do not alter authoritative facts or verdicts.",
            "review_method": "Extract wording claims first; propose a relevance rewrite only if those claims actually conflict with authoritative facts.",
        }

    @staticmethod
    def _structured_review_matches_authority(item, expected: dict) -> tuple[bool, str]:
        """Compare model-extracted wording claims to deterministic authoritative values."""
        problems: list[str] = []
        exp_rel = expected.get("evidence_relevance", ReviewEvidenceRelevance.UNDETERMINED.value)
        exp_suff = expected.get("evidence_sufficiency", ReviewEvidenceSufficiency.UNDETERMINED.value)
        exp_eval = expected.get("evaluation_status", ReviewClaimedEvaluationStatus.UNDETERMINED.value)

        # UNDETERMINED means the reviewer did not extract a claim; it is not a contradiction.
        if item.evidence_relevance.value != ReviewEvidenceRelevance.UNDETERMINED.value:
            if exp_rel != ReviewEvidenceRelevance.UNDETERMINED.value and item.evidence_relevance.value != exp_rel:
                problems.append(f"relevance claim {item.evidence_relevance.value} != {exp_rel}")
        if item.evidence_sufficiency.value != ReviewEvidenceSufficiency.UNDETERMINED.value:
            if exp_suff != ReviewEvidenceSufficiency.UNDETERMINED.value and item.evidence_sufficiency.value != exp_suff:
                problems.append(f"sufficiency claim {item.evidence_sufficiency.value} != {exp_suff}")
        if item.claimed_evaluation_status not in {
            ReviewClaimedEvaluationStatus.NOT_STATED,
            ReviewClaimedEvaluationStatus.UNDETERMINED,
        }:
            if item.claimed_evaluation_status.value != exp_eval:
                problems.append(f"verdict claim {item.claimed_evaluation_status.value} != {exp_eval}")

        return (not problems, "; ".join(problems))

    @staticmethod
    def apply(
        validated: ValidatedAnalysis,
        review: LinguisticReviewResponse,
        canonical: CanonicalCase,
        validator: DeterministicValidator,
    ) -> tuple[ValidatedAnalysis, list[str], list[str]]:
        semantic = copy.deepcopy(validated.semantic)
        req_by_id = {x.requirement_id: x for x in semantic.requirements}
        payload = LinguisticReviewGate.compact_payload(validated)
        expected_by_id = {
            x["requirement_id"]: x["expected_review_classification"]
            for x in payload["authoritative_requirements"]
        }
        accepted: list[str] = []
        rejected: list[str] = []
        seen: set[str] = set()

        # v0.6.4 structured review path.
        structured_patches: list[tuple[str, str]] = []
        for item in review.requirement_reviews:
            rid = item.requirement_id.strip()
            if not rid or rid not in req_by_id:
                rejected.append(f"Rejected structured review for unknown/empty requirement {rid or '<empty>'}.")
                continue
            matches, mismatch = LinguisticReviewGate._structured_review_matches_authority(
                item, expected_by_id.get(rid, {})
            )
            if matches and item.wording_issue:
                # If the extracted claims match authority, a claimed logical contradiction
                # has no factual basis. Keep the finding for audit but do not rewrite correct
                # wording unless there is an explicit replacement and the reviewer marked the
                # verdict itself consistent (e.g. a precision-only wording cleanup).
                if item.verdict_consistency.value == "INCONSISTENT":
                    rejected.append(
                        f"Rejected false-positive wording contradiction for {rid}: extracted wording claims already match authoritative relevance/sufficiency/verdict."
                    )
                    continue
            if not matches and item.verdict_consistency.value == "CONSISTENT":
                rejected.append(
                    f"Rejected inconsistent structured review for {rid}: extracted wording claims conflict with authority ({mismatch}) but reviewer marked them CONSISTENT."
                )
                continue
            replacement = " ".join((item.replacement_relevance or "").split()).strip()
            if item.wording_issue and replacement:
                structured_patches.append((rid, replacement))

        # Legacy fields remain accepted for saved sessions/tests and explicit old clients.
        legacy_patches = [
            (p.requirement_id.strip(), " ".join((p.relevance or "").split()).strip())
            for p in review.relevance_patches
        ]

        for rid, text in structured_patches + legacy_patches:
            if not rid or rid in seen:
                rejected.append(f"Rejected duplicate/empty relevance patch for {rid or '<empty>'}.")
                continue
            seen.add(rid)
            req = req_by_id.get(rid)
            if req is None:
                rejected.append(f"Rejected relevance patch for unknown requirement {rid}.")
                continue
            if not text:
                rejected.append(f"Rejected empty relevance patch for {rid}.")
                continue
            req.relevance = text
            accepted.append(rid)

        if not accepted:
            return validated, [], rejected

        revalidated = validator.normalize_and_validate(semantic, canonical_case=canonical)
        critical = validator.critical_issues(revalidated)
        if critical:
            codes = ", ".join(sorted({x.code for x in critical}))
            return validated, [], rejected + [f"Rejected all linguistic patches because deterministic revalidation failed: {codes}."]
        return revalidated, accepted, rejected
