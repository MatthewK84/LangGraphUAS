#!/bin/sh
# Back up the planner's database to one file (#113).
#
#   SUAS_DATABASE_URL=... scripts/backup.sh FILE
#
# One pg_dump of the one database: missions (with each operator's signed
# inputs_hash) and the LangGraph checkpoints (with the sealed assessment it was
# signed against) come from a single snapshot, so they cannot disagree. Restore
# with scripts/restore.sh, then check with scripts/verify_restore.py.
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: backup.sh FILE" >&2
    exit 2
fi
if [ -z "${SUAS_DATABASE_URL:-}" ]; then
    echo "backup.sh: set SUAS_DATABASE_URL to the database to back up" >&2
    exit 2
fi

exec pg_dump --format=custom --no-owner --no-privileges \
    --file="$1" --dbname="$(echo "${SUAS_DATABASE_URL}" | sed 's|^postgresql+psycopg://|postgresql://|')"
