"""
Configuration Management Module for Ozmoz.

This module defines the core configuration constants and the application state
container. It also handles the logging configuration, including custom formatters
and filters to ensure clean and useful logs.

Key Components:
- AppConfig: Immutable application constants
- AppState: Runtime state container (thread-safe where needed)
- Logging Infrastructure: Custom handlers, formatters, and security filters
"""

import collections
import logging
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Deque, Optional

# --- Third-Party Imports ---
import pyaudio
import webview

# --- Logger Setup ---
logger = logging.getLogger(__name__)

# --- Audio Configuration Constants ---

# PyAudio buffer size for real-time 16kHz mono capture
# 512 samples = 32ms latency (acceptable for voice, minimizes delay)
AUDIO_CHUNK_SIZE = 512

# Optimized chunk for batch processing (reduces I/O overhead)
# 2048 samples = 128ms windows for VAD and spectrum analysis
AUDIO_OPTIMIZED_CHUNK_SIZE = 2048

# Standard sample rate for speech recognition (Whisper, Deepgram)
AUDIO_SAMPLE_RATE_HZ = 16000

# Mono channel (speech doesn't benefit from stereo, reduces bandwidth)
AUDIO_CHANNEL_COUNT = 1

# 16-bit signed integer format (standard PCM, widely supported)
AUDIO_BIT_FORMAT = pyaudio.paInt16

# Temporary WAV file for recording session
AUDIO_TEMP_FILENAME = "temp_recording.wav"

# --- Voice Activity Detection (VAD) Constants ---

# VAD energy threshold (arbitrary units, tuned for typical room noise)
# Higher values = more aggressive filtering, may cut quiet speech
VAD_ENERGY_THRESHOLD = 300

# Silence duration before stopping recording (seconds)
# 0.8s balances natural speech pauses vs unwanted cutoffs
VAD_SILENCE_TIMEOUT_SECONDS = 0.8

# --- Visualizer Constants ---

# Number of points in the waveform display (more = smoother, slower)
VISUALIZER_DATA_POINTS = 150

# Maximum height in pixels for the visualizer bar
VISUALIZER_MAX_HEIGHT_PX = 150

# Amplitude scaling factor for visual normalization
# Lower = more sensitive to quiet sounds, higher = requires louder input
VISUALIZER_AMPLITUDE_SCALE = 80

# --- Conversation History Limits ---

# Maximum messages in conversation history (prevents memory leaks)
# 200 messages ≈ 100 turns, sufficient for long sessions while bounded
MAX_CONVERSATION_HISTORY_SIZE = 200

# --- Logging Buffer Capacity ---

# Maximum log records kept in UI buffer (developer mode)
LOG_BUFFER_CAPACITY = 1000

# Maximum log message length before truncation (prevents binary dumps)
MAX_LOG_MESSAGE_LENGTH = 1000

# Time window for duplicate log suppression (seconds)
DUPLICATE_LOG_WINDOW_SECONDS = 3

# Maximum unique messages tracked for duplicate detection
DUPLICATE_CACHE_SIZE = 50

# --- Security Patterns ---

# Regex patterns to detect and redact secrets in logs
SECRET_PATTERNS = [
    re.compile(
        r"api[_-]?key['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{20,})", re.IGNORECASE
    ),
    re.compile(r"token['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
    re.compile(r"password['\"]?\s*[:=]\s*['\"]?(.+?)['\"]?", re.IGNORECASE),
    re.compile(r"Bearer\s+([a-zA-Z0-9_\-\.]+)", re.IGNORECASE),
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),  # OpenAI-style keys
]


