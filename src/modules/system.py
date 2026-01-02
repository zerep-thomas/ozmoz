import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set

import win32api
import win32con
import win32gui
from pynput import keyboard as pynput_keyboard

from modules.config import AppState


class DualModeHotKey:
    """
    Custom wrapper for pynput hotkeys to handle both activation (press)
    and deactivation (release) events for complex interactions.
    """

    def __init__(
        self,
        keys: Set[Any],
        on_activate: Optional[Callable] = None,
        on_deactivate: Optional[Callable] = None,
    ):
        """
        Args:
            keys: A set of pynput Keys or KeyCodes required to trigger the action.
            on_activate: Callback executed when the combination is pressed.
            on_deactivate: Callback executed when the combination is released.
        """
        self._keys = keys
        self._state: Set[Any] = set()
        self._on_activate = on_activate
        self._on_deactivate = on_deactivate
        self._is_active = False

    def press(self, key: Any) -> None:
        """Updates internal state on key press and triggers activation if matched."""
        if key in self._keys:
            self._state.add(key)
            if self._state == self._keys:
                if not self._is_active:
                    self._is_active = True
                    if self._on_activate:
                        self._on_activate()

    def release(self, key: Any) -> None:
        """Updates internal state on key release and triggers deactivation."""
        if key in self._keys:
            self._state.discard(key)
            if self._is_active:
                self._is_active = False
                if self._on_deactivate:
                    self._on_deactivate()


class EventBus:
    """
    Thread-safe Publish/Subscribe mechanism for module decoupling.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._lock: threading.Lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """
        Registers a callback for a specific event type.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def publish(self, event_type: str, data: Any = None) -> None:
        """
        Broadcasts an event to all registered subscribers.
        """
        with self._lock:
            callbacks = self._subscribers.get(event_type, [])[:]

        for callback in callbacks:
            try:
                callback(data)
            except Exception as error:
                logging.error(f"EventBus error [{event_type}]: {error}", exc_info=True)


