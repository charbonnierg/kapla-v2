from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field
import toml
import yaml


class BuildSystem(BaseModel):
    """Pyproject files always contain a "[build-system]" section.

    References:
      * <https://python-poetry.org/docs/pyproject/#poetry-and-pep-517>
    """

    requires: List[str]
    build_backend: str = Field(..., alias="build-backend")


class Package(BaseModel):
    """A package can be declared as a dictionnary.

    References:
      *  <https://python-poetry.org/docs/pyproject/#packages>
    """

    include: str
    format: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")


class Dependency(BaseModel):
    """A dependency found in a pyproject.toml file.

    Dependencies can be found in:
      - `[tool.poetry.dependencies]`
      - `[tool.poetry.dev-dependencies]`

    Note: A dependency can also be declared as a string.

    References:
      * <https://python-poetry.org/docs/pyproject/#dependencies-and-dev-dependencies>
    """

    version: Optional[str] = None
    path: Optional[str] = None
    optional: Optional[bool] = None
    git: Optional[str] = None
    branch: Optional[str] = None
    extras: Optional[List[str]] = None
    python: Optional[str] = None
    markers: Optional[str] = None


class Pyproject(BaseModel):
    """A complete pyproject.toml file.

    References:
        * [The pyproject.toml file](https://python-poetry.org/docs/pyproject/)
        * [Poetry pyproject.toml file](https://github.com/python-poetry/poetry/blob/master/pyproject.toml)
    """

    # Docs: <https://python-poetry.org/docs/pyproject/#name>
    name: str
    # Docs: <https://python-poetry.org/docs/pyproject/#version>
    version: str
    # Docs: <https://python-poetry.org/docs/pyproject/#description>
    description: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#license>
    license: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#authors>
    authors: List[str] = []
    # Docs: <https://python-poetry.org/docs/pyproject/#maintainers>
    maintainers: List[str] = []
    # Docs: <https://python-poetry.org/docs/pyproject/#readme>
    readme: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#homepage>
    homepage: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#repository>
    repository: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#documentation>
    documentation: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#keywords>
    keywords: List[str] = []
    # Docs: <https://python-poetry.org/docs/pyproject/#classifiers>
    classifiers: List[str] = []
    # Docs: <https://python-poetry.org/docs/pyproject/#packages>
    packages: Optional[List[Union[str, Package]]] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#include-and-exclude>
    include: List[str] = []
    exclude: List[str] = []
    # Docs: <https://python-poetry.org/docs/pyproject/#dependencies-and-dev-dependencies>
    dependencies: Dict[str, Union[str, Dependency]]
    dev_dependencies: Dict[str, Union[str, Dependency]] = Field(
        {}, alias="dev-dependencies"
    )
    # Docs: <https://python-poetry.org/docs/pyproject/#scripts>
    scripts: Dict[str, str] = {}
    # Docs: <https://python-poetry.org/docs/pyproject/#extras>
    extras: Dict[str, List[str]] = {}
    # Docs: <https://python-poetry.org/docs/pyproject/#plugins>
    plugins: Dict[str, Dict[str, str]] = {}
    # Docs: <https://python-poetry.org/docs/pyproject/#urls>
    urls: Dict[str, str] = {}
    # Docs: <https://python-poetry.org/docs/pyproject/#poetry-and-pep-517>
    build_system: Optional[BuildSystem] = Field(None, alias="build-system")

    def toml(self) -> str:
        """Write content to TOML file"""
        return toml.dumps(
            {
                "build-system": {
                    "requires": [
                        "poetry-core @ git+https://github.com/python-poetry/poetry-core.git@master"
                    ],
                    "build-backend": "poetry.core.masonry.api",
                },
                "tool": {"poetry": self.dict(by_alias=True, exclude_none=True)},
            }
        )


class ProjectSpecs(BaseModel):
    # Docs: <https://python-poetry.org/docs/pyproject/#name>
    name: str
    # Docs: <https://python-poetry.org/docs/pyproject/#version>
    version: str
    # Docs: <https://python-poetry.org/docs/pyproject/#description>
    description: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#license>
    license: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#authors>
    authors: List[str] = []
    # Docs: <https://python-poetry.org/docs/pyproject/#maintainers>
    maintainers: List[str] = []
    # Docs: <https://python-poetry.org/docs/pyproject/#readme>
    readme: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#homepage>
    homepage: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#repository>
    repository: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#documentation>
    documentation: Optional[str] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#keywords>
    keywords: List[str] = []
    # Docs: <https://python-poetry.org/docs/pyproject/#classifiers>
    classifiers: List[str] = []
    # Docs: <https://python-poetry.org/docs/pyproject/#packages>
    packages: Optional[List[Union[str, Package]]] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#include-and-exclude>
    include: List[str] = []
    exclude: List[str] = []
    # # Internal dependencies
    # requires: List[str] = []
    # Docs: <https://python-poetry.org/docs/pyproject/#dependencies-and-dev-dependencies>
    dependencies: List[str] = []
    dev_dependencies: List[str] = Field([], alias="dev-dependencies")
    # Docs: <https://python-poetry.org/docs/pyproject/#scripts>
    scripts: Dict[str, str] = {}
    # Docs: <https://python-poetry.org/docs/pyproject/#extras>
    extras: Dict[str, List[str]] = {}
    # Docs: <https://python-poetry.org/docs/pyproject/#plugins>
    plugins: Dict[str, Dict[str, str]] = {}
    # Docs: <https://python-poetry.org/docs/pyproject/#urls>
    urls: Dict[str, str] = {}

    def to_pyproject(self, lock: Dict[str, Any]) -> Pyproject:
        config = self.dict(by_alias=True)
        # Override dependencies
        config["dependencies"] = {
            # FIXME: Use python version from monorepo
            "python": ">=3.8",
            **{key: lock[key]["version"] for key in self.dependencies}
        }
        # Override dev dependencies
        config["dev-dependencies"] = {
             key: lock[key]["version"] for key in self.dev_dependencies
        }
        # Return a pyproject instance
        return Pyproject(**config)

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> ProjectSpecs:
        filepath = Path(path)
        return cls.parse_obj(yaml.load(filepath.read_bytes(), yaml.SafeLoader))

    def yaml(self, **kwargs: Any) -> str:
        return yaml.dump(self.dict(by_alias=True, exclude_unset=True), indent=2, default_flow_style=False, default_style=False, sort_keys=False, Dumper=yaml.SafeDumper)

    def toml(self) -> str:
        """Write content to TOML file"""
        return toml.dumps(self.dict(by_alias=True, exclude_unset=True))
