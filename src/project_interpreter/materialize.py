from __future__ import annotations

from .analysis_engine import EngineOutput, PROMPT_VERSION
from .ledger import Ledger
from .models import ProjectEvent


def materialize(ledger: Ledger, event: ProjectEvent, output: EngineOutput) -> dict[str, int]:
    result = output.interpretation
    counts = {"analysis": 0, "decision": 0, "assumption": 0, "question": 0, "warning": 0}
    analysis_payload = result.as_dict()
    analysis_payload.update(
        {
            "provider": output.provider,
            "model": output.model,
            "fallback_reason": output.fallback_reason,
            "prompt_version": PROMPT_VERSION,
        }
    )
    inserted = ledger.add(
        "analysis",
        event.project,
        "current",
        analysis_payload,
        f"analysis:{event.id}:{PROMPT_VERSION}",
        source_id=event.id,
        record_id=Ledger.stable_id("analysis", event.id, PROMPT_VERSION),
    )
    counts["analysis"] += int(inserted)

    decision_status = "provisional" if result.importance >= 3 or result.requires_user_attention else "proposed"
    for text in result.decisions:
        payload = {
            "title": text,
            "explanation": result.plain_summary,
            "rationale": result.agent_understanding or result.plain_summary,
            "importance": result.importance,
            "consequences": result.consequences,
            "alternatives": result.alternatives,
            "evidence_refs": [event.id] + result.evidence_refs,
        }
        inserted = ledger.add(
            "decision",
            event.project,
            decision_status,
            payload,
            f"decision:{event.id}:{Ledger.digest(text)}",
            source_id=event.id,
            record_id=Ledger.stable_id("decision", event.id, text),
        )
        counts["decision"] += int(inserted)

    for text in result.assumptions:
        inserted = ledger.add(
            "assumption",
            event.project,
            "active",
            {"text": text, "evidence_refs": [event.id]},
            f"assumption:{event.id}:{Ledger.digest(text)}",
            source_id=event.id,
            record_id=Ledger.stable_id("assumption", event.id, text),
        )
        counts["assumption"] += int(inserted)

    for text in result.unresolved_questions:
        inserted = ledger.add(
            "question",
            event.project,
            "open",
            {"text": text, "evidence_refs": [event.id]},
            f"question:{event.id}:{Ledger.digest(text)}",
            source_id=event.id,
            record_id=Ledger.stable_id("question", event.id, text),
        )
        counts["question"] += int(inserted)

    if output.fallback_reason:
        payload = {
            "message": "The configured language model failed; deterministic interpretation was used.",
            "detail": output.fallback_reason,
            "event_id": event.id,
        }
        inserted = ledger.add(
            "warning",
            event.project,
            "open",
            payload,
            f"engine-fallback:{event.id}",
            source_id=event.id,
            record_id=Ledger.stable_id("engine-fallback", event.id),
        )
        counts["warning"] += int(inserted)
    return counts
