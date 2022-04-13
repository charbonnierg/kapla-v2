from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any, Generic, Iterator, List, Mapping, Optional, Type, TypeVar, Union

from pydantic import BaseModel

from kapla.core.cmd import Command, check_command, run_command
from kapla.core.finder import DEFAULT_GITIGNORE, find_files
from kapla.core.logger import logger
from kapla.core.windows import IS_WINDOWS
from kapla.wrappers.git import GitInfos, get_branch, get_commit, get_infos, get_tag

SpecT = TypeVar("SpecT", bound=BaseModel)


class BaseProject(Generic[SpecT]):
    """Base class for both kapla project and pyproject"""

    __SPEC__: Type[SpecT]

    def __init_subclass__(
        cls, spec: Optional[Type[BaseModel]] = None, **kwargs: Any
    ) -> None:
        """Initialize child class.

        This function is not when new class is defined (not instances).
        """
        super().__init_subclass__(**kwargs)
        if spec:
            # Store spec parameter into __SPEC__ attribute of child class
            # This attribute will be available to all instances of child classes
            cls.__SPEC__ = spec

    def __init__(self, filepath: Union[str, Path]):
        """Create a new instance of BaseProject.

        Projects are initialized using a filepath.
        """
        super().__init__()
        # Save filepath
        self.filepath = Path(filepath)
        # Check that filepath exists
        if not self.filepath.exists():
            raise FileNotFoundError(f"File does not exist: {filepath}")
        # Save project root directory
        self.root = self.filepath.parent
        # Read raw content of spec
        self._raw = self.read(self.filepath)
        # Parse spec
        self._spec = self.__SPEC__.parse_obj(self._raw)

    def __getitem__(self, key: str) -> Any:
        """Get a property from the raw spec. Mostly used to overwrite spec."""
        return self._raw[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate over raw spec fields"""
        return iter(self._raw)

    def __len__(self) -> int:
        """Number of fields in raw spec"""
        return len(self._raw)

    @property
    def spec(self) -> SpecT:
        """The parsed project spec. Spec is guaranteed to be a valid spec."""
        return self._spec

    @property
    def gitignore(self) -> List[str]:
        """Constant value at the moment. We should parse project gitignore in the future.

        FIXME: Support reading gitignore from project
        """
        return DEFAULT_GITIGNORE

    def get_property(self, key: str, raw: bool = False) -> Any:
        """Get a project property value.

        The key used to retrieve property can be either a string or a tuple of arguments.
        """
        # Initialize the object we're going to return
        obj: Any = None
        src = self._raw if raw else self._spec
        # Split key into tokens using "." as separator
        tokens = key.split(".")
        # Iterate over token
        for token in tokens:
            # Initialize object if needed
            if obj is None:
                obj = getattr(src, token)
            # Fetch nested object using token
            else:
                if isinstance(obj, list):
                    obj = obj[int(token)]
                elif isinstance(obj, Mapping):
                    obj = obj[token]
                else:
                    obj = getattr(obj, token)

        # Return object
        return obj

    def refresh(self) -> None:
        """Refresh project spec, I.E, read and parse spec from file."""
        # Read raw spec
        self._raw = self.read(self.filepath)
        # Update parsed spec
        self._spec = self.__SPEC__.parse_obj(self._raw)

    def read(self, path: Union[str, Path]) -> Any:
        """Read project specs from file"""
        raise NotImplementedError("read method must be overriden in child class")

    def write(self, path: Union[str, Path]) -> Path:
        """Write project specs into file"""
        raise NotImplementedError("write method must be overriden in child class")

    async def get_git_commit(self) -> Optional[str]:
        """Get current git commit sha"""
        return await get_commit(self.root)

    async def get_git_branch(self) -> Optional[str]:
        """Get current git branch name"""
        return await get_branch(self.root)

    async def get_git_tag(self) -> Optional[str]:
        """Get current git tag name"""
        return await get_tag(self.root)

    async def get_git_infos(self) -> GitInfos:
        """Ge git infos from project (include commit, branch and tag)"""
        return await get_infos(self.root)


class BasePythonProject(BaseProject[SpecT]):

    _python_executable: Path

    @property
    def venv_path(self) -> Path:
        """Return path to virtualenv root directory"""
        return self.root / ".venv"

    @property
    def venv_bin(self) -> Path:
        """Return path to virtualenv bin directory"""
        if IS_WINDOWS:
            return self.venv_path / "Scripts"
        else:
            return self.venv_path / "bin"

    @property
    def venv_site_packages(self) -> Path:
        """Return path to virtualenv bin directory"""
        if IS_WINDOWS:
            return self.venv_path / "Lib" / "site-packages"
        else:
            return (
                self.venv_path
                / "lib"
                / f"python{sys.version_info.major}.{sys.version_info.minor}"
                / "site-packages"
            )

    @property
    def python_executable(self) -> str:
        """Path to python executable associated with the project."""
        try:
            return self._python_executable.as_posix()
        except AttributeError:
            for python_exec in find_files(
                pattern="python.exe" if IS_WINDOWS else "python",
                root=self.venv_path,
                ignore=["include", "Include", "lib", "Lib", "share", "doc"],
            ):
                self._python_executable = python_exec
                return self._python_executable.as_posix()
        raise FileNotFoundError("No virtual environment found for this project")

    async def run_module(
        self,
        *module: str,
        shell: bool = False,
        env: Optional[Mapping[str, str]] = None,
        rc: Optional[int] = None,
        quiet: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Run a python module"""
        environment = {"VIRTUAL_ENV": self.venv_path.as_posix()}
        if env:
            environment.update(env)
        return await run_command(
            [self.python_executable, "-m", *module],
            shell=shell,
            env=environment,
            append_path=self.venv_bin,
            rc=rc,
            quiet=quiet,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def run_cmd(
        self,
        cmd: Union[str, List[str]],
        shell: bool = False,
        env: Optional[Mapping[str, str]] = None,
        rc: Optional[int] = None,
        quiet: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Run a command with poetry environment"""
        environment = {"VIRTUAL_ENV": self.venv_path.as_posix()}
        if env:
            environment.update(env)
        return await run_command(
            cmd,
            shell=shell,
            timeout=timeout,
            deadline=deadline,
            env=environment,
            append_path=self.venv_bin,
            rc=rc,
            quiet=quiet,
            **kwargs,
        )

    async def pip_install(
        self,
        *packages: str,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Install a package using pip but does not add package as dependency"""
        kwargs["rc"] = kwargs.get("rc", 0 if raise_on_error else None)
        return await self.run_module(
            "pip",
            "install",
            *packages,
            quiet=quiet,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def pip_update(
        self,
        *packages: str,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Install a package using pip but does not add package as dependency"""
        kwargs["rc"] = kwargs.get("rc", 0 if raise_on_error else None)
        return await self.run_module(
            "pip",
            "install",
            "-U",
            *packages,
            quiet=quiet,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def pip_remove(
        self,
        *packages: str,
        raise_on_error: bool = False,
        quiet: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Command:
        """Uninstall a package using pip but does not remove package as dependency"""
        kwargs["rc"] = kwargs.get("rc", 0 if raise_on_error else None)
        return await self.run_module(
            "pip",
            "uninstall",
            "-y",
            *packages,
            quiet=quiet,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def update_pip_toolkit(
        self,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        """Update pip, setuptools and wheel to their latest versions"""
        await self.pip_update(
            "pip",
            "setuptools",
            "wheel",
            quiet=quiet,
            raise_on_error=raise_on_error,
            timeout=timeout,
            deadline=deadline,
            **kwargs,
        )

    async def update_venv(
        self,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> Path:
        """Ensure venv is created within project"""
        kwargs["rc"] = kwargs.get("rc", 0 if raise_on_error else None)
        # by default use python3
        python = "python" if IS_WINDOWS else "python3"
        # Create virtual environment
        await check_command(
            [python, "-m", "venv", self.venv_path.name],
            shell=True,
            cwd=self.venv_path.parent,
            timeout=timeout,
            deadline=deadline,
            quiet=quiet,
            **kwargs,
        )
        # Remove broken packages
        self.remove_broken_packages()
        # Update pip using executable
        await self.pip_update(
            "pip",
            "setuptools",
            "wheel",
            timeout=timeout,
            deadline=deadline,
            quiet=quiet,
            **kwargs,
        )
        # Return path to venv
        return self.venv_path

    async def ensure_venv(
        self,
        quiet: bool = False,
        raise_on_error: bool = False,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        """Ensure virtual environment exists"""
        if not self.venv_path.exists():
            await self.update_venv(
                quiet=quiet,
                raise_on_error=raise_on_error,
                timeout=timeout,
                deadline=deadline,
                **kwargs,
            )
        else:
            self.remove_broken_packages()

    def remove_venv(self) -> None:
        """Remove virtual environment"""
        shutil.rmtree(self.venv_path, ignore_errors=True)

    def remove_broken_packages(self) -> None:
        broken_paths = self.venv_site_packages.glob("./~*")
        for path in broken_paths:
            logger.warning(f"Removing broken install: {path.resolve(True).as_posix()}")
            shutil.rmtree(path, ignore_errors=True)
