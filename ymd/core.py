import datetime as dt
import hashlib
import re
import time
import typing
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, auto
from pathlib import Path
from typing import Optional, Union

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3._frames import (
    APIC,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TPOS,
    TRCK,
    USLT,
    WOAF,
)
from mutagen.id3._specs import ID3TimeStamp, PictureType
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from strenum import LowercaseStrEnum
from yandex_music import (
    Album,
    Client,
    Track,
    YandexMusicModel,
)
from yandex_music.exceptions import NetworkError

from ymd import api
from ymd.api import (
    ApiTrackQuality,
    Container,
    CustomDownloadInfo,
    get_download_info,
)
from ymd.mime_utils import MimeType, guess_mime_type

UNSAFE_PATH_CLEAR_RE = re.compile(r"[/\\]+")
SAFE_PATH_CLEAR_RE = re.compile(r"([^\w\-\'() ]|^\s+|\s+$)")

DEFAULT_PATH_PATTERN = Path("#album-artist", "#album", "#number - #title")
DEFAULT_COVER_RESOLUTION = 400

MIN_COMPATIBILITY_LEVEL = 0
MAX_COMPATIBILITY_LEVEL = 1

AUDIO_FILE_SUFFIXES = {".mp3", ".flac", ".m4a"}
TEMPORARY_FILE_NAME_TEMPLATE = ".yandex-music-downloader.{}.tmp"
MAX_FILE_NAME_LENGTH_WITHOUT_SUFFIX = 255 - max(
    len(suffix) for suffix in AUDIO_FILE_SUFFIXES
)


class CoreTrackQuality(IntEnum):
    LOW = 0
    NORMAL = auto()
    LOSSLESS = auto()


class LyricsFormat(LowercaseStrEnum):
    NONE = auto()
    TEXT = auto()
    LRC = auto()


CONTAINER_MUTAGEN_MAPPING: dict[Container, type[mutagen.FileType]] = {  # type: ignore
    Container.MP3: MP3,
    Container.FLAC: FLAC,
    Container.MP4: MP4,
}


@dataclass
class DownloadableTrack:
    download_info: CustomDownloadInfo
    path: Path
    track: Track


@dataclass
class AlbumCover:
    data: bytes
    mime_type: MimeType


def init_client(
    token: str, timeout: int, max_try_count: int, retry_delay: int
) -> Client:
    assert timeout > 0
    assert max_try_count >= 0
    assert retry_delay >= 0

    client = Client(token)
    client.request.set_timeout(timeout)

    original_wrapper = client.request._request_wrapper

    def retry_wrapper(*args, **kwargs):
        try_count = 0
        while True:
            try:
                return original_wrapper(*args, **kwargs)
            except NetworkError as error:
                if max_try_count == 0 or try_count < max_try_count:
                    try_count += 1
                    time.sleep(retry_delay)
                    continue
                raise error

    client.request._request_wrapper = retry_wrapper
    return client.init()


def full_title(obj: YandexMusicModel) -> str:
    result = obj["title"]
    if result is None:
        return ""
    if version := obj["version"]:
        result += f" ({version})"
    return result


def prepare_base_path(
    path_pattern: Path, track: Track, unsafe_path: bool = False
) -> Path:
    path_str = str(path_pattern)
    album = None
    album_artist = None
    track_artist = None
    track_position = None
    if albums := track.albums:
        album = albums[0]
        track_position = album.track_position
        if artists := album.artists:
            album_artist = artists[0]
    if artists := track.artists:
        track_artist = artists[0]
    repl_dict: dict[str, Union[str, int, None]] = {
        "#number-padded": str(track_position.index).zfill(len(str(album.track_count)))
        if track_position and album
        else None,
        "#album-artist": album_artist.name if album_artist else None,
        "#track-artist": track_artist.name if track_artist else None,
        "#artist-id": track_artist.id if track_artist else None,
        "#album-id": album.id if album else None,
        "#track-id": track.id,
        "#number": track_position.index if track_position else None,
        "#title": full_title(track),
        "#album": full_title(album) if album else None,
        "#year": album.year if album else None,
    }
    for placeholder, replacement in repl_dict.items():
        replacement = str(replacement)
        if not unsafe_path:
            clear_re = SAFE_PATH_CLEAR_RE
        else:
            clear_re = UNSAFE_PATH_CLEAR_RE
        replacement = clear_re.sub("_", replacement)
        path_str = path_str.replace(placeholder, replacement)
    path = Path(path_str)
    trimmed_parts = [
        part
        if len(part) <= MAX_FILE_NAME_LENGTH_WITHOUT_SUFFIX
        else part[:MAX_FILE_NAME_LENGTH_WITHOUT_SUFFIX]
        for part in path.parts
    ]
    return Path(*trimmed_parts)


