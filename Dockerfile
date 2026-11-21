# The base image is pinned by digest; Dependabot proposes new digests.
ARG PYTHON_IMAGE=python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

# Build stage: git is needed to fetch orbispanora-lib from GitHub. It is not copied
# into the final image.
FROM ${PYTHON_IMAGE} AS build

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.12.10

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

WORKDIR /app

# Dependencies first, so this layer is cached when only the source changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project

COPY README.md LICENSE .env ./
COPY orbispanora_api ./orbispanora_api
RUN uv sync --locked

# Final stage: the virtual environment and the source, run by an unprivileged user.
FROM ${PYTHON_IMAGE}

# zlib1g: the Debian security update is newer than the base image, which Trivy reports
# (CVE-2026-85091). pip is not used at run time, and its vendored msgpack and urllib3 were
# flagged too, so it is removed.
RUN apt-get update \
    && apt-get install --no-install-recommends --only-upgrade -y zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip \
    && useradd --system --uid 10001 --no-create-home --home-dir /nonexistent orbispanora \
    && mkdir /data \
    && chown orbispanora /data

# The user has no home directory, so every setting whose default is under it is set here, next to each other.
ENV PATH="/app/.venv/bin:$PATH" \
    ORBISPANORA_TEMP_WORLD_DIR=/data/worlds \
    ORBISPANORA_UPLOAD_CHUNKS_DIR=/data/uploads

WORKDIR /app
COPY --from=build /app /app

USER orbispanora
EXPOSE 8000

CMD ["orbispanora", "run", "--host", "0.0.0.0", "--port", "8000"]
