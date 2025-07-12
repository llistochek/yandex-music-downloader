import logging


def setup_logger(debug: bool = False) -> logging.Logger:
    logging.basicConfig(
        format="%(asctime)s |%(levelname)s| %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if debug else logging.ERROR,
    )
    return logging.getLogger("yandex-music-downloader")
