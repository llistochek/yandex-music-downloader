import base64
import hashlib
import hmac
import time
import typing
from dataclasses import dataclass

from yandex_music import Track
from yandex_music.utils.sign_request import DEFAULT_SIGN_KEY


@dataclass
class LosslessDownloadInfo:
    quality: str
    codec: str
    urls: list[str]
    bitrate: int


def get_lossless_info(track: Track) -> LosslessDownloadInfo:
    client = track.client
    assert client
    timestamp = int(time.time())
    params = {
        "ts": timestamp,
        "trackId": track.id,
        "quality": "lossless",
        "codecs": "flac,aac,he-aac,mp3",
        "transports": "raw",
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
    return LosslessDownloadInfo(
        quality=e["quality"], codec=e["codec"], urls=e["urls"], bitrate=e["bitrate"]
    )
