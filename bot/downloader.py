from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from yt_dlp import YoutubeDL

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class FormatOption:
    format_id: str
    description: str
    is_audio: bool


@dataclass(slots=True)
class MediaMetadata:
    title: str
    uploader: str | None
    duration: int | None
    webpage_url: str
    formats: list[FormatOption]


@dataclass(slots=True)
class DownloadResult:
    file_path: Path
    is_audio: bool
    file_size: int
    title: str


ProgressCallback = Callable[[dict[str, Any]], None]


_FORMAT_PATTERNS = {
    "1080p": re.compile(r"^(?=.*1080).*"),
    "720p": re.compile(r"^(?=.*720).*"),
    "480p": re.compile(r"^(?=.*480).*"),
    "audio128": re.compile(r"audio"),
    "audio192": re.compile(r"audio"),
}


async def extract_metadata(url: str) -> MediaMetadata:
    def _extract() -> MediaMetadata:
        with YoutubeDL({"skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        formats = _simplify_formats(info.get("formats", []))
        return MediaMetadata(
            title=info.get("title", "Unknown title"),
            uploader=info.get("uploader"),
            duration=info.get("duration"),
            webpage_url=info.get("webpage_url", url),
            formats=formats,
        )

    return await asyncio.to_thread(_extract)


def _simplify_formats(formats: Iterable[dict[str, Any]]) -> list[FormatOption]:
    result: list[FormatOption] = []
    seen: set[str] = set()
    for fmt in formats:
        format_id = fmt.get("format_id")
        if not format_id or format_id in seen:
            continue
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        height = fmt.get("height")
        abr = fmt.get("abr")
        if vcodec != "none" and height:
            label = f"Video {height}p"
            result.append(FormatOption(format_id=format_id, description=label, is_audio=False))
        elif acodec != "none" and abr:
            label = f"Audio {int(abr)} kbps"
            result.append(FormatOption(format_id=format_id, description=label, is_audio=True))
        elif acodec != "none" and not vcodec:
            label = "Audio"
            result.append(FormatOption(format_id=format_id, description=label, is_audio=True))
        seen.add(format_id)
    # Deduplicate by description keeping first
    unique: dict[str, FormatOption] = {}
    for option in result:
        unique.setdefault(option.description, option)
    return list(unique.values())


async def download_media(
    url: str,
    download_dir: Path,
    format_id: str,
    progress_callback: ProgressCallback | None = None,
) -> DownloadResult:
    loop = asyncio.get_running_loop()
    done_event = asyncio.Event()
    last_data: dict[str, Any] = {}

    def hook(d: dict[str, Any]) -> None:
        nonlocal last_data
        last_data = d
        if progress_callback:
            loop.call_soon_threadsafe(progress_callback, d)
        if d.get("status") == "finished":
            loop.call_soon_threadsafe(done_event.set)

    def _download() -> DownloadResult:
        outtmpl = str(download_dir / "%(title).200s-%(id)s.%(ext)s")
        opts = {
            "format": format_id,
            "outtmpl": outtmpl,
            "progress_hooks": [hook],
            "noplaylist": True,
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = Path(ydl.prepare_filename(info))
        size = file_path.stat().st_size if file_path.exists() else 0
        is_audio = info.get("vcodec") == "none" or info.get("acodec") and not info.get("vcodec")
        return DownloadResult(
            file_path=file_path,
            is_audio=is_audio,
            file_size=size,
            title=info.get("title", file_path.stem),
        )

    result = await asyncio.to_thread(_download)
    if not done_event.is_set():
        done_event.set()
    return result


def pick_format(metadata: MediaMetadata, quality: str | None) -> FormatOption | None:
    if not metadata.formats:
        return None
    if not quality:
        return metadata.formats[0]
    pattern = _FORMAT_PATTERNS.get(quality.lower())
    if not pattern:
        return metadata.formats[0]
    for option in metadata.formats:
        if pattern.match(option.description.lower()) or pattern.match(option.format_id.lower()):
            return option
    return metadata.formats[0]


def sanitize_filename(name: str) -> str:
    name = re.sub(r"\s+(official video|lyrics|audio|video)\b", "", name, flags=re.I)
    name = re.sub(r"[\[\](){}]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()
