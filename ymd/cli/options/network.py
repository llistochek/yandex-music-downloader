from typing import Annotated

import typer

from .help_panels import HelpPanels

RequestsDelayOption = Annotated[
    int,
    typer.Option(
        "--delay",
        help="Задержка между запросами к API (в миллисекундах)",
        show_default=True,
        metavar="Секунды",
        rich_help_panel=HelpPanels.network,
    )
]

ResponseTimeoutOption = Annotated[
    int,
    typer.Option(
        "--response-timeout",
        help="Максимальное время ожидания ответа от API (в секундах) - Если есть сетевые ошибки - увеличьте это значение",
        show_default=True,
        metavar="Секунды",
        min=0,
        rich_help_panel=HelpPanels.network,
    )
]

RetryCountOption = Annotated[
    int,
    typer.Option(
        "--retry-count",
        help="Количество попыток повторного запроса при ошибках сети (0 - бесконечно)",
        show_default=True,
        metavar="Количество",
        min=0,
        rich_help_panel=HelpPanels.network,
    )
]
