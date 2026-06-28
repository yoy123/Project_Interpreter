from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Alignment, Constitution, EventType, Interpretation, ProjectEvent


PROMPT_VERSION = "1.0"


@dataclass(slots=True)
class EngineOutput:
    interpretation: Interpretation
    provider: str
    model: str
    fallback_reason: str = ""


class HeuristicEngine:
    name = "deterministic"

    def interpret(self, event: ProjectEvent, constitution: Constitution) -> Interpretation:
        lines = [line.strip(" -*\t") for line in event.content.splitlines() if line.strip()]
        sentences = self._sentences(event.content)
        decisions = self._matching(
            sentences,
            ("decided", "we will", "will use", "chosen", "selected", "implement", "architecture"),
        )
        if event.event_type == EventType.ARCHITECTURE_DECISION and not decisions and sentences:
            decisions = [sentences[0][:600]]
        assumptions = self._matching(
            sentences,
            ("assume", "assuming", "default to", "treated as", "expected to"),
        )
        consequences = self._matching(
            sentences,
            ("this means", "therefore", "as a result", "so that", "consequence"),
        )
        alternatives = self._matching(
            sentences,
            ("instead of", "alternative", "rejected", "rather than"),
        )
        questions = [line for line in lines if line.endswith("?")]
        importance = self._importance(event.event_type, decisions)
        alignment, explanation, impacted = self._alignment(event.content, constitution)
        summary = self._summary(event, lines)
        user_goal = summary if event.event_type == EventType.USER_PROMPT else None
        agent_understanding = summary if event.event_type in {
            EventType.AGENT_RESPONSE,
            EventType.PLAN,
            EventType.ARCHITECTURE_DECISION,
        } else None
        return Interpretation(
            plain_summary=summary,
            user_goal=user_goal,
            agent_understanding=agent_understanding,
            decisions=decisions[:8],
            assumptions=assumptions[:8],
            consequences=consequences[:8],
            alternatives=alternatives[:8],
            unresolved_questions=questions[:8],
            technical_terms=self._glossary(event.content),
            importance=importance,
            confidence=0.58,
            requires_user_attention=bool(questions or alignment == Alignment.CONFLICT or (decisions and importance >= 4)),
            evidence_refs=[event.id],
            alignment=alignment,
            alignment_explanation=explanation,
            requirements_impacted=impacted,
        )

    @staticmethod
    def _sentences(text: str) -> list[str]:
        collapsed = re.sub(r"\s+", " ", text).strip()
        return [part.strip() for part in re.split(r"(?<=[.!?])\s+", collapsed) if part.strip()]

    @staticmethod
    def _matching(sentences: list[str], phrases: tuple[str, ...]) -> list[str]:
        output: list[str] = []
        for sentence in sentences:
            lowered = sentence.lower()
            if any(phrase in lowered for phrase in phrases) and sentence not in output:
                output.append(sentence[:600])
        return output

    @staticmethod
    def _importance(event_type: EventType, decisions: list[str]) -> int:
        if event_type == EventType.ARCHITECTURE_DECISION:
            return 5
        if event_type in {EventType.PLAN, EventType.CODE_CHANGE, EventType.COMMIT}:
            return 4 if decisions else 3
        if event_type in {EventType.USER_PROMPT, EventType.TEST_RESULT}:
            return 3
        return 2

    @staticmethod
    def _summary(event: ProjectEvent, lines: list[str]) -> str:
        first = (lines[0] if lines else "No readable content was found.")[:500]
        labels = {
            EventType.USER_PROMPT: "The project owner requested",
            EventType.AGENT_RESPONSE: "An agent reported",
            EventType.PLAN: "A development plan proposed",
            EventType.CODE_CHANGE: "Uncommitted code changes indicate",
            EventType.COMMIT: "A version-control commit recorded",
            EventType.TEST_RESULT: "A test result reported",
            EventType.ARCHITECTURE_DECISION: "An architectural choice was described",
            EventType.MANUAL_NOTE: "A project note recorded",
            EventType.UNKNOWN: "An unclassified project event recorded",
        }
        return f"{labels[event.event_type]}: {first}"

    @staticmethod
    def _alignment(text: str, constitution: Constitution) -> tuple[Alignment, str, list[str]]:
        lowered = text.lower()
        impacted: list[str] = []
        conflicts = {
            "read-only": ("write to the observed", "edit the observed", "modify production"),
            "raw evidence": ("delete the original", "replace the original", "discard raw"),
            "without an external language model": ("requires an external model", "cannot run without"),
            "never silently approve": ("automatically approve", "auto-approve"),
            "stock market only": ("cryptocurrency", "bitcoin", "ethereum", "crypto trading"),
        }
        for requirement in constitution.non_negotiable_requirements:
            req_lower = requirement.lower()
            for marker, prohibited in conflicts.items():
                if marker in req_lower and any(term in lowered for term in prohibited):
                    impacted.append(requirement)
        if impacted:
            return Alignment.CONFLICT, "The event appears to conflict with a non-negotiable requirement.", impacted
        return Alignment.UNCERTAIN, "No direct contradiction was detected by deterministic rules.", []

    @staticmethod
    def _glossary(text: str) -> dict[str, str]:
        known = {"sqlite": "A local database stored in one file.", "api": "A defined way for software components to communicate.", "commit": "A saved version-control checkpoint.", "diff": "A description of file changes.", "schema": "The defined structure of stored data."}
        lowered = text.lower()
        return {term: definition for term, definition in known.items() if term in lowered}
