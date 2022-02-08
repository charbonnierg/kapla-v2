from __future__ import annotations
from shutil import ExecError
from typing import Any, Dict, Union
from pathlib import Path

from kapla.cli.cmd import run_cmd
from kapla.cli.datatypes import ProjectSpecs
from kapla.cli.errors import PyprojectNotFoundError
from kapla.cli.finder import lookup_file


class Project:
    def __init__(self, projectfile: Union[str, Path]) -> None:
        """Create a new instance of project"""
        self.projectfile_path = Path(projectfile).resolve(True)
        self.root = self.projectfile_path.parent
        self.specs = ProjectSpecs.from_yaml(self.projectfile_path)

    def __repr__(self) -> str:
        """String representation of a project"""
        return f"Project(name={self.specs.name}, version={self.specs.version}, root={self.root.as_posix()})"

    @classmethod
    def find(cls, start: Union[None, str, Path] = None) -> Project:
        """Find project from current directory by default"""
        projectfile = lookup_file("project.yml", start=start) or lookup_file(
            "project.yaml", start=start
        )
        if projectfile:
            return cls(projectfile)
        raise PyprojectNotFoundError(
            "Cannot find any pyproject.toml file in current directory or parent directories."
        )

    async def install(self, lock: Dict[str, Any]) -> None:
        """Install the project in editable mode"""
        # Generate pyproject.toml
        pyproject = self.specs.to_pyproject(lock=lock)
        pyproject_path = self.root / "pyproject.toml"
        # Write pyproject file
        pyproject_path.write_text(pyproject.toml())
        requirements_file = "requirements.txt"
        requirements_path = self.root / requirements_file
        # Install dependencies only
        await run_cmd(["poetry", "export", "--dev", "--format=requirements.txt", f"--output={requirements_file}"], cwd=self.root)
        await run_cmd(["pip", "install", "-r", "requirements.txt"], cwd=self.root)
        # Run install using editable mode
        finished_process = await run_cmd(["pip", "install", "-e", "."], cwd=self.root)
        # Remove pyproject file on success
        if finished_process.returncode == 0:
            pyproject_path.unlink()
            requirements_path.unlink()

    async def build(self, lock: Dict[str, Any]) -> None:
        # Generate pyproject.toml
        pyproject = self.specs.to_pyproject(lock=lock)
        pyproject_path = self.root / "pyproject.toml"
        # Write pyproject file
        pyproject_path.write_text(pyproject.toml())
        # Run install using editable mode
        finished_process = await run_cmd(["poetry", "build"], cwd=self.root)
        # Remove pyproject file on success
        if finished_process.returncode == 0:
            pyproject_path.unlink()
