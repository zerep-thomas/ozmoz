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
from typing import Any, Callable, Dict, List, Optional, Set

# --- Third-Party Imports ---
import win32api
import win32con
import win32gui
from pynput import keyboard as pynput_keyboard

# --- Local Imports ---
from modules.config import AppState


class DualModeHotKey:
    """
    Custom wrapper for `pynput` hotkeys to handle both activation (press)
    and deactivation (release) events.

    Standard `pynput.HotKey` only triggers on activation. This class maintains
    state to allow for "Press and Hold" interactions (e.g., Voice Dictation).
    """

    def __init__(
        self,
        trigger_keys: Set[Any],
        on_activate: Optional[Callable[[], None]] = None,
        on_deactivate: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Initialize the DualModeHotKey.

        Args:
            trigger_keys (Set[Any]): A set of `pynput` Keys or KeyCodes required to trigger the action.
            on_activate (Optional[Callable]): Callback executed when the combination is fully pressed.
            on_deactivate (Optional[Callable]): Callback executed when the combination is released.
        """
        self._trigger_keys: Set[Any] = trigger_keys
        self._currently_pressed_keys: Set[Any] = set()
        self._on_activate: Optional[Callable[[], None]] = on_activate
        self._on_deactivate: Optional[Callable[[], None]] = on_deactivate
        self._is_active: bool = False

    def press(self, key: Any) -> None:
        """
        Updates internal state on key press and triggers activation if the combination matches.

        Args:
            key (Any): The key pressed event from the listener.
        """
        if key in self._trigger_keys:
            self._currently_pressed_keys.add(key)

            if self._currently_pressed_keys == self._trigger_keys:
                if not self._is_active:
                    self._is_active = True
                    if self._on_activate:
                        self._on_activate()

    def release(self, key: Any) -> None:
        """
        Updates internal state on key release and triggers deactivation.

        Args:
            key (Any): The key released event from the listener.
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
    """

    def __init__(self) -> None:
        """Initialize the EventBus with an empty subscriber list and a thread lock."""
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._lock: threading.Lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """
        Registers a callback function for a specific event type.

        Args:
            event_type (str): The unique identifier for the event.
            callback (Callable[[Any], None]): The function to call when the event is published.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def publish(self, event_type: str, data: Any = None) -> None:
        """
        Broadcasts an event to all registered subscribers.

        Args:
            event_type (str): The unique identifier for the event.
            data (Any, optional): Payload to pass to the subscribers. Defaults to None.
        """
        with self._lock:
            # Create a shallow copy to iterate safely while holding the lock
            callbacks = self._subscribers.get(event_type, [])[:]

        for callback in callbacks:
            try:
                callback(data)
            except Exception as error:
                logging.error(
                    f"EventBus error processing [{event_type}]: {error}", exc_info=True
                )


class HotkeyManager:
    """
    Manages global system hotkeys using `pynput`.

    Implements a non-blocking execution model where actions and state checks
    are offloaded to separate daemon threads. This is critical to prevent the
    Windows LowLevelHooks from timing out if an action takes too long.
    """

    def __init__(
        self,
        app_state: AppState,
        window_manager: Any,
        audio_manager: Any,
        transcription_manager: Any,
    ) -> None:
        """
        Initialize the HotkeyManager.

        Args:
            app_state (AppState): Global application state.
            window_manager (Any): Instance of WindowManager.
            audio_manager (Any): Instance of AudioManager.
            transcription_manager (Any): Instance of TranscriptionManager.
        """
        self.app_state: AppState = app_state
        self.window_manager: Any = window_manager
        self.audio_manager: Any = audio_manager
        self.transcription_manager: Any = transcription_manager

        # Circular dependencies injected later via set_managers
        self.ai_generation_manager: Optional[Any] = None
        self.web_search_manager: Optional[Any] = None
        self.vision_manager: Optional[Any] = None

        self._listener: Optional[pynput_keyboard.Listener] = None
        self._registered_hotkeys: List[Any] = []

    def set_managers(self, ai_gen: Any, web_search: Any, vision: Any) -> None:
        """
        Dependency injection for circular references to service managers.

        Args:
            ai_gen (Any): The AI Generation Manager.
            web_search (Any): The Web Search Manager.
            vision (Any): The Vision Manager.
        """
        self.ai_generation_manager = ai_gen
        self.web_search_manager = web_search
        self.vision_manager = vision

    def _convert_to_pynput_format(self, combination_string: str) -> str:
        """
        Normalizes hotkey strings to a `pynput` compatible format.
        Handles modifiers, special keys (arrows, F-keys), and AltGr.

        Example: 'ctrl+alt+down' -> '<ctrl>+<alt>+<down>'

        Args:
            combination_string (str): The raw hotkey string from settings (e.g., "ctrl+c").

        Returns:
            str: The formatted string ready for `pynput`.
        """
        if not combination_string:
            return ""

        parts = combination_string.lower().split("+")
        formatted_parts: List[str] = []

        special_keys_map: Dict[str, str] = {
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

        for part in parts:
            part = part.strip()

            if part in special_keys_map:
                formatted_parts.append(special_keys_map[part])

            elif part.startswith("f") and part[1:].isdigit():
                # Handles F1 through F12+
                formatted_parts.append(f"<{part}>")

            elif part.startswith("numpad"):
                # Handles Numpad keys (e.g. numpad1 -> 1)
                if len(part) == 7 and part[-1].isdigit():
                    formatted_parts.append(part[-1])
                else:
                    formatted_parts.append(part)

            else:
                formatted_parts.append(part)

        return "+".join(formatted_parts)

    def _execute_action_safely(
        self,
        action_callback: Optional[Callable[[], None]],
        condition_callback: Optional[Callable[[], bool]] = None,
    ) -> None:
        """
        Executes the provided callback in a daemon thread.

        This ensures the keyboard hook returns immediately, maintaining system responsiveness
        even if the action (like starting AI generation) takes time.

        Args:
            action_callback (Optional[Callable]): The function to execute.
            condition_callback (Optional[Callable]): A predicate that must return True for the action to run.
        """

        def worker() -> None:
            try:
                if condition_callback and not condition_callback():
                    return
                if action_callback:
                    action_callback()
            except Exception as error:
                logging.error(f"Hotkey execution error: {error}")

        threading.Thread(target=worker, daemon=True).start()

    def stop_listening(self) -> None:
        """Stops the keyboard listener and clears registered hotkey objects."""
        if self._listener:
            try:
                self._listener.stop()
                self._listener = None
                self._registered_hotkeys.clear()
            except Exception:
                pass

    def register_all(self) -> bool:
        """
        Registers all configured hotkeys.

        Handles standard press triggers and press-and-hold logic via `DualModeHotKey`.
        It parses the configuration from `AppState` and sets up the low-level hooks.

        Returns:
            bool: True if registration was successful, False otherwise.
        """
        self.stop_listening()
        hotkeys_config = self.app_state.hotkeys

        def is_window_visible() -> bool:
            return self.window_manager.is_visible()

        # --- 1. Toggle Visibility (Simple Press) ---
        if toggle_key := hotkeys_config.get("toggle_visibility"):
            combo_str = self._convert_to_pynput_format(toggle_key)
            if combo_str:
                try:
                    # pynput.HotKey expects a list of keys for its constructor
                    parsed_keys = pynput_keyboard.HotKey.parse(combo_str)
                    hotkey_instance = pynput_keyboard.HotKey(
                        parsed_keys,
                        on_activate=lambda: self._execute_action_safely(
                            self.window_manager.toggle_main_window_visibility
                        ),
                    )
                    self._registered_hotkeys.append(hotkey_instance)
                except Exception as error:
                    logging.error(f"Error registering visibility key: {error}")

        # --- 2. Complex Actions (Press & Release / Hold) ---
        # Structure: Name -> (OnPress, OnRelease, PressCondition, ReleaseCondition)
        actions = {
            "record_toggle": (
                lambda: self.audio_manager.start_recording(),
                lambda: self.transcription_manager.stop_recording_and_transcribe(),
                lambda: is_window_visible()
                and not self.app_state.is_recording
                and not self.app_state.is_busy,
                lambda: self.app_state.is_recording,
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
                formatted_combo = self._convert_to_pynput_format(raw_combo)
                if formatted_combo:
                    try:
                        # Parsing returns a list, converting to set for DualModeHotKey logic
                        trigger_keys = set(
                            pynput_keyboard.HotKey.parse(formatted_combo)
                        )

                        # Use default argument binding in lambda to capture current loop values
                        dual_hotkey = DualModeHotKey(
                            trigger_keys,
                            on_activate=lambda a=on_press, c=cond_press: self._execute_action_safely(
                                a, c
                            ),
                            on_deactivate=lambda a=on_release, c=cond_release: self._execute_action_safely(
                                a, c
                            ),
                        )
                        self._registered_hotkeys.append(dual_hotkey)
                    except Exception as error:
                        logging.error(f"Error registering {name}: {error}")

        # --- Listener Initialization ---
        try:
            # Helper to normalize key events (canonical check)
            def for_canonical(func: Callable[[Any], None]) -> Callable[[Any], None]:
                return lambda k: (
                    func(self._listener.canonical(k)) if self._listener else None
                )

            self._listener = pynput_keyboard.Listener(
                on_press=for_canonical(self._handle_press),
                on_release=for_canonical(self._handle_release),
            )
            self._listener.start()
            logging.info("Pynput Hotkeys (Dual Mode) registered successfully.")
            return True
        except Exception as error:
            logging.critical(f"Failed to start pynput listener: {error}", exc_info=True)
            return False

    def _handle_press(self, key: Any) -> None:
        """Dispatches press events to all registered hotkey objects."""
        for hotkey_object in self._registered_hotkeys:
            hotkey_object.press(key)

    def _handle_release(self, key: Any) -> None:
        """Dispatches release events to all registered hotkey objects."""
        for hotkey_object in self._registered_hotkeys:
            hotkey_object.release(key)

    def system_resume_handler(self) -> None:
        """
        Handles system resume events (waking from sleep).
        Re-registers hotkeys to ensure hooks remain active after suspension.
        """
        logging.info("System resume detected. Reloading hotkeys...")
        time.sleep(2)  # Wait for system to stabilize
        self.register_all()


class SystemHealthManager:
    """
    Monitors application stability without aggressive polling.
    Provides methods to reset subsystems in case of failure.
    """

    def __init__(
        self,
        app_state: AppState,
        audio_manager: Any,
        hotkey_manager: HotkeyManager,
        window_manager: Any,
    ) -> None:
        """
        Initialize the SystemHealthManager.

        Args:
            app_state (AppState): Global application state.
            audio_manager (Any): Audio subsystem manager.
            hotkey_manager (HotkeyManager): Input subsystem manager.
            window_manager (Any): GUI window manager.
        """
        self.app_state = app_state
        self.audio_manager = audio_manager
        self.hotkey_manager = hotkey_manager
        self.window_manager = window_manager

    def deep_reset(self) -> bool:
        """
        Performs a soft reset of critical subsystems (Audio & Input).
        Useful if the audio stream hangs or hotkeys stop responding.

        Returns:
            bool: True if reset was attempted, False if a critical error occurred.
        """
        logging.warning("--- STARTING SOFT RESET ---")
        try:
            self.app_state.is_busy = False
            self.app_state.is_recording = False
            self.app_state.ai_recording = False

            self.audio_manager.terminate()
            self.audio_manager.initialize()

            self.hotkey_manager.register_all()
            return True
        except Exception as error:
            logging.critical(f"RESET ERROR: {error}", exc_info=True)
            return False

    def run_hotkey_health_monitor(self, stop_event: threading.Event) -> None:
        """
        Blocks until the stop event is set.
        Keeps the health monitor thread alive in Passive Mode.

        Args:
            stop_event (threading.Event): Event to signal application shutdown.
        """
        logging.info("Hotkey health monitor active (Passive Mode).")
        stop_event.wait()

    def _validate_hotkey_state(self) -> bool:
        """Internal check for hotkey stability (Placeholder for future logic)."""
        return True


class SystemPowerMonitor:
    """
    Hooks into the Windows Message Loop to detect Power Management events (Sleep/Resume).
    Uses a hidden window to receive `WM_POWERBROADCAST` messages.
    """

    def __init__(self, on_resume_callback: Callable[[], None]) -> None:
        """
        Initialize the power monitor.

        Args:
            on_resume_callback (Callable): Function to call when the system wakes up.
        """
        self.on_resume_callback = on_resume_callback
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts the message loop in a separate daemon thread."""
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()
        logging.info("Power monitor active.")

    def _message_loop(self) -> None:
        """Creates a hidden window and starts the Win32 message pump."""
        window_class = win32gui.WNDCLASS()
        # Type ignores required as Win32 struct attributes are dynamically typed in pywin32
        window_class.lpszClassName = "OzmozPowerMonitor"  # type: ignore
        window_class.hInstance = win32api.GetModuleHandle(None)  # type: ignore
        window_class.lpfnWndProc = self._window_procedure  # type: ignore

        try:
            win32gui.RegisterClass(window_class)
        except win32gui.error as error:
            # ERROR_CLASS_ALREADY_EXISTS = 1410
            if error.winerror != 1410:
                logging.error(f"PowerMonitor Class registration error: {error}")
                return

        # Create hidden window to receive messages
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

    def _window_procedure(
        self, window_handle: int, message_id: int, parameter_w: int, parameter_l: int
    ) -> int:
        """
        Win32 Window Procedure to handle messages.

        Args:
            window_handle (int): Window handle.
            message_id (int): Message identifier.
            parameter_w (int): Word parameter (WPARAM).
            parameter_l (int): Long parameter (LPARAM).

        Returns:
            int: 0 if handled.
        """
        if (
            message_id == win32con.WM_POWERBROADCAST
            and parameter_w == win32con.PBT_APMRESUMEAUTOMATIC
        ):
            logging.info("System: Resuming from sleep.")
            if self.on_resume_callback:
                self.on_resume_callback()
        return 0


class AppLifecycleManager:
    """
    Manages application startup tasks and resource cleanup.
    """

    def __init__(
        self,
        app_state: AppState,
        config_manager: Any,
        audio_manager: Any,
        window_manager: Any,
    ) -> None:
        """
        Initialize the Lifecycle Manager.

        Args:
            app_state (AppState): Global application state.
            config_manager (Any): Configuration manager.
            audio_manager (Any): Audio manager.
            window_manager (Any): Window manager.
        """
        self.app_state = app_state
        self.config_manager = config_manager
        self.audio_manager = audio_manager
        self.window_manager = window_manager

    def run_background_startup_tasks(self) -> None:
        """Fetches remote configurations asynchronously to speed up boot time."""
        logging.info("Background startup tasks started...")
        try:
            self.config_manager.load_and_parse_remote_config()
        except Exception:
            # Non-critical failure, logs handled inside manager
            pass

    def cleanup_resources(self) -> None:
        """Terminates active services and ensures clean shutdown."""
        logging.info("Stopping services...")
        if self.audio_manager:
            self.audio_manager.terminate()
        logging.info("Cleanup finished.")
