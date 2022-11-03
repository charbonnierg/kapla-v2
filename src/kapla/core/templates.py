import typing as t
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def render_template(
    source: t.Union[str, Path], destination: t.Union[str, Path], **kwargs: t.Any
) -> Path:
    """Render template from source into destination using provided keyword arguments"""
    filepath = Path(source)
    parent = filepath.parent
    loader = FileSystemLoader(searchpath=parent)
    env = Environment(loader=loader)
    template = env.get_template(filepath.name)
    content = template.render(**kwargs)
    output = Path(destination)
    output.write_text(content)
    return output
