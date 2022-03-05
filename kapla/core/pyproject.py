from __future__ import annotations

import sys
from functools import partial
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Type,
    TypeVar,
    Union,
)

from pydantic import BaseModel

from kapla.specs.pyproject import Dependency, PyProjectSpec
from kapla.specs.repo import KPyProjectSpec

from .base import BaseProject
from .cmd import Command, echo, run_command
from .errors import PyprojectNotFoundError
from .finder import lookup_file
from .io import load_toml, write_toml

if TYPE_CHECKING:
    from .repo import KRepo


SpecT = TypeVar("SpecT", bound=BaseModel)
PyProjectT = TypeVar("PyProjectT", bound="BasePyProject")


class BasePyProject(BaseProject[PyProjectSpec], spec=PyProjectSpec):
    """Base class for pyproject files implementing read and write operations"""

    _FIELDS = set(PyProjectSpec.__fields__) | set(
        field.alias for field in PyProjectSpec.__fields__.values() if field.alias
    )

    def get_property(self, key: str, raw: bool = False) -> Any:
        # Process first token
        first_token = key.split(".")[0]
        # Add "poetry.tool" prefix when needed
        if first_token not in self._FIELDS:
            key = "tool.poetry." + key
        # Use method from parent class
        return super().get_property(key, raw=raw)

    def read(self, path: Union[str, Path]) -> Any:
        """Read TOML pyproject specs"""
        return load_toml(path)

    def write(self, path: Union[str, Path]) -> Path:
        """Write TOML pyproject specs"""
        return write_toml(self._raw, path)

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


