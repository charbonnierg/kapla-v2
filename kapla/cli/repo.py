from __future__ import annotations
import asyncio
from functools import cached_property
from multiprocessing import pool
from typing import Any, Dict, Iterator, List, Optional, Set, Union
from pathlib import Path
from graphlib import TopologicalSorter
from kapla.cli.cmd import run_cmd
from kapla.cli.concurrency import TaskPool
from kapla.cli.config import KaplaToolConfig
from kapla.cli.datatypes import Pyproject, ProjectSpecs
from kapla.cli.errors import PyprojectNotFoundError, WorkspaceDoesNotExistError
from kapla.cli.finder import find_files, lookup_file
import toml
import yaml

from kapla.cli.project import Project


class Monorepo:
    def __init__(self, pyproject_path: Union[str, Path]) -> None:
        """Create a new instance of project"""
        self.pyproject_path = Path(pyproject_path).resolve(True)
        self.root = self.pyproject_path.parent
        self._pyproject = toml.load(pyproject_path)
        self.pyproject = Pyproject.parse_obj(self._pyproject["tool"]["poetry"])
        self.lock_path = self.root / "poetry.lock"
        try:
            self.kapla = KaplaToolConfig.parse_obj(self._pyproject["tool"]["kapla"])
        except KeyError:
            self.kapla = KaplaToolConfig()
        self.lock = self._get_packages_lock()

    def __repr__(self) -> str:
        """String representation of a project"""
        return f"Project(name={self.pyproject.name}, version={self.pyproject.version}, root={self.root.as_posix()})"

    def _get_packages_lock(self) -> Dict[str, Any]:
        if self.lock_path.exists():
            lockfile_content = toml.load(self.root / "poetry.lock")
            lock = {package["name"]: package for package in lockfile_content["package"]}
        else:
            lock = {}
        lock.update({
            name: {"version": project.specs.version} for name, project in self.projects.items()
        })
        return lock

    @classmethod
    def find(cls, start: Union[None, str, Path] = None) -> Monorepo:
        """Find project from current directory by default"""
        pyproject_path = lookup_file("pyproject.toml", start=start)
        if pyproject_path:
            return cls(pyproject_path)
        raise PyprojectNotFoundError(
            "Cannot find any pyproject.toml file in current directory or parent directories."
        )

    def find_projects(self, workspace: Optional[str] = None) -> Iterator[Project]:
        """Find all projects from current directory by default"""

        if workspace:
            try:
                root_directories = [
                    Path(self.root, directory)
                    for directory in self.kapla.workspaces[workspace]
                ]
            except KeyError:
                raise WorkspaceDoesNotExistError(
                    f"Workspace '{workspace}' does not exist. Available workspaces: [{', '.join(self.kapla.workspaces)}]"
                )
        else:
            root_directories = [
                Path(self.root, directory)
                for directories in self.kapla.workspaces.values()
                for directory in directories
            ]
        if not root_directories:
            root_directories = [self.root]

        for directory in root_directories:
            for project_path in find_files("**/project.yml", start=directory):
                if project_path == self.pyproject_path:
                    continue
                yield Project(project_path)

    @cached_property
    def projects(self) -> Dict[str, Project]:
        return {project.specs.name: project for project in self.find_projects()}

    @cached_property
    def projects_sequence(self) -> List[Project]:
        nodes = {}
        project_names = list(self.projects)
        for project in self.projects.values():
            local_dependencies = {dep for dep in project.specs.dependencies if dep in project_names}
            local_dev_dependencies = {dep for dep in project.specs.dev_dependencies if dep in project_names}
            nodes[project.specs.name] = list({*local_dependencies, *local_dev_dependencies})
        return [self.projects[project] for project in TopologicalSorter(nodes).static_order()]

    @cached_property
    def projects_dependencies(self) -> Dict[str, List[str]]:
        cache = dict()
        for project_name in self.projects:
            project_deps = self._get_project_local_dependencies(project_name, cache)
            cache[project_name] = project_deps
        return cache

    def get_local_dependencies(self, *names: str) -> List[str]:
        dependencies = set()
        for project_name in set(names):
            dependencies.update(self.projects_dependencies.get(project_name), [])
        return list(dependencies)

    def _get_project_local_dependencies(self, name: str, cache: Dict[str, Set[str]] = {}) -> Set[str]:
        project = self.projects[name]

        if name in cache:
            return cache[name]

        project_dependencies = set(project.specs.dependencies)
        project_dependencies.update(project.specs.dev_dependencies)
        # Keep only local dependencies
        project_dependencies = project_dependencies.intersection(self.projects)
        # Create a new set for indirect dependencies
        indirect_dependencies = set()
        # Iterate over dependencies
        for _project in project_dependencies:
            # And search for dependencies of dependencies
            new_dependencies = self._get_project_local_dependencies(_project, cache=cache)
            # Keep results into a cache to avoid looking several time for the dependencies of a single package
            cache[_project] = new_dependencies
            # Update indirect dependencies
            indirect_dependencies.update(new_dependencies)
        # Return the union of project dependencies and indirect dependencies
        return project_dependencies.union(indirect_dependencies)

    async def build_project(self, name: str) -> None:
        project = self.projects[name]
        await project.build(self.lock)

    async def add_dependency(self, expr: str, project_name: str) -> None:
        project = self.projects[project_name]
        await run_cmd(["poetry", "add", expr], cwd=self.root)
        # Keep a copy of old pyproject
        old_deps = list(self.pyproject.dependencies)
        # Refresh lock and pyproject
        self._pyproject = toml.load(self.pyproject_path)
        self.pyproject = Pyproject.parse_obj(self._pyproject["tool"]["poetry"])
        self.lock = self._get_packages_lock()
        # Get all dependencies
        all_deps = set(self.pyproject.dependencies)
        # Get difference
        new_deps = all_deps.difference(old_deps)
        # Add dependency to project file
        for new_dep in new_deps:
            project.specs.dependencies.append(new_dep)
        # Write project file
        project.projectfile_path.write_text(project.specs.yaml())

    async def install(self, *names: str) -> None:
        """Install one or several packages"""
        # Fetch list of packages to install
        names = names or list(self.projects)
        # Create a list containing all dependencies
        dependencies = [dependency for name in names for dependency in self.projects_dependencies[name]]
        installed: Set[str] = set()

        async def _install(project: Project) -> None:
            nonlocal installed
            await project.install(self.lock)
            print(f"Successfully installed {project.specs.name}")
            installed.add(project.specs.name)

        # A first pool where we can submit arbitrary tasks
        async with TaskPool(max_concurrency=None) as project_pool:
            # A second pool where we can submit only packages install
            async with TaskPool(max_concurrency=None) as packages_pool:
                # Iterate over project sequence
                for project in self.projects_sequence:
                    print(f"Preparing to install {project.specs.name}")
                    # Run the install if project is required
                    if project.specs.name in names or dependencies:
                        # If project does not have local dependencies
                        if not self.projects_dependencies[project.specs.name]:
                            # We can fire package installation using a task
                            await packages_pool.acreate_task(_install(project), name=project.specs.name)
                            continue
                        # If all local dependencies are installed
                        elif all([dep in installed for dep in self.projects_dependencies[project.specs.name]]):
                            print(f"Installing {project.specs.name} (all dependencies already installed)")
                            await packages_pool.acreate_task(_install(project), name=project.specs.name)
                            continue
                        # Wait for first dependency to be installed
                        else:
                            async def _wait_and_install(project: Project) -> None:
                                nonlocal installed
                                # Enter an infinite loop
                                while True:
                                    # Wait for any package to be installed
                                    # WARNING: There may be no packages
                                    await packages_pool.wait(return_when=asyncio.FIRST_COMPLETED)
                                    # Wait for another task in there are still pending dependencies
                                    if pending_deps := [dep for dep in self.projects_dependencies[project.specs.name] if dep not in installed]:
                                        continue
                                    # Break when there are no more pending tasks
                                    print(f"Installing {project.specs.name} (all dependencies successfully installed [{','.join(self.projects_dependencies[project.specs.name])}]))")
                                    await packages_pool.acreate_task(_install(project), name=project.specs.name)
                                    return
                            # Start the coroutine
                            await project_pool.acreate_task(_wait_and_install(project))
                # Wait for all tasks to finish
                await project_pool.wait()
                await packages_pool.wait()
