from __future__ import annotations

import sys
from argparse import ArgumentParser, _SubParsersAction
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from anyio import run

from kapla.core.errors import CommandFailedError
from kapla.core.logger import logger
from kapla.projects.krepo import KRepo
from kapla.specs.kproject import KProjectSpec


def set_write_parser(parser: ArgumentParser) -> None:
    parser.add_argument("--lock", "-l", action="store_true", default=True)
    parser.add_argument("--path", required=False, default=None)


def set_build_parser(parser: ArgumentParser) -> None:
    parser.add_argument("--lock", "-l", action="store_true", default=True)
    parser.add_argument(
        "--no-clean", action="store_true", default=False, dest="no_clean"
    )


def set_new_parser(parser: ArgumentParser) -> None:
    parser.add_argument("package_name", default=None)


def set_install_parser(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--with",
        "--include",
        dest="include_groups",
        nargs="+",
    )
    parser.add_argument(
        "--without",
        "--exclude",
        dest="exclude_groups",
        nargs="+",
    )
    parser.add_argument("-o", "--only", action="append", dest="only_groups", nargs="+")
    parser.add_argument(
        "-d", "--default", action="store_true", default=False, dest="default"
    )
    parser.add_argument(
        "--no-clean", action="store_true", default=False, dest="no_clean"
    )
    parser.add_argument("--lock", "-l", action="store_true", default=False)


def add_remove_parser(parser: ArgumentParser) -> None:
    parser.add_argument("package")
    parser.add_argument("-g", "--group", required=False, default=None, dest="group")
    parser.add_argument("--dry-run", action="store_true", default=False)


def set_add_parser(parser: ArgumentParser) -> None:
    parser.add_argument("package")
    parser.add_argument("-g", "--group", required=False, default=None, dest="group")
    parser.add_argument(
        "-e", "--editable", action="store_true", default=False, dest="editable"
    )
    parser.add_argument(
        "-o", "--optional", action="store_true", default=False, dest="optional"
    )
    parser.add_argument("-p", "--python", required=False, default=None, dest="python")
    parser.add_argument("--extras", nargs="+", dest="extras")
    parser.add_argument("--platform", nargs="+", dest="platform")
    parser.add_argument("-s", "--source", required=False, default=None, dest="source")
    parser.add_argument(
        "-a",
        "--allow-prereleases",
        action="store_true",
        default=False,
        dest="allow_prereleases",
    )
    parser.add_argument("--dry-run", action="store_true", default=False)


def set_docker_parser(parser: ArgumentParser) -> None:
    parser.add_argument("--tag", required=False, default=None)
    parser.add_argument("--load", action="store_true", default=False)
    parser.add_argument("--push", action="store_true", default=False)
    parser.add_argument("--output-dir", "-o", required=False, default=None)
    parser.add_argument("--no-build-dist", action="store_true", default=False)
    parser.add_argument("--build-arg", nargs="+", action="append", dest="build_arg")
    parser.add_argument("--platform", nargs="+", action="append", dest="platform")
    parser.add_argument(
        "--lock",
        "-l",
        help="Lock packages version. Ignored when --no-build-dist is used",
        action="store_true",
        default=True,
    )


def set_project_parser(
    parser: _SubParsersAction[ArgumentParser], parent: ArgumentParser
) -> None:
    project_parser = parser.add_parser("project", description="project projects")
    project_actions_subparser = project_parser.add_subparsers(
        title="project", dest="action"
    )

    write_parser = project_actions_subparser.add_parser("write", parents=[parent])
    set_write_parser(write_parser)

    build_parser = project_actions_subparser.add_parser("build", parents=[parent])
    set_build_parser(build_parser)

    install_parser = project_actions_subparser.add_parser("install", parents=[parent])
    set_install_parser(install_parser)

    add_parser = project_actions_subparser.add_parser("add", parents=[parent])
    set_add_parser(add_parser)

    remove_parser = project_actions_subparser.add_parser("remove", parents=[parent])
    set_add_parser(remove_parser)

    new_parser = project_actions_subparser.add_parser("new", parents=[parent])
    set_new_parser(new_parser)

    docker_parser = project_actions_subparser.add_parser("docker", parents=[parent])
    set_docker_parser(docker_parser)


