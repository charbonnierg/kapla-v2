from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Union

import tomlkit
from ruamel.yaml import YAML
from tomlkit.toml_document import TOMLDocument

yaml = YAML(typ="rt")


def loads_toml(content: Union[str, bytes]) -> TOMLDocument:
    """Load a TOMLDocument instance from TOML string or bytes"""
    return tomlkit.parse(content)


def load_toml(path: Union[str, Path]) -> TOMLDocument:
    """Load a toml TOMLDocument instance from given TOML file"""
    path = Path(path)
    return tomlkit.parse(Path(path).read_bytes())


def dumps_toml(doc: Any) -> str:
    """Return document in TOML representation as a string"""
    return tomlkit.dumps(doc)


def write_toml(doc: Any, path: Union[str, Path]) -> Path:
    """Write TOML representation at filepath"""
    out = Path(path)
    out.write_text(dumps_toml(doc))
    return out


def loads_yaml(content: Union[str, bytes]) -> Any:
    """Load a ruamel.yaml object (most of the time mapping or sequence) from YAML string or bytes"""
    return yaml.load(content)


def load_yaml(path: Union[str, Path]) -> Any:
    """Load a ruamel.yaml object (most of the time mapping or sequence) from YAML file"""
    return yaml.load(Path(path).read_bytes())


def dumps_yaml(doc: Any) -> str:
    """Return document YAML representation as a string"""
    yaml_out = io.StringIO()
    yaml.dump(doc, yaml_out)
    yaml_out.seek(0)
    return yaml_out.read()


def write_yaml(doc: Any, path: Union[str, Path]) -> Path:
    """Write YAML file"""
    out = Path(path)
    out.write_text(dumps_yaml(doc))
    return out
