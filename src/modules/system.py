"""
System Management Module for Ozmoz.

This module handles low-level system interactions including:
- Global Hotkey management via `pynput` with thread-safe execution.
- System Event Bus for decoupled module communication.
- System Power monitoring (Sleep/Resume detection) via Win32 API.
- Application lifecycle and health monitoring.
"""

import logging
import threading
import time
from typing import Callable, Final, Protocol, TypeAlias, cast

# --- Third-Party Imports ---
import win32api
import win32con
import win32gui
from pynput import keyboard as pynput_keyboard
from pynput.keyboard import Key, KeyCode

# --- Local Imports ---
from modules.config import AppState

# --- Type Aliases ---
PynputKey: TypeAlias = Key | KeyCode
EventCallback: TypeAlias = Callable[[object], None]
SimpleCallback: TypeAlias = Callable[[], None]
ConditionCallback: TypeAlias = Callable[[], bool]

# --- Constants ---
# System stabilization delay after resume from sleep (Windows compositor needs time)
SYSTEM_RESUME_STABILIZATION_DELAY_SECONDS: Final[int] = 2

# Win32 error code for "class already exists" during RegisterClass
WIN32_ERROR_CLASS_ALREADY_EXISTS: Final[int] = 1410

# Maximum time allowed for EventBus callbacks before timeout warning
EVENTBUS_CALLBACK_TIMEOUT_SECONDS: Final[float] = 5.0

# Hotkey execution thread name prefix for debugging
HOTKEY_THREAD_NAME_PREFIX: Final[str] = "HotkeyAction"


# --- Protocols for Dependency Injection ---
class AudioManagerProtocol(Protocol):
    """Protocol for audio recording management."""

    def initialize(self) -> bool:
        """Initialize audio subsystem."""
        ...

    def terminate(self) -> None:
        """Cleanup audio resources."""
        ...

    def start_recording(self) -> None:
        """Start audio capture."""
        ...


class TranscriptionManagerProtocol(Protocol):
    """Protocol for audio transcription."""

    def stop_recording_and_transcribe(self) -> None:
        """Stop recording and process audio to text."""
        ...


class WindowManagerProtocol(Protocol):
    """Protocol for GUI window management."""

    def is_visible(self) -> bool:
        """Check if main window is currently visible."""
        ...

    def toggle_main_window_visibility(self) -> None:
        """Show/hide the main application window."""
        ...


class AIGenerationManagerProtocol(Protocol):
    """Protocol for AI text generation."""

    def generate_ai_text(self) -> None:
        """Generate AI-assisted text content."""
        ...


class WebSearchManagerProtocol(Protocol):
    """Protocol for web search operations."""

    def generate_web_search_text(self) -> None:
        """Execute web search and format results."""
        ...


class VisionManagerProtocol(Protocol):
    """Protocol for screen vision analysis."""

    def generate_screen_vision_text(self) -> None:
        """Capture and analyze screen content."""
        ...


class ConfigManagerProtocol(Protocol):
    """Protocol for configuration management."""

    def load_and_parse_remote_config(self) -> None:
        """Fetch and parse remote configuration."""
        ...


# --- Custom Exceptions ---
class HotkeyRegistrationError(Exception):
    """Raised when hotkey registration fails."""


class EventBusError(Exception):
    """Raised when EventBus operations fail."""


