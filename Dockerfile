FROM python:3.12.16-slim-trixie

# curl is used by HEALTHCHECK; ffmpeg makes video thumbnails for the Photos tab.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# Dependencies at the exact, hash-checked versions in uv.lock (exported to
# dist/requirements.txt by `make build`), then the locally-built wheel itself.
COPY dist/requirements.txt dist/*.whl /tmp/
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
 && pip install --no-cache-dir --no-deps /tmp/*.whl \
 && rm /tmp/*.whl /tmp/requirements.txt

# Install entrypoint with execute bit BEFORE switching to non-root user.
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Non-root user. /data = durable state, /downloads = photo library,
# /cache = disposable index/thumbnails (put it on the big disk).
RUN useradd -m -u 1000 appuser \
 && mkdir -p /data /downloads /cache \
 && chown -R appuser:appuser /data /downloads /cache

USER appuser
WORKDIR /home/appuser

VOLUME ["/data", "/downloads", "/cache"]

EXPOSE 5000

ENV HOST=0.0.0.0 \
    PORT=5000 \
    DATA_DIR=/data \
    CACHE_DIR=/cache


HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/auth/status" >/dev/null || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
