"""Extracting an uploaded zip file with limits on what it may contain."""

import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

_BLOCK = 1024 * 1024
#: Archives that unzip to less than this are not checked for their ratio.
_RATIO_FLOOR = 1024 * 1024


class UnsafeArchiveError(ValueError):
    """The archive has an entry or a size that is not accepted."""


def safe_extract(zip_path: Path, target: Path, *, max_entries: int, max_total_bytes: int, max_ratio: int) -> None:
    """Extract `zip_path` into the existing directory `target`.

    Refused with UnsafeArchiveError: too many entries, symbolic links, absolute paths,
    `..` components, a backslash or a drive letter in a name, an entry that would land
    outside `target`, a declared unzipped size above `max_total_bytes` or a ratio of
    unzipped to zipped size above `max_ratio`. The bytes written are counted while
    extracting, so a header that declares a smaller size than the data does not
    get around the limit.
    """
    root = target.resolve()
    try:
        with zipfile.ZipFile(zip_path) as archive:
            entries = archive.infolist()
            _check_entries(entries, root, max_entries, max_total_bytes, max_ratio)
            written = 0
            for entry in entries:
                destination = root / entry.filename
                if entry.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, open(destination, "wb") as output:
                    while block := source.read(_BLOCK):
                        written += len(block)
                        if written > max_total_bytes:
                            raise UnsafeArchiveError("The archive unzips to more than the allowed size")
                        output.write(block)
    except zipfile.BadZipFile as exc:
        raise UnsafeArchiveError("The file is not a valid zip archive") from exc


def _check_entries(entries: list[zipfile.ZipInfo], root: Path, max_entries: int, max_total_bytes: int, max_ratio: int) -> None:
    """Refuse the archive before anything is written."""
    if len(entries) > max_entries:
        raise UnsafeArchiveError("The archive has too many entries")
    declared = sum(entry.file_size for entry in entries)
    stored = sum(entry.compress_size for entry in entries)
    if declared > max_total_bytes:
        raise UnsafeArchiveError("The archive unzips to more than the allowed size")
    if declared > _RATIO_FLOOR and declared > max_ratio * max(stored, 1):
        raise UnsafeArchiveError("The archive is compressed more than is plausible")
    for entry in entries:
        name = entry.filename
        parts = PurePosixPath(name).parts
        if stat.S_ISLNK(entry.external_attr >> 16):
            raise UnsafeArchiveError("The archive contains a symbolic link")
        if PurePosixPath(name).is_absolute() or ".." in parts or "\\" in name or (parts and ":" in parts[0]):
            raise UnsafeArchiveError("The archive has an entry with an unsafe path")
        if not (root / name).resolve().is_relative_to(root):
            raise UnsafeArchiveError("The archive has an entry with an unsafe path")


def remove_tree(path: Path) -> None:
    """Delete a directory and what it holds; a missing directory is not an error."""
    shutil.rmtree(path, ignore_errors=True)
