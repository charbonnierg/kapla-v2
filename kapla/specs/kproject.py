from typing import Dict, List, Optional, Union

from .base import AliasedModel
from .common import BasePythonConfig
from .pyproject import DepedencyMeta


class DockerSpec(AliasedModel):
    image: str
    base_image: Optional[str] = None
    template: Optional[str] = None
    dockerfile: Optional[str] = None
    platforms: List[str] = ["linux/amd64"]
    context: str = "./"
    labels: List[str] = []
    build_args: Optional[Dict[str, str]] = None


class KProjectSpec(BasePythonConfig):
    # Docs: <https://python-poetry.org/docs/pyproject/#version>
    version: Optional[str] = None
    dependencies: List[Union[str, Dict[str, DepedencyMeta]]] = []
    docker: Optional[DockerSpec] = None
    # Docs: <https://python-poetry.org/docs/pyproject/#extras>
    extras: Dict[str, List[Union[str, Dict[str, DepedencyMeta]]]] = {}
