# `kapla` project manager

`kapla-cli` is a packaging and build system for Python codebases. It can be used to develop several python packages in a single repository, and easily manage shared dependencies accross the packages.

It relies on:
  - venv
  - pip
  - poetry
  - poetry-core @ master (pushed package from master branch as `quara-poetry-core-next` on 2022/03/03)

## `poetry` and `pip` usage

`poetry` is used in order to manage packages dependencies:

- A pyproject.toml must exist at the root of the monorepo.
- This pyproject.toml file use dependency groups to keep track of each package dependencies.
- A single lock file is thus used to pin dependency versions accross all packages. 
    It avoids resolving dependency lock for each package, and shorten time required to update dependencies accross all packages.
- Each package in the monorepo must have a valid `project.yml` file.
- `project.yml` files are written according to a well known schema  (`KProjectSpec`).
- At build or install time, `pyproject.toml` files are generated in each package directory from both the content of `project.yml` and the monorepo `pyproject.toml` file.
- Packages are either built using `poetry build`.
- Or installed using `pip install -e /path/to/package` (aka *editable install*). (See [PEP 660 -- Editable installs for pyproject.toml based builds](https://www.python.org/dev/peps/pep-0660/))

> Packages are **not installed using Poetry**. Instead, `pip` is used to install packages in editable mode. This is possible using the master branch of `poetry-core` (not released yet)  which supports PEP 660 as `build system` for the editable install.

## Why `poetry` ?

Poetry is really powerful when it comes to declaring and resolving dependencies in a consistent manner. Without it, it would be difficult to ensure that all dependencies versions are compatible together.

## Why `pip` and `editable` install ?

Even though `poetry` provides an install feature out of the box, things can become quite slow when working with dozens of project.

Moreover, `poetry` provide some support for local dependencies, the experience is far from optimal.

By using `pip` to install packages, it's possible to install several local dependencies in parallel without messing with `.venv/lib/pythonX.X/site-packages/` directory.

# Quick Start

## Virtual environment

- Ensure a virtual environment exists at the root of a monorepo:

```bash
k venv
```

- Update pip toolkit within a virtual environment

```bash
k venv update
```

- Run a command within the virtual environment

```bash
k run python -c "import sys; print(sys.executable)"
```

## Global actions

- Install all projects:

```bash
k install
```

- Install only two projects (and their dependencies)

```bash
k install pkg1 pkg2
```

- Build all projects

```bash
k build
```

- Build only two projects

```bash
k build pkg1 pkg2
```

## Projects actions

- Add a project dependency (run the command from the package directory)

```bash
k project add package@version  # @version is optional
```

- Install the current project

```bash
k project install
```

- Show project dependencies

```bash
k project show [--latest] [--outdated] [--tree]
```