class DualModeHotKey:
    """
    Custom wrapper for `pynput` hotkeys to handle both activation (press)
    and deactivation (release) events.

    Standard `pynput.HotKey` only triggers on activation. This class maintains
    state to allow for "Press and Hold" interactions (e.g., Voice Dictation).

    Example:
        >>> hotkey = DualModeHotKey(
        ...     trigger_keys={Key.ctrl_l, KeyCode.from_char('c')},
        ...     on_activate=lambda: print("Pressed"),
        ...     on_deactivate=lambda: print("Released")
        ... )
    """

    def __init__(
        self,
        trigger_keys: set[PynputKey],
        on_activate: SimpleCallback | None = None,
        on_deactivate: SimpleCallback | None = None,
    ) -> None:
        """
        Initialize the DualModeHotKey.

        Args:
            trigger_keys: Set of `pynput` Keys or KeyCodes required to trigger the action.
            on_activate: Callback executed when the combination is fully pressed.
            on_deactivate: Callback executed when the combination is released.
        """
        self._trigger_keys: set[PynputKey] = trigger_keys
        self._currently_pressed_keys: set[PynputKey] = set()
        self._on_activate: SimpleCallback | None = on_activate
        self._on_deactivate: SimpleCallback | None = on_deactivate
        self._is_active: bool = False

    def press(self, key: PynputKey) -> None:
        """
        Update internal state on key press and trigger activation if combination matches.

        Args:
            key: The key pressed event from the listener.
        """
        if key in self._trigger_keys:
            self._currently_pressed_keys.add(key)

            if self._currently_pressed_keys == self._trigger_keys:
                if not self._is_active:
                    self._is_active = True
                    if self._on_activate:
                        self._on_activate()

    def release(self, key: PynputKey) -> None:
        """
        Update internal state on key release and trigger deactivation.

        Args:
            key: The key released event from the listener.
        """
        if key in self._trigger_keys:
            self._currently_pressed_keys.discard(key)

            if self._is_active:
                self._is_active = False
                if self._on_deactivate:
                    self._on_deactivate()


class EventBus:
    """
    Thread-safe Publish/Subscribe mechanism for module decoupling.

    Allows different parts of the application to communicate without direct dependencies.
    Implements timeout protection to prevent callback hangs from blocking the system.

    Example:
        >>> bus = EventBus()
        >>> bus.subscribe("user_action", lambda data: print(f"Received: {data}"))
        >>> bus.publish("user_action", {"action": "click"})
    """

    def __init__(self) -> None:
        """Initialize the EventBus with an empty subscriber list and a thread lock."""
        self._subscribers: dict[str, list[EventCallback]] = {}
        self._lock: threading.Lock = threading.Lock()
        self._logger: logging.Logger = logging.getLogger(__name__)

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """
        Register a callback function for a specific event type.

        Args:
            event_type: The unique identifier for the event.
            callback: The function to call when the event is published.
                     Must accept a single argument (event data).

        Raises:
            EventBusError: If callback is not callable.

        Example:
            >>> bus.subscribe("config_changed", handle_config_update)
        """
        if not callable(callback):
            raise EventBusError(f"Callback for event '{event_type}' is not callable")

        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def publish(self, event_type: str, data: object = None) -> None:
        """
        Broadcast an event to all registered subscribers.

        Executes callbacks with timeout protection. Long-running callbacks
        are logged but do not block subsequent subscribers.

        Args:
            event_type: The unique identifier for the event.
            data: Payload to pass to the subscribers. Defaults to None.

        Example:
            >>> bus.publish("recording_started", {"timestamp": time.time()})
        """
        with self._lock:
            # Create a shallow copy to iterate safely
            callbacks = self._subscribers.get(event_type, [])[:]

        for callback in callbacks:
            try:
                # Execute callback with timeout monitoring
                thread = threading.Thread(
                    target=callback,
                    args=(data,),
                    daemon=True,
                    name=f"EventBus-{event_type}",
                )
                thread.start()
                thread.join(timeout=EVENTBUS_CALLBACK_TIMEOUT_SECONDS)

                if thread.is_alive():
                    self._logger.warning(
                        "EventBus callback timeout exceeded",
                        extra={
                            "event_type": event_type,
                            "timeout_seconds": EVENTBUS_CALLBACK_TIMEOUT_SECONDS,
                        },
                    )

            except Exception as error:
                self._logger.error(
                    "EventBus callback execution failed",
                    extra={
                        "event_type": event_type,
                        "error": str(error),
                        "callback": callback.__name__,
                    },
                    exc_info=True,
                )


