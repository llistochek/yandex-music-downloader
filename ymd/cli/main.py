
import itertools
import time
import typing
from collections.abc import Generator, Iterable
from pathlib import Path
from urllib.parse import urlparse

import typer
from yandex_music import Album, Playlist, Track

from ymd.cli.logger import setup_logger

# Импорт перечисления типов загрузки (DownloadTypes) и регулярных выражений для парсинга url
from ymd.cli.options.download import (
    DownloadQuality,
    DownloadTypeArgument,
    DownloadTypes,
    OnlyMusicOption,
    QualityOption,
    StickToArtistOption,
    TargetOption,
    TokenOption,
)
from ymd.cli.options.file_managing import (
    DownloadDirectoryOption,
    PathPatternOption,
    SkipExistingOption,
    UnsafePathOption,
)
from ymd.cli.options.metadata import (
    CoverResolutionOption,
    EmbedCoverOption,
    LyricsFormatOption,
    TagsCompatibility,
    TagsCompatibilityOption,
)
from ymd.cli.options.network import (
    RequestsDelayOption,
    ResponseTimeoutOption,
    RetryCountOption,
)
from ymd.domain import core

from .filename_regexps import (
    ALBUM_RE,
    ARTIST_RE,
    PLAYLIST_RE,
    TRACK_RE,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

DEFAULT_PATH_PATTERN = Path("#album-artist", "#album", "#number - #title")
DEFAULT_DOWNLOAD_DIR = Path(".")
DEFAULT_DELAY = 0
FETCH_PAGE_SIZE = 10

# Doc string функции - выводится в --help справке
def main(
        # Обязательные аргументы
        type: DownloadTypeArgument,
        target: TargetOption,
        token: TokenOption,

        # Параметры загрузки
        quality: QualityOption = DownloadQuality.mp3_320,
        stick_to_artist: StickToArtistOption = False,
        only_music: OnlyMusicOption = False,
        
        # Метаданные
        lyrics_format: LyricsFormatOption = core.LyricsFormat.NONE,
        embed_cover: EmbedCoverOption = False,
        cover_resolution: CoverResolutionOption = 400,
        tags_compatibility: TagsCompatibilityOption = TagsCompatibility.m4a_compatible,

        # Работа с файлами
        download_dir: DownloadDirectoryOption = DEFAULT_DOWNLOAD_DIR,
        skip_existing: SkipExistingOption = False,
        path_pattern: PathPatternOption = DEFAULT_PATH_PATTERN,
        unsafe_path: UnsafePathOption = False,

        # Настройки сети
        delay: RequestsDelayOption = 0,
        response_timeout: ResponseTimeoutOption = 20,
        retry_count: RetryCountOption = 20,
    ):
    """
        🎵 yandex-music-downloader - Позволяет скачивать музыку с Яндекс Музыки

        📚 Примеры использования:
            

        ymd url https://music.yandex.ru/album/123456 --token YOUR_TOKEN
    """
    # TODO: Использовать где-то
    _ = setup_logger(debug=False)

    if type == DownloadTypes.url:
        if not target.startswith("https://music.yandex.ru/"):
            typer.echo("Неверный формат URL. Ожидается ссылка на Яндекс Музыку.")
            raise typer.Exit(code=1)
        
    url = target 
    parsed_url = urlparse(url)
    path = parsed_url.path

    artist_id: str | None = None
    album_id: str | None = None
    track_id: str | None = None
    playlist_id: str | None = None

    if match := ARTIST_RE.search(path):
        artist_id = match.group(1)
    elif match := ALBUM_RE.search(path):
        album_id = match.group(1)
    elif match := TRACK_RE.search(path):
        track_id = match.group(1)
    elif match := PLAYLIST_RE.search(path):
        playlist_id = match.group(1) + "/" + match.group(2)
    else:
        typer.echo("Параметер target указан в неверном формате")
        raise typer.Exit(code=1)
    

    client = core.init_client(
        token=token,
        timeout=response_timeout,
        max_try_count=retry_count,
        retry_delay=delay,
    )

    result_tracks: Iterable[Track]

    def album_tracks_gen(album_ids: Iterable[int | str]) -> Generator[Track]:
        for album_id in album_ids:
            if full_album := client.albums_with_tracks(album_id):
                if volumes := full_album.volumes:
                    yield from itertools.chain.from_iterable(volumes)

    # Общее количество треков может быть не определено
    total_track_count: int | None = None

    if artist_id is not None:
        def filter_album(album: Album) -> bool:
            title = album.title
            if album.id is None or not album.available:
                print(f'Альбом "{title}" не доступен для скачивания')
            elif only_music and album.meta_type != "music":
                print(f'Альбом "{title}" пропущен т.к. не является музыкальным')
            elif stick_to_artist and album.artists[0].id != int(artist_id):
                print(f'Альбом "{title}" пропущен из-за флага --stick-to-artist')
            else:
                return True
            return False

        def albums_id_gen() -> Generator[int]:
            has_next = True
            page = 0
            while has_next:
                if albums_info := client.artists_direct_albums(artist_id, page):
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
        artist = client.artists(artist_id)[0]
        if counts := artist.counts:
            total_track_count = counts.tracks

    elif album_id is not None:
        result_tracks = album_tracks_gen((album_id,))
        if album := client.albums_with_tracks(album_id):
            total_track_count = album.track_count
    elif track_id is not None:
        track = client.tracks(track_id)
        result_tracks = track
        total_track_count = 1
    elif playlist_id is not None:
        user, kind = playlist_id.split("/")
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
    covers_cache: dict[int, core.AlbumCover] = {}
    for track in result_tracks:
        if total_track_count:
            track_counter += 1
            progress_status = f"[{track_counter}/{total_track_count}] "

        if not track.available:
            print(f"{progress_status}Трек {track.title} не доступен для скачивания")
            continue

        save_path = download_dir / core.prepare_base_path(
            path_pattern,
            track,
            unsafe_path=unsafe_path,
        )
        if skip_existing:
            if any(
                Path(str(save_path) + s).is_file() for s in core.AUDIO_FILE_SUFFIXES
            ):
                continue

        save_dir = save_path.parent
        if not save_dir.is_dir():
            save_dir.mkdir(parents=True)

        downloadable = core.to_downloadable_track(track, quality.toCore(), save_path)
        bitrate = downloadable.download_info.bitrate
        format_info = "[" + downloadable.download_info.file_format.codec.name
        if bitrate > 0:
            format_info += f" {bitrate}kbps"
        format_info += "]"
        print(f"{progress_status}{format_info} Загружается {downloadable.path}")
        core.core_download_track(
            track_info=downloadable,
            lyrics_format=lyrics_format,
            embed_cover=embed_cover,
            cover_resolution=cover_resolution,
            covers_cache=covers_cache,
            compatibility_level=int(tags_compatibility),
        )
        if delay > 0:
            time.sleep(delay)



def run():
    # Запуск приложения с зарегистрированными флагами и командами
    typer.run(main)

