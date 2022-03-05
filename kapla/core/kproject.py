from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
)

from pydantic import BaseModel, ValidationError

from kapla.specs.common import BuildSystem
from kapla.specs.kproject import ProjectSpec
from kapla.specs.pyproject import (
    DEFAULT_BUILD_SYSTEM,
    Dependency,
    Group,
    PoetryConfig,
    PyProjectSpec,
)

from .base import BaseProject
from .cmd import Command
from .errors import CommandFailedError
from .finder import find_dirs, find_files
from .io import load_yaml, write_toml, write_yaml
from .logger import logger
from .pyproject import KPyProject

if TYPE_CHECKING:
    from .repo import KRepo


SpecT = TypeVar("SpecT", bound=BaseModel)
ProjectT = TypeVar("ProjectT", bound="BaseKProject")


class BaseKProject(BaseProject[ProjectSpec], spec=ProjectSpec):
    """Base class for pyproject files implementing read and write operations"""

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
    def gitignore(self) -> List[str]:
        if self.repo:
            return self.repo.gitignore
        else:
            return super().gitignore

    @property
    def venv_path(self) -> Path:
        if self.repo:
            return self.repo.venv_path
        else:
            return super().venv_path

    @property
    def pyproject_path(self) -> Path:
        """Path used to write pyproject file"""
        return self.root / "pyproject.toml"

    @property
    def name(self) -> str:
        """The project name"""
        return self.spec.name

    @property
    def version(self) -> str:
        """The project version"""
        return self.spec.version

    def read(self, path: Union[str, Path]) -> Any:
        """Read YAML project specs"""
        return load_yaml(path)

    def write(self, path: Union[str, Path]) -> Path:
        """Write YAML project specs"""
        return write_yaml(self._raw, path)

    def get_local_dependencies(self) -> Dict[str, Dependency]:
        """Get a dict holding local dependencies of project"""
        # We cannot do anything without a repo
        if self.repo is None:
            return {}

        # Fetch project local dependencies
        local_projects = {
            name: self.repo.projects[name]
            for name in self.get_dependencies_names()
            if name in self.repo.projects
        }

        # Gather local dependencies to override
        return {
            name: Dependency.parse_obj(
                {
                    "path": project.root.as_posix(),
                    "develop": True,
                }
            )
            for name, project in local_projects.items()
        }

    def get_build_dependencies(
        self,
        include_local: bool = True,
        include_python: bool = True,
    ) -> Tuple[Dict[str, Dependency], Dict[str, List[str]], Dict[str, Group]]:
        """Return dependencies, extras and groups"""
        dependencies: Dict[str, Dependency] = {}
        groups: Dict[str, Group] = {}
        extras: Dict[str, List[str]] = {}
        if self.repo is None:
            lock = {}
        else:
            lock = self.repo.packages_lock
        # Iterate over dependencies and replace version
        for dep in self.spec.dependencies:
            if isinstance(dep, str):
                dependencies[dep] = Dependency.parse_obj(
                    {"version": lock.get(dep.lower(), {"version": "*"})["version"]}
                )
            else:
                for key, value in dep.items():
                    dependencies[key] = Dependency.parse_obj(
                        {
                            **value.dict(exclude_unset=True, by_alias=True),
                            "version": lock.get(key.lower(), {"version": "*"})[
                                "version"
                            ],
                        }
                    )
        # Iterate over extra dependencies and replace version
        for group_name, group_dependencies in self.spec.extras.items():
            # Let's create a group and an extra
            groups[group_name] = Group(dependencies={})
            extras[group_name] = []
            # Iterate over dependencies and replace version
            for dep in group_dependencies:
                if isinstance(dep, str):
                    # Add dependency to group
                    groups[group_name].dependencies[dep] = Dependency.parse_obj(
                        {"version": lock.get(dep, {"version": "*"})["version"]}
                    )
                    # Add dependency to extra
                    if dep not in extras[group_name]:
                        extras[group_name].append(dep)
                    # Add dependency to optional dependencies
                    if dep not in dependencies:
                        dependencies[dep] = Dependency.parse_obj(
                            {
                                "version": lock.get(dep, {"version": "*"})["version"],
                                "optional": True,
                            }
                        )
                else:
                    for key, value in dep.items():
                        # Add dependency to group
                        groups[group_name].dependencies[key] = Dependency.parse_obj(
                            {
                                **value.dict(exclude_unset=True, by_alias=True),
                                "version": lock.get(key, {"version": "*"})["version"],
                            }
                        )
                        # Add dependency to extra
                        if key not in extras[group_name]:
                            extras[group_name].append(key)
                        # Add dependency to optional dependencies
                        if key not in dependencies:
                            dependencies[key] = Dependency.parse_obj(
                                {
                                    **value.dict(exclude_unset=True, by_alias=True),
                                    "version": lock.get(key, {"version": "*"})[
                                        "version"
                                    ],
                                    "optional": True,
                                }
                            )
        # Make sure python dependency is set
        if include_python:
            if "python" not in dependencies:
                dependencies["python"] = lock.get("python", ">=3.8,<4")
        else:
            dependencies.pop("python", None)
        # Remove local deps
        if not include_local:
            for dep in self.get_local_dependencies_names():
                dependencies.pop(dep)
        # Return values
        return dependencies, extras, groups

    def get_install_dependencies(
        self,
    ) -> Tuple[Dict[str, Dependency], Dict[str, List[str]], Dict[str, Group]]:
        dependencies, extras, groups = self.get_build_dependencies()
        local_dependencies = self.get_local_dependencies()
        # Iterate a second time on dependencies to apply dep overrides
        for name in dependencies:
            if name in local_dependencies:
                dependencies[name] = local_dependencies[name]

        # Iterate a second time on groups
        for group_name, group in groups.items():
            # Iterate on each group dependencies
            for name in group.dependencies:
                if name in local_dependencies:
                    groups[group_name].dependencies[name] = local_dependencies[name]

        return dependencies, extras, groups

    def get_dependencies_names(self) -> List[str]:
        names: Set[str] = set()
        for dep in self.spec.dependencies:
            if isinstance(dep, str):
                names.add(dep)
            else:
                for name in dep:
                    names.add(name)
        for extra_deps in self.spec.extras.values():
            for dep in extra_deps:
                if isinstance(dep, str):
                    names.add(dep)
                else:
                    for name in dep:
                        names.add(name)
        return list(names)

    def get_local_dependencies_names(self) -> List[str]:
        """Get local dependencies names (include all groups)"""
        return list(self.get_local_dependencies())

    def get_pyproject_spec(
        self, develop: bool = False, build_system: BuildSystem = DEFAULT_BUILD_SYSTEM
    ) -> PyProjectSpec:
        """Create content of pyproject.toml file according to project.yaml"""
        if develop:
            dependencies, extras, groups = self.get_install_dependencies()
        else:
            dependencies, extras, groups = self.get_build_dependencies()
        # Gather raw tool.poetry configuration byt exclude dependencies, extras and group fields
        raw_poetry_config = self.spec.dict(
            by_alias=True,
            exclude_unset=True,
            exclude={"dependencies", "extras", "group", "docker"},
        )
        # Generate poetry config by merging raw config and gather dependencies, extras and group
        poetry_config = PoetryConfig(
            **raw_poetry_config,
            dependencies=dependencies,
            extras=extras,
            group=groups,
        )
        # Generate pyproject file
        return PyProjectSpec(tool={"poetry": poetry_config}, build_system=build_system)

    def write_pyproject(
        self,
        path: Union[str, Path, None] = None,
        develop: bool = False,
        build_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
    ) -> KPyProject:
        """Write auto-generated pyproject.toml file.

        If path argument is not specified, file is generated in the project directory by default.
        """
        spec = self.get_pyproject_spec(develop=develop, build_system=build_system)
        pyproject_path = Path(path) if path else self.pyproject_path
        content = spec.dict()
        write_toml(content, pyproject_path)
        try:
            pyproject = KPyProject(pyproject_path, repo=self.repo)
        except ValidationError as err:
            logger.error("Failed to validate", exc_info=err)
            raise
        return pyproject

    @contextmanager
    def temporary_pyproject(
        self: ProjectT,
        path: Union[str, Path, None] = None,
        develop: bool = False,
        build_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
        clean: bool = True,
    ) -> Iterator[KPyProject]:
        """A context manager which ensures pyproject.toml is written to disk within context and removed out of context"""
        pyproject = self.write_pyproject(
            path, develop=develop, build_system=build_system
        )
        try:
            yield pyproject
        finally:
            if clean:
                self.clean_poetry_files()

    def clean_poetry_files(self, pyproject_path: Union[str, Path, None] = None) -> None:
        """Remove auto-generated poetry files"""
        pyproject_path = Path(pyproject_path) if pyproject_path else self.pyproject_path
        pyproject_path.unlink(missing_ok=True)
        lock_path = pyproject_path.parent / "poetry.lock"
        lock_path.unlink(missing_ok=True)

    async def venv(
        self,
        name: str = ".venv",
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
    ) -> Path:
        if self.repo:
            return await self.repo.venv(name, timeout, deadline)
        else:
            return await super().venv(name, timeout, deadline)

    async def ensure_venv(
        self,
        name: str = ".venv",
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
    ) -> None:
        if self.repo:
            return await self.repo.ensure_venv(name, timeout=timeout)
        else:
            return await super().ensure_venv(name, deadline=deadline)

    def remove_venv(
        self,
        name: str = ".venv",
    ) -> None:
        if self.repo:
            self.repo.remove_venv(name)
        else:
            super().remove_venv(name)


