"""Administration from a shell.

The server:

    orbispanora run
    orbispanora run --reload --port 8001
    orbispanora run --world-path ~/saves/my-world --dimension nether

The configuration the server would start with, and whether it is usable:

    orbispanora config show
    orbispanora config check

A world folder, read without loading it into the server:

    orbispanora world check ~/saves/my-world
    orbispanora world check ~/saves/my-world --dimension end

Every setting is an environment variable prefixed `ORBISPANORA_`, also read from `.env`
and `.env.local` in the current directory (see `settings.py`). An option given on the
command line wins over both.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Annotated

import typer
from pydantic import SecretStr, ValidationError

from .settings import APP_VERSION, Dimension, Settings, get_settings

app = typer.Typer(help="OrbisPanora API administration.", no_args_is_help=True)
config_app = typer.Typer(help="The configuration.", no_args_is_help=True)
world_app = typer.Typer(help="Minecraft world folders.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(world_app, name="world")

#: Where each dimension keeps its region files, relative to the world folder.
REGION_DIRS: dict[str, str] = {
    "overworld": "region",
    "nether": "DIM-1/region",
    "end": "DIM1/region",
}

REGION_FILE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")


def error(message: str) -> None:
    """Prints an error to stderr without exiting, so every problem can be listed."""
    typer.secho(f"[ERROR] {message}", fg=typer.colors.RED, err=True)


def fail(message: str) -> None:
    """Prints an error to stderr and exits non-zero."""
    error(message)
    raise typer.Exit(code=1)


def warn(message: str) -> None:
    """Prints a warning to stderr."""
    typer.secho(f"[WARNING] {message}", fg=typer.colors.YELLOW, err=True)


def load_settings() -> Settings:
    """The settings, or a one-line error naming the invalid key instead of a traceback."""
    try:
        return get_settings()
    except ValidationError as error:
        lines = [
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()
        ]
        fail("Invalid configuration (ORBISPANORA_ prefix):\n  " + "\n  ".join(lines))
        raise  # unreachable: fail() exits


def version_callback(value: bool) -> None:
    """Prints the version and exits."""
    if value:
        typer.echo(APP_VERSION)
        raise typer.Exit()


@app.callback()
def main(
    _version: Annotated[
        bool,
        typer.Option(
            "--version", callback=version_callback, is_eager=True, help="Show the version and exit."
        ),
    ] = False,
) -> None:
    """OrbisPanora API administration."""


@app.command("run")
def run(
    host: Annotated[str | None, typer.Option(help="Address to listen on.")] = None,
    port: Annotated[int | None, typer.Option(help="Port to listen on.")] = None,
    reload: Annotated[
        bool, typer.Option("--reload", help="Restart when a source file changes.")
    ] = False,
    root_path: Annotated[
        str | None, typer.Option(help="Path prefix when a proxy mounts the API below /.")
    ] = None,
    world_path: Annotated[
        Path | None, typer.Option(help="World folder to load. Read only.")
    ] = None,
    dimension: Annotated[Dimension | None, typer.Option(help="Dimension to load.")] = None,
    log_level: Annotated[str | None, typer.Option(help="Logging level.")] = None,
) -> None:
    """Serve the API.

    Options not given are taken from the settings. The settings are validated before
    the server starts, so a mistake is reported on one line instead of as a traceback
    from inside startup.
    """
    # Options go through the environment: the server imports its settings itself (in
    # a child process under --reload), and the environment is what reaches it.
    overrides = {
        "HOST": host,
        "PORT": port,
        "ROOT_PATH": root_path,
        "WORLD_PATH": world_path,
        "WORLD_DIMENSION": dimension,
        "LOG_LEVEL": log_level.upper() if log_level else None,
    }
    for key, value in overrides.items():
        if value is not None:
            os.environ[f"ORBISPANORA_{key}"] = str(value)
    get_settings.cache_clear()

    settings = load_settings()
    problems = settings.problems()
    for level, message in problems:
        if level == "warning":
            warn(message)
    errors = [message for level, message in problems if level == "error"]
    if errors:
        fail("\n  ".join(errors))

    # Imported here so the other commands do not pay for the server's import.
    import uvicorn  # pylint: disable=import-outside-toplevel

    uvicorn.run(
        "orbispanora_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=reload,
        root_path=settings.root_path,
        log_level=settings.log_level.lower(),
    )


@config_app.command("show")
def config_show(
    reveal: Annotated[
        bool, typer.Option("--reveal", help="Print secret values instead of masking them.")
    ] = False,
) -> None:
    """Print every setting with its effective value, as environment variables."""
    settings = load_settings()
    for name, value in settings.model_dump().items():
        if isinstance(value, SecretStr):
            value = value.get_secret_value() if reveal else "********"
        elif isinstance(value, list):
            value = ",".join(value)
        elif value is None:
            value = ""
        typer.echo(f"ORBISPANORA_{name.upper()}={value}")


@config_app.command("check")
def config_check() -> None:
    """Validate the configuration. Exits non-zero if the server could not start."""
    settings = load_settings()
    problems = settings.problems()
    for level, message in problems:
        (warn if level == "warning" else error)(message)
    if any(level == "error" for level, _ in problems):
        raise typer.Exit(code=1)
    typer.secho("Configuration is valid.", fg=typer.colors.GREEN, err=True)


@world_app.command("check")
def world_check(
    path: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, resolve_path=True, help="World folder."),
    ],
    dimension: Annotated[Dimension, typer.Option(help="Dimension to inspect.")] = "overworld",
) -> None:
    """Summarise a world folder's region files for one dimension.

    Only lists files. Nothing is opened for writing and nothing is created, unlike
    loading the world through the library, which creates a missing region folder.
    """
    region_dir = path / REGION_DIRS[dimension]
    if not region_dir.is_dir():
        fail(f"No {dimension} region folder at {region_dir}. Is this a Minecraft world?")

    regions = []
    ignored = 0
    for entry in region_dir.iterdir():
        match = REGION_FILE.match(entry.name)
        if match and entry.is_file():
            regions.append((int(match[1]), int(match[2]), entry.stat().st_size))
        else:
            ignored += 1

    if not regions:
        fail(f"{region_dir} holds no region files (r.<x>.<z>.mca).")

    xs = [x for x, _, _ in regions]
    zs = [z for _, z, _ in regions]
    typer.echo(f"World:      {path}")
    typer.echo(f"Dimension:  {dimension} ({region_dir.relative_to(path)})")
    typer.echo(f"Regions:    {len(regions)}")
    typer.echo(f"Region x:   {min(xs)} to {max(xs)}")
    typer.echo(f"Region z:   {min(zs)} to {max(zs)}")
    typer.echo(f"Block x:    {min(xs) * 512} to {max(xs) * 512 + 511}")
    typer.echo(f"Block z:    {min(zs) * 512} to {max(zs) * 512 + 511}")
    typer.echo(f"Size:       {sum(size for _, _, size in regions) / 1_048_576:.1f} MiB")
    if ignored:
        warn(f"{ignored} other entries in {region_dir} were ignored.")
