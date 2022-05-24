from __future__ import annotations

from typing import Dict, List, Optional, Union

from pydantic import Field

from .base import AliasedModel


class BuildSystem(AliasedModel):
    """Pyproject files always contain a "[build-system]" section.

    References:
      * <https://python-poetry.org/docs/pyproject/#poetry-and-pep-517>
    """

    requires: List[str]
    build_backend: str = Field(..., alias="build-backend")


class Package(AliasedModel):
    """A package can be declared as a dictionnary.

    References:
      *  <https://python-poetry.org/docs/pyproject/#packages>
    """

    include: str
    format: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")


class BasePythonConfig(AliasedModel):
    # Docs: <https://python-poetry.org/docs/pyproject/#name>
    name: str
    # Docs: <https://python-poetry.org/docs/pyproject/#version>
    version: Optional[str] = None
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
    # Docs: <https://python-poetry.org/docs/pyproject/#scripts>
    scripts: Dict[str, str] = {}
    # Docs: <https://python-poetry.org/docs/pyproject/#plugins>
    plugins: Dict[str, Dict[str, str]] = {}
    # Docs: <https://python-poetry.org/docs/pyproject/#urls>
    urls: Dict[str, str] = {}
