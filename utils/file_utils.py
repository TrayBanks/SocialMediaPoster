import math
import mimetypes
import os
from pathlib import Path

VALID_VIDEO_MIMES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
    "video/mpeg",
    "video/3gpp",
    "video/x-flv",
}

VALID_IMAGE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}


def validate_video_file(path: str) -> None:
    """Raise ValueError if path is not a valid, accessible video file."""
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Video file not found: '{path}'")
    if not p.is_file():
        raise ValueError(f"Path is not a file: '{path}'")
    mime, _ = mimetypes.guess_type(str(p))
    if mime not in VALID_VIDEO_MIMES:
        raise ValueError(
            f"File '{path}' does not appear to be a supported video format "
            f"(detected MIME: {mime or 'unknown'}).\n"
            f"Supported formats: mp4, mov, avi, mkv, webm, mpeg, 3gp, flv"
        )


def validate_thumbnail_file(path: str) -> None:
    """Raise ValueError if path is not a valid, accessible image file."""
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Thumbnail file not found: '{path}'")
    if not p.is_file():
        raise ValueError(f"Thumbnail path is not a file: '{path}'")
    mime, _ = mimetypes.guess_type(str(p))
    if mime not in VALID_IMAGE_MIMES:
        raise ValueError(
            f"Thumbnail '{path}' is not a supported image format "
            f"(detected MIME: {mime or 'unknown'}).\n"
            f"Supported formats: jpg, png, gif, webp"
        )


def get_file_size(path: str) -> int:
    """Return the file size in bytes."""
    return os.path.getsize(path)


def get_mime_type(path: str) -> str:
    """Return the MIME type of a file, defaulting to 'application/octet-stream'."""
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def chunk_count(file_size: int, chunk_size: int) -> int:
    """Return the number of chunks needed to upload a file."""
    return math.ceil(file_size / chunk_size)


# Filenames auto-detected when no --metadata-file is provided
_METADATA_NAMES = ["meta.yaml", "meta.yml", "meta.json"]

# Filenames auto-detected when no --thumbnail is provided
_THUMBNAIL_NAMES = [
    "thumbnail.jpg", "thumbnail.jpeg", "thumbnail.png", "thumbnail.webp",
    "thumb.jpg",     "thumb.jpeg",     "thumb.png",     "thumb.webp",
    "cover.jpg",     "cover.jpeg",     "cover.png",     "cover.webp",
]


def find_latest_video(folder: str) -> str | None:
    """
    Return the most recently modified video file in the given folder, or None.
    Checks for all supported video extensions.
    """
    extensions = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".mpeg", ".mpg", ".3gp", ".flv"}
    folder_path = Path(folder)
    if not folder_path.is_dir():
        raise ValueError(f"Folder not found: '{folder}'")

    videos = [
        f for f in folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in extensions
    ]

    if not videos:
        return None

    return str(max(videos, key=lambda f: f.stat().st_mtime))



    """
    Look for a metadata file alongside the video.
    Returns the first match from _METADATA_NAMES, or None if none found.
    """
    folder = Path(video_path).parent
    for name in _METADATA_NAMES:
        candidate = folder / name
        if candidate.exists():
            return str(candidate)
    return None


def find_thumbnail_file(video_path: str) -> str | None:
    """
    Look for a thumbnail image alongside the video.
    Returns the first match from _THUMBNAIL_NAMES, or None if none found.
    """
    folder = Path(video_path).parent
    for name in _THUMBNAIL_NAMES:
        candidate = folder / name
        if candidate.exists():
            return str(candidate)
    return None
