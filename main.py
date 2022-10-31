#!/bin/python3
import logging
import argparse
import requests
import json
import hashlib
import io
import time
import sys
import os
import urllib.parse
import re
import eyed3
import datetime
from typing import Optional
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from requests import Session

MD5_SALT = 'XGRlBW9FXlekgbPrRHuSiA'
ENCODED_BY = 'https://gitlab.com/llistochek/yandex-music-downloader'
DEFAULT_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36'
DEFAULT_DELAY = 0
DEFAULT_PATH_PATTERN = '#artist/#album/#number - #title'
DEFAULT_COVER_RESOLUTION = 400
DEFAULT_LOG_LEVEL = 'INFO'

TRACK_RE = re.compile(r'track/(\d+)$')
ALBUM_RE = re.compile(r'album/(\d+)$')
ARTIST_RE = re.compile(r'artist/(\d+)$')
PLAYLIST_RE = re.compile(r'([\w\-]+)/playlists/(\d+)$')


@dataclass
class PlaylistId:
    owner: str
    kind: int


@dataclass
class BasicAlbumInfo:
    id: str
    title: str
    year: int

    @staticmethod
    def from_json(json: dict):
        return BasicAlbumInfo(id=json['id'], title=json['title'], year=json['year'])


@dataclass
class BasicTrackInfo:
    title: str
    id: str
    real_id: str
    album: BasicAlbumInfo
    number: int
    disc_number: int
    artists_names: list[str]
    url_template: str
    has_lyrics: bool

    @staticmethod
    def from_json(json: dict):
        album_json = json['albums'][0]
        artists_names = [a['name'] for a in json['artists']]
        track_position = album_json['trackPosition']
        album = BasicAlbumInfo.from_json(album_json)
        url_template = 'https://' + json['ogImage']
        has_lyrics = json['lyricsInfo']['hasAvailableTextLyrics']
        return BasicTrackInfo(title=json['title'], id=str(json['id']), real_id=json['realId'],
                              number=track_position['index'], disc_number=track_position['volume'],
                              artists_names=artists_names, album=album, url_template=url_template,
                              has_lyrics=has_lyrics)

    def pic_url(self, resolution: int) -> str:
        return self.url_template.replace('%%', f'{resolution}x{resolution}')


@dataclass
class FullTrackInfo(BasicTrackInfo):
    lyrics: str

    @staticmethod
    def from_json(json: dict):
        base = BasicTrackInfo.from_json(json['track'])
        lyrics = json['lyric'][0]['fullLyrics']
        return FullTrackInfo(**base.__dict__, lyrics=lyrics)


@dataclass
class FullAlbumInfo(BasicAlbumInfo):
    tracks: list[BasicTrackInfo]

    @staticmethod
    def from_json(json: dict):
        base = BasicAlbumInfo.from_json(json)
        tracks = json.get('volumes', [])
        tracks = [t for v in tracks for t in v]  # Array flattening
        tracks = map(BasicTrackInfo.from_json, tracks)
        tracks = list(tracks)
        return FullAlbumInfo(**base.__dict__, tracks=tracks)


@dataclass
class ArtistInfo:
    id: str
    name: str
    albums: list[BasicAlbumInfo]
    url_template: str

    @staticmethod
    def from_json(json: dict):
        artist = json['artist']
        albums = map(BasicAlbumInfo.from_json, json.get('albums', []))
        albums = list(albums)
        url_template = 'https://' + artist['ogImage']
        return ArtistInfo(id=str(artist['id']), name=artist['name'],
                          albums=albums, url_template=url_template)

    def pic_url(self, resolution: int) -> str:
        return self.url_template.replace('%%', f'{resolution}x{resolution}')


def get_track_download_url(session: Session, track: BasicTrackInfo, hq: bool) -> str:
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
    return 'https://%s/get-mp3/%s/%s/%s?track-id=%s' \
           % (host, path_hash, ts, path, track.id)


