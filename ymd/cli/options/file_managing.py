from pathlib import Path
from typing import Annotated

import typer

from ymd.cli.options.help_panels import HelpPanels

SkipExistingOption = Annotated[
    bool,
    typer.Option(
        "--skip-existing",
        "-s",
        help="Пропустить файлы, которые уже существуют в директории загрузки",
        show_default=True,
        rich_help_panel=HelpPanels.file_managing,
    )
] 

DownloadDirectoryOption = Annotated[
    Path,
    typer.Option(
        "--download-dir",
        "-d",
        help="Директория для загрузки музыки",
        show_default=True,
        exists=False,
        file_okay=False,
        dir_okay=True,
        writable=True,
        readable=True,
        resolve_path=True,
        rich_help_panel=HelpPanels.file_managing,
    )
]
