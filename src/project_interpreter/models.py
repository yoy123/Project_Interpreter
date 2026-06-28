from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    USER_PROMPT = "user_prompt"
    AGENT_RESPONSE = "agent_response"
    PLAN = "plan"
    CODE_CHANGE = "code_change"
    COMMIT = "commit"
    TEST_RESULT = "test_result"
    ARCHITECTURE_DECISION = "architecture_decision"
    MANUAL_NOTE = "manual_note"
    UNKNOWN = "unknown"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    PROVISIONAL = "provisional"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    VALIDATED = "validated"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class Alignment(StrEnum):
    ALIGNED = "aligned"
    UNCERTAIN = "uncertain"
    CONFLICT = "conflict"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


@dataclass(slots=True)
class ProjectEvent:
    id: str
    project: str
    event_type: EventType
    source: str
    timestamp: str
    content: str
    metadata: dict[str, Any]
    content_hash: str

    @classmethod
    def create(
        cls,
        *,
        project: str,
        event_type: EventType,
        source: str,
        content: str,
        timestamp: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ProjectEvent:
        clean_content = content.strip()
        clean_metadata = dict(metadata or {})
        fingerprint = json.dumps(
            {
                "project": project,
                "event_type": event_type.value,
                "source": source,
                "content": clean_content,
                "metadata": clean_metadata,
            },
            sort_keys=True,
            default=str,
        )
        return cls(
            id=str(uuid.uuid4()),
            project=project,
            event_type=event_type,
            source=source,
            timestamp=timestamp or utc_now(),
            content=clean_content,
            metadata=clean_metadata,
            content_hash=hashlib.sha256(fingerprint.encode()).hexdigest(),
        )

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["event_type"] = self.event_type.value
        return result


@dataclass(slots=True)
class Constitution:
    purpose: str
    non_negotiable_requirements: list[str]
    success_criteria: list[str]
    unresolved_decisions: list[str]
    raw_text: str


@dataclass(slots=True)
class Interpretation:
    plain_summary: str
    user_goal: str | None = None
    agent_understanding: str | None = None
    decisions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    consequences: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    technical_terms: dict[str, str] = field(default_factory=dict)
    importance: int = 1
    confidence: float = 0.5
    requires_user_attention: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    alignment: Alignment = Alignment.UNCERTAIN
    alignment_explanation: str = ""
    requirements_impacted: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> Interpretation:
        terms = value.get("technical_terms", {})
        technical_terms = (
            {str(key): str(item) for key, item in terms.items()}
            if isinstance(terms, Mapping)
            else {}
        )
        try:
            alignment = Alignment(str(value.get("alignment", "uncertain")))
        except ValueError:
            alignment = Alignment.UNCERTAIN
        return cls(
            plain_summary=str(value.get("plain_summary", "")).strip()
            or "No reliable plain-language summary was produced.",
            user_goal=optional_string(value.get("user_goal")),
            agent_understanding=optional_string(value.get("agent_understanding")),
            decisions=clean_list(value.get("decisions")),
            assumptions=clean_list(value.get("assumptions")),
            consequences=clean_list(value.get("consequences")),
            alternatives=clean_list(value.get("alternatives")),
            unresolved_questions=clean_list(value.get("unresolved_questions")),
            technical_terms=technical_terms,
            importance=max(1, min(5, safe_int(value.get("importance"), 1))),
            confidence=max(0.0, min(1.0, safe_float(value.get("confidence"), 0.5))),
            requires_user_attention=bool(value.get("requires_user_attention", False)),
            evidence_refs=clean_list(value.get("evidence_refs")),
            alignment=alignment,
            alignment_explanation=str(value.get("alignment_explanation", "")).strip(),
            requirements_impacted=clean_list(value.get("requirements_impacted")),
        )

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["alignment"] = self.alignment.value
        return result


@dataclass(slots=True)
class DriftFinding:
    id: str
    project: str
    severity: Severity
    category: str
    explanation: str
    original_requirement: str | None
    current_direction: str
    likely_consequence: str
    evidence_refs: list[str]
    requires_review: bool
    status: str = "open"
    created_at: str = field(default_factory=utc_now)


    @classmethod
    def create(
        cls,
        *,
        project: str,
        severity: Severity,
        category: str,
        explanation: str,
        current_direction: str,
        likely_consequence: str,
        evidence_refs: list[str],
        requires_review: bool,
        original_requirement: str | None = None,
    ) -> DriftFinding:
        return cls(
            id=str(uuid.uuid4()),
            project=project,
            severity=severity,
            category=category,
            explanation=explanation,
            original_requirement=original_requirement,
            current_direction=current_direction,
            likely_consequence=likely_consequence,
            evidence_refs=evidence_refs,
            requires_review=requires_review,
        )


def optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
