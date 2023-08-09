#!/bin/python3
import argparse
import datetime as dt
import hashlib
import logging
import re
import sys
import tempfile
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import eyed3
from eyed3.id3.frames import ImageFrame
from requests import Session
from requests_cache import CachedSession, FileCache

MD5_SALT = 'XGRlBW9FXlekgbPrRHuSiA'
ENCODED_BY = 'https://github.com/llistochek/yandex-music-downloader'
DEFAULT_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36'
DEFAULT_DELAY = 3
DEFAULT_PATH_PATTERN = Path('#album-artist', '#album', '#number - #title')
DEFAULT_COVER_RESOLUTION = 400
DEFAULT_LOG_LEVEL = 'INFO'

CACHE_EXPIRE_AFTER = dt.timedelta(hours=8)
CACHE_DIR = Path(tempfile.gettempdir()) / 'ymd'

TRACK_RE = re.compile(r'track/(\d+)$')
ALBUM_RE = re.compile(r'album/(\d+)$')
ARTIST_RE = re.compile(r'artist/(\d+)$')
PLAYLIST_RE = re.compile(r'([\w\-._]+)/playlists/(\d+)$')

FILENAME_CLEAR_RE = re.compile(r'[^\w\-\'() ]+')

TITLE_TEMPLATE = '{title} ({version})'

logger = logging.getLogger('yandex-music-downloader')


@dataclass
class CoverInfo:
    cover_url_template: Optional[str]

    def cover_url(self, resolution: int) -> Optional[str]:
        if self.cover_url_template is None:
            return

        return self.cover_url_template.replace('%%',
                                               f'{resolution}x{resolution}')

    @classmethod
    def from_json(cls, data: dict) -> 'CoverInfo':
        og_image = data.get("ogImage")
        return cls(f'https://{og_image}' if og_image is not None else None)


@dataclass
class PlaylistId:
    owner: str
    kind: int


@dataclass
class BasicArtistInfo:
    id: str
    name: str

    @classmethod
    def from_json(cls, data: dict) -> 'BasicArtistInfo':
        return cls(id=data['id'], name=data['name'])


@dataclass
class FullArtistInfo(BasicArtistInfo):
    albums: list['BasicAlbumInfo']
    cover_info: CoverInfo

    @classmethod
    def from_json(cls, data: dict) -> 'FullArtistInfo':
        base = BasicArtistInfo.from_json(data['artist'])
        albums = map(BasicAlbumInfo.from_json, data.get('albums', []))
        albums = [a for a in albums if a is not None]
        cover_info = CoverInfo.from_json(data)
        return cls(**base.__dict__, cover_info=cover_info, albums=albums)


@dataclass
class BasicAlbumInfo:
    id: str
    title: str
    release_date: Optional[dt.datetime]
    year: Optional[int]
    artists: list[BasicArtistInfo]
    meta_type: str

    @classmethod
    def from_json(cls, data: dict) -> Optional['BasicAlbumInfo']:
        artists = parse_artists(data['artists'])
        title = parse_title(data)
        if release_date := data.get('releaseDate'):
            release_date = dt.datetime.fromisoformat(release_date)
        return cls(id=data['id'],
                   title=title,
                   year=data.get('year'),
                   meta_type=data['metaType'],
                   artists=artists,
                   release_date=release_date)


@dataclass
class BasicTrackInfo:
    title: str
    id: str
    real_id: str
    album: BasicAlbumInfo
    number: int
    disc_number: int
    artists: list[BasicArtistInfo]
    has_lyrics: bool
    cover_info: CoverInfo

    @classmethod
    def from_json(cls, data: dict) -> Optional['BasicTrackInfo']:
        if not data['available']:
            return None
        track_id = str(data['id'])
        title = parse_title(data)
        albums_data = data['albums']
        artists = parse_artists(data['artists'])
        track_position = {'index': 1, 'volume': 1}
        if len(albums_data):
            album_data = albums_data[0]
            album = BasicAlbumInfo.from_json(album_data)
            track_position = album_data.get('trackPosition', track_position)
        else:
            album = BasicAlbumInfo(id=track_id,
                                   title=title,
                                   release_date=None,
                                   year=None,
                                   meta_type='music',
                                   artists=artists)
        if album is None:
            raise ValueError
        cover_info = CoverInfo.from_json(data)
        has_lyrics = data.get('lyricsInfo', {}).get('hasAvailableTextLyrics',
                                                    False)
        return cls(title=title,
                   id=track_id,
                   real_id=data['realId'],
                   number=track_position['index'],
                   disc_number=track_position['volume'],
                   artists=artists,
                   album=album,
                   has_lyrics=has_lyrics,
                   cover_info=cover_info)

    @property
    def url(self) -> str:
        return f'https://music.yandex.ru/album/{self.album.id}/track/{self.id}'


