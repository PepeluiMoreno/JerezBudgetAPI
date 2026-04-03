# ── build stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.4 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

RUN pip install poetry==$POETRY_VERSION

WORKDIR /app
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root --without dev

# ── runtime stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Dependencias del sistema necesarias para pdfplumber y lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . .

# Alembic upgrade al arrancar (idempotente)
# El CMD real se sobreescribe en docker-compose
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
