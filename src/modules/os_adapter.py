import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

# Conditional imports to prevent linter errors on Linux/Mac
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
    # Debug print to identify missing dependencies
    print(f"DETAILED IMPORT ERROR: {import_error}")
    WINDOWS_AVAILABLE = False


class OSInterface(ABC):
    """
    Abstract interface defining Operating System interactions.
    Decouples business logic from the underlying OS (Windows/Linux/Mac).
    """

    @abstractmethod
    def get_system_volume(self) -> float:
        """
        Retrieves the current system master volume.

        Returns:
            float: Volume level between 0.0 and 1.0.
        """
        pass

    @abstractmethod
    def set_system_volume(self, level: float) -> None:
        """
        Sets the system master volume.

        Args:
            level (float): Target volume level between 0.0 and 1.0.
        """
        pass

    @abstractmethod
    def mute_system_volume(self) -> float:
        """
        Mutes the system volume.

        Returns:
            float: The volume level before muting (to allow restoring).
        """
        pass

    @abstractmethod
    def unmute_system_volume(self, original_level: float) -> None:
        """
        Restores the system volume to a specific level (unmute).

        Args:
            original_level (float): The volume level to restore.
        """
        pass

    @abstractmethod
    def find_window_handle(self, title: str) -> Optional[int]:
        """
        Finds a window handle (HWND) by its title.

        Args:
            title (str): The exact title of the window.

        Returns:
            Optional[int]: The window handle if found, else None.
        """
        pass

    @abstractmethod
    def is_window_visible(self, window_handle: int) -> bool:
        """
        Checks if a specific window is currently visible.

        Args:
            window_handle (int): The handle of the window.

        Returns:
            bool: True if visible, False otherwise.
        """
        pass

    @abstractmethod
    def hide_window(self, window_handle: int) -> None:
        """
        Hides a specific window.

        Args:
            window_handle (int): The handle of the window to hide.
        """
        pass

    @abstractmethod
    def show_window(
        self, window_handle: int, activate: bool = False, always_on_top: bool = False
    ) -> None:
        """
        Shows a specific window with optional activation and Z-order positioning.

        Args:
            window_handle (int): The handle of the window to show.
            activate (bool): Whether to bring the window to the foreground and activate it.
            always_on_top (bool): Whether to keep the window above all others.
        """
        pass

    @abstractmethod
    def set_window_topmost(self, window_handle: int, is_topmost: bool) -> None:
        """
        Modifies the "Always on Top" status of a window.

        Args:
            window_handle (int): The handle of the window.
            is_topmost (bool): True to make it always on top, False to reset.
        """
        pass

    @abstractmethod
    def create_single_instance_mutex(self, mutex_id: str) -> Any:
        """
        Creates a named mutex to prevent multiple instances of the application.

        Args:
            mutex_id (str): A unique string identifier for the mutex.

        Returns:
            Any: The mutex handle.

        Raises:
            RuntimeError: If the application is already running.
        """
        pass

    @abstractmethod
    def move_window(self, window_handle: int, x: int, y: int) -> None:
        """
        Moves a specific window to (x, y) coordinates.
        """
        pass


class WindowsAdapter(OSInterface):
    """Implementation of system calls specifically for Microsoft Windows."""

    def __init__(self) -> None:
        if not WINDOWS_AVAILABLE:
            logging.critical("Win32 libraries (pywin32, pycaw) are missing.")
        self._mutex_handle: Optional[Any] = None

    # --- AUDIO (PyCaw) ---

    def _get_volume_interface(self) -> Optional[IAudioEndpointVolume]:
        """
        Helper to initialize the Audio Endpoint Volume interface.

        Returns:
            Optional[IAudioEndpointVolume]: The COM interface or None on failure.
        """
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return interface.QueryInterface(IAudioEndpointVolume)
        except Exception as error:
            logging.error(f"Windows audio interface error: {error}")
            return None

    def get_system_volume(self) -> float:
        volume_interface = self._get_volume_interface()
        if volume_interface:
            return volume_interface.GetMasterVolumeLevelScalar()  # type: ignore
        return 1.0

    def set_system_volume(self, level: float) -> None:
        volume_interface = self._get_volume_interface()
        if volume_interface:
            volume_interface.SetMasterVolumeLevelScalar(level, None)  # type: ignore

    def mute_system_volume(self) -> float:
        volume_interface = self._get_volume_interface()
        if not volume_interface:
            return 1.0

        original_volume = volume_interface.GetMasterVolumeLevelScalar()  # type: ignore
        volume_interface.SetMasterVolumeLevelScalar(0.0, None)  # type: ignore
        return original_volume

    def unmute_system_volume(self, original_level: float) -> None:
        volume_interface = self._get_volume_interface()
        if volume_interface:
            volume_interface.SetMasterVolumeLevelScalar(original_level, None)  # type: ignore

    # --- WINDOWS (Win32Gui) ---

    def find_window_handle(self, title: str) -> Optional[int]:
        try:
            window_handle = win32gui.FindWindow(None, title)
            return window_handle if window_handle != 0 else None
        except Exception:
            return None

    def is_window_visible(self, window_handle: Optional[int]) -> bool:
        if not window_handle:
            return False
        return bool(win32gui.IsWindowVisible(window_handle))

    def hide_window(self, window_handle: Optional[int]) -> None:
        if window_handle:
            win32gui.ShowWindow(window_handle, win32con.SW_HIDE)

    def move_window(self, window_handle: Optional[int], x: int, y: int) -> None:
        if not window_handle:
            return
        try:
            # Flags: SWP_NOSIZE (taille fixe) | SWP_NOZORDER (ordre Z fixe) | SWP_NOACTIVATE (pas de focus)
            flags = (
                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )
            win32gui.SetWindowPos(window_handle, 0, x, y, 0, 0, flags)
        except Exception as error:
            logging.error(f"Move window error: {error}")

    def show_window(
        self,
        window_handle: Optional[int],
        activate: bool = False,
        always_on_top: bool = False,
    ) -> None:
        if not window_handle:
            return

        # Determine show command
        show_command = win32con.SW_SHOW if activate else win32con.SW_SHOWNOACTIVATE
        win32gui.ShowWindow(window_handle, show_command)

        # Determine Z-order
        z_order_flag = (
            win32con.HWND_TOPMOST if always_on_top else win32con.HWND_NOTOPMOST
        )

        # Determine positioning flags
        position_flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
        if not activate:
            position_flags |= win32con.SWP_NOACTIVATE

        try:
            win32gui.SetWindowPos(
                window_handle, z_order_flag, 0, 0, 0, 0, position_flags
            )

            if always_on_top and activate:
                try:
                    win32gui.SetForegroundWindow(window_handle)
                except Exception as error:
                    win_error_code = getattr(error, "winerror", None)
                    if win_error_code == 0:
                        pass
                    else:
                        logging.warning(f"SetForegroundWindow warning: {error}")

        except Exception as error:
            logging.error(f"Window positioning error: {error}")

    def set_window_topmost(
        self, window_handle: Optional[int], is_topmost: bool
    ) -> None:
        if not window_handle:
            return

        hwnd_insert_after = (
            win32con.HWND_TOPMOST if is_topmost else win32con.HWND_NOTOPMOST
        )

        win32gui.SetWindowPos(
            window_handle,
            hwnd_insert_after,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )

    # --- SYSTEM ---

    def create_single_instance_mutex(self, mutex_id: str) -> Any:
        self._mutex_handle = win32event.CreateMutex(None, 1, mutex_id)  # type: ignore

        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            raise RuntimeError("Application is already running")

        return self._mutex_handle
