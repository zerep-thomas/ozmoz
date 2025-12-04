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

# Pre-import configuration to prevent Pygame support prompt spam
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

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
    Manages file path resolution, handling differences between
    development environments and frozen applications (PyInstaller).
    """

    @staticmethod
    def get_user_data_path(relative_path: str) -> Path:
        """
        Returns an absolute path to the user storage directory.
        Falls back to a local folder if LOCALAPPDATA is missing.

        Args:
            relative_path (str): The relative path to the file.

        Returns:
            Path: The full absolute path.
        """
        try:
            base_dir: Optional[str] = os.getenv("LOCALAPPDATA")
            if not base_dir:
                raise ValueError("LOCALAPPDATA environment variable missing")
            base_path = Path(base_dir) / "Ozmoz"
        except (ValueError, TypeError):
            base_path = Path.cwd() / "ozmoz_data"

        full_path: Path = base_path / relative_path
        # Ensure the directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return full_path

    @staticmethod
    def get_resource_path(relative_path: str) -> str:
        """
        Resolves the absolute path to a resource, compatible with PyInstaller's
        temporary directory (_MEIPASS).

        Args:
            relative_path (str): The relative path to the resource.

        Returns:
            str: The absolute path string.
        """
        try:
            # PyInstaller creates a temporary directory at _MEIPASS
            base_path: str = getattr(sys, "_MEIPASS", os.path.abspath("."))
        except AttributeError:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)


class SuppressStderr:
    """
    Context manager to suppress stderr output (e.g., to hide low-level ALSA logs).
    """

    def __init__(self) -> None:
        self.original_stderr: Optional[Any] = None

    def __enter__(self) -> None:
        """Redirects stderr to os.devnull."""
        self.original_stderr = sys.stderr
        sys.stderr = open(os.devnull, "w")

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Restores the original stderr."""
        if sys.stderr:
            sys.stderr.close()
        if self.original_stderr:
            sys.stderr = self.original_stderr


# --- Audio & Sounds ---


class SoundManager:
    """
    Singleton class for handling audio feedback playback via Pygame.
    """

    _instance: Optional["SoundManager"] = None
    _initialized: bool = False

    # Sound attributes typed as Optional because initialization might fail
    beep_on: Optional[pygame.mixer.Sound] = None
    beep_off: Optional[pygame.mixer.Sound] = None

    def __new__(cls) -> "SoundManager":
        """Ensures only one instance of SoundManager exists."""
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
            relative_path (str): Path to the sound file.
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
            sound_name (str): The name of the attribute (e.g., 'beep_on').
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
    Manages screen related operations such as taking screenshots
    and controlling window visibility during capture.
    """

    def capture(self) -> Optional[str]:
        """
        Hides the application windows, captures the secondary screen,
        and restores the application windows.

        Returns:
            Optional[str]: The file path to the saved screenshot, or None on failure.
        """
        screenshot_path: Optional[str] = None
        main_window_handle: int = 0
        settings_window_handle: int = 0

        try:
            # Retrieve window handles
            main_window_handle = win32gui.FindWindow(None, "Ozmoz")
            settings_window_handle = win32gui.FindWindow(None, "Ozmoz Settings")

            # Temporarily hide windows if they are visible
            if main_window_handle and win32gui.IsWindowVisible(main_window_handle):
                win32gui.ShowWindow(main_window_handle, win32con.SW_HIDE)
            if settings_window_handle and win32gui.IsWindowVisible(
                settings_window_handle
            ):
                win32gui.ShowWindow(settings_window_handle, win32con.SW_HIDE)

            time.sleep(0.3)  # Short delay to allow the OS to refresh the display

            # Prepare temporary file path
            temp_directory = tempfile.gettempdir()
            screenshot_path = os.path.join(
                temp_directory, f"ozmoz_capture_{uuid.uuid4()}.png"
            )

            # Capture specific monitor (Monitor 1 = Index 1 in mss)
            with mss.mss() as screen_capture_tool:
                # Note: mss.monitors[1] is usually the first external or main screen
                monitor_region = screen_capture_tool.monitors[1]
                screenshot_image = screen_capture_tool.grab(monitor_region)
                mss.tools.to_png(
                    screenshot_image.rgb, screenshot_image.size, output=screenshot_path
                )

            logging.info(f"Screenshot saved successfully: {screenshot_path}")
            return screenshot_path

        except Exception as error:
            logging.error(f"Screen capture error: {error}", exc_info=True)
            # Cleanup if file was partially created
            if screenshot_path and os.path.exists(screenshot_path):
                os.remove(screenshot_path)
            return None

        finally:
            # Restore windows visibility
            if main_window_handle:
                win32gui.ShowWindow(main_window_handle, win32con.SW_SHOW)
            if settings_window_handle:
                win32gui.ShowWindow(settings_window_handle, win32con.SW_SHOW)

    def convert_image_to_base64(self, image_path: str) -> Optional[str]:
        """
        Reads an image file and converts it to a Base64 encoded string.

        Args:
            image_path (str): Path to the image file.

        Returns:
            Optional[str]: The Base64 string with data URI prefix, or None on error.
        """
        if not image_path or not os.path.exists(image_path):
            return None
        try:
            with open(image_path, "rb") as image_file:
                encoded_bytes = base64.b64encode(image_file.read())
                encoded_string = encoded_bytes.decode("utf-8")
            return f"data:image/png;base64,{encoded_string}"
        except Exception as error:
            logging.error(f"Base64 conversion error: {error}")
            return None


# --- Clipboard ---


class ClipboardManager:
    """
    Manages system clipboard operations using Win32 API for better robustness
    than standard libraries (handles 'Access Denied' errors).
    """

    def _get_native_clipboard_text(self, max_retries: int = 10) -> Optional[str]:
        """
        Attempts to read text from the clipboard with multiple retries
        to handle locking conflicts.

        Args:
            max_retries (int): Number of times to retry opening the clipboard.

        Returns:
            Optional[str]: The clipboard text content or None if unavailable.
        """
        for _ in range(max_retries):
            try:
                win32clipboard.OpenClipboard()
                try:
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
                    return None
                finally:
                    win32clipboard.CloseClipboard()
            except pywintypes.error as error:
                if error.winerror == 5:  # Error 5: Access Denied (clipboard busy)
                    time.sleep(0.1)
                    continue
                logging.warning(f"Win32 Clipboard error: {error}")
                return None
            except Exception:
                return None
        return None

    def get_selected_text(self, timeout_seconds: float = 0.8) -> str:
        """
        Simulates a Ctrl+C copy command to retrieve the currently selected text.

        Args:
            timeout_seconds (float): Max time to wait for clipboard update.

        Returns:
            str: The captured text.
        """
        selected_text: str = ""
        original_clipboard_content: str = ""

        # Backup current clipboard state
        try:
            original_clipboard_content = pyperclip.paste()
        except Exception:
            pass

        try:
            pyperclip.copy("")  # Clear buffer to detect changes
            time.sleep(0.05)

            # Simulate Copy command
            pyautogui.hotkey("ctrl", "c")

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
            # Asynchronously restore original clipboard to prevent UI blocking
            if original_clipboard_content:
                threading.Thread(
                    target=lambda: pyperclip.copy(original_clipboard_content),
                    daemon=True,
                ).start()

        return selected_text
