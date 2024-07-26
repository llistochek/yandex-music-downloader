#!/bin/python3
import argparse
import datetime as dt
import logging
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import browser_cookie3
from browser_cookie3 import BrowserCookieError
from requests import Session

from ymd import core
from ymd.ym_api import BasicTrackInfo, PlaylistId, YandexMusicApi, api

DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36"
DEFAULT_DELAY = 3
DEFAULT_DOMAIN = "music.yandex.ru"
SUPPORTED_BROWSERS = [
    "chrome",
    "opera",
    "opera_gx",
    "firefox",
    "edge",
    "safari",
    "chromium",
    "vivaldi",
    "librewolf",
]

CACHE_EXPIRE_AFTER = dt.timedelta(hours=8)
CACHE_DIR = Path(tempfile.gettempdir()) / "ymd"

TRACK_RE = re.compile(r"track/(\d+)")
ALBUM_RE = re.compile(r"album/(\d+)$")
ARTIST_RE = re.compile(r"artist/(\d+)$")
PLAYLIST_RE = re.compile(r"([\w\-._]+)/playlists/(\d+)$")

logger = logging.getLogger("yandex-music-downloader")


def args_playlist_id(arg: str) -> api.PlaylistId:
    arr = arg.split("/")
    return PlaylistId(owner=arr[0], kind=int(arr[1]))


def show_default(text: Optional[str] = None) -> str:
    default = "по умолчанию: %(default)s"
    if text is None:
        return default
    return f"{text} ({default})"


def main():
    parser = argparse.ArgumentParser(
        description="Загрузчик музыки с сервиса Яндекс.Музыка"
    )

    common_group = parser.add_argument_group("Общие параметры")
    common_group.add_argument(
        "--hq", action="store_true", help="Загружать треки в высоком качестве"
    )
    common_group.add_argument(
        "--skip-existing", action="store_true", help="Пропускать уже загруженные треки"
    )
    common_group.add_argument(
        "--add-lyrics", action="store_true", help="Загружать тексты песен"
    )
    common_group.add_argument(
        "--embed-cover", action="store_true", help="Встраивать обложку в .mp3 файл"
    )
    common_group.add_argument(
        "--cover-resolution",
        default=core.DEFAULT_COVER_RESOLUTION,
        metavar="<Разрешение обложки>",
        type=int,
        help=show_default(None),
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
        help="Загружать альбомы, созданные" " только данным исполнителем",
    )
    common_group.add_argument(
        "--only-music",
        action="store_true",
        help="Загружать только музыкальные альбомы"
        " (пропускать подкасты и аудиокниги)",
    )
    common_group.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)

    id_group_meta = parser.add_argument_group("ID")
    id_group = id_group_meta.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--artist-id", metavar="<ID исполнителя>")
    id_group.add_argument("--album-id", metavar="<ID альбома>")
    id_group.add_argument("--track-id", metavar="<ID трека>")
    id_group.add_argument(
        "--playlist-id",
        type=args_playlist_id,
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
            " #album, #year, #artist-id, #album-id, #track-id, #track-number"
        ),
    )

    auth_group = parser.add_argument_group("Авторизация")
    auth_group.add_argument(
        "--browser",
        required=True,
        help=(
            "Браузер из которого будут извлечены данные для авторизации."
            " Укажите браузер через который вы входили в Яндекс Музыку."
            f" Допустимые значения: {', '.join(SUPPORTED_BROWSERS)}"
        ),
    )
    auth_group.add_argument(
        "--cookies-path",
        help="Путь к файлу с cookies. Используйте если возникает ошибка получения cookies",
    )
    auth_group.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        metavar="<User-Agent>",
        help=show_default(),
    )

    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s |%(levelname)s| %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if args.debug else logging.ERROR,
    )

    def response_hook(resp, **kwargs):
        del kwargs
        if logger.isEnabledFor(logging.DEBUG):
            target_headers = ["application/json", "text/xml"]
            if any(h in resp.headers["Content-Type"] for h in target_headers):
                logger.debug(resp.text)
        if not resp.ok:
            print(f"Код ошибки: {resp.status_code}")
            if resp.status_code == 400:
                print(
                    "Информация по устранению данной ошибки: https://github.com/llistochek/yandex-music-downloader#%D0%BE%D1%88%D0%B8%D0%B1%D0%BA%D0%B0-400"
                )
            sys.exit(3)
        time.sleep(args.delay)

    try:
        cookies = getattr(browser_cookie3, args.browser)(cookie_file=args.cookies_path)
    except BrowserCookieError:
        print(f"Не удалось получить cookies для браузера {args.browser}")
        return 1

    result_tracks: list[BasicTrackInfo] = []

    domain = DEFAULT_DOMAIN
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
            args.playlist_id = PlaylistId(
                owner=match.group(1), kind=int(match.group(2))
            )
        else:
            print("Параметер url указан в неверном формате")
            return 1
        domain = parsed_url.hostname
    session = Session()
    core.setup_session(session, cookies, DEFAULT_USER_AGENT, domain)
    session.hooks = {"response": response_hook}
    client = YandexMusicApi(session, domain)

    if args.artist_id is not None:
        artist_info = client.get_artist_info(args.artist_id)
        albums_count = 0
        for album in artist_info.albums:
            if args.stick_to_artist and album.artists[0].name != artist_info.name:
                print(
                    f'Альбом "{album.title}" пропущен' " из-за флага --stick-to-artist"
                )
                continue
            if args.only_music and album.meta_type != "music":
                print(
                    f'Альбом "{album.title}" пропущен' " т.к. не является музыкальным"
                )
                continue
            full_album = client.get_full_album_info(album.id)
            result_tracks.extend(full_album.tracks)
            albums_count += 1
        print(artist_info.name)
        print(f"Альбомов: {albums_count}")
    elif args.album_id is not None:
        album = client.get_full_album_info(args.album_id)
        print(album.title)
        result_tracks = album.tracks
    elif args.track_id is not None:
        track = client.get_full_track_info(args.track_id)
        if track is not None:
            result_tracks = [track]
        else:
            logger.info("Трек не доступен для скачивания")
            return 1
    elif args.playlist_id is not None:
        result_tracks = client.get_playlist(args.playlist_id)

    print(f"Треков: {len(result_tracks)}")

    covers_cache: dict[str, bytes] = {}
    track_number = 0
    track_number_pad = len(str(len(result_tracks)))
    for track in result_tracks:
        track_number += 1
        save_path = args.dir / core.prepare_track_path(
            args.path_pattern,
            track,
            args.unsafe_path,
            str(track_number).zfill(track_number_pad),
        )
        if args.skip_existing and save_path.is_file():
            continue

        save_dir = save_path.parent
        if not save_dir.is_dir():
            save_dir.mkdir(parents=True)

        print(f"Загружается {save_path}")
        core.download_track(
            client=client,
            track=track,
            target_path=save_path,
            hq=args.hq,
            add_lyrics=args.add_lyrics,
            embed_cover=args.embed_cover,
            cover_resolution=args.cover_resolution,
            covers_cache=covers_cache,
        )
