from __future__ import annotations

import subprocess
from pathlib import Path

from ..models import EventType, ProjectEvent


class VersionControlCollector:
    def __init__(
        self,
        repo_path: Path,
        project: str,
        limit: int = 20,
        patch_limit: int = 40_000,
    ):
        self.repo_path = repo_path
        self.project = project
        self.limit = limit
        self.patch_limit = patch_limit

    def collect(self) -> list[ProjectEvent]:
        probe = self._run("rev-parse", "--is-inside-work-tree")
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            return []
        commits = self._run(
            "log",
            f"--max-count={self.limit}",
            "--reverse",
            "--format=%H",
        )
        events = [
            self._commit_event(commit)
            for commit in commits.stdout.splitlines()
            if commit.strip()
        ]
        working = self._working_event()
        if working is not None:
            events.append(working)
        return events

    def _commit_event(self, commit: str) -> ProjectEvent:
        commit = commit.strip()
        timestamp = self._run("show", "-s", "--format=%cI", commit).stdout.strip()
        shown = self._run(
            "show",
            "--format=Commit: %H%nAuthor: %an%nDate: %cI%nSubject: %s%n%n%b",
            "--stat",
            "--patch",
            "--no-ext-diff",
            commit,
        ).stdout
        return ProjectEvent.create(
            project=self.project,
            event_type=EventType.COMMIT,
            source="version-control",
            timestamp=timestamp or None,
            content=shown[: self.patch_limit],
            metadata={
                "collector": "version_control",
                "repo_path": str(self.repo_path),
                "commit": commit,
                "truncated": len(shown) > self.patch_limit,
                "original_chars": len(shown),
            },
        )

    def _working_event(self) -> ProjectEvent | None:
        status = self._run("status", "--short").stdout.strip()
        if not status:
            return None
        stat = self._run("diff", "--stat").stdout.strip()
        patch = self._run("diff", "--no-ext-diff").stdout
        text = "Working tree status:\n" + status
        if stat:
            text += "\n\nDiff summary:\n" + stat
        if patch.strip():
            text += "\n\nPatch:\n" + patch[: self.patch_limit]
        return ProjectEvent.create(
            project=self.project,
            event_type=EventType.CODE_CHANGE,
            source="version-control-working-tree",
            content=text,
            metadata={
                "collector": "version_control",
                "repo_path": str(self.repo_path),
                "untracked_files": [
                    line[3:] for line in status.splitlines() if line.startswith("?? ")
                ],
                "truncated": len(patch) > self.patch_limit,
                "original_patch_chars": len(patch),
            },
        )

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo_path), *args],
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