class PyProject(BasePyProject):
    @property
    def name(self) -> str:
        """The project name"""
        return self.spec.tool.poetry.name

    @property
    def version(self) -> str:
        """The project version"""
        return self.spec.tool.poetry.version

    async def build(
        self,
        env: Optional[Mapping[str, Any]] = None,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
    ) -> Command:
        return await run_command(
            "poetry build",
            cwd=self.root,
            env=env,
            timeout=timeout,
            deadline=deadline,
            rc=0 if raise_on_error else None,
        )

    async def install(
        self,
        exclude_groups: Union[Iterable[str], str, None] = None,
        include_groups: Union[Iterable[str], str, None] = None,
        only_groups: Union[Iterable[str], str, None] = None,
        default: bool = False,
        sync: bool = False,
        no_root: bool = False,
        dry_run: bool = False,
        extras: Union[Iterable[str], str, None] = None,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
        echo_stdout: Optional[Callable[[str], None]] = None,
        echo_stderr: Optional[Callable[[str], None]] = partial(echo, file=sys.stderr),
    ) -> Command:
        """Install poetry package.

        Reference: https://python-poetry.org/docs/master/cli/#install
        """
        venv_bin = Path(self.python_executable).parent
        venv_path = venv_bin.parent
        environment = {"VIRTUAL_ENV": venv_path.as_posix()}
        cmd = Command(
            "poetry install",
            cwd=self.root,
            env=environment,
            append_path=venv_bin,
            timeout=timeout,
            deadline=deadline,
            echo_stdout=echo_stdout,
            echo_stderr=echo_stderr,
        )

        if exclude_groups:
            cmd.add_repeat_option("--without", exclude_groups)
        if include_groups:
            cmd.add_repeat_option("--with", include_groups)
        if only_groups:
            cmd.add_repeat_option("--only", only_groups)
        if default:
            cmd.add_option("--default")
        if sync:
            cmd.add_option("--sync")
        if no_root:
            cmd.add_option("--no-root")
        if dry_run:
            cmd.add_option("--dry-run")
        if extras:
            cmd.add_option("--extras")

        return await cmd.run(rc=0 if raise_on_error else None)

    async def lock(
        self,
        check: bool = False,
        no_update: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        echo_stdout: Optional[Callable[[str], None]] = echo,
        echo_stderr: Optional[Callable[[str], None]] = partial(echo, file=sys.stderr),
        raise_on_error: bool = False,
    ) -> Command:
        """This command locks (without installing) the dependencies specified in pyproject.toml.

        Reference: https://python-poetry.org/docs/master/cli/#lock
        """
        venv_bin = Path(self.python_executable).parent
        venv_path = venv_bin.parent
        environment = {"VIRTUAL_ENV": venv_path.as_posix()}
        cmd = Command(
            "poetry lock",
            cwd=self.root,
            env=environment,
            append_path=venv_bin,
            timeout=timeout,
            deadline=deadline,
            echo_stdout=echo_stdout,
            echo_stderr=echo_stderr,
        )
        if check:
            cmd.add_option("--check")
        if no_update:
            cmd.add_option("--no-update")
        return await cmd.run(0 if raise_on_error else None)

    async def update(
        self,
        dry_run: bool = False,
        lock: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
    ) -> Command:
        """Perform package update. Use lock=True if you wish to update package lock only.

        Reference: https://python-poetry.org/docs/master/cli/#update
        """
        venv_bin = Path(self.python_executable).parent
        venv_path = venv_bin.parent
        environment = {"VIRTUAL_ENV": venv_path.as_posix()}
        cmd = Command(
            "poetry update",
            cwd=self.root,
            env=environment,
            append_path=venv_bin,
            timeout=timeout,
            deadline=deadline,
        )
        if dry_run:
            cmd.add_option("--dry-run")
        if lock:
            cmd.add_option("--lock-only")

        return await cmd.run(rc=0 if raise_on_error else None)

    async def add(
        self,
        package: str,
        group: Optional[str] = None,
        editable: bool = False,
        extras: Union[str, List[str], None] = None,
        optional: bool = False,
        python: Optional[str] = None,
        platform: Union[str, List[str], None] = None,
        source: Optional[str] = None,
        allow_prereleases: bool = False,
        dry_run: bool = False,
        lock: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
    ) -> Command:
        """Add a package dependency.

        Reference: https://python-poetry.org/docs/master/cli/#add
        """
        venv_bin = Path(self.python_executable).parent
        venv_path = venv_bin.parent
        environment = {"VIRTUAL_ENV": venv_path.as_posix()}
        cmd = Command(
            "poetry add",
            cwd=self.root,
            env=environment,
            append_path=venv_bin,
            timeout=timeout,
            deadline=deadline,
        )
        if group:
            cmd.add_option("--group", group)
        if optional:
            cmd.add_option("--optional")
        if python:
            cmd.add_option("--python", python)
        if platform:
            cmd.add_repeat_option("--platform", platform)
        if source:
            cmd.add_option("--source", source)
        if extras:
            cmd.add_repeat_option("--extras", extras)
        if allow_prereleases:
            cmd.add_option("--allow-prereleases")
        if dry_run:
            cmd.add_option("--dry-run")
        if lock:
            cmd.add_option("--lock")
        if editable:
            cmd.add_option("--editable")
        cmd.add_argument(package)

        return await cmd.run(rc=0 if raise_on_error else None)

    async def remove(
        self,
        package: str,
        group: Optional[str] = None,
        dry_run: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
    ) -> Command:
        """Remove a package dependency

        Reference: https://python-poetry.org/docs/master/cli/#remove
        """
        venv_bin = Path(self.python_executable).parent
        venv_path = venv_bin.parent
        environment = {"VIRTUAL_ENV": venv_path.as_posix()}
        cmd = Command(
            "poetry remove",
            cwd=self.root,
            env=environment,
            append_path=venv_bin,
            timeout=timeout,
            deadline=deadline,
        )

        if group:
            cmd.add_option("--group", group)
        if dry_run:
            cmd.add_option("--dry-run")
        cmd.add_argument(package)

        await cmd.run(rc=0 if raise_on_error else None)

        return cmd

    async def show(
        self,
        exclude_groups: Union[List[str], str, None] = None,
        include_groups: Union[List[str], str, None] = None,
        only_groups: Union[List[str], str, None] = None,
        default: Union[List[str], str, None] = None,
        tree: bool = False,
        latest: bool = False,
        outdated: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
    ) -> Command:
        """Show project dependencies"""
        venv_bin = Path(self.python_executable).parent
        venv_path = venv_bin.parent
        environment = {"VIRTUAL_ENV": venv_path.as_posix()}
        cmd = Command(
            "poetry show",
            cwd=self.root,
            env=environment,
            append_path=venv_bin,
            timeout=timeout,
            deadline=deadline,
        )
        if exclude_groups:
            cmd.add_repeat_option("--without", exclude_groups)
        if include_groups:
            cmd.add_repeat_option("--with", include_groups)
        if only_groups:
            cmd.add_repeat_option("--only", only_groups)
        if default:
            cmd.add_option("--default")
        if tree:
            cmd.add_option("--tree")
        if latest:
            cmd.add_option("--latest")
        if outdated:
            cmd.add_option("--outdated")

        return await cmd.run(rc=0 if raise_on_error else None)

    async def publish(
        self,
        repository: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        dry_run: Optional[str] = None,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
    ) -> Command:
        """This command publishes the package, previously built with the build command, to the remote repository.

        Reference: https://python-poetry.org/docs/master/cli/#publish
        """
        venv_bin = Path(self.python_executable).parent
        venv_path = venv_bin.parent
        environment = {"VIRTUAL_ENV": venv_path.as_posix()}
        cmd = Command(
            "poetry publish",
            cwd=self.root,
            env=environment,
            append_path=venv_bin,
            timeout=timeout,
            deadline=deadline,
        )
        if repository:
            cmd.add_option("--repository", repository)
        if username:
            cmd.add_option("--username", username)
        if password:
            cmd.add_option("--password", password)
        if dry_run:
            cmd.add_option("--dry-run", dry_run)
        return await cmd.run(rc=0 if raise_on_error else None)

    def get_dependency(self, name: str) -> Optional[Dependency]:
        dep = self.spec.tool.poetry.dependencies.get(name)
        if dep is None:
            return None
        return dep if isinstance(dep, Dependency) else Dependency(version=dep)

    def get_group_dependency(self, group_name: str, name: str) -> Optional[Dependency]:
        group = self.spec.tool.poetry.group.get(group_name)
        if group is None:
            return None
        dep = group.dependencies.get(name)
        if dep is None:
            return None
        return dep if isinstance(dep, Dependency) else Dependency(version=dep)

    def get_dependencies(self) -> Dict[str, Dependency]:
        return {
            name: dep if isinstance(dep, Dependency) else Dependency(version=dep)
            for name, dep in self.spec.tool.poetry.dependencies.items()
        }

    def get_group_dependencies(self, group_name: str) -> Dict[str, Dependency]:
        group = self.spec.tool.poetry.group.get(group_name, None)
        if group is None:
            return {}
        return {
            name: dep if isinstance(dep, Dependency) else Dependency(version=dep)
            for name, dep in group.dependencies.items()
        }


