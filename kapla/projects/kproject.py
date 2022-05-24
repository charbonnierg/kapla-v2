from __future__ import annotations

import shutil
from collections import defaultdict
from contextlib import contextmanager
from functools import partial
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
    Union,
)

from anyio import create_task_group
from pydantic import ValidationError

from kapla.specs.common import BuildSystem
from kapla.specs.kproject import KProjectSpec
from kapla.specs.pyproject import (
    DEFAULT_BUILD_SYSTEM,
    Dependency,
    Group,
    PoetryConfig,
    PyProjectSpec,
)

from ..core.cmd import Command, get_deadline
from ..core.errors import CommandFailedError
from ..core.finder import find_dirs, find_files
from ..core.io import read_yaml, write_toml, write_yaml
from ..core.logger import logger
from .base import BasePythonProject
from .pyproject import KPyProject

if TYPE_CHECKING:
    from .krepo import KRepo


class ReadWriteYAMLMixin:
    _raw: Any

    def read(self, path: Union[str, Path]) -> Any:
        """Read YAML project specs"""
        return read_yaml(path)

    def write(self, path: Union[str, Path]) -> Path:
        """Write YAML project specs"""
        return write_yaml(self._raw, path)


class KProject(ReadWriteYAMLMixin, BasePythonProject[KProjectSpec], spec=KProjectSpec):
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
        if self.spec.version is None and self.repo is not None:
            self.spec.version = self.repo.version

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

    @property
    def pyproject_path(self) -> Path:
        """Path used to write pyproject file"""
        return self.root / "pyproject.toml"

    @property
    def name(self) -> str:
        """The project name"""
        return self.spec.name

    @property
    def slug(self) -> str:
        return self.spec.name.replace("-", "_")

    @property
    def version(self) -> str:
        """The project version"""
        if self.spec.version:
            return self.spec.version
        if self.repo:
            return self.repo.version
        return ""

    def is_already_installed(self) -> bool:
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

    def get_dependencies_names(self, include_extras: bool = True) -> List[str]:
        """Get a list of dependencies names"""
        names: Set[str] = set()
        for dep in self.spec.dependencies:
            if isinstance(dep, str):
                names.add(dep)
            else:
                for name in dep:
                    names.add(name)
        if include_extras:
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
        _need_to_inspect = set(local_projects)
        _inspected: Set[str] = set([self.name])
        # For each local dependency
        while _need_to_inspect:
            local_dep = local_projects[_need_to_inspect.pop()]
            for dep in local_dep.get_local_dependencies():
                local_projects[dep] = self.repo.projects[dep]
                if dep not in _inspected:
                    _need_to_inspect.add(dep)
                else:
                    _inspected.add(dep)
        # Gather local dependencies to override
        return {
            name: Dependency.parse_obj({"version": "*"})
            for name, project in local_projects.items()
        }

    def get_build_dependencies(
        self,
        include_local: bool = True,
        include_python: bool = True,
        lock_versions: bool = True,
    ) -> Tuple[Dict[str, Dependency], Dict[str, List[str]], Dict[str, Group]]:
        """Return dependencies, extras and groups"""
        dependencies: Dict[str, Dependency] = {}
        groups: Dict[str, Group] = {}
        extras: Dict[str, List[str]] = {}
        # Fetch constraints
        constraints: Dict[str, str]
        if self.repo is None:
            constraints = defaultdict(lambda: "*")
        else:
            constraints = self.repo.get_packages_constraints()
        # Iterate over dependencies and replace version
        for dep in self.spec.dependencies:
            if isinstance(dep, str):
                if lock_versions:
                    locked_version = self.get_locked_version(dep)
                else:
                    locked_version = constraints.get(dep, "*")
                dependencies[dep] = Dependency(version=locked_version)
            else:
                for key, value in dep.items():
                    if lock_versions:
                        locked_version = self.get_locked_version(key)
                    else:
                        locked_version = constraints.get(key, "*")
                    dependencies[key] = Dependency.parse_obj(
                        {
                            **value.dict(exclude_unset=True, by_alias=True),
                            "version": locked_version,
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
                    if lock_versions:
                        locked_version = self.get_locked_version(dep)
                    else:
                        locked_version = constraints.get(dep, "*")
                    # Add dependency to group
                    groups[group_name].dependencies[dep] = Dependency(
                        version=locked_version
                    )
                    # Add dependency to extra
                    if dep not in extras[group_name]:
                        extras[group_name].append(dep)
                    # Add dependency to optional dependencies
                    if dep not in dependencies:
                        dependencies[dep] = Dependency.parse_obj(
                            {
                                "version": locked_version,
                                "optional": True,
                            }
                        )
                else:
                    for key, value in dep.items():
                        if lock_versions:
                            locked_version = self.get_locked_version(key)
                        else:
                            locked_version = constraints.get(key, "*")
                        # Add dependency to group
                        groups[group_name].dependencies[key] = Dependency.parse_obj(
                            {
                                **value.dict(exclude_unset=True, by_alias=True),
                                "version": locked_version,
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
                                    "version": locked_version,
                                    "optional": True,
                                }
                            )
        # Make sure python dependency is set
        if include_python:
            if "python" not in dependencies:
                if self.repo:
                    python_dep = self.repo.get_dependency("python")
                    if python_dep:
                        dependencies["python"] = python_dep.copy()
        else:
            dependencies.pop("python", None)
        # Remove local deps
        if not include_local:
            for dep in self.get_local_dependencies_names():
                dependencies.pop(dep)
        # Return values
        return dependencies, extras, groups

    def get_locked_version(self, package: str) -> str:
        if self.repo:
            return self.repo.get_locked_version(package)
        else:
            return "*"

    def get_pyproject_spec(
        self,
        lock_versions: bool = True,
        build_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
    ) -> PyProjectSpec:
        """Create content of pyproject.toml file according to project.yaml"""
        dependencies, extras, groups = self.get_build_dependencies(
            lock_versions=lock_versions
        )
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
        lock_versions: bool = True,
        build_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
    ) -> KPyProject:
        """Write auto-generated pyproject.toml file.

        If path argument is not specified, file is generated in the project directory by default.
        """
        spec = self.get_pyproject_spec(
            lock_versions=lock_versions, build_system=build_system
        )
        pyproject_path = Path(path) if path else self.pyproject_path
        content = spec.dict()
        # Create an inline table to have more readable pyprojects
        if spec.tool.poetry.dependencies:
            content["tool"]["poetry"][
                "dependencies"
            ] = KPyProject._create_inline_tables(
                content["tool"]["poetry"]["dependencies"]
            )
        # Ensure python dependency is a string
        if "python" in content["tool"]["poetry"]["dependencies"]:
            content["tool"]["poetry"]["dependencies"]["python"] = content["tool"][
                "poetry"
            ]["dependencies"]["python"]["version"]
        # Write pyproject.toml as file
        write_toml(content, pyproject_path)
        try:
            # Parse pyproject we just wrote so that we're sure it is valid
            pyproject = KPyProject(pyproject_path, repo=self.repo)
        except ValidationError as err:
            logger.error(
                "Failed to validate pyproject",
                exc_info=err,
                path=pyproject_path.as_posix(),
            )
            raise
        return pyproject

    def remove_pyproject(self, pyproject_path: Union[str, Path, None] = None) -> None:
        """Remove auto-generated poetry files"""
        pyproject_path = Path(pyproject_path) if pyproject_path else self.pyproject_path
        pyproject_path.unlink(missing_ok=True)
        lock_path = pyproject_path.parent / "poetry.lock"
        lock_path.unlink(missing_ok=True)

    @contextmanager
    def temporary_pyproject(
        self,
        path: Union[str, Path, None] = None,
        lock_versions: bool = True,
        build_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
        clean: bool = True,
    ) -> Iterator[KPyProject]:
        """A context manager which ensures pyproject.toml is written to disk within context and removed out of context"""
        pyproject = self.write_pyproject(
            path, lock_versions=lock_versions, build_system=build_system
        )
        try:
            yield pyproject
        finally:
            if clean:
                self.remove_pyproject()

    async def build(
        self,
        env: Optional[Mapping[str, Any]] = None,
        build_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
        lock_versions: bool = True,
        clear_dist: bool = True,
        clean: bool = True,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        recurse: bool = True,
        **kwargs: Any,
    ) -> Command:
        if recurse and self.repo:
            async with create_task_group() as tg:
                for name in self.get_local_dependencies_names():
                    tg.start_soon(
                        partial(
                            self.repo.projects[name].build,
                            env=env,
                            quiet=quiet,
                            build_system=build_system,
                            lock_versions=lock_versions,
                            recurse=False,
                        )
                    )
        if clear_dist:
            shutil.rmtree(self.root / "dist", ignore_errors=True)
        with self.temporary_pyproject(
            self.pyproject_path,
            lock_versions=lock_versions,
            build_system=build_system,
            clean=clean,
        ) as pyproject:
            return await pyproject.poetry_build(
                env=env,
                quiet=quiet,
                raise_on_error=raise_on_error,
                timeout=timeout,
                deadline=deadline,
                **kwargs,
            )

    async def install(
        self,
        exclude_groups: Union[Iterable[str], str, None] = None,
        include_groups: Union[Iterable[str], str, None] = None,
        only_groups: Union[Iterable[str], str, None] = None,
        default: bool = False,
        lock_versions: bool = True,
        force: bool = False,
        build_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
        clean: bool = True,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Optional[Command]:
        if not self.repo:
            raise NotImplementedError(
                "PEP 660 install is not supported without parent repo"
            )
        if self.is_already_installed():
            if not force:
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
        logger.debug(
            f"Installing {self.name}",
            version=self.version,
            package=target,
        )
        with self.temporary_pyproject(
            self.pyproject_path,
            clean=clean,
            lock_versions=lock_versions,
            build_system=build_system,
        ):
            return await self.repo.pip_install(
                "-e",
                target,
                quiet=quiet,
                raise_on_error=raise_on_error,
                timeout=timeout,
                deadline=deadline,
                **kwargs,
            )

    async def add_dependency(
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
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Dict[str, Union[str, Dependency]]:
        if group:
            repo_group = self.name + "--" + group
        else:
            repo_group = self.name
        if self.repo:
            group_before = self.repo.spec.tool.poetry.group.get(repo_group, Group())
            await self.repo.poetry_add(
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
                quiet=quiet,
                raise_on_error=raise_on_error,
                timeout=timeout,
                deadline=deadline,
                **kwargs,
            )
            # Refresh repo metadata
            self.repo.refresh()
            group_after = self.repo.spec.tool.poetry.group[repo_group]
            # Get package diff
            new_packages = set(group_after.dependencies).difference(
                group_before.dependencies
            )
            # Add new packages to project.yml raw spec
            if group is None:
                for package in new_packages:
                    self._raw["dependencies"].append(package)
            else:
                if group not in self._raw["extras"]:
                    self._raw["extras"][group] = []
                for package in new_packages:
                    self._raw["extras"][group].append(package)
            # Write spec
            self.write(self.root / "project.yml")
            self.refresh()
            # Return new packages
            return {name: group_after.dependencies[name] for name in new_packages}

        else:
            raise NotImplementedError(
                "It's not possible to add dependencies to projet without parent repo"
            )

    async def remove_dependency(
        self,
        package: str,
        group: Optional[str] = None,
        dry_run: bool = False,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Union[str, Dependency]]]:
        if group:
            repo_group = self.name + "--" + group
        else:
            repo_group = self.name
        if self.repo:
            group_before = self.repo.spec.tool.poetry.group.get(repo_group, Group())
            try:
                await self.repo.poetry_remove(
                    package,
                    group=repo_group,
                    dry_run=dry_run,
                    quiet=quiet,
                    raise_on_error=raise_on_error,
                    timeout=timeout,
                    deadline=deadline,
                    **kwargs,
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
            # Remove package from project.yml
            if group is None:
                self._raw["dependencies"] = [
                    dep
                    for dep in self._raw["dependencies"]
                    if dep not in removed_packages
                ]
            else:
                if group in self._raw["extras"]:
                    self._raw["extras"][group] = [
                        dep
                        for dep in self._raw["dependencies"][group]
                        if dep not in removed_packages
                    ]
            # Write and refresh
            if removed_packages:
                self.write(self.root / "project.yml")
                self.refresh()
            # Return removed packages
            return {name: group_before.dependencies[name] for name in removed_packages}

        else:
            raise NotImplementedError(
                "It's not possible to remove dependencies to projet without parent repo"
            )

    async def build_docker(
        self,
        tag: Optional[str] = None,
        load: bool = False,
        push: bool = False,
        build_args: Optional[Dict[str, str]] = None,
        platforms: Optional[List[str]] = None,
        output_dir: Union[str, Path, None] = None,
        build_dist: bool = True,
        lock_versions: bool = True,
        build_dist_env: Optional[Dict[str, str]] = None,
        build_dist_system: BuildSystem = DEFAULT_BUILD_SYSTEM,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Build docker image for the projcet according to the project spec."""
        # Gather deadline
        deadline = get_deadline(timeout, deadline)
        kwargs["rc"] = kwargs.get("rc", 0 if raise_on_error else None)
        # Gather git infos
        git_infos = await self.get_git_infos()
        # Gather tag
        if tag is None:
            # Check if it's a release
            if git_infos.tag:
                tag = git_infos.tag
            # Use branch and commit if available
            elif git_infos.branch and git_infos.commit:
                tag = "-".join(
                    [git_infos.branch.split("/")[-1].lower(), git_infos.commit]
                )
            # Use commit only
            elif git_infos.commit:
                tag = git_infos.commit
            else:
                tag = "latest"
        spec = self.spec.docker
        if not spec:
            raise ValueError("No docker spec found for project")
        if not self.repo:
            raise ValueError("Cannot build docker images without parent repo")
        template = spec.template or "library"
        template_file = "Dockerfile." + template
        template_path = self.repo.root / ".repo/templates/dockerfiles" / template_file
        try:
            shutil.copy2(template_path, self.root / "Dockerfile")
            cmd = Command(
                "docker buildx build", deadline=deadline, quiet=quiet, **kwargs
            )
            _build_args = spec.build_args.copy() if spec.build_args else {}
            if build_args:
                _build_args.update(build_args)
            build_args = _build_args.copy()
            if spec.base_image and "BASE_IMAGE" not in build_args:
                if ":" not in spec.base_image:
                    base_image = spec.base_image + ":" + tag
                else:
                    base_image = spec.base_image
                build_args["BASE_IMAGE"] = base_image
            build_args["PACKAGE_NAME"] = self.name
            build_args["PACKAGE_VERSION"] = self.version
            if git_infos.commit:
                build_args["GIT_COMMIT"] = git_infos.commit
            if git_infos.branch:
                build_args["GIT_BRANCH"] = git_infos.branch
            if git_infos.tag:
                build_args["GIT_TAG"] = git_infos.tag
            # Add build args
            logger.warning("Using build args", build_args=build_args)
            for key, value in build_args.items():
                cmd.add_option("--build-arg", "=".join([key, value]), escape=True)
            # Add labels
            cmd.add_repeat_option("--label", spec.labels)
            cmd.add_repeat_option(
                "--label",
                [
                    f"quara.package.version={self.version}",
                    f"quara.package.name={self.name}",
                ],
            )
            # Add git infos as labels
            if git_infos.tag:
                cmd.add_option("--label", f"git.tag.name={git_infos.tag}")
            if git_infos.branch:
                cmd.add_option("--label", f"git.branch.name={git_infos.branch}")
            if git_infos.commit:
                cmd.add_option("--label", f"git.commit={git_infos.commit}")
            # Add tag
            cmd.add_option("--tag", ":".join([spec.image, tag]))
            if load:
                cmd.add_option("--load")
            if push:
                cmd.add_option("--push")
            if output_dir is not None:
                cmd.add_option(
                    "--output",
                    "type=local,dest=" + Path(self.root, output_dir).as_posix(),
                )
            cmd.add_option(
                "--metadata-file",
                Path(
                    self.root,
                    "dist",
                    "-".join([self.name, self.version]) + ".docker-metadata",
                ).as_posix(),
            )
            if platforms:
                platform = list(set(spec.platforms).union(platforms))
            else:
                platform = spec.platforms
            if platform:
                cmd.add_repeat_option("--platform", platform)
            cmd.add_argument(
                Path(self.root, spec.context).resolve(True).as_posix()
                if spec.context
                else self.root.as_posix()
            )
            if build_dist:
                # Make sure sources are built before actually running the command
                await self.build(
                    env=build_dist_env,
                    build_system=build_dist_system,
                    lock_versions=lock_versions,
                    quiet=True,
                    deadline=deadline,
                    **kwargs,
                )
                # Copy dist into project dist
                dist_root = self.root / "dist"
                dist_root.mkdir(exist_ok=True, parents=False)
                for dep in self.repo.list_projects(include=[self.name]):
                    if dep.name == self.name:
                        continue
                    for filepath in Path(dep.root, "dist").glob("*.whl"):
                        shutil.copy2(filepath, dist_root)
            logger.warning("Invoking docker command", command=cmd.cmd)
            # Run docker build command
            return await cmd.run()
        finally:
            Path(self.root, "Dockerfile").unlink(missing_ok=True)

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
