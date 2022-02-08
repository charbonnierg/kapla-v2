from anyio import run
from kapla.cli.repo import Monorepo


def main():
    repo = Monorepo.find()
    run(repo.install)


if __name__ == "__main__":
    main()

