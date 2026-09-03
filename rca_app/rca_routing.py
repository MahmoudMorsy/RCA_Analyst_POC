from __future__ import annotations

from typing import List, Set

from .models import (
    CanonicalCase,
    EvidenceClass,
    EvidenceSemanticRole,
    RCAEvidencePacket,
    RCARouteDecision,
    RequirementIR,
    SemanticPreparation,
    SemanticResolution,
    TemporalSemantics,
    ValidatedAnalysis,
)


class RCARouter:
    """Decide whether an expensive deep RCA synthesis call is justified.

    The router does not attempt to infer a root cause. It only checks for
    mechanism-oriented evidence already identified structurally or by the
    semantic preparation stage.
    """

    def decide(self, canonical: CanonicalCase, preparation: SemanticPreparation, validated: ValidatedAnalysis) -> RCARouteDecision:
        reasons: List[str] = []
        evidence_ids: List[str] = []

        if canonical.diagnostics_text.strip():
            reasons.append("Current diagnostic/BZD evidence is present.")
            evidence_ids.extend(e.id for e in canonical.evidence_inventory if e.source == "Current BZD / Diagnostics")
        if canonical.historical_text.strip():
            reasons.append("Historical precedent is present and requires current-case comparison.")
            evidence_ids.extend(e.id for e in canonical.evidence_inventory if e.evidence_class == EvidenceClass.HISTORICAL_EVIDENCE)

        evidence_by_id = {e.id: e for e in canonical.evidence_inventory}
        output_signals = {
            ir.required_behavior.signal.strip().lower()
            for ir in preparation.requirement_irs
            if ir.required_behavior is not None and ir.required_behavior.signal.strip()
        }

        for ann in preparation.evidence_annotations:
            item = evidence_by_id.get(ann.evidence_id)
            if item is None:
                continue
            for fact in ann.facts:
                if fact.resolution != SemanticResolution.VERIFIED:
                    continue
                roles = set(fact.possible_roles)

                # Semantic roles alone are not enough to manufacture a source
                # class. An ordinary signal observation tagged DIAGNOSTIC by a
                # model is still not BZD/DTC evidence.
                if EvidenceSemanticRole.DIAGNOSTIC in roles and item.source == "Current BZD / Diagnostics":
                    reasons.append("Verified current diagnostic/BZD mechanism evidence is present.")
                    evidence_ids.append(ann.evidence_id)
                    break
                if EvidenceSemanticRole.HISTORICAL in roles and item.evidence_class == EvidenceClass.HISTORICAL_EVIDENCE:
                    reasons.append("Verified historical mechanism evidence is present.")
                    evidence_ids.append(ann.evidence_id)
                    break

                # RCA_CONTEXT is deliberately non-routing. MECHANISM is the
                # explicit semantic role for positive current-case mechanism
                # evidence. A point-state observation of a requirement output
                # signal is still only the symptom/compliance mismatch.
                if (
                    EvidenceSemanticRole.MECHANISM in roles
                    and item.evidence_class in {EvidenceClass.DIRECT_OBSERVATION, EvidenceClass.REPORTED_OBSERVATION}
                    and not (
                        fact.temporal_semantics == TemporalSemantics.POINT_STATE
                        and fact.subject.strip().lower() in output_signals
                    )
                ):
                    reasons.append("Semantic preparation identified positive current-case mechanism evidence.")
                    evidence_ids.append(ann.evidence_id)
                    break

        # A bare compliance violation is intentionally insufficient. Deep RCA is
        # justified by an additional mechanism source, not merely by "expected X,
        # observed Y". This keeps TC12/TC17 out of Phase-B-style 27B calls.
        return RCARouteDecision(
            run_rca=bool(reasons),
            reasons=self._dedupe(reasons),
            supporting_evidence_ids=self._dedupe(evidence_ids),
        )

    @staticmethod
    def _dedupe(values):
        out = []
        seen = set()
        for value in values:
            if value and value not in seen:
                seen.add(value)
                out.append(value)
        return out


