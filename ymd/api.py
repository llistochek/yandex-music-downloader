import base64
import hashlib
import hmac
import itertools
import random
import time
import typing
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from Crypto.Cipher import AES
from strenum import StrEnum
from yandex_music import Client, Track
from yandex_music.utils.sign_request import DEFAULT_SIGN_KEY


class Codec(Enum):
    FLAC = ["flac", "flac-mp4"]
    MP3 = ["mp3"]
    AAC = ["aac", "he-aac", "aac-mp4", "he-aac-mp4"]

    @classmethod
    def get_all_codecs(cls) -> Iterable[str]:
        return itertools.chain.from_iterable(e.value for e in cls)

    @classmethod
    def from_codec_str(cls, codec_str: str) -> typing.Optional["Codec"]:
        for codec in cls:
            if any(e == codec_str for e in codec.value):
                return codec


class ApiTrackQuality(StrEnum):
    LOW = "lq"
    NORMAL = "nq"
    LOSSLESS = "lossless"


@dataclass
class CustomDownloadInfo:
    quality: str
    codec: Codec
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
        "codecs": ",".join(Codec.get_all_codecs()),
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
    codec = Codec.from_codec_str(raw_codec)
    if codec is None:
        raise ValueError(f"Unknown codec: {raw_codec}")
    return CustomDownloadInfo(
        quality=e["quality"],
        codec=codec,
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
