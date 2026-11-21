# OrbisPanora API

A FastAPI server that reads Minecraft Java worlds (Anvil format, 1.21.1) and serves their
chunks as JSON. The viewer draws them in the browser.

It is the second of three parts of OrbisPanora, an isometric world viewer:

| Repository | Role |
|---|---|
| [lib](https://github.com/OrbisPanora/lib) | Reads and writes the world files. |
| **api** (this one) | Serves chunks as JSON, using the library. |
| [viewer](https://github.com/OrbisPanora/viewer) | Draws the chunks in the browser. |

## Quick start

With [uv](https://docs.astral.sh/uv/) and git (the library is installed from GitHub):

```bash
uv sync                                          # creates .venv from uv.lock
uv run orbispanora run --world-path /path/to/a/copy/of/a/world
```

The server listens on `127.0.0.1:8000`. Interactive documentation is at `/docs` (Swagger UI)
and `/redoc`. Without `--world-path`, start empty and upload a zipped world with
`POST /api/upload/world`, or through the viewer. Use a copy of a world you care about.

With Docker (the API has no authentication, so this publishes the port on the local machine only):

```bash
docker run -p 127.0.0.1:8000:8000 ghcr.io/orbispanora/api:0.1.0
```

The [viewer](https://github.com/OrbisPanora/viewer#quick-start) README shows how to run both images together.

## Requirements

Python 3.14 or newer (`.python-version` pins 3.14, which uv downloads if it is missing) and
git.

## Setup

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`. Add one with
`uv add <package>`. The optional Redis cache is installed with `uv sync --extra redis`.
Per-machine settings go in `.env.local`, see [Configuration](#configuration).

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
| `ORBISPANORA_CORS_ORIGINS` | empty | Comma-separated origins allowed to call the API from another site. Empty: none (the viewer uses the same origin). `*` allows all. |
| `ORBISPANORA_CACHE_ENABLED`, `ORBISPANORA_CACHE_TYPE` | `true`, `memory` | `memory`, or `redis` (needs the `redis` extra; not tested here). |
| `ORBISPANORA_REDIS_URL` | `redis://localhost:6379` | Secret: masked by `config show`. |
| `ORBISPANORA_CACHE_TTL_HEIGHTMAP`, `_SURFACE`, `_CHUNK` | `300`, `120`, `600` | Cache lifetime in seconds. |
| `ORBISPANORA_RATE_LIMIT_ENABLED`, `_REQUESTS`, `_WINDOW` | `true`, `10000`, `60` | Requests allowed per client per window (seconds). |
| `ORBISPANORA_UPLOAD_MAX_SIZE_MB` | `500` | Maximum size of an uploaded zip file. |
| `ORBISPANORA_UPLOAD_MAX_ENTRIES`, `_MAX_UNZIPPED_MB`, `_MAX_RATIO` | `20000`, `4096`, `100` | Limits on what a zip file may unzip to: files, total size, unzipped size over zipped size. |
| `ORBISPANORA_UPLOAD_MAX_SESSIONS`, `_SESSION_TTL`, `_MAX_CHUNK_MB` | `4`, `3600`, `16` | Chunked uploads: sessions at once, idle seconds before one is dropped, largest chunk. |
| `ORBISPANORA_TEMP_WORLD_DIR`, `_CLEANUP_TEMP_FILES`, `_MAX_TEMP_WORLDS` | `~/.cache/orbispanora/worlds`, `true`, `5` | Where uploaded worlds are extracted and how many are kept. |
| `ORBISPANORA_UPLOAD_CHUNKS_DIR` | `~/.cache/orbispanora/uploads` | Where the chunks of uploads in progress are stored. |
| `ORBISPANORA_COMPRESSION_ENABLED`, `_COMPRESSION_MIN_SIZE` | `true`, `500` | Gzip responses larger than this many bytes. |
| `ORBISPANORA_WORKERS` | CPU cores, at most 8 | Worker processes that compute chunks (1 to 64). All routes share them. |
| `ORBISPANORA_WORLD_CHUNK_CACHE` | `32` | Decoded chunks each process keeps. A decoded chunk takes about 240 KB. |
| `ORBISPANORA_WORLD_REGION_CACHE` | `8` | Region files each process keeps open. A region file is not read into memory: its header is, and each chunk when it is asked for. |

### Memory

The main process and each worker start at about 70 to 100 MB. With the default settings a worker stays near
120 MB while it reads a large world, because it keeps at most `ORBISPANORA_WORLD_CHUNK_CACHE` decoded chunks
and `ORBISPANORA_WORLD_REGION_CACHE` open region files. The total is about
`(ORBISPANORA_WORKERS + 1) * 120 MB`, whatever the size of the world and the area that was viewed. Measured
once on a 2.0 GB world (224 regions) with 5 minutes of panning at zoom 0.25: 1.15 GB in total with 8 workers,
the largest worker 126 MB, no growth. Each worker also keeps only the world that is loaded: loading another
world (an upload, a dimension switch) replaces the worker processes.

The API only reads the world at `ORBISPANORA_WORLD_PATH`. Uploaded worlds are extracted
into `ORBISPANORA_TEMP_WORLD_DIR`. Use a copy of a world you care about.

## Security

- The API has no authentication. Run it on a trusted network or behind a reverse proxy that
  restricts access.
- Uploaded zip files are checked before extraction: entry count, unzipped size, compression
  ratio, no absolute paths, `..`, backslashes or symbolic links. The size of an upload is
  counted while it is received.
- File names in resource requests are limited to letters, digits, `_`, `-` and `.`, and the
  resulting path has to stay inside `ORBISPANORA_RESOURCES_DIR`.
- Error responses do not contain paths or exception text. The details are in the server log.
- The rate limiter counts requests per client address as uvicorn reports it. Behind a
  reverse proxy, set the environment variable `FORWARDED_ALLOW_IPS` (read by uvicorn) to the
  proxy's address, so that uvicorn takes the client address from `X-Forwarded-For`. The middleware itself never
  reads that header.

## Endpoints

All responses use the envelope `{"status": "success", "data": {...}, "timestamp": "<ISO 8601, UTC>"}`.
Errors use FastAPI's `{"detail": "..."}`. The status codes used are 400
(invalid parameter), 404 (chunk or resource not found), 413 (upload too large),
422 (invalid query value), 429 (rate limit or too many uploads), 500 (server error) and
503 (no world loaded).

| Method and path | Purpose |
|---|---|
| `GET /` | API name, version and links. |
| `GET /api/worlds/health` | Health check. |
| `GET /api/worlds/current` | Information about the loaded world. |
| `POST /api/worlds/dimension` | Switch the loaded world to another dimension. |
| `GET /api/chunks/{chunk_x}/{chunk_z}/{chunk_h}?mode=` | Chunk data. `mode` is `heightmap`, `surface`, `isometric`, `simplified` or `full` (default `heightmap`). |
| `GET /api/chunks/area/heightmap?x1=&z1=&x2=&z2=` | Heightmap for a rectangle of chunks. |
| `GET /api/chunks/tile/{tile_x}/{tile_z}` | Data for a square tile of chunks. |
| `GET /api/blocks/{x}/{y}/{z}` | One block. |
| `GET /api/biomes/{x}/{y}/{z}` | Biome at a position. |
| `GET /api/resources/images/{image}`, `GET /api/resources/json`, `POST /api/resources/palette` | Block textures and block model data. |
| `POST /api/upload/world` | Upload a zipped world in one request. |
| `POST /api/upload/init`, `/chunk`, `/finalize`, `DELETE /api/upload/cancel/{upload_id}` | Chunked upload for large worlds. |

### Isometric chunk

`GET /api/chunks/{chunk_x}/{chunk_z}/{chunk_h}?mode=isometric` returns the blocks of a chunk that the
viewer draws. Since 0.2.0 it sends block positions, not screen positions, and the viewer projects them:

```json
{"chunk_x": 1, "chunk_z": 0, "surface_y": 62,
 "palette": ["minecraft:water", "minecraft:stone"],
 "x": [0, 1, 1], "y": [62, 62, 63], "z": [0, 0, 0], "block": [0, 0, 1]}
```

`x` and `z` are the position inside the chunk (0 to 15), `y` the height and `block` the index in `palette`.
The four lists have one entry per block, in the order z, then x, then y going up. `surface_y` is the height of
the lowest surface block of the chunk. The blocks are every block that is not air between the lowest and the
highest surface of the chunk. A chunk that exists but has no block to draw answers with empty lists, and a
chunk that does not exist answers 404. A viewer turns a block into a screen position with
`16 * (gx - gz)` and `8 * (gx + gz) - 16 * y`, where `gx = 16 * chunk_x + x` and `gz = 16 * chunk_z + z`.

This format replaces `surface_blocks` (`[sprite, screen x, screen y]` per block) of 0.1.0. A viewer and an API
of different versions do not work together: upgrade both to 0.2.0.

Removed in 0.2.0, because they projected blocks on the server and the viewer does not use them:
`mode=render`, `GET /api/chunks/viewport/render` and the routes under `/api/isometric/`.

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
│   ├── routers/            # world, chunk, block, biome, resource, upload
│   ├── services/           # world_service, cache_service, resource_service, zip_safety
│   ├── middleware/         # rate limiting, compression
│   ├── models/             # Pydantic request and response models
│   └── utils/              # error classes, safe path building
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

## Releases

Pushing a tag `vX.Y.Z` that matches the version in `pyproject.toml` runs
`.github/workflows/release.yaml`. It runs the tests, lint and type check, builds the image,
scans it with Trivy (fails on critical or high vulnerabilities that have a fix), pushes it to
`ghcr.io/orbispanora/api` and attests its provenance.

## Updating the library

`pyproject.toml` takes `orbispanora-lib` from `https://github.com/OrbisPanora/lib` at a tag
(`tag = "v0.1.0"` in `[tool.uv.sources]`), and `uv.lock` pins the commit. To move to a newer
release, change the tag and run:

```bash
uv lock --upgrade-package orbispanora-lib
uv sync
```

## Licence

PolyForm Noncommercial License 1.0.0, see `LICENSE`.
