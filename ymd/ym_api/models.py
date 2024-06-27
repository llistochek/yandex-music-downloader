import datetime as dt
import logging
import traceback
from dataclasses import dataclass
from typing import Optional

TITLE_TEMPLATE = "{title} ({version})"

logger = logging.getLogger("yandex-music-downloader")

@dataclass
class CoverInfo:
    cover_url_template: Optional[str]

    def cover_url(self, resolution: int) -> Optional[str]:
        if self.cover_url_template is None:
            return

        return self.cover_url_template.replace("%%", f"{resolution}x{resolution}")

    @classmethod
    def from_json(cls, data: dict) -> "CoverInfo":
        og_image = data.get("ogImage")
        if og_image is None or og_image == "":
            return cls(None)
        return cls(f"https://{og_image}")


@dataclass
class PlaylistId:
    owner: str
    kind: int


@dataclass
class BasicArtistInfo:
    id: str
    name: str

    @classmethod
    def from_json(cls, data: dict) -> "BasicArtistInfo":
        return cls(id=data["id"], name=data["name"])


@dataclass
class FullArtistInfo(BasicArtistInfo):
    albums: list["BasicAlbumInfo"]
    cover_info: CoverInfo

    @classmethod
    def from_json(cls, data: dict) -> "FullArtistInfo":
        base = BasicArtistInfo.from_json(data["artist"])
        albums = map(BasicAlbumInfo.from_json, data.get("albums", []))
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
    def from_json(cls, data: dict) -> Optional["BasicAlbumInfo"]:
        artists = parse_artists(data["artists"])
        title = parse_title(data)
        if release_date := data.get("releaseDate"):
            release_date = dt.datetime.fromisoformat(release_date)
        return cls(
            id=data["id"],
            title=title,
            year=data.get("year"),
            meta_type=data["metaType"],
            artists=artists,
            release_date=release_date,
        )


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
    def from_json(cls, data: dict) -> Optional["BasicTrackInfo"]:
        try:
            if not data["available"]:
                return None
            track_id = str(data["id"])
            title = parse_title(data)
            albums_data = data["albums"]
            artists = parse_artists(data["artists"])
            track_position = {"index": 1, "volume": 1}
            if len(albums_data):
                album_data = albums_data[0]
                album = BasicAlbumInfo.from_json(album_data)
                track_position = album_data.get("trackPosition", track_position)
            else:
                album = BasicAlbumInfo(
                    id=track_id,
                    title=title,
                    release_date=None,
                    year=None,
                    meta_type="music",
                    artists=artists,
                )
            if album is None:
                raise ValueError
            cover_info = CoverInfo.from_json(data)
            has_lyrics = data.get("lyricsInfo", {}).get("hasAvailableTextLyrics", False)
            return cls(
                title=title,
                id=track_id,
                real_id=data["realId"],
                number=track_position["index"],
                disc_number=track_position["volume"],
                artists=artists,
                album=album,
                has_lyrics=has_lyrics,
                cover_info=cover_info,
            )
        except Exception:
            logger.error(traceback.format_exc())
            return None

    @property
    def url(self) -> str:
        return f"https://music.yandex.ru/album/{self.album.id}/track/{self.id}"


@dataclass
class FullTrackInfo(BasicTrackInfo):
    lyrics: str

    @classmethod
    def from_json(cls, data: dict) -> "FullTrackInfo":
        try:
            base = BasicTrackInfo.from_json(data["track"])
            lyrics = data["lyric"][0]["fullLyrics"]
            return cls(**base.__dict__, lyrics=lyrics)
        except Exception:
            logger.error(traceback.format_exc())
            return None


@dataclass
class FullAlbumInfo(BasicAlbumInfo):
    tracks: list[BasicTrackInfo]

    @classmethod
    def from_json(cls, data: dict) -> "FullAlbumInfo":
        base = BasicAlbumInfo.from_json(data)
        tracks = data.get("volumes", [])
        tracks = [t for v in tracks for t in v]
        tracks = map(BasicTrackInfo.from_json, tracks)
        tracks = [t for t in tracks if t is not None]
        return cls(**base.__dict__, tracks=tracks)


def parse_artists(data: list) -> list[BasicArtistInfo]:
    artists = []
    for artist in data:
        artists.append(artist)
        if decomposed := artist.get("decomposed"):
            for d_artist in decomposed:
                if isinstance(d_artist, dict):
                    artists.append(d_artist)
    return [BasicArtistInfo.from_json(a) for a in artists]


def parse_title(data: dict) -> str:
    title = data["title"]
    if version := data.get("version"):
        title = TITLE_TEMPLATE.format(title=title, version=version)
    return title
