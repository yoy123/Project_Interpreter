# Project Interpreter

Project Interpreter is an independent comprehension and governance layer for AI-assisted software projects. It records source evidence first, translates development activity into plain language, tracks decisions and assumptions, and warns when implementation may be drifting from the project owner's stated intent.

It is deliberately separate from the coding agent. The interpreter observes prompts, agent messages, Git changes, and test evidence; it does not edit the application being audited.

## Current capabilities

- Immutable raw-event ingestion into SQLite
- Generic JSON mailbox collection with checksum and character-count validation
- Git commit and working-tree collection
- Deterministic plain-language interpretation with an optional OpenAI-compatible model
- Decision, assumption, consequence, question, and evidence extraction
- Deterministic and model-assisted drift findings
- Decision approval, rejection, and provisional-status workflow
- Human-readable Markdown reports
- One-shot and polling service modes
- No runtime Python dependencies outside the standard library

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
project-interpreter init
# Edit PROJECT_CONSTITUTION.md and config.toml
project-interpreter run
project-interpreter status
```

To monitor continuously:

```bash
project-interpreter watch
```

## Optional model configuration

The interpreter works without an LLM, using conservative deterministic extraction. To use LM Studio, Ollama's OpenAI-compatible endpoint, or another compatible service, edit `config.toml` and enable the `[llm]` section.

If the model request fails or returns invalid JSON, processing falls back to deterministic interpretation and records the failure without losing the source event.

## Core rule

The database keeps raw evidence separate from generated interpretation. A summary can be regenerated; the original prompt, message, commit, or test record remains the authority.

See `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`.
