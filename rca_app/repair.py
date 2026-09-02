from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .models import (
    Applicability,
    EvidenceNeed,
    RepairRoute,
    RequirementElementType,
    SemanticAnalysis,
    Sufficiency,
    ValidationIssue,
)


# v0.5.5 production repair policies, promoted from the validated v1.8
# fast-repair harness. Unknown defects intentionally escalate to the primary
# model rather than granting the 4B model broader authority.
REPAIR_POLICIES: dict[str, dict[str, Any]] = {
    # Fast-model field patches.
    "APPLICABILITY_NEED_IN_EVALUATION_BUCKET": {
        "route": RepairRoute.FAST_MODEL,
        "fields": ["missing_evaluation_evidence"],
        "instruction": "Correct the evaluation-evidence need. Applicability is already established separately; classify only what evidence is still missing to evaluate the required behavior.",
    },
    "NONEXISTENT_TRIGGER_IN_EVALUATION_BUCKET": {
        "route": RepairRoute.FAST_MODEL,
        "fields": ["missing_evaluation_evidence"],
        "instruction": "This IF-condition is an applicability condition, not a trigger. Remove the nonexistent trigger need and request only evidence needed to evaluate the required behavior.",
    },
    "EVALUATION_NEED_TARGET_MISMATCH": {
        "route": RepairRoute.FAST_MODEL,
        "fields": ["missing_evaluation_evidence"],
        "instruction": "The current Evaluation Evidence request targets an applicability/trigger signal instead of the unresolved required behavior, or asks again for evidence that is already supplied. Rewrite only missing_evaluation_evidence so it requests the still-missing response/timing/observation-interval evidence for the required behavior.",
    },
    "CONDITIONAL_CONVERSE_RISK": {
        "route": RepairRoute.FAST_MODEL,
        "fields": ["faithful_meaning"],
        "instruction": "Rewrite only faithful_meaning so it preserves the one-way conditional direction. Do not introduce ONLY IF, necessity, exclusivity, or a converse implication.",
    },
    "PERMISSIVE_CONVERSE_RISK": {
        "route": RepairRoute.FAST_MODEL,
        "fields": ["faithful_meaning"],
        "instruction": "Rewrite only faithful_meaning to preserve MAY/permission semantics. The stated condition permits the behavior there; it does not make that condition an exclusive prerequisite unless the source explicitly says so.",
    },
    "INVENTED_PROCESS_CONCEPT": {
        "route": RepairRoute.FAST_MODEL,
        "fields": ["faithful_meaning"],
        "instruction": "Remove invented mechanism/process language and restate only semantics supported by the canonical requirement.",
    },
    "CAUSAL_RELEVANCE_LANGUAGE": {
        "route": RepairRoute.FAST_MODEL,
        "fields": ["relevance"],
        "instruction": "Rewrite only relevance as concise requirement-local descriptive prose. Remove causal explanation, hypothesis, prerequisite, or alternative-cause language.",
    },
    "INTERNAL_RULE_ID_LEAK": {
        "route": RepairRoute.FAST_MODEL,
        "fields": ["faithful_meaning"],
        "instruction": "Remove the internal validator/control-rule identifier from faithful_meaning while preserving the actual requirement meaning.",
    },
    "RELEVANT_OBSERVATION_NOT_MAPPED": {
        "route": RepairRoute.FAST_MODEL,
        "fields": ["evaluation_evidence_ids"],
        "instruction": "Map only the supplied current-case observation ID(s) that directly concern the required behavior. Do not invent evidence or change applicability.",
    },

    # Deterministic repairs: mechanically implied by already-decomposed fields.
    "OBLIGATORY_SUFFICIENCY_NOT_REQUIRED_INVALID": {
        "route": RepairRoute.DETERMINISTIC,
        "fields": ["evaluation_sufficiency"],
        "instruction": "For an applicable MANDATORY/PROHIBITIVE requirement with explicit missing evaluation evidence, NOT_REQUIRED is mechanically invalid; set evaluation_sufficiency to INSUFFICIENT.",
    },
    "MISSING_TRIGGER_APPLICABILITY_NEED": {
        "route": RepairRoute.DETERMINISTIC,
        "fields": ["missing_applicability_evidence"],
        "instruction": "Add the already-decomposed trigger as missing applicability evidence.",
    },
    "MISSING_CONDITION_APPLICABILITY_NEED": {
        "route": RepairRoute.DETERMINISTIC,
        "fields": ["missing_applicability_evidence"],
        "instruction": "Add the already-decomposed condition as missing applicability evidence.",
    },
    "MISSING_RESPONSE_EVALUATION_NEED": {
        "route": RepairRoute.DETERMINISTIC,
        "fields": ["missing_evaluation_evidence"],
        "instruction": "Add a missing response/state observation need directly from required_behavior.",
    },
    "MISSING_TIMING_EVALUATION_NEED": {
        "route": RepairRoute.DETERMINISTIC,
        "fields": ["missing_evaluation_evidence"],
        "instruction": "Add a timing-window evidence need directly from timing_constraint.",
    },
    "MISSING_TRIGGER_TIMESTAMP_NEED": {
        "route": RepairRoute.DETERMINISTIC,
        "fields": ["missing_evaluation_evidence"],
        "instruction": "Require a timestamp for the already-decomposed trigger.",
    },
    "MISSING_PERSISTENCE_EVALUATION_NEED": {
        "route": RepairRoute.DETERMINISTIC,
        "fields": ["missing_evaluation_evidence"],
        "instruction": "Add an observation-interval need directly from the persistence semantics.",
    },

    # Core semantic decomposition remains primary-model authority.
    "MISSING_REQUIREMENT_ANALYSIS": {"route": RepairRoute.PRIMARY_MODEL, "fields": [], "instruction": "Reconstruct the missing requirement analysis from the canonical requirement."},
    "UNKNOWN_REQUIREMENT_ANALYSIS": {"route": RepairRoute.PRIMARY_MODEL, "fields": [], "instruction": "Resolve the requirement analysis using the canonical requirement and evidence."},
    "DUPLICATE_REQUIREMENT_ID": {"route": RepairRoute.PRIMARY_MODEL, "fields": [], "instruction": "Reconstruct the requirement set without duplicate semantic objects."},
    "MISSING_REQUIRED_BEHAVIOR": {"route": RepairRoute.PRIMARY_MODEL, "fields": ["required_behavior"], "instruction": "Reconstruct the normative required behavior from the canonical requirement text."},
    "MISSING_APPLICABILITY_CONDITION": {"route": RepairRoute.PRIMARY_MODEL, "fields": ["applicability_condition"], "instruction": "Reconstruct the explicit applicability condition from the canonical requirement text."},
    "MISSING_TRIGGER_DECOMPOSITION": {"route": RepairRoute.PRIMARY_MODEL, "fields": ["trigger"], "instruction": "Reconstruct the exact trigger semantics from the canonical requirement text."},
    "MISSING_TIMING_DECOMPOSITION": {"route": RepairRoute.PRIMARY_MODEL, "fields": ["timing_constraint"], "instruction": "Restore the explicit timing constraint from the canonical requirement text."},
    "MISSING_PERSISTENCE_DECOMPOSITION": {"route": RepairRoute.DETERMINISTIC, "fields": ["observation_interval_requirement"], "instruction": "Restore an explicit neutral observation-interval requirement from mechanically visible remain/shall-not/never wording in the canonical requirement."},
    "TIMING_WITHOUT_TRIGGER": {"route": RepairRoute.PRIMARY_MODEL, "fields": ["trigger", "timing_constraint"], "instruction": "Repair the trigger/timing decomposition from the canonical requirement text."},
    "HISTORICAL_SOURCE_UNACCOUNTED": {
        "route": RepairRoute.PRIMARY_MODEL,
        "fields": [],
        "instruction": "Account for every supplied historical ticket as precedent. Compare it to current evidence without copying the historical root cause. If positive current-case evidence independently supports a mechanism also seen historically, represent only that supported mechanism as a hypothesis.",
    },
    "EXPLICIT_RELATIONSHIP_UNACCOUNTED": {
        "route": RepairRoute.PRIMARY_MODEL,
        "fields": ["explicit_relationships"],
        "instruction": "Restore the explicit supplied relationship/scope statement into explicit_relationships without inventing additional hierarchy.",
    },
}


