from pathlib import Path

from requests import Session
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from ymd import logger

progress = Progress(
    TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
    BarColumn(bar_width=None),
    "[progress.percentage]{task.percentage:>3.1f}%",
    "•",
    DownloadColumn(),
    "•",
    TransferSpeedColumn(),
    "•",
    TimeRemainingColumn(),
)

def copy_url(session: Session, task_id: TaskID, url: str, path: Path) -> None:
    """Копирование данных из URL в локальный файл."""
    progress.console.log(f"Загрузка {path.name}")
    try:
        with session.get(url, stream=True) as response:
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            progress.update(task_id, total=total_size)
            with open(path, "wb") as dest_file:
                progress.start_task(task_id)
                for data in response.iter_content(chunk_size=1024):
                    dest_file.write(data)
                    progress.update(task_id, advance=len(data))
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла {path.name}: {e}")


def download_file(session: Session, url: str, path: Path) -> None:
    """Загрузка файла по URL."""
    with progress:
        filename = path.name
        task_id = progress.add_task("download", filename=filename, start=False)
        copy_url(session, task_id, url, path)
    if progress.finished:
        progress.console.log(f"Загружен файл {path.name}")


def download_bytes(session: Session, url: str) -> bytes:
    """Загрузка данных из URL в байтовый объект."""
    try:
        response = session.get(url)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных из {url}: {e}")
        return b''