def set_tags(
    path: Path,
    track: Track,
    container: Container,
    lyrics: Optional[str],
    album_cover: Optional[AlbumCover],
    compatibility_level: int,
) -> None:
    file_type = CONTAINER_MUTAGEN_MAPPING.get(container)
    if file_type is None:
        raise ValueError(f"Unknown container: {container}")

    tag = file_type(path)
    album = track.albums[0] if track.albums else Album()
    album_title = full_title(album)
    track_title = full_title(track)
    track_artists = [a.name for a in track.artists if a.name]
    album_artists = [a.name for a in album.artists if a.name]
    genre = None
    if album.genre:
        genre = album.genre
    track_number = None
    disc_number = None
    if position := album.track_position:
        track_number = position.index
        disc_number = position.volume
    iso8601_release_date = None
    release_year: Optional[str] = None
    if album.release_date is not None:
        iso8601_release_date = dt.datetime.fromisoformat(album.release_date).astimezone(
            dt.timezone.utc
        )
        release_year = str(iso8601_release_date.year)
        iso8601_release_date = iso8601_release_date.strftime("%Y-%m-%d %H:%M:%S")
    if year := album.year:
        release_year = str(year)
    track_url = f"https://music.yandex.ru/album/{album.id}/track/{track.id}"

    if isinstance(tag, MP3):
        tag["TIT2"] = TIT2(encoding=3, text=track_title)
        tag["TALB"] = TALB(encoding=3, text=album_title)
        tag["TPE1"] = TPE1(encoding=3, text=track_artists)
        tag["TPE2"] = TPE2(encoding=3, text=album_artists)

        if tdrc_text := iso8601_release_date or release_year:
            tag["TDRC"] = TDRC(encoding=3, text=[ID3TimeStamp(tdrc_text)])
        if track_number:
            tag["TRCK"] = TRCK(encoding=3, text=str(track_number))
        if disc_number:
            tag["TPOS"] = TPOS(encoding=3, text=str(disc_number))
        if genre:
            tag["TCON"] = TCON(encoding=3, text=genre)

        if lyrics:
            tag["USLT"] = USLT(encoding=3, text=lyrics)
        if album_cover:
            tag["APIC"] = APIC(
                encoding=3,
                mime=album_cover.mime_type.value,
                type=3,
                data=album_cover.data,
            )

        tag["WOAF"] = WOAF(
            encoding=3,
            text=track_url,
        )
    elif isinstance(tag, MP4):
        tag["\xa9nam"] = track_title
        tag["\xa9alb"] = album_title
        artists_value = track_artists
        album_artists_value = album_artists
        if compatibility_level == 1:
            artists_value = "; ".join(track_artists)
            album_artists_value = "; ".join(album_artists)
        tag["\xa9ART"] = artists_value
        tag["aART"] = album_artists_value

        if iso8601_release_date is not None:
            tag["\xa9day"] = iso8601_release_date
        elif release_year is not None:
            tag["\xa9day"] = release_year
        if track_number:
            tag["trkn"] = [(track_number, 0)]
        if disc_number:
            tag["disk"] = [(disc_number, 0)]
        if genre:
            tag["\xa9gen"] = genre

        if lyrics:
            tag["\xa9lyr"] = lyrics
        if album_cover:
            mime_mp4_dict = {
                MimeType.JPEG: MP4Cover.FORMAT_JPEG,
                MimeType.PNG: MP4Cover.FORMAT_PNG,
            }
            mp4_image_format = mime_mp4_dict.get(album_cover.mime_type)
            if mp4_image_format is None:
                raise RuntimeError("Unsupported cover type")
            tag["covr"] = [MP4Cover(album_cover.data, imageformat=mp4_image_format)]
        tag["\xa9cmt"] = track_url
    elif isinstance(tag, FLAC):
        tag["title"] = track_title
        tag["album"] = album_title
        tag["artist"] = track_artists
        tag["albumartist"] = album_artists

        if date_text := iso8601_release_date or release_year:
            tag["date"] = date_text
        if track_number:
            tag["tracknumber"] = str(track_number)
        if disc_number:
            tag["discnumber"] = str(disc_number)
        if genre:
            tag["genre"] = genre

        if lyrics:
            tag["lyrics"] = lyrics
        if album_cover is not None:
            pic = Picture()
            pic.type = PictureType.COVER_FRONT
            pic.data = album_cover.data
            pic.mime = album_cover.mime_type.value
            tag.add_picture(pic)
        tag["comment"] = track_url
    else:
        raise RuntimeError("Unknown file format")

    tag.save()


