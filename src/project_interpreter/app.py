import time
from dataclasses import dataclass, field

from . import drift as drift_module
from .collectors import MailboxCollector, VersionControlCollector
from .config import AppConfig
from .constitution import load_constitution
from .ledger import Ledger
from .materialize import materialize
from .model_engine import InterpretationEngine
from .models import EventType, ProjectEvent
from .reports import ReportWriter


@dataclass(slots=True)
class RunStats:
    events_seen: int = 0
    events_added: int = 0
    events_processed: int = 0
    findings_added: int = 0
    derived: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class ProjectApp:
    def __init__(self, config: AppConfig):
        self.config = config
        self.constitution = load_constitution(config.constitution_path)
        self.ledger = Ledger(config.database_path)
        self.engine = InterpretationEngine(config.llm)
        self.reporter = ReportWriter(self.ledger, self.constitution, config.name, config.reports_dir)

    def close(self) -> None:
        self.ledger.close()

    def collect(self) -> RunStats:
        stats = RunStats()
        collectors: list[object] = []
        if self.config.collectors.mailbox_paths:
            collectors.append(MailboxCollector(self.config.collectors.mailbox_paths, self.config.name))
        if self.config.collectors.git_enabled:
            collectors.append(
                VersionControlCollector(
                    self.config.repo_path,
                    self.config.name,
                    self.config.collectors.git_initial_commits,
                    self.config.collectors.git_patch_char_limit,
                )
            )
        for collector in collectors:
            try:
                events = collector.collect()  # type: ignore[attr-defined]
            except Exception as exc:
                stats.errors.append(f"{type(collector).__name__}: {exc}")
                continue
            stats.events_seen += len(events)
            for event in events:
                stats.events_added += int(self.ledger.add_event(event))
        return stats

    def process(self, limit: int = 100) -> RunStats:
        stats = RunStats()
        for event in self.ledger.pending_events(limit):
            try:
                output = self.engine.interpret(event, self.constitution)
                counts = materialize(self.ledger, event, output)
                for key, value in counts.items():
                    stats.derived[key] = stats.derived.get(key, 0) + value
                findings = drift_module.detect_drift(event, output.interpretation, self.constitution)
                stats.findings_added += drift_module.store_findings(self.ledger, findings)
                self.ledger.mark_processed(event, "processed")
                stats.events_processed += 1
            except Exception as exc:
                stats.errors.append(f"Event {event.id}: {exc}")
        return stats

    def run_once(self, limit: int = 100) -> RunStats:
        collected = self.collect()
        processed = self.process(limit)
        collected.events_processed = processed.events_processed
        collected.findings_added = processed.findings_added
        for key, value in processed.derived.items():
            collected.derived[key] = collected.derived.get(key, 0) + value
        collected.errors.extend(processed.errors)
        self.reporter.generate()
        return collected

    def watch(self, limit: int = 100) -> None:
        while True:
            self.run_once(limit)
            time.sleep(self.config.poll_seconds)

    def record(self, content: str, event_type: EventType = EventType.MANUAL_NOTE, source: str = "project-owner") -> ProjectEvent:
        event = ProjectEvent.create(
            project=self.config.name,
            event_type=event_type,
            source=source,
            content=content,
            metadata={"collector": "manual"},
        )
        self.ledger.add_event(event)
        return event

    def review_decision(self, decision_id: str, status: str, note: str = "") -> str:
        valid = {"proposed", "provisional", "approved", "implemented", "validated", "rejected", "superseded"}
        if status not in valid:
            raise ValueError(f"Unsupported decision status: {status}")
        decision = self.ledger.get(decision_id)
        if decision is None:
            raise KeyError(f"Decision not found: {decision_id}")
        review_id = self.ledger.review(decision_id, self.config.name, status, note)
        if status in {"approved", "rejected", "superseded"}:
            source_event_id = decision.get("source_id")
            for finding in self.ledger.findings(self.config.name, status="open", limit=100000):
                if (
                    finding.get("source_id") == source_event_id
                    and finding.get("category") == "major_decision_needs_review"
                ):
                    self.ledger.review_finding(
                        str(finding["id"]),
                        self.config.name,
                        "resolved",
                        f"Decision {status}: {note}".strip(),
                    )
        self.reporter.generate()
        return review_id

    def status(self) -> dict[str, object]:
        decisions = self.ledger.decisions(self.config.name)
        findings = self.ledger.findings(self.config.name, status="open", limit=100000)
        return {
            "project": self.config.name,
            "database": str(self.config.database_path),
            "reports": str(self.config.reports_dir),
            "counts": self.ledger.counts(self.config.name),
            "pending_events": len(self.ledger.pending_events(100000)),
            "provisional_decisions": sum(1 for item in decisions if item.get("status") == "provisional"),
            "findings_requiring_review": sum(1 for item in findings if item.get("requires_review")),
            "llm_enabled": self.config.llm.enabled,
        }
