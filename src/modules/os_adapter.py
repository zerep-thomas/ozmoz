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
import re
from abc import ABC, abstractmethod
from enum import IntFlag
from typing import Final, NewType, Protocol

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


# --- Type Definitions ---
# NewType for type safety - prevents accidental int/HWND confusion
WindowHandle = NewType("WindowHandle", int)

# --- Constants ---
# Default volume level when audio endpoint is unavailable
DEFAULT_FALLBACK_VOLUME: Final[float] = 1.0

# Volume level bounds for validation
MIN_VOLUME_LEVEL: Final[float] = 0.0
MAX_VOLUME_LEVEL: Final[float] = 1.0

# Win32 error code for mutex already exists
ERROR_ALREADY_EXISTS: Final[int] = winerror.ERROR_ALREADY_EXISTS

# Maximum length for window title and mutex ID (prevent DOS)
MAX_WINDOW_TITLE_LENGTH: Final[int] = 256
MAX_MUTEX_ID_LENGTH: Final[int] = 128


# Win32 SetWindowPos flags as documented enums for clarity
class WindowPosFlags(IntFlag):
    """
    Flags for SetWindowPos Win32 API.

    See: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos
    """

    NOSIZE = win32con.SWP_NOSIZE  # Retain current size
    NOMOVE = win32con.SWP_NOMOVE  # Retain current position
    NOZORDER = win32con.SWP_NOZORDER  # Retain current Z-order
    NOACTIVATE = win32con.SWP_NOACTIVATE  # Do not activate window


class ShowWindowCommand(IntFlag):
    """Show window commands for Win32 ShowWindow API."""

    HIDE = win32con.SW_HIDE
    SHOW = win32con.SW_SHOW
    SHOW_NO_ACTIVATE = win32con.SW_SHOWNOACTIVATE
    RESTORE = win32con.SW_RESTORE


class WindowZOrder(IntFlag):
    """Z-order insertion positions for SetWindowPos."""

    TOPMOST = win32con.HWND_TOPMOST
    NOT_TOPMOST = win32con.HWND_NOTOPMOST


# --- Custom Exceptions ---
class OSAdapterError(Exception):
    """Base exception for OS adapter operations."""


class AudioEndpointError(OSAdapterError):
    """Raised when audio endpoint operations fail."""


class WindowOperationError(OSAdapterError):
    """Raised when window operations fail."""


class MutexError(OSAdapterError):
    """Raised when mutex operations fail."""


class ApplicationAlreadyRunningError(MutexError):
    """Raised when another instance of the application is detected."""


# --- Validation Helpers ---
def validate_volume_level(level: float) -> None:
    """
    Validate volume level is within acceptable range.

    Args:
        level: Volume level to validate.

    Raises:
        ValueError: If level is outside [0.0, 1.0] range.
    """
    if not (MIN_VOLUME_LEVEL <= level <= MAX_VOLUME_LEVEL):
        raise ValueError(
            f"Volume level must be between {MIN_VOLUME_LEVEL} and {MAX_VOLUME_LEVEL}, "
            f"got {level}"
        )


def validate_window_title(title: str) -> None:
    """
    Validate window title string for safety.

    Args:
        title: Window title to validate.

    Raises:
        ValueError: If title is invalid (too long, contains null bytes, etc.).
    """
    if not title:
        raise ValueError("Window title cannot be empty")

    if len(title) > MAX_WINDOW_TITLE_LENGTH:
        raise ValueError(
            f"Window title exceeds maximum length of {MAX_WINDOW_TITLE_LENGTH} characters"
        )

    if "\x00" in title:
        raise ValueError("Window title cannot contain null bytes")


