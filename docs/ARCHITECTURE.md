# Architecture

Project Interpreter stores source evidence before interpretation. The append-only SQLite ledger keeps events separate from analyses, decisions, assumptions, questions, drift findings, and human reviews.

Collectors ingest mailbox JSON, Git activity, and manual notes. The deterministic interpreter works without an external model; an optional OpenAI-compatible engine falls back safely. The report layer generates owner-facing Markdown.
