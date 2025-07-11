
import random

from Crypto.Cipher import AES
from yandex_music import Client

from ymd.music_api.track_info.get_track_info import TrackDownloadInfo


def _decrypt_data(data: bytes, key: str) -> bytes:
    aes = AES.new(
        key=bytes.fromhex(key),
        nonce=bytes(12),
        mode=AES.MODE_CTR,
    )

    return aes.decrypt(data)

def download_track(client: Client, download_info: TrackDownloadInfo) -> bytes:
    data = client.request.retrieve(random.choice(download_info.urls))
    if decryption_key := download_info.decryption_key:
        data = _decrypt_data(data, decryption_key)
    return data


