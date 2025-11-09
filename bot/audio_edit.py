from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import ffmpeg
from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import APIC, ID3, error as ID3Error

from .downloader import sanitize_filename


@dataclass(slots=True)
class AudioEditResult:
    file_path: Path
    title: str


async def copy_audio_to_temp(source_path: Path, temp_dir: Path) -> Path:
    def _copy() -> Path:
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / source_path.name
        shutil.copy2(source_path, temp_path)
        return temp_path

    return await asyncio.to_thread(_copy)


async def apply_rename(source: Path, temp_dir: Path, new_title: str) -> AudioEditResult:
    sanitized = sanitize_filename(new_title)
    target = temp_dir / f"{sanitized}{source.suffix}"

    def _process() -> AudioEditResult:
        shutil.copy2(source, target)
        audio = MutagenFile(target, easy=True)
        if audio is not None:
            if isinstance(audio, EasyID3):
                audio["title"] = [sanitized]
            else:
                audio["title"] = sanitized
            audio.save()
        return AudioEditResult(file_path=target, title=sanitized)

    return await asyncio.to_thread(_process)


async def apply_cover(
    source: Path,
    temp_dir: Path,
    image_path: Path,
    new_title: Optional[str] = None,
) -> AudioEditResult:
    sanitized = sanitize_filename(new_title) if new_title else source.stem
    target = temp_dir / f"{sanitized}{source.suffix}"

    def _ffmpeg_embed() -> None:
        stream_audio = ffmpeg.input(str(source))
        stream_cover = ffmpeg.input(str(image_path))
        (
            ffmpeg.output(
                stream_audio,
                stream_cover,
                str(target),
                c="copy",
                id3v2_version=3,
                **{"metadata:s:v": "title=Cover", "metadata:s:v:0": "comment=Cover"},
            )
            .global_args("-map", "0", "-map", "1")
            .overwrite_output()
            .run(quiet=True)
        )

    await asyncio.to_thread(_ffmpeg_embed)

    async def _mutagen_cover() -> None:
        def _write() -> None:
            try:
                tags = ID3(str(target))
            except ID3Error:
                tags = ID3()
            with open(image_path, "rb") as img:
                tags.add(
                    APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,
                        desc="Cover",
                        data=img.read(),
                    )
                )
            tags.save(str(target))
        await asyncio.to_thread(_write)

    await _mutagen_cover()
    return AudioEditResult(file_path=target, title=sanitized)
