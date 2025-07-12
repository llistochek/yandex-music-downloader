from typing import Annotated

import typer

from .help_panels import HelpPanels

RequestsDelayOption = Annotated[
    int,
    typer.Option(
        "--delay",
        help="Задержка между запросами к API (в миллисекундах)",
        show_default=True,
        rich_help_panel=HelpPanels.network,
    )
]

ResponseTimeoutOption = Annotated[
    int,
    typer.Option(
        "--response-timeout",
        help="Максимальное время ожидания ответа от API (в секундах) - Если есть сетевые ошибки - увеличьте это значение",
        show_default=True,
        min=0,
        rich_help_panel=HelpPanels.network,
    )
]