def download_track(
    track_info: DownloadableTrack,
    cover_resolution: int = DEFAULT_COVER_RESOLUTION,
    lyrics_format: LyricsFormat = LyricsFormat.NONE,
    embed_cover: bool = False,
    covers_cache: Optional[dict[int, AlbumCover]] = None,
    compatibility_level: int = 1,
):
    if embed_cover and covers_cache is None:
        raise RuntimeError("covers_cache isn't provided")
    covers_cache = typing.cast(dict[int, AlbumCover], covers_cache)
    target_path = track_info.path
    track = track_info.track
    client = typing.cast(Client, track.client)
    assert client

    text_lyrics = None
    if lyrics_format != LyricsFormat.NONE and (lyrics_info := track.lyrics_info):
        if lyrics_format == LyricsFormat.LRC and lyrics_info.has_available_sync_lyrics:
            lrc_path = target_path.with_suffix(".lrc")
            if not lrc_path.is_file() and (
                track_lyrics := track.get_lyrics(format_="LRC")
            ):
                lyrics = track_lyrics.fetch_lyrics()
                write_via_temporary_file(lyrics.encode("utf-8"), lrc_path)
        elif lyrics_info.has_available_text_lyrics:
            if track_lyrics := track.get_lyrics(format_="TEXT"):
                text_lyrics = track_lyrics.fetch_lyrics()

    cover = None
    if track.cover_uri is not None:
        if cover_resolution == -1:
            cover_size = "orig"
        else:
            cover_size = f"{cover_resolution}x{cover_resolution}"
        cover_bytes = track.download_cover_bytes(size=cover_size)
        mime_type = guess_mime_type(cover_bytes)
        if mime_type is None:
            raise RuntimeError("Unknown cover mime type")
        album_cover = AlbumCover(data=cover_bytes, mime_type=mime_type)
        if embed_cover:
            album = track.albums[0] if track.albums else Album()
            if album.id and (cached_cover := covers_cache.get(album.id)):
                cover = cached_cover
            else:
                if album.id:
                    cover = covers_cache[album.id] = album_cover
        else:
            mime_suffix_dict = {MimeType.JPEG: ".jpg", MimeType.PNG: ".png"}
            file_suffix = mime_suffix_dict.get(album_cover.mime_type)
            if file_suffix is None:
                raise RuntimeError("Unknown mime type")
            cover_path = target_path.parent / ("cover" + file_suffix)
            if not cover_path.is_file():
                write_via_temporary_file(album_cover.data, cover_path)

    download_info = track_info.download_info
    track_data = api.download_track(client, download_info)

    write_via_temporary_file(
        track_data,
        target_path,
        temporary_file_hook=lambda tmp_path: set_tags(
            tmp_path,
            track,
            download_info.file_format.container,
            text_lyrics,
            cover,
            compatibility_level,
        ),
    )


def to_downloadable_track(
    track: Track, quality: CoreTrackQuality, base_path: Path
) -> DownloadableTrack:
    api_quality = ApiTrackQuality.NORMAL
    if quality == CoreTrackQuality.LOW:
        api_quality = ApiTrackQuality.LOW
    elif quality == CoreTrackQuality.NORMAL:
        api_quality = ApiTrackQuality.NORMAL
    elif quality == CoreTrackQuality.LOSSLESS:
        api_quality = ApiTrackQuality.LOSSLESS

    download_info = get_download_info(track, api_quality)
    container = download_info.file_format.container

    if container == Container.MP3:
        suffix = ".mp3"
    elif container == Container.MP4:
        suffix = ".m4a"
    elif container == Container.FLAC:
        suffix = ".flac"
    else:
        raise RuntimeError("Unknown codec")

    target_path = str(base_path) + suffix
    return DownloadableTrack(
        download_info=download_info,
        track=track,
        path=Path(target_path),
    )


def write_via_temporary_file(
    data: bytes,
    target_path: Path,
    temporary_file_hook: Optional[Callable[[Path], None]] = None,
) -> Path:
    target_name = hashlib.sha256(target_path.name.encode()).hexdigest()
    temporary_file = target_path.parent / (
        TEMPORARY_FILE_NAME_TEMPLATE.format(target_name)
    )
    try:
        temporary_file.write_bytes(data)
        if temporary_file_hook is not None:
            temporary_file_hook(temporary_file)
    except InterruptedError as e:
        temporary_file.unlink()
        raise e
    temporary_file.rename(target_path)
    return target_path
