import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .app import ProjectApp
from .config import load_config
from .models import EventType


DEFAULT_CONFIG = '''[project]
name = "Project_Interpreter"
repo_path = "."
constitution_path = "PROJECT_CONSTITUTION.md"
state_dir = ".interpreter"
reports_dir = "reports"
poll_seconds = 3.0

[collectors]
mailbox_paths = []
git_enabled = true
git_initial_commits = 20
git_patch_char_limit = 40000

[llm]
enabled = false
endpoint = "http://127.0.0.1:1234/v1"
model = "local-model"
api_key_env = "PROJECT_INTERPRETER_API_KEY"
timeout_seconds = 90
temperature = 0.1
'''

DEFAULT_CONSTITUTION = '''# Project Constitution

## Purpose

Describe what this project is intended to accomplish in plain language.

## Non-negotiable requirements

- Preserve raw evidence separately from generated summaries.
- Explain consequential decisions in language the project owner can understand.
- Never silently approve a major architectural decision.

## Success criteria

- Important decisions are traceable to source evidence.
- Project drift is surfaced before it becomes expensive to reverse.

## Current unresolved decisions

- Add project-specific unresolved decisions here.
'''


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="project-interpreter",
        description="Record and explain AI-assisted project decisions and drift.",
    )
    parser.add_argument("--config", default="config.toml", help="Path to config.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create local configuration and runtime state")
    init.add_argument("--force", action="store_true")
    run = sub.add_parser("run", help="Collect, interpret, and regenerate reports")
    run.add_argument("--limit", type=int, default=100)
    sub.add_parser("collect", help="Collect new evidence without interpreting it")
    process = sub.add_parser("process", help="Interpret pending evidence")
    process.add_argument("--limit", type=int, default=100)
    watch = sub.add_parser("watch", help="Continuously collect and interpret")
    watch.add_argument("--limit", type=int, default=100)
    sub.add_parser("status", help="Show interpreter status")
    sub.add_parser("report", help="Regenerate Markdown reports")

    record = sub.add_parser("record", help="Record a manual project event")
    record.add_argument("content")
    record.add_argument("--type", choices=[item.value for item in EventType], default="manual_note")
    record.add_argument("--source", default="project-owner")

    events = sub.add_parser("events", help="List source events")
    events.add_argument("--limit", type=int, default=20)
    decisions = sub.add_parser("decisions", help="List detected decisions")
    decisions.add_argument("--limit", type=int, default=100)
    findings = sub.add_parser("drift", help="List open drift findings")
    findings.add_argument("--limit", type=int, default=100)

    review = sub.add_parser("review", help="Change a decision lifecycle status")
    review.add_argument("decision_id")
    review.add_argument(
        "status",
        choices=["proposed", "provisional", "approved", "implemented", "validated", "rejected", "superseded"],
    )
    review.add_argument("--note", default="")
    sub.add_parser("doctor", help="Check paths and configuration")
    return parser


def _initialize(config_path: Path, force: bool) -> int:
    if config_path.exists() and not force:
        print(f"Configuration already exists: {config_path}", file=sys.stderr)
        return 2
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    constitution_path = config_path.parent / "PROJECT_CONSTITUTION.md"
    if not constitution_path.exists() or force:
        constitution_path.write_text(DEFAULT_CONSTITUTION, encoding="utf-8")
    config = load_config(config_path)
    app = ProjectApp(config)
    try:
        app.reporter.generate()
    finally:
        app.close()
    print(f"Initialized {config.name} at {config_path.parent}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config).expanduser().resolve()
    if args.command == "init":
        return _initialize(config_path, args.force)
    try:
        config = load_config(config_path)
        app = ProjectApp(config)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        if args.command == "status":
            print(json.dumps(app.status(), indent=2))
        elif args.command == "report":
            print("\n".join(str(path) for path in app.reporter.generate()))
        elif args.command == "events":
            records = app.ledger.list("event", project=config.name, limit=args.limit)
            print(json.dumps(records, indent=2))
        elif args.command == "decisions":
            print(json.dumps(app.ledger.decisions(config.name, args.limit), indent=2))
        elif args.command == "drift":
            records = app.ledger.findings(config.name, status="open", limit=args.limit)
            print(json.dumps(records, indent=2))
        elif args.command == "record":
            event = app.record(args.content, EventType(args.type), args.source)
            print(event.id)
        elif args.command == "review":
            print(app.review_decision(args.decision_id, args.status, args.note))
        elif args.command == "collect":
            stats = app.collect()
            payload = {"events_seen": stats.events_seen, "events_added": stats.events_added, "errors": stats.errors}
            print(json.dumps(payload, indent=2))
        elif args.command == "process":
            stats = app.process(args.limit)
            app.reporter.generate()
            payload = {
                "events_processed": stats.events_processed,
                "findings_added": stats.findings_added,
                "derived": stats.derived,
                "errors": stats.errors,
            }
            print(json.dumps(payload, indent=2))
        elif args.command == "run":
            stats = app.run_once(args.limit)
            payload = {
                "events_seen": stats.events_seen,
                "events_added": stats.events_added,
                "events_processed": stats.events_processed,
                "findings_added": stats.findings_added,
                "derived": stats.derived,
                "errors": stats.errors,
            }
            print(json.dumps(payload, indent=2))
        elif args.command == "watch":
            app.watch(args.limit)
        elif args.command == "doctor":
            payload = {"config": str(config.config_path), "repo_exists": config.repo_path.exists()}
            payload["constitution_exists"] = config.constitution_path.exists()
            payload["llm_enabled"] = config.llm.enabled
            print(json.dumps(payload, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
