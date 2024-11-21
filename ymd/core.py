import datetime as dt
import random
import re
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3._frames import (
    APIC,
    TALB,
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
from yandex_music import Client, DownloadInfo, Track, YandexMusicObject

from ymd.api import get_lossless_info

UNSAFE_PATH_CLEAR_RE = re.compile(r"[/\\]+")
SAFE_PATH_CLEAR_RE = re.compile(r"[^\w\-\'() ]+")

DEFAULT_PATH_PATTERN = Path("#album-artist", "#album", "#number - #title")
DEFAULT_COVER_RESOLUTION = 400

MIN_COMPATIBILITY_LEVEL = 0
MAX_COMPATIBILITY_LEVEL = 1

AUDIO_FILE_SUFFIXES = {".mp3", ".flac", ".m4a"}


@dataclass
class DownloadableTrack:
    url: str
    bitrate: int
    codec: str
    path: Path
    track: Track


def init_client(token: str) -> Client:
    return Client(token).init()


def full_title(obj: YandexMusicObject) -> Optional[str]:
    result = obj["title"]
    if result is None:
        return
    if version := obj["version"]:
        result += f" ({version})"
    return result


def prepare_base_path(
    path_pattern: Path, track: Track, unsafe_path: bool = False
) -> Path:
    path_str = str(path_pattern)
    album = track.albums[0]
    artist = album.artists[0]
    track_position = album.track_position
    repl_dict: dict[str, Union[str, int, None]] = {
        "#number-padded": str(track_position.index).zfill(len(str(album.track_count)))
        if track_position
        else None,
        "#album-artist": album.artists[0].name,
        "#artist-id": artist.name,
        "#album-id": album.id,
        "#track-id": track.id,
        "#number": track_position.index if track_position else None,
        "#artist": artist.name,
        "#title": full_title(track),
        "#album": full_title(album),
        "#year": album.year,
    }
    for placeholder, replacement in repl_dict.items():
        replacement = str(replacement)
        if not unsafe_path:
            clear_re = SAFE_PATH_CLEAR_RE
        else:
            clear_re = UNSAFE_PATH_CLEAR_RE
        replacement = clear_re.sub("_", replacement)
        path_str = path_str.replace(placeholder, replacement)
    return Path(path_str)


def set_tags(
    path: Path,
    track: Track,
    lyrics: Optional[str],
    album_cover: Optional[bytes],
    compatibility_level: int,
) -> None:
    album = track.albums[0]
    track_artists = [a.name for a in track.artists if a.name]
    album_artists = [a.name for a in album.artists if a.name]
    tag = mutagen.File(path, [MP3, MP4, FLAC])  # type: ignore
    album_title = full_title(album)
    track_title = full_title(track)
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

        if lyrics:
            tag["USLT"] = USLT(encoding=3, text=lyrics)
        if album_cover:
            tag["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3, data=album_cover)

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
            tag["rldt"] = iso8601_release_date
        if release_year is not None:
            tag["\xa9day"] = release_year
        if track_number:
            tag["trkn"] = [(track_number, 0)]
        if disc_number:
            tag["disk"] = [(disc_number, 0)]

        if lyrics:
            tag["\xa9lyr"] = lyrics
        if album_cover:
            tag["covr"] = [MP4Cover(album_cover, imageformat=MP4Cover.FORMAT_JPEG)]
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

        if lyrics:
            tag["lyrics"] = lyrics
        if album_cover is not None:
            pic = Picture()
            pic.type = PictureType.COVER_FRONT
            pic.data = album_cover
            pic.mime = "image/jpeg"
            tag.add_picture(pic)
        tag["comment"] = track_url
    else:
        raise RuntimeError("Unknown file format")

    tag.save()


def download_track(
    track_info: DownloadableTrack,
    cover_resolution: int = DEFAULT_COVER_RESOLUTION,
    add_lyrics: bool = False,
    embed_cover: bool = False,
    covers_cache: Optional[dict[int, bytes]] = None,
    compatibility_level: int = 1,
):
    if embed_cover and covers_cache is None:
        raise RuntimeError("covers_cache isn't provided")
    covers_cache = typing.cast(dict[int, bytes], covers_cache)
    target_path = track_info.path
    track = track_info.track
    client = track.client
    assert client
    album = track.albums[0]

    client.request.download(track_info.url, str(target_path))

    lyrics = None
    if add_lyrics and (lyrics_info := track.lyrics_info):
        if lyrics_info.has_available_text_lyrics:
            if track_lyrics := track.get_lyrics(format="TEXT"):
                lyrics = track_lyrics.fetch_lyrics()

    cover = None
    if track.cover_uri is not None:
        if cover_resolution == -1:
            cover_size = "orig"
        else:
            cover_size = f"{cover_resolution}x{cover_resolution}"
        if embed_cover:
            album_id = album.id
            if album_id and (cached_cover := covers_cache.get(album_id)):
                cover = cached_cover
            else:
                cover_bytes = track.download_cover_bytes(size=cover_size)
                if album_id:
                    cover = covers_cache[album_id] = cover_bytes
        else:
            cover_path = target_path.parent / "cover.jpg"
            if not cover_path.is_file():
                track.download_cover(str(cover_path), cover_size)

    set_tags(target_path, track, lyrics, cover, compatibility_level)


def to_downloadable_track(
    track: Track, quality: int, base_path: Path
) -> DownloadableTrack:
    url: str
    codec: str
    bitrate: int
    codec: str
    if quality == 2:
        download_info = get_lossless_info(track)
        codec = download_info.codec
        url = random.choice(download_info.urls)
        bitrate = download_info.bitrate
    else:
        download_info = track.get_download_info(get_direct_links=True)
        download_info = [e for e in download_info if e.codec in ("mp3", "aac")]

        def sort_key(e: DownloadInfo) -> Union[int, float]:
            aac_multiplier = 1.5
            bitrate = e.bitrate_in_kbps
            if bitrate <= 192:
                aac_multiplier = 0.5
            if e.codec == "aac":
                bitrate *= aac_multiplier
            return bitrate

        download_info.sort(
            key=sort_key,
            reverse=quality == 0,
        )
        target_info = download_info[-1]
        url = typing.cast(str, target_info.direct_link)
        bitrate = target_info.bitrate_in_kbps
        codec = target_info.codec

    if codec == "mp3":
        suffix = ".mp3"
    elif codec == "aac" or codec == "he-aac":
        suffix = ".m4a"
    elif codec == "flac":
        suffix = ".flac"
    else:
        raise RuntimeError("Unknown codec")
    target_path = str(base_path) + suffix
    return DownloadableTrack(
        url=url,
        track=track,
        bitrate=bitrate,
        codec=codec,
        path=Path(target_path),
    )
