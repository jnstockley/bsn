FROM python:3.13.6-alpine

ARG VERSION=0.0.0.dev

COPY . /app

RUN adduser -S app && \
    chown -R app /app
USER app

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN sed -i "s/^version = .*/version = \"${VERSION}\"/" /app/pyproject.toml

RUN uv sync --frozen --no-cache

ENV PATH=/app/.venv/bin:$PATH
ENV PYTHONPATH=src:$PYTHONPATH

ENTRYPOINT ["uv", "run", "src/main.py"]
