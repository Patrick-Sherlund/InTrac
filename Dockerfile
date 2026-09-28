FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS api
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INTRAC_DB_PATH=/data/intrac.db
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home intrac \
    && mkdir /data && chown intrac:intrac /data
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app/ ./app/
USER intrac
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=6 \
    CMD python -c "import http.client; c = http.client.HTTPConnection('127.0.0.1', 8000, timeout=3); c.request('GET', '/api/auth/me'); exit(0 if c.getresponse().status == 401 else 1)"
# Only Caddy can reach this port; it sets the original request scheme and host.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM caddy:2-alpine AS web
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend /build/dist /srv
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=6 \
    CMD wget -q -O /dev/null http://127.0.0.1:8082/healthz || exit 1
