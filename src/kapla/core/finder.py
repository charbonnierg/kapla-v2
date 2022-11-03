from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import AsyncIterator, Iterable, Iterator, Optional, Pattern, Tuple, Union

from kapla.wrappers.git import get_files

DEFAULT_GITIGNORE = [
    "__pycache__/",
    "**/.ipynb_checkpoints",
    "build/",
    "develop-eggs/",
    "dist/",
    "downloads/",
    "eggs/",
    ".eggs/",
    "lib/",
    "lib64/",
    "parts/",
    "sdist/",
    "var/",
    "wheels/",
    "share/python-wheels/",
    "*.egg-info/",
    "htmlcov/",
    ".tox/",
    ".nox/",
    ".coverage",
    ".coverage.*",
    ".cache",
    "*.cover",
    "*.py,cover",
    ".hypothesis/",
    ".pytest_cache/",
    "cover/",
    "instance/",
    ".webassets-cache",
    ".scrapy",
    "docs/_build/",
    ".pybuilder/",
    "target/",
    "profile_default/",
    "__pypackages__/",
    ".env",
    ".venv",
    "venv",
    "ENV",
    "env.bak",
    "venv.bak",
    ".spyderproject",
    ".spyproject",
    ".ropeproject",
    "/site",
    ".mypy_cache/",
    ".pyre/",
    ".pytype/",
    "cython_debug/",
    ".ipynb_checkpoints",
]


def get_patterns(
    pattern: Union[str, Iterable[str]],
    ignore: Union[str, Iterable[str], None] = None,
) -> Tuple[Pattern[str], Optional[Pattern[str]]]:
    """Get patterns to filter filenames"""
    if isinstance(pattern, str):
        pattern = [pattern]
    if isinstance(ignore, str):
        ignore = [ignore]

    ignore_re: Optional[Pattern[str]] = None

    if ignore:
        ignore_iterable = set(
            [dirname[:-1] for dirname in ignore if dirname.endswith("/")] + list(ignore)
        )
        ignore_expr = "|".join([fnmatch.translate(p) for p in ignore_iterable])
        ignore_re = re.compile(ignore_expr)

    pattern_expr = "|".join(fnmatch.translate(p) for p in pattern)
    pattern_re = re.compile(pattern_expr)

    return pattern_re, ignore_re


def check_exclude(path: Path, pattern: Optional[Pattern[str]] = None) -> bool:
    """Check if a file or directory should be excluded"""
    if pattern is None:
        return False
    if pattern.match(path.name):
        return True
    if pattern.match(path.as_posix()):
        return True
    return False


def find_files(
    pattern: Union[str, Iterable[str]],
    root: Union[Path, str, None] = None,
    ignore: Union[str, Iterable[str]] = [],
) -> Iterator[Path]:
    """Find files recursively."""

    root = Path(root).resolve(True) if root else Path.cwd().resolve(True)

    pattern_re, ignore_re = get_patterns(pattern, ignore)

    for current_dir, child_dirs, current_files in os.walk(root):

        current_path = root / current_dir

        if check_exclude(current_path, ignore_re):
            child_dirs.clear()
            continue

        keep_child_dirs = [
            dirname
            for dirname in child_dirs
            if not check_exclude(current_path / dirname, ignore_re)
        ]
        excluded_dirs = set(child_dirs).difference(keep_child_dirs)

        for dirname in excluded_dirs:
            child_dirs.remove(dirname)

        for file in current_files:
            if pattern_re.match(file):
                yield current_path / file


async def find_git_files(
    pattern: Union[str, Iterable[str], None] = None,
    root: Union[Path, str, None] = None,
) -> AsyncIterator[Path]:
    """Find files tracked by git"""
    files = await get_files(root)
    root = Path(root).resolve(True) if root else Path.cwd().resolve(True)

    if pattern:
        pattern_re, _ = get_patterns(pattern)
        for file in files:
            if pattern_re.match(file):
                yield root / file
    else:
        for file in files:
            yield root / file


def find_dirs(
    pattern: Union[str, Iterable[str]],
    root: Union[Path, str, None] = None,
    ignore: Union[str, Iterable[str]] = [],
) -> Iterator[Path]:
    """Find directories recursively."""

    root = Path(root).resolve(True) if root else Path.cwd().resolve(True)

    pattern_re, ignore_re = get_patterns(pattern, ignore)

    for current_dir, child_dirs, current_files in os.walk(root):

        current_path = root / current_dir

        if check_exclude(current_path, ignore_re):
            child_dirs.clear()
            continue

        for dirname in child_dirs:

            if check_exclude(current_path / dirname, ignore_re):
                continue

            if pattern_re.match(dirname):
                yield current_path / dirname


def find_files_using_gitignore(
    pattern: Union[str, Iterable[str]] = "*",
    root: Union[Path, str, None] = None,
    gitignore: Union[Path, str, None] = None,
) -> Iterator[Path]:
    """Find find recursively. Use gitignore to filter directories"""

    if gitignore is None:
        lines = DEFAULT_GITIGNORE
    else:
        lines = [
            line
            for line in Path(gitignore).read_text().splitlines(False)
            if line and not line.startswith("#")
        ]

    return find_files(pattern, root, lines)


def find_dirs_using_gitignore(
    pattern: Union[str, Iterable[str]] = "*",
    root: Union[Path, str, None] = None,
    gitignore: Union[Path, str, None] = None,
) -> Iterator[Path]:
    """Find directories recursively. Use gitignore to filter directories.

    If not path is provided for gitinogre argument, default values are used
    """

    if gitignore is None:
        lines = DEFAULT_GITIGNORE
    else:
        lines = [
            line
            for line in Path(gitignore).read_text().splitlines(False)
            if line and not line.startswith("#")
        ]

    return find_dirs(pattern, root, lines)


def lookup_file(
    filename: Union[str, Tuple[str, ...]],
    start: Union[None, str, Path] = None,
    max_dir: Optional[int] = None,
) -> Optional[Path]:
    """
    Find a file located in current or parent directory by its name.

    NOTE: In this project, this function is mainly used to look for pyproject.toml files.
    """
    # The directory where file will be searched at initialization
    current = Path(start).resolve(True) if start else Path.cwd()
    current_idx = 0
    # Make sure filename is a tuple
    if isinstance(filename, str):
        filename = (filename,)
    # Enter an infinite loop
    while True:
        # Exit the loop if we already looked into maximum number of directories
        if max_dir and current_idx > max_dir:
            return None
        # List content of current directory
        files_list = os.listdir(current)
        # Get parent directory
        parent = current.parent
        # Make sure filename is a tuple
        for name in filename:
            # Check if file exists in the directory
            if name in files_list:
                return current / name
            else:
                # The root directory of a filesystem is its own parent
                if current == parent:
                    # When we're at the root (I.E, / or C:/) and we did not find the file, it means the file does not exist
                    return None
                else:
                    # Set parent directory as current directory
                    current = parent
                    # Increment directory index and reenter the while loop
                    current_idx += 1
