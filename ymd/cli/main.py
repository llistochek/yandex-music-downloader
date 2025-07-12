from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ymd.cli.options.download import (
    DownloadQuality,
    DownloadTypeArgument,
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
    LyricsFormat,
    LyricsFormatOption,
    TagsCompatibility,
    TagsCompatibilityOption,
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
        lyrics_format: LyricsFormatOption = LyricsFormat.none,
        embed_cover: EmbedCoverOption = False,
        cover_resolution: CoverResolutionOption = "400",
        tags_compatibility: TagsCompatibilityOption = TagsCompatibility.m4a_compatible,

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
            

        ymd url https://music.yandex.ru/album/123456 --token YOUR_TOKEN
    """


    console = Console()

    table = Table(title="🎶 Yandex Music Download Options", show_header=True, header_style="bold magenta")
    table.add_column("📝 Option", style="dim", width=18)
    table.add_column("🔢\tValue", style="bold")

    # Основные
    table.add_section()
    table.add_row("🎯  Target", f"{target}")
    table.add_row("📂  Target Type", f"{type}")
    table.add_row("🔑  Token", f"{token}")

    # Загрузка  
    table.add_section()
    table.add_row("🎼  Quality", f"{quality}")
    table.add_row("🎏  Skip Existing", f"{skip_existing}")
    table.add_row("📁  Directory", f"{download_dir}")
    table.add_row("📝  Stick to Artist", f"{stick_to_artist}")
    table.add_row("🎵  Only Music", f"{only_music}")

    # Метаданные
    table.add_section()
    table.add_row("📷  Embed Cover", f"{embed_cover}")
    table.add_row("🖼️  Cover Resolution", f"{cover_resolution}")
    table.add_row("📝  Lyrics Format", f"{lyrics_format}")
    table.add_row("🏷️  Tags Compatibility", f"{tags_compatibility}")

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
    typer.run(main)
