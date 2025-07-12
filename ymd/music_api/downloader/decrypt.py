
from Crypto.Cipher import AES


def decrypt_data(data: bytes, key: str) -> bytes:
    '''
        Функция расшифровывает трек data по указанному ключу key 
    '''
    aes = AES.new(
        key=bytes.fromhex(key),
        nonce=bytes(12),
        mode=AES.MODE_CTR,
    )

    return aes.decrypt(data)
