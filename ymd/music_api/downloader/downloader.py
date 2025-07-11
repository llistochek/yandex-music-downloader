
import random

from yandex_music import Client

from ymd.music_api.downloader.decrypt import decrypt_data
from ymd.music_api.track_info.fetch import TrackDownloadInfo


def download_track(client: Client, download_info: TrackDownloadInfo) -> bytes:
    data = client.request.retrieve(random.choice(download_info.urls))
    if decryption_key := download_info.decryption_key:
        data = decrypt_data(data, decryption_key)
    return data

