"""The container image has no home directory, so settings whose default is under it must be set in the Dockerfile."""

from pathlib import Path

import pytest

from orbispanora_api.settings import Settings, get_settings

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """No ORBISPANORA_ variable and no .env file: the defaults only."""
    monkeypatch.chdir(tmp_path)
    for name in list(__import__("os").environ):
        if name.startswith("ORBISPANORA_"):
            monkeypatch.delenv(name)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_every_setting_that_defaults_under_the_home_directory_is_set_in_the_dockerfile():
    home = Path.home()
    under_home = [
        name for name, value in Settings().model_dump().items()
        if isinstance(value, Path) and (home == value or home in value.parents)
    ]
    assert under_home, "expected at least the upload and world folders to default under the home directory"
    text = DOCKERFILE.read_text(encoding="utf-8")
    missing = [name for name in under_home if f"ORBISPANORA_{name.upper()}=" not in text]
    assert not missing, f"set {missing} in the Dockerfile, the image user has no home directory"


def test_the_image_folders_are_under_the_data_directory():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "ORBISPANORA_UPLOAD_CHUNKS_DIR=/data/uploads" in text
    assert "ORBISPANORA_TEMP_WORLD_DIR=/data/worlds" in text
