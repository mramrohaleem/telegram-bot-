from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


NAMING_TEMPLATES = [
    "{title}",
    "{title} - {uploader}",
    "{playlist} - {title}",
]


@dataclass(slots=True)
class UserSettings:
    naming_template_index: int = 0
    video_send_as_document: bool = False
    name_mode: str = "auto"  # auto | ask

    @property
    def naming_template(self) -> str:
        return NAMING_TEMPLATES[self.naming_template_index % len(NAMING_TEMPLATES)]


class SettingsStore:
    def __init__(self) -> None:
        self._store: Dict[int, UserSettings] = {}

    def get(self, user_id: int) -> UserSettings:
        if user_id not in self._store:
            self._store[user_id] = UserSettings()
        return self._store[user_id]

    def cycle_template(self, user_id: int) -> UserSettings:
        settings = self.get(user_id)
        settings.naming_template_index = (settings.naming_template_index + 1) % len(NAMING_TEMPLATES)
        return settings

    def toggle_send_type(self, user_id: int) -> UserSettings:
        settings = self.get(user_id)
        settings.video_send_as_document = not settings.video_send_as_document
        return settings

    def toggle_name_mode(self, user_id: int) -> UserSettings:
        settings = self.get(user_id)
        settings.name_mode = "ask" if settings.name_mode == "auto" else "auto"
        return settings


settings_store = SettingsStore()
