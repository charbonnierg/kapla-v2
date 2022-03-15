from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from functools import partial
from pathlib import Path
from typing import Any, Optional, Tuple, Union

from anyio import run

from kapla.projects.krepo import KRepo
from kapla.specs.kproject import KProjectSpec


def set_show_parser(parser: ArgumentParser) -> None:
    parser.add_argument(
        "-g",
        "--group",
        "--with",
        "--include-group",
        dest="include_groups",
        nargs="+",
    )
    parser.add_argument(
        "--without",
        "--exclude-group",
        dest="exclude_groups",
        nargs="+",
    )
    parser.add_argument(
        "--only", "--only-group", action="append", dest="only_groups", nargs="+"
    )
    parser.add_argument(
        "--outdated", action="store_true", default=False, dest="outdated"
    )
    parser.add_argument("--tree", action="store_true", default=False, dest="tree")
    parser.add_argument(
        "--latest",
        action="store_true",
        default=False,
        dest="latest",
    )
    parser.add_argument("--default", action="store_true", default=False, dest="default")


def set_write_parser(parser: ArgumentParser) -> None:
    parser.add_argument("--develop", "-e", action="store_true", default=False)
    parser.add_argument("--path", required=False, default=None)


def set_build_parser(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--no-clean", action="store_true", default=False, dest="no_clean"
    )


def set_new_parser(parser: ArgumentParser) -> None:
    parser.add_argument("package_name", default=None)


def set_install_parser(parser: ArgumentParser) -> None:
    parser.add_argument(
        "-g",
        "--group",
        "--with",
        "--include-group",
        dest="include_groups",
        nargs="+",
    )
    parser.add_argument(
        "--without",
        "--exclude-group",
        dest="exclude_groups",
        nargs="+",
    )
    parser.add_argument(
        "-o", "--only", "--only-group", action="append", dest="only_groups", nargs="+"
    )
    parser.add_argument(
        "-d", "--default", action="store_true", default=False, dest="default"
    )
    parser.add_argument(
        "--no-clean", action="store_true", default=False, dest="no_clean"
    )


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


def set_project_parser(
    parser: _SubParsersAction[ArgumentParser], parent: ArgumentParser
) -> None:
    project_parser = parser.add_parser("project", description="project projects")
    project_actions_subparser = project_parser.add_subparsers(
        title="project", dest="action"
    )

    show_parser = project_actions_subparser.add_parser("show", parents=[parent])
    set_show_parser(show_parser)

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

    repo = KRepo.find_current()
    project = repo.find_current_project()

    docker_func = partial(
        project.build_docker,
        tag=tag,
        load=load,
        push=push,
        output_dir=output_dir,
        build_dist=False if no_build_dist else True,
    )

    run(docker_func)


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
    )

    run(remove_func)


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

    run(add_func)


def do_show_dependencies(args: Any) -> None:
    # Parse args
    include_groups: Optional[Tuple[str]] = args.include_groups
    exclude_groups: Optional[Tuple[str]] = args.exclude_groups
    only_groups: Optional[Tuple[str]] = args.only_groups
    default: bool = args.default
    tree: bool = args.tree
    latest: bool = args.latest
    outdated: bool = args.outdated
    # Find repo
    repo = KRepo.find_current()
    # Find project
    project = repo.find_current_project()
    # Create func
    show_func = partial(
        project.show,
        include_groups=include_groups,
        exclude_groups=exclude_groups,
        only_groups=only_groups,
        default=default,
        tree=tree,
        latest=latest,
        outdated=outdated,
    )
    # Update project
    run(show_func)


def do_write_project(args: Any) -> None:
    # Parse args
    develop: bool = args.develop
    path: str = args.path
    # Find repo
    repo = KRepo.find_current()
    # Find project
    project = repo.find_current_project()
    # Write pyproject
    project.write_pyproject(path, develop=develop)


def do_build_project(args: Any) -> None:
    # Parse arguments
    clean: bool = not args.no_clean

    # Find repo
    repo = KRepo.find_current()
    # Find project
    project = repo.find_current_project()
    # Define function to perform build
    build = partial(
        project.build,
        clean=clean,
    )

    # Run build
    run(build)


def do_install_project(args: Any) -> None:
    include_groups: Optional[Tuple[str]] = args.include_groups
    exclude_groups: Optional[Tuple[str]] = args.exclude_groups
    only_groups: Optional[Tuple[str]] = args.only_groups
    default: bool = args.default
    clean: bool = not args.no_clean
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
        clean=clean,
    )
    run(install_func)


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