class KProject(BaseKProject):
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
        clean: bool = True,
    ) -> Command:
        """Show project dependencies"""
        if not self.repo:
            with self.temporary_pyproject(
                self.pyproject_path, develop=True, clean=clean
            ) as pyproject:
                await pyproject.lock(
                    echo_stdout=None, no_update=True, raise_on_error=True
                )
                return await pyproject.show(
                    exclude_groups=exclude_groups,
                    include_groups=include_groups,
                    only_groups=only_groups,
                    default=default,
                    tree=tree,
                    latest=latest,
                    outdated=outdated,
                    timeout=timeout,
                    deadline=deadline,
                    raise_on_error=raise_on_error,
                )
        else:
            try:
                for project in self.repo.get_projects_stack(
                    self.get_local_dependencies_names()
                ):
                    project.write_pyproject(develop=True)
                # Write pyproject
                pyproject = self.write_pyproject(develop=True)
                # Lock and show deps
                await pyproject.lock(
                    echo_stdout=None, no_update=True, raise_on_error=False
                )
                return await pyproject.show(
                    exclude_groups=exclude_groups,
                    include_groups=include_groups,
                    only_groups=only_groups,
                    default=default,
                    tree=tree,
                    latest=latest,
                    outdated=outdated,
                    timeout=timeout,
                    deadline=deadline,
                    raise_on_error=False,
                )
            finally:
                self.repo.clean_pyproject_files()

    async def build(
        self,
        env: Optional[Mapping[str, Any]] = None,
        build_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
        clean: bool = True,
    ) -> Command:
        with self.temporary_pyproject(
            self.pyproject_path, develop=False, build_system=build_system, clean=clean
        ) as pyproject:
            print(f"Starting build for {self.name}")
            return await pyproject.build(
                env=env,
                timeout=timeout,
                deadline=deadline,
                raise_on_error=raise_on_error,
            )

    def should_skip_install(self) -> bool:
        if self.repo:
            for _ in find_files(
                f"{self.name.replace('-','_').lower()}.pth",
                root=self.venv_path,
                ignore=[
                    "bin/",
                    "Scripts/",
                    "include",
                    "Include",
                    "share",
                    "doc",
                    "etc",
                ],
            ):
                return True
        return False

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
        build_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
        clean: bool = True,
    ) -> Optional[Command]:
        if self.should_skip_install():
            return None
        with self.temporary_pyproject(
            self.pyproject_path,
            clean=clean,
            develop=True,
            build_system=build_system,
        ) as pyproject:
            return await pyproject.install(
                exclude_groups=exclude_groups,
                include_groups=include_groups,
                only_groups=only_groups,
                default=default,
                sync=sync,
                no_root=no_root,
                dry_run=dry_run,
                extras=extras,
                timeout=timeout,
                deadline=deadline,
                raise_on_error=raise_on_error,
            )

    async def install_pep_660(
        self,
        exclude_groups: Union[Iterable[str], str, None] = None,
        include_groups: Union[Iterable[str], str, None] = None,
        only_groups: Union[Iterable[str], str, None] = None,
        default: bool = False,
        build_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
        clean: bool = True,
    ) -> Optional[Command]:
        if not self.repo:
            raise NotImplementedError(
                "PEP 660 install is not supported without parent repo"
            )
        if self.should_skip_install():
            return None
        groups = list(self.spec.extras)
        if default:
            groups = []
        elif only_groups:
            groups = [group for group in groups if group in only_groups]
        else:
            if exclude_groups:
                groups = [group for group in groups if group not in exclude_groups]
            if include_groups:
                groups = [group for group in groups if group in include_groups]
        target = self.root.as_posix()
        if groups:
            target += f'[{",".join(groups)}]'
        with self.temporary_pyproject(
            self.pyproject_path,
            clean=clean,
            develop=False,
            build_system=build_system,
        ):
            return await self.repo.pip_install(
                "-e",
                target,
                timeout=timeout,
                deadline=deadline,
                raise_on_error=raise_on_error,
            )

    def clean(self) -> None:
        """Remove well-known non versioned files"""
        # Remove venv
        shutil.rmtree(Path(self.root, ".venv"), ignore_errors=True)
        # Remove directories
        for path in find_dirs(
            self.gitignore,
            self.root,
        ):
            shutil.rmtree(path, ignore_errors=True)
        # Remove files
        for path in find_files(
            self.gitignore,
            root=self.root,
        ):
            path.unlink(missing_ok=True)

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
    ) -> Dict[str, Union[str, Dependency]]:
        if group:
            repo_group = self.name + "--" + group
        else:
            repo_group = self.name
        if self.repo:
            group_before = self.repo.spec.tool.poetry.group.get(repo_group, Group())
            await self.repo.add(
                package=package,
                group=repo_group,
                editable=editable,
                extras=extras,
                optional=optional,
                python=python,
                platform=platform,
                source=source,
                allow_prereleases=allow_prereleases,
                dry_run=dry_run,
                lock=lock,
                timeout=timeout,
                deadline=deadline,
                raise_on_error=True,
            )
            # Refresh repo metadata
            self.repo.refresh()
            group_after = self.repo.spec.tool.poetry.group[repo_group]
            # Get package diff
            new_packages = set(group_after.dependencies).difference(
                group_before.dependencies
            )
            # FIXME: Write new deps in YAML proejct
            # Return new packages
            return {name: group_after.dependencies[name] for name in new_packages}

        else:
            raise NotImplementedError(
                "It's not possible to add dependencies to projet without parent repo"
            )

    async def remove(
        self,
        package: str,
        group: Optional[str] = None,
        dry_run: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
    ) -> Optional[Dict[str, Union[str, Dependency]]]:
        if group:
            repo_group = self.name + "--" + group
        else:
            repo_group = self.name
        if self.repo:
            group_before = self.repo.spec.tool.poetry.group.get(repo_group, Group())
            try:
                await self.repo.remove(
                    package,
                    group=repo_group,
                    dry_run=dry_run,
                    timeout=timeout,
                    deadline=deadline,
                    raise_on_error=True,
                )
            except CommandFailedError:
                # Try to remove dep anyway
                return None
            # Refresh repo metadata
            self.repo.refresh()
            group_after = self.repo.spec.tool.poetry.group[repo_group]
            # Get package diff
            removed_packages = set(group_before.dependencies).difference(
                group_after.dependencies
            )
            # Return removed packages
            return {name: group_before.dependencies[name] for name in removed_packages}

        else:
            raise NotImplementedError(
                "It's not possible to remove dependencies to projet without parent repo"
            )
