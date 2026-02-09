"""
Audio Management Module for Ozmoz.

This module handles:
- Audio Recording: Capturing microphone input via PyAudio.
- Transcription Services: Orchestrating API calls to Groq/Deepgram and local Whisper inference.
- Audio Preprocessing: Volume normalization and format conversion.
- Text Post-processing: Converting numbers (text to digits) and applying user replacements.
"""

import io
import json
import logging
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable, Final, Protocol, TypeAlias

# --- Third-Party Imports ---
import numpy as np
import pyaudio
import win32con
import win32gui
from deepgram import DeepgramClient, FileSource, PrerecordedOptions
from groq import Groq
from text_to_num.transforms import alpha2digit

# --- Local Imports ---
from modules.config import AppConfig, AppState
from modules.data import (
    CredentialManager,
    HistoryManager,
    ReplacementManager,
    StatsManager,
)
from modules.local_audio import local_whisper
from modules.utils import SoundManager, SuppressStderr

# --- Type Aliases ---
AudioBuffer: TypeAlias = io.BytesIO | str
SimpleCallback: TypeAlias = Callable[[], None]

# --- Constants ---
# French number words pattern for text-to-digit conversion
WORDS_FR: Final[str] = (
    "et|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|"
    "treize|quatorze|quinze|seize|vingt|trente|quarante|cinquante|soixante|"
    "cent|cents|mille|milles"
)
PATTERN_FR: Final[re.Pattern[str]] = re.compile(
    rf"\b((?:{WORDS_FR})(?:-(?:{WORDS_FR}))+)\b", flags=re.IGNORECASE
)

# English number words pattern for text-to-digit conversion
WORDS_EN: Final[str] = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    "fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|"
    "fifty|sixty|seventy|eighty|ninety|hundred|thousand|million"
)
PATTERN_EN: Final[re.Pattern[str]] = re.compile(
    rf"\b((?:{WORDS_EN})(?:-(?:{WORDS_EN}))+)\b", flags=re.IGNORECASE
)

# Audio file naming pattern
RECORDING_FILENAME_PREFIX: Final[str] = "ozmoz_rec"
RECORDING_FILENAME_EXTENSION: Final[str] = ".wav"

# Timing constants
# Brief delay before muting system to allow beep sound to play
PRE_MUTE_DELAY_SECONDS: Final[float] = 0.15
# Delay to allow OS window manager to process SetForegroundWindow
WINDOW_FOCUS_DELAY_SECONDS: Final[float] = 0.1
# Maximum time to wait for audio file to be written to disk
AUDIO_FILE_WRITE_TIMEOUT_SECONDS: Final[float] = 2.0
# Polling interval when checking for file existence
FILE_CHECK_INTERVAL_SECONDS: Final[float] = 0.05

# Deepgram API timeout configuration (connection, read)
DEEPGRAM_TIMEOUT_SECONDS: Final[tuple[int, int]] = (15, 45)

# Minimum valid audio file size in bytes (below this is considered invalid)
MIN_VALID_AUDIO_FILE_SIZE_BYTES: Final[int] = 1024

# Subprocess creation flags for Windows (CREATE_NO_WINDOW)
WINDOWS_CREATE_NO_WINDOW_FLAG: Final[int] = 0x08000000


# --- Protocols for Dependency Injection ---
class OSInterfaceProtocol(Protocol):
    """Protocol for operating system interactions."""

    def mute_system_volume(self) -> float:
        """Mute system audio and return previous volume level."""
        ...

    def unmute_system_volume(self, original_level: float) -> None:
        """Restore system audio to specified volume level."""
        ...


class ClipboardManagerProtocol(Protocol):
    """Protocol for clipboard and paste operations."""

    def paste_and_clear(self, text: str) -> None:
        """Paste text to active window and clear clipboard."""
        ...


class EventBusProtocol(Protocol):
    """Protocol for event publishing."""

    def publish(self, event_type: str, data: object) -> None:
        """Publish event to all subscribers."""
        ...


class WindowProtocol(Protocol):
    """Protocol for webview window operations."""

    def evaluate_js(self, script: str) -> object:
        """Execute JavaScript in the webview."""
        ...

    def show(self) -> None:
        """Show the window."""
        ...


# --- Custom Exceptions ---
class AudioInitializationError(Exception):
    """Raised when PyAudio initialization fails."""


class TranscriptionError(Exception):
    """Raised when audio transcription fails."""


class AudioFileError(Exception):
    """Raised when audio file operations fail."""


