import struct
import sys
import zlib
from pathlib import Path

import pytest

# scripts/ 는 패키지가 아니므로 테스트에서 import 할 수 있게 경로를 추가한다
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


@pytest.fixture
def png_bytes() -> bytes:
    """테스트용 아주 작은 단색 PNG."""
    w = h = 8
    raw = b"".join(b"\x00" + bytes((80, 90, 80)) * w for _ in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = struct.pack(">I", len(data)) + kind + data
        return body + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
