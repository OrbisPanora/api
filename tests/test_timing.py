"""Phase timing and the Server-Timing header of isometric chunks."""

import re

from orbispanora_api.services import world_service as module
from orbispanora_api.utils.timing import Stopwatch, server_timing

PHASES = ["queue", "world", "chunk", "scan1", "scan2", "project", "return", "total"]


def test_stopwatch_adds_laps_of_the_same_name():
    watch = Stopwatch()
    watch.lap("a")
    watch.lap("b")
    watch.lap("a")
    assert list(watch.phases) == ["a", "b"]
    assert all(millis >= 0 for millis in watch.phases.values())


def test_server_timing_format():
    assert server_timing({"queue": 1.234, "chunk": 20.0}, cold=1, blocks=7) == (
        'queue;dur=1.23, chunk;dur=20.00, cold;desc="1", blocks;desc="7"'
    )


def test_worker_reports_every_phase(world_dir):
    data, timings = module._worker_get_chunk_isometric_timed(str(world_dir), "overworld", 0, 1)
    assert data is not None
    assert {"queue", "world", "chunk", "scan1", "scan2", "project", "finished", "cold"} <= set(timings)
    assert timings["cold"] in (0.0, 1.0)


def test_worker_reports_the_wait_since_submission(world_dir):
    submitted = module.time.time() - 0.5
    _, timings = module._worker_get_chunk_isometric_timed(str(world_dir), "overworld", 0, 1, submitted)
    assert timings["queue"] >= 500


def test_isometric_response_has_server_timing(client):
    response = client.get("/api/chunks/0/1/0", params={"mode": "isometric"})
    assert response.status_code == 200
    header = response.headers["Server-Timing"]
    for phase in PHASES:
        assert re.search(rf"(^|, ){phase};dur=\d+\.\d\d", header), (phase, header)
    assert re.search(r'blocks;desc="[1-9]\d*"', header)
    assert re.search(r'cold;desc="[01]"', header)


def test_other_modes_have_no_server_timing(client):
    assert "Server-Timing" not in client.get("/api/chunks/0/0/0", params={"mode": "heightmap"}).headers
