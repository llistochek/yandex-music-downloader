import time
from dataclasses import dataclass

from pydantic import BaseModel
from yandex_music import Track

from ymd.music_api.file_format import FILE_FORMAT_MAPPING, FileFormat
from ymd.music_api.request_signing import sign_params
from ymd.music_api.track_info.params import (
    ApiTrackQuality,
    TrackInfoRequestParams,
)


@dataclass
class TrackDownloadInfo:
    quality: str
    file_format: FileFormat
    urls: list[str]
    decryption_key: str
    bitrate: int

def get_download_info(track: Track, quality: ApiTrackQuality) -> TrackDownloadInfo:
    '''
        Функция для получения информации о треке (для дальнейшего скачивания)

        track - искомый трек
        quality - желаемое качество 
    '''

    client = track.client

    if client is None:
        raise AssertionError(f"Track {track} has no attached client")

    params = TrackInfoRequestParams(
        ts=int(time.time()),
        trackId=int(track.id),
        quality=quality,
        codecs=",".join(FILE_FORMAT_MAPPING.keys()),
        transports="encraw",
    )


    signedParams = sign_params(params.toJsonType())

    resp = client.request.get(
        "https://api.music.yandex.net/get-file-info", params=signedParams, 
    )

    # Проверяем и валидируем ответ от Yandex Music API
    parsed = _RawTrackInfoResponse.model_validate(resp)

    download_info = parsed.download_info

    return TrackDownloadInfo(
        quality=download_info.quality,
        file_format=FILE_FORMAT_MAPPING[download_info.codec],
        urls=download_info.urls,
        bitrate=download_info.bitrate,
        decryption_key=download_info.key if download_info.key else "",
    )

class _RawTrackDownloadInfoResponse(BaseModel):
    quality: str
    codec: str
    urls: list[str]
    bitrate: int
    key: str | None = None

class _RawTrackInfoResponse(BaseModel):
    '''
        Модель ответа от Yandex Music API по endpoint:
        https://api.music.yandex.net/get-file-info

        download_info - Вложенная структура с информацией для скачивании трека
    '''
    download_info: _RawTrackDownloadInfoResponse
