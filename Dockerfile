# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.11.33 AS uv

FROM python:3.12.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --system ambient \
    && useradd --system --gid ambient --home-dir /app --shell /usr/sbin/nologin ambient

WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable \
    && chown -R ambient:ambient /app

USER ambient
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "ambient_ha.healthcheck"]

CMD ["ambient-ha-mcp"]

