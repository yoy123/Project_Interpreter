from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .analysis_engine import EngineOutput, HeuristicEngine, PROMPT_VERSION
from .config import LLMConfig
from .models import Constitution, Interpretation, ProjectEvent


class InterpretationEngine:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.fallback = HeuristicEngine()

    def interpret(self, event: ProjectEvent, constitution: Constitution) -> EngineOutput:
        if not self.config.enabled:
            return EngineOutput(self.fallback.interpret(event, constitution), "deterministic", "rules")
        try:
            interpretation = self._request(event, constitution)
            return EngineOutput(interpretation, "openai-compatible", self.config.model)
        except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError) as exc:
            fallback = self.fallback.interpret(event, constitution)
            return EngineOutput(fallback, "deterministic", "rules", str(exc))

    def _request(self, event: ProjectEvent, constitution: Constitution) -> Interpretation:
        endpoint = self.config.endpoint.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        body = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": self._user_prompt(event, constitution)},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        content = parsed["choices"][0]["message"]["content"]
        mapping = self._parse_json(str(content))
        result = Interpretation.from_mapping(mapping)
        if event.id not in result.evidence_refs:
            result.evidence_refs.append(event.id)
        return result

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are an independent project interpretation agent. Translate software-development "
            "activity into ordinary language for a project owner. Identify goals, decisions, hidden "
            "assumptions, practical consequences, alternatives, unresolved questions, and alignment "
            "with the supplied constitution. Do not claim that code works merely because it exists or "
            "tests pass. Use only supplied evidence. Return one JSON object with these keys: "
            "plain_summary, user_goal, agent_understanding, decisions, assumptions, consequences, "
            "alternatives, unresolved_questions, technical_terms, importance, confidence, "
            "requires_user_attention, evidence_refs, alignment, alignment_explanation, "
            "requirements_impacted. alignment must be aligned, uncertain, or conflict."
        )

    @staticmethod
    def _user_prompt(event: ProjectEvent, constitution: Constitution) -> str:
        payload = {
            "event": event.as_dict(),
            "constitution": {
                "purpose": constitution.purpose,
                "non_negotiable_requirements": constitution.non_negotiable_requirements,
                "success_criteria": constitution.success_criteria,
                "unresolved_decisions": constitution.unresolved_decisions,
            },
            "prompt_version": PROMPT_VERSION,
        }
        return json.dumps(payload, indent=2, default=str)

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Model response was not a JSON object")
        return parsed
