import re
import typing
from datetime import datetime as dt
from pathlib import Path
from typing import Optional, Union

import eyed3
from eyed3.id3.frames import ImageFrame
from yandex_music import Track, YandexMusicObject

ENCODED_BY = "https://github.com/llistochek/yandex-music-downloader"
FILENAME_CLEAR_RE = re.compile(r"[^\w\-\'() ]+")

DEFAULT_PATH_PATTERN = Path("#album-artist", "#album", "#number - #title")
DEFAULT_COVER_RESOLUTION = 400


def full_title(obj: YandexMusicObject) -> Optional[str]:
    result = obj["title"]
    if result is None:
        return
    if version := obj["version"]:
        result += f" ({version})"
    return result


def prepare_track_path(
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
            replacement = FILENAME_CLEAR_RE.sub("_", replacement)
        path_str = path_str.replace(placeholder, replacement)
    path_str += ".mp3"
    return Path(path_str)


def set_id3_tags(
    path: Path,
    track: Track,
    lyrics: Optional[str],
    album_cover: Optional[bytes],
) -> None:
    album = track.albums[0]
    if album.release_date is not None:
        datetime = dt.fromisoformat(album.release_date)
        release_date = eyed3.core.Date(*datetime.timetuple()[:6])
    else:
        release_date = album.year
    audiofile = eyed3.load(path)
    assert audiofile

    tag = audiofile.initTag()

    tag.artist = chr(0).join(a.name for a in track.artists if a.name)
    tag.album_artist = album.artists[0].name
    tag.album = full_title(album)
    tag.title = full_title(track)
    if position := album.track_position:
        tag.track_num = position.index
        tag.disc_num = position.volume
    tag.release_date = tag.original_release_date = release_date
    tag.encoded_by = ENCODED_BY
    tag.audio_file_url = f"https://music.yandex.ru/album/{album.id}/track/{track.id}"

    if lyrics is not None:
        tag.lyrics.set(lyrics)
    if album_cover is not None:
        tag.images.set(ImageFrame.FRONT_COVER, album_cover, "image/jpeg")

    tag.save()


def download_track(
    track: Track,
    target_path: Path,
    cover_resolution: int = DEFAULT_COVER_RESOLUTION,
    quality: int = 0,
    add_lyrics: bool = False,
    embed_cover: bool = False,
    covers_cache: Optional[dict[int, bytes]] = None,
):
    if embed_cover and covers_cache is None:
        raise RuntimeError("covers_cache isn't provided")
    covers_cache = typing.cast(dict[int, bytes], covers_cache)
    album = track.albums[0]

    download_info = track.get_download_info()
    download_info = [e for e in download_info if e.codec == "mp3"]
    download_info.sort(key=lambda e: e.bitrate_in_kbps)
    target_info = download_info[-1] if quality == 1 else download_info[0]
    track.download(str(target_path), bitrate_in_kbps=target_info.bitrate_in_kbps)

    lyrics = None
    if add_lyrics and (lyrics_info := track.lyrics_info):
        if lyrics_info.has_available_text_lyrics:
            if track_lyrics := track.get_lyrics(format="TEXT"):
                lyrics = track_lyrics.fetch_lyrics()

    cover = None
    if track.cover_uri is not None:
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

    set_id3_tags(target_path, track, lyrics, cover)