class AppConfig:
    """
    Global application configuration constants.

    This class contains immutable configuration values including:
    - Application metadata (version, identifiers)
    - External service endpoints
    - Audio/VAD settings
    - UI defaults
    - Hotkey bindings

    All attributes are class-level constants and should not be modified at runtime.
    For runtime state, use AppState instead.
    """

    # --- Application Metadata ---
    VERSION: str = "2.0.0"

    # Windows mutex ID for single-instance enforcement
    MUTEX_ID: str = "f7c9acc6-46a7-4712-89f5-171549439308-Ozmoz"

    # GitHub API endpoint for update checks
    GITHUB_RELEASES_URL: str = (
        "https://api.github.com/repos/zerep-thomas/ozmoz/releases/latest"
    )

    # --- Audio Configuration ---
    AUDIO_CHUNK: int = AUDIO_CHUNK_SIZE
    AUDIO_FORMAT: int = AUDIO_BIT_FORMAT
    AUDIO_CHANNELS: int = AUDIO_CHANNEL_COUNT
    AUDIO_RATE: int = AUDIO_SAMPLE_RATE_HZ
    AUDIO_OPTIMIZED_CHUNK: int = AUDIO_OPTIMIZED_CHUNK_SIZE
    AUDIO_OUTPUT_FILENAME: str = AUDIO_TEMP_FILENAME

    # --- Voice Activity Detection (VAD) Settings ---
    VAD_ENABLED: bool = True
    VAD_THRESHOLD: int = VAD_ENERGY_THRESHOLD
    VAD_SILENCE_TIMEOUT: float = VAD_SILENCE_TIMEOUT_SECONDS

    # --- Visualizer Settings ---
    VISUALIZER_POINTS: int = VISUALIZER_DATA_POINTS
    VISUALIZER_MAX_HEIGHT: int = VISUALIZER_MAX_HEIGHT_PX
    VISUALIZER_SCALING_FACTOR: int = VISUALIZER_AMPLITUDE_SCALE

    # --- Defaults ---
    DEFAULT_LANGUAGE: str = "en"
    DEFAULT_AI_MODEL: str = "llama-3.3-70b-versatile"
    DEFAULT_AUDIO_MODEL: str = "nova-2"

    DEFAULT_HOTKEYS: dict[str, str] = {
        "toggle_visibility": "ctrl+alt",
        "record_toggle": "ctrl+x",
        "ai_toggle": "ctrl+q",
        "web_search_toggle": "alt+w",
        "screen_vision_toggle": "alt+x",
    }


# --- State Dataclasses ---


@dataclass
class ThreadingState:
    """Thread synchronization primitives and executor references."""

    keyboard_lock: threading.Lock = field(default_factory=threading.Lock)
    settings_file_lock: threading.Lock = field(default_factory=threading.Lock)
    stop_app_event: threading.Event = field(default_factory=threading.Event)
    mutex_handle: Optional[int] = None
    transcription_executor: Optional[Any] = None


@dataclass
class UIState:
    """User interface component references and display state."""

    window: Optional[webview.Window] = None
    settings_window: Optional[webview.Window] = None
    settings_open: bool = False
    settings_html: Optional[str] = None
    index_html: Optional[str] = None
    chart_type: str = "line"
    dashboard_period: int = 7


@dataclass
class AudioState:
    """Audio system state and recording configuration."""

    pyaudio_instance: Optional[pyaudio.PyAudio] = None
    audio_stream: Optional[pyaudio.Stream] = None
    original_volume: float = 1.0
    is_muted: bool = False
    was_muted_during_recording: bool = False
    sound_enabled: bool = True
    mute_sound: bool = True
    is_recording: bool = False
    current_recording_path: Optional[str] = None
    recording_start_time: float = 0.0


@dataclass
class ModelState:
    """AI model configuration and capability lists."""

    language: str = AppConfig.DEFAULT_LANGUAGE
    model: str = AppConfig.DEFAULT_AI_MODEL
    last_selected_model: str = AppConfig.DEFAULT_AI_MODEL
    audio_model: str = AppConfig.DEFAULT_AUDIO_MODEL

    # Capability Lists (Populated from remote config)
    advanced_model_list: list[str] = field(default_factory=list)
    tool_model_list: list[str] = field(default_factory=list)
    web_search_model_list: list[str] = field(default_factory=list)
    screen_vision_model_list: list[str] = field(default_factory=list)

    cached_models: Optional[list[str]] = None


