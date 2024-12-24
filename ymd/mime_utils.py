from enum import Enum
from typing import Optional


class MimeType(Enum):
    JPEG = "image/jpeg"
    PNG = "image/png"


MAGIC_BYTES = (
    (MimeType.JPEG, bytes((0xFF, 0xD8, 0xFF))),
    (MimeType.PNG, bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))),
)


def guess_mime_type(data: bytes) -> Optional[MimeType]:
    for mime_type, magic_bytes in MAGIC_BYTES:
        if data.startswith(magic_bytes):
            return mime_type
