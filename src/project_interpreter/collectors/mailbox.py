from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..models import EventType, ProjectEvent

_CONTENT_KEYS = ("message", "content", "text", "body", "prompt", "response", "full_message")
_SOURCE_KEYS = ("sender", "source", "role", "agent", "from")
_TIME_KEYS = ("timestamp", "created_at", "createdAt", "sent_at", "checkedAt")


class MailboxCollector:
    def __init__(self, paths: Iterable[Path], project: str):
        self.paths = list(paths)
        self.project = project

    def collect(self) -> list[ProjectEvent]:
        events: list[ProjectEvent] = []
        for path in self._json_files():
            events.extend(self._read_file(path))
        return events

    def _json_files(self) -> list[Path]:
        files: set[Path] = set()
        for path in self.paths:
            if path.is_file() and path.suffix.lower() == ".json":
                files.add(path)
            elif path.is_dir():
                files.update(item for item in path.rglob("*.json") if item.is_file())
        return sorted(files)

    def _read_file(self, path: Path) -> list[ProjectEvent]:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            return [self._error_event(path, "read_error", str(exc))]
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return [self._error_event(path, "invalid_json", str(exc), raw[:20000])]
        items = parsed if isinstance(parsed, list) else [parsed]
        events: list[ProjectEvent] = []
        for index, item in enumerate(items):
            if isinstance(item, dict):
                events.append(self._event_from_payload(path, item, index))
            else:
                events.append(
                    self._error_event(path, "unsupported_payload", f"Item {index} is not an object")
                )
        return events

    def _event_from_payload(self, path: Path, payload: dict[str, Any], index: int) -> ProjectEvent:
        content = self._extract_content(payload)
        source = self._first_string(payload, _SOURCE_KEYS) or self._source_from_name(path)
        timestamp = self._first_string(payload, _TIME_KEYS)
        declared_hash = self._first_string(payload, ("sha256", "content_sha256", "hash"))
        declared_chars = self._first_int(payload, ("chars", "character_count", "content_chars"))
        actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        metadata: dict[str, Any] = {
            "collector": "mailbox",
            "path": str(path),
            "item_index": index,
            "declared_sha256": declared_hash,
            "actual_sha256": actual_hash,
            "declared_chars": declared_chars,
            "actual_chars": len(content),
            "hash_valid": declared_hash in (None, actual_hash),
            "char_count_valid": declared_chars in (None, len(content)),
        }
        metadata["payload_keys"] = sorted(str(key) for key in payload)
        return ProjectEvent.create(
            project=str(payload.get("project") or self.project),
            event_type=self._classify(payload, path, source, content),
            source=source,
            timestamp=timestamp,
            content=content or json.dumps(payload, sort_keys=True, default=str),
            metadata=metadata,
        )

    def _extract_content(self, payload: dict[str, Any]) -> str:
        for key in _CONTENT_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        nested = payload.get("payload")
        if isinstance(nested, dict):
            return self._extract_content(nested)
        return ""

    @staticmethod
    def _classify(payload: dict[str, Any], path: Path, source: str, content: str) -> EventType:
        explicit = payload.get("event_type") or payload.get("type")
        if isinstance(explicit, str) and explicit in EventType._value2member_map_:
            return EventType(explicit)
        text = (path.name + " " + source + " " + content[:1000]).lower()
        if "test" in text:
            return EventType.TEST_RESULT
        if "plan" in text:
            return EventType.PLAN
        if "decision" in text or "architecture" in text:
            return EventType.ARCHITECTURE_DECISION
        if source.lower() in {"user", "human", "dan"}:
            return EventType.USER_PROMPT
        if source.lower() != "unknown":
            return EventType.AGENT_RESPONSE
        return EventType.UNKNOWN

    def _error_event(self, path: Path, error_type: str, detail: str, raw: str = "") -> ProjectEvent:
        metadata = {
            "collector": "mailbox",
            "path": str(path),
            "error": error_type,
            "detail": detail,
        }
        return ProjectEvent.create(
            project=self.project,
            event_type=EventType.UNKNOWN,
            source="mailbox_collector",
            content=raw or detail,
            metadata=metadata,
        )

    @staticmethod
    def _first_string(payload: dict[str, Any], keys: Iterable[str]) -> str | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _first_int(payload: dict[str, Any], keys: Iterable[str]) -> int | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
        return None

    @staticmethod
    def _source_from_name(path: Path) -> str:
        name = path.name.lower()
        for source in ("copilot", "chatgpt", "user", "agent"):
            if source in name:
                return source
        return "unknown"
