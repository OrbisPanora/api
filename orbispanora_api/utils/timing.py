"""Phase timing for a request, reported in a ``Server-Timing`` header and in the log."""

import time
from typing import Dict


class Stopwatch:
    """Records how many milliseconds each named phase took, one after the other."""

    def __init__(self) -> None:
        self.phases: Dict[str, float] = {}
        self._last = time.perf_counter()

    def lap(self, name: str) -> None:
        """End the phase called ``name``; it started at the previous lap (or at creation)."""
        now = time.perf_counter()
        self.phases[name] = self.phases.get(name, 0.0) + (now - self._last) * 1000
        self._last = now


def server_timing(phases: Dict[str, float], **notes: object) -> str:
    """Value of a ``Server-Timing`` header: ``name;dur=ms`` per phase, then ``name;desc="value"`` per note."""
    parts = [f"{name};dur={millis:.2f}" for name, millis in phases.items()]
    parts += [f'{name};desc="{value}"' for name, value in notes.items()]
    return ", ".join(parts)