@dataclass
class FullTrackInfo(BasicTrackInfo):
    lyrics: str

    @classmethod
    def from_json(cls, data: dict) -> 'FullTrackInfo':
        base = BasicTrackInfo.from_json(data['track'])
        lyrics = data['lyric'][0]['fullLyrics']
        return cls(**base.__dict__, lyrics=lyrics)


@dataclass
class FullAlbumInfo(BasicAlbumInfo):
    tracks: list[BasicTrackInfo]

    @classmethod
    def from_json(cls, data: dict) -> 'FullAlbumInfo':
        base = BasicAlbumInfo.from_json(data)
        tracks = data.get('volumes', [])
        tracks = [t for v in tracks for t in v]
        tracks = map(BasicTrackInfo.from_json, tracks)
        tracks = [t for t in tracks if t is not None]
        return cls(**base.__dict__, tracks=tracks)


def parse_artists(data: list) -> list[BasicArtistInfo]:
    artists = []
    for artist in data:
        artists.append(artist)
        if decomposed := artist.get('decomposed'):
            for d_artist in decomposed:
                if isinstance(d_artist, dict):
                    artists.append(d_artist)
    return [BasicArtistInfo.from_json(a) for a in artists]


def parse_title(data: dict) -> str:
    title = data['title']
    if version := data.get('version'):
        title = TITLE_TEMPLATE.format(title=title, version=version)
    return title


def get_track_download_url(session: Session, track: BasicTrackInfo,
                           hq: bool) -> str:
    resp = session.get('https://music.yandex.ru/api/v2.1/handlers/track'
                       f'/{track.id}:{track.album.id}'
                       '/web-album_track-track-track-main/download/m'
                       f'?hq={int(hq)}')
    url_info_src = resp.json()['src']

    resp = session.get('https:' + url_info_src)
    url_info = ET.fromstring(resp.text)
    path = url_info.find('path').text[1:]
    s = url_info.find('s').text
    ts = url_info.find('ts').text
    host = url_info.find('host').text
    path_hash = hashlib.md5((MD5_SALT + path + s).encode()).hexdigest()
    return f'https://{host}/get-mp3/{path_hash}/{ts}/{path}?track-id={track.id}'


def download_file(session: Session, url: str, path: Path) -> None:
    resp = session.get(url)
    with open(path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=1024):
            f.write(chunk)


def download_bytes(session: Session, url: str) -> bytes:
    return session.get(url).content


def get_full_track_info(session: Session, track_id: str) -> FullTrackInfo:
    params = {'track': track_id, 'lang': 'ru'}
    resp = session.get('https://music.yandex.ru/handlers/track.jsx',
                       params=params)
    return FullTrackInfo.from_json(resp.json())


def get_full_album_info(session: Session, album_id: str) -> FullAlbumInfo:
    params = {'album': album_id, 'lang': 'ru'}
    resp = session.get('https://music.yandex.ru/handlers/album.jsx',
                       params=params)
    return FullAlbumInfo.from_json(resp.json())


def get_artist_info(session: Session, artist_id: str) -> FullArtistInfo:
    params = {'artist': artist_id, 'what': 'albums', 'lang': 'ru'}
    resp = session.get('https://music.yandex.ru/handlers/artist.jsx',
                       params=params)
    return FullArtistInfo.from_json(resp.json())


def get_playlist(session: Session,
                 playlist: PlaylistId) -> list[BasicTrackInfo]:
    params = {'owner': playlist.owner, 'kinds': playlist.kind, 'lang': 'ru'}
    resp = session.get('https://music.yandex.ru/handlers/playlist.jsx',
                       params=params)
    raw_tracks = resp.json()['playlist'].get('tracks', [])
    tracks = map(BasicTrackInfo.from_json, raw_tracks)
    tracks = [t for t in tracks if t is not None]
    return tracks


