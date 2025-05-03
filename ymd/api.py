import base64
import hashlib
import hmac
import random
import time
import typing
from dataclasses import dataclass
from enum import Enum, auto

from Crypto.Cipher import AES
from strenum import StrEnum
from yandex_music import Client, Track
from yandex_music.utils.sign_request import DEFAULT_SIGN_KEY


class Container(Enum):
    FLAC = auto()
    MP3 = auto()
    MP4 = auto()


class Codec(Enum):
    FLAC = auto()
    MP3 = auto()
    AAC = auto()


@dataclass
class FileFormat:
    container: Container
    codec: Codec


FILE_FORMAT_MAPPING = {
    "flac": FileFormat(Container.FLAC, Codec.FLAC),
    "flac-mp4": FileFormat(Container.MP4, Codec.FLAC),
    "mp3": FileFormat(Container.MP3, Codec.MP3),
    "aac": FileFormat(Container.MP4, Codec.AAC),
    "he-aac": FileFormat(Container.MP4, Codec.AAC),
    "aac-mp4": FileFormat(Container.MP4, Codec.AAC),
    "he-aac-mp4": FileFormat(Container.MP4, Codec.AAC),
}


class ApiTrackQuality(StrEnum):
    LOW = "lq"
    NORMAL = "nq"
    LOSSLESS = "lossless"


@dataclass
class CustomDownloadInfo:
    quality: str
    file_format: FileFormat
    urls: list[str]
    decryption_key: str
    bitrate: int


def get_download_info(track: Track, quality: ApiTrackQuality) -> CustomDownloadInfo:
    client = track.client
    assert client
    timestamp = int(time.time())
    params = {
        "ts": timestamp,
        "trackId": track.id,
        "quality": quality,
        "codecs": ",".join(FILE_FORMAT_MAPPING.keys()),
        "transports": "encraw",
    }
    hmac_sign = hmac.new(
        DEFAULT_SIGN_KEY.encode(),
        "".join(str(e) for e in params.values()).replace(",", "").encode(),
        hashlib.sha256,
    )
    sign = base64.b64encode(hmac_sign.digest()).decode()[:-1]
    params["sign"] = sign

    resp = client.request.get(
        "https://api.music.yandex.net/get-file-info", params=params
    )
    resp = typing.cast(dict, resp)
    e = resp["download_info"]
    raw_codec = e["codec"]
    file_format = FILE_FORMAT_MAPPING.get(raw_codec)
    if file_format is None:
        raise ValueError(f"Unknown codec: {raw_codec}")
    return CustomDownloadInfo(
        quality=e["quality"],
        file_format=file_format,
        urls=e["urls"],
        bitrate=e["bitrate"],
        decryption_key=e.get("key"),
    )


def download_track(client: Client, download_info: CustomDownloadInfo) -> bytes:
    data = client.request.retrieve(random.choice(download_info.urls))
    if decryption_key := download_info.decryption_key:
        data = decrypt_data(data, decryption_key)
    return data


def decrypt_data(data: bytes, key: str) -> bytes:
    aes = AES.new(
        key=bytes.fromhex(key),
        nonce=bytes(12),
        mode=AES.MODE_CTR,
    )

    return aes.decrypt(data)
