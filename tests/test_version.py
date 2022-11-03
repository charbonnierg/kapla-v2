"""FIXME: Add unit tests"""
from subprocess import check_output

from kapla import __version__


def test_version() -> None:
    assert check_output(["k", "--version"], encoding="utf-8").strip() == __version__
