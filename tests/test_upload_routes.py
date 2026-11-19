"""World upload, in one request and in chunks."""

import pytest


def post_zip(client, zip_path, **params):
    with open(zip_path, "rb") as handle:
        return client.post("/api/upload/world", files={"file": ("world.zip", handle, "application/zip")}, params=params)


def test_upload_world_loads_it(client_without_world, world_zip):
    response = post_zip(client_without_world, world_zip)
    assert response.status_code == 200, response.text
    assert client_without_world.get("/api/worlds/health").json()["world_loaded"] is True
    assert client_without_world.get("/api/blocks/0/62/0").json()["data"]["id"] == "water"


def test_upload_rejects_a_file_that_is_not_a_zip(client_without_world, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not a world")
    response = client_without_world.post("/api/upload/world", files={"file": ("notes.txt", path.read_bytes(), "text/plain")})
    assert response.status_code == 400


def test_upload_rejects_a_zip_without_a_world(client_without_world, tmp_path):
    import zipfile

    path = tmp_path / "empty.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("readme.txt", "no world here")
    assert post_zip(client_without_world, path).status_code in (400, 500)


def test_upload_rejects_an_unknown_dimension(client_without_world, world_zip):
    assert post_zip(client_without_world, world_zip, dimension="moon").status_code == 400


def start_chunked(client, data, pieces):
    size = -(-len(data) // pieces)
    init = client.post("/api/upload/init", data={"filename": "world.zip", "total_chunks": pieces, "total_size": len(data)})
    assert init.status_code == 200, init.text
    upload_id = init.json()["data"]["upload_id"]
    return upload_id, [data[i * size:(i + 1) * size] for i in range(pieces)]


def test_chunked_upload_loads_the_world(client_without_world, world_zip):
    upload_id, parts = start_chunked(client_without_world, world_zip.read_bytes(), 3)
    for index in (2, 0, 1):
        response = client_without_world.post(
            "/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": index}, files={"chunk": ("part", parts[index])}
        )
        assert response.status_code == 200, response.text
    assert response.json()["data"]["is_complete"] is True
    final = client_without_world.post("/api/upload/finalize", data={"upload_id": upload_id})
    assert final.status_code == 200, final.text
    assert client_without_world.get("/api/worlds/health").json()["world_loaded"] is True


def test_finalize_needs_every_chunk(client_without_world, world_zip):
    upload_id, parts = start_chunked(client_without_world, world_zip.read_bytes(), 2)
    client_without_world.post("/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": 0}, files={"chunk": ("part", parts[0])})
    assert client_without_world.post("/api/upload/finalize", data={"upload_id": upload_id}).status_code == 400


def test_chunk_index_and_repeats_are_checked(client_without_world, world_zip):
    upload_id, parts = start_chunked(client_without_world, world_zip.read_bytes(), 2)
    send = lambda index: client_without_world.post(
        "/api/upload/chunk", data={"upload_id": upload_id, "chunk_index": index}, files={"chunk": ("part", parts[0])}
    )
    assert send(5).status_code == 400
    assert send(0).status_code == 200
    assert send(0).status_code == 400


def test_chunk_for_an_unknown_session(client_without_world):
    response = client_without_world.post("/api/upload/chunk", data={"upload_id": "nope", "chunk_index": 0}, files={"chunk": ("part", b"x")})
    assert response.status_code == 404


def test_cancel(client_without_world, world_zip):
    upload_id, _ = start_chunked(client_without_world, world_zip.read_bytes(), 2)
    assert client_without_world.delete(f"/api/upload/cancel/{upload_id}").status_code == 200
    assert client_without_world.delete(f"/api/upload/cancel/{upload_id}").status_code == 404


@pytest.mark.parametrize("filename", ["world.tar", "world"])
def test_init_only_accepts_zip_files(client_without_world, filename):
    response = client_without_world.post("/api/upload/init", data={"filename": filename, "total_chunks": 1, "total_size": 10})
    assert response.status_code == 400
