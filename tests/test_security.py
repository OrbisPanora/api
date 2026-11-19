"""Hostile input: crafted zip files, oversized uploads, path traversal, leaked errors."""

import json
import os
import time
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orbispanora_api.middleware import RateLimitMiddleware
from orbispanora_api.routers import upload
from orbispanora_api.services.world_service import get_world_service
from orbispanora_api.services.zip_safety import UnsafeArchiveError, safe_extract
from orbispanora_api.settings import Settings, get_settings
from orbispanora_api.utils.paths import UnsafeNameError, path_inside, safe_name

LIMITS = {"max_entries": 100, "max_total_bytes": 10 * 1024 * 1024, "max_ratio": 100}


def make_zip(path, entries):
    """A zip file with the `(name, data)` entries."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return path


class TestSafeExtract:

    def test_normal_archive(self, tmp_path):
        archive = make_zip(tmp_path / "a.zip", [("world/level.dat", b"x"), ("world/region/r.0.0.mca", b"y")])
        target = tmp_path / "out"
        target.mkdir()
        safe_extract(archive, target, **LIMITS)
        assert (target / "world/region/r.0.0.mca").read_bytes() == b"y"

    @pytest.mark.parametrize("name", ["../escape.txt", "world/../../escape.txt", "/etc/escape.txt", "C:/escape.txt", "world\\..\\escape.txt"])
    def test_paths_that_leave_the_target(self, tmp_path, name):
        archive = make_zip(tmp_path / "a.zip", [(name, b"x")])
        target = tmp_path / "out"
        target.mkdir()
        with pytest.raises(UnsafeArchiveError):
            safe_extract(archive, target, **LIMITS)
        assert not (tmp_path / "escape.txt").exists()
        assert list(target.iterdir()) == []

    def test_symbolic_link(self, tmp_path):
        archive = tmp_path / "a.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            link = zipfile.ZipInfo("link")
            link.create_system = 3
            link.external_attr = 0o120777 << 16
            handle.writestr(link, "/etc")
        target = tmp_path / "out"
        target.mkdir()
        with pytest.raises(UnsafeArchiveError):
            safe_extract(archive, target, **LIMITS)

    def test_too_many_entries(self, tmp_path):
        archive = make_zip(tmp_path / "a.zip", [(f"f{i}", b"x") for i in range(11)])
        with pytest.raises(UnsafeArchiveError):
            safe_extract(archive, tmp_path, max_entries=10, max_total_bytes=10**6, max_ratio=100)

    def test_declared_size_above_the_limit(self, tmp_path):
        archive = make_zip(tmp_path / "a.zip", [("big", os.urandom(2048))])
        with pytest.raises(UnsafeArchiveError):
            safe_extract(archive, tmp_path, max_entries=10, max_total_bytes=1024, max_ratio=100)

    def test_zip_bomb_is_refused_by_ratio(self, tmp_path):
        archive = make_zip(tmp_path / "a.zip", [("zeros", bytes(50 * 1024 * 1024))])
        assert archive.stat().st_size < 100 * 1024
        target = tmp_path / "out"
        target.mkdir()
        with pytest.raises(UnsafeArchiveError):
            safe_extract(archive, target, max_entries=10, max_total_bytes=100 * 1024 * 1024, max_ratio=100)
        assert list(target.iterdir()) == []

    def test_written_bytes_are_counted_even_if_the_header_lies(self, tmp_path, monkeypatch):
        archive = make_zip(tmp_path / "a.zip", [("zeros", bytes(4 * 1024 * 1024))])
        # The size check on the headers is skipped, as if the headers declared small sizes.
        monkeypatch.setattr("orbispanora_api.services.zip_safety._check_entries", lambda *a, **k: None)
        target = tmp_path / "out"
        target.mkdir()
        with pytest.raises(UnsafeArchiveError):
            safe_extract(archive, target, max_entries=10, max_total_bytes=1024 * 1024, max_ratio=10**9)

    def test_not_a_zip(self, tmp_path):
        path = tmp_path / "a.zip"
        path.write_bytes(b"not a zip")
        with pytest.raises(UnsafeArchiveError):
            safe_extract(path, tmp_path, **LIMITS)


class TestNames:

    @pytest.mark.parametrize("name", ["", ".", "..", "../x", "a/b", "a\\b", ".hidden", "a..b", "a b", "a\x00b", "é"])
    def test_refused(self, name):
        with pytest.raises(UnsafeNameError):
            safe_name(name)

    @pytest.mark.parametrize("name", ["stone", "oak_stairs", "stone_top.webp", "a-b_c.1"])
    def test_accepted(self, name):
        assert safe_name(name) == name

    def test_symbolic_link_out_of_the_base_is_refused(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        (tmp_path / "outside").mkdir()
        (base / "link").symlink_to(tmp_path / "outside")
        with pytest.raises(UnsafeNameError):
            path_inside(base, "link", "file.txt")

    def test_path_inside(self, tmp_path):
        assert path_inside(tmp_path, "a", "b.json") == tmp_path.resolve() / "a" / "b.json"


class TestResourceTraversal:

    @pytest.fixture
    def resources(self, tmp_path, monkeypatch):
        root = tmp_path / "resources"
        (root / "images").mkdir(parents=True)
        (root / "json/blockstates").mkdir(parents=True)
        (tmp_path / "secret.json").write_text(json.dumps({"variants": {"": {"model": "x"}}}))
        (root / "images/ok.webp").write_bytes(b"RIFF")
        (root / "json/blockstates/stone.json").write_text(json.dumps({"variants": {"": {"model": "block/stone"}}}))
        monkeypatch.setenv("ORBISPANORA_RESOURCES_DIR", str(root))
        get_settings.cache_clear()
        return root

    @pytest.mark.parametrize("name", ["..%2f..%2fsecret.json", "%2e%2e%2fsecret.json", "..%5csecret.json", "%2fetc%2fpasswd", ".hidden"])
    def test_image_names_that_traverse(self, resources, client, name):
        response = client.get(f"/api/resources/images/{name}")
        assert response.status_code in (400, 404)
        assert b"RIFF" not in response.content

    def test_image_inside_the_folder_is_served(self, resources, client):
        assert client.get("/api/resources/images/ok.webp").status_code == 200

    @pytest.mark.parametrize("params", [
        {"id": "../../secret"},
        {"id": "stone", "namespace": "../x"},
        {"id": "stone", "biome": "../../../etc/passwd"},
        {"id": "a/b"},
    ])
    def test_json_parameters_that_traverse(self, resources, client, params):
        assert client.get("/api/resources/json", params=params).status_code in (400, 404)

    def test_properties_that_are_not_json(self, resources, client):
        assert client.get("/api/resources/json", params={"id": "stone", "properties": "{not json"}).status_code == 400

    def test_properties_that_are_too_long(self, resources, client):
        assert client.get("/api/resources/json", params={"id": "stone", "properties": "x" * 5000}).status_code == 400

    def test_palette_limits(self, resources, client):
        assert client.post("/api/resources/palette", json={"blocks": []}).status_code == 400
        many = {"stone": [{"biome": "plains", "properties": {}, "side": 0}] * 2001}
        assert client.post("/api/resources/palette", json={"blocks": [many]}).status_code == 400

    def test_palette_names_that_traverse_are_skipped(self, resources, client):
        body = {"blocks": [{"../../secret": [{"biome": "plains", "properties": {}, "side": 0}]}]}
        assert client.post("/api/resources/palette", json=body).json()["data"] == {"../../secret": []}


class TestUploadLimits:

    @pytest.fixture(autouse=True)
    def clean_sessions(self):
        yield
        for upload_id in list(upload.chunked_uploads):
            upload._drop_session(upload_id)

    def init(self, client, **overrides):
        data = {"filename": "w.zip", "total_chunks": 1, "total_size": 10, **overrides}
        return client.post("/api/upload/init", data=data)

    @pytest.mark.parametrize("size", [0, -5, 600 * 1024 * 1024])
    def test_declared_size_must_be_in_range(self, client_without_world, size):
        assert self.init(client_without_world, total_size=size).status_code == 413

    @pytest.mark.parametrize("chunks", [0, -1, 11, 10**9])
    def test_chunk_count_must_fit_the_size(self, client_without_world, chunks):
        assert self.init(client_without_world, total_chunks=chunks).status_code == 400

    def test_chunk_count_must_cover_the_size(self, client_without_world):
        size = 100 * 1024 * 1024
        assert self.init(client_without_world, total_size=size, total_chunks=2).status_code == 400
        assert self.init(client_without_world, total_size=size, total_chunks=7).status_code == 200

    def test_number_of_sessions_is_limited(self, client_without_world):
        for _ in range(4):
            assert self.init(client_without_world).status_code == 200
        assert self.init(client_without_world).status_code == 429

    def test_idle_sessions_expire(self, client_without_world):
        upload_id = self.init(client_without_world).json()["data"]["upload_id"]
        upload.chunked_uploads[upload_id]["last_activity"] = time.monotonic() - 10**6
        directory = upload.chunked_uploads[upload_id]["upload_dir"]
        assert client_without_world.delete(f"/api/upload/cancel/{upload_id}").status_code == 404
        assert not directory.exists()

    def test_chunk_over_the_declared_size_is_refused(self, client_without_world):
        upload_id = self.init(client_without_world, total_size=10).json()["data"]["upload_id"]
        response = client_without_world.post(
            "/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": 0}, files={"chunk": ("c", b"x" * 11)}
        )
        assert response.status_code == 413
        assert list(upload.chunked_uploads[upload_id]["upload_dir"].iterdir()) == []

    def test_chunk_over_the_chunk_limit_is_refused(self, client_without_world, monkeypatch):
        monkeypatch.setenv("ORBISPANORA_UPLOAD_MAX_CHUNK_MB", "1")
        get_settings.cache_clear()
        size = 4 * 1024 * 1024
        upload_id = self.init(client_without_world, total_size=size, total_chunks=4).json()["data"]["upload_id"]
        response = client_without_world.post(
            "/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": 0}, files={"chunk": ("c", b"x" * (1024 * 1024 + 1))}
        )
        assert response.status_code == 413

    def test_finalize_checks_the_total(self, client_without_world):
        upload_id = self.init(client_without_world, total_size=10).json()["data"]["upload_id"]
        client_without_world.post("/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": 0}, files={"chunk": ("c", b"x" * 4)})
        assert client_without_world.post("/api/upload/finalize", data={"upload_id": upload_id}).status_code == 400
        assert upload_id not in upload.chunked_uploads

    def test_finalize_with_bytes_that_are_not_a_zip(self, client_without_world):
        upload_id = self.init(client_without_world, total_size=4).json()["data"]["upload_id"]
        client_without_world.post("/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": 0}, files={"chunk": ("c", b"abcd")})
        response = client_without_world.post("/api/upload/finalize", data={"upload_id": upload_id})
        assert response.status_code == 400
        assert upload_id not in upload.chunked_uploads

    @pytest.mark.parametrize("upload_id", ["../../etc", "x", "00000000-0000-0000-0000-00000000000g", "A" * 500])
    def test_upload_ids_that_are_not_uuids(self, client_without_world, upload_id):
        response = client_without_world.post(
            "/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": 0}, files={"chunk": ("c", b"x")}
        )
        assert response.status_code == 404

    def test_single_request_over_the_limit(self, client_without_world, monkeypatch, tmp_path):
        monkeypatch.setenv("ORBISPANORA_UPLOAD_MAX_SIZE_MB", "1")
        get_settings.cache_clear()
        response = client_without_world.post(
            "/api/upload/world", files={"file": ("w.zip", b"x" * (1024 * 1024 + 1), "application/zip")}
        )
        assert response.status_code == 413
        assert list(get_settings().upload_chunks_dir.iterdir()) == []

    def test_zip_bomb_upload_leaves_nothing_behind(self, client_without_world, tmp_path):
        bomb = make_zip(tmp_path / "bomb.zip", [("world/level.dat", bytes(60 * 1024 * 1024))])
        with open(bomb, "rb") as handle:
            response = client_without_world.post("/api/upload/world", files={"file": ("w.zip", handle, "application/zip")})
        assert response.status_code == 400
        assert not get_world_service().is_loaded()
        assert list(get_settings().temp_world_dir.iterdir()) == []

    def test_zip_with_traversal_upload(self, client_without_world, tmp_path):
        evil = make_zip(tmp_path / "evil.zip", [("../../evil.txt", b"x"), ("world/level.dat", b"x")])
        with open(evil, "rb") as handle:
            response = client_without_world.post("/api/upload/world", files={"file": ("w.zip", handle, "application/zip")})
        assert response.status_code == 400
        assert "evil" not in response.text.replace("evil.zip", "")


class TestErrorsDoNotLeak:

    def test_unexpected_error_in_a_route(self, client, monkeypatch):
        def boom(*args):
            raise RuntimeError("/home/someone/secret/path failed")

        monkeypatch.setattr(get_world_service(), "get_block_data", boom)
        response = client.get("/api/blocks/0/62/0")
        assert response.status_code == 500
        assert "secret" not in response.text and "/home" not in response.text

    def test_unexpected_error_outside_a_route_handler(self, make_client, world_dir, monkeypatch):
        client = make_client(world_dir)
        monkeypatch.setattr(upload, "_get_session", lambda upload_id: (_ for _ in ()).throw(RuntimeError("/var/secret")))
        response = client.post("/api/upload/finalize", data={"upload_id": "x"})
        assert response.status_code == 500
        assert "/var/secret" not in response.text

    def test_extraction_errors_do_not_name_paths(self, client_without_world, tmp_path):
        path = tmp_path / "a.zip"
        make_zip(path, [("readme.txt", b"x")])
        with open(path, "rb") as handle:
            response = client_without_world.post("/api/upload/world", files={"file": ("w.zip", handle, "application/zip")})
        assert str(tmp_path) not in response.text
        assert str(get_settings().temp_world_dir) not in response.text


class TestRequestLimits:

    def test_area_size_is_limited(self, client):
        params = {"x1": 0, "z1": 0, "x2": 5000, "z2": 5}
        assert client.get("/api/chunks/area/heightmap", params=params).status_code == 400
        assert client.get("/api/chunks/area/heightmap", params={"x1": 5, "z1": 0, "x2": 0, "z2": 5}).status_code == 400

    @pytest.mark.parametrize("route", ["blocks", "surface"])
    def test_chunk_limit_is_bounded(self, client, route):
        assert client.get(f"/api/isometric/{route}", params={"limit": 10**6}).status_code == 422
        assert client.get(f"/api/isometric/{route}", params={"limit": -1}).status_code == 422

    def test_chunk_list_length_is_bounded(self, client):
        response = client.get("/api/isometric/blocks", params={"mode": "list", "chunk_list": "0,0;" * 5000})
        assert response.status_code == 422


class TestRateLimitResponse:

    def test_limit_exceeded_is_a_429_response(self):
        app = FastAPI()

        @app.get("/ping")
        def ping():
            return {}

        app.add_middleware(RateLimitMiddleware, requests=2, window=60)
        client = TestClient(app)
        assert [client.get("/ping").status_code for _ in range(3)] == [200, 200, 429]
        blocked = client.get("/ping")
        assert blocked.json() == {"detail": "Rate limit exceeded. Please try again later."}
        assert blocked.headers["X-RateLimit-Remaining"] == "0"

    def test_forwarded_header_is_not_used_by_the_middleware(self):
        app = FastAPI()

        @app.get("/ping")
        def ping():
            return {}

        app.add_middleware(RateLimitMiddleware, requests=1, window=60)
        client = TestClient(app)
        assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        assert client.get("/ping", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429

    def test_idle_clients_are_forgotten(self):
        import asyncio

        from orbispanora_api.middleware.rate_limiter import RateLimiter

        limiter = RateLimiter(requests=5, window=60)
        limiter.CLEANUP_EVERY = 2
        limiter._requests["old"] = [0.0]
        asyncio.run(limiter.is_allowed("a"))
        asyncio.run(limiter.is_allowed("b"))
        assert "old" not in limiter._requests


class TestCors:

    def test_no_origin_is_allowed_by_default(self, client):
        response = client.get("/api/worlds/health", headers={"Origin": "https://example.invalid"})
        assert "access-control-allow-origin" not in response.headers

    def test_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for name in list(os.environ):
            if name.startswith("ORBISPANORA_"):
                monkeypatch.delenv(name)
        settings = Settings()
        assert settings.cors_origins == []
        assert Path.home() in settings.temp_world_dir.parents or "XDG_CACHE_HOME" in os.environ
        assert settings.temp_world_dir != Path("temp_worlds")
