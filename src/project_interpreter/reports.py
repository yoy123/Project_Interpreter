from __future__ import annotations

from pathlib import Path
from typing import Any

from .ledger import Ledger
from .models import Constitution, utc_now


class ReportWriter:
    def __init__(self, ledger: Ledger, constitution: Constitution, project: str, directory: Path):
        self.ledger = ledger
        self.constitution = constitution
        self.project = project
        self.directory = directory

    def generate(self) -> list[Path]:
        self.directory.mkdir(parents=True, exist_ok=True)
        outputs = {
            "CURRENT_STATE.md": self._current_state(),
            "DECISIONS.md": self._decisions(),
            "ASSUMPTIONS.md": self._assumptions(),
            "OPEN_QUESTIONS.md": self._questions(),
            "DRIFT_REPORT.md": self._drift(),
            "TRACEABILITY.md": self._traceability(),
        }
        paths: list[Path] = []
        for name, content in outputs.items():
            path = self.directory / name
            path.write_text(content.rstrip() + "\n", encoding="utf-8")
            paths.append(path)
        return paths

    def _header(self, title: str) -> list[str]:
        return [
            f"# {title}",
            "",
            f"Project: **{self.project}**",
            f"Generated: `{utc_now()}`",
            "",
        ]

    def _current_state(self) -> str:
        lines = self._header("Current Project State")
        lines += [
            "## What is being built",
            "",
            self.constitution.purpose or "Purpose has not been defined.",
            "",
            "## Evidence status",
            "",
        ]
        counts = self.ledger.counts(self.project)
        for label in ("event", "analysis", "decision", "assumption", "question", "drift", "warning"):
            lines.append(f"- {label.replace('_', ' ').title()}: **{counts.get(label, 0)}**")
        findings = self.ledger.findings(self.project, status="open", limit=1000)
        review_count = sum(1 for item in findings if item.get("requires_review"))
        provisional = sum(
            1 for item in self.ledger.decisions(self.project) if item.get("status") == "provisional"
        )
        lines += [
            "",
            "## Owner attention",
            "",
            f"- Open findings requiring review: **{review_count}**",
            f"- Provisional decisions: **{provisional}**",
            "",
            "## Latest interpreted activity",
            "",
        ]
        analyses = self.ledger.list("analysis", project=self.project, limit=10)
        if not analyses:
            lines.append("No activity has been interpreted yet.")
        for item in analyses:
            lines += [
                f"### {item.get('created_at', '')}",
                "",
                str(item.get("plain_summary", "No summary.")),
                "",
            ]
            if item.get("alignment_explanation"):
                lines.append(
                    f"**Alignment:** {item.get('alignment', 'uncertain')} — "
                    f"{item['alignment_explanation']}"
                )
                lines.append("")
            lines += [f"Evidence: `{item.get('source_id', '')}`", ""]
        return "\n".join(lines)

    def _decisions(self) -> str:
        lines = self._header("Decision Ledger")
        decisions = self.ledger.decisions(self.project)
        if not decisions:
            lines.append("No decisions have been detected.")
            return "\n".join(lines)
        for item in decisions:
            lines += [
                f"## {item.get('title', 'Untitled decision')}",
                "",
                f"**Status:** `{item.get('status', 'unknown')}`",
                f"**Importance:** {item.get('importance', 'unknown')}/5",
                f"**Decision ID:** `{item.get('id', '')}`",
                "",
                "**Plain-language explanation**",
                "",
                str(item.get("explanation", "")),
                "",
                "**Why it was selected**",
                "",
                str(item.get("rationale", "Not recorded.")),
                "",
            ]
            consequences = item.get("consequences") or []
            if consequences:
                lines += ["**Practical consequences**", ""]
                lines += [f"- {value}" for value in consequences]
                lines.append("")
            alternatives = item.get("alternatives") or []
            if alternatives:
                lines += ["**Alternatives mentioned**", ""]
                lines += [f"- {value}" for value in alternatives]
                lines.append("")
            lines += [f"Evidence: `{item.get('source_id', '')}`", ""]
        return "\n".join(lines)

    def _assumptions(self) -> str:
        lines = self._header("Assumption Register")
        items = self.ledger.list("assumption", project=self.project, status="active", limit=1000)
        if not items:
            lines.append("No active assumptions have been detected.")
        for item in items:
            lines += [f"- {item.get('text', '')}", f"  Evidence: `{item.get('source_id', '')}`"]
        return "\n".join(lines)

    def _questions(self) -> str:
        lines = self._header("Open Questions")
        items = self.ledger.list("question", project=self.project, status="open", limit=1000)
        if not items:
            lines.append("No open questions have been detected.")
        for item in items:
            lines += [f"- {item.get('text', '')}", f"  Evidence: `{item.get('source_id', '')}`"]
        return "\n".join(lines)

    def _drift(self) -> str:
        lines = self._header("Project Drift Report")
        items = self.ledger.findings(self.project, status="open", limit=1000)
        severity_order = {"critical": 0, "high": 1, "warning": 2, "info": 3}
        items.sort(key=lambda item: severity_order.get(str(item.get("severity")), 9))
        if not items:
            lines.append("No open drift findings have been recorded.")
        for item in items:
            lines += [
                f"## [{str(item.get('severity', 'info')).upper()}] "
                f"{item.get('category', 'finding')}",
                "",
                str(item.get("explanation", "")),
                "",
            ]
            if item.get("original_requirement"):
                lines.append(f"**Original requirement:** {item['original_requirement']}")
            lines += [
                f"**Current direction:** {item.get('current_direction', '')}",
                f"**Likely consequence:** {item.get('likely_consequence', '')}",
                f"**Needs owner review:** {'yes' if item.get('requires_review') else 'no'}",
                f"Evidence: `{item.get('source_id', '')}`",
                "",
            ]
        return "\n".join(lines)

    def _traceability(self) -> str:
        lines = self._header("Traceability Index")
        events = self.ledger.list("event", project=self.project, limit=1000)
        analyses = self.ledger.list("analysis", project=self.project, limit=1000)
        by_event: dict[str, list[dict[str, Any]]] = {}
        for item in analyses:
            by_event.setdefault(str(item.get("source_id")), []).append(item)
        for event in events:
            event_id = str(event.get("id", ""))
            related = by_event.get(event_id, [])
            lines += [
                f"## {event.get('event_type', 'event')} — `{event_id}`",
                "",
                f"Source: **{event.get('source', 'unknown')}**",
                f"Recorded time: `{event.get('timestamp', '')}`",
                f"Interpretations: **{len(related)}**",
            ]
            if related:
                lines.append(f"Latest summary: {related[0].get('plain_summary', '')}")
            lines.append("")
        return "\n".join(lines)
