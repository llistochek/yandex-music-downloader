import re
import urllib.parse
from pathlib import Path
from typing import Optional

import eyed3
from eyed3.id3.frames import ImageFrame
from requests import Session

from ymd import http_utils
from ymd.ym_api import BasicTrackInfo, FullTrackInfo, api

ENCODED_BY = 'https://github.com/llistochek/yandex-music-downloader'
FILENAME_CLEAR_RE = re.compile(r'[^\w\-\'() ]+')

DEFAULT_PATH_PATTERN = Path('#album-artist', '#album', '#number - #title')
DEFAULT_COVER_RESOLUTION = 400


def prepare_track_path(path_pattern: Path,
                       track: BasicTrackInfo,
                       unsafe_path: bool = False) -> Path:
    path_str = str(path_pattern)
    album = track.album
    artist = album.artists[0]
    repl_dict = {
        '#album-artist': album.artists[0].name,
        '#artist-id': artist.name,
        '#album-id': album.id,
        '#track-id': track.id,
        '#number': track.number,
        '#artist': artist.name,
        '#title': track.title,
        '#album': album.title,
        '#year': album.year
    }
    for placeholder, replacement in repl_dict.items():
        replacement = str(replacement)
        if not unsafe_path:
            replacement = FILENAME_CLEAR_RE.sub('_', replacement)
        path_str = path_str.replace(placeholder, replacement)
    path_str += '.mp3'
    return Path(path_str)


def set_id3_tags(path: Path, track: BasicTrackInfo, lyrics: Optional[str],
                 album_cover: Optional[bytes]) -> None:
    if track.album.release_date is not None:
        release_date = eyed3.core.Date(
            *track.album.release_date.timetuple()[:6])
    else:
        release_date = track.album.year
    audiofile = eyed3.load(path)
    assert audiofile

    tag = audiofile.initTag()

    tag.artist = chr(0).join(a.name for a in track.artists)
    tag.album_artist = track.album.artists[0].name
    tag.album = track.album.title
    tag.title = track.title
    tag.track_num = track.number
    tag.disc_num = track.disc_number
    tag.release_date = tag.original_release_date = release_date
    tag.encoded_by = ENCODED_BY
    tag.audio_file_url = track.url

    if lyrics is not None:
        tag.lyrics.set(lyrics)
    if album_cover is not None:
        tag.images.set(ImageFrame.FRONT_COVER, album_cover, 'image/jpeg')

    tag.save()


def setup_session(session: Session, session_id: str,
                  user_agent: str) -> Session:
    session.cookies.set('Session_id', session_id, domain='yandex.ru')
    session.headers['User-Agent'] = user_agent
    session.headers['X-Retpath-Y'] = urllib.parse.quote_plus(
        'https://music.yandex.ru')
    return session


def download_track(session: Session,
                   track: BasicTrackInfo,
                   target_path: Path,
                   covers_cache: dict[str, bytes],
                   cover_resolution: int = DEFAULT_COVER_RESOLUTION,
                   hq: bool = False,
                   add_lyrics: bool = False,
                   embed_cover: bool = False):

    album = track.album

    url = api.get_track_download_url(session, track, hq)
    http_utils.download_file(session, url, target_path)

    lyrics = None
    if add_lyrics and track.has_lyrics:
        if isinstance(track, FullTrackInfo):
            lyrics = track.lyrics
        else:
            full_track = api.get_full_track_info(session, track.id)
            lyrics = full_track.lyrics

    cover = None
    cover_url = track.cover_info.cover_url(cover_resolution)
    if cover_url is not None:
        if embed_cover:
            if cached_cover := covers_cache.get(album.id):
                cover = cached_cover
            else:
                cover = covers_cache[album.id] = http_utils.download_bytes(
                    session, cover_url)
        else:
            cover_path = target_path.parent / 'cover.jpg'
            if not cover_path.is_file():
                http_utils.download_file(session, cover_url, cover_path)

    set_id3_tags(target_path, track, lyrics, cover)