@dataclass
class RepairTask:
    requirement_id: str
    route: RepairRoute
    allowed_fields: list[str] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)

    @property
    def issue_codes(self) -> list[str]:
        return sorted({x.code for x in self.issues})

    @property
    def signature(self) -> tuple:
        return (self.requirement_id, self.route.value, tuple(self.allowed_fields), tuple(self.issue_codes))


class RepairRouter:
    """Build least-authority repair tasks from deterministic validator errors."""

    def build_plan(
        self,
        semantic: SemanticAnalysis,
        issues: Sequence[ValidationIssue],
        fast_model_available: bool,
    ) -> list[RepairTask]:
        raw: list[RepairTask] = []
        scoped = [self.requirement_id_for_issue(semantic, issue) for issue in issues]
        scoped = [x for x in scoped if x]
        fallback_rid = scoped[0] if len(set(scoped)) == 1 else ""

        for issue in issues:
            rid = self.requirement_id_for_issue(semantic, issue) or fallback_rid
            policy = REPAIR_POLICIES.get(issue.code)
            if policy is None:
                route = RepairRoute.PRIMARY_MODEL
                fields: list[str] = []
                instruction = "Validation error is not in the deterministic/fast allowlist; escalate for primary semantic repair."
            else:
                route = policy["route"]
                fields = list(policy.get("fields", []))
                instruction = str(policy.get("instruction", ""))
                if route == RepairRoute.FAST_MODEL and not fast_model_available:
                    route = RepairRoute.PRIMARY_MODEL
                    fields = []
                    instruction = "Fast repair model is unavailable; escalate this narrow semantic defect to the primary model."
            raw.append(RepairTask(rid, route, fields, [issue], [instruction]))

        grouped: list[RepairTask] = []
        for item in raw:
            existing = next(
                (
                    x for x in grouped
                    if x.requirement_id == item.requirement_id
                    and x.route == item.route
                    and x.allowed_fields == item.allowed_fields
                ),
                None,
            )
            if existing is None:
                grouped.append(item)
            else:
                existing.issues.extend(item.issues)
                existing.instructions.extend(item.instructions)

        rank = {RepairRoute.DETERMINISTIC: 0, RepairRoute.FAST_MODEL: 1, RepairRoute.PRIMARY_MODEL: 2}
        grouped.sort(key=lambda x: (rank.get(x.route, 99), x.requirement_id, tuple(x.allowed_fields)))
        return grouped

    @staticmethod
    def route(issues: Iterable[ValidationIssue], fast_model_available: bool) -> RepairRoute:
        # Compatibility helper used by older tests/callers.
        issue_list = list(issues)
        if not issue_list:
            return RepairRoute.PRIMARY_MODEL
        routes = []
        for issue in issue_list:
            policy = REPAIR_POLICIES.get(issue.code)
            route = policy["route"] if policy else RepairRoute.PRIMARY_MODEL
            if route == RepairRoute.FAST_MODEL and not fast_model_available:
                route = RepairRoute.PRIMARY_MODEL
            routes.append(route)
        if RepairRoute.PRIMARY_MODEL in routes:
            return RepairRoute.PRIMARY_MODEL
        if RepairRoute.FAST_MODEL in routes:
            return RepairRoute.FAST_MODEL
        return RepairRoute.DETERMINISTIC

    @staticmethod
    def requirement_id_for_issue(semantic: SemanticAnalysis, issue: ValidationIssue) -> str:
        m = re.search(r"semantic\.requirements\[(\d+)\]", issue.path or "")
        if not m:
            return ""
        idx = int(m.group(1))
        if 0 <= idx < len(semantic.requirements):
            return semantic.requirements[idx].requirement_id
        return ""

    @staticmethod
    def deterministic_codes() -> set[str]:
        return {code for code, p in REPAIR_POLICIES.items() if p["route"] == RepairRoute.DETERMINISTIC}


