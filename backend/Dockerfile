# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Install dependencies first (layer caching).
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install .

# Run as an unprivileged user in production.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
# Default: run the API. Compose overrides commands for worker/beat/migrate.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
