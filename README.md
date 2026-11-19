# OrbisPanora API

FastAPI backend for the OrbisPanora isometric Minecraft world viewer. It reads
Minecraft Anvil worlds with the [`orbispanora-lib`](https://github.com/OrbisPanora/lib)
library and returns JSON that the [viewer](https://github.com/OrbisPanora/viewer) draws.

Target Minecraft version: 1.21.1.

## Requirements

- [uv](https://docs.astral.sh/uv/). Python 3.14 or newer is required; `.python-version`
  pins 3.14, which uv downloads if it is missing. The Dockerfile uses `python:3.14-slim`.
- git, because `orbispanora-lib` is installed from GitHub (see [Updating the library](#updating-the-library)).

## Setup

```bash
uv sync                      # creates .venv from uv.lock (includes the dev group)
# optional: create .env.local with per-machine settings, see Configuration
uv run orbispanora run
```

The server listens on `ORBISPANORA_HOST:ORBISPANORA_PORT` (default `127.0.0.1:8000`).
Interactive documentation is at `/docs` (Swagger UI) and `/redoc`.

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`.
Add one with `uv add <package>`. The optional Redis cache is installed with
`uv sync --extra redis`.

## Command line

`uv sync` installs the `orbispanora` command (`uv run orbispanora ...`, or
`orbispanora ...` with the virtual environment active).

| Command | Purpose |
|---|---|
| `orbispanora run` | Serve the API. Options: `--host`, `--port`, `--reload`, `--root-path`, `--world-path`, `--dimension`, `--log-level`. |
| `orbispanora config show` | Print every setting with its effective value. Secrets are masked; `--reveal` prints them. |
| `orbispanora config check` | Validate the configuration. Exits with status 1 if the server could not start. |
| `orbispanora world check PATH` | Summarise a world folder's region files (count, region and block bounds, size). Only lists files; it does not open them and creates nothing. |
| `orbispanora --version` | Print the version. |

`run` validates the settings first and prints a one-line error, not a traceback.
An option given on the command line wins over the environment and the `.env` files.

## Configuration

Settings are defined in `orbispanora_api/settings.py` with pydantic-settings.
Every variable is prefixed `ORBISPANORA_`. Values come from these sources; the first
one that sets a key wins:

1. The command line (`run` options).
2. Environment variables.
3. `.env.local` in the current directory. Not committed. Per-machine values go here.
4. `.env` in the current directory. Committed. Defaults that suit every machine; no secrets.
5. Files in the directory named by `ORBISPANORA_SECRETS_DIR`, one file per setting
   (as a container runtime mounts secrets).
6. The defaults in `settings.py`.

Unprefixed keys and unknown keys in the files are ignored. A value of the wrong type or
outside its range stops the command with the key named.

| Variable | Default | Meaning |
|---|---|---|
| `ORBISPANORA_WORLD_PATH` | unset | World folder to load. Unset or empty: no world is loaded and one has to be uploaded. |
| `ORBISPANORA_WORLD_DIMENSION` | `overworld` | `overworld`, `nether` or `end`. |
| `ORBISPANORA_RESOURCES_DIR` | `resources` | Block textures and models (`images/`, `json/`). Not part of this repository. |
| `ORBISPANORA_HOST`, `ORBISPANORA_PORT` | `127.0.0.1`, `8000` | Address to listen on. |
| `ORBISPANORA_ROOT_PATH` | empty | Path prefix when a reverse proxy mounts the API below `/`. |
| `ORBISPANORA_LOG_LEVEL` | `INFO` | `CRITICAL`, `ERROR`, `WARNING`, `INFO` or `DEBUG`. |
| `ORBISPANORA_CORS_ORIGINS` | `*` | Comma-separated allowed origins. `*` allows all. |
| `ORBISPANORA_CACHE_ENABLED`, `ORBISPANORA_CACHE_TYPE` | `true`, `memory` | `memory`, or `redis` (needs the `redis` extra; not tested here). |
| `ORBISPANORA_REDIS_URL` | `redis://localhost:6379` | Secret: masked by `config show`. |
| `ORBISPANORA_CACHE_TTL_HEIGHTMAP`, `_SURFACE`, `_CHUNK` | `300`, `120`, `600` | Cache lifetime in seconds. |
| `ORBISPANORA_RATE_LIMIT_ENABLED`, `_REQUESTS`, `_WINDOW` | `true`, `10000`, `60` | Requests allowed per client per window (seconds). |
| `ORBISPANORA_UPLOAD_MAX_SIZE_MB` | `500` | Maximum size of an uploaded world. |
| `ORBISPANORA_TEMP_WORLD_DIR`, `_CLEANUP_TEMP_FILES`, `_MAX_TEMP_WORLDS` | `temp_worlds`, `true`, `5` | Where uploaded worlds are extracted and how many are kept. |
| `ORBISPANORA_COMPRESSION_ENABLED`, `_COMPRESSION_MIN_SIZE` | `true`, `500` | Gzip responses larger than this many bytes. |

Changes from the previous version, which read unprefixed names (`WORLD_PATH`,
`API_PORT`, ...): the prefix is new; `API_HOST` and `API_PORT` are now `HOST` and
`PORT`; `API_RELOAD` is now the `--reload` option; `UPLOAD_ALLOWED_EXTENSIONS` was
never read and is removed; `CORS_ORIGINS` is now applied (before, the server
allowed every origin whatever it said).

The API only reads the world at `ORBISPANORA_WORLD_PATH`. Uploaded worlds are extracted
into `ORBISPANORA_TEMP_WORLD_DIR`. Use a copy of a world you care about.

## Endpoints

All responses use the envelope `{"status": "success", "data": {...}, "timestamp": "<ISO 8601, UTC>"}`.
Errors use FastAPI's `{"detail": "..."}`. The status codes used are 400
(invalid parameter), 404 (chunk or resource not found), 422 (invalid query
value), 500 (server error) and 503 (no world loaded).

| Method and path | Purpose |
|---|---|
| `GET /` | API name, version and links. |
| `GET /api/worlds/health` | Health check. |
| `GET /api/worlds/current` | Information about the loaded world. |
| `POST /api/worlds/dimension` | Switch the loaded world to another dimension. |
| `GET /api/chunks/{chunk_x}/{chunk_z}/{chunk_h}?mode=` | Chunk data. `mode` is `heightmap`, `surface`, `isometric`, `render`, `simplified` or `full` (default `heightmap`). |
| `GET /api/chunks/viewport/render?center_x=&center_z=&view_distance=` | Pre-computed render data for the chunks around a centre chunk (`view_distance` 1 to 32). |
| `GET /api/chunks/area/heightmap?x1=&z1=&x2=&z2=` | Heightmap for a rectangle of chunks. |
| `GET /api/chunks/tile/{tile_x}/{tile_z}` | Data for a square tile of chunks. |
| `GET /api/blocks/{x}/{y}/{z}` | One block. |
| `GET /api/biomes/{x}/{y}/{z}` | Biome at a position. |
| `GET /api/isometric/blocks`, `GET /api/isometric/surface` | Block lists for the isometric renderer. |
| `GET /api/isometric/stats`, `POST /api/isometric/cache/clear` | Renderer cache statistics and reset. |
| `GET /api/resources/images/{image}`, `GET /api/resources/json`, `POST /api/resources/palette` | Block textures and block model data. |
| `POST /api/upload/world` | Upload a zipped world in one request. |
| `POST /api/upload/init`, `/chunk`, `/finalize`, `DELETE /api/upload/cancel/{upload_id}` | Chunked upload for large worlds. |

Parameters and response schemas are listed in `/docs`. That page is generated
from the code and is the reference if this table and the code disagree.

## Project structure

```
api/
├── pyproject.toml          # dependencies, `orbispanora` command, build backend
├── uv.lock
├── .env                    # committed defaults (ORBISPANORA_*)
├── orbispanora_api/
│   ├── cli.py              # the `orbispanora` command (Typer)
│   ├── settings.py         # settings (pydantic-settings)
│   ├── main.py             # FastAPI app, CORS, rate limiting, router registration
│   ├── routers/            # world, chunk, block, biome, isometric, resource, upload
│   ├── services/           # world_service, cache_service, resource_service
│   ├── middleware/         # rate limiting, compression
│   ├── models/             # Pydantic request and response models
│   └── utils/              # error classes
└── tests/                  # pytest suite
```

## Tests

```bash
uv run pytest
```

The tests call the application in-process with a FastAPI test client, on a small world
generated by `tests/utilities/make_world.py`, and once with no world.
The coverage minimum is 80 %.
No test uses a world from your machine.

## Docker

```bash
docker build -t orbispanora-api .
docker run -p 8000:8000 orbispanora-api
```

The image runs as an unprivileged user and starts
`orbispanora run --host 0.0.0.0 --port 8000`. Behind a reverse proxy that mounts the API
below a path prefix, add `--root-path /prefix` or set `ORBISPANORA_ROOT_PATH`.
The committed `.env` is copied into the image; `.env.local` is not. Pass other
settings as `ORBISPANORA_*` environment variables. Uploaded worlds are extracted
under `/data/worlds`; mount a volume there to keep them across restarts.

## Updating the library

`pyproject.toml` takes `orbispanora-lib` from `https://github.com/OrbisPanora/lib`
and `uv.lock` pins the commit. To move to a newer commit:

```bash
uv lock --upgrade-package orbispanora-lib
uv sync
```

Released versions of the API use a tag of the library (`tag = "v0.1.0"` in
`[tool.uv.sources]`).
