import base64
import hashlib
import hmac
import time
import typing
from dataclasses import dataclass

from yandex_music import Track
from yandex_music.utils.sign_request import DEFAULT_SIGN_KEY
import requests

@dataclass
class LosslessDownloadInfo:
    quality: str
    codec: str
    urls: list[str]
    bitrate: int

def get_lossless_info(track: Track, retries: int = 3, delay: float = 2.0) -> LosslessDownloadInfo:
    client = track.client
    if not client:
        raise ValueError("Track object does not have an associated client.")

    for attempt in range(retries):
        try:
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
            download_info = resp["download_info"]

            return LosslessDownloadInfo(
                quality=download_info["quality"],
                codec=download_info["codec"],
                urls=download_info["urls"],
                bitrate=download_info["bitrate"],
            )

        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise Exception("Failed to fetch lossless info after retries.") from e
        except KeyError as e:
            raise ValueError(f"Unexpected response format: {resp}") from e
