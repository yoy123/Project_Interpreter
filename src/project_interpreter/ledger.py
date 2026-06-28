from __future__ import annotations

import builtins
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, cast

from .models import EventType, ProjectEvent, utc_now


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS records ("
            "id TEXT PRIMARY KEY, kind TEXT NOT NULL, project TEXT NOT NULL, "
            "source_id TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, "
            "payload_json TEXT NOT NULL, unique_key TEXT NOT NULL UNIQUE)"
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def add(
        self,
        kind: str,
        project: str,
        status: str,
        payload: dict[str, Any],
        unique_key: str,
        source_id: str | None = None,
        record_id: str | None = None,
    ) -> bool:
        current_id = record_id or str(uuid.uuid4())
        sql = (
            "INSERT OR IGNORE INTO records "
            "(id, kind, project, source_id, status, created_at, payload_json, unique_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        cursor = self.connection.execute(
            sql,
            (
                current_id,
                kind,
                project,
                source_id,
                status,
                utc_now(),
                json.dumps(payload, sort_keys=True, default=str),
                unique_key,
            ),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def add_event(self, event: ProjectEvent) -> bool:
        return self.add(
            "event",
            event.project,
            "recorded",
            event.as_dict(),
            f"event:{event.content_hash}",
            record_id=event.id,
        )

    def pending_events(self, limit: int = 100) -> list[ProjectEvent]:
        events = self.list("event", limit=100000)
        processed = {row["source_id"] for row in self.list("processing", limit=100000)}
        pending = [row for row in reversed(events) if row["id"] not in processed]
        return [self._event(row) for row in pending[:limit]]

    def mark_processed(self, event: ProjectEvent, result: str, detail: str = "") -> None:
        payload = {"event_id": event.id, "result": result, "detail": detail}
        self.add(
            "processing",
            event.project,
            result,
            payload,
            f"processing:{event.id}",
            source_id=event.id,
            record_id=self.stable_id("processing", event.id),
        )

    def list(
        self,
        kind: str,
        project: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT id, project, source_id, status, created_at, payload_json "
            "FROM records WHERE kind = ? ORDER BY created_at DESC",
            (kind,),
        ).fetchall()
        output = [self._expand(row) for row in rows]
        if project is not None:
            output = [row for row in output if row["project"] == project]
        if status is not None:
            output = [row for row in output if row["status"] == status]
        return output[:limit]

    def get(self, record_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT id, project, source_id, status, created_at, payload_json "
            "FROM records WHERE id = ?",
            (record_id,),
        ).fetchone()
        return self._expand(row) if row else None

    def review(self, decision_id: str, project: str, status: str, note: str = "") -> str:
        review_id = str(uuid.uuid4())
        payload = {"decision_id": decision_id, "status": status, "note": note}
        self.add(
            "review",
            project,
            status,
            payload,
            f"review:{decision_id}:{review_id}",
            source_id=decision_id,
            record_id=review_id,
        )
        return review_id

    def decisions(
        self, project: str | None = None, limit: int = 500
    ) -> builtins.list[dict[str, Any]]:
        decisions = self.list("decision", project=project, limit=limit)
        reviews = self.list("review", project=project, limit=100000)
        latest: dict[str, dict[str, Any]] = {}
        for review in reviews:
            decision_id = str(review.get("source_id") or "")
            if decision_id and decision_id not in latest:
                latest[decision_id] = review
        for decision in decisions:
            matched_review = latest.get(str(decision["id"]))
            if matched_review is not None:
                decision["status"] = matched_review["status"]
                decision["review_note"] = matched_review.get("note", "")
        return decisions

    def review_finding(
        self,
        finding_id: str,
        project: str,
        status: str,
        note: str = "",
    ) -> str:
        review_id = str(uuid.uuid4())
        payload = {"finding_id": finding_id, "status": status, "note": note}
        self.add(
            "finding_review",
            project,
            status,
            payload,
            f"finding-review:{finding_id}:{review_id}",
            source_id=finding_id,
            record_id=review_id,
        )
        return review_id

    def findings(
        self,
        project: str | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> builtins.list[dict[str, Any]]:
        findings = self.list("drift", project=project, limit=limit)
        reviews = self.list("finding_review", project=project, limit=100000)
        latest: dict[str, dict[str, Any]] = {}
        for review in reviews:
            finding_id = str(review.get("source_id") or "")
            if finding_id and finding_id not in latest:
                latest[finding_id] = review
        for finding in findings:
            matched_review = latest.get(str(finding["id"]))
            if matched_review is not None:
                finding["status"] = matched_review["status"]
                finding["review_note"] = matched_review.get("note", "")
        if status is not None:
            findings = [item for item in findings if item.get("status") == status]
        return findings[:limit]

    def put_meta(self, project: str, key: str, value: str) -> None:
        marker = str(uuid.uuid4())
        self.add(
            "meta",
            project,
            "current",
            {"key": key, "value": value},
            f"meta:{key}:{marker}",
            source_id=key,
            record_id=marker,
        )

    def get_meta(self, project: str, key: str) -> str | None:
        for row in self.list("meta", project=project, limit=100000):
            if row.get("key") == key:
                return str(row.get("value", ""))
        return None

    def counts(self, project: str | None = None) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT kind, project, COUNT(*) AS count FROM records GROUP BY kind, project"
        ).fetchall()
        output: dict[str, int] = {}
        for row in rows:
            if project is None or row["project"] == project:
                key = str(row["kind"])
                output[key] = output.get(key, 0) + int(row["count"])
        return output

    @staticmethod
    def stable_id(kind: str, *parts: str) -> str:
        value = ":".join((kind, *parts))
        return str(uuid.uuid5(uuid.NAMESPACE_URL, value))

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _expand(row: sqlite3.Row) -> dict[str, Any]:
        parsed = json.loads(row["payload_json"])
        payload = cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}
        payload.update(
            {
                "id": row["id"],
                "project": row["project"],
                "source_id": row["source_id"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
        )
        return payload

    @staticmethod
    def _event(row: dict[str, Any]) -> ProjectEvent:
        event_type_raw = str(row.get("event_type", EventType.UNKNOWN.value))
        try:
            event_type = EventType(event_type_raw)
        except ValueError:
            event_type = EventType.UNKNOWN
        return ProjectEvent(
            id=str(row["id"]),
            project=str(row["project"]),
            event_type=event_type,
            source=str(row["source"]),
            timestamp=str(row["timestamp"]),
            content=str(row["content"]),
            metadata=dict(row.get("metadata", {})),
            content_hash=str(row["content_hash"]),
        )