# --- Patch subprocess for Windows (Hide Console Window) ---
if sys.platform == "win32":
    """
    Patch subprocess.Popen to automatically hide console windows on Windows.

    This prevents CMD windows from flashing when spawning subprocesses
    (e.g., ffmpeg for audio processing). Applied globally to maintain
    backward compatibility with existing code.

    Note: This modifies global behavior - consider refactoring to a
    context manager for more localized control.
    """
    _original_popen = subprocess.Popen

    class _PatchedPopen(_original_popen):  # type: ignore[misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if "startupinfo" not in kwargs:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                kwargs["startupinfo"] = startupinfo

            if "creationflags" not in kwargs:
                kwargs["creationflags"] = WINDOWS_CREATE_NO_WINDOW_FLAG

            super().__init__(*args, **kwargs)  # type: ignore

    subprocess.Popen = _PatchedPopen  # type: ignore[misc]


class SafeJSExecutor:
    """
    Wrapper for safe JavaScript execution in webview windows.

    Prevents injection attacks by properly escaping all arguments
    passed to JavaScript functions.
    """

    @staticmethod
    def call_function(window: WindowProtocol, func_name: str, *args: object) -> None:
        """
        Execute a JavaScript function with sanitized arguments.

        Args:
            window: The webview window instance.
            func_name: Name of the JavaScript function to call.
            *args: Arguments to pass (will be JSON-encoded).

        Raises:
            ValueError: If function name contains invalid characters.

        Example:
            >>> SafeJSExecutor.call_function(window, "showError", "Hello")
            # Executes: showError("Hello")
        """
        # Validate function name (alphanumeric + underscore only)
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", func_name):
            raise ValueError(f"Invalid JavaScript function name: {func_name}")

        # JSON-encode all arguments to prevent injection
        encoded_args = ",".join(json.dumps(arg) for arg in args)
        script = f"{func_name}({encoded_args})"

        try:
            window.evaluate_js(script)
        except Exception as error:
            logging.error(
                "JavaScript execution failed",
                extra={
                    "function": func_name,
                    "error": str(error),
                },
            )

    @staticmethod
    def dispatch_event(window: WindowProtocol, event_type: str, detail: str) -> None:
        """
        Dispatch a custom DOM event safely.

        Args:
            window: The webview window instance.
            event_type: Type of the custom event (e.g., 'pywebview').
            detail: Event detail string.
        """
        # Encode detail safely
        safe_detail = json.dumps(detail)
        script = f"window.dispatchEvent(new CustomEvent({json.dumps(event_type)}, {{ detail: {safe_detail} }}))"

        try:
            window.evaluate_js(script)
        except Exception as error:
            logging.error(
                "Event dispatch failed",
                extra={
                    "event_type": event_type,
                    "error": str(error),
                },
            )


