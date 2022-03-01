from kapla.core.io import dumps_toml
from kapla.core.projects import KProject

if __name__ == "__main__":
    project = KProject("project.yml")
    print(
        dumps_toml(project.get_pyproject_spec().dict(exclude_unset=True, by_alias=True))
    )
