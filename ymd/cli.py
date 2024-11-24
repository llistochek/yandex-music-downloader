#!/bin/python3
import argparse
import itertools
import logging
import re
import time
import typing
from argparse import ArgumentTypeError
from collections.abc import Generator, Iterable
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

from yandex_music import Album, Playlist, Track

from ymd import core

DEFAULT_DELAY = 0

TRACK_RE = re.compile(r"track/(\d+)")
ALBUM_RE = re.compile(r"album/(\d+)$")
ARTIST_RE = re.compile(r"artist/(\d+)$")
PLAYLIST_RE = re.compile(r"([\w\-._]+)/playlists/(\d+)$")

logger = logging.getLogger("yandex-music-downloader")


def show_default(text: Optional[str] = None) -> str:
    default = "по умолчанию: %(default)s"
    if text is None:
        return default
    return f"{text} ({default})"


def quality_arg(astr: str) -> int:
    aint = int(astr)
    if 0 <= aint <= 2:
        return aint
    raise ArgumentTypeError("Значение должно быть в промежутке от 0 до 2")


def compatibility_level_arg(astr: str) -> int:
    aint = int(astr)
    min_val = core.MIN_COMPATIBILITY_LEVEL
    max_val = core.MAX_COMPATIBILITY_LEVEL
    if min_val <= aint <= max_val:
        return aint
    raise ArgumentTypeError(
        f"Значение должен быть в промежутке от {min_val} до {max_val}"
    )


def cover_resolution_arg(astr: str) -> int:
    if astr == "original":
        return -1
    return int(astr)


def lyrics_format_arg(astr: str) -> core.LyricsFormat:
    try:
        return core.LyricsFormat(astr)
    except ValueError:
        raise ArgumentTypeError(f"Допустимые значения: {','.join(core.LyricsFormat)}")


