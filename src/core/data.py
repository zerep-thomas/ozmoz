import sys
import base64
import json
import logging
import uuid
import win32crypt
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from src.core.utils import PathManager

logger = logging.getLogger(__name__)

def get_portable_data_dir() -> Path:
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path.cwd()
    
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

class CredentialManager:
    """Manages secure storage and retrieval of API keys using Windows DPAPI."""

    def __init__(self):
        self.filepath = get_portable_data_dir() / "credentials.json"
        if not self.filepath.exists():
            self.filepath.write_text("{}", encoding="utf-8")

    def get_api_key(self, service: str) -> Optional[str]:
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
            encrypted_key = data.get(service)
            if not encrypted_key:
                return None
            
            try:
                decoded = base64.b64decode(encrypted_key)
                decrypted = win32crypt.CryptUnprotectData(decoded, None, None, None, 0)[1]
                return decrypted.decode('utf-8')
            except Exception:
                logger.warning("Failed to decrypt API key for service: %s", service)
                return None
        except Exception:
            logger.exception("Failed to read credentials file")
            return None

    def save_api_key(self, service: str, key: str) -> None:
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
        except Exception:
            data = {}
            
        if key:
            encrypted_bytes = win32crypt.CryptProtectData(key.encode('utf-8'), None, None, None, None, 0)
            data[service] = base64.b64encode(encrypted_bytes).decode('utf-8')
        else:
            data[service] = ""
            
        self.filepath.write_text(json.dumps(data, indent=4), encoding="utf-8")

class HistoryManager:
    """Manages the storage and retrieval of transcription history."""

    def __init__(self, event_bus=None):
        self.filepath = get_portable_data_dir() / "history.json"
        self.event_bus = event_bus
        if not self.filepath.exists():
            self.filepath.write_text("[]", encoding="utf-8")

    def add_entry(self, text: str, duration_sec: float, processing_sec: float, method: str) -> None:
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
        except Exception:
            data = []

        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "text": text,
            "words": len(text.split()),
            "audio_duration_sec": round(duration_sec, 2),
            "processing_time_sec": round(processing_sec, 2),
            "method": method
        }
        data.append(entry)
        self.filepath.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")

        if self.event_bus:
            self.event_bus.publish("history_updated", None)

    def delete_entry(self, entry_id: str) -> None:
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
            new_data = [item for item in data if item.get("id") != entry_id]
            
            if len(new_data) != len(data):
                self.filepath.write_text(json.dumps(new_data, indent=4, ensure_ascii=False), encoding="utf-8")
                if self.event_bus:
                    self.event_bus.publish("history_updated", None)
        except Exception:
            logger.exception("Failed to delete history entry")

    def get_all(self) -> list:
        try:
            return json.loads(self.filepath.read_text(encoding="utf-8"))
        except Exception:
            return []

class StatsManager:
    """Calculates usage statistics based on history."""

    def __init__(self, history_manager: HistoryManager):
        self.history_manager = history_manager

    def get_home_stats(self) -> dict:
        history = self.history_manager.get_all()
        now = datetime.now()
        one_week_ago = now - timedelta(days=7)

        total_words_ever = 0
        total_audio_sec_ever = 0
        words_this_week = 0
        audio_sec_this_week = 0
        processing_sec_this_week = 0

        for entry in history:
            try:
                dt = datetime.fromisoformat(entry.get("timestamp", now.isoformat()))
                w = entry.get("words", 0)
                a_sec = entry.get("audio_duration_sec", 0)
                p_sec = entry.get("processing_time_sec", 0)

                total_words_ever += w
                total_audio_sec_ever += a_sec

                if dt >= one_week_ago:
                    words_this_week += w
                    audio_sec_this_week += a_sec
                    processing_sec_this_week += p_sec
            except Exception:
                continue

        avg_speed_wpm = int(total_words_ever / (total_audio_sec_ever / 60)) if total_audio_sec_ever > 0 else 0

        manual_typing_time_min = words_this_week / 40.0
        app_time_min = (audio_sec_this_week + processing_sec_this_week) / 60.0
        time_saved_min = max(0, int(round(manual_typing_time_min - app_time_min)))

        return {
            "avgSpeed": f"{avg_speed_wpm} WPM",
            "wordsThisWeek": str(words_this_week),
            "timeSaved": f"{time_saved_min} minutes"
        }

class ChangelogManager:
    """Reads the changelog file."""

    def __init__(self):
        self.filepath = Path(PathManager.get_resource_path("data/changelog.json"))

    def get_changelog(self) -> list:
        try:
            return json.loads(self.filepath.read_text(encoding="utf-8"))
        except Exception:
            return []