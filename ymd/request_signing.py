
import base64
import hashlib
import hmac

from yandex_music import JSONType
from yandex_music.utils.sign_request import DEFAULT_SIGN_KEY


def sign_params(params: dict[str, JSONType]) -> dict[str, JSONType]:
    """
    JSON на входе --> Подпись 🔐 --> JSON параметры + подпись

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