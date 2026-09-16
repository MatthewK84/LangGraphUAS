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

set -eu

alembic upgrade head

exec uvicorn suas.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}"
