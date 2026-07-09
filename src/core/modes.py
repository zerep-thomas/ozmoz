import json
import logging
from pathlib import Path

from src.core.data import get_portable_data_dir
from src.core.utils import atomic_write_json

logger = logging.getLogger(__name__)

DEFAULT_MODES = {
    "default": {
        "name": "Default",
        "preset": "Voice to text",
        "language": "English",
        "voice_model": "Whisper V3 Turbo"
    }
}


class ModeManager:
    """Manages the storage and reading of mode configurations (e.g., Default mode)."""

    def __init__(self, event_bus=None):
        self.filepath = get_portable_data_dir() / "modes.json"
        self.event_bus = event_bus
        self._modes = {}
        self.load()

    def load(self):
        if self.filepath.exists():
            try:
                self._modes = json.loads(self.filepath.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Error reading modes.json: {e}", exc_info=True)
                self._modes = DEFAULT_MODES.copy()
        else:
            self._modes = DEFAULT_MODES.copy()
            self.save()

        if "default" not in self._modes:
            self._modes["default"] = DEFAULT_MODES["default"].copy()

    def save(self):
        atomic_write_json(self.filepath, self._modes)

    def get_mode(self, mode_id="default"):
        return self._modes.get(mode_id, DEFAULT_MODES["default"])

    def update_mode(self, mode_id, key, value):
        if mode_id not in self._modes:
            self._modes[mode_id] = DEFAULT_MODES["default"].copy()
            self._modes[mode_id]["name"] = mode_id
        self._modes[mode_id][key] = value
        self.save()
        if self.event_bus:
            self.event_bus.publish("mode_updated", {"mode_id": mode_id, "key": key, "value": value})

    def add_mode(self, mode_id, name, preset, language, voice_model):
        self._modes[mode_id] = {
            "name": name,
            "preset": preset,
            "language": language,
            "voice_model": voice_model
        }
        self.save()
        if self.event_bus:
            self.event_bus.publish("mode_updated", {"mode_id": mode_id, "created": True})

    def delete_mode(self, mode_id):
        if mode_id in self._modes and mode_id not in ["default", "system"]:
            del self._modes[mode_id]
            self.save()
            if self.event_bus:
                self.event_bus.publish("mode_updated", {"mode_id": mode_id, "deleted": True})

    def get_custom_modes(self):
        return {k: v for k, v in self._modes.items() if k not in ["default", "system"]}