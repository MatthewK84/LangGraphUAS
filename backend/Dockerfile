# syntax=docker/dockerfile:1

# Build context is the REPOSITORY ROOT, not backend/. Every COPY source below is
# prefixed accordingly, and .dockerignore at the root keeps the context small.
#
# This is not a style choice. Railway resolves `dockerfilePath` relative to the
# service's Root Directory; with that left empty, `backend/Dockerfile` resolves
# and the context is the repo root. A backend/-relative COPY then fails on a file
# that is plainly committed, which reads as a missing file and is not one.
# `COPY scripts ./scripts` was the quiet one: the repo root has its own scripts/,
# so that line would have succeeded and shipped the wrong directory.
#
# Keep CI (.github/workflows/ci.yml), docker-compose.yml and railway.json using
# the root as context. If you ever move to a backend/ context, every path here
# changes with it.

# ---- Builder: install dependencies into a virtual environment ----
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY backend/pyproject.toml ./
COPY backend/suas ./suas
RUN pip install --upgrade pip && pip install .

# ---- Runtime: copy the venv and app, run as a non-root user ----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}" \
    LANGGRAPH_STRICT_MSGPACK=true

RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app backend/suas ./suas
COPY --chown=app:app backend/alembic ./alembic
COPY --chown=app:app backend/alembic.ini ./alembic.ini
COPY --chown=app:app backend/scripts ./scripts

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "suas.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
