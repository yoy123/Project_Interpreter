from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from project_interpreter.app import ProjectApp
from project_interpreter.config import load_config


CONSTITUTION = """# Project Constitution

## Purpose

Explain AI-assisted development to the project owner.

## Non-negotiable requirements

- Preserve raw evidence separately from generated summaries.
- Never silently approve a major architectural decision.

## Success criteria

- Important decisions remain traceable to source evidence.

## Current unresolved decisions

- None recorded.
"""


class AppEndToEndTests(unittest.TestCase):
    def test_mailbox_to_reports_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mailbox = root / "mailbox"
            mailbox.mkdir()
            (root / "PROJECT_CONSTITUTION.md").write_text(CONSTITUTION, encoding="utf-8")
            message = {
                "sender": "copilot",
                "event_type": "architecture_decision",
                "message": "Use SQLite as the append-only evidence ledger.",
            }
            (mailbox / "event.json").write_text(json.dumps(message), encoding="utf-8")
            config_path = root / "config.toml"
            config_path.write_text(self._config(mailbox), encoding="utf-8")
            app = ProjectApp(load_config(config_path))
            try:
                stats = app.run_once()
                status = app.status()
                decisions = app.ledger.decisions("Demo")
                app.review_decision(
                    str(decisions[0]["id"]),
                    "approved",
                    "Approved in test.",
                )
                approved = app.ledger.decisions("Demo")
                open_findings = app.ledger.findings("Demo", status="open")
            finally:
                app.close()
            self.assertEqual(stats.events_added, 1)
            self.assertEqual(stats.events_processed, 1)
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["status"], "provisional")
            self.assertEqual(approved[0]["status"], "approved")
            self.assertFalse(
                any(
                    item.get("category") == "major_decision_needs_review"
                    for item in open_findings
                )
            )
            self.assertEqual(status["pending_events"], 0)
            for name in self._report_names():
                self.assertTrue((root / "reports" / name).exists(), name)

    @staticmethod
    def _config(mailbox: Path) -> str:
        return f'''[project]
name = "Demo"
repo_path = "."
constitution_path = "PROJECT_CONSTITUTION.md"
state_dir = ".interpreter"
reports_dir = "reports"
poll_seconds = 1.0

[collectors]
mailbox_paths = ["{mailbox.as_posix()}"]
git_enabled = false
git_initial_commits = 5
git_patch_char_limit = 10000

[llm]
enabled = false
endpoint = "http://127.0.0.1:1234/v1"
model = "local"
api_key_env = "PROJECT_INTERPRETER_API_KEY"
timeout_seconds = 5
temperature = 0.1
'''

    @staticmethod
    def _report_names() -> tuple[str, ...]:
        return (
            "CURRENT_STATE.md",
            "DECISIONS.md",
            "ASSUMPTIONS.md",
            "OPEN_QUESTIONS.md",
            "DRIFT_REPORT.md",
            "TRACEABILITY.md",
        )


if __name__ == "__main__":
    unittest.main()
