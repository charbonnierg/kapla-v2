from __future__ import annotations

from typing import Dict, List, Optional, Union

from pydantic import Field

from .base import AliasedModel
from .common import BasePythonConfig, BuildSystem


class DepedencyMeta(AliasedModel):
    path: Optional[str] = None
    develop: Optional[bool] = None
    optional: Optional[bool] = None
    url: Optional[str] = None
    git: Optional[str] = None
    branch: Optional[str] = None
    extras: Optional[List[str]] = None
    python: Optional[str] = None
    markers: Optional[str] = None
    allow_prereleases: Optional[bool] = Field(None, alias="allow-prereleases")


class Dependency(DepedencyMeta):
    """A dependency found in a pyproject.toml file.

    Dependencies can be found in:
      - `[tool.poetry.dependencies]`
      - `[tool.poetry.dev-dependencies]`

    Note: A dependency can also be declared as a string.

    References:
      * <https://python-poetry.org/docs/pyproject/#dependencies-and-dev-dependencies>
    """

    version: Optional[str] = None


class Group(AliasedModel):
    dependencies: Dict[str, Union[Dependency, str]] = {}
    optional: Optional[bool] = None


class PoetryConfig(BasePythonConfig):
    """Configuration of a poetry project found within pyproject.toml

    References:
        * [The pyproject.toml file](https://python-poetry.org/docs/pyproject/)
        * [Poetry pyproject.toml file](https://github.com/python-poetry/poetry/blob/master/pyproject.toml)
    """

    # Docs: <https://python-poetry.org/docs/pyproject/#dependencies-and-dev-dependencies>
    dependencies: Dict[str, Union[Dependency, str]]
    dev_dependencies: Dict[str, Union[Dependency, str]] = Field(
        {}, alias="dev-dependencies"
    )
    # Docs: <https://python-poetry.org/docs/pyproject/#extras>
    extras: Dict[str, List[str]] = {}
    # Docs: <https://python-poetry.org/docs/master/managing-dependencies/#dependency-groups>
    group: Dict[str, Group] = {}


class PyProjectTooling(AliasedModel):
    """[tool.*] sections of a pyproject.toml file"""

    poetry: PoetryConfig

    class Config:
        extra = "allow"


class BasePyProjectSpec(AliasedModel):
    build_system: BuildSystem = Field(..., alias="build-system")


class PyProjectSpec(BasePyProjectSpec):
    """Complete pyproject.toml file"""

    tool: PyProjectTooling


DEFAULT_BUILD_SYSTEM = BuildSystem(
    build_backend="poetry.core.masonry.api",
    requires=[
        "quara-poetry-core-next",
    ],
)
