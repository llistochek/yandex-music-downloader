#!/bin/python3
import argparse
import itertools
import logging
import re
import time
import typing
from argparse import ArgumentTypeError
from collections.abc import Callable, Generator, Iterable
from pathlib import Path
from urllib.parse import urlparse

from yandex_music import Album, Playlist, Track

from ymd import core

DEFAULT_DELAY = 0

TRACK_RE = re.compile(r"track/(\d+)")
ALBUM_RE = re.compile(r"album/(\d+)$")
ARTIST_RE = re.compile(r"artist/(\d+)$")
PLAYLIST_RE = re.compile(r"([\w\-._@]+)/playlists/(\d+)$")

FETCH_PAGE_SIZE = 10

logger = logging.getLogger("yandex-music-downloader")


def show_default(text: str | None = None) -> str:
    default = "по умолчанию: %(default)s"
    if text is None:
        return default
    return f"{text} ({default})"


def checked_int_arg(
    min_value: int, max_value: int | None = None
) -> Callable[[str], int]:
    def func(astr: str) -> int:
        aint = int(astr)
        if aint >= min_value and (max_value is None or aint <= max_value):
            return aint
        error_text = f"Значение должен быть >= {min_value}"
        if max_value is not None:
            error_text += f" и <= {max_value}"
        raise ArgumentTypeError(error_text)

    return func


