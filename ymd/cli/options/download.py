
from enum import Enum
from typing import Annotated

import typer

from .help_panels import HelpPanels

StickToArtistOption = Annotated[
    bool,
    typer.Option(
        "--stick-to-artist/--no-stick-to-artist",
        help="Сохранять треки только основного артиста",
        show_default=True,
        rich_help_panel=HelpPanels.download,
    ),
]

class DownloadTypes(str, Enum):
    url = "url"
    artist_id = "artist_id"
    album_id = "album_id"
    track_id = "track_id"
    playlist_id = "playlist_id"

DownloadTypeArgument = Annotated[
    DownloadTypes,
    typer.Argument(
        help="Тип цели загрузки (что качаем)",
        show_default=False,
        case_sensitive=False,
        metavar="url | artist_id | album_id | track_id | playlist_id",
        rich_help_panel=HelpPanels.download,
    )
]

TargetOption = Annotated[
    str,
    typer.Argument(
        help="Цель загрузки (ссылка или ID артиста, альбома, трека или плейлиста)",
        show_default=False,
        rich_help_panel=HelpPanels.download,
    )
]

TokenOption = Annotated[
    str, 
    typer.Option(
        "--token",
        "-t",
        show_default=False,
        help="Yandex Music API Токен доступа",
        rich_help_panel=HelpPanels.download,
    )
]

class DownloadQuality(int, Enum):
    aac_128 = 0
    mp3_320 = 1
    flac = 2

QualityOption = Annotated[
    DownloadQuality,
    typer.Option(
        "--quality",
        "-q",
        help="Качество загрузки (aac_128 - 0, mp3_320 - 1, flac - 2)",
        metavar="0 | 1 | 2",
        show_choices=True,
        rich_help_panel=HelpPanels.download
    )
]

OnlyMusicOption = Annotated[
    bool,
    typer.Option(
        "--only-music/--no-only-music",
        help="Загружать только музыкальные файлы (игнорировать подкасты/аудиокниги)",
        show_default=True,
        rich_help_panel=HelpPanels.download,
    ),
]