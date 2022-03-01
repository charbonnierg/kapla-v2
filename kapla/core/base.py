from __future__ import annotations

import shutil
from pathlib import Path
from shutil import which
from typing import (
    Any,
    Dict,
    Generic,
    Iterator,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Type,
    TypeVar,
    Union,
)

from pydantic import BaseModel, ValidationError

from .cmd import Command, check_command, run_command
from .finder import find_files

SpecT = TypeVar("SpecT", bound=BaseModel)


class BaseProject(Generic[SpecT]):
    """Base class for kapla project"""

    __SPEC__: Type[SpecT]

    def __init_subclass__(
        cls, spec: Optional[Type[BaseModel]] = None, **kwargs: Any
    ) -> None:
        super().__init_subclass__(**kwargs)
        if spec:
            cls.__SPEC__ = spec

    def __init__(self, filepath: Union[str, Path]) -> None:
        """Project instances are created using a filepath"""
        super().__init__()
        # Save filepath
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"File does not exist: {filepath}")
        # Save project root directory
        self.root = self.filepath.parent
        # Read content
        self._raw = self.read(self.filepath)
        # Read specs
        self._spec = self.__SPEC__.parse_obj(self._raw)

    def __getitem__(self, key: str) -> Any:
        return self._raw[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._raw)

    def __len__(self) -> int:
        return len(self._raw)

    @property
    def spec(self) -> SpecT:
        """The project specs"""
        return self._spec

    @property
    def python_executable(self) -> str:
        for python_exec in find_files(
            ("**/.venv/bin/python", "**/.venv/Scripts/python.exe"), self.root
        ):
            return python_exec.as_posix()
        raise FileNotFoundError("No virtual environment found for this project")

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

    def set_property(self, key: str, value: Any) -> None:
        """Set a project property value"""
        self.set_properties({key: value})

    def set_properties(self, properties: Dict[str, Any]) -> None:
        """Set a project property value"""
        # Create a mapping to store old values until validation is performed
        old_values: Dict[str, Any] = {}
        # We must generate all nested keys before mutating
        for key, value in properties.items():
            # Make sure that values are not base models
            if isinstance(value, BaseModel):
                value = value.dict(exclude_none=True, exclude_unset=True, by_alias=True)
            elif isinstance(value, list):
                value = [
                    item.dict(exclude_none=True, exclude_unset=True, by_alias=True)
                    if isinstance(item, BaseModel)
                    else item
                    for item in value
                ]
            # Initialize object to mutation
            obj: Any = None
            # Split key using "." separator
            tokens = key.split(".")
            # Iterate over all tokens except last one
            for token in tokens[:-1]:
                if obj is None:
                    try:
                        obj = self._raw[token]
                    except KeyError:
                        if token.isdigit():
                            self._raw[token] = list()
                        else:
                            self._raw[token] = dict()
                else:
                    if isinstance(obj, list):
                        obj = obj[int(token)]
                    elif isinstance(obj, Mapping):
                        obj = obj[token]
                    else:
                        obj = getattr(obj, token)
            # Update value
            if obj:
                if isinstance(obj, list):
                    last_token = tokens[-1]
                    if last_token == "$push":
                        obj.append(value)
                    elif last_token == "$pop":
                        obj.remove(value)
                    else:
                        idx = int(tokens[-1])
                        if idx == len(obj):
                            obj.append(value)
                        else:
                            obj[idx] = value
                elif isinstance(obj, MutableMapping):
                    obj[tokens[-1]] = value
                else:
                    setattr(obj, tokens[-1], value)
            else:
                self._raw[key] = value
        # Validation project spec
        try:
            self._spec = self.__SPEC__.parse_obj(self._raw)
        except ValidationError:
            # Revert value change
            self.refresh()
            # Raise error back
            raise
        else:
            # We can discard old values
            del old_values
        # Write new spec
        self.write(self.filepath)

    def refresh(self) -> None:
        """Refresh project specs"""
        # Read content
        self._raw = self.read(self.filepath)
        # Read specs
        self._spec = self.__SPEC__.parse_obj(self._raw)

    def read(self, path: Union[str, Path]) -> Any:
        """Read project specs from file"""
        raise NotImplementedError("read method must be overriden in child class")

    def write(self, path: Union[str, Path]) -> Path:
        """Write project specs into file"""
        raise NotImplementedError("write method must be overriden in child class")

    async def run_module(
        self,
        *module: str,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        rc: Optional[int] = 0,
    ) -> Command:
        """Uninstall a package using pip but does not remove package as dependency"""
        return await run_command(
            [self.python_executable, "-m", *module],
            timeout=timeout,
            deadline=deadline,
            rc=rc,
        )

    async def pip_install(
        self,
        *packages: str,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
    ) -> Command:
        """Install a package using pip but does not add package as dependency"""
        return await self.run_module(
            "pip",
            "install",
            *packages,
            timeout=timeout,
            deadline=deadline,
            rc=0 if raise_on_error else None,
        )

    async def pip_remove(
        self,
        *packages: str,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
    ) -> Command:
        """Uninstall a package using pip but does not remove package as dependency"""
        return await self.run_module(
            "pip",
            "uninstall",
            "-y",
            *packages,
            timeout=timeout,
            deadline=deadline,
            rc=0 if raise_on_error else None,
        )

    async def update_pip_toolkit(
        self,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        raise_on_error: bool = False,
    ) -> None:
        """Update pip, setuptools and wheel to their latest versions"""
        await self.pip_install(
            "-U",
            "pip",
            "setuptools",
            "wheel",
            timeout=timeout,
            deadline=deadline,
            raise_on_error=raise_on_error,
        )

    async def run(
        self,
        cmd: Union[str, List[str]],
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        env: Optional[Mapping[str, str]] = None,
        rc: Optional[int] = None,
        **kwargs: Any,
    ) -> Command:
        """Run a command with poetry environment"""
        venv_bin = Path(self.python_executable).parent
        venv_path = venv_bin.parent
        environment = {"VIRTUAL_ENV": venv_path.as_posix()}
        if env:
            environment.update(env)
        return await run_command(
            cmd,
            timeout=timeout,
            deadline=deadline,
            env=environment,
            append_path=venv_bin,
            rc=rc,
            **kwargs,
        )

    async def venv(
        self,
        name: str = ".venv",
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
    ) -> Path:
        """Ensure venv is created within project"""
        venv_root = self.root / name
        # by default use python3
        python = "python3"
        # Check if it exist though
        if which(python) is None:
            # And fallback to "python" if not (windows users here you go)
            python = "python"
        done_cmd = await check_command(
            [python, "-m", "venv", name],
            cwd=self.root,
            timeout=timeout,
            deadline=deadline,
        )
        # Update pip using executable
        await self.update_pip_toolkit(deadline=done_cmd.deadline)
        # Return path to venv
        return venv_root

    async def ensure_venv(
        self,
        name: str = ".venv",
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
    ) -> None:
        """Ensure virtual environment exists"""
        if not Path(self.root / name).exists():
            await self.venv(name, timeout=timeout, deadline=deadline)

    def remove_venv(
        self,
        name: str = ".venv",
    ) -> None:
        shutil.rmtree(Path(self.root, name), ignore_errors=True)
