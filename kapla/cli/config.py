from typing import Dict, List
from pydantic import BaseModel, validator


class KaplaToolConfig(BaseModel):
    workspaces: Dict[str, List[str]] = []
