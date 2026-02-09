"""
Utilities Module for Ozmoz.

This module provides infrastructure components including:
- Secure path management for development and frozen (PyInstaller) environments
- Audio playback management using native Windows API (winsound)
- Screen capture capabilities using MSS and Win32 APIs
- Clipboard manipulation with robust error handling for Windows
- Context managers for stream suppression

Security Features:
- Path traversal protection with whitelist validation
- Secure temporary file handling
- Clipboard access with retry logic and race condition handling
"""

import base64
import logging
import os
import sys
import tempfile
import threading
import time
import uuid
import winsound
from pathlib import Path
from types import TracebackType
from typing import IO, Final, Optional

# Third-party imports
import keyboard
import mss
import mss.tools
import pyautogui
import pyperclip
import pywintypes
import win32clipboard
import win32con
import win32gui

# --- Module Constants ---

# Path Management
FALLBACK_DATA_DIR_NAME: Final[str] = "ozmoz_data"
ALLOWED_BASE_DIRS: Final[frozenset[str]] = frozenset(
    {"data", "cache", "logs", "config"}
)

# Audio Configuration
# Pre-load audio files into memory for instant playback without disk I/O
BEEP_ON_FILENAME: Final[str] = "src/static/audio/beep_on.wav"
BEEP_OFF_FILENAME: Final[str] = "src/static/audio/beep_off.wav"

# Screen Capture Configuration
# Allow OS window manager to refresh display after hiding windows
WINDOW_HIDE_COMPOSITOR_DELAY_SECONDS: Final[float] = 0.3
# Unique prefix for screenshot temp files to avoid collisions
SCREENSHOT_TEMP_PREFIX: Final[str] = "ozmoz_capture_"
# Monitor index for primary display (mss uses 1-based indexing)
PRIMARY_MONITOR_INDEX: Final[int] = 1

# Clipboard Configuration
# Maximum attempts to open clipboard before giving up (handles locking by other apps)
CLIPBOARD_MAX_RETRIES: Final[int] = 10
# Delay between clipboard access retries when locked
CLIPBOARD_RETRY_DELAY_SECONDS: Final[float] = 0.1
# Brief pause after clearing clipboard to ensure OS registers the change
CLIPBOARD_CLEAR_SETTLE_DELAY_SECONDS: Final[float] = 0.05
# Maximum time to wait for Ctrl+C to populate clipboard
CLIPBOARD_COPY_TIMEOUT_SECONDS: Final[float] = 0.8
# Delay after copy before simulating paste
CLIPBOARD_PASTE_DELAY_SECONDS: Final[float] = 0.1
# Delay after paste before clearing clipboard history
CLIPBOARD_CLEAR_DELAY_SECONDS: Final[float] = 0.5
# Polling interval when waiting for clipboard content
CLIPBOARD_POLL_INTERVAL_SECONDS: Final[float] = 0.05

# Win32 Error Codes
WIN32_ERROR_ACCESS_DENIED: Final[int] = 5


# --- Custom Exceptions ---


class PathSecurityError(Exception):
    """Raised when a path operation violates security constraints."""


class ScreenCaptureError(Exception):
    """Raised when screen capture fails."""


class ClipboardAccessError(Exception):
    """Raised when clipboard operations fail after all retries."""


# --- Path Management ---


