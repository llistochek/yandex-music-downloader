from pathlib import Path

from requests import Session


def download_file(session: Session, url: str, path: Path) -> None:
    resp = session.get(url)
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024):
            f.write(chunk)


def download_bytes(session: Session, url: str) -> bytes:
    return session.get(url).content
