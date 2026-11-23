# Build context: repository root
FROM python:3.14-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    STITCHCRAFT_DATA=/app/data STITCHCRAFT_CACHE=/cache PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/mcp/pyproject.toml services/mcp/pyproject.toml
RUN mkdir -p packages/core/src/stitchcraft_core services/api/src/stitchcraft_api \
    services/mcp/src/stitchcraft_mcp \
 && uv sync --frozen --no-dev --no-install-workspace --package stitchcraft-mcp
COPY data data
COPY packages/core packages/core
COPY services/api services/api
COPY services/mcp services/mcp
RUN uv sync --frozen --no-dev --package stitchcraft-mcp
EXPOSE 8000 8765
VOLUME /cache
CMD ["uvicorn", "stitchcraft_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