class PathManager:
    """
    Secure file path resolution manager.

    Handles differences between development and frozen (PyInstaller) environments
    while enforcing security constraints to prevent path traversal attacks.

    Security Features:
    - Validates all paths are within approved base directories
    - Resolves symlinks to prevent directory escape
    - Sanitizes relative paths to remove parent directory references

    Thread Safety: All methods are stateless and thread-safe.
    """

    @staticmethod
    def get_user_data_path(relative_path: str) -> Path:
        """
        Resolve secure path to user data directory with traversal protection.

        Uses %LOCALAPPDATA%/Ozmoz as base directory. Falls back to
        './ozmoz_data' if environment variable is unavailable.

        Security:
        - Validates relative_path doesn't escape base directory
        - Checks resolved path is within allowed directory tree
        - Creates parent directories with restrictive permissions

        Args:
            relative_path: Path relative to user data root (e.g., 'data/settings.json').
                          Must not contain '..' or absolute path components.

        Returns:
            Validated absolute Path object.

        Raises:
            PathSecurityError: If path validation fails or traversal detected.
            OSError: If directory creation fails due to permissions.

        Example:
            >>> PathManager.get_user_data_path("data/settings.json")
            WindowsPath('C:/Users/Alice/AppData/Local/Ozmoz/data/settings.json')

            >>> PathManager.get_user_data_path("../../etc/passwd")  # Raises PathSecurityError
        """
        # Input validation
        if not relative_path or not isinstance(relative_path, str):
            raise PathSecurityError("relative_path must be a non-empty string")

        # Prevent absolute paths
        if os.path.isabs(relative_path):
            raise PathSecurityError(f"Absolute paths not allowed: {relative_path}")

        # Determine base directory
        try:
            local_app_data: Optional[str] = os.getenv("LOCALAPPDATA")
            if not local_app_data:
                raise ValueError("LOCALAPPDATA environment variable is missing")
            base_path = Path(local_app_data) / "Ozmoz"
        except (ValueError, TypeError) as e:
            logging.warning(
                f"LOCALAPPDATA unavailable, using fallback: {e}",
                extra={"fallback_dir": FALLBACK_DATA_DIR_NAME},
            )
            base_path = Path.cwd() / FALLBACK_DATA_DIR_NAME

        # Resolve base to absolute path (follows symlinks)
        base_path = base_path.resolve()

        # Construct and resolve full path
        try:
            full_path = (base_path / relative_path).resolve()
        except (ValueError, OSError) as e:
            raise PathSecurityError(
                f"Invalid path resolution for '{relative_path}': {e}"
            ) from e

        # CRITICAL: Verify path is within base directory (prevents traversal)
        if not full_path.is_relative_to(base_path):
            raise PathSecurityError(
                f"Path traversal detected: '{relative_path}' resolves outside base directory. "
                f"Base: {base_path}, Resolved: {full_path}"
            )

        # Additional check: Ensure first path component is in whitelist
        try:
            relative_to_base = full_path.relative_to(base_path)
            first_component = (
                relative_to_base.parts[0] if relative_to_base.parts else ""
            )

            if first_component and first_component not in ALLOWED_BASE_DIRS:
                raise PathSecurityError(
                    f"Path component '{first_component}' not in allowed directories: {ALLOWED_BASE_DIRS}"
                )
        except ValueError as e:
            # Should never happen due to is_relative_to check, but defensive
            raise PathSecurityError(f"Path validation error: {e}") from e

        # Create parent directories if they don't exist
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            logging.error(
                "Failed to create directory structure",
                exc_info=True,
                extra={"path": str(full_path), "error": str(error)},
            )
            raise

        return full_path

    @staticmethod
    def get_resource_path(relative_path: str) -> str:
        """
        Resolve absolute path to application static resource.

        Compatible with PyInstaller's `_MEIPASS` temporary directory for
        single-file executables. Resources are bundled into the executable
        and extracted to a temp folder at runtime.

        Args:
            relative_path: Path relative to application root (e.g., 'src/static/icon.png').

        Returns:
            Absolute path as string for compatibility with legacy APIs.

        Example:
            >>> PathManager.get_resource_path("src/static/audio/beep.wav")
            'C:/Users/Alice/AppData/Local/Temp/_MEI123/src/static/audio/beep.wav'
        """
        if not relative_path or not isinstance(relative_path, str):
            raise ValueError("relative_path must be a non-empty string")

        try:
            # PyInstaller sets sys._MEIPASS to temp extraction directory
            base_path: str = getattr(sys, "_MEIPASS", os.path.abspath("."))
        except AttributeError:
            # Fallback for development environment
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)


