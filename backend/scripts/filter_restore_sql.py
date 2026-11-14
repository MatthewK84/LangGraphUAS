#!/usr/bin/env python3
"""Drop session SETs that Postgres 16 does not recognize from restore SQL.

pg_dump 17+ writes ``SET transaction_timeout = 0;``. Postgres 16, which this
project runs in Compose and CI, rejects that parameter. Lines inside a COPY
block are data and are left alone.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Iterator

# Parameters added after Postgres 16. Extend this set when a newer pg_dump
# introduces another session SET that 16 rejects.
_UNSUPPORTED_SET = re.compile(r"^SET\s+transaction_timeout\s*=", re.IGNORECASE)
_COPY_START = re.compile(r"^COPY\s+.+\s+FROM\s+stdin;\s*$", re.IGNORECASE)
_COPY_END = "\\.\n"


def filter_restore_sql(lines: Iterable[str]) -> Iterator[str]:
    """Yield SQL lines, omitting unsupported session SETs outside COPY data."""
    in_copy = False
    for line in lines:
        if in_copy:
            if line == _COPY_END or line == "\\.":
                in_copy = False
            yield line
            continue
        if _COPY_START.match(line):
            in_copy = True
            yield line
            continue
        if _UNSUPPORTED_SET.match(line):
            continue
        yield line


def main() -> int:
    """Filter stdin to stdout."""
    sys.stdout.writelines(filter_restore_sql(sys.stdin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