class HotkeyManager:
    """
    Manage global system hotkeys using `pynput`.

    Implements a non-blocking execution model where actions and state checks
    are offloaded to separate daemon threads. This is critical to prevent the
    Windows LowLevelHooks from timing out if an action takes too long.

    Thread Safety:
        All hotkey callbacks are executed in isolated daemon threads to prevent
        blocking the main keyboard hook listener.
    """

    # Mapping of common key names to pynput format
    _SPECIAL_KEYS_MAP: Final[dict[str, str]] = {
        # Modifiers
        "ctrl": "<ctrl>",
        "control": "<ctrl>",
        "alt": "<alt>",
        "altgr": "<alt_gr>",
        "shift": "<shift>",
        "cmd": "<cmd>",
        "win": "<cmd>",
        "meta": "<cmd>",
        # Arrows & Navigation
        "up": "<up>",
        "down": "<down>",
        "left": "<left>",
        "right": "<right>",
        "pageup": "<page_up>",
        "pagedown": "<page_down>",
        "home": "<home>",
        "end": "<end>",
        "insert": "<insert>",
        "delete": "<delete>",
        "backspace": "<backspace>",
        "enter": "<enter>",
        "tab": "<tab>",
        "space": "<space>",
        "esc": "<esc>",
        # Locks & System
        "caps_lock": "<caps_lock>",
        "num_lock": "<num_lock>",
        "print_screen": "<print_screen>",
        "scroll_lock": "<scroll_lock>",
        "pause": "<pause>",
    }

    def __init__(
        self,
        app_state: AppState,
        window_manager: WindowManagerProtocol,
        audio_manager: AudioManagerProtocol,
        transcription_manager: TranscriptionManagerProtocol,
    ) -> None:
        """
        Initialize the HotkeyManager.

        Args:
            app_state: Global application state.
            window_manager: Instance of WindowManager.
            audio_manager: Instance of AudioManager.
            transcription_manager: Instance of TranscriptionManager.
        """
        self.app_state: AppState = app_state
        self.window_manager: WindowManagerProtocol = window_manager
        self.audio_manager: AudioManagerProtocol = audio_manager
        self.transcription_manager: TranscriptionManagerProtocol = transcription_manager

        # Circular dependencies injected later via set_managers
        self.ai_generation_manager: AIGenerationManagerProtocol | None = None
        self.web_search_manager: WebSearchManagerProtocol | None = None
        self.vision_manager: VisionManagerProtocol | None = None

        self._listener: pynput_keyboard.Listener | None = None
        self._registered_hotkeys: list[DualModeHotKey | pynput_keyboard.HotKey] = []
        self._logger: logging.Logger = logging.getLogger(__name__)
        self._thread_counter: int = 0

    def set_managers(
        self,
        ai_gen: AIGenerationManagerProtocol,
        web_search: WebSearchManagerProtocol,
        vision: VisionManagerProtocol,
    ) -> None:
        """
        Dependency injection for circular references to service managers.

        Args:
            ai_gen: The AI Generation Manager.
            web_search: The Web Search Manager.
            vision: The Vision Manager.
        """
        self.ai_generation_manager = ai_gen
        self.web_search_manager = web_search
        self.vision_manager = vision

    def _convert_to_pynput_format(self, combination_string: str) -> str:
        """
        Normalize hotkey strings to a `pynput` compatible format.

        Handles modifiers, special keys (arrows, F-keys), and AltGr.
        Validates input to prevent injection attacks.

        Args:
            combination_string: The raw hotkey string from settings (e.g., "ctrl+c").

        Returns:
            The formatted string ready for `pynput`.

        Raises:
            ValueError: If combination contains invalid characters or structure.

        Example:
            >>> self._convert_to_pynput_format("ctrl+alt+down")
            '<ctrl>+<alt>+<down>'
        """
        if not combination_string:
            return ""

        # Validate input: only allow alphanumeric, +, and _
        if not all(c.isalnum() or c in {"+", "_"} for c in combination_string):
            raise ValueError(
                f"Invalid hotkey format: '{combination_string}'. "
                "Only alphanumeric characters, '+', and '_' allowed."
            )

        parts = combination_string.lower().split("+")
        formatted_parts: list[str] = []

        for part in parts:
            part = part.strip()

            if not part:
                continue

            # Check special keys mapping
            if part in self._SPECIAL_KEYS_MAP:
                formatted_parts.append(self._SPECIAL_KEYS_MAP[part])

            # Handle F-keys (F1 through F24)
            elif part.startswith("f") and part[1:].isdigit():
                f_num = int(part[1:])
                if 1 <= f_num <= 24:
                    formatted_parts.append(f"<{part}>")
                else:
                    raise ValueError(f"Invalid function key: {part}")

            # Handle Numpad keys
            elif part.startswith("numpad"):
                if len(part) == 7 and part[-1].isdigit():
                    formatted_parts.append(part[-1])
                else:
                    formatted_parts.append(part)

            # Single character keys
            elif len(part) == 1 and part.isalnum():
                formatted_parts.append(part)

            else:
                raise ValueError(f"Unrecognized hotkey component: {part}")

        return "+".join(formatted_parts)

    def _execute_action_safely(
        self,
        action_callback: SimpleCallback | None,
        condition_callback: ConditionCallback | None = None,
    ) -> None:
        """
        Execute the provided callback in a daemon thread.

        This ensures the keyboard hook returns immediately, maintaining system responsiveness
        even if the action (like starting AI generation) takes time.

        Args:
            action_callback: The function to execute.
            condition_callback: A predicate that must return True for the action to run.
        """

        def worker() -> None:
            try:
                if condition_callback and not condition_callback():
                    return
                if action_callback:
                    action_callback()
            except Exception as error:
                self._logger.error(
                    "Hotkey action execution failed",
                    extra={"error": str(error)},
                    exc_info=True,
                )

        self._thread_counter += 1
        thread = threading.Thread(
            target=worker,
            daemon=True,
            name=f"{HOTKEY_THREAD_NAME_PREFIX}-{self._thread_counter}",
        )
        thread.start()

    def stop_listening(self) -> None:
        """Stop the keyboard listener and clear registered hotkey objects."""
        if self._listener:
            try:
                self._listener.stop()
                self._listener = None
                self._registered_hotkeys.clear()
                self._logger.info("Hotkey listener stopped")
            except Exception as error:
                self._logger.error(
                    "Error stopping hotkey listener", extra={"error": str(error)}
                )

    def register_all(self) -> bool:
        """
        Register all configured hotkeys.

        Handles standard press triggers and press-and-hold logic via `DualModeHotKey`.
        Parses the configuration from `AppState` and sets up the low-level hooks.

        Returns:
            True if registration was successful, False otherwise.

        Raises:
            HotkeyRegistrationError: If critical hotkey setup fails.
        """
        self.stop_listening()
        hotkeys_config = self.app_state.hotkeys

        def is_window_visible() -> bool:
            return self.window_manager.is_visible()

        # --- 1. Toggle Visibility (Simple Press) ---
        if toggle_key := hotkeys_config.get("toggle_visibility"):
            try:
                combo_str = self._convert_to_pynput_format(toggle_key)
                if combo_str:
                    parsed_keys = pynput_keyboard.HotKey.parse(combo_str)
                    hotkey_instance = pynput_keyboard.HotKey(
                        parsed_keys,
                        on_activate=lambda: self._execute_action_safely(
                            self.window_manager.toggle_main_window_visibility
                        ),
                    )
                    self._registered_hotkeys.append(hotkey_instance)
            except ValueError as error:
                self._logger.error(
                    "Invalid toggle visibility hotkey",
                    extra={"hotkey": toggle_key, "error": str(error)},
                )
            except Exception as error:
                self._logger.error(
                    "Error registering visibility hotkey",
                    extra={"error": str(error)},
                    exc_info=True,
                )

        # --- 2. Complex Actions (Press & Release / Hold) ---
        # Structure: Name -> (OnPress, OnRelease, PressCondition, ReleaseCondition)
        actions: dict[
            str,
            tuple[SimpleCallback, SimpleCallback, ConditionCallback, ConditionCallback],
        ] = {
            "record_toggle": (
                self.audio_manager.start_recording,
                self.transcription_manager.stop_recording_and_transcribe,
                lambda: is_window_visible()
                and not self.app_state.audio.is_recording
                and not self.app_state.is_busy,
                lambda: self.app_state.audio.is_recording,
            ),
            "ai_toggle": (
                lambda: (
                    self.ai_generation_manager.generate_ai_text()
                    if self.ai_generation_manager
                    else None
                ),
                lambda: (
                    self.ai_generation_manager.generate_ai_text()
                    if self.ai_generation_manager
                    else None
                ),
                lambda: is_window_visible()
                and not self.app_state.ai_recording
                and not self.app_state.is_busy,
                lambda: self.app_state.ai_recording,
            ),
            "web_search_toggle": (
                lambda: (
                    self.web_search_manager.generate_web_search_text()
                    if self.web_search_manager
                    else None
                ),
                lambda: (
                    self.web_search_manager.generate_web_search_text()
                    if self.web_search_manager
                    else None
                ),
                lambda: is_window_visible()
                and not self.app_state.ai_recording
                and not self.app_state.is_busy,
                lambda: self.app_state.ai_recording,
            ),
            "screen_vision_toggle": (
                lambda: (
                    self.vision_manager.generate_screen_vision_text()
                    if self.vision_manager
                    else None
                ),
                lambda: (
                    self.vision_manager.generate_screen_vision_text()
                    if self.vision_manager
                    else None
                ),
                lambda: is_window_visible()
                and not self.app_state.ai_recording
                and not self.app_state.is_busy,
                lambda: self.app_state.ai_recording,
            ),
        }

        for name, (on_press, on_release, cond_press, cond_release) in actions.items():
            if raw_combo := hotkeys_config.get(name):
                try:
                    formatted_combo = self._convert_to_pynput_format(raw_combo)
                    if formatted_combo:
                        # Parsing returns a list, converting to set for DualModeHotKey logic
                        trigger_keys = set(
                            pynput_keyboard.HotKey.parse(formatted_combo)
                        )

                        # Use default argument binding in lambda to capture current loop values
                        dual_hotkey = DualModeHotKey(
                            trigger_keys=cast(set[PynputKey], trigger_keys),
                            on_activate=lambda a=on_press, c=cond_press: self._execute_action_safely(
                                a, c
                            ),
                            on_deactivate=lambda a=on_release, c=cond_release: self._execute_action_safely(
                                a, c
                            ),
                        )
                        self._registered_hotkeys.append(dual_hotkey)

                except ValueError as error:
                    self._logger.error(
                        f"Invalid hotkey for {name}",
                        extra={"hotkey": raw_combo, "error": str(error)},
                    )
                except Exception as error:
                    self._logger.error(
                        f"Error registering {name}",
                        extra={"error": str(error)},
                        exc_info=True,
                    )

        # --- Listener Initialization ---
        try:

            def for_canonical(
                func: Callable[[PynputKey], None],
            ) -> Callable[[PynputKey | None], None]:
                return lambda k: (
                    func(self._listener.canonical(k))
                    if self._listener and k is not None
                    else None
                )

            self._listener = pynput_keyboard.Listener(
                on_press=for_canonical(self._handle_press),
                on_release=for_canonical(self._handle_release),
            )
            self._listener.start()
            self._logger.info("Hotkey listener started successfully")
            return True

        except Exception as error:
            self._logger.critical(
                "Failed to start hotkey listener",
                extra={"error": str(error)},
                exc_info=True,
            )
            raise HotkeyRegistrationError(
                f"Critical failure in hotkey registration: {error}"
            ) from error

    def _handle_press(self, key: PynputKey) -> None:
        """Dispatch press events to all registered hotkey objects."""
        for hotkey_object in self._registered_hotkeys:
            hotkey_object.press(key)

    def _handle_release(self, key: PynputKey) -> None:
        """Dispatch release events to all registered hotkey objects."""
        for hotkey_object in self._registered_hotkeys:
            hotkey_object.release(key)

    def system_resume_handler(self) -> None:
        """
        Handle system resume events (waking from sleep).

        Re-registers hotkeys to ensure hooks remain active after suspension.
        Includes stabilization delay to allow Windows subsystems to fully resume.
        """
        self._logger.info("System resume detected. Reloading hotkeys...")
        # Wait for system to stabilize (compositor, input subsystem)
        time.sleep(SYSTEM_RESUME_STABILIZATION_DELAY_SECONDS)
        self.register_all()