def main():
    parser = argparse.ArgumentParser(
        description="Загрузчик музыки с сервиса Яндекс.Музыка",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    common_group = parser.add_argument_group("Общие параметры")
    common_group.add_argument(
        "--quality",
        metavar="<Качество>",
        default=0,
        type=quality_arg,
        help="Качество трека:\n0 - Низкое (AAC 64kbps)\n1 - Высокое (MP3 320kbps)\n2 - Лучшее (FLAC)\n(по умолчанию: %(default)s)",
    )
    common_group.add_argument(
        "--skip-existing", action="store_true", help="Пропускать уже загруженные треки"
    )
    common_group.add_argument(
        "--lyrics-format",
        type=lyrics_format_arg,
        default=core.LyricsFormat.NONE,
        help=show_default("Формат текста песни"),
        choices=core.LyricsFormat,
    )
    common_group.add_argument(
        "--add-lyrics", action="store_true", help=argparse.SUPPRESS
    )
    common_group.add_argument(
        "--embed-cover", action="store_true", help="Встраивать обложку в аудиофайл"
    )
    common_group.add_argument(
        "--cover-resolution",
        default=core.DEFAULT_COVER_RESOLUTION,
        metavar="<Разрешение обложки>",
        type=cover_resolution_arg,
        help=show_default(
            'Разрешение обложки (в пикселях). Передайте "original" для загрузки в оригинальном (наилучшем) разрешении'
        ),
    )
    common_group.add_argument(
        "--delay",
        default=DEFAULT_DELAY,
        metavar="<Задержка>",
        type=int,
        help=show_default("Задержка между запросами, в секундах"),
    )
    common_group.add_argument(
        "--stick-to-artist",
        action="store_true",
        help="Загружать альбомы, созданные только данным исполнителем",
    )
    common_group.add_argument(
        "--only-music",
        action="store_true",
        help="Загружать только музыкальные альбомы"
        " (пропускать подкасты и аудиокниги)",
    )
    common_group.add_argument(
        "--compatibility-level",
        metavar="<Уровень совместимости>",
        default=1,
        type=compatibility_level_arg,
        help=show_default(
            f"Уровень совместимости, от {core.MIN_COMPATIBILITY_LEVEL} до {core.MAX_COMPATIBILITY_LEVEL}. См. README для подробного описания"
        ),
    )
    common_group.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)

    id_group_meta = parser.add_argument_group("ID")
    id_group = id_group_meta.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--artist-id", metavar="<ID исполнителя>")
    id_group.add_argument("--album-id", metavar="<ID альбома>")
    id_group.add_argument("--track-id", metavar="<ID трека>")
    id_group.add_argument(
        "--playlist-id",
        metavar="<владелец плейлиста>/<тип плейлиста>",
    )
    id_group.add_argument("-u", "--url", help="URL исполнителя/альбома/трека/плейлиста")

    path_group = parser.add_argument_group("Указание пути")
    path_group.add_argument(
        "--unsafe-path",
        action="store_true",
        help="Не очищать путь от недопустимых символов",
    )
    path_group.add_argument(
        "--dir",
        default=".",
        metavar="<Папка>",
        help=show_default("Папка для загрузки музыки"),
        type=Path,
    )
    path_group.add_argument(
        "--path-pattern",
        default=core.DEFAULT_PATH_PATTERN,
        metavar="<Паттерн>",
        type=Path,
        help=show_default(
            "Поддерживает следующие заполнители:"
            " #number, #artist, #album-artist, #title,"
            " #album, #year, #artist-id, #album-id, #track-id, #number-padded"
        ),
    )

    auth_group = parser.add_argument_group("Авторизация")
    auth_group.add_argument(
        "--token",
        required=True,
        metavar="<Токен>",
        help="Токен для авторизации. См. README для способов получения",
    )

    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s |%(levelname)s| %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if args.debug else logging.ERROR,
    )

    if args.add_lyrics:
        print(
            "Аргумент --add-lyrics устарел и будет удален в будущем. Используйте --lyrics-format"
        )
        args.lyrics_format = core.LyricsFormat.TEXT

    if args.url is not None:
        parsed_url = urlparse(args.url)
        path = parsed_url.path
        if match := ARTIST_RE.search(path):
            args.artist_id = match.group(1)
        elif match := ALBUM_RE.search(path):
            args.album_id = match.group(1)
        elif match := TRACK_RE.search(path):
            args.track_id = match.group(1)
        elif match := PLAYLIST_RE.search(path):
            args.playlist_id = match.group(1) + "/" + match.group(2)
        else:
            print("Параметер url указан в неверном формате")
            return 1

    client = core.init_client(args.token)
    result_tracks: Iterable[Track] = []

    def album_tracks_gen(album_ids: Iterable[Union[int, str]]) -> Generator[Track]:
        for album_id in album_ids:
            if full_album := client.albums_with_tracks(album_id):
                if volumes := full_album.volumes:
                    yield from itertools.chain.from_iterable(volumes)

    if args.artist_id is not None:

        def filter_album(album: Album) -> bool:
            title = album.title
            if album.id is None or not album.available:
                print(f'Альбом "{title}" не доступен для скачивания')
            elif args.only_music and album.meta_type != "music":
                print(f'Альбом "{title}" пропущен' " т.к. не является музыкальным")
            elif args.stick_to_artist and album.artists[0].id != int(args.artist_id):
                print(f'Альбом "{title}" пропущен' " из-за флага --stick-to-artist")
            else:
                return True
            return False

        def albums_gen() -> Generator[Album]:
            has_next = True
            page = 0
            while has_next:
                if albums := client.artists_direct_albums(args.artist_id, page):
                    yield from albums.albums
                else:
                    break
                if pager := albums.pager:
                    page = pager.page + 1
                    has_next = pager.per_page * page < pager.total
                else:
                    break

        result_tracks = album_tracks_gen(
            a.id for a in albums_gen() if filter_album(a) and a.id is not None
        )
    elif args.album_id is not None:
        result_tracks = album_tracks_gen((args.album_id,))
    elif args.track_id is not None:
        track = client.tracks(args.track_id)
        result_tracks = track
    elif args.playlist_id is not None:
        user, kind = args.playlist_id.split("/")
        playlist = typing.cast(Playlist, client.users_playlists(kind, user))

        def playlist_tracks_gen() -> Generator[Track]:
            tracks = playlist.fetch_tracks()
            for track in tracks:
                yield track.fetch_track()

        result_tracks = playlist_tracks_gen()

    covers_cache: dict[int, bytes] = {}
    for track in result_tracks:
        if not track.available:
            print(f"Трек {track.title} не доступен для скачивания")
            continue

        save_path = args.dir / core.prepare_base_path(
            args.path_pattern,
            track,
            args.unsafe_path,
        )
        if args.skip_existing:
            if any(
                Path(str(save_path) + s).is_file() for s in core.AUDIO_FILE_SUFFIXES
            ):
                continue

        save_dir = save_path.parent
        if not save_dir.is_dir():
            save_dir.mkdir(parents=True)

        downloadable = core.to_downloadable_track(track, args.quality, save_path)
        bitrate = downloadable.bitrate
        format_info = "[" + downloadable.codec.upper()
        if bitrate > 0:
            format_info += f" {bitrate}kbps"
        format_info += "]"
        print(f"{format_info} Загружается {downloadable.path}")
        core.download_track(
            track_info=downloadable,
            lyrics_format=args.lyrics_format,
            embed_cover=args.embed_cover,
            cover_resolution=args.cover_resolution,
            covers_cache=covers_cache,
            compatibility_level=args.compatibility_level,
        )
        if args.delay > 0:
            time.sleep(args.delay)
