from __future__ import annotations

from .ledger import Ledger
from .models import Alignment, Constitution, DriftFinding, EventType, Interpretation, ProjectEvent, Severity


def detect_drift(
    event: ProjectEvent,
    interpretation: Interpretation,
    constitution: Constitution,
) -> list[DriftFinding]:
    findings: list[DriftFinding] = []
    evidence = [event.id]

    if event.metadata.get("hash_valid") is False or event.metadata.get("char_count_valid") is False:
        findings.append(
            DriftFinding.create(
                project=event.project,
                severity=Severity.HIGH,
                category="evidence_integrity",
                explanation="A mailbox file did not match its declared checksum or character count.",
                current_direction="The interpreter received evidence whose integrity could not be confirmed.",
                likely_consequence="The source message may be incomplete, altered, or paired with incorrect metadata.",
                evidence_refs=evidence,
                requires_review=True,
            )
        )

    if interpretation.alignment == Alignment.CONFLICT:
        requirements: list[str | None] = (
            list(interpretation.requirements_impacted)
            if interpretation.requirements_impacted
            else [None]
        )
        for requirement in requirements:
            findings.append(
                DriftFinding.create(
                    project=event.project,
                    severity=Severity.HIGH,
                    category="constitution_conflict",
                    explanation=interpretation.alignment_explanation or "The activity conflicts with the project constitution.",
                    original_requirement=requirement,
                    current_direction=interpretation.plain_summary,
                    likely_consequence="Continuing without review could move the project away from an explicit owner requirement.",
                    evidence_refs=evidence,
                    requires_review=True,
                )
            )

    if interpretation.decisions and interpretation.importance >= 4:
        findings.append(
            DriftFinding.create(
                project=event.project,
                severity=Severity.WARNING,
                category="major_decision_needs_review",
                explanation="A consequential decision was detected and has not been explicitly approved by the project owner.",
                current_direction="; ".join(interpretation.decisions[:3]),
                likely_consequence="A provisional implementation choice may become permanent without deliberate review.",
                evidence_refs=evidence,
                requires_review=True,
            )
        )

    if event.event_type == EventType.ARCHITECTURE_DECISION and not interpretation.decisions:
        findings.append(
            DriftFinding.create(
                project=event.project,
                severity=Severity.WARNING,
                category="undocumented_architecture_choice",
                explanation="The event was classified as architectural, but no explicit decision could be extracted.",
                current_direction=interpretation.plain_summary,
                likely_consequence="The project may acquire an important design constraint without a reviewable decision record.",
                evidence_refs=evidence,
                requires_review=True,
            )
        )

    lowered = event.content.lower()
    if event.event_type == EventType.TEST_RESULT and any(term in lowered for term in ("pass", "passed", "green")):
        findings.append(
            DriftFinding.create(
                project=event.project,
                severity=Severity.INFO,
                category="test_scope_limit",
                explanation="Passing tests show that tested behavior matched test expectations; they do not prove the project objective was achieved.",
                current_direction=interpretation.plain_summary,
                likely_consequence="Technical validation could be mistaken for product or strategy validation.",
                evidence_refs=evidence,
                requires_review=False,
            )
        )

    completion_claim = any(term in lowered for term in ("project is complete", "fully complete", "everything is done"))
    evidence_claim = any(term in lowered for term in ("acceptance criteria", "validated against", "end-to-end test"))
    if completion_claim and not evidence_claim:
        findings.append(
            DriftFinding.create(
                project=event.project,
                severity=Severity.WARNING,
                category="completion_evidence_gap",
                explanation="The event claims broad completion without describing evidence against the project's success criteria.",
                current_direction=interpretation.plain_summary,
                likely_consequence="Work may stop after implementation is present but before the intended outcome is demonstrated.",
                evidence_refs=evidence,
                requires_review=True,
            )
        )

    if interpretation.unresolved_questions and interpretation.importance >= 4:
        findings.append(
            DriftFinding.create(
                project=event.project,
                severity=Severity.WARNING,
                category="high_impact_open_question",
                explanation="Important work is proceeding while consequential questions remain unresolved.",
                current_direction="; ".join(interpretation.unresolved_questions[:3]),
                likely_consequence="An agent may silently answer these questions through implementation choices.",
                evidence_refs=evidence,
                requires_review=True,
            )
        )
    return findings


def store_findings(ledger: Ledger, findings: list[DriftFinding]) -> int:
    added = 0
    for finding in findings:
        payload = {
            "severity": finding.severity.value,
            "category": finding.category,
            "explanation": finding.explanation,
            "original_requirement": finding.original_requirement,
            "current_direction": finding.current_direction,
            "likely_consequence": finding.likely_consequence,
            "evidence_refs": finding.evidence_refs,
            "requires_review": finding.requires_review,
        }
        key = "drift:" + Ledger.digest(str(sorted(payload.items())))
        inserted = ledger.add(
            "drift",
            finding.project,
            finding.status,
            payload,
            key,
            source_id=finding.evidence_refs[0] if finding.evidence_refs else None,
            record_id=finding.id,
        )
        added += int(inserted)
    return added