class AudioManager:
    """
    Manage audio input, recording streams, and system volume control.

    Handles PyAudio lifecycle, microphone capture, and real-time
    audio visualization during recording sessions.

    Thread Safety:
        Recording operations run in background threads to prevent
        blocking the main application loop.
    """

    def __init__(
        self,
        app_state: AppState,
        sound_manager: SoundManager,
        os_interface: OSInterfaceProtocol,
    ) -> None:
        """
        Initialize the AudioManager.

        Args:
            app_state: Global application state.
            sound_manager: Sound effect player.
            os_interface: OS-level audio control interface.
        """
        self.app_state = app_state
        self.sound_manager = sound_manager
        self.os_interface = os_interface
        self._pyaudio_instance: pyaudio.PyAudio | None = None
        self._audio_stream: pyaudio.Stream | None = None
        self._original_volume: float = 1.0
        self._is_system_muted_by_app: bool = False
        self._silence_callback: SimpleCallback | None = None
        self._logger = logging.getLogger(__name__)

    def warmup(self) -> None:
        """
        Pre-initialize audio subsystem if needed.

        Currently a placeholder for potential hardware warmup routines
        (e.g., opening/closing a test stream to wake up drivers).
        """
        pass

    def initialize(self) -> bool:
        """
        Initialize the PyAudio instance.

        Returns:
            True if initialization succeeded, False otherwise.

        Raises:
            AudioInitializationError: If PyAudio setup fails critically.
        """
        if self._pyaudio_instance:
            return True

        self._logger.info("Initializing PyAudio")
        try:
            with SuppressStderr():
                self._pyaudio_instance = pyaudio.PyAudio()
            self.app_state.audio.pyaudio_instance = self._pyaudio_instance
            self._logger.info("PyAudio initialized successfully")
            return True

        except Exception as error:
            self._logger.critical(
                "PyAudio initialization failed",
                extra={"error": str(error)},
                exc_info=True,
            )
            raise AudioInitializationError(
                f"Failed to initialize audio subsystem: {error}"
            ) from error

    def terminate(self) -> None:
        """
        Close audio streams and terminate the PyAudio instance.

        Ensures proper cleanup of system audio resources to prevent
        driver locks or orphaned streams.
        """
        self._logger.info("Terminating audio subsystem")

        if self._audio_stream:
            try:
                if self._audio_stream.is_active():
                    self._audio_stream.stop_stream()
                self._audio_stream.close()
                self._logger.debug("Audio stream closed")
            except Exception as error:
                self._logger.warning(
                    "Error closing audio stream", extra={"error": str(error)}
                )
            finally:
                self._audio_stream = None

        if self._pyaudio_instance:
            try:
                self._pyaudio_instance.terminate()
                self._logger.debug("PyAudio instance terminated")
            except Exception as error:
                self._logger.warning(
                    "Error terminating PyAudio", extra={"error": str(error)}
                )
            finally:
                self._pyaudio_instance = None

    def start_recording(
        self, on_silence_callback: SimpleCallback | None = None
    ) -> None:
        """
        Start the audio recording process with immediate UI feedback.

        Args:
            on_silence_callback: Optional callback to execute when silence is detected.

        Note:
            This method returns immediately - actual recording happens in a background thread.
        """

        def update_ui_in_background() -> None:
            """Update UI elements to reflect recording state."""
            if self.app_state.ui.window:
                try:
                    SafeJSExecutor.call_function(
                        self.app_state.ui.window, "setSettingsButtonState", True
                    )
                    # CORRECTION ICI - Utiliser evaluate_js directement pour les événements personnalisés
                    safe_detail = json.dumps("start_recording")
                    self.app_state.ui.window.evaluate_js(
                        f"window.dispatchEvent(new CustomEvent('pywebview', {{ detail: {safe_detail} }}))"
                    )
                except Exception as error:
                    self._logger.warning(
                        "UI update failed", extra={"error": str(error)}
                    )

        threading.Thread(target=update_ui_in_background, daemon=True).start()

        # Play start beep if sounds enabled
        if self.app_state.audio.sound_enabled:
            self.sound_manager.play("beep_on")

        # Store mute state and apply if configured
        self.app_state.audio.was_muted_during_recording = (
            self.app_state.audio.mute_sound
        )
        if self.app_state.audio.mute_sound:
            threading.Thread(target=self._delayed_mute, daemon=True).start()

        # Ensure PyAudio is initialized
        if not self.app_state.audio.pyaudio_instance:
            try:
                if not self.initialize():
                    return
            except AudioInitializationError:
                return

        # Update state flags
        self.app_state.is_busy = True
        self.app_state.audio.is_recording = True
        self.app_state.audio.recording_start_time = time.time()
        self._silence_callback = on_silence_callback

        # Generate secure temporary file path
        temp_path = self._generate_temp_audio_path()
        self.app_state.audio.current_recording_path = str(temp_path)

        # Start recording worker thread
        threading.Thread(
            target=self._record_audio_worker,
            args=(str(temp_path),),
            daemon=True,
            name="AudioRecorder",
        ).start()

    def stop_recording(self) -> None:
        """
        Stop the recording and restore system volume.

        Sets the recording flag to False, which signals the worker
        thread to stop capturing and finalize the audio file.
        """
        if self.app_state.audio.is_recording:
            self.app_state.audio.is_recording = False
            self.unmute_system_volume()
            self._logger.info("Recording stopped")

    def _generate_temp_audio_path(self) -> Path:
        """
        Generate a secure temporary file path for audio recording.

        Returns:
            Secure Path object within the system temp directory.

        Raises:
            ValueError: If path resolution escapes temp directory.
        """
        import uuid

        temp_dir = Path(tempfile.gettempdir()).resolve()
        unique_name = f"{RECORDING_FILENAME_PREFIX}_{uuid.uuid4().hex}{RECORDING_FILENAME_EXTENSION}"
        temp_path = (temp_dir / unique_name).resolve()

        # Validate that path stays within temp directory (prevent path traversal)
        if not temp_path.is_relative_to(temp_dir):
            raise ValueError(
                "Generated path escapes temp directory (security violation)"
            )

        return temp_path

    def _delayed_mute(self) -> None:
        """
        Mute system audio after a brief delay.

        The delay allows the start-recording beep sound to play
        before system volume is muted.
        """
        time.sleep(PRE_MUTE_DELAY_SECONDS)
        self.mute_system_volume()

    def _record_audio_worker(self, filename: str) -> None:
        """
        Background worker that captures audio frames from microphone.

        Args:
            filename: Path where the WAV file will be saved.

        Note:
            This runs in a daemon thread and terminates when
            app_state.audio.is_recording becomes False.
        """
        frames: list[bytes] = []
        stream: pyaudio.Stream | None = None

        if self._pyaudio_instance is None:
            self._logger.error("PyAudio not initialized - cannot start recording")
            self.app_state.audio.is_recording = False
            return

        # Open audio stream
        try:
            stream = self._pyaudio_instance.open(
                format=AppConfig.AUDIO_FORMAT,
                channels=AppConfig.AUDIO_CHANNELS,
                rate=AppConfig.AUDIO_RATE,
                input=True,
                frames_per_buffer=AppConfig.AUDIO_CHUNK,
            )
            self._audio_stream = stream
            self._logger.info("Audio stream opened successfully")

        except OSError as error:
            self._logger.error(
                "Failed to open audio stream",
                extra={"error": str(error)},
                exc_info=True,
            )
            self.app_state.audio.is_recording = False
            return

        viz_enabled = True
        window = self.app_state.ui.window

        # Recording loop
        try:
            while self.app_state.audio.is_recording:
                try:
                    data = stream.read(
                        AppConfig.AUDIO_CHUNK, exception_on_overflow=False
                    )
                    frames.append(data)

                    # Update real-time visualizer UI
                    if viz_enabled and window:
                        try:
                            self._update_visualizer(window, data)
                        except Exception as error:
                            self._logger.warning(
                                "Visualizer update failed - disabling",
                                extra={"error": str(error)},
                            )
                            viz_enabled = False

                except OSError as error:
                    self._logger.warning(
                        "Audio stream read error",
                        extra={"error": str(error)},
                    )
                    break

        finally:
            # Cleanup stream
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                    self._logger.debug("Audio stream cleaned up")
                except Exception as error:
                    self._logger.warning(
                        "Error during stream cleanup", extra={"error": str(error)}
                    )
                finally:
                    self._audio_stream = None

            # Write frames to WAV file
            if frames:
                self._write_wav_file(filename, frames)
            else:
                self._logger.warning("No audio frames captured")

    def _update_visualizer(self, window: WindowProtocol, audio_data: bytes) -> None:
        """
        Update the UI visualizer with current audio levels.

        Args:
            window: The webview window instance.
            audio_data: Raw audio bytes from the stream.

        Raises:
            ValueError: If audio data cannot be processed.
        """
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        samples_per_point = len(audio_array) // AppConfig.VISUALIZER_POINTS

        if samples_per_point <= 0:
            return

        # Reshape and compute max amplitude per visualization point
        truncated_length = samples_per_point * AppConfig.VISUALIZER_POINTS
        reshaped = audio_array[:truncated_length].reshape(
            AppConfig.VISUALIZER_POINTS, -1
        )

        visualizer_data = (
            np.max(np.abs(reshaped), axis=1) / AppConfig.VISUALIZER_SCALING_FACTOR
        ).astype(int)

        # Clamp values to max height
        np.clip(
            visualizer_data,
            0,
            AppConfig.VISUALIZER_MAX_HEIGHT,
            out=visualizer_data,
        )

        # Send to UI via safe JS execution
        SafeJSExecutor.call_function(
            window, "updateVisualizer", visualizer_data.tolist()
        )

    def _write_wav_file(self, filename: str, frames: list[bytes]) -> None:
        """
        Write captured audio frames to a WAV file.

        Args:
            filename: Path where the WAV file will be saved.
            frames: List of raw audio frame bytes.

        Raises:
            AudioFileError: If file writing fails.
        """
        if self._pyaudio_instance is None:
            raise AudioFileError("PyAudio instance not available")

        try:
            with wave.open(filename, "wb") as wave_file:
                wave_file.setnchannels(AppConfig.AUDIO_CHANNELS)
                wave_file.setsampwidth(
                    self._pyaudio_instance.get_sample_size(AppConfig.AUDIO_FORMAT)
                )
                wave_file.setframerate(AppConfig.AUDIO_RATE)
                wave_file.writeframes(b"".join(frames))

            self._logger.info("Audio file written", extra={"path": filename})

        except OSError as error:
            self._logger.critical(
                "WAV file write failed",
                extra={"path": filename, "error": str(error)},
                exc_info=True,
            )
            raise AudioFileError(f"Failed to write audio file: {error}") from error

    def mute_system_volume(self) -> None:
        """
        Mute the system volume using the OS interface.

        Stores the original volume level for later restoration.
        Implements idempotency - calling multiple times has no effect.
        """
        if not self.app_state.audio.mute_sound or self._is_system_muted_by_app:
            return

        try:
            self._original_volume = self.os_interface.mute_system_volume()
            self._is_system_muted_by_app = True
            self._logger.debug("System audio muted")

        except Exception as error:
            self._logger.error(
                "Failed to mute system volume", extra={"error": str(error)}
            )
            self._is_system_muted_by_app = False

    def unmute_system_volume(self) -> None:
        """
        Restore the system volume to its original level.

        Only executes if this instance previously muted the system.
        Implements idempotency - safe to call multiple times.
        """
        if not self._is_system_muted_by_app:
            return

        try:
            self.os_interface.unmute_system_volume(self._original_volume)
            self._logger.debug("System audio restored")

        except Exception as error:
            self._logger.error(
                "Failed to restore system volume", extra={"error": str(error)}
            )
        finally:
            self._is_system_muted_by_app = False


