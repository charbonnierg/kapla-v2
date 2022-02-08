class PyprojectNotFoundError(FileNotFoundError):
    """No pyproject.toml were found in current directory or parent directories"""

    pass


class WorkspaceDoesNotExistError(KeyError):
    """Workspace does not exist"""
