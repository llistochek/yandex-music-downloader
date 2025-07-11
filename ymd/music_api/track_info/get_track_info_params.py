
from enum import StrEnum

import pydantic
from yandex_music import JSONType


class ApiTrackQuality(StrEnum):
    '''
        Возможные качества трека
    '''
    LOW = "lq"
    NORMAL = "nq"
    LOSSLESS = "lossless"

class TrackInfoRequestParams(pydantic.BaseModel):
    '''
        Структура для запроса информации о треке через endpoint:
        https://api.music.yandex.net/get-file-info

        ts - timestamp текущего времени 
        trackId - идентификатор трека
        quality - качество трека ()
        codecs - список поддерживаемых кодеков
        transports - список поддерживаемых транспортов (протоколы)
    '''

    ts: int
    trackId: int
    quality: ApiTrackQuality
    codecs: str
    transports: str

    def toJsonType(self) -> dict[str, JSONType]:
        return {
            "ts": self.ts,
            "trackId": self.trackId,
            "quality": self.quality,
            "codecs": self.codecs,
            "transports": self.transports,
        }