class SystemHealthManager:
    """
    Monitor application stability without aggressive polling.

    Provides methods to reset subsystems in case of failure without
    requiring full application restart.
    """

    def __init__(
        self,
        app_state: AppState,
        audio_manager: AudioManagerProtocol,
        hotkey_manager: HotkeyManager,
        window_manager: WindowManagerProtocol,
    ) -> None:
        """
        Initialize the SystemHealthManager.

        Args:
            app_state: Global application state.
            audio_manager: Audio subsystem manager.
            hotkey_manager: Input subsystem manager.
            window_manager: GUI window manager.
        """
        self.app_state = app_state
        self.audio_manager = audio_manager
        self.hotkey_manager = hotkey_manager
        self.window_manager = window_manager
        self._logger = logging.getLogger(__name__)

    def _validate_hotkey_state(self) -> bool:
        """
        Checks if the hotkey listener is currently active and running.
        Returns True if healthy, False if the listener is dead or missing.
        """
        try:
            # Access the listener from the hotkey manager
            if self.hotkey_manager and self.hotkey_manager._listener:
                return self.hotkey_manager._listener.is_alive()
            return False
        except Exception as e:
            self._logger.error(f"Error validating hotkey state: {e}")
            return False

    def deep_reset(self) -> bool:
        """
        Perform a soft reset of critical subsystems (Audio & Input).

        Useful if the audio stream hangs or hotkeys stop responding.
        Does not restart the entire application.

        Returns:
            True if reset was successful, False if a critical error occurred.

        Raises:
            RuntimeError: If reset fails and system is in unstable state.
        """
        self._logger.warning("Initiating system soft reset")
        try:
            # Reset application state flags
            self.app_state.is_busy = False
            self.app_state.audio.is_recording = False
            self.app_state.ai_recording = False

            # Reinitialize audio subsystem
            self.audio_manager.terminate()
            self.audio_manager.initialize()

            # Re-register all hotkeys
            self.hotkey_manager.register_all()

            self._logger.info("System soft reset completed successfully")
            return True

        except HotkeyRegistrationError as error:
            self._logger.critical(
                "Critical failure during hotkey re-registration",
                extra={"error": str(error)},
                exc_info=True,
            )
            raise RuntimeError("System in unstable state after reset") from error

        except Exception as error:
            self._logger.critical(
                "Unexpected error during system reset",
                extra={"error": str(error)},
                exc_info=True,
            )
            return False

    def run_hotkey_health_monitor(self, stop_event: threading.Event) -> None:
        """
        Block until the stop event is set.

        Keeps the health monitor thread alive in Passive Mode.
        Future implementations may add active health checks here.

        Args:
            stop_event: Event to signal application shutdown.
        """
        self._logger.info("Hotkey health monitor active (Passive Mode)")
        stop_event.wait()
        self._logger.info("Hotkey health monitor shutting down")


