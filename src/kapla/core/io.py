from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Optional, Type, TypeVar, Union, overload

import pydantic
import tomlkit
from ruamel.yaml import YAML
from tomlkit.toml_document import TOMLDocument

# replacement strings
WINDOWS_LINE_ENDING = b"\r\n"
UNIX_LINE_ENDING = b"\n"

yaml = YAML(typ="rt")


ValidatorT = TypeVar("ValidatorT", bound=pydantic.BaseModel)


@overload
def load_toml(content: Union[str, bytes]) -> TOMLDocument:
    ...


@overload
def load_toml(content: Union[str, bytes], validator: None) -> TOMLDocument:
    ...


@overload
def load_toml(content: Union[str, bytes], validator: Type[ValidatorT]) -> ValidatorT:
    ...


def load_toml(
    content: Union[str, bytes], validator: Optional[Type[ValidatorT]] = None
) -> Any:
    """Load a TOMLDocument instance from TOML string or bytes"""
    parsed_content = tomlkit.parse(content)
    if validator:
        return validator.parse_obj(parsed_content)
    else:
        return parsed_content


def dumps_toml(doc: Any) -> str:
    """Return document in TOML representation as a string"""
    return tomlkit.dumps(doc)


def dump_toml(doc: Any) -> bytes:
    """Return document in TOML representation as a string"""
    toml_out = io.StringIO()
    tomlkit.dump(doc, toml_out)
    toml_out.seek(0)
    return toml_out.read().encode("utf-8")


@overload
def read_toml(path: Union[str, Path]) -> TOMLDocument:
    ...


@overload
def read_toml(path: Union[str, Path], validator: None) -> TOMLDocument:
    ...


@overload
def read_toml(path: Union[str, Path], validator: Type[ValidatorT]) -> ValidatorT:
    ...


def read_toml(
    path: Union[str, Path], validator: Optional[Type[ValidatorT]] = None
) -> Any:
    """Load a toml TOMLDocument instance from given TOML file"""
    path = Path(path)
    parsed_content = tomlkit.parse(
        Path(path).read_bytes().replace(WINDOWS_LINE_ENDING, UNIX_LINE_ENDING)
    )
    if validator:
        return validator.parse_obj(parsed_content)
    else:
        return parsed_content


def write_toml(
    doc: Any,
    path: Union[str, Path],
) -> Path:
    """Write TOML representation at filepath"""
    out = Path(path)
    content = dumps_toml(doc).encode()
    out.write_bytes(content)
    return out


@overload
def load_yaml(content: Union[str, bytes]) -> Any:
    ...


@overload
def load_yaml(content: Union[str, bytes], validator: None) -> Any:
    ...


@overload
def load_yaml(content: Union[str, bytes], validator: Type[ValidatorT]) -> ValidatorT:
    ...


def load_yaml(
    content: Union[str, bytes], validator: Optional[Type[ValidatorT]] = None
) -> Any:
    """Load a ruamel.yaml object (most of the time mapping or sequence) from YAML string or bytes"""
    parsed_content = yaml.load(content)
    if validator:
        return validator.parse_obj(parsed_content)
    else:
        return parsed_content


def dumps_yaml(doc: Any) -> str:
    """Return document YAML representation as a string"""
    yaml_out = io.StringIO()
    yaml.dump(doc, yaml_out)
    yaml_out.seek(0)
    return yaml_out.read()


def dump_yaml(doc: Any) -> bytes:
    """Return document YAML representation as bytes"""
    yaml_out = io.BytesIO()
    yaml.dump(doc, yaml_out)
    yaml_out.seek(0)
    return yaml_out.read()


@overload
def read_yaml(path: Union[str, Path]) -> Any:
    ...


@overload
def read_yaml(path: Union[str, Path], validator: None) -> Any:
    ...


@overload
def read_yaml(path: Union[str, Path], validator: Type[ValidatorT]) -> ValidatorT:
    ...


def read_yaml(
    path: Union[str, Path], validator: Optional[Type[ValidatorT]] = None
) -> Any:
    """Load a ruamel.yaml object (most of the time mapping or sequence) from YAML file"""
    parsed_content = yaml.load(
        Path(path).read_bytes().replace(WINDOWS_LINE_ENDING, UNIX_LINE_ENDING)
    )
    if validator:
        return validator.parse_obj(parsed_content)
    else:
        return parsed_content


def write_yaml(
    doc: Any, path: Union[str, Path], eof: Optional[bytes] = UNIX_LINE_ENDING
) -> Path:
    """Write YAML file"""
    out = Path(path)
    content = dump_yaml(doc)
    out.write_bytes(content)
    return out


@overload
def load_json(content: Union[str, bytes]) -> Any:
    ...


@overload
def load_json(content: Union[str, bytes], validator: None) -> Any:
    ...


@overload
def load_json(content: Union[str, bytes], validator: Type[ValidatorT]) -> ValidatorT:
    ...


def load_json(
    content: Union[str, bytes], validator: Optional[Type[ValidatorT]] = None
) -> Any:
    """Load an object from JSON string or bytes"""
    if validator:
        return validator.parse_raw(content)
    return json.loads(content)


def dumps_json(doc: Any) -> str:
    """Dump document to JSON representation as string"""
    if isinstance(doc, pydantic.BaseModel):
        return doc.json()
    else:
        return json.dumps(doc)


def dump_json(doc: Any) -> bytes:
    """Dump document to JSON representation as bytes"""
    return dumps_json(doc).encode()


@overload
def read_json(path: Union[str, Path]) -> Any:
    ...


@overload
def read_json(path: Union[str, Path], validator: None) -> Any:
    ...


@overload
def read_json(path: Union[str, Path], validator: Type[ValidatorT]) -> ValidatorT:
    ...


def read_json(
    path: Union[str, Path], validator: Optional[Type[ValidatorT]] = None
) -> Any:
    """Load an object from JSON file"""
    if validator:
        return validator.parse_file(path)
    else:
        return json.loads(
            Path(path).read_bytes().replace(WINDOWS_LINE_ENDING, UNIX_LINE_ENDING)
        )