def validate_mutex_id(mutex_id: str) -> None:
    """
    Validate mutex identifier for safety.

    Mutex IDs must be valid Windows kernel object names.

    Args:
        mutex_id: Mutex identifier to validate.

    Raises:
        ValueError: If mutex_id is invalid.
    """
    if not mutex_id:
        raise ValueError("Mutex ID cannot be empty")

    if len(mutex_id) > MAX_MUTEX_ID_LENGTH:
        raise ValueError(
            f"Mutex ID exceeds maximum length of {MAX_MUTEX_ID_LENGTH} characters"
        )

    # Windows kernel object names cannot contain backslashes
    if "\\" in mutex_id:
        raise ValueError("Mutex ID cannot contain backslash characters")

    if "\x00" in mutex_id:
        raise ValueError("Mutex ID cannot contain null bytes")

    # Alphanumeric, hyphens, underscores only for safety
    if not re.match(r"^[A-Za-z0-9_\-]+$", mutex_id):
        raise ValueError(
            "Mutex ID must contain only alphanumeric characters, hyphens, and underscores"
        )


# --- Protocol Definitions ---
class AudioEndpointProtocol(Protocol):
    """
    Protocol for Windows Audio Endpoint Volume interface.

    This mirrors the pycaw IAudioEndpointVolume interface
    for better type checking.
    """

    def GetMasterVolumeLevelScalar(self) -> float:
        """Get master volume level (0.0 - 1.0)."""
        ...

    def SetMasterVolumeLevelScalar(self, level: float, context: object) -> None:
        """Set master volume level (0.0 - 1.0)."""
        ...


# --- Abstract Base Class ---
class OSInterface(ABC):
    """
    Abstract Base Class defining the contract for OS interactions.

    This allows for potential future cross-platform support or mocking in tests.

    Example:
        >>> os_adapter = WindowsAdapter()
        >>> original_volume = os_adapter.mute_system_volume()
        >>> # ... do work ...
        >>> os_adapter.unmute_system_volume(original_volume)
    """

    @abstractmethod
    def get_system_volume(self) -> float:
        """
        Retrieve the current system master volume.

        Returns:
            Volume level normalized between 0.0 and 1.0.

        Raises:
            AudioEndpointError: If volume retrieval fails.
        """
        pass

    @abstractmethod
    def set_system_volume(self, level: float) -> None:
        """
        Set the system master volume.

        Args:
            level: Target volume level normalized between 0.0 and 1.0.

        Raises:
            ValueError: If level is outside valid range.
            AudioEndpointError: If volume setting fails.
        """
        pass

    @abstractmethod
    def mute_system_volume(self) -> float:
        """
        Mute the system volume.

        Returns:
            The volume level before muting (for later restoration).

        Raises:
            AudioEndpointError: If muting operation fails.

        Example:
            >>> adapter = WindowsAdapter()
            >>> original = adapter.mute_system_volume()
            >>> # System is now muted
            >>> adapter.unmute_system_volume(original)
        """
        pass

    @abstractmethod
    def unmute_system_volume(self, original_level: float) -> None:
        """
        Restore the system volume to a specific level.

        Args:
            original_level: The volume level to restore.

        Raises:
            ValueError: If level is outside valid range.
            AudioEndpointError: If unmuting operation fails.
        """
        pass

    @abstractmethod
    def find_window_handle(self, title: str) -> WindowHandle | None:
        """
        Find a native window handle (HWND) by its title.

        Args:
            title: The exact title of the window to find.

        Returns:
            The window handle if found, None otherwise.

        Raises:
            ValueError: If title is invalid.

        Example:
            >>> hwnd = adapter.find_window_handle("Ozmoz")
            >>> if hwnd:
            ...     adapter.show_window(hwnd)
        """
        pass

    @abstractmethod
    def is_window_visible(self, window_handle: WindowHandle) -> bool:
        """
        Check if a specific window is currently visible on screen.

        Args:
            window_handle: The native handle of the window.

        Returns:
            True if visible, False otherwise.
        """
        pass

    @abstractmethod
    def hide_window(self, window_handle: WindowHandle) -> None:
        """
        Hide a specific window from the user view.

        Args:
            window_handle: The native handle of the window.

        Raises:
            WindowOperationError: If hide operation fails.
        """
        pass

    @abstractmethod
    def show_window(
        self,
        window_handle: WindowHandle,
        activate: bool = False,
        always_on_top: bool = False,
    ) -> None:
        """
        Show a specific window with optional activation and Z-order positioning.

        Args:
            window_handle: The native handle of the window.
            activate: If True, brings window to foreground and gives focus.
            always_on_top: If True, sets window to remain above all others.

        Raises:
            WindowOperationError: If show operation fails.
        """
        pass

    @abstractmethod
    def set_window_topmost(self, window_handle: WindowHandle, is_topmost: bool) -> None:
        """
        Modify the "Always on Top" status without changing visibility.

        Args:
            window_handle: The native handle of the window.
            is_topmost: True to enable topmost, False to disable.

        Raises:
            WindowOperationError: If topmost operation fails.
        """
        pass

    @abstractmethod
    def create_single_instance_mutex(self, mutex_id: str) -> object:
        """
        Create a named system mutex to prevent multiple instances.

        Args:
            mutex_id: A unique string identifier for the mutex.
                     Must contain only alphanumeric, hyphens, underscores.

        Returns:
            The mutex handle object.

        Raises:
            ValueError: If mutex_id is invalid.
            ApplicationAlreadyRunningError: If instance already running.
            MutexError: If mutex creation fails for other reasons.

        Example:
            >>> try:
            ...     mutex = adapter.create_single_instance_mutex("Ozmoz-Mutex-v1")
            ... except ApplicationAlreadyRunningError:
            ...     print("App already running!")
            ...     sys.exit(1)
        """
        pass

    @abstractmethod
    def move_window(self, window_handle: WindowHandle, x: int, y: int) -> None:
        """
        Move a specific window to absolute (x, y) screen coordinates.

        Args:
            window_handle: The native handle of the window.
            x: X coordinate in pixels.
            y: Y coordinate in pixels.

        Raises:
            WindowOperationError: If move operation fails.
        """
        pass