@dataclass
class ConversationState:
    """Conversation history and context management."""

    # Bounded deque prevents memory leaks from infinite conversation growth
    conversation_history: Deque[dict[str, Any]] = field(
        default_factory=lambda: collections.deque(maxlen=MAX_CONVERSATION_HISTORY_SIZE)
    )
    transcribed_text_for_ai: str = ""
    original_clipboard: str = ""
    is_ai_response_visible: bool = False


class AppState:
    """
    Global state container for the application.

    Holds runtime data organized into logical subsystems:
    - threading: Locks, events, executors
    - ui: Window references, display state
    - audio: Recording state, PyAudio instances
    - models: AI model configuration
    - conversation: Chat history and context

    Thread Safety:
    - Individual locks provided in ThreadingState
    - Conversation history uses thread-safe deque with maxlen
    - Other attributes should be accessed from main thread or protected externally

    Example:
        >>> state = AppState()
        >>> state.audio.is_recording = True
        >>> state.conversation.conversation_history.append({"role": "user", "content": "Hi"})
    """

    def __init__(self) -> None:
        """Initialize the application state with default values."""

        # --- Organized State Subsystems ---
        self.threading = ThreadingState()
        self.ui = UIState()
        self.audio = AudioState()
        self.models = ModelState()
        self.conversation = ConversationState()

        # --- Global Application State ---
        self.is_busy: bool = False
        self.is_exiting: bool = False
        self.ai_recording: bool = False
        self.developer_mode: bool = False

        # --- Configuration & Cache ---
        self.log_handler: Optional[logging.Handler] = None
        self.cached_remote_config: Optional[list[Any]] = None
        self.settings: dict[str, Any] = {}
        self.hotkeys: dict[str, str] = AppConfig.DEFAULT_HOTKEYS.copy()

        # --- Update Information ---
        self.remote_version: Optional[str] = None
        self.remote_update_url: Optional[str] = None

        # --- API Clients (Lazy Loaded) ---
        # NOTE: These should be initialized via setter methods that validate credentials
        self.groq_client: Optional[Any] = None
        self.deepgram_client: Optional[Any] = None
        self.cerebras_client: Optional[Any] = None

    def clear_conversation_history(self) -> None:
        """
        Clears the conversation history.

        Useful for starting fresh conversations or freeing memory.
        """
        self.conversation.conversation_history.clear()
        logger.debug("Conversation history cleared")

    def reset_audio_state(self) -> None:
        """
        Resets audio recording state to defaults.

        Should be called after recording completion or errors.
        """
        self.audio.is_recording = False
        self.audio.current_recording_path = None
        self.audio.recording_start_time = 0.0
        logger.debug("Audio state reset")


# Global Singleton Instance
app_state = AppState()


# --- Logging Infrastructure ---


class BufferingLogHandler(logging.Handler):
    """
    Thread-safe logging handler that stores recent log records in a bounded buffer.

    Used for displaying logs in the UI (Developer Mode) without memory leaks.
    The buffer automatically discards oldest entries when full.

    Thread Safety:
        Uses threading.Lock to protect concurrent access to the deque.

    Attributes:
        buffer: Deque containing formatted log records with level and message.
    """

    def __init__(self, capacity: int = LOG_BUFFER_CAPACITY) -> None:
        """
        Initialize the buffering handler.

        Args:
            capacity: Maximum number of log records to keep in memory.
        """
        super().__init__()
        self.buffer: Deque[dict[str, str]] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """
        Stores the formatted log record in the buffer (thread-safe).

        Args:
            record: The log record to store.
        """
        try:
            with self._lock:
                self.buffer.append(
                    {"level": record.levelname, "message": self.format(record)}
                )
        except Exception:
            self.handleError(record)


