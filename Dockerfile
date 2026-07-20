# ── Stage 1: Build dependencies ───────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --prefix=/install -r requirements-prod.txt

# ── Stage 2: Runtime image ────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    PORT=8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Create non-root user for security
RUN useradd --no-create-home --shell /bin/false nexivo && \
    mkdir -p /app/staticfiles /app/media && \
    chown -R nexivo:nexivo /app

USER nexivo

# Collect static files (no DB needed at build time)
RUN python manage.py collectstatic --noinput 2>&1 || true

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/events/ || exit 1

CMD ["sh", "-c", \
    "python manage.py migrate --noinput && \
     gunicorn config.wsgi:application \
       --bind 0.0.0.0:${PORT} \
       --workers ${WEB_CONCURRENCY:-3} \
       --worker-class=sync \
       --worker-connections=1000 \
       --timeout=60 \
       --max-requests=1000 \
       --max-requests-jitter=50 \
       --access-logfile=- \
       --error-logfile=- \
       --log-level=info"]
