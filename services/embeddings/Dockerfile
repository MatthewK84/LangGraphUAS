# syntax=docker/dockerfile:1

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models \
    EMBEDDING_MODEL_ID=sentence-transformers/all-MiniLM-L6-v2 \
    EMBEDDING_DIMENSION=384

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Bake the weights into the image. Without this the first request after every
# deploy pays a cold download, and a service that is slow exactly when it is
# first used is a service people route around.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

RUN useradd --create-home --uid 10001 embed && chown -R embed /app /models
USER embed

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
    sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health').status==200 else 1)"

COPY --chown=embed docker-entrypoint.sh /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
