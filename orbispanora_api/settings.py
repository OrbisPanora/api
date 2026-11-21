"""Configuration, read from the environment and from `.env`.

Every key is prefixed `ORBISPANORA_`; unprefixed keys in the files are ignored.
Precedence is constructor arguments, then the environment, then `.env.local`, then
`.env`, then a secrets directory, then the defaults below.

`.env` is committed and holds defaults that suit every machine. `.env.local` is not
committed and holds what differs on one machine: a world path, a Redis password.
"""

from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

try:
    APP_VERSION = metadata.version("orbispanora-api")
except metadata.PackageNotFoundError:  # run from a source tree that is not installed
    APP_VERSION = "0+unknown"

APP_TITLE = "OrbisPanora API"
APP_DESCRIPTION = "FastAPI backend for the OrbisPanora isometric Minecraft world viewer"

#: Per-user cache directory (`$XDG_CACHE_HOME` or `~/.cache`) holding extracted worlds and uploads.
_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "orbispanora"

#: The Minecraft dimensions the library can read.
Dimension = Literal["overworld", "nether", "end"]


class Settings(BaseSettings):
    """Everything the application reads from its environment."""

    model_config = SettingsConfigDict(
        env_prefix="ORBISPANORA_",
        # Layered, last one winning: `.env` is committed and holds defaults,
        # `.env.local` is not committed and holds per-machine values.
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Minecraft world ---

    #: A world folder to load at startup. Unset, no world is loaded and one has to be
    #: uploaded. The API only reads it.
    world_path: Path | None = None
    world_dimension: Dimension = "overworld"

    #: Textures and block models (`images/`, `json/`). They are not part of this
    #: repository, so the default is relative to the directory the server starts in.
    resources_dir: Path = Path("resources")

    # --- Server ---

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    #: Path prefix when a reverse proxy mounts the API below `/`. Passed to uvicorn.
    root_path: str = ""

    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"

    #: Comma-separated in the environment (`a,b`). Empty by default: the viewer reaches
    #: the API through the same origin (its development server or its reverse proxy),
    #: so no cross-origin access is needed. List the origins that may call the API
    #: from another site. `*` allows every origin.
    cors_origins: Annotated[list[str], NoDecode] = []

    # --- Cache ---

    cache_enabled: bool = True
    #: `redis` needs the `redis` extra (`uv sync --extra redis`).
    cache_type: Literal["memory", "redis"] = "memory"
    redis_url: SecretStr = SecretStr("redis://localhost:6379")
    cache_ttl_heightmap: int = Field(default=300, gt=0)
    cache_ttl_surface: int = Field(default=120, gt=0)
    cache_ttl_chunk: int = Field(default=600, gt=0)

    # --- Rate limiting ---

    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=10000, gt=0)
    #: Seconds.
    rate_limit_window: int = Field(default=60, gt=0)

    # --- Uploads ---

    #: Largest zip file accepted, in one request or as the sum of its chunks.
    upload_max_size_mb: int = Field(default=500, gt=0)
    #: Limits on what a zip file may expand to. A world has a few hundred files.
    upload_max_entries: int = Field(default=20000, gt=0)
    upload_max_unzipped_mb: int = Field(default=4096, gt=0)
    #: Largest ratio of unzipped to zipped size, for archives that unzip to more than 1 MB.
    upload_max_ratio: int = Field(default=100, gt=0)
    #: Chunked uploads: sessions open at once, how long an idle one is kept (seconds),
    #: and the largest single chunk.
    upload_max_sessions: int = Field(default=4, ge=1)
    upload_session_ttl: int = Field(default=3600, gt=0)
    upload_max_chunk_mb: int = Field(default=16, gt=0)
    #: Where uploaded worlds are extracted. The default is in the user's cache directory.
    temp_world_dir: Path = _CACHE_DIR / "worlds"
    #: Where the chunks of an upload in progress are stored.
    upload_chunks_dir: Path = _CACHE_DIR / "uploads"
    cleanup_temp_files: bool = True
    max_temp_worlds: int = Field(default=5, ge=1)

    # --- Worker processes and memory ---

    #: Processes that compute chunks. The default is the number of CPU cores, at most 8.
    workers: int = Field(default_factory=lambda: min(os.cpu_count() or 1, 8), ge=1, le=64)
    #: Decoded chunks each process keeps (the main process and every worker). A decoded chunk takes about
    #: 240 KB, so a worker's chunk cache is at most this many times 240 KB.
    world_chunk_cache: int = Field(default=32, ge=0)
    #: Region files each process keeps open. A region is read when a chunk of it is asked for, not loaded whole.
    world_region_cache: int = Field(default=8, ge=0)

    # --- Compression ---

    compression_enabled: bool = True
    #: Bytes. Smaller responses are sent as they are.
    compression_min_size: int = Field(default=500, ge=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """A comma-separated string becomes a list; an empty item is dropped."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("world_path", mode="before")
    @classmethod
    def _empty_world_path_is_unset(cls, value: object) -> object:
        """`ORBISPANORA_WORLD_PATH=` means no world, not the current directory."""
        return None if value == "" else value

    @field_validator("world_path", "resources_dir", "temp_world_dir", "upload_chunks_dir")
    @classmethod
    def _expand_user(cls, value: Path | None) -> Path | None:
        """`~` in a path is expanded, since these are paths a person types."""
        return value.expanduser() if value is not None else None

    def problems(self) -> list[tuple[Literal["error", "warning"], str]]:
        """What is wrong with this configuration, as (level, message) pairs.

        An error stops the server from starting. A warning leaves it running with a
        feature missing.
        """
        found: list[tuple[Literal["error", "warning"], str]] = []

        if self.world_path is not None and not self.world_path.is_dir():
            found.append(("error", f"ORBISPANORA_WORLD_PATH is not a directory: {self.world_path}"))

        if self.cache_enabled and self.cache_type == "redis":
            if importlib.util.find_spec("redis") is None:
                found.append(("error", "ORBISPANORA_CACHE_TYPE is redis but the redis package is not installed. Run: uv sync --extra redis"))

        if not self.resources_dir.is_dir():
            found.append(
                ("warning", f"No resources directory ({self.resources_dir} is absent), so the /api/resources endpoints will fail. The web viewer does not use them and worlds load normally. Set ORBISPANORA_RESOURCES_DIR to enable them.")
            )

        if self.cors_origins == ["*"]:
            found.append(("warning", "ORBISPANORA_CORS_ORIGINS is *: any website can call this API from a visitor's browser."))

        if "*" in self.cors_origins and len(self.cors_origins) > 1:
            found.append(("warning", "ORBISPANORA_CORS_ORIGINS contains * and other origins; * alone applies."))

        return found


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings. Cached, so the files are read once.

    `ORBISPANORA_SECRETS_DIR` names a directory with one file per setting, as a
    container runtime mounts secrets (`/run/secrets/ORBISPANORA_REDIS_URL`). A file
    there is read after the environment and the `.env` files, so it is the lowest
    source. It is read from the environment here rather than declared in `model_config`,
    which warns on every start when the directory is absent.
    """
    secrets_dir = os.environ.get("ORBISPANORA_SECRETS_DIR")
    return Settings(_secrets_dir=secrets_dir) if secrets_dir else Settings()
