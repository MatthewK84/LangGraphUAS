#!/bin/sh
# Container entrypoint: migrate, then serve.
#
# This exists because the image's CMD is what actually runs in production. A
# start command configured outside the image (railway.json, a dashboard field,
# a compose override) is easy to believe in and easy to have silently not
# applied -- and when it does not apply, migrations never run and the server
# binds a port nothing is routing to. Both failures look like "502" and neither
# names its cause. Putting both in the image means every path that starts this
# container gets them.
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

alembic upgrade head

exec uvicorn suas.main:app \
    --host "${HOST}" \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}"
