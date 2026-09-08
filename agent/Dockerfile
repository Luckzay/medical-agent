FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_HTTP_TIMEOUT=300 \
    UV_HTTP_RETRIES=5 \
    AGENT_DATABASE_PATH=/app/data/agent_runs.db \
    AGENT_CHECKPOINT_PATH=/app/data/checkpoints.db \
    AGENT_EVIDENCE_SOURCE_PATH=/app/resources/literature/TCM_Supramolecular_Literature_Search_EN_v3_filled.xlsx \
    AGENT_EVIDENCE_DATABASE_PATH=/app/data/evidence.db

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --extra rdkit --extra embedding

COPY app ./app
COPY resources ./resources
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