class TranscriptionService:
    """
    Service responsible for converting audio files to text.

    Supports multiple backends:
    - Local Whisper (CPU/GPU inference)
    - Groq Whisper API
    - Deepgram Nova API

    Handles text post-processing including number conversion and
    user-defined text replacements.
    """

    # Languages supporting automatic number conversion
    _SUPPORTED_NUMBER_CONVERSION_LANGUAGES: Final[frozenset[str]] = frozenset(
        {"fr", "en", "es", "pt", "de", "ru"}
    )

    def __init__(
        self,
        app_state: AppState,
        replacement_manager: ReplacementManager,
        credential_manager: CredentialManager,
    ) -> None:
        """
        Initialize the TranscriptionService.

        Args:
            app_state: Global application state.
            replacement_manager: Text replacement configuration.
            credential_manager: API credentials storage.
        """
        self.app_state = app_state
        self.replacement_manager = replacement_manager
        self.credential_manager = credential_manager
        self._logger = logging.getLogger(__name__)

    def warmup(self) -> None:
        """
        Pre-initialize API clients and models in background.

        Speeds up first transcription by loading dependencies
        (Groq client, Deepgram client, local Whisper model) ahead of time.
        """

        def _warmup_worker() -> None:
            try:
                # Pre-load text_to_num for faster first conversion
                alpha2digit("vingt-deux", lang="fr")

                # Initialize Groq client if API key available
                groq_key = self.credential_manager.get_api_key(
                    "groq_audio"
                ) or self.credential_manager.get_api_key("ai")
                if groq_key and self.app_state.groq_client is None:
                    self.app_state.groq_client = Groq(api_key=groq_key)
                    self._logger.debug("Groq client initialized")

                # Initialize Deepgram client if API key available
                dg_key = self.credential_manager.get_api_key("deepgram")
                if dg_key and self.app_state.deepgram_client is None:
                    self.app_state.deepgram_client = DeepgramClient(dg_key)
                    self._logger.debug("Deepgram client initialized")

                # Pre-load local Whisper model if configured
                if self.app_state.models.audio_model.startswith("local"):
                    if local_whisper.is_installed():
                        local_whisper.load()
                        self._logger.debug("Local Whisper model loaded")

            except Exception as error:
                self._logger.warning(
                    "Warmup encountered error (non-critical)",
                    extra={"error": str(error)},
                )

        threading.Thread(
            target=_warmup_worker, daemon=True, name="WarmupWorker"
        ).start()

    def apply_replacements(self, text: str) -> str:
        """
        Apply user-defined text replacements.

        Args:
            text: Input text to process.

        Returns:
            Text with all configured replacements applied.

        Example:
            >>> # User configured: "ozmoz" -> "Ozmoz"
            >>> service.apply_replacements("I use ozmoz daily")
            'I use Ozmoz daily'
        """
        if not text:
            return ""

        try:
            replacements = self.replacement_manager.load()
            for item in replacements:
                word1 = item.get("word1")
                word2 = item.get("word2")
                if word1 and word2:
                    text = text.replace(word1, word2)
            return text

        except Exception as error:
            self._logger.warning(
                "Replacement application failed",
                extra={"error": str(error)},
            )
            return text

    def convert_numbers(self, transcript: str, language: str) -> str:
        """
        Convert written numbers to digits using text_to_num.

        Args:
            transcript: Input text with written numbers.
            language: Language code (fr, en, etc.).

        Returns:
            Text with numbers converted to digits.

        Example:
            >>> service.convert_numbers("vingt-deux euros", "fr")
            '22 euros'
        """
        if not transcript:
            return ""

        try:
            # Pre-process hyphenated numbers by replacing hyphens with spaces
            # This is required by alpha2digit library
            if language == "fr":
                transcript = PATTERN_FR.sub(
                    lambda m: m.group(0).replace("-", " "), transcript
                )
            elif language == "en":
                transcript = PATTERN_EN.sub(
                    lambda m: m.group(0).replace("-", " "), transcript
                )

            return alpha2digit(transcript, lang=language)

        except Exception as error:
            self._logger.warning(
                "Number conversion failed",
                extra={"language": language, "error": str(error)},
            )
            return transcript

    def _optimize_audio_in_memory(self, original_path: str) -> AudioBuffer:
        """
        Load audio file into memory buffer for API transmission.

        Args:
            original_path: Path to the audio file on disk.

        Returns:
            BytesIO buffer with file contents, or original path on failure.

        Note:
            Falls back to path-based approach if memory loading fails.
        """
        try:
            file_path = Path(original_path).resolve()

            # Validate file exists and is readable
            if not file_path.exists():
                raise FileNotFoundError(f"Audio file not found: {file_path}")

            if not file_path.is_file():
                raise ValueError(f"Path is not a file: {file_path}")

            # Read file into memory buffer
            buffer = io.BytesIO(file_path.read_bytes())
            buffer.name = "audio.wav"
            return buffer

        except Exception as error:
            self._logger.warning(
                "Audio optimization failed - using file path",
                extra={"path": original_path, "error": str(error)},
            )
            return original_path

    def _transcribe_ai(self, filename: str, lang: str) -> str:
        """
        Transcribe audio using Groq Whisper API.

        Args:
            filename: Path to the audio file.
            lang: Language code (or "autodetect").

        Returns:
            Transcribed text or error message.

        Raises:
            TranscriptionError: If API call fails.
        """
        try:
            # Initialize Groq client if needed
            if self.app_state.groq_client is None:
                api_key = self.credential_manager.get_api_key(
                    "groq_audio"
                ) or self.credential_manager.get_api_key("ai")
                if not api_key:
                    return "Error: Missing Groq API key. Check Settings."
                self.app_state.groq_client = Groq(api_key=api_key)

            client = self.app_state.groq_client
            file_obj = self._optimize_audio_in_memory(filename)

            # Build API request parameters
            params: dict[str, object] = {"model": self.app_state.models.audio_model}
            if lang and lang != "autodetect":
                params["language"] = lang

            # Prepare file payload
            if isinstance(file_obj, str):
                # File path approach
                file_path = Path(file_obj).resolve()
                params["file"] = (file_path.name, file_path.read_bytes())
            else:
                # BytesIO buffer approach
                params["file"] = (file_obj.name, file_obj.read())

            # Execute transcription
            transcription = client.audio.transcriptions.create(**params)  # type: ignore[arg-type]
            result = transcription.text or ""

            if not result:
                return "Error: Empty transcription result."

            return result

        except Exception as error:
            self._logger.error(
                "Groq Whisper transcription failed",
                extra={"error": str(error)},
                exc_info=True,
            )
            raise TranscriptionError(f"Groq API error: {error}") from error

    def _transcribe_deepgram(self, filename: str, lang: str) -> str:
        """
        Transcribe audio using Deepgram Nova API.

        Args:
            filename: Path to the audio file.
            lang: Language code.

        Returns:
            Transcribed text or error message.

        Raises:
            TranscriptionError: If API call fails.
        """
        try:
            # Initialize Deepgram client if needed
            if self.app_state.deepgram_client is None:
                api_key = self.credential_manager.get_api_key("deepgram")
                if not api_key:
                    return "Error: Deepgram API key missing. Check Settings."
                self.app_state.deepgram_client = DeepgramClient(api_key)

            client = self.app_state.deepgram_client
            file_obj = self._optimize_audio_in_memory(filename)

            # Prepare file payload
            payload: FileSource
            if isinstance(file_obj, str):
                file_path = Path(file_obj).resolve()
                payload = {"buffer": file_path.read_bytes()}
            else:
                payload = {"buffer": file_obj.read()}

            # Configure Deepgram options
            options = PrerecordedOptions(
                model=self.app_state.models.audio_model,
                language=lang,
                smart_format=True,
                numerals=False,  # We handle number conversion ourselves
                punctuate=True,
            )

            # Execute transcription with timeout
            response = client.listen.rest.v("1").transcribe_file(
                payload, options, timeout=DEEPGRAM_TIMEOUT_SECONDS
            )

            # Extract transcript from response
            if response.results and response.results.channels:
                transcript = response.results.channels[0].alternatives[0].transcript
                if transcript:
                    return transcript

            return "Error: Empty Deepgram response."

        except Exception as error:
            self._logger.error(
                "Deepgram transcription failed",
                extra={"error": str(error)},
                exc_info=True,
            )
            raise TranscriptionError(f"Deepgram API error: {error}") from error

    def transcribe(self, filename: str, lang: str, duration: float) -> str:
        """
        Transcribe audio file using configured backend.

        Orchestrates the full transcription pipeline:
        1. Validate file
        2. Route to appropriate backend (local/Groq/Deepgram)
        3. Apply number conversion
        4. Apply user replacements

        Args:
            filename: Path to the audio file.
            lang: Language code.
            duration: Recording duration in seconds (for logging).

        Returns:
            Final transcribed and processed text, or error message.
        """
        try:
            # Validate audio file
            file_path = Path(filename).resolve()
            if not file_path.exists():
                return "Error: Audio file not found."

            if file_path.stat().st_size < MIN_VALID_AUDIO_FILE_SIZE_BYTES:
                return "Error: Audio file too small or corrupted."

            model = self.app_state.models.audio_model
            transcript = ""

            # Route to appropriate backend
            if model.startswith("local"):
                transcript = local_whisper.transcribe(
                    str(file_path), lang, model_name=model
                )
            elif model.startswith("whisper"):
                transcript = self._transcribe_ai(str(file_path), lang)
            elif model.startswith("nova"):
                transcript = self._transcribe_deepgram(str(file_path), lang)
            else:
                return f"Error: Unknown transcription model '{model}'."

            # Check for backend errors
            if transcript.startswith("Error"):
                return transcript

            # Apply number conversion for supported languages
            if lang in self._SUPPORTED_NUMBER_CONVERSION_LANGUAGES:
                transcript = self.convert_numbers(transcript, lang)

            # Apply user-defined replacements
            final_text = self.apply_replacements(transcript)

            self._logger.info(
                "Transcription completed",
                extra={
                    "model": model,
                    "language": lang,
                    "duration": duration,
                    "length": len(final_text),
                },
            )

            return final_text

        except TranscriptionError as error:
            # Already logged in _transcribe_* methods
            return str(error)

        except Exception as error:
            self._logger.error(
                "Transcription pipeline failed",
                extra={"error": str(error)},
                exc_info=True,
            )
            return f"Error: Unexpected transcription failure - {error}"


