"""The benchmark scripts still run against the test world. No timing is checked."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import httpx

BENCHMARKS = Path(__file__).parent.parent / "benchmarks"


def load(name):
    """Import a script of ``benchmarks/`` by path."""
    spec = importlib.util.spec_from_file_location(name, BENCHMARKS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_server_timing():
    bench = load("bench_api")
    durations, notes = bench.parse_server_timing('queue;dur=1.50, chunk;dur=20.00, cold;desc="1", blocks;desc="7"')
    assert durations == {"queue": 1.5, "chunk": 20.0}
    assert notes == {"cold": "1", "blocks": "7"}


def test_square_around_starts_with_the_centre():
    bench = load("bench_api")
    chunks = bench.square_around((3, -2), 2)
    assert chunks[0] == (3, -2)
    assert len(chunks) == 25


def test_benchmark_runs_against_the_test_world(client):
    bench = load("bench_api")
    from orbispanora_api.main import app  # pylint: disable=import-outside-toplevel

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            return await bench.run_benchmark(http, (0, 0), 1, [1, 3], None)

    result = asyncio.run(run())
    assert result["world_info"]["status"] == 200
    assert [level["concurrency"] for level in result["levels"]] == [1, 3]
    for level in result["levels"]:
        assert level["requests"] == 9
        assert level["found"] >= 1 and level["errors"] == 0
        assert "chunk" in level["phase_ms"]


def test_compare_lists_common_numbers(tmp_path, capsys):
    compare = load("compare")
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_text(json.dumps({"machine": {}, "world": {}, "levels": {"p50": 2.0}}), encoding="utf-8")
    second.write_text(json.dumps({"machine": {}, "world": {}, "levels": {"p50": 1.0}}), encoding="utf-8")
    assert compare.main([str(first), str(second)]) == 0
    assert "levels.p50" in capsys.readouterr().out
    assert compare.main([]) == 2
