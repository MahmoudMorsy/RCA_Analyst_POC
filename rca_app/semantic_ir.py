from __future__ import annotations

import copy
from typing import Dict, Iterable, List, Optional, Set

from .models import (
    CanonicalCase,
    EvidenceSemanticAnnotation,
    EvidenceSemanticRole,
    LogicExpression,
    LogicKind,
    RequirementIR,
    ScopeResolution,
    SemanticArbitrationResponse,
    SemanticClauseRole,
    SemanticIntegrityIssue,
    SemanticPreparation,
    SemanticResolution,
    TemporalSemantics,
)


MATERIAL_CLAUSE_ROLES = {
    SemanticClauseRole.CONDITION,
    SemanticClauseRole.TRIGGER,
    SemanticClauseRole.REQUIRED_BEHAVIOR,
    SemanticClauseRole.TIMING,
    SemanticClauseRole.PERSISTENCE,
    SemanticClauseRole.RELATIONSHIP,
    SemanticClauseRole.EXCEPTION,
}

MATERIAL_EVIDENCE_ROLES = {
    EvidenceSemanticRole.APPLICABILITY,
    EvidenceSemanticRole.TRIGGER,
    EvidenceSemanticRole.RESPONSE,
    EvidenceSemanticRole.TIMING,
}


