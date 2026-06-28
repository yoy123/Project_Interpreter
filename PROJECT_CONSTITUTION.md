# Project Constitution

## Purpose

Build an independent project-comprehension layer that records AI-assisted software-development activity, explains it in ordinary language, preserves the project owner's intent, and identifies likely drift before substantial work proceeds in the wrong direction.

## Non-negotiable requirements

- Preserve raw evidence separately from generated summaries.
- Explain consequential decisions in language a nontechnical project owner can understand.
- Track prompts, agent interpretations, architectural decisions, assumptions, consequences, unresolved questions, and supporting evidence.
- Distinguish code existing, tests passing, a feature functioning, and the project achieving its intended objective.
- Never silently approve a major architectural decision on behalf of the project owner.
- Keep the interpreter operationally independent from the coding agent it observes.
- Prefer read-only access to observed project repositories.
- Make every generated claim traceable to source evidence.
- Continue operating without an external language model through a conservative deterministic fallback.

## Success criteria

- A project owner can determine what is being built and why without reading the codebase.
- Every important decision has a status, rationale, consequences, and source evidence.
- New activity is checked against durable project requirements.
- High-impact provisional decisions are clearly surfaced for review.
- Reports can be regenerated from durable evidence.
- Collectors tolerate different mailbox formats without corrupting or discarding evidence.

## Current unresolved decisions

- Which agent-specific adapters should be included after the generic mailbox collector.
- Whether a browser dashboard is necessary after the Markdown and CLI workflow is validated.
- Which observability backend, if any, should supplement the local SQLite evidence store.
- How aggressively semantic drift findings should interrupt coding-agent workflows.
