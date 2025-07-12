import itertools
import time
import typing
from collections.abc import Generator, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import typer
from yandex_music import Album, Client, Playlist, Track

from ymd.cli.logger import setup_logger
from ymd.cli.options.download import (
    DownloadQuality,
    OnlyMusicOption,
    QualityOption,
    StickToArtistOption,
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


@dataclass
class ParsedUrl:
    """Результат парсинга URL"""
    artist_id: str | None = None
    album_id: str | None = None
    track_id: str | None = None
    playlist_id: str | None = None


@dataclass
class DownloadConfig:
    """Конфигурация загрузки"""
    quality: DownloadQuality
    stick_to_artist: bool
    only_music: bool
    lyrics_format: core.LyricsFormat
    embed_cover: bool
    cover_resolution: int
    tags_compatibility: TagsCompatibility
    download_dir: Path
    skip_existing: bool
    path_pattern: Path
    unsafe_path: bool
    delay: int


def validate_and_parse_url(target: str) -> ParsedUrl:
    """Валидация и парсинг URL"""
    if not target.startswith("https://music.yandex.ru/"):
        typer.echo("Неверный формат URL. Ожидается ссылка на Яндекс Музыку.")
        raise typer.Exit(code=1)
    
    parsed_url = urlparse(target)
    path = parsed_url.path
    
    if match := ARTIST_RE.search(path):
        return ParsedUrl(artist_id=match.group(1))
    elif match := ALBUM_RE.search(path):
        return ParsedUrl(album_id=match.group(1))
    elif match := TRACK_RE.search(path):
        return ParsedUrl(track_id=match.group(1))
    elif match := PLAYLIST_RE.search(path):
        return ParsedUrl(playlist_id=f"{match.group(1)}/{match.group(2)}")
    else:
        typer.echo("Параметер target указан в неверном формате")
        raise typer.Exit(code=1)


def get_album_tracks(client: Client, album_ids: Iterable[int | str]) -> Generator[Track, None, None]:
    """Получение треков из альбомов"""
    for album_id in album_ids:
        if full_album := client.albums_with_tracks(album_id):
            if volumes := full_album.volumes:
                yield from itertools.chain.from_iterable(volumes)


def should_skip_album(
    album: Album, 
    only_music: bool, 
    stick_to_artist: bool, 
    artist_id: str | None
) -> tuple[bool, str]:
    title = album.title
    
    if album.id is None or not album.available:
        return True, f'Альбом "{title}" не доступен для скачивания'
    
    if only_music and album.meta_type != "music":
        return True, f'Альбом "{title}" пропущен т.к. не является музыкальным'
    
    if stick_to_artist and artist_id and album.artists and album.artists[0].id != int(artist_id):
        return True, f'Альбом "{title}" пропущен из-за флага --stick-to-artist'
    
    return False, ""


def get_artist_tracks(
    client: Client, 
    artist_id: str, 
    config: DownloadConfig
) -> tuple[Generator[Track, None, None], int | None]:
    """Получение треков артиста"""
    def get_album_ids() -> Generator[int, None, None]:
        has_next = True
        page = 0
        
        while has_next:
            albums_info = client.artists_direct_albums(artist_id, page)
            if albums_info is None:
                break
                
            for album in albums_info.albums:
                should_skip, skip_reason = should_skip_album(
                    album, config.only_music, config.stick_to_artist, artist_id
                )
                
                if should_skip:
                    print(skip_reason)
                else:
                    assert album.id is not None
                    yield album.id
                    
            if pager := albums_info.pager:
                page = pager.page + 1
                has_next = pager.per_page * page < pager.total
            else:
                break
    
    tracks = get_album_tracks(client, get_album_ids())
    
    # Получаем общее количество треков
    artist_list = client.artists(artist_id)
    if not artist_list:
        return tracks, None
        
    artist = artist_list[0]
    total_count: int | None = None
    if counts := artist.counts:
        total_count = counts.tracks
    
    return tracks, total_count


TrackGenerator = Generator[Track, None, None]
TrackCount = int | None

def get_album_tracks_with_count(
    client: Client, 
    album_id: str
) -> tuple[TrackGenerator, TrackCount]:
    """Получение треков альбома с подсчётом"""
    tracks = get_album_tracks(client, (album_id,))
    
    total_count: int | None = None
    if album := client.albums_with_tracks(album_id):
        total_count = album.track_count
    
    return tracks, total_count


def get_single_track(client: Client, track_id: str) -> tuple[list[Track], int]:
    """Получение одного трека"""
    track = client.tracks(track_id)
    return track, 1


def get_playlist_tracks(
    client: Client, 
    playlist_id: str
) -> tuple[Generator[Track, None, None], int | None]:
    """Получение треков плейлиста"""
    user, kind = playlist_id.split("/")
    playlist = typing.cast(Playlist, client.users_playlists(kind, user))
    
    def playlist_tracks_gen() -> Generator[Track, None, None]:
        tracks = playlist.fetch_tracks()
        for i in range(0, len(tracks), FETCH_PAGE_SIZE):
            yield from client.tracks(
                [track.id for track in tracks[i : i + FETCH_PAGE_SIZE]]
            )
    
    return playlist_tracks_gen(), playlist.track_count


def get_tracks_by_type(
    client: Client, 
    parsed_url: ParsedUrl, 
    config: DownloadConfig
) -> tuple[Iterable[Track], int | None]:
    """Получение треков в зависимости от типа URL"""
    if parsed_url.artist_id:
        return get_artist_tracks(client, parsed_url.artist_id, config)
    elif parsed_url.album_id:
        return get_album_tracks_with_count(client, parsed_url.album_id)
    elif parsed_url.track_id:
        return get_single_track(client, parsed_url.track_id)
    elif parsed_url.playlist_id:
        return get_playlist_tracks(client, parsed_url.playlist_id)
    else:
        raise ValueError("Invalid ID argument")


def should_skip_existing_track(save_path: Path) -> bool:
    """Проверка, существует ли уже трек"""
    return any(
        Path(str(save_path) + suffix).is_file() 
        for suffix in core.AUDIO_FILE_SUFFIXES
    )


def download_single_track(
    track: Track, 
    config: DownloadConfig, 
    covers_cache: dict[int, core.AlbumCover],
    progress_status: str = ""
) -> bool:
    """Загрузка одного трека. Возвращает True, если трек был загружен"""
    if not track.available:
        print(f"{progress_status}Трек {track.title} не доступен для скачивания")
        return False
    
    save_path = config.download_dir / core.prepare_base_path(
        config.path_pattern,
        track,
        unsafe_path=config.unsafe_path,
    )
    
    if config.skip_existing and should_skip_existing_track(save_path):
        return False
    
    save_dir = save_path.parent
    if not save_dir.is_dir():
        save_dir.mkdir(parents=True)
    
    downloadable = core.to_downloadable_track(track, config.quality.toCore(), save_path)
    bitrate = downloadable.download_info.bitrate
    format_info = "[" + downloadable.download_info.file_format.codec.name
    if bitrate > 0:
        format_info += f" {bitrate}kbps"
    format_info += "]"
    
    print(f"{progress_status}{format_info} Загружается {downloadable.path}")
    
    core.core_download_track(
        track_info=downloadable,
        lyrics_format=config.lyrics_format,
        embed_cover=config.embed_cover,
        cover_resolution=config.cover_resolution,
        covers_cache=covers_cache,
        compatibility_level=int(config.tags_compatibility),
    )
    
    return True


def download_tracks(
    tracks: Iterable[Track], 
    config: DownloadConfig, 
    total_count: int | None
) -> None:
    """Загрузка всех треков"""
    track_counter = 0
    covers_cache: dict[int, core.AlbumCover] = {}
    
    for track in tracks:
        if total_count:
            track_counter += 1
            progress_status = f"[{track_counter}/{total_count}] "
        else:
            progress_status = ""
        
        if download_single_track(track, config, covers_cache, progress_status):
            if config.delay > 0:
                time.sleep(config.delay)


UrlArgument = Annotated[
    str,
    typer.Argument(help="URL с Яндекс Музыки")
]


def main(
    # Обязательные аргументы
    url: UrlArgument,
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
) -> None:
    """
    🎵 yandex-music-downloader - Позволяет скачивать музыку с Яндекс Музыки

    📚 Примеры использования:

    yandex-music-downloader https://music.yandex.ru/album/123456 --token YOUR_TOKEN
    yandex-music-downloader https://music.yandex.ru/artist/123456 --token YOUR_TOKEN
    yandex-music-downloader https://music.yandex.ru/album/123456/track/789012 --token YOUR_TOKEN
    yandex-music-downloader https://music.yandex.ru/users/username/playlists/123456 --token YOUR_TOKEN

    ✅ Внимание! Для получения ссылок в нужном формате используйте кнопку 
       "Поделиться" в самой Яндекс Музыке. 
       
       (Не копируйте ссылку из адресной строки браузера, она имеет другой формат)
    """
    # Настройка логирования
    _ = setup_logger(debug=False)
    
    # Парсинг URL
    parsed_url = validate_and_parse_url(url)
    
    # Инициализация клиента
    client = core.init_client(
        token=token,
        timeout=response_timeout,
        max_try_count=retry_count,
        retry_delay=delay,
    )
    
    # Создание конфигурации
    config = DownloadConfig(
        quality=quality,
        stick_to_artist=stick_to_artist,
        only_music=only_music,
        lyrics_format=lyrics_format,
        embed_cover=embed_cover,
        cover_resolution=cover_resolution,
        tags_compatibility=tags_compatibility,
        download_dir=download_dir,
        skip_existing=skip_existing,
        path_pattern=path_pattern,
        unsafe_path=unsafe_path,
        delay=delay,
    )
    
    # Получение треков
    tracks, total_count = get_tracks_by_type(client, parsed_url, config)
    
    # Загрузка треков
    download_tracks(tracks, config, total_count)


def run() -> None:
    """Запуск приложения с зарегистрированными флагами и командами"""
    typer.run(main)

