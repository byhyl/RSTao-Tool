"""Abstract interface for project persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from migration_project.domain.project import Project


class ProjectRepository(ABC):
    """Port for loading and saving project files.

    Maps to: core/project_manager.py (ProjectManager)
    """

    @abstractmethod
    def load(self, path: str) -> Project:
        """Load a project from disk. Raises on error."""
        ...

    @abstractmethod
    def save(self, project: Project) -> bool:
        """Save a project to disk. Returns True on success."""
        ...

    @abstractmethod
    def backup_path(self, path: str) -> str:
        """Return the backup file path for a given project path."""
        ...