def do_build_docker(args: Any) -> None:
    tag: Optional[str] = args.tag
    load: bool = args.load
    push: bool = args.push
    output_dir: Optional[str] = args.output_dir
    no_build_dist: bool = args.no_build_dist
    build_args: List[List[str]] = args.build_arg
    platforms: List[List[str]] = args.platform
    lock_versions: bool = args.lock

    parsed_build_args: Dict[str, str] = {}
    for build_arg in build_args or []:
        key, value = build_arg[0].split("=")
        parsed_build_args[key] = value

    parsed_platforms: List[str] = []
    for platform in platforms or []:
        parsed_platforms.append(platform[0])

    repo = KRepo.find_current()
    project = repo.find_current_project()
    docker_func = partial(
        project.build_docker,
        tag=tag,
        load=load,
        push=push,
        build_args=parsed_build_args,
        platforms=parsed_platforms,
        output_dir=output_dir,
        build_dist=False if no_build_dist else True,
        lock_versions=lock_versions,
        raise_on_error=True,
    )

    try:
        run(docker_func)
    except CommandFailedError:
        logger.error("Build failed")
        sys.exit(1)


def do_remove_dependency(args: Any) -> None:
    package: str = args.package
    group: Optional[str] = args.group
    dry_run: bool = args.dry_run

    repo = KRepo.find_current()
    project = repo.find_current_project()

    remove_func = partial(
        project.remove_dependency,
        package=package,
        group=group,
        dry_run=dry_run,
        raise_on_error=True,
    )

    try:
        run(remove_func)
    except CommandFailedError:
        logger.error("Failed to remove dependency")


def do_add_dependency(args: Any) -> None:
    package: str = args.package
    group: Optional[str] = args.group
    editable: bool = args.editable
    extras: Union[Tuple[str], None] = args.extras
    optional: bool = args.optional
    python: Optional[str] = args.python
    platform: Union[Tuple[str], None] = args.platform
    source: Optional[str] = args.source
    allow_prereleases: bool = args.allow_prereleases
    dry_run: bool = args.dry_run

    repo = KRepo.find_current()
    project = repo.find_current_project()

    add_func = partial(
        project.add_dependency,
        package=package,
        group=group,
        editable=editable,
        extras=list(extras) if extras else None,
        optional=optional,
        python=python,
        platform=list(platform) if platform else None,
        source=source,
        allow_prereleases=allow_prereleases,
        dry_run=dry_run,
    )

    try:
        run(add_func)
    except CommandFailedError:
        logger.error("Failed to add dependency")
        sys.exit(1)


def do_write_project(args: Any) -> None:
    # Parse args
    lock_versions: bool = args.lock
    path: str = args.path
    # Find repo
    repo = KRepo.find_current()
    # Find project
    project = repo.find_current_project()
    # Write pyproject
    project.write_pyproject(path, lock_versions=lock_versions)


def do_build_project(args: Any) -> None:
    # Parse arguments
    clean: bool = not args.no_clean
    lock_versions: bool = args.lock
    # Find repo
    repo = KRepo.find_current()
    # Find project
    project = repo.find_current_project()
    # Define function to perform build
    build = partial(
        project.build,
        lock_versions=lock_versions,
        clean=clean,
    )

    # Run build
    try:
        run(build)
    except CommandFailedError:
        logger.error("Failed to build project")
        sys.exit(1)


def do_install_project(args: Any) -> None:
    include_groups: Optional[Tuple[str]] = args.include_groups
    exclude_groups: Optional[Tuple[str]] = args.exclude_groups
    only_groups: Optional[Tuple[str]] = args.only_groups
    default: bool = args.default
    clean: bool = not args.no_clean
    lock_versions: bool = args.lock
    # Find repo
    repo = KRepo.find_current()
    # Find project
    project = repo.find_current_project()
    # Install project with its deps
    install_func = partial(
        repo.install_editable_projects,
        include_projects=[project.name] + project.get_local_dependencies_names(),
        include_groups=include_groups,
        exclude_groups=exclude_groups,
        only_groups=only_groups,
        default=default,
        lock_versions=lock_versions,
        clean=clean,
    )
    try:
        run(install_func)
    except CommandFailedError:
        logger.error("Failed to install package")
        sys.exit(1)


def do_create_new_project(args: Any) -> None:
    package_name: str = args.package_name
    project_name = package_name.replace("_", "-")
    package_name = project_name.replace("-", "_")
    module = package_name.split("quara_")[-1]

    repo = KRepo.find_current()
    version = repo.version
    cur_dir = Path.cwd()
    project_root = cur_dir / project_name

    project_root.mkdir(parents=False, exist_ok=False)

    readme_path = project_root / "README.md"
    readme_path.touch()

    src_root = project_root / "quara"
    src_root.mkdir(parents=False, exist_ok=False)

    test_root = project_root / "tests"
    test_root.mkdir(parents=False, exist_ok=False)

    confest_path = test_root / "conftest.py"
    confest_path.touch()

    pkg_root = src_root / module
    pkg_root.mkdir(parents=False, exist_ok=False)

    init_path = pkg_root / "__init__.py"
    init_path.touch()

    project_path = project_root / "project.yml"

    project_spec = KProjectSpec(  # noqa: F841
        name=project_name, version=version, packages=[{"include": "quara"}]
    )
    # FIXME: Write project file
    project_path.touch()
