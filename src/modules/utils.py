"""
Utilities Module for Ozmoz.

This module provides infrastructure components including:
- Path management for development and frozen (PyInstaller) environments.
- Audio playback management using Pygame.
- Screen capture capabilities using MSS and Win32 APIs.
- Clipboard manipulation with error handling for Windows.
- Context managers for stream suppression.
"""

import base64
import logging
import os
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from types import TracebackType
from typing import Any, Optional, Type

# --- Environment Configuration ---
# Suppress PyGame support prompt on import
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

# --- Third-Party Imports ---
import mss
import mss.tools
import pyautogui
import pygame
import pyperclip
import pywintypes
import win32clipboard
import win32con
import win32gui

# --- Path Management ---


class PathManager:
    """
    Manages file path resolution.

    Handles differences between development environments and frozen applications
    (e.g., running from source vs. running as a PyInstaller EXE).
    """

    @staticmethod
    def get_user_data_path(relative_path: str) -> Path:
        """
        Resolves an absolute path to the user storage directory.

        Attempts to use the %LOCALAPPDATA% directory. If unavailable,
        falls back to a local 'ozmoz_data' folder in the current working directory.

        Args:
            relative_path (str): The relative path to the file (e.g., 'data/settings.json').

        Returns:
            Path: The fully resolved absolute path.
        """
        try:
            local_app_data: Optional[str] = os.getenv("LOCALAPPDATA")
            if not local_app_data:
                raise ValueError("LOCALAPPDATA environment variable is missing")
            base_path = Path(local_app_data) / "Ozmoz"
        except (ValueError, TypeError):
            base_path = Path.cwd() / "ozmoz_data"

        full_path: Path = base_path / relative_path

        # Ensure the directory hierarchy exists before returning
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            logging.error(
                f"Failed to create directory structure for {full_path}: {error}"
            )

        return full_path

    @staticmethod
    def get_resource_path(relative_path: str) -> str:
        """
        Resolves the absolute path to a static resource.

        Compatible with PyInstaller's `_MEIPASS` temporary directory for one-file builds.

        Args:
            relative_path (str): The relative path to the resource (e.g., 'src/static/icon.png').

        Returns:
            str: The absolute path as a string.
        """
        try:
            # PyInstaller creates a temporary directory at _MEIPASS
            base_path: str = getattr(sys, "_MEIPASS", os.path.abspath("."))
        except AttributeError:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)


