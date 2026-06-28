from __future__ import annotations

import re
from pathlib import Path

from .models import Constitution

SECTION_ALIASES = {
    "purpose": "purpose",
    "non-negotiable requirements": "requirements",
    "non negotiable requirements": "requirements",
    "requirements": "requirements",
    "success criteria": "success",
    "current unresolved decisions": "unresolved",
    "unresolved decisions": "unresolved",
}


def load_constitution(path: Path) -> Constitution:
    if not path.exists():
        raise FileNotFoundError(f"Project constitution not found: {path}")
    raw = path.read_text(encoding="utf-8")
    sections = _parse_sections(raw)
    purpose_lines = sections.get("purpose", [])
    return Constitution(
        purpose=" ".join(_strip_markdown(line) for line in purpose_lines).strip(),
        non_negotiable_requirements=_bullets(sections.get("requirements", [])),
        success_criteria=_bullets(sections.get("success", [])),
        unresolved_decisions=_bullets(sections.get("unresolved", [])),
        raw_text=raw,
    )


def _parse_sections(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", raw_line)
        if heading:
            normalized = heading.group(1).strip().lower()
            current = SECTION_ALIASES.get(normalized)
            if current is not None:
                result.setdefault(current, [])
            continue
        if current is not None and raw_line.strip():
            result[current].append(raw_line.strip())
    return result


def _bullets(lines: list[str]) -> list[str]:
    values: list[str] = []
    for line in lines:
        clean = re.sub(r"^[-*+]\s+", "", line).strip()
        clean = re.sub(r"^\d+[.)]\s+", "", clean).strip()
        if clean:
            values.append(_strip_markdown(clean))
    return values


def _strip_markdown(value: str) -> str:
    return value.replace("**", "").replace("`", "").strip()
