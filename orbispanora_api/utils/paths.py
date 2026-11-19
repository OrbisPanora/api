"""Building file paths inside a base directory from names that come from a request."""

import re
from pathlib import Path

#: Letters, digits, `_`, `-` and `.` inside a name. A name never contains a separator.
_NAME = re.compile(r"[A-Za-z0-9_.\-]+")


class UnsafeNameError(ValueError):
    """A name that cannot be used as a path component."""


def safe_name(name: str) -> str:
    """`name` if it is one path component made of allowed characters, else UnsafeNameError."""
    if not _NAME.fullmatch(name) or name.startswith(".") or ".." in name:
        raise UnsafeNameError("Invalid name")
    return name


def path_inside(base: Path, *names: str) -> Path:
    """`base` joined with `names`, which are checked one by one.

    The result is resolved (symbolic links followed) and has to stay inside `base`.
    """
    candidate = base.joinpath(*(safe_name(name) for name in names)).resolve()
    if not candidate.is_relative_to(base.resolve()):
        raise UnsafeNameError("Invalid name")
    return candidate
