from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from project_interpreter.analysis_engine import HeuristicEngine
from project_interpreter.collectors.mailbox import MailboxCollector
from project_interpreter.constitution import load_constitution
from project_interpreter.drift import detect_drift
from project_interpreter.ledger import Ledger
from project_interpreter.models import Alignment, EventType, ProjectEvent


CONSTITUTION = """# Project Constitution

## Purpose

Explain AI-assisted development to the project owner.

## Non-negotiable requirements

- Preserve raw evidence separately from generated summaries.
- Keep the observed repository read-only.
- Never silently approve a major architectural decision.

## Success criteria

- Important decisions remain traceable to source evidence.

## Current unresolved decisions

- Select future observability integrations.
"""


class CoreTests(unittest.TestCase):
    def test_constitution_parser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PROJECT_CONSTITUTION.md"
            path.write_text(CONSTITUTION, encoding="utf-8")
            constitution = load_constitution(path)
        self.assertIn("Explain AI-assisted", constitution.purpose)
        self.assertEqual(len(constitution.non_negotiable_requirements), 3)

    def test_ledger_deduplication_processing_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with Ledger(Path(directory) / "ledger.db") as ledger:
                event = ProjectEvent.create(
                    project="Demo",
                    event_type=EventType.ARCHITECTURE_DECISION,
                    source="agent",
                    content="Use SQLite as the evidence ledger.",
                )
                self.assertTrue(ledger.add_event(event))
                self.assertFalse(ledger.add_event(event))
                self.assertEqual(len(ledger.pending_events()), 1)
                ledger.mark_processed(event, "processed")
                self.assertEqual(ledger.pending_events(), [])
                decision_id = Ledger.stable_id("decision", event.id, event.content)
                ledger.add(
                    "decision",
                    "Demo",
                    "provisional",
                    {"title": event.content},
                    f"decision:{event.id}",
                    source_id=event.id,
                    record_id=decision_id,
                )
                ledger.review(decision_id, "Demo", "approved", "Owner approved.")
                decision = ledger.decisions("Demo")[0]
                self.assertEqual(decision["status"], "approved")
                self.assertEqual(decision["review_note"], "Owner approved.")

    def test_mailbox_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mailbox = Path(directory)
            content = "We will use SQLite for durable evidence."
            payload = {
                "project": "Demo",
                "sender": "copilot",
                "event_type": "architecture_decision",
                "message": content,
                "sha256": hashlib.sha256(content.encode()).hexdigest(),
                "chars": len(content),
            }
            (mailbox / "message.json").write_text(json.dumps(payload), encoding="utf-8")
            events = MailboxCollector([mailbox], "Fallback").collect()
        self.assertEqual(events[0].event_type, EventType.ARCHITECTURE_DECISION)
        self.assertTrue(events[0].metadata["hash_valid"])
        self.assertTrue(events[0].metadata["char_count_valid"])

    def test_decision_and_conflict_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PROJECT_CONSTITUTION.md"
            path.write_text(CONSTITUTION, encoding="utf-8")
            constitution = load_constitution(path)
        decision_event = ProjectEvent.create(
            project="Demo",
            event_type=EventType.ARCHITECTURE_DECISION,
            source="agent",
            content="Use SQLite as the append-only evidence ledger.",
        )
        result = HeuristicEngine().interpret(decision_event, constitution)
        self.assertEqual(result.decisions, [decision_event.content])
        self.assertTrue(
            any(item.category == "major_decision_needs_review" for item in detect_drift(decision_event, result, constitution))
        )
        conflict_event = ProjectEvent.create(
            project="Demo",
            event_type=EventType.PLAN,
            source="agent",
            content="The agent will edit the observed repository automatically.",
        )
        conflict = HeuristicEngine().interpret(conflict_event, constitution)
        self.assertEqual(conflict.alignment, Alignment.CONFLICT)


if __name__ == "__main__":
    unittest.main()