# --- Windows Implementation ---
class WindowsAdapter(OSInterface):
    """
    Concrete implementation of OSInterface for Microsoft Windows.

    Uses pycaw (Core Audio APIs) for volume control and pywin32 for
    window management via Win32 APIs.

    Thread Safety:
        Individual methods are thread-safe for Win32 API calls.
        Audio endpoint is retrieved fresh for each operation to avoid
        COM threading issues.
    """

    def __init__(self) -> None:
        """
        Initialize the Windows adapter.

        Raises:
            OSAdapterError: If required Win32 libraries are not available.
        """
        if not WINDOWS_AVAILABLE:
            raise OSAdapterError(
                "WindowsAdapter requires pywin32 and pycaw libraries. "
                "Install with: pip install pywin32 pycaw"
            )

        self._mutex_handle: object | None = None
        self._logger = logging.getLogger(__name__)

    # --- AUDIO MANAGEMENT (PyCaw) ---

    def _get_audio_endpoint(self) -> AudioEndpointProtocol:
        """
        Initialize the Audio Endpoint Volume COM interface.

        Returns:
            The COM interface for audio endpoint volume control.

        Raises:
            AudioEndpointError: If audio endpoint cannot be accessed.

        Note:
            This is called fresh for each operation to avoid COM
            threading issues with pywin32.
        """
        try:
            speakers = AudioUtilities.GetSpeakers()
            if speakers is None:
                raise AudioEndpointError("No audio output devices found")

            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)

            endpoint = interface.QueryInterface(IAudioEndpointVolume)
            if endpoint is None:
                raise AudioEndpointError("Failed to query audio endpoint interface")

            return endpoint  # type: ignore[return-value]

        except AudioEndpointError:
            raise
        except Exception as error:
            self._logger.error(
                "Failed to access Windows Audio Endpoint",
                extra={"error": str(error)},
                exc_info=True,
            )
            raise AudioEndpointError(
                f"Cannot access audio endpoint: {error}"
            ) from error

    def get_system_volume(self) -> float:
        """
        Retrieve current master volume level.

        Returns:
            Volume level between 0.0 and 1.0.

        Raises:
            AudioEndpointError: If volume cannot be retrieved.
        """
        try:
            endpoint = self._get_audio_endpoint()
            # PyCaw type stubs are incomplete - type ignore is safe here
            volume = endpoint.GetMasterVolumeLevelScalar()  # type: ignore[no-untyped-call]

            # Validate returned value
            if not isinstance(volume, (int, float)):
                raise AudioEndpointError(
                    f"Audio endpoint returned invalid type: {type(volume)}"
                )

            return float(volume)

        except AudioEndpointError:
            raise
        except Exception as error:
            self._logger.error(
                "Get volume failed",
                extra={"error": str(error)},
                exc_info=True,
            )
            raise AudioEndpointError(f"Failed to get volume: {error}") from error

    def set_system_volume(self, level: float) -> None:
        """
        Set master volume level.

        Args:
            level: Volume level between 0.0 and 1.0.

        Raises:
            ValueError: If level is outside valid range.
            AudioEndpointError: If volume cannot be set.
        """
        validate_volume_level(level)

        try:
            endpoint = self._get_audio_endpoint()
            # Second parameter is event context (not used)
            endpoint.SetMasterVolumeLevelScalar(level, None)  # type: ignore[no-untyped-call]

        except AudioEndpointError:
            raise
        except Exception as error:
            self._logger.error(
                "Set volume failed",
                extra={"level": level, "error": str(error)},
                exc_info=True,
            )
            raise AudioEndpointError(f"Failed to set volume: {error}") from error

    def mute_system_volume(self) -> float:
        """
        Mute system volume and return the previous level.

        Returns:
            Volume level before muting.

        Raises:
            AudioEndpointError: If mute operation fails.
        """
        try:
            endpoint = self._get_audio_endpoint()
            current_volume = endpoint.GetMasterVolumeLevelScalar()  # type: ignore[no-untyped-call]

            if not isinstance(current_volume, (int, float)):
                raise AudioEndpointError("Invalid volume value from endpoint")

            endpoint.SetMasterVolumeLevelScalar(0.0, None)  # type: ignore[no-untyped-call]

            self._logger.debug(
                "System muted", extra={"previous_volume": current_volume}
            )

            return float(current_volume)

        except AudioEndpointError:
            raise
        except Exception as error:
            self._logger.error(
                "Mute operation failed",
                extra={"error": str(error)},
                exc_info=True,
            )
            raise AudioEndpointError(f"Failed to mute: {error}") from error

    def unmute_system_volume(self, original_level: float) -> None:
        """
        Restore system volume to specified level.

        Args:
            original_level: Volume level to restore.

        Raises:
            ValueError: If level is outside valid range.
            AudioEndpointError: If unmute operation fails.
        """
        validate_volume_level(original_level)

        try:
            endpoint = self._get_audio_endpoint()
            endpoint.SetMasterVolumeLevelScalar(original_level, None)  # type: ignore[no-untyped-call]

            self._logger.debug(
                "System unmuted", extra={"restored_volume": original_level}
            )

        except AudioEndpointError:
            raise
        except Exception as error:
            self._logger.error(
                "Unmute operation failed",
                extra={"target_level": original_level, "error": str(error)},
                exc_info=True,
            )
            raise AudioEndpointError(f"Failed to unmute: {error}") from error

    # --- WINDOW MANAGEMENT (Win32GUI) ---

    def find_window_handle(self, title: str) -> WindowHandle | None:
        """
        Find a window by exact title match.

        Args:
            title: Exact window title to search for.

        Returns:
            Window handle if found, None otherwise.

        Raises:
            ValueError: If title is invalid.
        """
        validate_window_title(title)

        try:
            # FindWindow returns 0 if window not found
            handle = win32gui.FindWindow(None, title)

            if handle == 0:
                return None

            return WindowHandle(handle)

        except Exception as error:
            self._logger.warning(
                "Window search failed",
                extra={"title": title, "error": str(error)},
            )
            # Return None for not found - this is expected behavior
            return None

    def is_window_visible(self, window_handle: WindowHandle) -> bool:
        """
        Check window visibility status.

        Args:
            window_handle: Window handle to check.

        Returns:
            True if window is visible, False otherwise.
        """
        try:
            return bool(win32gui.IsWindowVisible(window_handle))

        except Exception as error:
            self._logger.warning(
                "Visibility check failed",
                extra={"hwnd": window_handle, "error": str(error)},
            )
            # Assume invisible on error
            return False

    def hide_window(self, window_handle: WindowHandle) -> None:
        """
        Hide the specified window.

        Args:
            window_handle: Window handle to hide.

        Raises:
            WindowOperationError: If hide operation fails.
        """
        try:
            win32gui.ShowWindow(window_handle, ShowWindowCommand.HIDE)
            self._logger.debug("Window hidden", extra={"hwnd": window_handle})

        except Exception as error:
            self._logger.error(
                "Hide window failed",
                extra={"hwnd": window_handle, "error": str(error)},
                exc_info=True,
            )
            raise WindowOperationError(f"Failed to hide window: {error}") from error

    def move_window(self, window_handle: WindowHandle, x: int, y: int) -> None:
        """
        Move window to specified coordinates without resizing or activating.

        Args:
            window_handle: Window handle to move.
            x: Target X coordinate in pixels.
            y: Target Y coordinate in pixels.

        Raises:
            WindowOperationError: If move operation fails.
        """
        try:
            # Flags: Retain size, Z-order, and don't activate
            flags = (
                WindowPosFlags.NOSIZE
                | WindowPosFlags.NOZORDER
                | WindowPosFlags.NOACTIVATE
            )

            # SetWindowPos(hwnd, insertAfter, x, y, width, height, flags)
            # insertAfter=0 is ignored due to NOZORDER flag
            # width=0, height=0 are ignored due to NOSIZE flag
            win32gui.SetWindowPos(window_handle, 0, x, y, 0, 0, flags)

            self._logger.debug(
                "Window moved", extra={"hwnd": window_handle, "x": x, "y": y}
            )

        except Exception as error:
            self._logger.error(
                "Move window failed",
                extra={"hwnd": window_handle, "x": x, "y": y, "error": str(error)},
                exc_info=True,
            )
            raise WindowOperationError(f"Failed to move window: {error}") from error

    def show_window(
        self,
        window_handle: WindowHandle,
        activate: bool = False,
        always_on_top: bool = False,
    ) -> None:
        """
        Show window with configurable activation and Z-order.

        Args:
            window_handle: Window handle to show.
            activate: If True, bring window to foreground with focus.
            always_on_top: If True, set window as topmost (above all others).

        Raises:
            WindowOperationError: If show operation fails.
        """
        try:
            # Step 1: Show the window (with or without activation)
            show_cmd = (
                ShowWindowCommand.SHOW
                if activate
                else ShowWindowCommand.SHOW_NO_ACTIVATE
            )
            win32gui.ShowWindow(window_handle, show_cmd)

            # Step 2: Configure Z-order (topmost vs normal)
            z_order = (
                WindowZOrder.TOPMOST if always_on_top else WindowZOrder.NOT_TOPMOST
            )

            # Step 3: Build SetWindowPos flags
            # NOMOVE | NOSIZE -> only changing Z-order and activation state
            pos_flags = WindowPosFlags.NOMOVE | WindowPosFlags.NOSIZE
            if not activate:
                pos_flags |= WindowPosFlags.NOACTIVATE

            win32gui.SetWindowPos(
                window_handle,
                z_order,
                0,
                0,
                0,
                0,  # x, y, width, height (ignored due to flags)
                pos_flags,
            )

            # Step 4: Force foreground if both topmost and activate requested
            if always_on_top and activate:
                try:
                    win32gui.SetForegroundWindow(window_handle)
                except Exception as fg_error:
                    # Check if it's a harmless error
                    # Some versions of pywin32 raise error even on success
                    win_error_code = getattr(fg_error, "winerror", None)
                    if win_error_code and win_error_code != 0:
                        self._logger.warning(
                            "SetForegroundWindow failed (non-critical)",
                            extra={
                                "hwnd": window_handle,
                                "error_code": win_error_code,
                                "error": str(fg_error),
                            },
                        )

            self._logger.debug(
                "Window shown",
                extra={
                    "hwnd": window_handle,
                    "activate": activate,
                    "topmost": always_on_top,
                },
            )

        except Exception as error:
            self._logger.error(
                "Show window failed",
                extra={
                    "hwnd": window_handle,
                    "activate": activate,
                    "topmost": always_on_top,
                    "error": str(error),
                },
                exc_info=True,
            )
            raise WindowOperationError(f"Failed to show window: {error}") from error

    def set_window_topmost(self, window_handle: WindowHandle, is_topmost: bool) -> None:
        """
        Set window Z-order without changing visibility or activation.

        Args:
            window_handle: Window handle to modify.
            is_topmost: True to set as topmost, False for normal Z-order.

        Raises:
            WindowOperationError: If topmost operation fails.
        """
        try:
            z_order = WindowZOrder.TOPMOST if is_topmost else WindowZOrder.NOT_TOPMOST

            # Don't move, resize, or activate - only change Z-order
            flags = (
                WindowPosFlags.NOMOVE
                | WindowPosFlags.NOSIZE
                | WindowPosFlags.NOACTIVATE
            )

            win32gui.SetWindowPos(window_handle, z_order, 0, 0, 0, 0, flags)

            self._logger.debug(
                "Window topmost status changed",
                extra={"hwnd": window_handle, "topmost": is_topmost},
            )

        except Exception as error:
            self._logger.error(
                "Set topmost failed",
                extra={
                    "hwnd": window_handle,
                    "topmost": is_topmost,
                    "error": str(error),
                },
                exc_info=True,
            )
            raise WindowOperationError(f"Failed to set topmost: {error}") from error

    # --- SYSTEM / MUTEX ---

    def create_single_instance_mutex(self, mutex_id: str) -> object:
        """
        Enforce single application instance using a named Win32 Mutex.

        Args:
            mutex_id: Unique mutex identifier (alphanumeric, hyphens, underscores only).

        Returns:
            Mutex handle object (must be kept alive for lifetime of app).

        Raises:
            ValueError: If mutex_id is invalid.
            ApplicationAlreadyRunningError: If another instance is running.
            MutexError: If mutex creation fails for other reasons.

        Example:
            >>> adapter = WindowsAdapter()
            >>> try:
            ...     mutex = adapter.create_single_instance_mutex("MyApp-Instance-v1")
            ... except ApplicationAlreadyRunningError:
            ...     sys.exit(1)
        """
        validate_mutex_id(mutex_id)

        try:
            # CreateMutex(lpMutexAttributes, bInitialOwner, lpName)
            # bInitialOwner=1 means we own the mutex immediately
            self._mutex_handle = win32event.CreateMutex(None, 1, mutex_id)  # type: ignore[arg-type]

            # Check if mutex already existed
            last_error = win32api.GetLastError()

            if last_error == ERROR_ALREADY_EXISTS:
                self._logger.warning(
                    "Application instance already running", extra={"mutex_id": mutex_id}
                )
                raise ApplicationAlreadyRunningError(
                    f"Another instance with mutex '{mutex_id}' is already running"
                )

            self._logger.info(
                "Single instance mutex created", extra={"mutex_id": mutex_id}
            )

            return self._mutex_handle

        except ApplicationAlreadyRunningError:
            raise
        except Exception as error:
            self._logger.critical(
                "Mutex creation failed",
                extra={"mutex_id": mutex_id, "error": str(error)},
                exc_info=True,
            )
            raise MutexError(f"Failed to create mutex: {error}") from error