class DeterministicRepairEngine:
    """Conservative validator-owned repair of mechanically implied fields."""

    def apply_task(self, semantic: SemanticAnalysis, task: RepairTask) -> tuple[SemanticAnalysis, list[str]]:
        if task.route != RepairRoute.DETERMINISTIC:
            return copy.deepcopy(semantic), []
        out = copy.deepcopy(semantic)
        if not task.requirement_id:
            return out, []
        req = next((r for r in out.requirements if r.requirement_id == task.requirement_id), None)
        if req is None:
            return out, []

        changed: list[str] = []
        for issue in task.issues:
            code = issue.code

            if code == "OBLIGATORY_SUFFICIENCY_NOT_REQUIRED_INVALID":
                if (
                    req.applicability != Applicability.NOT_APPLICABLE
                    and req.evaluation_sufficiency == Sufficiency.NOT_REQUIRED
                    and req.missing_evaluation_evidence
                ):
                    req.evaluation_sufficiency = Sufficiency.INSUFFICIENT
                    changed.append("evaluation_sufficiency")

            elif code == "MISSING_TRIGGER_APPLICABILITY_NEED" and req.trigger.strip():
                if not any(n.element == RequirementElementType.TRIGGER for n in req.missing_applicability_evidence):
                    req.missing_applicability_evidence.append(EvidenceNeed(
                        element=RequirementElementType.TRIGGER,
                        description=f"Current-case observation establishing that the trigger occurred: {req.trigger.strip()}.",
                    ))
                    changed.append("missing_applicability_evidence")

            elif code == "MISSING_CONDITION_APPLICABILITY_NEED" and req.applicability_condition.strip():
                if not any(n.element == RequirementElementType.APPLICABILITY for n in req.missing_applicability_evidence):
                    req.missing_applicability_evidence.append(EvidenceNeed(
                        element=RequirementElementType.APPLICABILITY,
                        description=f"Current-case observation establishing the applicability condition at the relevant evaluation point: {req.applicability_condition.strip()}.",
                    ))
                    changed.append("missing_applicability_evidence")

            elif code == "MISSING_RESPONSE_EVALUATION_NEED" and req.required_behavior.strip():
                if not any(n.element in {RequirementElementType.RESPONSE, RequirementElementType.OBSERVATION_INTERVAL} for n in req.missing_evaluation_evidence):
                    req.missing_evaluation_evidence.append(EvidenceNeed(
                        element=RequirementElementType.RESPONSE,
                        description=f"Observe the required response/state: {req.required_behavior.strip()}.",
                    ))
                    changed.append("missing_evaluation_evidence")

            elif code == "MISSING_TIMING_EVALUATION_NEED" and req.timing_constraint.strip():
                if not any(n.element == RequirementElementType.TIMING for n in req.missing_evaluation_evidence):
                    req.missing_evaluation_evidence.append(EvidenceNeed(
                        element=RequirementElementType.TIMING,
                        description=f"Provide timing-window coverage sufficient to evaluate {req.timing_constraint.strip()}, with an alignable timebase where needed.",
                    ))
                    changed.append("missing_evaluation_evidence")

            elif code == "MISSING_TRIGGER_TIMESTAMP_NEED" and req.trigger.strip():
                trigger_needs = [n for n in req.missing_evaluation_evidence if n.element == RequirementElementType.TRIGGER]
                if trigger_needs:
                    local_change = False
                    for need in trigger_needs:
                        if not re.search(r"timestamp|time\s*stamp", need.description, re.I):
                            need.description = need.description.rstrip(". ") + ", with timestamp."
                            local_change = True
                    if local_change:
                        changed.append("missing_evaluation_evidence")
                else:
                    req.missing_evaluation_evidence.append(EvidenceNeed(
                        element=RequirementElementType.TRIGGER,
                        description=f"Timestamped observation establishing the trigger occurrence: {req.trigger.strip()}.",
                    ))
                    changed.append("missing_evaluation_evidence")

            elif code == "MISSING_PERSISTENCE_EVALUATION_NEED":
                if not any(n.element == RequirementElementType.OBSERVATION_INTERVAL for n in req.missing_evaluation_evidence):
                    req.missing_evaluation_evidence.append(EvidenceNeed(
                        element=RequirementElementType.OBSERVATION_INTERVAL,
                        description=f"INTERVAL_STATE evidence establishing {self._clean_behavior(req.required_behavior)} throughout the applicable interval.",
                    ))
                    changed.append("missing_evaluation_evidence")

            elif code == "MISSING_PERSISTENCE_DECOMPOSITION":
                source = " ".join((req.requirement_text or "").split())
                if (
                    not req.observation_interval_requirement.strip()
                    and re.search(r"\bremain(?:s|ed|ing)?\b|\bstay(?:s|ed|ing)?\b|\bthroughout\b|\bshall\s+not\b|\bmust\s+not\b|\bnever\b", source, re.I)
                ):
                    basis = req.applicability_condition.strip() or req.trigger.strip() or "the applicable condition/scope"
                    behavior = self._clean_behavior(req.required_behavior) or "the required state/non-occurrence"
                    req.observation_interval_requirement = f"Evaluate {behavior} throughout the interval in which {basis} applies."
                    changed.append("observation_interval_requirement")

        out = SemanticAnalysis.model_validate(out.model_dump(mode="json"))
        return out, sorted(set(changed))

    def apply(self, semantic: SemanticAnalysis, issues: Iterable[ValidationIssue]) -> tuple[SemanticAnalysis, list[str]]:
        """Backward-compatible batch helper for deterministic-only callers."""
        data = copy.deepcopy(semantic)
        applied_codes: list[str] = []
        router = RepairRouter()
        for task in router.build_plan(data, list(issues), fast_model_available=True):
            if task.route != RepairRoute.DETERMINISTIC:
                continue
            data, changed = self.apply_task(data, task)
            if changed:
                applied_codes.extend(task.issue_codes)
        return data, applied_codes

    @staticmethod
    def _clean_behavior(text: str) -> str:
        return re.sub(r"\s*\((?:persistence|permission)[^)]*\)\s*$", "", text.strip(), flags=re.I)