class SuppressStderr:
    """
    Context manager to suppress standard error output.

    Useful for silencing low-level C-library noise (e.g., ALSA/PyAudio warnings)
    that cannot be caught by Python's logging module.
    """

    def __init__(self) -> None:
        """Initialize the context manager."""
        self._original_stderr: Optional[Any] = None
        self._null_file: Optional[Any] = None

    def __enter__(self) -> None:
        """Redirects sys.stderr to os.devnull."""
        self._original_stderr = sys.stderr
        try:
            self._null_file = open(os.devnull, "w")
            sys.stderr = self._null_file
        except OSError:
            # Fallback if devnull cannot be opened
            pass

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Restores the original sys.stderr."""
        if self._null_file:
            self._null_file.close()
        if self._original_stderr:
            sys.stderr = self._original_stderr


# --- Audio & Sounds ---


class SoundManager:
    """
    Singleton class for handling audio feedback playback via Pygame.

    Manages the loading and playing of UI sound effects (beeps).
    """

    _instance: Optional["SoundManager"] = None
    _initialized: bool = False

    # Sound attributes typed as Optional because initialization might fail
    beep_on: Optional[pygame.mixer.Sound] = None
    beep_off: Optional[pygame.mixer.Sound] = None

    def __new__(cls) -> "SoundManager":
        """Ensures only one instance of SoundManager exists (Singleton Pattern)."""
        if cls._instance is None:
            cls._instance = super(SoundManager, cls).__new__(cls)
        return cls._instance

    def _initialize(self) -> None:
        """
        Initializes the Pygame mixer and loads default sound effects.
        """
        if self._initialized:
            return

        logging.info("Initializing Audio (Pygame)...")
        try:
            # Pre-initialize to reduce latency
            pygame.mixer.pre_init(frequency=44100, buffer=512)
            pygame.mixer.init()

            self.beep_on = self._load_sound("src/static/audio/beep_on.wav", 0.2)
            self.beep_off = self._load_sound("src/static/audio/beep_off.wav", 0.2)

            self._initialized = True
        except Exception as error:
            logging.critical(f"Audio initialization error: {error}", exc_info=True)
            self.beep_on = None
            self.beep_off = None

    def _load_sound(
        self, relative_path: str, volume: float
    ) -> Optional[pygame.mixer.Sound]:
        """
        Helper to safely load a sound file.

        Args:
            relative_path (str): Path to the sound file relative to the app root.
            volume (float): Volume level (0.0 to 1.0).

        Returns:
            Optional[pygame.mixer.Sound]: The sound object or None if failed.
        """
        try:
            file_path: str = PathManager.get_resource_path(relative_path)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Audio file not found: {file_path}")

            sound = pygame.mixer.Sound(file_path)
            sound.set_volume(volume)
            return sound
        except Exception as error:
            logging.error(f"Error loading sound '{relative_path}': {error}")
            return None

    def play(self, sound_name: str) -> None:
        """
        Plays a pre-loaded sound by name.

        Args:
            sound_name (str): The name of the attribute to play (e.g., 'beep_on').
        """
        if not self._initialized:
            self._initialize()

        sound_object: Optional[pygame.mixer.Sound] = getattr(self, sound_name, None)

        if sound_object:
            try:
                sound_object.play()
            except pygame.error as error:
                logging.warning(f"Playback error for '{sound_name}': {error}")
        else:
            logging.warning(f"Unknown sound requested: '{sound_name}'")


# --- Capture & Screen ---


class ScreenManager:
    """
    Manages screen-related operations.

    Responsibilities:
    - Taking screenshots of specific monitors.
    - Managing window visibility during capture to prevent recursion.
    - Converting images to Base64 for API consumption.
    """

    def capture(self) -> Optional[str]:
        """
        Captures the screen content.

        Workflow:
        1. Hides the application windows (Main & Settings) to uncover content behind them.
        2. Captures the specific monitor using MSS.
        3. Restores application windows.

        Returns:
            Optional[str]: The file path to the saved screenshot, or None on failure.
        """
        screenshot_path: Optional[str] = None
        main_window_handle: int = 0
        settings_window_handle: int = 0

        try:
            # 1. Retrieve window handles
            main_window_handle = win32gui.FindWindow(None, "Ozmoz")
            settings_window_handle = win32gui.FindWindow(None, "Ozmoz Settings")

            # 2. Temporarily hide windows if they are visible
            if main_window_handle and win32gui.IsWindowVisible(main_window_handle):
                win32gui.ShowWindow(main_window_handle, win32con.SW_HIDE)

            if settings_window_handle and win32gui.IsWindowVisible(
                settings_window_handle
            ):
                win32gui.ShowWindow(settings_window_handle, win32con.SW_HIDE)

            # Short delay to allow the OS compositor to refresh the display
            time.sleep(0.3)

            # 3. Prepare temporary file path
            temp_directory = tempfile.gettempdir()
            screenshot_path = os.path.join(
                temp_directory, f"ozmoz_capture_{uuid.uuid4()}.png"
            )

            # 4. Capture
            with mss.mss() as screen_capture_tool:
                # mss.monitors[1] typically refers to the primary monitor
                # If specific monitor selection is needed, logic should be added here.
                if len(screen_capture_tool.monitors) > 1:
                    monitor_region = screen_capture_tool.monitors[1]
                    screenshot_image = screen_capture_tool.grab(monitor_region)

                    mss.tools.to_png(
                        screenshot_image.rgb,
                        screenshot_image.size,
                        output=screenshot_path,
                    )
                else:
                    logging.error("No monitors detected by MSS.")
                    return None

            logging.info(f"Screenshot saved successfully: {screenshot_path}")
            return screenshot_path

        except Exception as error:
            logging.error(f"Screen capture error: {error}", exc_info=True)
            # Clean up potentially corrupted file
            if screenshot_path and os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                except OSError:
                    pass
            return None

        finally:
            # 5. Restore windows visibility regardless of success/failure
            if main_window_handle:
                win32gui.ShowWindow(main_window_handle, win32con.SW_SHOW)
            if settings_window_handle:
                win32gui.ShowWindow(settings_window_handle, win32con.SW_SHOW)

    def convert_image_to_base64(self, image_path: str) -> Optional[str]:
        """
        Reads an image file and converts it to a Base64 encoded Data URI.

        Args:
            image_path (str): Path to the image file.

        Returns:
            Optional[str]: The Base64 string prefixed with 'data:image/png;base64,',
                           or None on error.
        """
        if not image_path or not os.path.exists(image_path):
            logging.warning(f"Image not found for conversion: {image_path}")
            return None

        try:
            with open(image_path, "rb") as image_file:
                encoded_bytes = base64.b64encode(image_file.read())
                encoded_string = encoded_bytes.decode("utf-8")
            return f"data:image/png;base64,{encoded_string}"
        except Exception as error:
            logging.error(f"Base64 conversion error for {image_path}: {error}")
            return None


# --- Clipboard ---


class ClipboardManager:
    """
    Manages system clipboard operations.

    Uses Win32 API directly for read operations to handle 'Access Denied' errors
    more robustly than standard libraries, which is common when monitoring clipboard.
    """

    def _get_native_clipboard_text(self, max_retries: int = 10) -> Optional[str]:
        """
        Attempts to read text from the Windows clipboard with multiple retries.

        This handles race conditions where the clipboard is briefly locked by
        another application.

        Args:
            max_retries (int): Number of times to retry opening the clipboard.

        Returns:
            Optional[str]: The clipboard text content or None if unavailable/empty.
        """
        for _ in range(max_retries):
            try:
                win32clipboard.OpenClipboard()
                try:
                    # Prioritize Unicode text, fall back to ANSI text
                    if win32clipboard.IsClipboardFormatAvailable(
                        win32clipboard.CF_UNICODETEXT
                    ):
                        return win32clipboard.GetClipboardData(
                            win32clipboard.CF_UNICODETEXT
                        )
                    elif win32clipboard.IsClipboardFormatAvailable(
                        win32clipboard.CF_TEXT
                    ):
                        return win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)

                    return None  # No compatible text format found
                finally:
                    win32clipboard.CloseClipboard()

            except pywintypes.error as error:
                # Error 5: Access Denied (Clipboard locked by another process)
                if error.winerror == 5:
                    time.sleep(0.1)
                    continue
                logging.warning(f"Win32 Clipboard error: {error}")
                return None
            except Exception as error:
                logging.error(f"Unexpected clipboard error: {error}")
                return None

        return None

    def get_selected_text(self, timeout_seconds: float = 0.8) -> str:
        """
        Retrieves the currently selected text in the active window.

        Mechanism:
        1. Backs up current clipboard content.
        2. Clears clipboard.
        3. Simulates Ctrl+C (Copy).
        4. Polls clipboard for new data.
        5. Restores original clipboard content asynchronously.

        Args:
            timeout_seconds (float): Max time to wait for the copy operation to complete.

        Returns:
            str: The captured text, or an empty string if nothing was selected/copied.
        """
        selected_text: str = ""
        original_clipboard_content: str = ""

        # 1. Backup current clipboard state
        try:
            original_clipboard_content = pyperclip.paste()
        except Exception:
            # Clipboard might be empty or inaccessible; non-fatal
            pass

        try:
            # 2. Clear buffer to detect changes reliably
            pyperclip.copy("")
            time.sleep(0.05)

            # 3. Simulate System Copy command
            pyautogui.hotkey("ctrl", "c")

            # 4. Poll for data
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                content = self._get_native_clipboard_text()
                if content:
                    selected_text = content
                    break
                time.sleep(0.05)

        except Exception as error:
            logging.error(f"Smart Copy error: {error}")

        finally:
            # 5. Restore original clipboard to prevent user disruption
            # Done in a daemon thread to avoid blocking the UI return
            if original_clipboard_content:
                threading.Thread(
                    target=lambda: pyperclip.copy(original_clipboard_content),
                    daemon=True,
                ).start()

        return selected_text