class SemanticIntegrityChecker:
    """Structural verifier for LLM-produced semantic objects.

    It deliberately does *not* interpret natural language. It validates IDs,
    provenance/source-span grounding, compiler self-coverage, unresolved fields,
    and dependency links already produced by the semantic compiler.
    """

    @staticmethod
    def _norm(text: str) -> str:
        return " ".join((text or "").split()).strip().lower()

    @classmethod
    def _span_supported(cls, source_text: str, phrase: str) -> bool:
        phrase = (phrase or "").strip()
        if not phrase:
            return True
        return cls._norm(phrase) in cls._norm(source_text)

    @classmethod
    def _logic_ids(cls, node: Optional[LogicExpression]) -> Set[str]:
        if node is None:
            return set()
        out = {node.semantic_id} if node.semantic_id else set()
        for child in node.children:
            out.update(cls._logic_ids(child))
        return out

    @classmethod
    def _condition_leaf_ids(cls, node: Optional[LogicExpression]) -> List[str]:
        if node is None:
            return []
        if node.kind == LogicKind.PREDICATE:
            return [node.semantic_id]
        out: List[str] = []
        for child in node.children:
            out.extend(cls._condition_leaf_ids(child))
        return out

    @classmethod
    def _represented_semantic_ids(cls, ir: RequirementIR) -> Set[str]:
        out = cls._logic_ids(ir.condition)
        for item in (ir.trigger, ir.required_behavior, ir.timing, ir.persistence):
            if item is not None and item.semantic_id:
                out.add(item.semantic_id)
        for rel in ir.relationships:
            if rel.semantic_id:
                out.add(rel.semantic_id)
        return out

    @classmethod
    def structural_requirement_issues(cls, preparation: SemanticPreparation) -> List[SemanticIntegrityIssue]:
        """Return transport-level Requirement IR defects without reading source language.

        These defects are eligible for one cheap targeted 4B recompilation before
        the independent semantic verifier and any 27B arbitration. Python does
        not infer the missing semantics; it merely detects that an already
        emitted structured object is not executable.
        """
        issues: List[SemanticIntegrityIssue] = []
        seq = 1

        def add(ir: RequirementIR, description: str, semantic_id: str = ""):
            nonlocal seq
            issues.append(SemanticIntegrityIssue(
                issue_id=f"STRUCT-{seq:03d}",
                requirement_id=ir.requirement_id,
                semantic_id=semantic_id,
                description=description,
                material_to_compliance=True,
            ))
            seq += 1

        def walk(ir: RequirementIR, node: Optional[LogicExpression]):
            if node is None:
                return
            if node.kind == LogicKind.PREDICATE:
                if not node.signal.strip():
                    add(ir, "Requirement condition PREDICATE is missing signal.", node.semantic_id)
                if node.operator.value == "OTHER":
                    add(ir, "Requirement condition PREDICATE is missing an executable operator.", node.semantic_id)
                if node.children:
                    add(ir, "Requirement condition PREDICATE must not contain child logic nodes.", node.semantic_id)
            elif node.kind == LogicKind.NOT:
                if len(node.children) != 1:
                    add(ir, "Requirement condition NOT node must contain exactly one child.", node.semantic_id)
            elif node.kind in {LogicKind.AND, LogicKind.OR}:
                if len(node.children) < 2:
                    add(ir, f"Requirement condition {node.kind.value} node must contain at least two children.", node.semantic_id)
            elif node.kind == LogicKind.TRUE and node.children:
                add(ir, "Requirement condition TRUE node must not contain children.", node.semantic_id)
            for child in node.children:
                walk(ir, child)

        for ir in preparation.requirement_irs:
            walk(ir, ir.condition)
            if ir.trigger is not None:
                if not ir.trigger.signal.strip():
                    add(ir, "Requirement trigger object is missing signal.", ir.trigger.semantic_id)
                if not ir.trigger.event.strip():
                    add(ir, "Requirement trigger object is missing event semantics.", ir.trigger.semantic_id)
            if ir.required_behavior is not None:
                if not ir.required_behavior.signal.strip() and not ir.required_behavior.process_description.strip():
                    add(ir, "Requirement required_behavior object is missing signal/process description.", ir.required_behavior.semantic_id)
            if ir.timing is not None and ir.timing.limit_ms is None:
                add(ir, "Requirement timing object is missing limit_ms.", ir.timing.semantic_id)
        return issues

    @classmethod
    def structural_evidence_issues(cls, preparation: SemanticPreparation) -> List[SemanticIntegrityIssue]:
        """Return structured evidence defects eligible for one targeted 4B reannotation.

        Python does not interpret the evidence prose here.  It only checks
        whether the LLM-produced object has the explicit fields needed for safe
        deterministic use.  In particular, persistent natural-language evidence
        is not executable merely because ``resolution=RESOLVED``; it also needs a
        concrete non-empty ``scope_id`` supplied by the semantic annotator.
        """
        issues: List[SemanticIntegrityIssue] = []
        seq = 1

        def add(ann: EvidenceSemanticAnnotation, fact_id: str, description: str, material: bool):
            nonlocal seq
            issues.append(SemanticIntegrityIssue(
                issue_id=f"EVSTRUCT-{seq:03d}",
                evidence_id=ann.evidence_id,
                semantic_id=fact_id,
                description=description,
                material_to_compliance=material,
            ))
            seq += 1

        for ann in preparation.evidence_annotations:
            material_ann = any(
                bool(set(fact.possible_roles) & MATERIAL_EVIDENCE_ROLES) or bool(fact.related_requirement_ids)
                for fact in ann.facts
            )
            if (
                ann.resolution != SemanticResolution.VERIFIED
                and ann.facts
                and not ann.unresolved_semantics
                and all(fact.resolution == SemanticResolution.VERIFIED for fact in ann.facts)
            ):
                add(
                    ann, "",
                    "Evidence annotation transport did not establish a VERIFIED annotation-level resolution despite fully VERIFIED facts.",
                    material_ann,
                )
            for fact in ann.facts:
                material = (
                    bool(set(fact.possible_roles) & MATERIAL_EVIDENCE_ROLES)
                    or bool(fact.related_requirement_ids)
                    or (fact.temporal_semantics == TemporalSemantics.PERSISTENT_STATE and bool(fact.subject.strip()))
                )
                if material and not fact.subject.strip():
                    add(ann, fact.fact_id, "Material evidence fact is missing subject.", True)
                if (
                    fact.temporal_semantics == TemporalSemantics.PERSISTENT_STATE
                    and fact.scope.resolution == ScopeResolution.RESOLVED
                    and not fact.scope.scope_id.strip()
                ):
                    add(
                        ann, fact.fact_id,
                        "Persistent natural-language evidence claims RESOLVED scope but has no concrete scope_id.",
                        material,
                    )
        return issues

    @classmethod
    def validate(cls, canonical: CanonicalCase, preparation: SemanticPreparation) -> List[SemanticIntegrityIssue]:
        issues: List[SemanticIntegrityIssue] = []
        req_sources = {r.requirement_id: r for r in canonical.requirements}
        irs = {r.requirement_id: r for r in preparation.requirement_irs}
        evidence = {e.id: e for e in canonical.evidence_inventory}

        seq = 1

        def add(description: str, *, requirement_id: str = "", evidence_id: str = "", semantic_id: str = "", material: bool = False):
            nonlocal seq
            issues.append(SemanticIntegrityIssue(
                issue_id=f"SEM-{seq:03d}",
                requirement_id=requirement_id,
                evidence_id=evidence_id,
                semantic_id=semantic_id,
                description=description,
                material_to_compliance=material,
            ))
            seq += 1

        for structural in cls.structural_requirement_issues(preparation):
            add(
                structural.description,
                requirement_id=structural.requirement_id,
                semantic_id=structural.semantic_id,
                material=True,
            )
        for structural in cls.structural_evidence_issues(preparation):
            add(
                structural.description,
                evidence_id=structural.evidence_id,
                semantic_id=structural.semantic_id,
                material=structural.material_to_compliance,
            )

        for rid in req_sources:
            if rid not in irs:
                add("Semantic compiler returned no Requirement IR for an authoritative requirement.", requirement_id=rid, material=True)
        for rid in irs:
            if rid not in req_sources:
                add("Semantic compiler returned an unknown requirement ID.", requirement_id=rid, material=True)

        for rid, ir in irs.items():
            src = req_sources.get(rid)
            if src is None:
                continue
            represented = cls._represented_semantic_ids(ir)
            if not ir.source_clauses:
                add("Requirement IR is missing the compiler source-clause audit inventory.", requirement_id=rid, material=True)
            for semantic_id in cls._condition_leaf_ids(ir.condition):
                if not semantic_id:
                    add("Requirement condition predicate is missing semantic_id/source-clause linkage.", requirement_id=rid, material=True)
            for label, item in (("trigger", ir.trigger), ("required behavior", ir.required_behavior), ("timing", ir.timing), ("persistence", ir.persistence)):
                if item is not None and not item.semantic_id:
                    add(f"Requirement {label} is missing semantic_id/source-clause linkage.", requirement_id=rid, material=True)
            for rel in ir.relationships:
                if not rel.semantic_id:
                    add("Requirement relationship is missing semantic_id/source-clause linkage.", requirement_id=rid, material=True)
            seen_clause_ids: Set[str] = set()
            for clause in ir.source_clauses:
                if clause.semantic_id in seen_clause_ids:
                    add("Duplicate semantic_id in requirement source-clause inventory.", requirement_id=rid, semantic_id=clause.semantic_id, material=True)
                seen_clause_ids.add(clause.semantic_id)
                if not cls._span_supported(src.requirement_text, clause.source_phrase):
                    add("Requirement semantic source phrase is not grounded in the authoritative requirement text.", requirement_id=rid, semantic_id=clause.semantic_id, material=clause.role in MATERIAL_CLAUSE_ROLES)
                if clause.resolution != SemanticResolution.VERIFIED:
                    add(
                        f"Requirement clause remains {clause.resolution.value}: {clause.notes or clause.source_phrase}",
                        requirement_id=rid,
                        semantic_id=clause.semantic_id,
                        material=clause.role in MATERIAL_CLAUSE_ROLES,
                    )
                if clause.role in MATERIAL_CLAUSE_ROLES and clause.semantic_id not in represented:
                    add("Compiler source-clause inventory contains a material clause that is not represented in the Requirement IR.", requirement_id=rid, semantic_id=clause.semantic_id, material=True)

            missing_audit_ids = sorted(x for x in represented if x not in seen_clause_ids)
            for semantic_id in missing_audit_ids:
                add("Requirement IR semantic element has no matching source-clause audit entry.", requirement_id=rid, semantic_id=semantic_id, material=True)

            for phrase in ir.unmapped_source_spans:
                if not cls._span_supported(src.requirement_text, phrase):
                    add("Compiler reported an unmapped requirement span that is not grounded in the source text.", requirement_id=rid, material=True)
                else:
                    add(f"Material requirement source span remains unmapped: {phrase}", requirement_id=rid, material=True)
            for note in ir.unresolved_semantics:
                add(f"Requirement semantic ambiguity remains unresolved: {note}", requirement_id=rid, material=True)

            if ir.normative_type.value in {"MANDATORY", "PROHIBITIVE"} and ir.required_behavior is None:
                add("Obligatory Requirement IR has no required_behavior object.", requirement_id=rid, material=True)
            if ir.timing is not None and ir.trigger is None:
                add("Timed Requirement IR has no trigger object.", requirement_id=rid, material=True)

        for ann in preparation.evidence_annotations:
            item = evidence.get(ann.evidence_id)
            if item is None:
                add("Evidence annotation references an unknown canonical evidence ID.", evidence_id=ann.evidence_id, material=True)
                continue
            if ann.resolution != SemanticResolution.VERIFIED:
                material = any(
                    role in MATERIAL_EVIDENCE_ROLES
                    for fact in ann.facts for role in fact.possible_roles
                ) or any(fact.related_requirement_ids for fact in ann.facts)
                add(f"Evidence annotation remains {ann.resolution.value}.", evidence_id=ann.evidence_id, material=material)
            for fact in ann.facts:
                if not cls._span_supported(item.raw_source_text or item.text, fact.source_phrase):
                    add("Evidence semantic source phrase is not grounded in its canonical evidence item.", evidence_id=ann.evidence_id, semantic_id=fact.fact_id, material=True)
                material = bool(set(fact.possible_roles) & MATERIAL_EVIDENCE_ROLES) or bool(fact.related_requirement_ids)
                if fact.resolution != SemanticResolution.VERIFIED:
                    add(f"Evidence fact remains {fact.resolution.value}: {fact.notes or fact.source_phrase}", evidence_id=ann.evidence_id, semantic_id=fact.fact_id, material=material)
                if fact.scope.resolution in {ScopeResolution.UNRESOLVED, ScopeResolution.PARTIAL}:
                    add(
                        f"Evidence scope remains {fact.scope.resolution.value}: {fact.scope.source_phrase or fact.notes}",
                        evidence_id=ann.evidence_id,
                        semantic_id=fact.fact_id,
                        material=material,
                    )
            for note in ann.unresolved_semantics:
                add(f"Evidence semantic ambiguity remains unresolved: {note}", evidence_id=ann.evidence_id, material=True)

        for note in preparation.unresolved_case_semantics:
            add(f"Case-level semantic ambiguity remains unresolved: {note}", material=True)

        # Dependency-based materiality without reading language: if a fact's
        # subject is used by an IR and its scope is unresolved, it can block that
        # requirement even when the compiler omitted explicit related IDs.
        subjects_by_req: Dict[str, Set[str]] = {}
        for ir in preparation.requirement_irs:
            subjects: Set[str] = set()
            cls._collect_logic_signals(ir.condition, subjects)
            if ir.trigger and ir.trigger.signal:
                subjects.add(ir.trigger.signal.lower())
            if ir.required_behavior and ir.required_behavior.signal:
                subjects.add(ir.required_behavior.signal.lower())
            subjects_by_req[ir.requirement_id] = subjects

        material_keys = {(i.evidence_id, i.semantic_id) for i in issues if i.material_to_compliance}
        for ann in preparation.evidence_annotations:
            for fact in ann.facts:
                if fact.scope.resolution not in {ScopeResolution.UNRESOLVED, ScopeResolution.PARTIAL} or not fact.subject:
                    continue
                impacted = [rid for rid, subjects in subjects_by_req.items() if fact.subject.lower() in subjects]
                key = (ann.evidence_id, fact.fact_id)
                if impacted and key not in material_keys:
                    add(
                        "Unresolved evidence scope lies on a structured dependency used by requirement(s): " + ", ".join(impacted),
                        evidence_id=ann.evidence_id,
                        semantic_id=fact.fact_id,
                        material=True,
                    )

        return issues

    @classmethod
    def _collect_logic_signals(cls, node: Optional[LogicExpression], out: Set[str]) -> None:
        if node is None:
            return
        if node.kind == LogicKind.PREDICATE and node.signal:
            out.add(node.signal.lower())
        for child in node.children:
            cls._collect_logic_signals(child, out)

    @staticmethod
    def material_issues(issues: Iterable[SemanticIntegrityIssue]) -> List[SemanticIntegrityIssue]:
        return [x for x in issues if x.material_to_compliance]


class SemanticArbitrationMerger:
    """Merge one case-level arbitration response without semantic inference."""

    @staticmethod
    def apply(preparation: SemanticPreparation, arbitration: SemanticArbitrationResponse) -> SemanticPreparation:
        out = copy.deepcopy(preparation)
        req_updates = {x.requirement_id: x for x in arbitration.requirement_irs}
        out.requirement_irs = [copy.deepcopy(req_updates.get(x.requirement_id, x)) for x in out.requirement_irs]
        known_req = {x.requirement_id for x in out.requirement_irs}
        out.requirement_irs.extend(copy.deepcopy(x) for x in arbitration.requirement_irs if x.requirement_id not in known_req)

        ann_updates = {x.evidence_id: x for x in arbitration.evidence_annotations}
        out.evidence_annotations = [copy.deepcopy(ann_updates.get(x.evidence_id, x)) for x in out.evidence_annotations]
        known_ev = {x.evidence_id for x in out.evidence_annotations}
        out.evidence_annotations.extend(copy.deepcopy(x) for x in arbitration.evidence_annotations if x.evidence_id not in known_ev)
        return out
