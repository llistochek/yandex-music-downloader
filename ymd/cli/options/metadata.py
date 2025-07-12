from enum import Enum
from typing import Annotated

import typer

from .help_panels import HelpPanels


class LyricsFormat(str, Enum):
    none = "none"
    text = "text"
    lrc = "lrc"

LyricsFormatOption = Annotated[
    LyricsFormat,
    typer.Option(
        "--lyrics-format",
        "-l",
        help="Формат загрузки текстов песен (none - не загружать, text - обычный текст, lrc - LRC формат)",
        metavar="none | text | lrc",
        show_choices=True,
        rich_help_panel=HelpPanels.metadata
    )
]


CoverResolutionOption = Annotated[
    str,
    typer.Option(
        "--cover-resolution",
        help="Разрешение обложки",
        metavar="Пиксели",
        show_default=True,
        rich_help_panel=HelpPanels.metadata
    )
]


EmbedCoverOption = Annotated[
    bool,
    typer.Option(
        "--embed-cover/--no-embed-cover",
        help="Встраивать ли обложку в файл",
        show_default=True,
        rich_help_panel=HelpPanels.metadata
    ),
]

class TagsCompatibility(str, Enum):
    mutagen = "mutagen"
    m4a_compatible = "m4a_compatible"
    

TagsCompatibilityOption = Annotated[
    TagsCompatibility,
    typer.Option(
        "--tags-compatibility",
        help="Совместимость тегов (mutagen, m4a_compatible - для M4A файлов с разделением через ;)",
        show_choices=True,
        rich_help_panel=HelpPanels.metadata,
        metavar="mutagen | m4a_compatible",
    )
]
