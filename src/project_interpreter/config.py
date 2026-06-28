from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CollectorConfig:
    mailbox_paths: list[Path] = field(default_factory=list)
    git_enabled: bool = True
    git_initial_commits: int = 20
    git_patch_char_limit: int = 40_000


@dataclass(slots=True)
class LLMConfig:
    enabled: bool = False
    endpoint: str = "http://127.0.0.1:1234/v1"
    model: str = "local-model"
    api_key_env: str = "PROJECT_INTERPRETER_API_KEY"
    timeout_seconds: int = 90
    temperature: float = 0.1

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None


@dataclass(slots=True)
class AppConfig:
    name: str
    config_path: Path
    repo_path: Path
    constitution_path: Path
    state_dir: Path
    reports_dir: Path
    poll_seconds: float
    collectors: CollectorConfig
    llm: LLMConfig

    @property
    def database_path(self) -> Path:
        return self.state_dir / "interpreter.db"


def load_config(path: str | Path = "config.toml") -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration not found: {config_path}. Run 'project-interpreter init'."
        )
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    base = config_path.parent
    project = _mapping(raw.get("project"))
    collectors_raw = _mapping(raw.get("collectors"))
    llm_raw = _mapping(raw.get("llm"))

    repo_path = _resolve(base, str(project.get("repo_path", ".")))
    constitution_path = _resolve(
        base, str(project.get("constitution_path", "PROJECT_CONSTITUTION.md"))
    )
    state_dir = _resolve(base, str(project.get("state_dir", ".interpreter")))
    reports_dir = _resolve(base, str(project.get("reports_dir", "reports")))

    mailbox_paths_raw = collectors_raw.get("mailbox_paths", [])
    mailbox_paths = [
        _resolve(base, str(item))
        for item in mailbox_paths_raw
        if isinstance(item, str | os.PathLike)
    ] if isinstance(mailbox_paths_raw, list) else []

    return AppConfig(
        name=str(project.get("name", config_path.parent.name)),
        config_path=config_path,
        repo_path=repo_path,
        constitution_path=constitution_path,
        state_dir=state_dir,
        reports_dir=reports_dir,
        poll_seconds=float(project.get("poll_seconds", 3.0)),
        collectors=CollectorConfig(
            mailbox_paths=mailbox_paths,
            git_enabled=bool(collectors_raw.get("git_enabled", True)),
            git_initial_commits=int(collectors_raw.get("git_initial_commits", 20)),
            git_patch_char_limit=int(collectors_raw.get("git_patch_char_limit", 40_000)),
        ),
        llm=LLMConfig(
            enabled=bool(llm_raw.get("enabled", False)),
            endpoint=str(llm_raw.get("endpoint", "http://127.0.0.1:1234/v1")),
            model=str(llm_raw.get("model", "local-model")),
            api_key_env=str(llm_raw.get("api_key_env", "PROJECT_INTERPRETER_API_KEY")),
            timeout_seconds=int(llm_raw.get("timeout_seconds", 90)),
            temperature=float(llm_raw.get("temperature", 0.1)),
        ),
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()
