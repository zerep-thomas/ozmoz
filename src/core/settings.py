import json
import logging
from src.core.data import get_portable_data_dir

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "play_sounds": True,
    "auto_check_updates": True
}

class SettingsManager:
    """Manages loading and saving of application settings."""

    def __init__(self, event_bus=None):
        self.filepath = get_portable_data_dir() / "settings.json"
        self.event_bus = event_bus
        self._settings = {}
        self.load()

    def load(self) -> None:
        try:
            if self.filepath.exists():
                self._settings = json.loads(self.filepath.read_text(encoding="utf-8"))
            else:
                self._settings = DEFAULT_SETTINGS.copy()
        except Exception:
            logger.exception("Failed to load settings")
            self._settings = DEFAULT_SETTINGS.copy()
        
        for key, value in DEFAULT_SETTINGS.items():
            self._settings.setdefault(key, value)
        
        self.save()

    def save(self) -> None:
        try:
            self.filepath.write_text(json.dumps(self._settings, indent=4), encoding="utf-8")
        except Exception:
            logger.exception("Failed to save settings")

    def get(self, key: str, default=None):
        return self._settings.get(key, default)

    def set(self, key: str, value) -> None:
        self._settings[key] = value
        self.save()
        if self.event_bus:
            self.event_bus.publish("settings_updated", {"key": key, "value": value})

    def get_all(self) -> dict:
        return self._settings.copy()