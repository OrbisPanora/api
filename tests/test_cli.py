"""The command line, run in-process. No server is started."""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from orbispanora_api.cli import app
from orbispanora_api.settings import APP_VERSION, get_settings

REGION_FILE = Path(__file__).resolve().parents[2] / "lib" / "tests" / "world_files" / "r.0.0.mca"

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in list(__import__("os").environ):
        if name.startswith("ORBISPANORA_"):
            monkeypatch.delenv(name)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == APP_VERSION


def test_no_arguments_prints_help():
    result = runner.invoke(app, [])
    assert "run" in result.output and "config" in result.output and "world" in result.output


def test_config_show_masks_secrets_unless_revealed(monkeypatch):
    monkeypatch.setenv("ORBISPANORA_REDIS_URL", "redis://:hunter2@host:6379")
    shown = runner.invoke(app, ["config", "show"])
    assert shown.exit_code == 0
    assert "hunter2" not in shown.stdout
    assert "ORBISPANORA_REDIS_URL=********" in shown.stdout
    revealed = runner.invoke(app, ["config", "show", "--reveal"])
    assert "hunter2" in revealed.stdout


def test_config_check_fails_for_a_missing_world(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBISPANORA_WORLD_PATH", str(tmp_path / "absent"))
    result = runner.invoke(app, ["config", "check"])
    assert result.exit_code == 1
    assert "WORLD_PATH" in result.output


def test_invalid_setting_is_one_line_not_a_traceback(monkeypatch):
    monkeypatch.setenv("ORBISPANORA_PORT", "not-a-number")
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 1
    assert "Invalid configuration" in result.output
    assert "Traceback" not in result.output


def test_run_refuses_to_start_with_a_missing_world(tmp_path):
    result = runner.invoke(app, ["run", "--world-path", str(tmp_path / "absent")])
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_world_check_lists_the_region_files(tmp_path):
    world = tmp_path / "world"
    (world / "region").mkdir(parents=True)
    shutil.copy(REGION_FILE, world / "region" / "r.0.0.mca")
    result = runner.invoke(app, ["world", "check", str(world)])
    assert result.exit_code == 0, result.output
    assert "Regions:    1" in result.stdout
    assert "Block x:    0 to 511" in result.stdout


def test_world_check_creates_nothing(tmp_path):
    world = tmp_path / "world"
    world.mkdir()
    result = runner.invoke(app, ["world", "check", str(world), "--dimension", "nether"])
    assert result.exit_code == 1
    assert list(world.iterdir()) == []


def test_world_check_rejects_an_empty_region_folder(tmp_path):
    world = tmp_path / "world"
    (world / "region").mkdir(parents=True)
    result = runner.invoke(app, ["world", "check", str(world)])
    assert result.exit_code == 1
    assert "no region files" in result.output
