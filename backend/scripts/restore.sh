#!/bin/sh
# Restore a scripts/backup.sh file into an EMPTY database (#113).
#
#   SUAS_DATABASE_URL=<empty database> scripts/restore.sh FILE
#
# One transaction, stopping at the first error: a restore that half-applies
# could bring back signatures without the assessments they signed. Restore
# into a new database rather than over a live one, verify it with
# scripts/verify_restore.py, and only then point the planner at it.
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: restore.sh FILE" >&2
    exit 2
fi
if [ -z "${SUAS_DATABASE_URL:-}" ]; then
    echo "restore.sh: set SUAS_DATABASE_URL to the empty database to restore into" >&2
    exit 2
fi
if [ ! -f "$1" ]; then
    echo "restore.sh: no backup file at $1" >&2
    exit 2
fi

exec pg_restore --exit-on-error --single-transaction --no-owner --no-privileges \
    --dbname="$(echo "${SUAS_DATABASE_URL}" | sed 's|^postgresql+psycopg://|postgresql://|')" "$1"
