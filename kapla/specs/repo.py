from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import Field

from .base import AliasedModel
from .pyproject import Dependency, Group, PyProjectSpec, PyProjectTooling


class RepoConfig(AliasedModel):
    workspaces: Dict[str, List[str]] = {}


class RepoTooling(PyProjectTooling):
    repo: RepoConfig = Field(default_factory=RepoConfig)
    auto_generated: Optional[bool] = Field(False, alias="auto-generated")


class RepoSpec(PyProjectSpec):
    tool: RepoTooling


class KPyProjectSpec(RepoSpec):
    pass


class ProjectDependencies(AliasedModel):
    repo_dependencies: Dict[str, Dependency] = {}
    repo_groups: Dict[str, Group] = {}
    dependencies: Dict[str, Dependency] = {}
    groups: Dict[str, Group] = {}
    python: str
