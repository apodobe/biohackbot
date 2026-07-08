"""Zip archive safety checks (zip-slip, zip bombs)."""
from __future__ import annotations

import zipfile
from pathlib import PurePosixPath

MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024
MAX_ZIP_MEMBERS = 50_000
MAX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


class UnsafeZipError(ValueError):
    pass


def _member_name_safe(name: str) -> None:
    path = PurePosixPath(name)
    if name.startswith("/") or ".." in path.parts:
        raise UnsafeZipError(f"unsafe zip member path: {name!r}")


def validate_zip_archive(zf: zipfile.ZipFile, *, zip_size: int | None = None) -> None:
    if zip_size is not None and zip_size > MAX_ZIP_BYTES:
        raise UnsafeZipError(f"zip file too large: {zip_size} bytes")

    members = zf.infolist()
    if len(members) > MAX_ZIP_MEMBERS:
        raise UnsafeZipError(f"too many zip members: {len(members)}")

    total_uncompressed = 0
    for info in members:
        _member_name_safe(info.filename)
        total_uncompressed += info.file_size
        if info.file_size and info.compress_size:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > MAX_COMPRESSION_RATIO:
                raise UnsafeZipError(
                    f"suspicious compression ratio for {info.filename!r}: {ratio:.1f}"
                )

    if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
        raise UnsafeZipError(
            f"uncompressed zip payload too large: {total_uncompressed} bytes"
        )