class SystemPowerMonitor:
    """
    Hook into the Windows Message Loop to detect Power Management events (Sleep/Resume).

    Uses a hidden window to receive `WM_POWERBROADCAST` messages.
    This is necessary because Python applications don't have a native message loop.
    """

    def __init__(self, on_resume_callback: SimpleCallback) -> None:
        """
        Initialize the power monitor.

        Args:
            on_resume_callback: Function to call when the system wakes up.

        Raises:
            ValueError: If callback is not callable.
        """
        if not callable(on_resume_callback):
            raise ValueError("on_resume_callback must be callable")

        self.on_resume_callback = on_resume_callback
        self._thread: threading.Thread | None = None
        self._logger = logging.getLogger(__name__)

    def start(self) -> None:
        """Start the message loop in a separate daemon thread."""
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()
        self._logger.info("Power monitor started")

    def _message_loop(self) -> None:
        """
        Create a hidden window and start the Win32 message pump.

        This method registers a window class and creates a message-only window
        to receive power management broadcasts from Windows.
        """
        window_class = win32gui.WNDCLASS()
        window_class.lpszClassName = "OzmozPowerMonitor"  # type: ignore
        window_class.hInstance = win32api.GetModuleHandle(None)  # type: ignore
        window_class.lpfnWndProc = self._window_procedure  # type: ignore

        try:
            win32gui.RegisterClass(window_class)
        except win32gui.error as error:
            # ERROR_CLASS_ALREADY_EXISTS = 1410 - safe to ignore
            if error.winerror != WIN32_ERROR_CLASS_ALREADY_EXISTS:
                self._logger.error(
                    "Failed to register power monitor window class",
                    extra={"error": str(error), "error_code": error.winerror},
                    exc_info=True,
                )
                return

        # Create hidden message-only window
        try:
            win32gui.CreateWindowEx(
                0,
                window_class.lpszClassName,
                "OzmozPowerMonitorWindow",
                0,
                0,
                0,
                0,
                0,
                win32con.HWND_MESSAGE,
                0,
                window_class.hInstance,
                None,
            )
            win32gui.PumpMessages()
        except Exception as error:
            self._logger.error(
                "Power monitor message loop failed",
                extra={"error": str(error)},
                exc_info=True,
            )

    def _window_procedure(
        self, window_handle: int, message_id: int, parameter_w: int, parameter_l: int
    ) -> int:
        """
        Win32 Window Procedure to handle messages.

        Args:
            window_handle: Window handle.
            message_id: Message identifier.
            parameter_w: Word parameter (WPARAM).
            parameter_l: Long parameter (LPARAM).

        Returns:
            0 if handled, default window procedure result otherwise.
        """
        if (
            message_id == win32con.WM_POWERBROADCAST
            and parameter_w == win32con.PBT_APMRESUMEAUTOMATIC
        ):
            self._logger.info("System resume detected (wake from sleep)")
            try:
                if self.on_resume_callback:
                    self.on_resume_callback()
            except Exception as error:
                self._logger.error(
                    "Error executing resume callback",
                    extra={"error": str(error)},
                    exc_info=True,
                )
        return 0