class HotkeyManager:
    """
    Manages global system hotkeys using 'pynput'.

    Implements a non-blocking execution model where actions and state checks
    are offloaded to separate threads to prevent Windows LowLevelHooks timeouts.
    """

    def __init__(
        self,
        app_state: AppState,
        window_manager: Any,
        audio_manager: Any,
        transcription_manager: Any,
    ) -> None:
        self.app_state: AppState = app_state
        self.window_manager: Any = window_manager
        self.audio_manager: Any = audio_manager
        self.transcription_manager: Any = transcription_manager

        self.ai_generation_manager: Optional[Any] = None
        self.web_search_manager: Optional[Any] = None
        self.vision_manager: Optional[Any] = None

        self._listener: Optional[pynput_keyboard.Listener] = None
        self._hotkeys_objects: List[Any] = []

    def set_managers(self, ai_gen: Any, web_search: Any, vision: Any) -> None:
        """Dependency injection for circular references."""
        self.ai_generation_manager = ai_gen
        self.web_search_manager = web_search
        self.vision_manager = vision

    def _convert_to_pynput_format(self, combo_str: str) -> str:
        """
        Normalizes hotkey strings to pynput compatible format.
        Example: 'ctrl+alt+x' -> '<ctrl>+<alt>+x'
        """
        if not combo_str:
            return ""
        parts = combo_str.lower().split("+")
        formatted_parts = []
        for part in parts:
            if part in ["ctrl", "control"]:
                formatted_parts.append("<ctrl>")
            elif part in ["alt"]:
                formatted_parts.append("<alt>")
            elif part in ["shift"]:
                formatted_parts.append("<shift>")
            elif part in ["cmd", "win"]:
                formatted_parts.append("<cmd>")
            else:
                formatted_parts.append(part)
        return "+".join(formatted_parts)

    def _execute_safely(
        self,
        action_callback: Optional[Callable],
        condition_callback: Optional[Callable[[], bool]] = None,
    ) -> None:
        """
        Executes the callback in a daemon thread.
        This ensures the keyboard hook returns immediately, maintaining system responsiveness.
        """

        def worker():
            try:
                if condition_callback and not condition_callback():
                    return
                if action_callback:
                    action_callback()
            except Exception as e:
                logging.error(f"Hotkey execution error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def stop_listening(self) -> None:
        """Stops the keyboard listener and clears registered hotkey objects."""
        if self._listener:
            try:
                self._listener.stop()
                self._listener = None
                self._hotkeys_objects.clear()
            except Exception:
                pass

    def register_all(self) -> bool:
        """
        Registers all configured hotkeys.
        Handles standard press triggers and press-and-hold logic via DualModeHotKey.
        """
        self.stop_listening()
        hotkeys_config = self.app_state.hotkeys

        def is_window_visible() -> bool:
            return self.window_manager.is_visible()

        # --- 1. Toggle Visibility (Simple Press) ---
        if toggle_key := hotkeys_config.get("toggle_visibility"):
            combo = self._convert_to_pynput_format(toggle_key)
            if combo:
                try:
                    keys = pynput_keyboard.HotKey.parse(combo)
                    hk = pynput_keyboard.HotKey(
                        keys,
                        on_activate=lambda: self._execute_safely(
                            self.window_manager.toggle_main_window_visibility
                        ),
                    )
                    self._hotkeys_objects.append(hk)
                except Exception as e:
                    logging.error(f"Error registering visibility key: {e}")

        # --- 2. Complex Actions (Press & Release / Hold) ---
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
            if combo_str := hotkeys_config.get(name):
                combo = self._convert_to_pynput_format(combo_str)
                if combo:
                    try:
                        # Parsing returns a list, converting to set for DualModeHotKey logic
                        keys = set(pynput_keyboard.HotKey.parse(combo))
                        hk = DualModeHotKey(
                            keys,
                            on_activate=lambda a=on_press, c=cond_press: self._execute_safely(
                                a, c
                            ),
                            on_deactivate=lambda a=on_release, c=cond_release: self._execute_safely(
                                a, c
                            ),
                        )
                        self._hotkeys_objects.append(hk)
                    except Exception as e:
                        logging.error(f"Error registering {name}: {e}")

        # --- Listener Initialization ---
        try:
            # Helper to normalize key events (canonical check)
            def for_canonical(f: Callable[[Any], None]) -> Callable[[Any], None]:
                return lambda k: (
                    f(self._listener.canonical(k)) if self._listener else None
                )

            self._listener = pynput_keyboard.Listener(
                on_press=for_canonical(self._handle_press),
                on_release=for_canonical(self._handle_release),
            )
            self._listener.start()
            logging.info("Pynput Hotkeys (Dual Mode) registered successfully.")
            return True
        except Exception as e:
            logging.critical(f"Failed to start pynput listener: {e}", exc_info=True)
            return False

    def _handle_press(self, key: Any) -> None:
        """Dispatches press events to all registered hotkey objects."""
        for hk in self._hotkeys_objects:
            hk.press(key)

    def _handle_release(self, key: Any) -> None:
        """Dispatches release events to all registered hotkey objects."""
        for hk in self._hotkeys_objects:
            hk.release(key)

    def system_resume_handler(self) -> None:
        """Handles system resume events to ensure hooks remain active."""
        logging.info("System resume detected. Reloading hotkeys...")
        time.sleep(2)
        self.register_all()


class SystemHealthManager:
    """
    Monitors application stability without aggressive polling.
    """

    def __init__(
        self,
        app_state: AppState,
        audio_manager: Any,
        hotkey_manager: HotkeyManager,
        window_manager: Any,
    ) -> None:
        self.app_state = app_state
        self.audio_manager = audio_manager
        self.hotkey_manager = hotkey_manager
        self.window_manager = window_manager

    def deep_reset(self) -> bool:
        """
        Performs a soft reset of critical subsystems (Audio & Input).
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
        Passive monitoring allows pynput to handle internal state.
        """
        logging.info("Hotkey health monitor active (Passive Mode).")
        stop_event.wait()

    def _validate_hotkey_state(self) -> bool:
        return True


class SystemPowerMonitor:
    """
    Hooks into the Windows Message Loop to detect Power Management events (Sleep/Resume).
    """

    def __init__(self, on_resume_callback: Callable[[], None]) -> None:
        self.on_resume_callback = on_resume_callback
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()
        logging.info("Power monitor active.")

    def _message_loop(self) -> None:
        wc = win32gui.WNDCLASS()
        # Type ignores required for Win32 struct attributes not fully typed in stubs
        wc.lpszClassName = "OzmozPowerMonitor"  # type: ignore
        wc.hInstance = win32api.GetModuleHandle(None)  # type: ignore
        wc.lpfnWndProc = self._window_procedure  # type: ignore

        try:
            win32gui.RegisterClass(wc)
        except win32gui.error as error:
            if error.winerror != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                logging.error(f"PowerMonitor Class error: {error}")
                return

        win32gui.CreateWindowEx(
            0,
            wc.lpszClassName,
            "OzmozPowerMonitorWindow",
            0,
            0,
            0,
            0,
            0,
            win32con.HWND_MESSAGE,
            0,
            wc.hInstance,
            None,
        )
        win32gui.PumpMessages()

    def _window_procedure(
        self, window_handle: int, message_id: int, parameter_w: int, parameter_l: int
    ) -> int:
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
        self.app_state = app_state
        self.config_manager = config_manager
        self.audio_manager = audio_manager
        self.window_manager = window_manager

    def run_background_startup_tasks(self) -> None:
        """Fetches remote configurations asynchronously."""
        logging.info("Background startup tasks started...")
        try:
            self.config_manager.load_and_parse_remote_config()
        except Exception:
            pass

    def cleanup_resources(self) -> None:
        """Terminates active services and ensures clean shutdown."""
        logging.info("Stopping services...")
        if self.audio_manager:
            self.audio_manager.terminate()
        logging.info("Cleanup finished.")