def prepare_track_path(path: Path, prepare_path: bool,
                       track: BasicTrackInfo) -> Path:
    path_str = str(path)
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
        if prepare_path:
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Загрузчик музыки с сервиса Яндекс.Музыка')

    def help_str(text: Optional[str] = None) -> str:
        default = 'по умолчанию: %(default)s'
        if text is None:
            return default
        return f'{text} ({default})'

    common_group = parser.add_argument_group('Общие параметры')
    common_group.add_argument('--hq',
                              action='store_true',
                              help='Загружать треки в высоком качестве')
    common_group.add_argument('--skip-existing',
                              action='store_true',
                              help='Пропускать уже загруженные треки')
    common_group.add_argument('--add-lyrics',
                              action='store_true',
                              help='Загружать тексты песен')
    common_group.add_argument('--embed-cover',
                              action='store_true',
                              help='Встраивать обложку в .mp3 файл')
    common_group.add_argument('--cover-resolution',
                              default=DEFAULT_COVER_RESOLUTION,
                              metavar='<Разрешение обложки>',
                              type=int,
                              help=help_str(None))
    common_group.add_argument(
        '--delay',
        default=DEFAULT_DELAY,
        metavar='<Задержка>',
        type=int,
        help=help_str('Задержка между запросами, в секундах'))
    common_group.add_argument('--stick-to-artist',
                              action='store_true',
                              help='Загружать альбомы, созданные'
                              ' только данным исполнителем')
    common_group.add_argument('--only-music',
                              action='store_true',
                              help='Загружать только музыкальные альбомы'
                              ' (пропускать подкасты и аудиокниги)')
    common_group.add_argument('--enable-caching',
                              action='store_true',
                              help='Включить кэширование. Данная опция полезна'
                              ' при нестабильном интернете.'
                              f' (кэш хранится в папке {CACHE_DIR})')
    common_group.add_argument('--debug',
                              action='store_true',
                              help=argparse.SUPPRESS)

    def args_playlist_id(arg: str) -> PlaylistId:
        arr = arg.split('/')
        return PlaylistId(owner=arr[0], kind=int(arr[1]))

    id_group_meta = parser.add_argument_group('ID')
    id_group = id_group_meta.add_mutually_exclusive_group(required=True)
    id_group.add_argument('--artist-id', metavar='<ID исполнителя>')
    id_group.add_argument('--album-id', metavar='<ID альбома>')
    id_group.add_argument('--track-id', metavar='<ID трека>')
    id_group.add_argument('--playlist-id',
                          type=args_playlist_id,
                          metavar='<владелец плейлиста>/<тип плейлиста>')
    id_group.add_argument('-u',
                          '--url',
                          help='URL исполнителя/альбома/трека/плейлиста')

    path_group = parser.add_argument_group('Указание пути')
    path_group.add_argument('--unsafe-path',
                            action='store_true',
                            help='Не очищать путь от недопустимых символов')
    path_group.add_argument('--dir',
                            default='.',
                            metavar='<Папка>',
                            help=help_str('Папка для загрузки музыки'),
                            type=Path)
    path_group.add_argument(
        '--path-pattern',
        default=DEFAULT_PATH_PATTERN,
        metavar='<Паттерн>',
        type=Path,
        help=help_str('Поддерживает следующие заполнители:'
                      ' #number, #artist, #album-artist, #title,'
                      ' #album, #year, #artist-id, #album-id, #track-id'))

    auth_group = parser.add_argument_group('Авторизация')
    auth_group.add_argument('--session-id',
                            required=True,
                            metavar='<ID сессии>')
    auth_group.add_argument('--user-agent',
                            default=DEFAULT_USER_AGENT,
                            metavar='<User-Agent>',
                            help=help_str())

    args = parser.parse_args()
    logging.basicConfig(
        format='%(asctime)s |%(levelname)s| %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        level=logging.DEBUG if args.debug else logging.ERROR)

    session = Session()
    cached_session = Session()
    if args.enable_caching:
        cached_session = CachedSession(backend=FileCache(cache_name=CACHE_DIR),
                                       expire_after=CACHE_EXPIRE_AFTER)

    def setup_session(session: Session):

        def response_hook(resp, **kwargs):
            del kwargs
            if logger.isEnabledFor(logging.DEBUG):
                target_headers = ['application/json', 'text/xml']
                if any(h in resp.headers['Content-Type']
                       for h in target_headers):
                    logger.debug(resp.text)
            if not resp.ok:
                print('Яндекс вернул ошибку. Скорее всего, это связано с'
                      ' с ограничением количества запросов.'
                      ' Попробуйте перезапустить скрипт через некоторое время.'
                      ' Если проблема сохраняется - откройте issue на github.')
                print(f'Код ошибки: {resp.status_code}')
                sys.exit(3)
            if not getattr(resp, 'from_cache', False):
                time.sleep(args.delay)

        session.hooks = {'response': response_hook}
        session.cookies.set('Session_id', args.session_id, domain='yandex.ru')
        session.headers['User-Agent'] = args.user_agent
        session.headers['X-Retpath-Y'] = urllib.parse.quote_plus(
            'https://music.yandex.ru')

    setup_session(session)
    setup_session(cached_session)

    result_tracks: list[BasicTrackInfo] = []

    if args.url is not None:
        if match := ARTIST_RE.search(args.url):
            args.artist_id = match.group(1)
        elif match := ALBUM_RE.search(args.url):
            args.album_id = match.group(1)
        elif match := TRACK_RE.search(args.url):
            args.track_id = match.group(1)
        elif match := PLAYLIST_RE.search(args.url):
            args.playlist_id = PlaylistId(owner=match.group(1),
                                          kind=int(match.group(2)))
        else:
            print('Параметер url указан в неверном формате')
            sys.exit(1)

    if args.artist_id is not None:
        artist_info = get_artist_info(cached_session, args.artist_id)
        albums_count = 0
        for album in artist_info.albums:
            if args.stick_to_artist and album.artists[0] != artist_info.name:
                print(f'Альбом "{album.title}" пропущен'
                      ' из-за флага --stick-to-artist')
                continue
            if args.only_music and album.meta_type != 'music':
                print(f'Альбом "{album.title}" пропущен'
                      ' т.к. не является музыкальным')
                continue
            full_album = get_full_album_info(cached_session, album.id)
            result_tracks.extend(full_album.tracks)
            albums_count += 1
        print(artist_info.name)
        print(f'Альбомов: {albums_count}')
    elif args.album_id is not None:
        album = get_full_album_info(cached_session, args.album_id)
        print(album.title)
        result_tracks = album.tracks
    elif args.track_id is not None:
        result_tracks = [get_full_track_info(cached_session, args.track_id)]
    elif args.playlist_id is not None:
        result_tracks = get_playlist(cached_session, args.playlist_id)

    print(f'Треков: {len(result_tracks)}')
    covers: dict[str, bytes] = {}

    for track in result_tracks:
        album = track.album
        save_path = args.dir / prepare_track_path(args.path_pattern,
                                                  not args.unsafe_path, track)
        if args.skip_existing and save_path.is_file():
            continue

        save_dir = save_path.parent
        if not save_dir.is_dir():
            save_dir.mkdir(parents=True)

        url = get_track_download_url(session, track, args.hq)
        print(f'Загружается {save_path}')
        download_file(session, url, save_path)

        lyrics = None
        if args.add_lyrics and track.has_lyrics:
            if isinstance(track, FullTrackInfo):
                lyrics = track.lyrics
            else:
                full_track = get_full_track_info(session, track.id)
                lyrics = full_track.lyrics

        cover = None
        cover_url = track.cover_info.cover_url(args.cover_resolution)
        if cover_url is not None:
            if args.embed_cover:
                if cached_cover := covers.get(album.id):
                    cover = cached_cover
                else:
                    cover = covers[album.id] = download_bytes(
                        session, cover_url)
            else:
                cover_path = save_dir / 'cover.jpg'
                if not cover_path.is_file():
                    download_file(session, cover_url, cover_path)

        set_id3_tags(save_path, track, lyrics, cover)