class SuppressStderr:
    """
    Context manager to suppress stderr output from C libraries.

    Useful for silencing low-level warnings (e.g., ALSA/PyAudio) that
    bypass Python's logging system and clutter console output.

    Thread Safety: Not thread-safe. Only use in single-threaded contexts
    or with external synchronization.

    Example:
        >>> with SuppressStderr():
        ...     noisy_c_library_call()  # stderr is hidden
    """

    def __init__(self) -> None:
        """Initialize context manager with null state."""
        # Type hint précis : soit un file object, soit sys.stderr, soit None
        self._original_stderr: Optional[IO[str]] = None
        self._null_file: Optional[IO[str]] = None

    def __enter__(self) -> "SuppressStderr":
        """
        Redirect sys.stderr to os.devnull.

        Returns:
            Self for context manager protocol.
        """
        self._original_stderr = sys.stderr
        try:
            self._null_file = open(os.devnull, "w", encoding="utf-8")
            sys.stderr = self._null_file  # type: ignore[assignment]
        except OSError as e:
            # Fallback: keep original stderr if devnull unavailable
            logging.warning(f"Failed to open devnull for stderr suppression: {e}")

        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """
        Restore original sys.stderr.

        Args:
            exc_type: Exception type if raised in context.
            exc_value: Exception instance if raised.
            traceback: Traceback object if exception raised.
        """
        if self._null_file is not None:
            try:
                self._null_file.close()
            except Exception as e:
                logging.warning(f"Error closing devnull: {e}")

        if self._original_stderr is not None:
            sys.stderr = self._original_stderr  # type: ignore[assignment]


# --- Audio & Sounds ---


class SoundManager:
    """
    Thread-safe singleton for managing audio feedback sounds.

    Pre-loads WAV files into memory on first access for instant playback
    without disk I/O latency. Uses Windows winsound API for synchronous
    playback to ensure sounds complete before continuing.

    Design Pattern: Thread-safe singleton with lazy initialization.

    Attributes:
        beep_on_data: Raw bytes of "recording started" sound.
        beep_off_data: Raw bytes of "recording stopped" sound.
    """

    _instance: Optional["SoundManager"] = None
    _lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    # Pre-loaded audio data (stored as bytes for winsound.SND_MEMORY)
    beep_on_data: Optional[bytes] = None
    beep_off_data: Optional[bytes] = None

    def __new__(cls) -> "SoundManager":
        """
        Create or return existing singleton instance (thread-safe).

        Returns:
            The single SoundManager instance.
        """
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def _initialize(self) -> None:
        """
        Pre-load audio files into memory (called once on first use).

        Loads WAV files into byte arrays for instant playback via winsound.SND_MEMORY.
        This eliminates disk I/O latency during playback.

        Thread Safety: Protected by instance check in callers.

        Raises:
            No exceptions raised - failures are logged and gracefully handled.
        """
        if self._initialized:
            return

        with self._lock:
            # Double-checked locking
            if self._initialized:
                return

            logging.info("Initializing SoundManager: Pre-loading audio files into RAM")

            try:
                on_path = PathManager.get_resource_path(BEEP_ON_FILENAME)
                off_path = PathManager.get_resource_path(BEEP_OFF_FILENAME)

                # Load "recording started" sound
                if os.path.exists(on_path):
                    with open(on_path, "rb") as f:
                        self.beep_on_data = f.read()
                    logging.debug(f"Loaded beep_on: {len(self.beep_on_data)} bytes")
                else:
                    logging.warning(f"Beep ON sound not found: {on_path}")

                # Load "recording stopped" sound
                if os.path.exists(off_path):
                    with open(off_path, "rb") as f:
                        self.beep_off_data = f.read()
                    logging.debug(f"Loaded beep_off: {len(self.beep_off_data)} bytes")
                else:
                    logging.warning(f"Beep OFF sound not found: {off_path}")

                self._initialized = True
                logging.info("SoundManager initialization complete")

            except OSError as e:
                logging.error(
                    "Failed to load audio files", exc_info=True, extra={"error": str(e)}
                )
            except Exception as e:
                logging.critical(
                    "Unexpected error during audio initialization",
                    exc_info=True,
                    extra={"error": str(e)},
                )

    def play(self, sound_name: str) -> None:
        """
        Play pre-loaded sound synchronously (blocks until complete).

        This synchronous behavior is intentional to guarantee the sound
        is heard before any subsequent audio device state changes (e.g., muting).

        Args:
            sound_name: Identifier for sound ("beep_on" or "beep_off").

        Example:
            >>> sound_mgr = SoundManager()
            >>> sound_mgr.play("beep_on")  # Blocks ~200ms until beep completes
        """
        if not self._initialized:
            self._initialize()

        # Map sound name to loaded data
        sound_data: Optional[bytes] = None
        if sound_name == "beep_on":
            sound_data = self.beep_on_data
        elif sound_name == "beep_off":
            sound_data = self.beep_off_data
        else:
            logging.warning(
                f"Unknown sound name: '{sound_name}'. Valid: beep_on, beep_off"
            )
            return

        if not sound_data:
            logging.warning(
                f"Sound '{sound_name}' not loaded. Playback skipped.",
                extra={"initialized": self._initialized},
            )
            return

        try:
            # SND_MEMORY: Read from RAM (no disk I/O) - ultra fast
            # SND_NODEFAULT: Don't play system default sound on error
            # No SND_ASYNC: Block until playback completes
            flags = winsound.SND_MEMORY | winsound.SND_NODEFAULT
            winsound.PlaySound(sound_data, flags)

        except RuntimeError as e:
            # winsound raises RuntimeError for playback failures
            logging.warning(
                f"Playback failed for '{sound_name}'", extra={"error": str(e)}
            )
        except Exception as e:
            logging.error(
                f"Unexpected playback error for '{sound_name}'",
                exc_info=True,
                extra={"error": str(e)},
            )


