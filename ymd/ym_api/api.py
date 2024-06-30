import hashlib
import xml.etree.ElementTree as ET

from requests import Session

from .models import *

MD5_SALT = "XGRlBW9FXlekgbPrRHuSiA"


def get_track_download_url(session: Session, track: BasicTrackInfo, hq: bool) -> str:
    resp = session.get(
        "https://music.yandex.ru/api/v2.1/handlers/track"
        f"/{track.id}:{track.album.id}"
        "/web-album_track-track-track-main/download/m"
        f"?hq={int(hq)}"
    )
    url_info_src = resp.json()["src"]

    resp = session.get("https:" + url_info_src)
    url_info = ET.fromstring(resp.text)
    path = url_info.find("path").text[1:]
    s = url_info.find("s").text
    ts = url_info.find("ts").text
    host = url_info.find("host").text
    path_hash = hashlib.md5((MD5_SALT + path + s).encode()).hexdigest()
    return f"https://{host}/get-mp3/{path_hash}/{ts}/{path}?track-id={track.id}"


def get_full_track_info(session: Session, track_id: str) -> Optional[FullTrackInfo]:
    params = {"track": track_id, "lang": "ru"}
    resp = session.get("https://music.yandex.ru/handlers/track.jsx", params=params)
    return FullTrackInfo.from_json(resp.json())


def get_full_album_info(session: Session, album_id: str) -> FullAlbumInfo:
    params = {"album": album_id, "lang": "ru"}
    resp = session.get("https://music.yandex.ru/handlers/album.jsx", params=params)
    return FullAlbumInfo.from_json(resp.json())


def get_artist_info(session: Session, artist_id: str) -> FullArtistInfo:
    params = {"artist": artist_id, "what": "albums", "lang": "ru"}
    resp = session.get("https://music.yandex.ru/handlers/artist.jsx", params=params)
    return FullArtistInfo.from_json(resp.json())


def get_playlist(session: Session, playlist: PlaylistId) -> list[BasicTrackInfo]:
    params = {"owner": playlist.owner, "kinds": playlist.kind, "lang": "ru"}
    resp = session.get("https://music.yandex.ru/handlers/playlist.jsx", params=params)
    raw_tracks = resp.json()["playlist"].get("tracks", [])
    tracks = map(BasicTrackInfo.from_json, raw_tracks)
    tracks = [t for t in tracks if t is not None]
    return tracks
