
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.project_store import load_project


class ProjectContext:
    """Launcher-wide reference to the Project JSON selected in Module 0."""

    def __init__(self):
        self.path: Path | None = None
        self.project: dict[str, Any] | None = None

    def clear(self, project: dict[str, Any] | None = None) -> None:
        self.path = None
        self.project = project

    def set(self, path: str | Path, project: dict[str, Any] | None = None) -> None:
        self.path = Path(path)
        self.project = project if project is not None else load_project(self.path)

    def synchronize_from_disk(self) -> dict[str, Any] | None:
        if self.path is not None and self.path.exists():
            latest = load_project(self.path)
            if self.project is None:
                self.project = latest
            else:
                self.project.clear()
                self.project.update(latest)
        return self.project

    def reload(self) -> dict[str, Any] | None:
        if self.path is not None and self.path.exists():
            self.project = load_project(self.path)
        return self.project

    @property
    def display_path(self) -> str:
        return str(self.path) if self.path is not None else ""
