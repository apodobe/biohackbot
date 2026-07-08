"""Tests for zip archive safety."""
from __future__ import annotations

import io
import zipfile

import pytest

from medbots.zip_safety import UnsafeZipError, validate_zip_archive


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_validate_zip_accepts_normal_archive() -> None:
    data = _zip_bytes({"export.xml": b"<HealthData/>"})
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        validate_zip_archive(zf, zip_size=len(data))


def test_validate_zip_rejects_path_traversal() -> None:
    data = _zip_bytes({"../etc/passwd": b"evil"})
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        with pytest.raises(UnsafeZipError, match="unsafe zip member"):
            validate_zip_archive(zf, zip_size=len(data))
