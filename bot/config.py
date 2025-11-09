from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    telegram_token: str
    download_dir: Path
    max_file_size_mb: int
    max_concurrent_downloads: int
    log_level: str

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


_settings: Settings | None = None


def load_settings() -> Settings:
    global _settings
    if _settings is not None:
        return _settings

    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    download_dir = Path(os.getenv("DOWNLOAD_DIR", "downloads")).expanduser()
    download_dir.mkdir(parents=True, exist_ok=True)

    max_file_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "1900"))
    max_concurrent_downloads = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _settings = Settings(
        telegram_token=token,
        download_dir=download_dir,
        max_file_size_mb=max_file_size_mb,
        max_concurrent_downloads=max_concurrent_downloads,
        log_level=log_level,
    )
    return _settings


def get_settings() -> Settings:
    return load_settings()
