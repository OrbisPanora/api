FROM python:3.14-slim

RUN pip install --no-cache-dir uv==0.12.10

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so this layer is cached when only the source changes.
COPY pyproject.toml uv.lock .python-version ./
COPY orbispanora_lib-1.0.0-py3-none-any.whl ./
RUN uv sync --locked --no-install-project

COPY README.md .env ./
COPY orbispanora_api ./orbispanora_api
RUN uv sync --locked

EXPOSE 8000

CMD ["orbispanora", "run", "--host", "0.0.0.0", "--port", "8000", "--root-path", "/kubernetes/iut-inf63-projets-etudiants-orbispanora/orbispanora-api"]
