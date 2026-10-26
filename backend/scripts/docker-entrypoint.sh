#!/bin/sh
# Container entrypoint: serve; migrate only when told to (#87).
#
#   docker-entrypoint.sh            serve (no schema change)
#   docker-entrypoint.sh migrate    alembic upgrade head, then exit
#   docker-entrypoint.sh CMD ...    run CMD instead (one-off or pre-deploy)
#   MIGRATE_ON_START=true           upgrade head, then serve (single replica)
#
# Migrating is a deploy step, not a side effect of a restart: an image that
# upgraded on every start undid a rollback the next time it restarted, and N
# replicas starting together ran N upgrades at once. Compose runs a one-shot
# `migrate` service first; Railway runs a pre-deploy command.
#
# The server command lives in the image because the image's CMD is what
# actually runs in production. A start command configured outside the image (a
# dashboard field, a compose override) is easy to believe in and easy to have
# silently not applied, and the server then binds a port nothing routes to.
#
# PORT is supplied by the platform (Railway injects it); 8000 is the local
# default. WEB_CONCURRENCY mirrors the name gunicorn and uvicorn already use.
#
# HOST defaults to :: rather than 0.0.0.0 because Railway's private network is
# IPv6-only. A service bound to 0.0.0.0 listens on IPv4 alone, so a sibling
# service resolving <name>.railway.internal gets an AAAA record with nothing
# behind it: the connection is refused, and the caller reports a 502 that looks
# like the backend being down rather than unreachable. On Linux a :: socket also
# accepts IPv4-mapped connections (net.ipv6.bindv6only=0 is the default), so
# this keeps public ingress and local docker-compose working unchanged. HOST is
# overridable, and detected rather than assumed: binding :: on a host without
# IPv6 does not degrade, it fails outright, and Docker disables IPv6 in
# containers by default -- so a hardcoded :: would trade a broken Railway
# deployment for a broken docker-compose one.

set -eu

if [ -z "${HOST:-}" ]; then
    if [ -e /proc/net/if_inet6 ]; then
        HOST="::"
    else
        HOST="0.0.0.0"
    fi
fi

case "${1:-}" in
    migrate)
        exec alembic upgrade head
        ;;
    "")
        ;;
    *)
        exec "$@"
        ;;
esac

if [ "${MIGRATE_ON_START:-false}" = "true" ]; then
    alembic upgrade head
fi

# --no-proxy-headers: uvicorn otherwise believes X-Forwarded-For from 127.0.0.1
# and overwrites the peer address with it. SUAS_TRUSTED_PROXIES is the one
# place that decides whose forwarding header counts (rotation overlap).

exec uvicorn suas.main:app \
    --host "${HOST}" \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --no-proxy-headers
