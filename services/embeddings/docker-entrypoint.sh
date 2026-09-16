#!/bin/sh
# Container entrypoint: serve the embedding model.
#
# Mirrors backend/scripts/docker-entrypoint.sh, and for the same reason. The
# planner reaches this service over Railway's private network, which is
# IPv6-only: bound to 0.0.0.0 this listens on IPv4 alone, the planner's
# <name>.railway.internal lookup returns an AAAA record with nothing behind it,
# and the connection is refused. Retrieval then falls back to the hashing
# embedder -- quietly, because a fallback is a supported state. A silent drop in
# recall is worse than a loud failure, so bind the stack the platform uses.
#
# Detected rather than hardcoded: binding :: where the kernel has no IPv6 fails
# outright, and Docker disables IPv6 in containers by default.

set -eu

if [ -z "${HOST:-}" ]; then
    if [ -e /proc/net/if_inet6 ]; then
        HOST="::"
    else
        HOST="0.0.0.0"
    fi
fi

exec uvicorn app:app --host "${HOST}" --port "${PORT:-8080}"