class TranscriptionManager:
    """
    Orchestrate the end-to-end transcription flow with robust pasting logic.

    Coordinates:
    - Recording lifecycle (start/stop)
    - Window focus management
    - Transcription service invocation
    - Stats and history updates
    - Clipboard paste operations
    """

    def __init__(
        self,
        app_state: AppState,
        audio_manager: AudioManager,
        sound_manager: SoundManager,
        stats_manager: StatsManager,
        history_manager: HistoryManager,
        transcription_service: TranscriptionService,
        clipboard_manager: ClipboardManagerProtocol,
        event_bus: EventBusProtocol,
    ) -> None:
        """
        Initialize the TranscriptionManager.

        Args:
            app_state: Global application state.
            audio_manager: Audio recording subsystem.
            sound_manager: Sound effect player.
            stats_manager: Usage statistics tracker.
            history_manager: Transcription history storage.
            transcription_service: Audio-to-text conversion service.
            clipboard_manager: Clipboard and paste operations.
            event_bus: Event publishing system.
        """
        self.app_state = app_state
        self.audio_manager = audio_manager
        self.sound_manager = sound_manager
        self.stats_manager = stats_manager
        self.history_manager = history_manager
        self.transcription_service = transcription_service
        self.clipboard_manager = clipboard_manager
        self.event_bus = event_bus
        self._logger = logging.getLogger(__name__)

        # Window handle that was active before recording started
        self._previous_active_window: int | None = None

    def _wait_for_file(self, filepath: str) -> bool:
        """
        Wait for the audio file to be fully written to disk.

        Args:
            filepath: Path to the audio file.

        Returns:
            True if file is ready, False if timeout exceeded.
        """
        start = time.time()
        file_path = Path(filepath)

        while time.time() - start < AUDIO_FILE_WRITE_TIMEOUT_SECONDS:
            if file_path.exists() and file_path.stat().st_size > 0:
                return True
            time.sleep(FILE_CHECK_INTERVAL_SECONDS)

        self._logger.warning(
            "Audio file write timeout",
            extra={"path": filepath, "timeout": AUDIO_FILE_WRITE_TIMEOUT_SECONDS},
        )
        return False

    def _safe_paste(self, text: str) -> None:
        """
        Safely paste text to the previously active window.

        Handles window focus restoration and delegates to clipboard manager.

        Args:
            text: Text to paste.
        """
        if not text:
            return

        try:
            # Restore focus to the window that was active before recording
            if self._previous_active_window:
                try:
                    # Restore minimized window if needed
                    if win32gui.IsIconic(self._previous_active_window):
                        win32gui.ShowWindow(
                            self._previous_active_window, win32con.SW_RESTORE
                        )

                    # Bring window to foreground
                    win32gui.SetForegroundWindow(self._previous_active_window)

                    # Allow OS window manager to process focus change
                    time.sleep(WINDOW_FOCUS_DELAY_SECONDS)

                except OSError as error:
                    self._logger.warning(
                        "Could not restore focus to previous window",
                        extra={
                            "hwnd": self._previous_active_window,
                            "error": str(error),
                        },
                    )

            # Execute paste operation
            self.clipboard_manager.paste_and_clear(text)

        except Exception as error:
            self._logger.error(
                "Safe paste orchestration failed",
                extra={"error": str(error)},
                exc_info=True,
            )

    def stop_recording_and_transcribe(
        self, timing_tracker: dict[str, object] | None = None
    ) -> None:
        """
        Stop recording, transcribe audio, and safely paste the result.

        Full workflow:
        1. Capture currently active window (paste target)
        2. Stop audio recording
        3. Hide Ozmoz window to reveal target app
        4. Transcribe audio file
        5. Restore window focus
        6. Paste transcribed text
        7. Update stats and history
        8. Cleanup temporary files

        Args:
            timing_tracker: Optional dictionary to store performance metrics.
        """
        start_time = time.perf_counter()

        if not self.app_state.audio.is_recording:
            return

        current_audio_file = self.app_state.audio.current_recording_path
        rec_duration = time.time() - self.app_state.audio.recording_start_time

        if not current_audio_file:
            self._logger.error("No recording path set before stopping")
            self._safe_paste("Error: No recording path available.")
            self.app_state.is_busy = False
            return

        try:
            self._previous_active_window = win32gui.GetForegroundWindow()
        except OSError as error:
            self._logger.warning(
                "Could not capture foreground window",
                extra={"error": str(error)},
            )
            self._previous_active_window = None

        self.app_state.audio.is_recording = False

        self.event_bus.publish("transcription_started", None)

        # Notify UI
        if self.app_state.ui.window:
            try:
                SafeJSExecutor.dispatch_event(
                    self.app_state.ui.window, "pywebview", "stop_recording"
                )
            except Exception as error:
                self._logger.warning(
                    "UI notification failed", extra={"error": str(error)}
                )

        # Hide Ozmoz window to reveal underlying application
        try:
            hwnd = win32gui.FindWindow(None, "Ozmoz")
            if hwnd and win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
        except OSError as error:
            self._logger.warning(
                "Could not hide Ozmoz window", extra={"error": str(error)}
            )

        transcribed_text: str | None = None

        try:
            # Restore system volume if muted during recording
            if self.app_state.audio.was_muted_during_recording:
                self.audio_manager.unmute_system_volume()
                self.app_state.audio.was_muted_during_recording = False

            # Play stop beep
            if self.app_state.audio.sound_enabled:
                self.sound_manager.play("beep_off")

            # Wait for audio file to be written
            if not current_audio_file or not self._wait_for_file(current_audio_file):
                self._safe_paste("Error: Audio file not ready.")
                return

            # Transcribe audio
            transcribed_text = self.transcription_service.transcribe(
                current_audio_file, self.app_state.models.language, rec_duration
            )

            # Handle local model missing error
            if transcribed_text == "Error: Local model not found":
                self._safe_paste("⚠️ Local Whisper model missing. Check Settings.")

                # Show settings window with model installation instructions
                if self.app_state.ui.settings_window:
                    try:
                        self.app_state.ui.settings_window.show()
                        SafeJSExecutor.call_function(
                            self.app_state.ui.settings_window,
                            "window.showLocalModelModal",
                        )
                    except Exception as error:
                        self._logger.warning(
                            "Could not show settings modal", extra={"error": str(error)}
                        )
                return

            # Paste result
            if not transcribed_text or transcribed_text.startswith("Error"):
                self._safe_paste(transcribed_text or "Error: Transcription failed.")
            else:
                self._safe_paste(transcribed_text)

            # Update stats and history in background
            def update_stats() -> None:
                try:
                    if transcribed_text and not transcribed_text.startswith("Error"):
                        self.stats_manager.update_stats(
                            transcribed_text,
                            rec_duration,
                            time.perf_counter() - start_time,
                            False,
                        )
                        self.history_manager.add_entry(transcribed_text)

                    # Refresh UI dashboard
                    if self.app_state.ui.settings_window:
                        SafeJSExecutor.call_function(
                            self.app_state.ui.settings_window, "refreshDashboardFull"
                        )

                except Exception as error:
                    self._logger.warning(
                        "Stats update failed", extra={"error": str(error)}
                    )

            threading.Thread(
                target=update_stats, daemon=True, name="StatsUpdater"
            ).start()

            # Publish completion event
            self.event_bus.publish(
                "transcription_complete",
                {"text": transcribed_text, "source": "dictation"},
            )

        except Exception as error:
            self._logger.critical(
                "Transcription workflow failed",
                extra={"error": str(error)},
                exc_info=True,
            )
            self._safe_paste(f"Error: Critical failure - {error}")

        finally:
            # Reset state flags
            self.app_state.is_busy = False
            self.app_state.audio.recording_start_time = 0.0
            self._previous_active_window = None

            # Cleanup temporary audio file
            if current_audio_file:
                try:
                    file_path = Path(current_audio_file)
                    if file_path.exists():
                        threading.Thread(
                            target=file_path.unlink,
                            args=(True,),  # missing_ok=True
                            daemon=True,
                            name="AudioCleanup",
                        ).start()
                except Exception as error:
                    self._logger.warning(
                        "Audio file cleanup failed",
                        extra={"path": current_audio_file, "error": str(error)},
                    )

            # Reset UI state
            if self.app_state.ui.window:
                try:
                    SafeJSExecutor.call_function(
                        self.app_state.ui.window, "setSettingsButtonState", False
                    )
                except Exception as error:
                    self._logger.warning(
                        "UI state reset failed", extra={"error": str(error)}
                    )