def download_file(session: Session, url: str, filename: str) -> None:
    resp = session.get(url)
    with open(filename, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=1024):
            f.write(chunk)


def get_full_track_info(session: Session, track_id: str) -> FullTrackInfo:
    resp = session.get(f'https://music.yandex.ru/handlers/track.jsx?track={track_id}&lang=ru')
    return FullTrackInfo.from_json(resp.json())


def get_full_album_info(session: Session, album_id: str) -> FullAlbumInfo:
    resp = session.get(f'https://music.yandex.ru/handlers/album.jsx?album={album_id}&lang=ru')
    return FullAlbumInfo.from_json(resp.json())


def get_artist_info(session: Session, artist_id: str) -> ArtistInfo:
    resp = session.get('https://music.yandex.ru/handlers/artist.jsx'
                       f'?artist={artist_id}&what=albums&lang=ru')
    return ArtistInfo.from_json(resp.json())


def get_playlist(session: Session, playlist: PlaylistId) -> list[BasicTrackInfo]:
    resp = session.get('https://music.yandex.ru/handlers/playlist.jsx'
                       f'?owner={playlist.owner}&kinds={playlist.kind}&lang=ru')
    raw_tracks = resp.json()['playlist']['tracks']
    return [BasicTrackInfo.from_json(t) for t in raw_tracks]


def prepare_track_path(directory: str, path: str, track: BasicTrackInfo) -> str:
    path_part = path.replace('#number', str(track.number)) \
               .replace('#artist', track.artists_names[0]) \
               .replace('#title', track.title) \
               .replace('#album', track.album.title) \
               .replace('#year', str(track.album.year)) \
               + '.mp3'
    return os.path.join(directory + '/' + path_part)


