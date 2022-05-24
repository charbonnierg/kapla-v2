from __future__ import annotations

import shutil
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
    Tuple,
    Type,
    Union,
)

from anyio import CapacityLimiter, create_task_group

from kapla.specs.lock import LockFile
from kapla.specs.pyproject import Dependency, Group
from kapla.specs.repo import KRepoSpec, ProjectDependencies

from ..core.cmd import Command
from ..core.errors import KProjectNotFoundError
from ..core.finder import find_dirs, find_files, find_files_using_gitignore, lookup_file
from ..core.io import read_toml
from ..core.logger import logger
from ..core.timeout import get_deadline
from .kproject import KProject
from .pyproject import PyProject


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


class BaseKRepo(PyProject, spec=KRepoSpec):
    __SPEC__: Type[KRepoSpec]
    spec: KRepoSpec


class KRepo(BaseKRepo):
    def __init__(self, filepath: Union[str, Path]) -> None:
        super().__init__(filepath)
        self._workspaces = self.spec.tool.repo.workspaces or {"default": ["./"]}
        self._projects = {project.name: project for project in self.discover_projects()}
        self._projects_local_dependencies = self.get_projects_local_dependencies()
        self._sequence = [
            self.projects[project]
            for project in TopologicalSorter(
                self._projects_local_dependencies
            ).static_order()
        ]
        self._stack = self.get_projects_stack()
        self._lock = self.get_packages_lock()

    @property
    def workspaces(self) -> Dict[str, List[Path]]:
        """Dictionary of workspaces. If no workspaces are specified, current directory is used as default workspace.

        Each dictionnary value holds a list of directory path.
        """
        return {
            name: [Path(self.root, path).resolve(True) for path in directories]
            for name, directories in self._workspaces.items()
        }

    @property
    def projects(self) -> Dict[str, KProject]:
        """Return a dictionnary of project names and projects"""
        return self._projects

    @property
    def projects_names(self) -> List[str]:
        """Return a list of project names to consume in order"""
        return [project.name for project in self._sequence]

    @property
    def packages_lock(self) -> LockFile:
        """FIXME: Add model for lockfile to specs"""
        return self._lock

    def refresh(self) -> None:
        super().refresh()
        self._workspaces = self.spec.tool.repo.workspaces or {"default": ["./"]}
        self._projects = {project.name: project for project in self.discover_projects()}
        self._projects_local_dependencies = self.get_projects_local_dependencies()
        self._sequence = [
            self.projects[project]
            for project in TopologicalSorter(
                self._projects_local_dependencies
            ).static_order()
        ]
        self._stack = self.get_projects_stack()
        self._lock = self.get_packages_lock()

    def find_current_project(self) -> KProject:
        """Find project from current directory by default, and iterate recursively on parent directotries"""
        projectfile = lookup_file(("project.yml", "project.yaml"), start=Path.cwd())
        if projectfile:
            return KProject(projectfile, repo=self)
        raise KProjectNotFoundError(
            "Cannot find any project.yml or project.yaml file in current directory or parent directories."
        )

    def filter_project_name(
        self,
        name: str,
        include: Optional[Union[str, Iterable[str]]] = None,
        exclude: Optional[Union[str, Iterable[str]]] = None,
    ) -> bool:
        """Filter a project name according to include and exclude iterables"""
        if include:
            if isinstance(include, str):
                return name == include
            if name not in include:
                return False
        if exclude:
            if isinstance(exclude, str):
                return name != exclude
            if name in exclude:
                return False
        return True

    def discover_projects(
        self,
        workspaces: Optional[Iterable[str]] = None,
        include: Optional[Union[str, Iterable[str]]] = None,
        exclude: Optional[Union[str, Iterable[str]]] = None,
    ) -> Iterator[KProject]:
        # Get a dict holding all workspaces and their directories
        all_workspaces = self.workspaces
        # Get a list of workspaces names
        all_workspaces_names = workspaces or list(self.workspaces)
        # Iterate over each workspace name
        for name in all_workspaces_names:
            # Iterate over each directory in workspace
            for workspace_directory in all_workspaces[name]:
                # Find files named "project.yml" or "project.yaml" starting from the workspace
                for filepath in find_files_using_gitignore(
                    ("project.yml", "project.yaml"),
                    root=workspace_directory,
                ):
                    # Create a new instance of KProject
                    project = KProject(filepath, repo=self, workspace=name)
                    # Check if project should be filtered
                    if self.filter_project_name(
                        project.name, include=include, exclude=exclude
                    ):
                        yield project

    def filter_projects(
        self,
        workspaces: Optional[Iterable[str]] = None,
        include: Optional[Union[str, Iterable[str]]] = None,
        exclude: Optional[Union[str, Iterable[str]]] = None,
    ) -> Iterator[KProject]:
        if isinstance(include, str):
            include = [include]
        if isinstance(exclude, str):
            exclude = [exclude]
        # Consider projects which MUST be included
        must_install: Set[str] = set(include) if include else set()
        if include:
            # Iterate over included projects
            for project_name in include:
                # Local dependencies of local projects must be included
                try:
                    must_install.update(self._projects_local_dependencies[project_name])
                except KeyError:
                    continue
            # Use list to get a copy of the set and avoid mutating the same object we're iterating upon
            for project_name in list(must_install):
                # As well as local dependencies of local dependencies
                try:
                    must_install.update(
                        self.projects[project_name].get_local_dependencies_names()
                    )
                except KeyError:
                    continue
        # Iterate over project names and instances
        for project in self._sequence:
            # Fetch the project workspace
            ws = project.workspace
            # Filter project using include/exclude iterables
            if self.filter_project_name(
                project.name, include=must_install, exclude=exclude
            ):
                # Filter project a second time using workspace only if workspaces variable is defined
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
        return list(
            self.filter_projects(
                workspaces=workspaces, include=include, exclude=exclude
            )
        )

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
    ) -> List[List[KProject]]:
        # Create an empty list of sequences
        async_sequences: List[List[KProject]] = list()
        # Iterate over projects sequence
        for project in self.list_projects(
            workspaces=workspaces, include=include, exclude=exclude
        ):
            try:
                current_sequence = [project.name for project in async_sequences[-1]]
            except IndexError:
                # Always append first project
                async_sequences.append([project])
                continue
            # Create new sequence if any project is required as dependency
            if any(
                name in current_sequence
                for name in self._projects_local_dependencies[project.name]
            ):
                async_sequences.append([project])
            # Else append to sequence
            else:
                async_sequences[-1].append(project)
        return async_sequences

    def get_projects_local_dependencies(self) -> Dict[str, List[str]]:
        """Get local dependencies for each project"""
        return {
            name: project.get_local_dependencies_names()
            for name, project in self.projects.items()
        }

    def get_single_project_dependencies(
        self, name: str, lock_versions: bool = True
    ) -> ProjectDependencies:
        deps = self.get_projects_dependencies(
            include=[name], lock_versions=lock_versions
        )
        return deps[name]

    def get_projects_dependencies(
        self,
        workspaces: Optional[Iterable[str]] = None,
        include: Optional[Iterable[str]] = None,
        exclude: Optional[Iterable[str]] = None,
        lock_versions: bool = True,
    ) -> Dict[str, ProjectDependencies]:
        """Get all informations related to projects dependencies"""
        dependencies: Dict[str, ProjectDependencies] = {}
        for project in self.list_projects(
            workspaces=workspaces, include=include, exclude=exclude
        ):
            (
                project_deps,
                project_extras,
                project_groups,
            ) = project.get_build_dependencies(lock_versions=lock_versions)
            repo_deps = self.get_group_dependencies(project.name)
            project_python = project_deps.pop("python", None)
            repo_python = repo_deps.pop("python", None)
            repo_groups = {
                name: group
                for name, group in self.spec.tool.poetry.group.items()
                if name.startswith(project.name + "--")
            }
            python_version = project_python or repo_python
            dependencies[project.name] = ProjectDependencies(
                repo_dependencies=repo_deps,
                repo_groups=repo_groups,
                dependencies=project_deps,
                groups=project_groups,
                python=python_version,
            )
        return dependencies

    def get_projects_dependencies_missing(
        self,
    ) -> Tuple[Dict[str, Dict[str, Dependency]], Dict[str, List[str]]]:

        missing_deps: Dict[str, Dict[str, Dependency]] = defaultdict(dict)
        # Used like a set
        zombie_deps: Dict[str, Dict[str, None]] = defaultdict(dict)

        for project_name in self.projects:

            deps_summary = self.get_single_project_dependencies(project_name)

            # Iterate over groups
            for group_name, group_deps in deps_summary.groups.items():
                # Fetch group name
                repo_group_name = "--".join([project_name, group_name])
                # Fetch group
                repo_group_deps = deps_summary.repo_groups.get(repo_group_name, Group())
                # Check if there is a missing group dependency in pyproject.toml compared to project.yml
                for dep_name in group_deps.dependencies:
                    if dep_name in self.projects:
                        continue
                    if dep_name.lower() not in [
                        dep.lower() for dep in repo_group_deps.dependencies
                    ]:
                        # We need to add the dependency to the group !
                        group_dep = group_deps.dependencies[dep_name]
                        missing_deps[repo_group_name][dep_name] = (
                            group_dep
                            if isinstance(group_dep, Dependency)
                            else Dependency(version=group_dep)
                        )
                # Check if there is a dependency in the group which is not needed
                for dep in repo_group_deps.dependencies:
                    if dep.lower() not in [
                        dep_name.lower() for dep_name in group_deps.dependencies
                    ]:
                        logger.warning(
                            "Adding zombie dep", dep_name=dep, group=repo_group_name
                        )
                        # Append to zombie deps of visited group
                        zombie_deps[repo_group_name][dep] = None

            for dep, dep_spec in deps_summary.dependencies.items():

                if dep in self.projects:
                    continue

                repo_dependencies = deps_summary.repo_dependencies

                # Check if there is a missing dependency in pyproject.toml compared to project.yml
                if dep.lower() not in [
                    dep_name.lower() for dep_name in repo_dependencies
                ]:
                    for repo_group in deps_summary.repo_groups.values():
                        if dep.lower() in [
                            dep_name.lower() for dep_name in repo_group.dependencies
                        ]:
                            break
                    else:
                        logger.warning("Adding missing dep", dep_name=dep)
                        missing_deps[project_name][dep] = dep_spec

            # Check if there is a dep which is not present in any project
            for dep in deps_summary.repo_dependencies:
                # Try to find a usage of the dep
                if dep.lower() in [dep.lower() for dep in deps_summary.dependencies]:
                    break
                for project_group in deps_summary.groups.values():
                    if dep.lower() in [
                        dep_name.lower() for dep_name in project_group.dependencies
                    ]:
                        break
                    else:
                        continue
                else:
                    logger.warning("Removing zombie dep", dep_name=dep)
                    zombie_deps[project_name][dep] = None

        return missing_deps, {group: list(deps) for group, deps in zombie_deps.items()}

    def get_packages_lock(self) -> LockFile:
        """Get packages lock file as a pydantic model"""
        lock_path = self.root / "poetry.lock"
        if lock_path.exists():
            lockfile_content = read_toml(lock_path)
            locked_packages = {package["name"]: package for package in lockfile_content["package"]}  # type: ignore[union-attr, index]
            locked_metadata: Any = lockfile_content["metadata"]

        else:
            locked_packages = {}
            locked_metadata = None
        locked_packages.update(
            {
                name: {"name": name, "version": project.version}
                for name, project in self.get_projects().items()
            }
        )
        return LockFile(packages=locked_packages, metadata=locked_metadata)

    def get_packages_constraints(self) -> Dict[str, str]:
        return {
            dep_name: dep.version or "*"
            for group in self.get_all_group_dependencies().values()
            for dep_name, dep in group.items()
        }

    def get_locked_version(self, package: str) -> str:
        lpackage = package.lower()
        if lpackage in self.packages_lock.packages:
            return self.packages_lock.packages[lpackage].version or "*"
        return "*"

    async def add_missing_dependencies(self) -> None:
        missing_deps, _ = self.get_projects_dependencies_missing()
        for group, deps in missing_deps.items():
            packages: Set[str] = set()
            for dep_name, dep in deps.items():
                if dep.version is None or dep.version == "*":
                    packages.add(dep_name)
                else:
                    packages.add(f"{dep_name}@{dep.version}")
            if packages:
                await self.poetry_add(
                    *packages,
                    group=group,
                    editable=True if dep.develop else False,
                    extras=dep.extras,
                    optional=True if dep.optional else False,
                    python=dep.python,
                    lock=True,
                )

    async def remove_zombie_dependencies(self) -> None:
        _, zombie_deps = self.get_projects_dependencies_missing()
        for group, deps in zombie_deps.items():
            await self.poetry_remove(deps, group=group, raise_on_error=True)
        self.refresh()

    async def install_editable_projects(
        self,
        include_projects: Optional[List[str]] = None,
        exclude_projects: Optional[Iterable[str]] = None,
        include_groups: Optional[Iterable[str]] = None,
        exclude_groups: Optional[Iterable[str]] = None,
        only_groups: Optional[Iterable[str]] = None,
        lock_versions: bool = True,
        default: bool = False,
        no_root: bool = False,
        force: bool = False,
        pip_quiet: bool = True,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        clean: bool = True,
        update_venv: bool = False,
    ) -> List[Command]:
        if update_venv:
            await self.update_venv(raise_on_error=True)
        else:
            await self.ensure_venv(raise_on_error=True)
        # Create concurrency limiter
        limiter = CapacityLimiter(12)
        try:
            # Compute deadline to use to enforce timeouts
            deadline = get_deadline(timeout, deadline)
            # Get list of projects to install
            projects_names = [
                project.name
                for project in self.list_projects(
                    include=include_projects, exclude=exclude_projects
                )
            ]
            if not no_root:
                # Perform first round of install
                await self.poetry_install(
                    include_groups=projects_names,
                    raise_on_error=True,
                    deadline=deadline,
                )
            # List of all results
            all_results: List[Command] = []
            all_projects = self.get_projects_stack(
                include=include_projects, exclude=exclude_projects
            )
            # Iterate over concurrent sequences
            project_idx = 0
            total_projects = sum([len(projects) for projects in all_projects])
            total_steps = len(all_projects)
            for idx, projects in enumerate(all_projects):
                async with create_task_group() as tg:
                    # Create a variable which will hold results for this round of projects
                    results: List[Command] = []
                    # Create a task group to coordinate installs
                    # Iterate over each project
                    for project in projects:
                        project_idx += 1

                        # Define function to perform install
                        async def install_project(project: KProject) -> None:
                            nonlocal results
                            async with limiter:
                                cmd = await project.install(
                                    exclude_groups=exclude_groups,
                                    include_groups=include_groups,
                                    only_groups=only_groups,
                                    default=default,
                                    lock_versions=lock_versions,
                                    force=force,
                                    deadline=deadline,
                                    raise_on_error=True,
                                    quiet=pip_quiet,
                                    clean=False,
                                )
                                if cmd:
                                    results.append(cmd)

                        # Kick off install
                        # tg.start_soon(
                        #     install_project, project, name=f"install-{project.name}"
                        # )
                        tg.start_soon(
                            install_project, project, name=f"install-{project.name}"
                        )
                    logger.info(
                        f"Installing projects (steps={idx+1}/{total_steps} pkgs={project_idx}/{total_projects}): {[p.name for p in projects]}"
                    )
                # Extend all results
                all_results.extend(results)
            # Return all results
            return all_results
        # Always clean files if required
        finally:
            if clean:
                self.clean_pyproject_files()

    async def uninstall_editable_projects(
        self,
        include_projects: Optional[List[str]] = None,
        exclude_projects: Optional[Iterable[str]] = None,
        pip_quiet: bool = True,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
    ) -> Optional[Command]:
        # Create concurrency limiter
        # Get list of projects to install
        projects_names = [
            project.name
            for project in self.list_projects(
                include=include_projects, exclude=exclude_projects
            )
        ]
        if projects_names:
            # Perform first round of install
            return await self.pip_remove(
                *projects_names,
                quiet=pip_quiet,
                raise_on_error=True,
                timeout=timeout,
                deadline=deadline,
            )
        return None

    async def build_projects(
        self,
        include_projects: List[str],
        exclude_projects: Optional[Iterable[str]] = None,
        env: Optional[Mapping[str, str]] = None,
        pip_quiet: bool = True,
        lock_versions: bool = True,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        clean: bool = True,
    ) -> List[Command]:
        # Compute deadline to use to enforce timeouts
        deadline = get_deadline(timeout, deadline)
        # Create a variable which will hold results for this round of projects
        results: List[Command] = []
        # Make sure dist directory exists
        dist_root = Path(self.root, "dist")
        dist_root.mkdir(exist_ok=True, parents=False)
        limiter = CapacityLimiter(8)
        # Create a task group to coordinate installs
        async with create_task_group() as tg:
            # Iterate over synchronous sequences
            for project in self.list_projects(
                include=include_projects, exclude=exclude_projects
            ):
                # Define function to perform install
                async def build_project(project: KProject) -> None:
                    nonlocal results
                    async with limiter:
                        cmd = await project.build(
                            env=env,
                            lock_versions=lock_versions,
                            deadline=deadline,
                            quiet=pip_quiet,
                            raise_on_error=True,
                            clean=clean,
                            recurse=False,
                        )
                        results.append(cmd)
                        wheels = list(Path(project.root / "dist").glob("*.whl"))
                        logger.info(
                            f"Sucessfully built {project.name}",
                            files=[w.relative_to(self.root).as_posix() for w in wheels],
                        )
                        for wheel in wheels:
                            shutil.copy2(wheel, dist_root.as_posix())

                # Kick off install
                tg.start_soon(build_project, project, name=f"build-{project.name}")
        # Return all results
        return results

    def clean_pyproject_files(self) -> None:
        """Clean all auto-generated poetry files"""
        for project in self.projects.values():
            project.remove_pyproject()

    def clean(self, remove_venv: bool = False) -> None:
        """Remove well-known non versioned files"""
        to_remove = [
            expr for expr in self.gitignore if expr not in (".venv", ".venv/", ".git")
        ]
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
