import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Optional

import pyaudio

logger = logging.getLogger(__name__)

# Audio capture parameters
AUDIO_CHUNK_SIZE: int = 512
AUDIO_SAMPLE_RATE_HZ: int = 16_000
AUDIO_CHANNEL_COUNT: int = 1
AUDIO_BIT_FORMAT: int = pyaudio.paInt16

# Model mappings
GROQ_MODEL_MAPPING: dict[str, str] = {
    "Whisper V3": "whisper-large-v3",
    "Whisper V3 Turbo": "whisper-large-v3-turbo"
}

SECRET_PATTERNS = [
    re.compile(r"api[_-]?key['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{20,})", re.IGNORECASE),
    re.compile(r"token['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
]

class AppConfig:
    VERSION: str = "1.0.1"
    GITHUB_RELEASES_URL: str = "https://api.github.com/repos/zerep-thomas/ozmoz/releases/latest"
    AUDIO_CHUNK: int = AUDIO_CHUNK_SIZE
    AUDIO_FORMAT: int = AUDIO_BIT_FORMAT
    AUDIO_CHANNELS: int = AUDIO_CHANNEL_COUNT
    AUDIO_RATE: int = AUDIO_SAMPLE_RATE_HZ
    DEFAULT_HOTKEYS: dict[str, str] = {
        "toggle_visibility": "ctrl+alt",
        "record_toggle": "ctrl+space",
    }

@dataclass
class ThreadingState:
    keyboard_lock: threading.Lock = field(default_factory=threading.Lock)

@dataclass
class AudioState:
    pyaudio_instance: Optional[pyaudio.PyAudio] = None
    is_recording: bool = False
    current_recording_path: Optional[str] = None
    recording_start_time: float = 0.0
    sound_enabled: bool = True

class AppState:
    def __init__(self) -> None:
        self.threading = ThreadingState()
        self.audio = AudioState()
        self.is_busy: bool = False
        self.hotkeys: dict[str, str] = AppConfig.DEFAULT_HOTKEYS.copy()

app_state = AppState()