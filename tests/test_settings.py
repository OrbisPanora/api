"""Settings: prefix, files, parsing and validation. No server is started."""

import pytest
from pydantic import ValidationError

from orbispanora_api.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Run in an empty directory with no ORBISPANORA_ variable, so no .env file is read."""
    monkeypatch.chdir(tmp_path)
    for name in list(__import__("os").environ):
        if name.startswith("ORBISPANORA_"):
            monkeypatch.delenv(name)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults():
    settings = Settings()
    assert settings.world_path is None
    assert settings.world_dimension == "overworld"
    assert settings.port == 8000
    assert settings.cors_origins == []


def test_environment_variable_needs_the_prefix(monkeypatch):
    monkeypatch.setenv("PORT", "9999")
    assert Settings().port == 8000
    monkeypatch.setenv("ORBISPANORA_PORT", "9999")
    assert Settings().port == 9999


def test_env_local_overrides_env(tmp_path):
    (tmp_path / ".env").write_text("ORBISPANORA_PORT=7001\nORBISPANORA_HOST=0.0.0.0\n")
    (tmp_path / ".env.local").write_text("ORBISPANORA_PORT=7002\n")
    settings = Settings()
    assert settings.port == 7002
    assert settings.host == "0.0.0.0"


def test_environment_overrides_files(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("ORBISPANORA_PORT=7001\n")
    monkeypatch.setenv("ORBISPANORA_PORT", "7003")
    assert Settings().port == 7003


def test_unprefixed_and_unknown_keys_in_files_are_ignored(tmp_path):
    (tmp_path / ".env").write_text("PORT=1\nORBISPANORA_NOT_A_SETTING=x\n")
    assert Settings().port == 8000


def test_cors_origins_are_split_on_commas(monkeypatch):
    monkeypatch.setenv("ORBISPANORA_CORS_ORIGINS", "http://a.test, http://b.test,")
    assert Settings().cors_origins == ["http://a.test", "http://b.test"]


def test_empty_world_path_means_no_world(monkeypatch):
    monkeypatch.setenv("ORBISPANORA_WORLD_PATH", "")
    assert Settings().world_path is None


def test_invalid_values_are_rejected(monkeypatch):
    monkeypatch.setenv("ORBISPANORA_WORLD_DIMENSION", "moon")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("ORBISPANORA_WORLD_DIMENSION", "nether")
    monkeypatch.setenv("ORBISPANORA_PORT", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_redis_url_is_masked_in_repr(monkeypatch):
    monkeypatch.setenv("ORBISPANORA_REDIS_URL", "redis://:hunter2@host:6379")
    settings = Settings()
    assert "hunter2" not in repr(settings)
    assert settings.redis_url.get_secret_value() == "redis://:hunter2@host:6379"


def test_secrets_dir_is_the_lowest_source(tmp_path, monkeypatch):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "ORBISPANORA_PORT").write_text("7100")
    (secrets / "ORBISPANORA_HOST").write_text("10.0.0.1")
    monkeypatch.setenv("ORBISPANORA_SECRETS_DIR", str(secrets))
    monkeypatch.setenv("ORBISPANORA_PORT", "7101")
    settings = get_settings()
    assert settings.port == 7101
    assert settings.host == "10.0.0.1"


def test_problems_reports_a_missing_world_as_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBISPANORA_WORLD_PATH", str(tmp_path / "absent"))
    levels = [level for level, _ in Settings().problems()]
    assert "error" in levels


def test_problems_has_no_error_for_the_defaults():
    assert all(level != "error" for level, _ in Settings().problems())


def test_worker_and_cache_defaults():
    settings = Settings()
    assert 1 <= settings.workers <= 8
    assert settings.world_chunk_cache == 32
    assert settings.world_region_cache == 8


def test_worker_and_cache_settings_are_read_and_checked(monkeypatch):
    monkeypatch.setenv("ORBISPANORA_WORKERS", "3")
    monkeypatch.setenv("ORBISPANORA_WORLD_CHUNK_CACHE", "5")
    monkeypatch.setenv("ORBISPANORA_WORLD_REGION_CACHE", "2")
    settings = Settings()
    assert (settings.workers, settings.world_chunk_cache, settings.world_region_cache) == (3, 5, 2)
    for name, value in [("ORBISPANORA_WORKERS", "0"), ("ORBISPANORA_WORKERS", "65"), ("ORBISPANORA_WORLD_CHUNK_CACHE", "-1")]:
        monkeypatch.setenv(name, value)
        with pytest.raises(ValidationError):
            Settings()
        monkeypatch.delenv(name)
