FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-prod.txt .
RUN pip install --prefix=/install -r requirements-prod.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    PORT=8000
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY . .
RUN useradd --no-create-home --shell /bin/false nexivo && \
    mkdir -p /app/staticfiles /app/media && \
    chown -R nexivo:nexivo /app
USER nexivo
RUN python manage.py collectstatic --noinput 2>&1 || true
EXPOSE 8000
CMD ["sh", "-c", \
    "python manage.py migrate --noinput && \
     python manage.py create_superadmin && \
     gunicorn config.wsgi:application \
       --bind 0.0.0.0:${PORT} \
       --workers ${WEB_CONCURRENCY:-2} \
       --timeout=60 \
       --access-logfile=- \
       --error-logfile=- \
       --log-level=info"]