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
    """Copy data from a url to a local file."""
    progress.console.log(f"Загрузка {path.name}")
    response = session.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    progress.update(task_id, total=total_size)
    with open(path, "wb") as dest_file:
        progress.start_task(task_id)
        for data in response.iter_content(chunk_size=1024):
            dest_file.write(data)
            progress.update(task_id, advance=len(data), refresh=False)


def download_file(session: Session, url: str, path: Path) -> None:
    with progress:
        filename = path.name
        task_id = progress.add_task("download", filename=filename, start=False)
        copy_url(session, task_id, url, path)
    if progress.finished:
        progress.console.log(f"Загружен файл {path.name}")


def download_bytes(session: Session, url: str) -> bytes:
    return session.get(url).content