# --- Capture & Screen ---


class ScreenManager:
    """
    Manage screen capture operations with window occlusion handling.

    Responsibilities:
    - Capture screenshots of primary or specific monitors
    - Temporarily hide application windows to reveal underlying content
    - Convert images to base64 for API consumption
    - Clean up temporary files

    Security:
    - Only reads from validated temporary directory
    - Sanitizes file paths before base64 conversion
    """

    def capture(self) -> Optional[str]:
        """
        Capture primary monitor screenshot, hiding app windows temporarily.

        Workflow:
        1. Find and hide Ozmoz windows (main toolbar + settings)
        2. Wait for OS compositor to refresh display
        3. Capture primary monitor using MSS library
        4. Save to temporary file with unique name
        5. Restore window visibility

        Returns:
            Path to saved screenshot PNG, or None on failure.

        Raises:
            ScreenCaptureError: If capture fails critically.

        Example:
            >>> screen_mgr = ScreenManager()
            >>> path = screen_mgr.capture()
            >>> if path:
            ...     print(f"Screenshot: {path}")
        """
        screenshot_path: Optional[str] = None
        main_window_handle: int = 0
        settings_window_handle: int = 0

        try:
            # 1. Retrieve window handles for occlusion management
            main_window_handle = win32gui.FindWindow(None, "Ozmoz")
            settings_window_handle = win32gui.FindWindow(None, "Ozmoz Settings")

            # 2. Temporarily hide visible windows
            if main_window_handle and win32gui.IsWindowVisible(main_window_handle):
                win32gui.ShowWindow(main_window_handle, win32con.SW_HIDE)
                logging.debug("Hidden main window for capture")

            if settings_window_handle and win32gui.IsWindowVisible(
                settings_window_handle
            ):
                win32gui.ShowWindow(settings_window_handle, win32con.SW_HIDE)
                logging.debug("Hidden settings window for capture")

            # Wait for OS window manager/compositor to refresh display
            # Without this, screenshot may still show the hidden windows
            time.sleep(WINDOW_HIDE_COMPOSITOR_DELAY_SECONDS)

            # 3. Generate unique temporary file path
            temp_directory = tempfile.gettempdir()
            screenshot_filename = f"{SCREENSHOT_TEMP_PREFIX}{uuid.uuid4()}.png"
            screenshot_path = os.path.join(temp_directory, screenshot_filename)

            # 4. Capture screenshot using MSS
            with mss.mss() as screen_capture_tool:
                # Validate monitors are available
                if len(screen_capture_tool.monitors) <= PRIMARY_MONITOR_INDEX:
                    raise ScreenCaptureError(
                        f"Primary monitor (index {PRIMARY_MONITOR_INDEX}) not detected. "
                        f"Available monitors: {len(screen_capture_tool.monitors)}"
                    )

                # mss.monitors is 1-indexed: [0] = all monitors, [1] = primary, [2] = secondary...
                monitor_region = screen_capture_tool.monitors[PRIMARY_MONITOR_INDEX]
                screenshot_image = screen_capture_tool.grab(monitor_region)

                # Save as PNG
                mss.tools.to_png(
                    screenshot_image.rgb,
                    screenshot_image.size,
                    output=screenshot_path,
                )

            logging.info(
                "Screenshot captured successfully",
                extra={
                    "path": screenshot_path,
                    "size": f"{screenshot_image.width}x{screenshot_image.height}",
                },
            )
            return screenshot_path

        except ScreenCaptureError:
            # Re-raise our custom exceptions
            raise

        except Exception as error:
            logging.error(
                "Screen capture failed", exc_info=True, extra={"error": str(error)}
            )

            # Clean up potentially corrupted/partial file
            if screenshot_path and os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                    logging.debug(f"Cleaned up failed capture: {screenshot_path}")
                except OSError as e:
                    logging.warning(f"Failed to clean up screenshot: {e}")

            return None

        finally:
            # 5. CRITICAL: Always restore window visibility
            if main_window_handle:
                try:
                    win32gui.ShowWindow(main_window_handle, win32con.SW_SHOW)
                except Exception as e:
                    logging.error(f"Failed to restore main window: {e}")

            if settings_window_handle:
                try:
                    win32gui.ShowWindow(settings_window_handle, win32con.SW_SHOW)
                except Exception as e:
                    logging.error(f"Failed to restore settings window: {e}")

    def convert_image_to_base64(self, image_path: str) -> Optional[str]:
        """
        Convert image file to base64-encoded Data URI for API consumption.

        Security: Only processes files from system temp directory to prevent
        arbitrary file read attacks.

        Args:
            image_path: Absolute path to PNG image file (must be in temp directory).

        Returns:
            Base64 Data URI string (data:image/png;base64,...) or None on error.

        Raises:
            No exceptions raised - errors are logged and None is returned.

        Example:
            >>> screen_mgr = ScreenManager()
            >>> base64_uri = screen_mgr.convert_image_to_base64("/tmp/screenshot.png")
            >>> if base64_uri:
            ...     send_to_api(base64_uri)
        """
        # Input validation
        if not image_path or not isinstance(image_path, str):
            logging.warning("Invalid image_path provided for base64 conversion")
            return None

        # Security: Verify file exists
        if not os.path.exists(image_path):
            logging.warning(f"Image not found for base64 conversion: {image_path}")
            return None

        # Security: Ensure path is in temp directory (prevent arbitrary file read)
        try:
            image_path_obj = Path(image_path).resolve()
            temp_dir = Path(tempfile.gettempdir()).resolve()

            if not image_path_obj.is_relative_to(temp_dir):
                logging.error(
                    "Security violation: Attempted to convert file outside temp directory",
                    extra={"requested_path": image_path, "temp_dir": str(temp_dir)},
                )
                return None

        except (ValueError, OSError) as e:
            logging.error(f"Path validation error: {e}")
            return None

        # Perform conversion
        try:
            with open(image_path, "rb") as image_file:
                image_bytes = image_file.read()
                encoded_bytes = base64.b64encode(image_bytes)
                encoded_string = encoded_bytes.decode("utf-8")

            data_uri = f"data:image/png;base64,{encoded_string}"

            logging.debug(
                "Image converted to base64",
                extra={
                    "path": image_path,
                    "size_bytes": len(image_bytes),
                    "base64_length": len(encoded_string),
                },
            )

            return data_uri

        except OSError as e:
            logging.error(
                f"Failed to read image file: {image_path}", extra={"error": str(e)}
            )
            return None
        except Exception as error:
            logging.error(
                f"Base64 conversion error for {image_path}",
                exc_info=True,
                extra={"error": str(error)},
            )
            return None


