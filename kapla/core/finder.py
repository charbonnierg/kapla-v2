from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Optional, Tuple, Union


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


def find_files(
    pattern: Union[str, Tuple[str, ...]], start: Union[None, str, Path] = None
) -> Iterator[Path]:
    """Use a glob pattern to find files from start directory"""
    current = Path(start).resolve(True) if start else Path.cwd()
    if isinstance(pattern, str):
        pattern = (pattern,)
    for _pattern in pattern:
        for path in current.glob(_pattern):
            yield path
