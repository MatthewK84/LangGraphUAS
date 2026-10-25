"""Print the backend files the report-only mutation job should mutate.

On a pull request the job passes the paths the PR changed (``--changed``), and
this keeps the Python modules under ``backend/suas`` that still exist. With no
change list, as on a push to ``main``, it prints the safety core: the
calculators, the seal, and the ingest screener. A pull request that edits this
selector also gets the safety core, so the change that alters the job is the
one that shows it still runs.

Paths are printed relative to ``backend/``, one per line, sorted.
"""

import argparse
from collections.abc import Iterable
from pathlib import Path

_PREFIX = "backend/"
_SELF = "backend/scripts/mutation_targets.py"
_SAFETY_FILES = ("suas/graph/seal.py", "suas/rag/screening.py")


def _is_module(relative: str) -> bool:
    return (
        relative.startswith("suas/")
        and relative.endswith(".py")
        and not relative.endswith("__init__.py")
    )


def safety_core(backend: Path) -> list[str]:
    """Return the calculators, the seal, and the screener, relative to ``backend``."""
    calculators = sorted(
        path.relative_to(backend).as_posix()
        for path in (backend / "suas" / "calculations").glob("*.py")
    )
    return [path for path in calculators if _is_module(path)] + list(_SAFETY_FILES)


def select(changed: Iterable[str], backend: Path) -> list[str]:
    """Return the existing ``suas`` modules among ``changed``, relative to ``backend``."""
    paths = [path.strip() for path in changed]
    if _SELF in paths:
        return safety_core(backend)
    chosen = {
        path.removeprefix(_PREFIX)
        for path in paths
        if path.startswith(_PREFIX) and _is_module(path.removeprefix(_PREFIX))
    }
    return sorted(path for path in chosen if (backend / path).is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--changed", type=Path, help="File listing changed paths, one per line.")
    args = parser.parse_args(argv)
    backend = Path(__file__).resolve().parent.parent
    if args.changed is None:
        chosen = safety_core(backend)
    else:
        chosen = select(args.changed.read_text(encoding="utf-8").splitlines(), backend)
    for path in chosen:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
