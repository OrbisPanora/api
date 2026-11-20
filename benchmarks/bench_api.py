"""Time the isometric chunk endpoint of a running API, to find where a request spends its time.

Usage (the API is started separately, on the world to measure)::

    uv run orbispanora run --world-path /path/to/world &
    uv run python benchmarks/bench_api.py --base-url http://127.0.0.1:8000 \\
        --start 0,0 --radius 8 --label small --server-pid $!

It requests the chunks of a square around ``--start`` (chunk coordinates), nearest first as the
viewer does, once per concurrency level. It prints a table and writes
``benchmarks/results/api-<label>-<timestamp>.json`` (git-ignored). The file holds the numbers
and labels (machine, commits, world size, region count) so that two runs can be compared with
``benchmarks/compare.py``.

The API keeps no response cache. A request is "cold" when the worker process that served it had
to open the world, which the ``Server-Timing`` header reports. Start the server just before the
run to see the cold requests; the first concurrency level then carries all of them.
"""
import argparse
import asyncio
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

RESULTS_DIR = Path(__file__).parent / 'results'
TIMING_PART = re.compile(r'([a-z0-9_]+);(?:dur=([\d.]+)|desc="([^"]*)")')


def percentile(values: List[float], fraction: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def summary(values: List[float]) -> Dict[str, float]:
    """Count, p50, p95, max and mean of a list of measurements."""
    return {
        'count': len(values),
        'p50': round(percentile(values, 0.5), 3),
        'p95': round(percentile(values, 0.95), 3),
        'max': round(max(values), 3) if values else 0.0,
        'mean': round(statistics.fmean(values), 3) if values else 0.0,
    }


def parse_server_timing(header: str) -> Tuple[Dict[str, float], Dict[str, str]]:
    """Durations (ms) and notes of a ``Server-Timing`` header."""
    durations: Dict[str, float] = {}
    notes: Dict[str, str] = {}
    for name, duration, description in TIMING_PART.findall(header):
        if duration:
            durations[name] = float(duration)
        else:
            notes[name] = description
    return durations, notes


def process_tree_rss_mb(root_pid: int) -> Dict[str, float]:
    """Resident memory in MB of a process and of each of its descendants (Linux only; empty elsewhere)."""
    parents: Dict[int, int] = {}
    rss: Dict[int, float] = {}
    try:
        for entry in os.listdir('/proc'):
            if not entry.isdigit():
                continue
            try:
                with open(f'/proc/{entry}/status', encoding='utf-8') as status:
                    fields = dict(line.split(':', 1) for line in status if ':' in line)
            except OSError:
                continue
            parents[int(entry)] = int(fields.get('PPid', '0').strip())
            rss[int(entry)] = int(fields.get('VmRSS', '0 kB').split()[0]) / 1024
    except OSError:
        return {}
    family = {root_pid}
    grew = True
    while grew:
        grew = False
        for pid, parent in parents.items():
            if parent in family and pid not in family:
                family.add(pid)
                grew = True
    return {('main' if pid == root_pid else str(pid)): round(rss[pid], 1) for pid in sorted(family) if pid in rss}


def command_output(command: List[str], cwd: Optional[Path] = None) -> str:
    """Output of a command, or an empty string if it fails."""
    try:
        return subprocess.run(command, capture_output=True, text=True, check=True, cwd=cwd).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def library_label() -> str:
    """Version of orbispanora-lib and, for a git install, its commit."""
    try:
        distribution = metadata.distribution('orbispanora-lib')
        label = distribution.version
        direct = distribution.read_text('direct_url.json')
        if direct:
            commit = json.loads(direct).get('vcs_info', {}).get('commit_id', '')
            label += f' ({commit[:7]})' if commit else ''
        return label
    except metadata.PackageNotFoundError:
        return ''


def machine_labels() -> Dict[str, object]:
    """CPU, cores, memory, Python and commits, written next to the numbers."""
    cpu = ''
    memory_mb = 0
    try:
        with open('/proc/cpuinfo', encoding='utf-8') as info:
            cpu = next((line.split(':', 1)[1].strip() for line in info if line.startswith('model name')), '')
        with open('/proc/meminfo', encoding='utf-8') as info:
            memory_mb = int(next(line for line in info if line.startswith('MemTotal')).split()[1]) // 1024
    except (OSError, StopIteration):
        pass
    here = Path(__file__).parent
    return {
        'cpu': cpu or platform.processor(),
        'cores': os.cpu_count(),
        'memory_mb': memory_mb,
        'python': platform.python_version(),
        'commit': command_output(['git', 'rev-parse', '--short', 'HEAD'], here),
        'dirty': bool(command_output(['git', 'status', '--porcelain'], here)),
        'lib': library_label(),
    }


def square_around(start: Tuple[int, int], radius: int) -> List[Tuple[int, int]]:
    """Chunks of a square around ``start``, nearest first."""
    cx, cz = start
    chunks = [(cx + dx, cz + dz) for dz in range(-radius, radius + 1) for dx in range(-radius, radius + 1)]
    return sorted(chunks, key=lambda chunk: (chunk[0] - cx) ** 2 + (chunk[1] - cz) ** 2)


async def fetch(client: httpx.AsyncClient, chunk: Tuple[int, int]) -> Dict[str, Any]:
    """Request one chunk and keep what was measured about it."""
    start = time.perf_counter()
    response = await client.get(f'/api/chunks/{chunk[0]}/{chunk[1]}/-60', params={'mode': 'isometric'})
    elapsed = (time.perf_counter() - start) * 1000
    durations, notes = parse_server_timing(response.headers.get('server-timing', ''))
    return {
        'status': response.status_code,
        'latency_ms': elapsed,
        'wire_bytes': response.num_bytes_downloaded,
        'body_bytes': len(response.content),
        'durations': durations,
        'cold': notes.get('cold') == '1',
        'blocks': int(notes.get('blocks', '0') or 0),
    }


async def run_level(client: httpx.AsyncClient, chunks: List[Tuple[int, int]], concurrency: int) -> Dict[str, Any]:
    """Request every chunk with ``concurrency`` requests at once and summarise."""
    queue: asyncio.Queue = asyncio.Queue()
    for chunk in chunks:
        queue.put_nowait(chunk)
    results: List[Dict[str, Any]] = []

    async def worker() -> None:
        while True:
            try:
                chunk = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            results.append(await fetch(client, chunk))

    started = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(concurrency)))
    wall = time.perf_counter() - started

    found = [item for item in results if item['status'] == 200]
    phases = sorted({name for item in found for name in item['durations']})
    return {
        'concurrency': concurrency,
        'requests': len(results),
        'found': len(found),
        'not_found': sum(1 for item in results if item['status'] == 404),
        'errors': sum(1 for item in results if item['status'] not in (200, 404)),
        'cold_requests': sum(1 for item in found if item['cold']),
        'wall_s': round(wall, 3),
        'chunks_per_s': round(len(results) / wall, 2) if wall else 0.0,
        'latency_ms': summary([item['latency_ms'] for item in found]),
        'phase_ms': {name: summary([item['durations'][name] for item in found if name in item['durations']]) for name in phases},
        'blocks': summary([float(item['blocks']) for item in found]),
        'wire_kb': summary([item['wire_bytes'] / 1024 for item in found]),
        'body_kb': summary([item['body_bytes'] / 1024 for item in found]),
    }