def set_id3_tags(path: str, track: BasicTrackInfo, lyrics: Optional[str]) -> None:
    audiofile = eyed3.load(path)
    audiofile.tag = tag = eyed3.id3.tag.Tag(version=(2, 4, 0))
    tag.artist = '; '.join(track.artists_names)
    tag.album = track.album.title
    tag.title = track.title
    tag.album_artist = track.artists_names[0]
    tag.track_num = track.number
    tag.release_date = tag.original_release_date = tag.recording_date \
        = track.album.year
    tag.disc_num = track.disc_number
    tag.encoded_by = ENCODED_BY
    if lyrics is not None:
        tag.lyrics.set(lyrics)
    tag.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Загрузчик музыки с сервиса Яндекс.Музыка')

    def help_str(text: str) -> str:
        return text + ' (по умолчанию: %(default)s)'

    common_group = parser.add_argument_group('Общие параметры')
    common_group.add_argument('--hq', action='store_true',
                              help=help_str('Загружать треки в высоком качестве'))
    common_group.add_argument('--skip-existing', action='store_true',
                              help=help_str('Пропускать уже загруженные треки'))
    common_group.add_argument('--cover-resolution', default=DEFAULT_COVER_RESOLUTION,
                              metavar='<Разрешение обложки>', help=help_str(''))
    common_group.add_argument('--add-lyrics', action='store_true',
                              help=help_str('Загружать тексты песен'))
    common_group.add_argument('--delay', default=DEFAULT_DELAY, metavar='<Задержка>',
                              help=help_str('Задержка между запросами, в секундах'))
    common_group.add_argument('--log-level', default=DEFAULT_LOG_LEVEL,
                              choices=logging._nameToLevel.keys())

    def args_playlist_id(arg: str) -> PlaylistId:
        arr = arg.split('/')
        return PlaylistId(owner=arr[0], kind=int(arr[1]))
    id_group_meta = parser.add_argument_group('ID')
    id_group = id_group_meta.add_mutually_exclusive_group(required=True)
    id_group.add_argument('--artist-id', metavar='<ID исполнителя>')
    id_group.add_argument('--album-id', metavar='<ID альбома>')
    id_group.add_argument('--track-id', metavar='<ID трека>')
    id_group.add_argument('--playlist-id', type=args_playlist_id,
                          metavar='<владелец плейлиста>/<тип плейлиста>')
    id_group.add_argument('-u', '--url', help='URL исполнителя/альбома/трека/плейлиста')

    path_group = parser.add_argument_group('Указание пути')
    path_group.add_argument('--dir', default='.', metavar='<Папка>',
                            help=help_str('Папка для загрузки музыки'))
    path_group.add_argument('--path-pattern', default=DEFAULT_PATH_PATTERN,
                            metavar='<Паттерн>',
                            help=help_str('Поддерживает следующие заполнители:'
                                          ' #number, #artist, #title, #album, #year'))

    auth_group = parser.add_argument_group('Авторизация')
    auth_group.add_argument('--session-id', required=True, metavar='<ID сессии>')
    auth_group.add_argument('--spravka', required=True, metavar='<Справка>')
    auth_group.add_argument('--user-agent', default=DEFAULT_USER_AGENT, metavar='<User-Agent>')

    args = parser.parse_args()
    logging.basicConfig(format='%(levelname)s -> %(message)s', level=args.log_level.upper())

    def response_hook(resp, *_args, **_kwargs):
        time.sleep(args.delay)
        pass

    session = Session()
    session.hooks = {'response': response_hook}
    session.cookies.set('Session_id', args.session_id, domain='yandex.ru')
    session.cookies.set('spravka', args.spravka, domain='yandex.ru')
    session.headers['User-Agent'] = args.user_agent
    session.headers['X-Retpath-Y'] = urllib.parse.quote_plus('https://music.yandex.ru')

    result_tracks: list[BasicTrackInfo] = []

    if args.url is not None:
        if match := ARTIST_RE.search(args.url):
            args.artist_id = match.group(1)
        elif match := ALBUM_RE.search(args.url):
            args.album_id = match.group(1)
        elif match := TRACK_RE.search(args.url):
            args.track_id = match.group(1)
        elif match := PLAYLIST_RE.search(args.url):
            args.playlist_id = PlaylistId(owner=match.group(1), kind=int(match.group(2)))
        else:
            print('Параметер url указан в неверном формате')
            sys.exit(1)

    if args.artist_id is not None:
        artist_info = get_artist_info(session, args.artist_id)
        albums = [get_full_album_info(session, a.id) for a in artist_info.albums]
        for album in albums:
            result_tracks.extend(album.tracks)
        print(f'{artist_info.name}:')
        print(f'Альбомов: {len(albums)}')
    elif args.album_id is not None:
        album = get_full_album_info(session, args.album_id)
        result_tracks = album.tracks
    elif args.track_id is not None:
        result_tracks = [get_full_track_info(session, args.track_id)]
    elif args.playlist_id is not None:
        result_tracks = get_playlist(session, args.playlist_id)
    print(f'Треков: {len(result_tracks)}')

    for track in result_tracks:
        save_path = prepare_track_path(args.dir, args.path_pattern, track)
        if os.path.isfile(save_path) and args.skip_existing:
            continue
        save_dir = os.path.dirname(save_path)
        cover_path = save_dir + '/cover.jpg'
        if not os.path.isdir(save_dir):
            os.makedirs(save_dir)
        url = get_track_download_url(session, track, args.hq)

        logging.info('Загружается %s', save_path)
        download_file(session, url, save_path)
        lyrics = None
        if args.add_lyrics and track.has_lyrics:
            if isinstance(track, FullTrackInfo):
                lyrics = track.lyrics
            else:
                full_info = get_full_track_info(session, track.id)
                lyrics = full_info.lyrics
        set_id3_tags(save_path, track, lyrics)
        if not os.path.isfile(cover_path):
            download_file(session, track.pic_url(args.cover_resolution), cover_path)
