import collections
import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pyaudio
import webview
from PySide6.QtWidgets import QSystemTrayIcon

os.environ["QT_LOGGING_RULES"] = "qt.qpa.window=false"


class AppConfig:
    VERSION: str = "1.1.3"
    MUTEX_ID: str = "{f7c9acc6-46a7-4712-89f5-171549439308}-Ozmoz"

    GITHUB_RELEASES_URL: str = (
        "https://api.github.com/repos/zerep-thomas/ozmoz/releases/latest"
    )

    AUDIO_CHUNK: int = 512
    AUDIO_FORMAT: int = pyaudio.paInt16
    AUDIO_CHANNELS: int = 1
    AUDIO_RATE: int = 16000
    AUDIO_OPTIMIZED_CHUNK: int = 2048
    AUDIO_OUTPUT_FILENAME: str = "temp_recording.wav"

    VAD_ENABLED: bool = True
    VAD_THRESHOLD: int = 300
    VAD_SILENCE_TIMEOUT: float = 0.8

    VISUALIZER_POINTS: int = 150
    VISUALIZER_MAX_HEIGHT: int = 150
    VISUALIZER_SCALING_FACTOR: int = 80

    DEFAULT_LANGUAGE: str = "en"
    DEFAULT_AI_MODEL: str = "llama-3.3-70b-versatile"
    DEFAULT_AUDIO_MODEL: str = "nova-2"

    DEFAULT_HOTKEYS: Dict[str, str] = {
        "toggle_visibility": "ctrl+alt",
        "record_toggle": "ctrl+x",
        "ai_toggle": "ctrl+q",
        "web_search_toggle": "alt+w",
        "screen_vision_toggle": "alt+x",
    }


class AppState:
    def __init__(self) -> None:
        # Threading & Synchronization
        self.keyboard_lock: threading.Lock = threading.Lock()
        self.mutex_handle: Optional[int] = None
        self.transcription_executor: Optional[Any] = None
        self.stop_app_event: threading.Event = threading.Event()
        self.settings_file_lock: threading.Lock = threading.Lock()

        # Graphic Interface
        self.tray_icon_qt: Optional[QSystemTrayIcon] = None
        self.window: Optional[webview.Window] = None
        self.settings_window: Optional[webview.Window] = None
        self.settings_open: bool = False

        # Data & Cache
        self.log_handler: Optional[logging.Handler] = None
        self.cached_remote_config: Optional[List[Any]] = None
        self.cached_models: Optional[List[str]] = None
        self.advanced_model_list: List[str] = []
        self.tool_model_list: List[str] = []
        self.web_search_model_list: List[str] = []
        self.screen_vision_model_list: List[str] = []
        self.remote_version: Optional[str] = None
        self.remote_update_url: Optional[str] = None
        self.settings: Dict[str, Any] = {}

        # Current Preferences
        self.language: str = AppConfig.DEFAULT_LANGUAGE
        self.model: str = AppConfig.DEFAULT_AI_MODEL
        self.last_selected_model: str = AppConfig.DEFAULT_AI_MODEL
        self.audio_model: str = AppConfig.DEFAULT_AUDIO_MODEL

        # Audio State
        self.pyaudio_instance: Optional[pyaudio.PyAudio] = None
        self.audio_stream: Optional[pyaudio.Stream] = None
        self.original_volume: float = 1.0
        self.is_muted: bool = False
        self.was_muted_during_recording: bool = False
        self.sound_enabled: bool = True
        self.mute_sound: bool = True

        # Functional State
        self.is_recording: bool = False
        self.current_recording_path: Optional[str] = None
        self.is_busy: bool = False
        self.is_exiting: bool = False
        self.ai_recording: bool = False
        self.recording_start_time: float = 0.0

        # Context & History
        self.original_clipboard: str = ""
        self.transcribed_text_for_ai: str = ""
        self.conversation_history: List[Dict[str, Any]] = []
        self.is_ai_response_visible: bool = False
        self.groq_client: Optional[Any] = None
        self.deepgram_client: Optional[Any] = None
        self.cerebras_client: Optional[Any] = None

        # UI Content
        self.settings_html: Optional[str] = None
        self.index_html: Optional[str] = None

        # Features
        self.chart_type: str = "line"
        self.dashboard_period: int = 7
        self.developer_mode: bool = False
        self.hotkeys: Dict[str, str] = AppConfig.DEFAULT_HOTKEYS.copy()


app_state: AppState = AppState()


class BufferingLogHandler(logging.Handler):
    def __init__(self, capacity: int = 1000) -> None:
        super().__init__()
        self.buffer: collections.deque = collections.deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self.buffer.append({"level": record.levelname, "message": self.format(record)})


class ColoredFormatter(logging.Formatter):
    RESET_CODE: str = "\033[0m"
    COLOR_MAP: Dict[str, str] = {
        "DEBUG": "\033[92m",
        "INFO": "\033[94m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[41m",
    }

    def format(self, record: logging.LogRecord) -> str:
        color: str = self.COLOR_MAP.get(record.levelname, self.RESET_CODE)
        return f"{color}{super().format(record)}{self.RESET_CODE}"


class BinaryDataFilter(logging.Filter):
    MAX_MESSAGE_LENGTH: int = 1000
    BINARY_PATTERNS: Tuple[str, ...] = ("\\x00", "\\xff")

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message: str = str(record.getMessage())
            if any(pattern in message for pattern in self.BINARY_PATTERNS):
                return False
            return len(message) <= self.MAX_MESSAGE_LENGTH
        except Exception:
            return True


class DuplicateFilter(logging.Filter):
    def __init__(self, time_window_seconds: int = 3, max_cache_size: int = 50) -> None:
        super().__init__()
        self.time_window: timedelta = timedelta(seconds=time_window_seconds)
        self.log_cache: collections.deque = collections.deque(maxlen=max_cache_size)
        self.lock = threading.Lock()

    def filter(self, record: logging.LogRecord) -> bool:
        with self.lock:
            current_time: datetime = datetime.now()
            message: str = record.getMessage()

            for timestamp, cached_message in self.log_cache:
                if (
                    message == cached_message
                    and (current_time - timestamp) < self.time_window
                ):
                    return False

            self.log_cache.append((current_time, message))
            return True


def setup_logging() -> None:
    console_formatter: ColoredFormatter = ColoredFormatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )
    buffer_formatter: logging.Formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )

    console_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.DEBUG)
    console_handler.addFilter(BinaryDataFilter())
    console_handler.addFilter(DuplicateFilter(time_window_seconds=5))

    app_state.log_handler = BufferingLogHandler()
    app_state.log_handler.setFormatter(buffer_formatter)
    app_state.log_handler.setLevel(logging.DEBUG)
    app_state.log_handler.addFilter(BinaryDataFilter())
    app_state.log_handler.addFilter(DuplicateFilter(time_window_seconds=5))

    root_logger: logging.Logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_state.log_handler)
    root_logger.setLevel(logging.DEBUG)

    libraries_to_silence: List[str] = [
        "httpx",
        "httpcore",
        "requests",
        "urllib3",
        "pyaudio",
        "pygame",
        "groq",
        "deepgram",
        "openai",
        "comtypes",
        "pycaw",
    ]
    for library in libraries_to_silence:
        logging.getLogger(library).setLevel(logging.WARNING)

    logging.info("Logging initialized.")
