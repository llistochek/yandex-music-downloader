from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ymd.cli.options.download import (
    DownloadQuality,
    DownloadTypeArgument,
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
    LyricsFormat,
    LyricsFormatOption,
)
from ymd.cli.options.network import (
    RequestsDelayOption,
    ResponseTimeoutOption,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

DEFAULT_DOWNLOAD_DIR = Path(".")

# Doc string функции - выводится в --help справке
@app.callback()
def main(
        # Обязательные аргументы
        type: DownloadTypeArgument,
        target: TargetOption,
        token: TokenOption,

        # Опциональные настройки
        quality: QualityOption = DownloadQuality.mp3_320,
        lyrics_format: LyricsFormatOption = LyricsFormat.none,
        embed_cover: EmbedCoverOption = False,
        cover_resolution: CoverResolutionOption = "400",
        stick_to_artist: StickToArtistOption = False,

        # Работа с файлами
        download_dir: DownloadDirectoryOption = DEFAULT_DOWNLOAD_DIR,
        skip_existing: SkipExistingOption = False,
        path_pattern: PathPatternOption = "{artist}/{album}/{title}",
        unsafe_path: UnsafePathOption = False,

        # Настройки сети
        delay: RequestsDelayOption = 0,
        response_timeout: ResponseTimeoutOption = 20,
    ):
    """
        🎵 yandex-music-downloader - Позволяет скачивать музыку с Яндекс Музыки

        📚 Примеры использования:
            

        ymd url https://music.yandex.ru/album/123456 --token YOUR_TOKEN --quality 1 
    """


    console = Console()

    table = Table(title="🎶 Yandex Music Download Options", show_header=True, header_style="bold magenta")
    table.add_column("📝 Option", style="dim", width=18)
    table.add_column("🔢\tValue", style="bold")

    # Основные параметры
    table.add_section()
    table.add_row("🎯  Target", f"{target}")
    table.add_row("📂  Target Type", f"{type}")
    table.add_row("🔑  Token", f"{token}")

    # Параметры загрузки
    table.add_section()
    table.add_row("🎼  Quality", f"{quality}")
    table.add_row("🎏  Skip Existing", f"{skip_existing}")
    table.add_row("📁  Directory", f"{download_dir}")
    table.add_row("📝  Stick to Artist", f"{stick_to_artist}")

    # Параметры обложки и текста
    table.add_section()
    table.add_row("📷  Embed Cover", f"{embed_cover}")
    table.add_row("🖼️  Cover Resolution", f"{cover_resolution}")
    table.add_row("📝  Lyrics Format", f"{lyrics_format}")

    # Сеть
    table.add_section()
    table.add_row("📅  Delay", f"{delay}")   
    table.add_row("⏳  Response Timeout", f"{response_timeout}")

    # Путь и шаблон
    table.add_section()
    table.add_row("📂  Download Directory", f"{download_dir}")
    table.add_row("📝  Path Pattern", f"{path_pattern}")
    table.add_row("🔒  Unsafe Path", f"{unsafe_path}")

    console.print(table)

def run():
    # Запуск приложения с зарегистрированными флагами и командами
    app()