class RCAEvidencePacketBuilder:
    """Build the compact, verified packet consumed by the 27B RCA model.

    The packet does not resend the full raw case or original natural-language
    requirements. Raw excerpts are empty by default and can be added later only
    for narrowly selected narrative evidence where semantic compression would
    remove material RCA nuance.
    """

    def build(
        self,
        canonical: CanonicalCase,
        preparation: SemanticPreparation,
        validated: ValidatedAnalysis,
        route: RCARouteDecision,
    ) -> RCAEvidencePacket:
        relevant_req_ids: Set[str] = {
            rr.analysis.requirement_id
            for rr in validated.requirement_results
            if rr.analysis.applicability.value == "APPLICABLE" or rr.evaluation_status.value == "VIOLATED"
        }
        # Keep requirements with material semantic-integrity blockers visible to
        # RCA as unresolved normative context. They are not executable truth, but
        # disappearing them can make RCA falsely claim that no requirement exists.
        relevant_req_ids.update(
            issue.requirement_id
            for issue in canonical.semantic_integrity_issues
            if issue.material_to_compliance and issue.requirement_id
        )
        requirement_irs: List[RequirementIR] = [
            ir for ir in preparation.requirement_irs if ir.requirement_id in relevant_req_ids
        ]
        unresolved_requirement_context = []
        for rid in sorted(relevant_req_ids):
            blockers = [
                issue for issue in canonical.semantic_integrity_issues
                if issue.material_to_compliance and issue.requirement_id == rid
            ]
            if blockers:
                source = next((r for r in canonical.requirements if r.requirement_id == rid), None)
                unresolved_requirement_context.append({
                    "requirement_id": rid,
                    "requirement_text": (source.raw_source_text or source.requirement_text) if source else "",
                    "status": "STRUCTURED_SEMANTICS_UNRESOLVED",
                    "issues": [x.model_dump(mode="json") for x in blockers],
                })

        verified_evidence = []
        diagnostics = []
        historical = []
        unresolved = []
        evidence_by_id = {e.id: e for e in canonical.evidence_inventory}

        for ann in preparation.evidence_annotations:
            item = evidence_by_id.get(ann.evidence_id)
            for fact in ann.facts:
                base = {
                    "evidence_id": ann.evidence_id,
                    "fact_id": fact.fact_id,
                    "subject": fact.subject,
                    "operator": fact.operator.value,
                    "value": fact.value,
                    "numeric_value": fact.numeric_value,
                    "numeric_unit": fact.numeric_unit,
                    "temporal_semantics": fact.temporal_semantics.value,
                    "scope_resolution": fact.scope.resolution.value,
                    "scope_id": fact.scope.scope_id,
                    "related_requirement_ids": list(fact.related_requirement_ids),
                    "possible_roles": [x.value for x in fact.possible_roles],
                }
                if fact.resolution == SemanticResolution.VERIFIED:
                    verified_evidence.append(base)
                    # Canonical source classification is authoritative.  The
                    # model's possible_roles are supplementary and are not
                    # required to rediscover an already-known source class.
                    if item is not None and item.source == "Current BZD / Diagnostics":
                        diagnostics.append(base)
                    if item is not None and item.evidence_class == EvidenceClass.HISTORICAL_EVIDENCE:
                        historical.append(base)
                else:
                    unresolved.append(base)

        # Canonical direct observations are already deterministic structured
        # evidence. Include the ones actually referenced by deterministic
        # requirement results/route even when no language annotation exists, so
        # RCA synthesis does not lose an explicit current-case mechanism fact.
        referenced_evidence_ids: Set[str] = set(route.supporting_evidence_ids)
        for rr in validated.requirement_results:
            referenced_evidence_ids.update(rr.analysis.applicability_evidence_ids)
            referenced_evidence_ids.update(rr.analysis.evaluation_evidence_ids)
        already_packeted = {x.get("evidence_id", "") for x in verified_evidence}
        for item in canonical.evidence_inventory:
            if (
                item.id in referenced_evidence_ids
                and item.id not in already_packeted
                and item.evidence_class == EvidenceClass.DIRECT_OBSERVATION
                and item.signal_name.strip()
                and item.signal_value.strip()
                and item.observation_type.value != "UNSPECIFIED"
            ):
                verified_evidence.append({
                    "evidence_id": item.id,
                    "fact_id": "",
                    "source_kind": "CANONICAL_STRUCTURAL_DIRECT_OBSERVATION",
                    "subject": item.signal_name,
                    "value": item.signal_value,
                    "observation_type": item.observation_type.value,
                    "timestamp_seconds": item.timestamp_seconds,
                    "clock_id": item.clock_id,
                    "transition_from": item.transition_from,
                    "transition_to": item.transition_to,
                    "event_coverage_complete": item.event_coverage_complete,
                    "coverage_complete": item.coverage_complete,
                })
                already_packeted.add(item.id)

        deterministic_facts = []
        for rr in validated.requirement_results:
            deterministic_facts.append({
                "requirement_id": rr.analysis.requirement_id,
                "applicability": rr.analysis.applicability.value,
                "evaluation_status": rr.evaluation_status.value,
                "applicability_evidence_ids": list(rr.analysis.applicability_evidence_ids),
                "evaluation_evidence_ids": list(rr.analysis.evaluation_evidence_ids),
                "timing_fact": rr.timing_fact.model_dump(mode="json") if rr.timing_fact else None,
            })

        compact_requirement_results = []
        for rr in validated.requirement_results:
            compact_requirement_results.append({
                "requirement_id": rr.analysis.requirement_id,
                "normative_type": rr.analysis.normative_type.value,
                "applicability": rr.analysis.applicability.value,
                "evaluation_status": rr.evaluation_status.value,
                "applicability_evidence_ids": list(rr.analysis.applicability_evidence_ids),
                "evaluation_evidence_ids": list(rr.analysis.evaluation_evidence_ids),
                "timing_fact": rr.timing_fact.model_dump(mode="json") if rr.timing_fact else None,
            })

        return RCAEvidencePacket(
            ticket_id=canonical.ticket_id,
            affected_functionality=validated.semantic.affected_functionality,
            requirement_results=compact_requirement_results,
            requirement_irs=requirement_irs,
            verified_evidence=verified_evidence,
            deterministic_facts=deterministic_facts,
            diagnostics=diagnostics,
            historical=historical,
            unresolved_requirement_context=unresolved_requirement_context,
            unresolved_rca_context=unresolved,
            selected_source_excerpts=[],
        )