def cover_resolution_arg(astr: str) -> int:
    if astr == "original":
        return -1
    return checked_int_arg(100)(astr)


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
    _ = common_group.add_argument(
        "--quality",
        metavar="<Качество>",
        default=0,
        type=checked_int_arg(0, 2),
        help="Качество трека:\n0 - Низкое (AAC 64kbps)\n1 - Оптимальное (AAC 192kbps)\n2 - Лучшее (FLAC)\n(по умолчанию: %(default)s)",
    )
    _ = common_group.add_argument(
        "--skip-existing", action="store_true", help="Пропускать уже загруженные треки"
    )
    _ = common_group.add_argument(
        "--lyrics-format",
        type=lyrics_format_arg,
        default=core.LyricsFormat.NONE,
        help=show_default("Формат текста песни"),
        choices=core.LyricsFormat,
    )
    _ = common_group.add_argument(
        "--add-lyrics", action="store_true", help=argparse.SUPPRESS
    )
    _ = common_group.add_argument(
        "--embed-cover", action="store_true", help="Встраивать обложку в аудиофайл"
    )
    _ = common_group.add_argument(
        "--cover-resolution",
        default=core.DEFAULT_COVER_RESOLUTION,
        metavar="<Разрешение обложки>",
        type=cover_resolution_arg,
        help=show_default(
            'Разрешение обложки (в пикселях). Передайте "original" для загрузки в оригинальном (наилучшем) разрешении'
        ),
    )
    _ = common_group.add_argument(
        "--delay",
        default=DEFAULT_DELAY,
        metavar="<Задержка>",
        type=checked_int_arg(0),
        help=show_default("Задержка между запросами, в секундах"),
    )
    _ = common_group.add_argument(
        "--stick-to-artist",
        action="store_true",
        help="Загружать альбомы, созданные только данным исполнителем",
    )
    _ = common_group.add_argument(
        "--only-music",
        action="store_true",
        help="Загружать только музыкальные альбомы (пропускать подкасты и аудиокниги)",
    )
    _ = common_group.add_argument(
        "--compatibility-level",
        metavar="<Уровень совместимости>",
        default=1,
        type=checked_int_arg(
            core.MIN_COMPATIBILITY_LEVEL, core.MAX_COMPATIBILITY_LEVEL
        ),
        help=show_default(
            f"Уровень совместимости, от {core.MIN_COMPATIBILITY_LEVEL} до {core.MAX_COMPATIBILITY_LEVEL}. См. README для подробного описания"
        ),
    )

    network_group = parser.add_argument_group("Сетевые параметры")
    _ = network_group.add_argument(
        "--timeout",
        metavar="<Время ожидания>",
        default=20,
        type=checked_int_arg(1),
        help=show_default(
            "Время ожидания ответа от сервера, в секундах. Увеличьте если возникают сетевые ошибки"
        ),
    )
    _ = network_group.add_argument(
        "--tries",
        metavar="<Количество попыток>",
        default=20,
        type=checked_int_arg(0),
        help=show_default(
            "Количество попыток при возникновении сетевых ошибок. 0 - бесконечное количество попыток"
        ),
    )
    _ = network_group.add_argument(
        "--retry-delay",
        metavar="<Задержка>",
        default=5,
        type=checked_int_arg(0),
        help=show_default("Задержка между повторными запросами при сетевых ошибках"),
    )
    _ = common_group.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)

    id_group_meta = parser.add_argument_group("ID")
    id_group = id_group_meta.add_mutually_exclusive_group(required=True)
    _ = id_group.add_argument("--artist-id", metavar="<ID исполнителя>")
    _ = id_group.add_argument("--album-id", metavar="<ID альбома>")
    _ = id_group.add_argument("--track-id", metavar="<ID трека>")
    _ = id_group.add_argument(
        "--playlist-id",
        metavar="<владелец плейлиста>/<тип плейлиста>",
    )
    _ = id_group.add_argument("-u", "--url", help="URL исполнителя/альбома/трека/плейлиста")

    path_group = parser.add_argument_group("Указание пути")
    _ = path_group.add_argument(
        "--unsafe-path",
        action="store_true",
        help="Не очищать путь от недопустимых символов",
    )
    _ = path_group.add_argument(
        "--dir",
        default=".",
        metavar="<Папка>",
        help=show_default("Папка для загрузки музыки"),
        type=Path,
    )
    _ = path_group.add_argument(
        "--path-pattern",
        default=core.DEFAULT_PATH_PATTERN,
        metavar="<Паттерн>",
        type=Path,
        help=show_default(
            "Поддерживает следующие заполнители:" +
            " #number, #track-artist, #album-artist, #title," +
            " #album, #year, #artist-id, #album-id, #track-id, #number-padded"
        ),
    )

    auth_group = parser.add_argument_group("Авторизация")
    _ = auth_group.add_argument(
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

    client = core.init_client(
        token=args.token,
        timeout=args.timeout,
        max_try_count=args.tries,
        retry_delay=args.retry_delay,
    )
    result_tracks: Iterable[Track]

    def album_tracks_gen(album_ids: Iterable[int | str]) -> Generator[Track]:
        for album_id in album_ids:
            if full_album := client.albums_with_tracks(album_id):
                if volumes := full_album.volumes:
                    yield from itertools.chain.from_iterable(volumes)

    total_track_count = None
    if args.artist_id is not None:

        def filter_album(album: Album) -> bool:
            title = album.title
            if album.id is None or not album.available:
                print(f'Альбом "{title}" не доступен для скачивания')
            elif args.only_music and album.meta_type != "music":
                print(f'Альбом "{title}" пропущен т.к. не является музыкальным')
            elif args.stick_to_artist and album.artists[0].id != int(args.artist_id):
                print(f'Альбом "{title}" пропущен из-за флага --stick-to-artist')
            else:
                return True
            return False

        def albums_id_gen() -> Generator[int]:
            has_next = True
            page = 0
            while has_next:
                if albums_info := client.artists_direct_albums(args.artist_id, page):
                    for album in albums_info.albums:
                        if filter_album(album):
                            assert album.id
                            yield album.id
                        else:
                            nonlocal total_track_count
                            if (
                                track_count := album.track_count
                            ) and total_track_count is not None:
                                total_track_count -= track_count
                else:
                    break
                if pager := albums_info.pager:
                    page = pager.page + 1
                    has_next = pager.per_page * page < pager.total
                else:
                    break

        result_tracks = album_tracks_gen(albums_id_gen())
        artist = client.artists(args.artist_id)[0]
        if counts := artist.counts:
            total_track_count = counts.tracks

    elif args.album_id is not None:
        result_tracks = album_tracks_gen((args.album_id,))
        if album := client.albums_with_tracks(args.album_id):
            total_track_count = album.track_count
    elif args.track_id is not None:
        track = client.tracks(args.track_id)
        result_tracks = track
        total_track_count = 1
    elif args.playlist_id is not None:
        user, kind = args.playlist_id.split("/")
        playlist = typing.cast(Playlist, client.users_playlists(kind, user))
        total_track_count = playlist.track_count

        def playlist_tracks_gen() -> Generator[Track]:
            tracks = playlist.fetch_tracks()
            for i in range(0, len(tracks), FETCH_PAGE_SIZE):
                yield from client.tracks(
                    [track.id for track in tracks[i : i + FETCH_PAGE_SIZE]]
                )

        result_tracks = playlist_tracks_gen()
    else:
        raise ValueError("Invalid ID argument")

    track_counter = 0
    progress_status = ""
    covers_cache = {}
    for track in result_tracks:
        if total_track_count:
            track_counter += 1
            progress_status = f"[{track_counter}/{total_track_count}] "

        if not track.available:
            print(f"{progress_status}Трек {track.title} не доступен для скачивания")
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
        bitrate = downloadable.download_info.bitrate
        format_info = "[" + downloadable.download_info.file_format.codec.name
        if bitrate > 0:
            format_info += f" {bitrate}kbps"
        format_info += "]"
        print(f"{progress_status}{format_info} Загружается {downloadable.path}")
        core.core_download_track(
            track_info=downloadable,
            lyrics_format=args.lyrics_format,
            embed_cover=args.embed_cover,
            cover_resolution=args.cover_resolution,
            covers_cache=covers_cache,
            compatibility_level=args.compatibility_level,
        )
        if args.delay > 0:
            time.sleep(args.delay)