class ColoredFormatter(logging.Formatter):
    """
    Custom formatter that adds ANSI color codes to console logs based on severity.

    Colors:
    - DEBUG: Green
    - INFO: Blue
    - WARNING: Yellow
    - ERROR: Red
    - CRITICAL: Red background

    Note: Colors may not display correctly on all terminals (e.g., Windows cmd.exe).
    """

    RESET_CODE: str = "\033[0m"
    COLOR_MAP: dict[str, str] = {
        "DEBUG": "\033[92m",  # Green
        "INFO": "\033[94m",  # Blue
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[41m",  # Red Background
    }

    def format(self, record: logging.LogRecord) -> str:
        """
        Formats the log record with appropriate color codes.

        Args:
            record: The log record to format.

        Returns:
            Formatted string with ANSI color codes.
        """
        color = self.COLOR_MAP.get(record.levelname, self.RESET_CODE)
        return f"{color}{super().format(record)}{self.RESET_CODE}"


class BinaryDataFilter(logging.Filter):
    """
    Filters out log messages containing binary data or excessive length.

    This prevents logs from being polluted with base64 data, binary dumps,
    or extremely long messages that make logs unreadable.

    Filtering Criteria:
    - Messages containing null bytes (\\x00) or 0xFF bytes
    - Messages exceeding MAX_LOG_MESSAGE_LENGTH characters
    """

    BINARY_PATTERNS: tuple[str, ...] = ("\\x00", "\\xff")

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Determines if a log record should be logged.

        Args:
            record: The log record to evaluate.

        Returns:
            True if the record should be logged, False to suppress it.
        """
        try:
            message = str(record.getMessage())

            # Check for binary data patterns
            if any(pattern in message for pattern in self.BINARY_PATTERNS):
                return False

            # Check message length
            return len(message) <= MAX_LOG_MESSAGE_LENGTH

        except Exception:
            # If we can't evaluate the message, let it through (fail-open)
            return True


class SecretsFilter(logging.Filter):
    """
    Redacts sensitive information (API keys, tokens, passwords) from log messages.

    Security Rationale:
    - Prevents credential leakage in log files
    - Protects against accidental exposure via log aggregation services
    - Complies with security best practices (OWASP, PCI-DSS)

    Redaction Strategy:
    - Replaces matched secrets with '***REDACTED***'
    - Preserves log structure and readability
    - Uses regex patterns defined in SECRET_PATTERNS constant
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Redacts secrets from the log record message.

        Args:
            record: The log record to sanitize.

        Returns:
            Always True (record is modified in-place, not suppressed).
        """
        try:
            message = str(record.getMessage())
            sanitized_message = message

            # Apply all secret patterns
            for pattern in SECRET_PATTERNS:
                sanitized_message = pattern.sub(
                    lambda m: m.group(0).replace(m.group(1), "***REDACTED***"),
                    sanitized_message,
                )

            # Update the record's message if redaction occurred
            if sanitized_message != message:
                record.msg = sanitized_message
                record.args = ()  # Clear args to prevent re-formatting

        except Exception as error:
            # Log the filter error without exposing the original message
            logger.warning(
                "SecretsFilter encountered an error",
                extra={"error": str(error)},
            )

        return True


class DuplicateFilter(logging.Filter):
    """
    Suppresses identical log messages that occur within a short time window.

    This reduces log spam from repetitive operations (e.g., polling loops, retries).

    Algorithm:
    - Maintains a cache of (timestamp, message) tuples
    - Blocks messages that match a cached entry within time_window
    - Automatically evicts old entries via bounded deque

    Thread Safety:
        Uses threading.Lock to protect the cache during concurrent logging.
    """

    def __init__(
        self,
        time_window_seconds: int = DUPLICATE_LOG_WINDOW_SECONDS,
        max_cache_size: int = DUPLICATE_CACHE_SIZE,
    ) -> None:
        """
        Initialize the duplicate filter.

        Args:
            time_window_seconds: Time duration (seconds) to suppress duplicates.
            max_cache_size: Maximum number of unique messages to track.
        """
        super().__init__()
        self.time_window = timedelta(seconds=time_window_seconds)
        self.log_cache: Deque[tuple[datetime, str]] = collections.deque(
            maxlen=max_cache_size
        )
        self._lock = threading.Lock()

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Determines if a log record is a duplicate within the time window.

        Args:
            record: The log record to evaluate.

        Returns:
            False if the message is a duplicate (suppress it), True otherwise.
        """
        with self._lock:
            current_time = datetime.now()
            message = record.getMessage()

            # Check if message exists in cache within time window
            for timestamp, cached_message in self.log_cache:
                if (
                    message == cached_message
                    and (current_time - timestamp) < self.time_window
                ):
                    return False  # Suppress duplicate

            # Add new message to cache
            self.log_cache.append((current_time, message))
            return True  # Allow message


def setup_logging() -> None:
    """
    Configures the root logger with console and buffer handlers.

    Setup includes:
    1. Console handler with colored output
    2. Buffer handler for UI display (developer mode)
    3. Security filters (secrets redaction, binary data filtering)
    4. Duplicate message suppression
    5. Silencing of noisy third-party libraries

    This function should be called once at application startup.

    Raises:
        RuntimeError: If logging setup fails (critical error).
    """
    try:
        # --- Formatters ---
        console_formatter = ColoredFormatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        buffer_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )

        # --- Console Handler ---
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.DEBUG)

        # Apply security and quality filters
        console_handler.addFilter(SecretsFilter())
        console_handler.addFilter(BinaryDataFilter())
        console_handler.addFilter(
            DuplicateFilter(time_window_seconds=DUPLICATE_LOG_WINDOW_SECONDS)
        )

        # --- Buffer Handler (For UI Logs) ---
        app_state.log_handler = BufferingLogHandler()
        app_state.log_handler.setFormatter(buffer_formatter)
        app_state.log_handler.setLevel(logging.DEBUG)

        # Apply same filters to UI logs
        app_state.log_handler.addFilter(SecretsFilter())
        app_state.log_handler.addFilter(BinaryDataFilter())
        app_state.log_handler.addFilter(
            DuplicateFilter(time_window_seconds=DUPLICATE_LOG_WINDOW_SECONDS)
        )

        # --- Root Logger Setup ---
        root_logger = logging.getLogger()

        # Clear any existing handlers (prevent duplicates on reload)
        if root_logger.hasHandlers():
            root_logger.handlers.clear()

        root_logger.addHandler(console_handler)
        root_logger.addHandler(app_state.log_handler)
        root_logger.setLevel(logging.DEBUG)

        # --- Silence Noisy Libraries ---
        # These libraries produce excessive debug logs that pollute output
        libraries_to_silence: list[str] = [
            "httpx",  # HTTP client (verbose connection logs)
            "httpcore",  # Low-level HTTP (byte-level logs)
            "requests",  # HTTP library (retry spam)
            "urllib3",  # Connection pool warnings
            "pyaudio",  # Audio buffer warnings
            "groq",  # API client debug logs
            "deepgram",  # WebSocket connection logs
            "openai",  # API client verbose logs
            "comtypes",  # COM interface warnings (Windows)
            "pycaw",  # Audio control library (Windows)
        ]

        for library in libraries_to_silence:
            logging.getLogger(library).setLevel(logging.WARNING)

        logger.info("Logging system initialized successfully")

    except Exception as error:
        # If logging setup fails, we have a critical problem
        print(f"CRITICAL: Logging setup failed: {error}", file=sys.stderr)
        raise RuntimeError("Failed to initialize logging system") from error
