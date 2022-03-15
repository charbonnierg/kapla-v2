from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import Field

from .base import AliasedModel


class LockedPackage(AliasedModel):
    name: str
    version: str
    description: Optional[str] = None
    category: Optional[str] = None
    optional: Optional[bool] = None
    python_versions: Optional[str] = Field(alias="python-versions")
    extras: Optional[Dict[str, List[str]]] = {}
    dependencies: Optional[Dict[str, Union[str, Dict[str, Any]]]] = {}


class LockedMetadata(AliasedModel):
    lock_version: str = Field(alias="lock-version")
    python_versions: str = Field(alias="python-versions")
    content_hash: str = Field(alias="content-hash")

    class Config(AliasedModel.Config):
        extra = "allow"


class LockFile(AliasedModel):
    packages: Dict[str, LockedPackage]
    metadata: Optional[LockedMetadata] = None