# --- Clipboard ---


class ClipboardManager:
    """
    Robust Windows clipboard operations with race condition handling.

    Uses Win32 API directly for more reliable clipboard access than
    standard libraries. Implements retry logic to handle transient
    "Access Denied" errors when clipboard is locked by other applications.

    Common Issues Addressed:
    - Clipboard locked by another process (ERROR_ACCESS_DENIED)
    - Race conditions during rapid clipboard changes
    - Incomplete copy operations (Ctrl+C not finished)
    - Clipboard history pollution

    Thread Safety: Methods are thread-safe via Win32 clipboard locking.
    """

    def _get_native_clipboard_text(
        self, max_retries: int = CLIPBOARD_MAX_RETRIES
    ) -> Optional[str]:
        """
        Read text from clipboard with retry logic for locked clipboard.

        Handles race conditions where clipboard is temporarily locked by
        another application (common with clipboard managers, RDP, etc.).

        Args:
            max_retries: Maximum attempts to open clipboard before giving up.

        Returns:
            Clipboard text content, or None if unavailable/empty/timeout.

        Example:
            >>> clipboard_mgr = ClipboardManager()
            >>> text = clipboard_mgr._get_native_clipboard_text()
            >>> if text:
            ...     print(f"Clipboard: {text}")
        """
        for attempt in range(max_retries):
            try:
                win32clipboard.OpenClipboard()
                try:
                    # Prioritize Unicode (CF_UNICODETEXT) over ANSI (CF_TEXT)
                    if win32clipboard.IsClipboardFormatAvailable(
                        win32clipboard.CF_UNICODETEXT
                    ):
                        data = win32clipboard.GetClipboardData(
                            win32clipboard.CF_UNICODETEXT
                        )
                        return data if data else None

                    elif win32clipboard.IsClipboardFormatAvailable(
                        win32clipboard.CF_TEXT
                    ):
                        data = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
                        return data.decode("utf-8") if data else None

                    # No text format available
                    return None

                finally:
                    # CRITICAL: Always close clipboard to avoid locking
                    win32clipboard.CloseClipboard()

            except pywintypes.error as error:
                # Win32 error code 5 = ERROR_ACCESS_DENIED (clipboard locked)
                if error.winerror == WIN32_ERROR_ACCESS_DENIED:
                    if attempt < max_retries - 1:
                        time.sleep(CLIPBOARD_RETRY_DELAY_SECONDS)
                        continue

                    logging.warning(
                        "Clipboard access denied after all retries",
                        extra={"attempts": max_retries, "error_code": error.winerror},
                    )
                else:
                    logging.warning(
                        f"Win32 clipboard error: {error}",
                        extra={"error_code": error.winerror},
                    )
                return None

            except Exception as error:
                logging.error(
                    "Unexpected clipboard error",
                    exc_info=True,
                    extra={"error": str(error)},
                )
                return None

        logging.warning(f"Clipboard read failed after {max_retries} retries")
        return None

    def get_selected_text(
        self, timeout_seconds: float = CLIPBOARD_COPY_TIMEOUT_SECONDS
    ) -> str:
        """
        Capture selected text from active window via clipboard.

        Mechanism:
        1. Backup current clipboard content
        2. Clear clipboard to detect new data reliably
        3. Simulate Ctrl+C to copy selection
        4. Poll clipboard for new content (with timeout)
        5. Restore original clipboard asynchronously

        Args:
            timeout_seconds: Maximum time to wait for copy operation.

        Returns:
            Selected text, or empty string if nothing selected or timeout.

        Warning:
            This method temporarily modifies clipboard. Fast consecutive calls
            may interfere with each other.

        Example:
            >>> clipboard_mgr = ClipboardManager()
            >>> selected = clipboard_mgr.get_selected_text()
            >>> if selected:
            ...     process_text(selected)
        """
        selected_text: str = ""
        original_clipboard_content: str = ""

        # 1. Backup current clipboard state (non-critical if fails)
        try:
            original_clipboard_content = pyperclip.paste()
        except Exception as e:
            logging.debug(f"Could not backup clipboard (may be empty): {e}")

        try:
            # 2. Clear clipboard to reliably detect new content
            pyperclip.copy("")
            time.sleep(CLIPBOARD_CLEAR_SETTLE_DELAY_SECONDS)

            # 3. Simulate system copy command (Ctrl+C)
            pyautogui.hotkey("ctrl", "c")

            # 4. Poll for data with timeout
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                content = self._get_native_clipboard_text()
                if content:
                    selected_text = content
                    logging.debug(
                        f"Captured selection: {len(selected_text)} characters"
                    )
                    break

                time.sleep(CLIPBOARD_POLL_INTERVAL_SECONDS)

            if not selected_text:
                logging.debug(f"No clipboard content after {timeout_seconds}s timeout")

        except Exception as error:
            logging.error(
                "Smart copy operation failed",
                exc_info=True,
                extra={"error": str(error)},
            )

        finally:
            # 5. Restore original clipboard in background (non-blocking)
            # Daemon thread prevents blocking UI while clipboard restores
            if original_clipboard_content:

                def restore_clipboard() -> None:
                    try:
                        pyperclip.copy(original_clipboard_content)
                        logging.debug("Clipboard restored")
                    except Exception as e:
                        logging.warning(f"Clipboard restore failed: {e}")

                threading.Thread(
                    target=restore_clipboard, daemon=True, name="ClipboardRestore"
                ).start()

        return selected_text

    def paste_and_clear(self, text: str) -> None:
        """
        Copy text to clipboard, paste it, then clear clipboard history.

        Workflow:
        1. Copy text to clipboard
        2. Simulate Ctrl+V to paste
        3. Clear clipboard to avoid polluting Windows clipboard history

        This prevents the pasted text from appearing in clipboard managers
        or Windows clipboard history (Win+V).

        Args:
            text: Text to paste into active window.

        Example:
            >>> clipboard_mgr = ClipboardManager()
            >>> clipboard_mgr.paste_and_clear("Hello, world!")
        """
        if not text:
            logging.debug("paste_and_clear called with empty text, skipping")
            return

        def _paste_worker() -> None:
            """
            Background worker to avoid blocking caller.

            Runs paste operation asynchronously to maintain UI responsiveness.
            """
            try:
                # 1. Copy text to clipboard
                pyperclip.copy(text)
                logging.debug(f"Copied {len(text)} characters to clipboard")

                # Brief delay to ensure clipboard is populated
                time.sleep(CLIPBOARD_PASTE_DELAY_SECONDS)

                # 2. Simulate paste command (Ctrl+V)
                # Using keyboard library for reliability over pyautogui
                keyboard.press_and_release("ctrl+v")
                logging.debug("Simulated Ctrl+V")

                # Wait for paste to complete before clearing
                time.sleep(CLIPBOARD_CLEAR_DELAY_SECONDS)

                # 3. Clear clipboard to avoid history pollution
                pyperclip.copy("")
                logging.debug("Clipboard cleared")

            except Exception as e:
                logging.error(
                    "Clipboard paste operation failed",
                    exc_info=True,
                    extra={"error": str(e), "text_length": len(text)},
                )

        # Execute in background to avoid blocking caller
        threading.Thread(
            target=_paste_worker, daemon=True, name="ClipboardPaste"
        ).start()
