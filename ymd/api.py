import base64
import hashlib
import hmac
import random
import time
import typing
from dataclasses import dataclass
from enum import Enum, auto

from Crypto.Cipher import AES
from pydantic import BaseModel
from strenum import StrEnum
from yandex_music import Client, Track
from yandex_music.base import JSONType
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
    '''
        Возможные качества трека
    '''
    LOW = "lq"
    NORMAL = "nq"
    LOSSLESS = "lossless"

class TrackInfoRequestParams(typing.TypedDict):
    '''
       Структура для запроса информации о треке через endpoint:
       https://api.music.yandex.net/get-file-info

       ts - timestamp текущего времени 
       trackId - идентификатор трека
       quality - качество трека ()
       codecs - список поддерживаемых кодеков
       transports - список поддерживаемых транспортов (протоколы)
       sign - HMAC подпись структура 
    '''

    ts: int
    trackId: int
    quality: ApiTrackQuality
    codecs: str
    transports: str



SignedTrackInfoRequestParams = dict[str, JSONType]

def _sign_params(params: TrackInfoRequestParams) -> SignedTrackInfoRequestParams:
    """
    Подписывает параметры запроса с использованием HMAC-SHA256.

    Алгоритм подписи:
    1. Извлекаются значения параметров в порядке: ts, trackId, quality, codecs, transports.
    2. Значения конкатенируются в одну строку без разделителей и запятых.
    3. Полученная строка кодируется в байты и используется как сообщение для HMAC.
    4. HMAC рассчитывается с использованием алгоритма SHA-256 и секретного ключа `DEFAULT_SIGN_KEY`.
    5. Результат кодируется в base64, после чего отрезается последний символ.
    6. Подпись добавляется в исходные параметры под ключом `sign`.
    """
    # Сериализация с сортировкой ключей и без пробелов
    serialized = "".join(str(e) for e in params.values()).replace(",", "")

    # Вычисление HMAC
    hmac_sign = hmac.new(
        DEFAULT_SIGN_KEY.encode(),
        serialized.encode(),
        hashlib.sha256,
    )

    # Base64 и обрезка последнего символа
    sign = base64.b64encode(hmac_sign.digest()).decode()[:-1]

    return {
        "ts": params["ts"],
        "trackId": params["trackId"],
        "quality": params["quality"],
        "codecs": params["codecs"],
        "transports": params["transports"],
        "sign": sign,
    }

@dataclass
class CustomDownloadInfo:
    quality: str
    file_format: FileFormat
    urls: list[str]
    decryption_key: str
    bitrate: int

class _TrackDownloadInfo(BaseModel):
    quality: str
    codec: str
    urls: list[str]
    bitrate: int
    key: str | None = None

class _TrackInfoResponseModel(BaseModel):
    '''
        Модель ответа от Yandex Music API по endpoint:
        https://api.music.yandex.net/get-file-info

        download_info - Вложенная структура с информацией для скачивании трека
    '''
    download_info: _TrackDownloadInfo

def get_download_info(track: Track, quality: ApiTrackQuality) -> CustomDownloadInfo:
    '''
        Функция для получения информации о треке (для дальнейшего скачивания)

        track - искомый трек
        quality - желаемое качество 
    '''

    client = track.client

    if client is None:
        raise AssertionError(f"Track {track} has no attached client")

    params: TrackInfoRequestParams = {
        "ts": int(time.time()),
        "trackId": int(track.id),
        "quality": quality,
        "codecs": ",".join(FILE_FORMAT_MAPPING.keys()),
        "transports": "encraw",
    }

    signedParams = _sign_params(params)

    resp = client.request.get(
        "https://api.music.yandex.net/get-file-info", params=signedParams, 
    )

    # Проверяем и валидируем ответ от Yandex Music API
    parsed = _TrackInfoResponseModel.model_validate(resp)

    download_info = parsed.download_info

    return CustomDownloadInfo(
        quality=download_info.quality,
        file_format=FILE_FORMAT_MAPPING[download_info.codec],
        urls=download_info.urls,
        bitrate=download_info.bitrate,
        decryption_key=download_info.key if download_info.key else "",
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
