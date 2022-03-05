from __future__ import annotations

import shutil
import sys
from collections import defaultdict
from graphlib import TopologicalSorter
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Set,
    Type,
    Union,
)

from anyio import create_task_group

from kapla.specs.pyproject import Dependency, Group
from kapla.specs.repo import ProjectDependencies, RepoSpec

from .cmd import Command, echo, get_deadline
from .errors import KProjectNotFoundError
from .finder import find_dirs, find_files, find_files_using_gitignore, lookup_file
from .io import load_toml
from .kproject import KProject
from .logger import logger
from .pyproject import BaseKPyProject


def filter_project(
    project_name: str,
    include: Optional[Iterable[str]] = None,
    exclude: Optional[Iterable[str]] = None,
) -> bool:
    if not (include or exclude):
        return True
    if include and project_name not in include:
        return False
    if exclude and project_name in exclude:
        return False
    return True


class BaseKRepo(BaseKPyProject, spec=RepoSpec):
    __SPEC__: Type[RepoSpec]  # type: ignore[assignment]
    spec: RepoSpec  # type: ignore[assignment]


class KRepo(BaseKRepo):
    def __init__(self, filepath: Union[str, Path]) -> None:
        super().__init__(filepath)
        self._projects_ws_mapping: Dict[str, str] = {}
        self._projects = {project.name: project for project in self.find_projects()}
        self._tree = self.get_projects_tree()
        self._stack = [
            self.projects[project]
            for project in TopologicalSorter(self._tree).static_order()
        ]
        self._async_stack = self.get_projects_async_stack()
        self._lock = self.get_packages_lock()

    @property
    def _workspaces(self) -> Dict[str, List[str]]:
        return self.spec.tool.repo.workspaces or {"default": ["./"]}

    @property
    def workspaces(self) -> Dict[str, List[Path]]:
        return {
            name: [Path(self.root, path).resolve(True) for path in directories]
            for name, directories in self._workspaces.items()
        }

    @property
    def projects(self) -> Dict[str, KProject]:
        """Return a dictionnary of project names and projects"""
        return self._projects

    @property
    def projects_tree(self) -> Dict[str, List[str]]:
        return self._tree

    @property
    def projects_sequence(self) -> List[KProject]:
        return self._stack

    @property
    def projects_async_sequences(self) -> List[List[KProject]]:
        return self._async_stack

    @property
    def projects_names(self) -> List[str]:
        """Return a list of project names"""
        return list(self._projects)

    @property
    def packages_lock(self) -> Dict[str, Any]:
        """FIXME: Add model for lockfile to specs"""
        return self._lock

    def refresh(self) -> None:
        super().refresh()
        self._projects = self.get_projects()
        self._tree = self.get_projects_tree()
        self._stack = [
            self.projects[project]
            for project in TopologicalSorter(self._tree).static_order()
        ]
        self._async_stack = self.get_projects_async_stack()
        self._lock = self.get_packages_lock()

    def find_current_project(self) -> KProject:
        """Find project from current directory by default, and iterate recursively on parent directotries"""
        projectfile = lookup_file(("project.yml", "project.yaml"), start=Path.cwd())
        if projectfile:
            return KProject(projectfile, repo=self)
        raise KProjectNotFoundError(
            "Cannot find any project.yml or project.yaml file in current directory or parent directories."
        )

    def filter_project(
        self,
        name: str,
        include: Optional[Union[str, Iterable[str]]] = None,
        exclude: Optional[Union[str, Iterable[str]]] = None,
    ) -> bool:
        if include:
            if name not in include:
                return False
        if exclude:
            if name in exclude:
                return False
        return True

    def find_projects(
        self,
        workspaces: Optional[Iterable[str]] = None,
        include: Optional[Union[str, Iterable[str]]] = None,
        exclude: Optional[Union[str, Iterable[str]]] = None,
    ) -> Iterator[KProject]:
        all_workspaces = self.workspaces
        workspaces = workspaces or list(self.workspaces)
        for name in workspaces:
            for workspace in all_workspaces[name]:
                for filepath in find_files_using_gitignore(
                    ("project.yml", "project.yaml"),
                    root=workspace,
                ):
                    project = KProject(filepath, repo=self, workspace=name)
                    if self.filter_project(
                        project.name, include=include, exclude=exclude
                    ):
                        yield project

    def filter_projects(
        self,
        workspaces: Optional[Iterable[str]] = None,
        include: Optional[Union[str, Iterable[str]]] = None,
        exclude: Optional[Union[str, Iterable[str]]] = None,
    ) -> Iterator[KProject]:
        for project_name, project in self.projects.items():
            ws = project.workspace
            if self.filter_project(project_name, include=include, exclude=exclude):
                if workspaces:
                    if ws and ws in workspaces:
                        yield project
                else:
                    yield project

    def list_projects(
        self,
        workspaces: Optional[Iterable[str]] = None,
        include: Optional[Union[str, Iterable[str]]] = None,
        exclude: Optional[Union[str, Iterable[str]]] = None,
    ) -> List[KProject]:
        """Get a list of all projects found in monorepo.

        It's possible to filter using workspaces or names
        """
        return [
            project
            for project in self.filter_projects(
                workspaces=workspaces, include=include, exclude=exclude
            )
        ]

    def get_projects(
        self,
        workspaces: Optional[Iterable[str]] = None,
        include: Optional[Union[str, Iterable[str]]] = None,
        exclude: Optional[Union[str, Iterable[str]]] = None,
    ) -> Dict[str, KProject]:
        """Get a dictionnary holding project names and projects found in monorepo"""
        return {
            project.name: project
            for project in self.filter_projects(
                workspaces=workspaces, include=include, exclude=exclude
            )
        }

    def get_projects_stack(
        self,
        workspaces: Optional[Iterable[str]] = None,
        include: Optional[Iterable[str]] = None,
        exclude: Optional[Iterable[str]] = None,
    ) -> Iterator[KProject]:
        """Get project stack according to dependency order"""
        must_install: Set[str] = set(include) if include else set(self.projects)
        for project in self.filter_projects(
            workspaces=workspaces, include=include, exclude=exclude
        ):
            must_install.update(project.get_local_dependencies_names())
        # Use list to get a copy of the set and avoid mutating the same object we're iterating upon
        for project_name in list(must_install):
            must_install.update(
                self.projects[project_name].get_local_dependencies_names()
            )
        # Use must_install to consider projects to install but still allow exclude
        for project in self.projects_sequence:
            if filter_project(project.name, must_install, exclude):
                yield project

    def get_projects_async_stack(
        self,
        workspaces: Optional[Iterable[str]] = None,
        include: Optional[Iterable[str]] = None,
        exclude: Optional[Iterable[str]] = None,
    ) -> List[List[KProject]]:
        # Create an empty list of sequences
        async_sequences: List[List[KProject]] = list()
        # Iterate over projects sequence
        for project in self.get_projects_stack(
            workspaces=workspaces, include=include, exclude=exclude
        ):
            try:
                current_sequence = [project.name for project in async_sequences[-1]]
            except IndexError:
                async_sequences.append(list())
            # Create new sequence if any project is required as dependency
            if any(
                name in current_sequence for name in self.projects_tree[project.name]
            ):
                async_sequences.append([project])
            # Else append to sequence
            else:
                async_sequences[-1].append(project)
        return async_sequences

    def get_projects_tree(self) -> Dict[str, List[str]]:
        return {
            name: project.get_local_dependencies_names()
            for name, project in self.projects.items()
        }

    def get_all_projects_dependencies(
        self,
        workspaces: Optional[Iterable[str]] = None,
        include: Optional[Iterable[str]] = None,
        exclude: Optional[Iterable[str]] = None,
        editable: bool = False,
    ) -> Dict[str, ProjectDependencies]:
        """Get all informations related to projects dependencies"""
        dependencies: Dict[str, ProjectDependencies] = {}
        for project in self.get_projects_stack(
            workspaces=workspaces, include=include, exclude=exclude
        ):
            if editable:
                (
                    project_deps,
                    project_extras,
                    project_groups,
                ) = project.get_install_dependencies()
            else:
                (
                    project_deps,
                    project_extras,
                    project_groups,
                ) = project.get_build_dependencies()
            repo_deps = self.get_group_dependencies(project.name)
            project_python = project_deps.pop("python", None)
            repo_python = repo_deps.pop("python", None)
            repo_groups = {
                name: group
                for name, group in self.spec.tool.poetry.group.items()
                if name.startswith(project.name + "--")
            }
            dependencies[project.name] = ProjectDependencies(
                repo_dependencies=repo_deps,
                repo_groups=repo_groups,
                dependencies=project_deps,
                groups=project_groups,
                python=project_python or repo_python,
            )
        return dependencies

    def get_missing_projects_dependencies(self) -> Dict[str, Dict[str, Dependency]]:

        missing_deps: Dict[str, Dict[str, Dependency]] = defaultdict(dict)

        for project_name in self.projects:

            deps_summary = self.get_project_dependencies(project_name)

            for group_name, group_deps in deps_summary.groups.items():
                repo_group_name = "--".join([project_name, group_name])
                repo_group_deps = deps_summary.repo_groups.get(repo_group_name, Group())
                for dep_name in group_deps.dependencies:
                    if dep_name in self.projects:
                        continue
                    if dep_name not in repo_group_deps.dependencies:
                        # We need to add the dependency to the group !
                        # But it would be better to add all dependencies of same group at the same time
                        # It will avoid resolving poetry lock too many times
                        group_dep = group_deps.dependencies[dep_name]
                        missing_deps[repo_group_name][dep_name] = (
                            group_dep
                            if isinstance(group_dep, Dependency)
                            else Dependency(version=group_dep)
                        )

            for dep_name, dep_spec in deps_summary.dependencies.items():
                if dep_name in self.projects:
                    continue
                repo_dependencies = deps_summary.repo_dependencies
                if dep_name not in repo_dependencies:
                    for group in deps_summary.repo_groups.values():
                        if dep_name in group.dependencies:
                            break
                    else:
                        missing_deps[project_name][dep_name] = dep_spec
        return missing_deps

    def get_project_dependencies(self, name: str) -> ProjectDependencies:
        deps = self.get_all_projects_dependencies(include=[name])
        return deps[name]

    def get_packages_lock(self) -> Dict[str, Any]:
        lock_path = self.root / "poetry.lock"
        if lock_path.exists():
            lockfile_content = load_toml(lock_path)
            lock = {package["name"]: package for package in lockfile_content["package"]}  # type: ignore[union-attr, index]
        else:
            lock = {}
        lock.update(
            {
                name: {"version": project.spec.version}
                for name, project in self.get_projects().items()
            }
        )
        return lock

    def clean_pyproject_files(self) -> None:
        """Clean all auto-generated poetry files"""
        for project in self.projects_sequence:
            project.clean_poetry_files()

    def clean(self, remove_venv: bool = False) -> None:
        """Remove well-known non versioned files"""
        to_remove = [expr for expr in self.gitignore if expr not in (".venv", ".venv/")]
        # Remove venv
        if remove_venv:
            shutil.rmtree(Path(self.root, ".venv"), ignore_errors=True)
        # clean monorepo
        for path in find_dirs(to_remove, self.root):
            shutil.rmtree(path, ignore_errors=True)
        # Remove files
        for path in find_files(to_remove, self.root):
            path.unlink(missing_ok=True)

        # Clean pyproject files
        self.clean_pyproject_files()

    async def add_missing_dependencies(self) -> None:
        missing_deps = self.get_missing_projects_dependencies()
        for group, deps in missing_deps.items():
            for dep_name, dep in deps.items():
                if dep.version is None or dep.version == "*":
                    package = dep_name
                else:
                    package = f"{dep_name}@{dep.version}"
                await self.add(
                    package,
                    group=group,
                    editable=True if dep.develop else False,
                    extras=dep.extras,
                    optional=True if dep.optional else False,
                    python=dep.python,
                    lock=True,
                )

    async def install_poetry_projects(
        self,
        include_projects: List[str],
        exclude_projects: Optional[Iterable[str]] = None,
        include_groups: Optional[Iterable[str]] = None,
        exclude_groups: Optional[Iterable[str]] = None,
        only_groups: Optional[Iterable[str]] = None,
        default: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        clean: bool = True,
        update_venv: bool = False,
    ) -> List[Command]:
        if update_venv:
            await self.venv()
        else:
            await self.ensure_venv()
        # Make sure to add missing dependencies
        try:
            # Compute deadline to use to enforce timeouts
            deadline = get_deadline(timeout, deadline)
            # Perform first round of install
            await self.install(
                include_groups=include_projects,
                exclude_groups=exclude_projects,
                raise_on_error=True,
                deadline=deadline,
                echo_stdout=echo,
            )
            # List of all results
            all_results: List[Command] = []
            # Denote first group of packages
            first = True
            stack = list(
                self.get_projects_async_stack(
                    include=include_projects, exclude=exclude_projects
                )
            )
            # Iterate over concurrent sequences
            for projects in stack:
                if first:
                    # Create a variable which will hold results for this round of projects
                    results: List[Command] = []
                    # Create a task group to coordinate installs
                    async with create_task_group() as tg:
                        # Iterate over each project
                        for project in projects:
                            # Define function to perform install
                            async def install_project(project: KProject) -> None:
                                nonlocal results
                                print(f"Starting install for {project.name}")
                                cmd = await project.install_pep_660(
                                    exclude_groups=exclude_groups,
                                    include_groups=include_groups,
                                    only_groups=only_groups,
                                    default=default,
                                    deadline=deadline,
                                    raise_on_error=False,
                                    clean=False,
                                )
                                if cmd:
                                    results.append(cmd)
                                if cmd is None or cmd.code == 0:
                                    print(f"Sucessfully installed {project.name}")
                                else:
                                    print(f"Failed  to install {project.name}")
                                    print("Captured stdout:")
                                    print(cmd.stdout)
                                    print("Captured stderr:", file=sys.stderr)
                                    print(cmd.stderr, file=sys.stderr)

                            if first:
                                # Kick off install
                                tg.start_soon(
                                    install_project,
                                    project,
                                    name=f"install-{project.name}",
                                )
                    # Extend all results
                    all_results.extend(results)
                    # We can no longer run things in // 😓
                    first = False
                else:
                    for project in projects:
                        print(f"Starting install for {project.name}")
                        cmd = await project.install(
                            exclude_groups=exclude_groups,
                            include_groups=include_groups,
                            only_groups=only_groups,
                            default=default,
                            deadline=deadline,
                            raise_on_error=False,
                            clean=False,
                        )
                        if cmd:
                            all_results.append(cmd)
            # Return all results
            return all_results
        # Always clean files if required
        finally:
            if clean:
                self.clean_pyproject_files()

    async def install_editable_projects(
        self,
        include_projects: Optional[List[str]] = None,
        exclude_projects: Optional[Iterable[str]] = None,
        include_groups: Optional[Iterable[str]] = None,
        exclude_groups: Optional[Iterable[str]] = None,
        only_groups: Optional[Iterable[str]] = None,
        no_root: bool = False,
        default: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        clean: bool = True,
        update_venv: bool = False,
    ) -> List[Command]:
        if update_venv:
            await self.venv()
        else:
            await self.ensure_venv()
        try:
            # Compute deadline to use to enforce timeouts
            deadline = get_deadline(timeout, deadline)

            # Perform first round of install
            await self.install(
                include_groups=include_projects,
                exclude_groups=exclude_projects,
                raise_on_error=True,
                deadline=deadline,
                no_root=no_root,
                echo_stdout=echo,
            )
            # List of all results
            all_results: List[Command] = []
            async_stack = self.get_projects_async_stack(
                include=include_projects, exclude=exclude_projects
            )
            # Iterate over concurrent sequences
            for projects in async_stack:
                # Create a variable which will hold results for this round of projects
                results: List[Command] = []
                # Create a task group to coordinate installs
                async with create_task_group() as tg:
                    # Iterate over each project
                    for project in projects:
                        print(f"Starting install for {project.name}")

                        # Define function to perform install
                        async def install_project(project: KProject) -> None:
                            nonlocal results
                            cmd = await project.install_pep_660(
                                exclude_groups=exclude_groups,
                                include_groups=include_groups,
                                only_groups=only_groups,
                                default=default,
                                deadline=deadline,
                                raise_on_error=True,
                                clean=False,
                            )
                            if cmd:
                                results.append(cmd)

                        # Kick off install
                        tg.start_soon(
                            install_project, project, name=f"install-{project.name}"
                        )
                # Extend all results
                all_results.extend(results)
            # Return all results
            return all_results
        # Always clean files if required
        finally:
            if clean:
                self.clean_pyproject_files()

    async def build_projects(
        self,
        include_projects: List[str],
        exclude_projects: Optional[Iterable[str]] = None,
        env: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        clean: bool = True,
    ) -> List[Command]:
        # Compute deadline to use to enforce timeouts
        deadline = get_deadline(timeout, deadline)
        # Create a variable which will hold results for this round of projects
        results: List[Command] = []
        # Create a task group to coordinate installs
        async with create_task_group() as tg:
            # Iterate over synchronous sequences
            for project in self.get_projects_stack(
                include=include_projects, exclude=exclude_projects
            ):
                # Define function to perform install
                async def build_project(project: KProject) -> None:
                    nonlocal results
                    try:
                        cmd = await project.build(
                            env=env,
                            deadline=deadline,
                            raise_on_error=False,
                            clean=clean,
                        )
                    except Exception as err:
                        logger.error(f"Failed to build {project.name}", exc_info=err)
                        return
                    results.append(cmd)
                    if cmd.code == 0:
                        print(f"Sucessfully built {project.name}")
                    else:
                        print(f"Failed to build {project.name}")

                # Kick off install
                tg.start_soon(build_project, project, name=f"build-{project.name}")
        # Return all results
        return results