class AppLifecycleManager:
    """
    Manage application startup tasks and resource cleanup.

    Coordinates initialization of remote configurations and ensures
    proper shutdown of all subsystems.
    """

    def __init__(
        self,
        app_state: AppState,
        config_manager: ConfigManagerProtocol,
        audio_manager: AudioManagerProtocol,
        window_manager: WindowManagerProtocol,
    ) -> None:
        """
        Initialize the Lifecycle Manager.

        Args:
            app_state: Global application state.
            config_manager: Configuration manager.
            audio_manager: Audio manager.
            window_manager: Window manager.
        """
        self.app_state = app_state
        self.config_manager = config_manager
        self.audio_manager = audio_manager
        self.window_manager = window_manager
        self._logger = logging.getLogger(__name__)

    def run_background_startup_tasks(self) -> None:
        """
        Fetch remote configurations asynchronously to speed up boot time.

        Non-critical failures are logged but do not block application startup.
        """
        self._logger.info("Starting background configuration fetch")
        try:
            self.config_manager.load_and_parse_remote_config()
            self._logger.info("Remote configuration loaded successfully")
        except Exception as error:
            # Non-critical failure - app can run with local config
            self._logger.warning(
                "Failed to load remote configuration (using local fallback)",
                extra={"error": str(error)},
            )

    def cleanup_resources(self) -> None:
        """
        Terminate active services and ensure clean shutdown.

        Guarantees proper cleanup of system resources (audio streams, threads)
        to prevent orphaned processes or locked files.
        """
        self._logger.info("Starting application cleanup")
        try:
            if self.audio_manager:
                self.audio_manager.terminate()
                self._logger.info("Audio subsystem terminated")
        except Exception as error:
            self._logger.error(
                "Error during audio cleanup",
                extra={"error": str(error)},
                exc_info=True,
            )
        finally:
            self._logger.info("Application cleanup completed")