async def world_info(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Cost of ``/api/worlds/current``, which lists every region."""
    start = time.perf_counter()
    response = await client.get('/api/worlds/current')
    elapsed = (time.perf_counter() - start) * 1000
    data = response.json().get('data', {}) if response.status_code == 200 else {}
    return {'ms': round(elapsed, 3), 'status': response.status_code, 'regions': len(data.get('region_list') or []),
            'body_kb': round(len(response.content) / 1024, 1)}


async def run_benchmark(client: httpx.AsyncClient, start: Tuple[int, int], radius: int, levels: List[int],
                        server_pid: Optional[int]) -> Dict[str, Any]:
    """Run every concurrency level against the chunks around ``start``."""
    chunks = square_around(start, radius)
    result: Dict[str, Any] = {'world_info': await world_info(client), 'levels': []}
    if server_pid:
        result['rss_mb_before'] = process_tree_rss_mb(server_pid)
    for concurrency in levels:
        result['levels'].append(await run_level(client, chunks, concurrency))
    if server_pid:
        result['rss_mb_after'] = process_tree_rss_mb(server_pid)
    return result


def print_table(result: Dict[str, Any]) -> None:
    """Print one row per concurrency level, then the share of each phase."""
    print(f"world info: {result['world_info']}")
    print(f"\n{'concurrency':>11}{'requests':>9}{'found':>7}{'cold':>6}{'chunks/s':>10}{'p50 ms':>9}{'p95 ms':>9}{'max ms':>9}{'wire kB p50':>13}")
    for level in result['levels']:
        latency = level['latency_ms']
        print(f"{level['concurrency']:>11}{level['requests']:>9}{level['found']:>7}{level['cold_requests']:>6}{level['chunks_per_s']:>10}"
              f"{latency['p50']:>9}{latency['p95']:>9}{latency['max']:>9}{level['wire_kb']['p50']:>13}")
    for level in result['levels']:
        print(f"\nphases at concurrency {level['concurrency']} (ms):")
        for name, values in level['phase_ms'].items():
            print(f"  {name:<10}p50 {values['p50']:>9}  p95 {values['p95']:>9}  max {values['max']:>9}")
    for key in ('rss_mb_before', 'rss_mb_after'):
        if key in result:
            print(f'\n{key}: {result[key]}')


def parse_start(text: str) -> Tuple[int, int]:
    """``x,z`` as two integers."""
    x, z = text.split(',')
    return int(x), int(z)


async def amain(args: argparse.Namespace) -> int:
    """Run against the server at ``--base-url`` and write the result file."""
    async with httpx.AsyncClient(base_url=args.base_url, timeout=60.0, headers={'Accept-Encoding': 'gzip'}) as client:
        health = await client.get('/api/worlds/health')
        if health.status_code != 200:
            print(f'The API at {args.base_url} is not healthy: {health.status_code}', file=sys.stderr)
            return 1
        result = await run_benchmark(client, args.start, args.radius, args.concurrency, args.server_pid)
    result.update({
        'script': 'api/bench_api',
        'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'machine': machine_labels(),
        'world': {'label': args.label, 'start': list(args.start), 'radius': args.radius, 'chunks': (2 * args.radius + 1) ** 2},
    })
    print_table(result)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f'api-{args.label}-{datetime.now().strftime("%Y%m%d-%H%M%S")}.json'
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'\nWrote {path}')
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Parse the command line and run."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000', help='Address of the running API.')
    parser.add_argument('--start', type=parse_start, default=(0, 0), help='Centre chunk as x,z (default 0,0).')
    parser.add_argument('--radius', type=int, default=8, help='Chunks on each side of the centre (default 8: 289 chunks).')
    parser.add_argument('--concurrency', type=lambda text: [int(part) for part in text.split(',')], default=[1, 6, 12],
                        help='Comma-separated numbers of requests at once (default 1,6,12).')
    parser.add_argument('--label', default='world', help='Name for this world in the result file, for example small or large.')
    parser.add_argument('--server-pid', type=int, help='Process id of the API, to record its memory and its workers\' (Linux).')
    parser.add_argument('--out', type=Path, default=RESULTS_DIR, help='Folder for the result file.')
    return asyncio.run(amain(parser.parse_args(argv)))


if __name__ == '__main__':
    sys.exit(main())
