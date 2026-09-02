from __future__ import annotations

import copy

from .models import HypothesisReviewAction, HypothesisReviewResponse, ValidatedAnalysis


class HypothesisEpistemicGate:
    """Apply non-authoritative 4B hypothesis-language actions safely.

    The 4B owns linguistic/epistemic classification. Python only applies an
    index-matched KEEP/REWRITE/DROP operation and revalidates the resulting
    structured state. It never decides from words such as "caused" itself.
    """

    @staticmethod
    def payload(validated: ValidatedAnalysis) -> dict:
        evidence = {e.id: e.model_dump(mode="json") for e in validated.semantic.evidence_inventory}
        return {
            "authoritative_requirement_results": [x.model_dump(mode="json") for x in validated.requirement_results],
            "hypotheses": [
                {
                    "hypothesis_index": idx,
                    "hypothesis": hyp.model_dump(mode="json"),
                    "supporting_evidence": [evidence[eid] for eid in hyp.supporting_evidence_ids if eid in evidence],
                    "weakening_evidence": [evidence[eid] for eid in hyp.weakening_evidence_ids if eid in evidence],
                }
                for idx, hyp in enumerate(validated.semantic.hypotheses)
            ],
            "instruction": "Classify hypothesis language/epistemic strength only. Do not change authoritative requirement facts.",
        }

    @staticmethod
    def apply(validated: ValidatedAnalysis, review: HypothesisReviewResponse, validator, canonical):
        semantic = copy.deepcopy(validated.semantic)
        original = list(semantic.hypotheses)
        reviews = {x.hypothesis_index: x for x in review.reviews}
        out = []
        accepted: list[str] = []
        rejected: list[str] = []

        for idx, hyp in enumerate(original):
            item = reviews.get(idx)
            if item is None or item.action == HypothesisReviewAction.KEEP:
                out.append(hyp)
                continue
            if item.action == HypothesisReviewAction.DROP:
                accepted.append(f"DROP hypothesis[{idx}]")
                continue
            if item.action == HypothesisReviewAction.REWRITE:
                replacement = " ".join((item.replacement_hypothesis or "").split()).strip()
                if not replacement:
                    rejected.append(f"Rejected empty rewrite for hypothesis[{idx}].")
                    out.append(hyp)
                    continue
                updated = copy.deepcopy(hyp)
                updated.hypothesis = replacement
                out.append(updated)
                accepted.append(f"REWRITE hypothesis[{idx}]")
                continue
            out.append(hyp)

        semantic.hypotheses = out
        revalidated = validator.normalize_and_validate(semantic, canonical_case=canonical)
        critical = validator.critical_issues(revalidated)
        if critical:
            return validated, [], rejected + ["Rejected hypothesis review actions because deterministic revalidation failed."]
        return revalidated, accepted, rejected
    @staticmethod
    def apply_v080(validated: ValidatedAnalysis, review: HypothesisReviewResponse):
        """Apply hypothesis language actions without re-running legacy compliance semantics.

        v0.8 compliance has already been executed from Requirement IR. The review
        stage may only KEEP/REWRITE/DROP hypothesis text while preserving every
        authoritative requirement result and deterministic timing fact byte-for-byte.
        """
        out = copy.deepcopy(validated)
        original_results = copy.deepcopy(out.requirement_results)
        original = list(out.semantic.hypotheses)
        reviews = {x.hypothesis_index: x for x in review.reviews}
        hypotheses = []
        accepted = []
        rejected = []
        for idx, hyp in enumerate(original):
            item = reviews.get(idx)
            if item is None or item.action == HypothesisReviewAction.KEEP:
                hypotheses.append(hyp)
                continue
            if item.action == HypothesisReviewAction.DROP:
                accepted.append(f"DROP hypothesis[{idx}]")
                continue
            if item.action == HypothesisReviewAction.REWRITE:
                replacement = " ".join((item.replacement_hypothesis or "").split()).strip()
                if not replacement:
                    rejected.append(f"Rejected empty rewrite for hypothesis[{idx}].")
                    hypotheses.append(hyp)
                    continue
                updated = copy.deepcopy(hyp)
                updated.hypothesis = replacement
                hypotheses.append(updated)
                accepted.append(f"REWRITE hypothesis[{idx}]")
                continue
            hypotheses.append(hyp)
        out.semantic.hypotheses = hypotheses
        out.hypotheses = copy.deepcopy(hypotheses)
        out.requirement_results = original_results
        return out, accepted, rejected

