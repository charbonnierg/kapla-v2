from typing import Dict, List, Optional, Union

from .base import AliasedModel
from .common import BasePythonConfig
from .pyproject import DepedencyMeta


class DockerSpec(AliasedModel):
    image: str
    template: Optional[str] = None
    dockerfile: Optional[str] = None
    platforms: List[str] = ["linux/amd64"]
    context: str = "./"


class ProjectSpec(BasePythonConfig):
    dependencies: List[Union[str, Dict[str, DepedencyMeta]]] = []
    docker: Optional[DockerSpec] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#extras>
    extras: Dict[str, List[Union[str, Dict[str, DepedencyMeta]]]] = {}
