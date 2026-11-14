#!/bin/sh
# Restore a scripts/backup.sh file into an EMPTY database (#113).
#
#   SUAS_DATABASE_URL=<empty database> scripts/restore.sh FILE
#
# One transaction, stopping at the first error: a restore that half-applies
# could bring back signatures without the assessments they signed. Restore
# into a new database rather than over a live one, verify it with
# scripts/verify_restore.py, and only then point the planner at it.
#
# Dumps taken with pg_dump 17+ include SET transaction_timeout, which
# Postgres 16 rejects. The SQL is filtered before it is applied so those
# dumps still restore onto 16, the version Compose and CI run.
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

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DBURL=$(echo "${SUAS_DATABASE_URL}" | sed 's|^postgresql+psycopg://|postgresql://|')
RAW=$(mktemp)
FILTERED=$(mktemp)
trap 'rm -f "$RAW" "$FILTERED"' EXIT

pg_restore --no-owner --no-privileges --file="$RAW" "$1"
python3 "$SCRIPT_DIR/filter_restore_sql.py" < "$RAW" > "$FILTERED"
psql --quiet --single-transaction --set ON_ERROR_STOP=on --dbname="$DBURL" --file="$FILTERED"
