"""
OS Adapter Module for Ozmoz.

This module provides an abstraction layer for Operating System interactions,
specifically targeting Windows APIs via pywin32 and pycaw.

It handles:
- Audio volume control (Get, Set, Mute/Unmute).
- Low-level Window management (Find, Show, Hide, Move, Z-Order).
- Single Instance enforcement using Mutexes.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

# --- Conditional Imports for OS-Specific Libraries ---
try:
    import win32api
    import win32con
    import win32event
    import win32gui
    import winerror
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    WINDOWS_AVAILABLE = True
except ImportError as import_error:
    logging.critical(f"OS Adapter: Win32 dependencies missing. {import_error}")
    WINDOWS_AVAILABLE = False


class OSInterface(ABC):
    """
    Abstract Base Class defining the contract for OS interactions.
    This allows for potential future cross-platform support or mocking in tests.
    """

    @abstractmethod
    def get_system_volume(self) -> float:
        """
        Retrieves the current system master volume.

        Returns:
            float: Volume level normalized between 0.0 and 1.0.
        """
        pass

    @abstractmethod
    def set_system_volume(self, level: float) -> None:
        """
        Sets the system master volume.

        Args:
            level (float): Target volume level normalized between 0.0 and 1.0.
        """
        pass

    @abstractmethod
    def mute_system_volume(self) -> float:
        """
        Mutes the system volume.

        Returns:
            float: The volume level before muting (useful for restoring state).
        """
        pass

    @abstractmethod
    def unmute_system_volume(self, original_level: float) -> None:
        """
        Restores the system volume to a specific level.

        Args:
            original_level (float): The volume level to restore.
        """
        pass

    @abstractmethod
    def find_window_handle(self, title: str) -> Optional[int]:
        """
        Finds a native window handle (HWND) by its title.

        Args:
            title (str): The exact title of the window to find.

        Returns:
            Optional[int]: The window handle if found, else None.
        """
        pass

    @abstractmethod
    def is_window_visible(self, window_handle: int) -> bool:
        """
        Checks if a specific window is currently visible on screen.

        Args:
            window_handle (int): The native handle of the window.

        Returns:
            bool: True if visible, False otherwise.
        """
        pass

    @abstractmethod
    def hide_window(self, window_handle: int) -> None:
        """
        Hides a specific window from the user view.

        Args:
            window_handle (int): The native handle of the window.
        """
        pass

    @abstractmethod
    def show_window(
        self, window_handle: int, activate: bool = False, always_on_top: bool = False
    ) -> None:
        """
        Shows a specific window with optional activation and Z-order positioning.

        Args:
            window_handle (int): The native handle of the window.
            activate (bool): If True, brings the window to the foreground and gives focus.
            always_on_top (bool): If True, sets the window to remain above all others.
        """
        pass

    @abstractmethod
    def set_window_topmost(self, window_handle: int, is_topmost: bool) -> None:
        """
        Modifies the "Always on Top" status of a window without changing visibility.

        Args:
            window_handle (int): The native handle of the window.
            is_topmost (bool): True to enable topmost, False to disable.
        """
        pass

    @abstractmethod
    def create_single_instance_mutex(self, mutex_id: str) -> Any:
        """
        Creates a named system mutex to prevent multiple instances of the application.

        Args:
            mutex_id (str): A unique string identifier for the mutex.

        Returns:
            Any: The mutex handle object.

        Raises:
            RuntimeError: If the application instance is already running.
        """
        pass

    @abstractmethod
    def move_window(self, window_handle: int, x: int, y: int) -> None:
        """
        Moves a specific window to absolute (x, y) screen coordinates.

        Args:
            window_handle (int): The native handle of the window.
            x (int): X coordinate.
            y (int): Y coordinate.
        """
        pass


class WindowsAdapter(OSInterface):
    """
    Concrete implementation of OSInterface for Microsoft Windows.
    Uses 'pycaw' for audio control and 'pywin32' for window management.
    """

    def __init__(self) -> None:
        """Initialize the adapter and verify OS dependencies."""
        if not WINDOWS_AVAILABLE:
            logging.critical(
                "WindowsAdapter initialized without required Win32 libraries."
            )
        self._mutex_handle: Optional[Any] = None

    # --- AUDIO MANAGEMENT (PyCaw) ---

    def _get_audio_endpoint(self) -> Optional[IAudioEndpointVolume]:
        """
        Internal helper to initialize the Audio Endpoint Volume COM interface.

        Returns:
            Optional[IAudioEndpointVolume]: The COM interface or None on failure.
        """
        try:
            speakers = AudioUtilities.GetSpeakers()
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return interface.QueryInterface(IAudioEndpointVolume)
        except Exception as error:
            logging.error(f"Failed to access Windows Audio Endpoint: {error}")
            return None

    def get_system_volume(self) -> float:
        """Retrieves current master volume (0.0 - 1.0)."""
        endpoint = self._get_audio_endpoint()
        if endpoint:
            # Type ignore: PyCaw stubs are often incomplete
            return endpoint.GetMasterVolumeLevelScalar()  # type: ignore
        return 1.0

    def set_system_volume(self, level: float) -> None:
        """Sets master volume (0.0 - 1.0)."""
        endpoint = self._get_audio_endpoint()
        if endpoint:
            endpoint.SetMasterVolumeLevelScalar(level, None)  # type: ignore

    def mute_system_volume(self) -> float:
        """Mutes system volume and returns the previous level."""
        endpoint = self._get_audio_endpoint()
        if not endpoint:
            return 1.0

        current_volume = endpoint.GetMasterVolumeLevelScalar()  # type: ignore
        endpoint.SetMasterVolumeLevelScalar(0.0, None)  # type: ignore
        return current_volume

    def unmute_system_volume(self, original_level: float) -> None:
        """Restores system volume to the specified level."""
        endpoint = self._get_audio_endpoint()
        if endpoint:
            endpoint.SetMasterVolumeLevelScalar(original_level, None)  # type: ignore

    # --- WINDOW MANAGEMENT (Win32Gui) ---

    def find_window_handle(self, title: str) -> Optional[int]:
        """Finds a window by exact title match."""
        try:
            handle = win32gui.FindWindow(None, title)
            return handle if handle != 0 else None
        except Exception:
            # Silent failure expected if window doesn't exist
            return None

    def is_window_visible(self, window_handle: Optional[int]) -> bool:
        """Checks window visibility safely."""
        if not window_handle:
            return False
        try:
            return bool(win32gui.IsWindowVisible(window_handle))
        except Exception as error:
            logging.error(f"Error checking window visibility: {error}")
            return False

    def hide_window(self, window_handle: Optional[int]) -> None:
        """Hides the window."""
        if window_handle:
            try:
                win32gui.ShowWindow(window_handle, win32con.SW_HIDE)
            except Exception as error:
                logging.error(f"Error hiding window: {error}")

    def move_window(self, window_handle: Optional[int], x: int, y: int) -> None:
        """Moves window to (x,y) without resizing or activating."""
        if not window_handle:
            return
        try:
            # Flags: SWP_NOSIZE (retain size) | SWP_NOZORDER (retain Z-pos) | SWP_NOACTIVATE (no focus)
            flags = (
                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )
            win32gui.SetWindowPos(window_handle, 0, x, y, 0, 0, flags)
        except Exception as error:
            logging.error(f"Error moving window: {error}")

    def show_window(
        self,
        window_handle: Optional[int],
        activate: bool = False,
        always_on_top: bool = False,
    ) -> None:
        """Shows window with configurable activation and Z-order."""
        if not window_handle:
            return

        try:
            # 1. Determine Visibility Command
            show_cmd = win32con.SW_SHOW if activate else win32con.SW_SHOWNOACTIVATE
            win32gui.ShowWindow(window_handle, show_cmd)

            # 2. Determine Z-Order
            hwnd_insert_after = (
                win32con.HWND_TOPMOST if always_on_top else win32con.HWND_NOTOPMOST
            )

            # 3. Determine Positioning Flags
            # SWP_NOMOVE | SWP_NOSIZE -> only changing Z-order and Activation
            pos_flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            if not activate:
                pos_flags |= win32con.SWP_NOACTIVATE

            win32gui.SetWindowPos(
                window_handle, hwnd_insert_after, 0, 0, 0, 0, pos_flags
            )

            # 4. Force Foreground if requested
            if always_on_top and activate:
                try:
                    win32gui.SetForegroundWindow(window_handle)
                except Exception as fg_error:
                    # Ignore harmless error 0, log others
                    win_error = getattr(fg_error, "winerror", None)
                    if win_error != 0:
                        logging.warning(f"SetForegroundWindow failed: {fg_error}")

        except Exception as error:
            logging.error(f"Error in show_window: {error}")

    def set_window_topmost(
        self, window_handle: Optional[int], is_topmost: bool
    ) -> None:
        """Sets window Z-order without showing/hiding it."""
        if not window_handle:
            return

        try:
            hwnd_insert_after = (
                win32con.HWND_TOPMOST if is_topmost else win32con.HWND_NOTOPMOST
            )
            flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
            win32gui.SetWindowPos(window_handle, hwnd_insert_after, 0, 0, 0, 0, flags)
        except Exception as error:
            logging.error(f"Error setting topmost: {error}")

    # --- SYSTEM / MUTEX ---

    def create_single_instance_mutex(self, mutex_id: str) -> Any:
        """
        Enforces single application instance using a named Mutex.
        """
        try:
            self._mutex_handle = win32event.CreateMutex(None, 1, mutex_id)  # type: ignore
            last_error = win32api.GetLastError()

            if last_error == winerror.ERROR_ALREADY_EXISTS:
                raise RuntimeError("Another instance of the application is running.")

            return self._mutex_handle

        except Exception as error:
            # Re-raise RuntimeError if it's our own detection, otherwise log
            if isinstance(error, RuntimeError):
                raise
            logging.critical(f"Failed to create system mutex: {error}")
            return None