class BaseKPyProject(PyProject, spec=KPyProjectSpec):
    __SPEC__: Type[KPyProjectSpec]
    spec: KPyProjectSpec

    def find_repo_root(self) -> Optional[Path]:
        return lookup_file("pyproject.toml", start=self.root.parent)


class KPyProject(BaseKPyProject):
    def __init__(
        self, filepath: Union[str, Path], repo: Optional[KRepo] = None
    ) -> None:
        super().__init__(filepath)
        self.repo = repo

    @property
    def venv_path(self) -> Path:
        if self.repo:
            return self.repo.venv_path
        else:
            return super().venv_path

    @property
    def gitignore(self) -> List[str]:
        if self.repo:
            return self.repo.gitignore
        else:
            return super().gitignore

    async def venv(
        self,
        name: str = ".venv",
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
    ) -> Path:
        if self.repo:
            return await self.repo.venv(name, timeout=timeout, deadline=deadline)
        else:
            return await super().venv(name, timeout=timeout, deadline=deadline)

    async def ensure_venv(
        self,
        name: str = ".venv",
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
    ) -> None:
        if self.repo:
            return await self.repo.ensure_venv(name, timeout=timeout, deadline=deadline)
        else:
            return await super().ensure_venv(name, timeout=timeout, deadline=deadline)

    def remove_venv(
        self,
        name: str = ".venv",
    ) -> None:
        if self.repo:
            self.repo.remove_venv(name)
        else:
            super().remove_venv(name)
