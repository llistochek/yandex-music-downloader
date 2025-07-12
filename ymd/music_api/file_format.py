
from dataclasses import dataclass
from enum import Enum, auto


class Container(Enum):
    FLAC = auto()
    MP3 = auto()
    MP4 = auto()


class Codec(Enum):
    FLAC = auto()
    MP3 = auto()
    AAC = auto()


@dataclass
class FileFormat:
    container: Container
    codec: Codec

FILE_FORMAT_MAPPING = {
    "flac": FileFormat(Container.FLAC, Codec.FLAC),
    "flac-mp4": FileFormat(Container.MP4, Codec.FLAC),
    "mp3": FileFormat(Container.MP3, Codec.MP3),
    "aac": FileFormat(Container.MP4, Codec.AAC),
    "he-aac": FileFormat(Container.MP4, Codec.AAC),
    "aac-mp4": FileFormat(Container.MP4, Codec.AAC),
    "he-aac-mp4": FileFormat(Container.MP4, Codec.AAC),
}