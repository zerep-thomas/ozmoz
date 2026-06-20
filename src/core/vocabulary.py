import json
import logging
from src.core.data import get_portable_data_dir

logger = logging.getLogger(__name__)

class VocabularyManager:
    """Manages custom vocabulary words for transcription."""

    def __init__(self, event_bus=None):
        self.filepath = get_portable_data_dir() / "vocabulary.json"
        self.event_bus = event_bus
        self._words = []
        self._load()

    def _load(self) -> None:
        if not self.filepath.exists():
            self._words = []
            self._save()
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._words = data
            else:
                self._words = []
        except Exception:
            self._words = []

    def _save(self) -> None:
        self.filepath.write_text(json.dumps(self._words, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_word(self, word: str) -> bool:
        word = word.strip()
        if not word or word in self._words:
            return False
        self._words.append(word)
        self._save()
        self._notify_change()
        return True

    def remove_word(self, index: int) -> None:
        if 0 <= index < len(self._words):
            del self._words[index]
            self._save()
            self._notify_change()

    def get_words(self) -> list:
        return list(self._words)

    def _notify_change(self) -> None:
        if self.event_bus:
            self.event_bus.publish("vocabulary_updated", None)