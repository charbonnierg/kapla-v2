from __future__ import annotations

from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Type,
    TypeVar,
    Union,
)

import tomlkit

from kapla.specs.pyproject import Dependency, PyProjectSpec
from kapla.wrappers import poetry

from ..core.cmd import Command
from ..core.errors import PyprojectNotFoundError
from ..core.finder import lookup_file
from ..core.io import read_toml, write_toml
from .base import BasePythonProject

if TYPE_CHECKING:
    from .krepo import KRepo


class ReadWriteTOMLMixin:
    """Read TOML pyproject specs"""

    _raw: Any

    def read(self, path: Union[str, Path]) -> Any:
        return read_toml(path)

    def write(self, path: Union[str, Path]) -> Path:
        """Write TOML pyproject specs"""
        return write_toml(self._raw, path)

    @staticmethod
    def _create_inline_tables(data: Dict[str, Dict[str, Any]]) -> tomlkit.items.Table:
        root_table = tomlkit.table()
        for key, value in data.items():
            sub_table = tomlkit.inline_table()
            sub_table.update(value)
            root_table.append(key, sub_table)
        return root_table


PyProjectT = TypeVar("PyProjectT", bound="PyProject")


class PyProject(
    ReadWriteTOMLMixin, BasePythonProject[PyProjectSpec], spec=PyProjectSpec
):
    @property
    def name(self) -> str:
        """The project name"""
        return self.spec.tool.poetry.name

    @property
    def version(self) -> str:
        """The project version"""
        return self.spec.tool.poetry.version

    def get_dependency(self, name: str) -> Optional[Dependency]:
        """Get a single dependency"""
        dep = self.spec.tool.poetry.dependencies.get(name)
        if dep is None:
            return None
        return dep if isinstance(dep, Dependency) else Dependency(version=dep)

    def get_group_dependency(self, name: str, group_name: str) -> Optional[Dependency]:
        """Get a a single dependency from a group"""
        group = self.spec.tool.poetry.group.get(group_name)
        if group is None:
            return None
        dep = group.dependencies.get(name)
        if dep is None:
            return None
        return dep if isinstance(dep, Dependency) else Dependency(version=dep)

    def get_dependencies(self) -> Dict[str, Dependency]:
        """Get all dependencies (group dependencies are excluded)"""
        return {
            name: dep if isinstance(dep, Dependency) else Dependency(version=dep)
            for name, dep in self.spec.tool.poetry.dependencies.items()
        }

    def get_group_dependencies(self, group_name: str) -> Dict[str, Dependency]:
        """Get all dependencies from a single group"""
        group = self.spec.tool.poetry.group.get(group_name, None)
        if group is None:
            return {}
        return {
            name: dep if isinstance(dep, Dependency) else Dependency(version=dep)
            for name, dep in group.dependencies.items()
        }

    def get_all_group_dependencies(self) -> Dict[str, Dict[str, Dependency]]:
        """Get all group depedencies"""
        groups: Dict[str, Dict[str, Dependency]] = {}
        for group in self.spec.tool.poetry.group:
            groups[group] = self.get_group_dependencies(group)
        return groups

    async def poetry_build(
        self,
        dist_format: Optional[str] = None,
        env: Optional[Mapping[str, Any]] = None,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        quiet: bool = False,
        raise_on_error: bool = False,
        **kwargs: Any,
    ) -> Command:
        """Build project using poetry build command"""
        return await poetry.build(
            directory=self.root,
            virtualenv=self.venv_path,
            dist_format=dist_format,
            env=env,
            quiet=quiet,
            timeout=timeout,
            deadline=deadline,
            raise_on_error=raise_on_error,
            **kwargs,
        )

    async def poetry_install(
        self,
        exclude_groups: Union[Iterable[str], str, None] = None,
        include_groups: Union[Iterable[str], str, None] = None,
        only_groups: Union[Iterable[str], str, None] = None,
        default: bool = False,
        sync: bool = False,
        no_root: bool = False,
        extras: Union[Iterable[str], str, None] = None,
        dry_run: bool = False,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Install project using poetry install command"""
        return await poetry.install(
            directory=self.root,
            virtualenv=self.venv_path,
            exclude_groups=exclude_groups,
            include_groups=include_groups,
            only_groups=only_groups,
            default=default,
            sync=sync,
            no_root=no_root,
            dry_run=dry_run,
            extras=extras,
            quiet=quiet,
            raise_on_error=raise_on_error,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def poetry_lock(
        self,
        check: bool = False,
        no_update: bool = False,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """This command locks (without installing) the dependencies specified in pyproject.toml"""
        return await poetry.lock(
            directory=self.root,
            virtualenv=self.venv_path,
            check=check,
            no_update=no_update,
            quiet=quiet,
            raise_on_error=raise_on_error,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def poetry_update(
        self,
        lock: bool = False,
        dry_run: bool = False,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Perform package update. Use lock=True if you wish to update package lock only."""
        return await poetry.update(
            directory=self.root,
            virtualenv=self.venv_path,
            lock=lock,
            dry_run=dry_run,
            quiet=quiet,
            raise_on_error=raise_on_error,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def poetry_add(
        self,
        *package: str,
        group: Optional[str] = None,
        editable: bool = False,
        extras: Union[str, Iterable[str], None] = None,
        optional: bool = False,
        python: Optional[str] = None,
        platform: Union[str, Iterable[str], None] = None,
        source: Optional[str] = None,
        allow_prereleases: bool = False,
        lock: bool = False,
        dry_run: bool = False,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Add a package dependency."""
        return await poetry.add(
            *package,
            directory=self.root,
            virtualenv=self.venv_path,
            group=group,
            editable=editable,
            extras=extras,
            optional=optional,
            python=python,
            platform=platform,
            source=source,
            allow_prereleases=allow_prereleases,
            lock=lock,
            dry_run=dry_run,
            quiet=quiet,
            raise_on_error=raise_on_error,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def poetry_remove(
        self,
        package: Union[str, Iterable[str]],
        group: Optional[str] = None,
        dry_run: bool = False,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Remove a package dependency"""
        return await poetry.remove(
            package,
            directory=self.root,
            virtualenv=self.venv_path,
            group=group,
            dry_run=dry_run,
            quiet=quiet,
            raise_on_error=raise_on_error,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def poetry_show(
        self,
        exclude_groups: Union[Iterable[str], str, None] = None,
        include_groups: Union[Iterable[str], str, None] = None,
        only_groups: Union[Iterable[str], str, None] = None,
        default: Union[Iterable[str], str, None] = None,
        tree: bool = False,
        latest: bool = False,
        outdated: bool = False,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Show project dependencies"""
        return await poetry.show(
            directory=self.root,
            virtualenv=self.venv_path,
            exclude_groups=exclude_groups,
            include_groups=include_groups,
            only_groups=only_groups,
            default=default,
            tree=tree,
            latest=latest,
            outdated=outdated,
            quiet=quiet,
            raise_on_error=raise_on_error,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def poetry_publish(
        self,
        repository: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        dry_run: Optional[str] = None,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Publish project artifacts to repository"""
        return await poetry.publish(
            directory=self.root,
            virtualenv=self.venv_path,
            repository=repository,
            username=username,
            password=password,
            dry_run=dry_run,
            quiet=quiet,
            raise_on_error=raise_on_error,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    @classmethod
    def find_current(
        cls: Type[PyProjectT], start: Union[None, str, Path] = None
    ) -> PyProjectT:
        """Find project from current directory by default"""
        projectfile = lookup_file("pyproject.toml", start=start)
        if projectfile:
            return cls(projectfile)
        raise PyprojectNotFoundError(
            "Cannot find any pyproject.toml file in current directory or parent directories."
        )


RepoT = TypeVar("RepoT", bound=PyProject)


class KPyProject(PyProject):
    """Parent class for child projects.

    Child projects are projects without virtual environment in their directories.
    Environment is expected to be located in the root repository instead.
    """

    def __init__(
        self,
        filepath: Union[str, Path],
        repo: Optional[KRepo] = None,
        workspace: Optional[str] = None,
    ) -> None:
        super().__init__(filepath)
        self.repo = repo
        self.workspace = workspace

    @property
    def venv_path(self) -> Path:
        """Get path to virtual environment of the project"""
        if self.repo:
            return self.repo.venv_path
        return super().venv_path

    @property
    def gitignore(self) -> List[str]:
        """Constant value at the moment. We should parse project gitignore in the future.

        FIXME: Support reading gitignore from project
        """
        if self.repo:
            return self.repo.gitignore
        else:
            return super().gitignore
