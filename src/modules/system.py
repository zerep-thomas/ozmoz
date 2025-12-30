import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set

import keyboard
import win32api
import win32con
import win32gui

# Local Modules
from modules.config import AppState


class EventBus:
    """
    Publish/Subscribe communication system to decouple modules.
    Allows components to emit events without knowing the recipients.
    """

    def __init__(self) -> None:
        """Initializes the EventBus with an empty subscriber dictionary and a thread lock."""
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._lock: threading.Lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """
        Subscribes a callback function to a specific event type.

        Args:
            event_type (str): The name of the event to subscribe to.
            callback (Callable[[Any], None]): The function to execute when the event occurs.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def publish(self, event_type: str, data: Any = None) -> None:
        """
        Broadcasts an event to all subscribers of that event type.

        Args:
            event_type (str): The name of the event being triggered.
            data (Any, optional): Data to pass to the callback functions. Defaults to None.
        """
        # Copy the list to avoid issues if a callback modifies subscriptions during iteration
        with self._lock:
            callbacks = self._subscribers.get(event_type, [])[:]

        for callback in callbacks:
            try:
                # Execution in the current thread (blocking)
                callback(data)
            except Exception as error:
                logging.error(f"EventBus error [{event_type}]: {error}", exc_info=True)


class HotkeyManager:
    """
    Manages global hotkeys with support for press and release events.
    Handles conditional triggering based on application state.
    """

    def __init__(
        self,
        app_state: AppState,
        window_manager: Any,
        audio_manager: Any,
        transcription_manager: Any,
    ) -> None:
        """
        Initializes the HotkeyManager.

        Args:
            app_state (AppState): The global application state.
            window_manager (Any): Manager for window visibility and interactions.
            audio_manager (Any): Manager for audio recording.
            transcription_manager (Any): Manager for handling transcriptions.
        """
        self.app_state: AppState = app_state
        self.window_manager: Any = window_manager
        self.audio_manager: Any = audio_manager
        self.transcription_manager: Any = transcription_manager

        # Deferred injection to avoid circular imports
        self.ai_generation_manager: Optional[Any] = None
        self.web_search_manager: Optional[Any] = None
        self.vision_manager: Optional[Any] = None

    def set_managers(self, ai_gen: Any, web_search: Any, vision: Any) -> None:
        """
        Injects dependency managers after instantiation to handle circular dependencies.

        Args:
            ai_gen (Any): The AI generation manager.
            web_search (Any): The web search manager.
            vision (Any): The screen vision manager.
        """
        self.ai_generation_manager = ai_gen
        self.web_search_manager = web_search
        self.vision_manager = vision

    def _create_handler(
        self,
        combo: str,
        action: Callable[[], None],
        condition: Callable[[], bool] = lambda: True,
    ) -> Callable[[keyboard.KeyboardEvent], None]:
        """
        Generates a callback that checks modifiers and executes the action
        IN A SEPARATE THREAD to prevent Windows from killing the hook due to timeout.
        """
        modifiers: Set[str] = {
            part
            for part in combo.lower().split("+")
            if part in ("ctrl", "alt", "shift")
        }

        def handler(event: keyboard.KeyboardEvent) -> None:
            if all(keyboard.is_pressed(mod) for mod in modifiers) and condition():
                threading.Thread(target=action, daemon=True).start()

        return handler

    def register_all(self) -> bool:
        """
        Registers all hotkeys defined in the AppState configuration.
        Unhooks existing hotkeys before registering new ones.

        Returns:
            bool: True if registration succeeded, False otherwise.
        """
        if not all(
            [self.ai_generation_manager, self.web_search_manager, self.vision_manager]
        ):
            logging.warning(
                "HotkeyManager: Managers not injected, some hotkeys will be ignored."
            )

        with self.app_state.keyboard_lock:
            try:
                keyboard.unhook_all()
                time.sleep(0.1)

                hotkeys: Dict[str, str] = self.app_state.hotkeys

                # 1. Visibility Toggle
                if toggle_key := hotkeys.get("toggle_visibility"):
                    keyboard.add_hotkey(
                        toggle_key,
                        self.window_manager.toggle_main_window_visibility,
                        suppress=False,
                        trigger_on_release=False,
                    )

                def is_window_visible() -> bool:
                    return self.window_manager.is_visible()

                # 2. Press/Release Actions (Push-to-Talk & AI Features)
                # Structure: Name -> (OnPress, OnRelease, ConditionPress, ConditionRelease)
                actions: Dict[
                    str,
                    tuple[
                        Callable[[], None],
                        Callable[[], None],
                        Callable[[], bool],
                        Callable[[], bool],
                    ],
                ] = {
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

                for name, (
                    on_press,
                    on_release,
                    condition_press,
                    condition_release,
                ) in actions.items():
                    if combo := hotkeys.get(name):
                        trigger_key = combo.split("+")[-1]

                        keyboard.on_press_key(
                            trigger_key,
                            self._create_handler(combo, on_press, condition_press),
                            suppress=False,
                        )
                        keyboard.on_release_key(
                            trigger_key,
                            self._create_handler(combo, on_release, condition_release),
                            suppress=False,
                        )

                return True

            except Exception as error:
                logging.critical(f"Error registering hotkeys: {error}", exc_info=True)
                return False

    def system_resume_handler(self) -> None:
        """
        Reloads hotkeys after the system resumes from sleep/hibernation.
        Waits briefly to ensure drivers are ready.
        """
        logging.info("System resume detected. Reloading hotkeys...")
        time.sleep(2)
        self.register_all()


class SystemHealthManager:
    """
    Manages critical component monitoring and performs emergency resets
    if the application enters an unstable state.
    """

    def __init__(
        self,
        app_state: AppState,
        audio_manager: Any,
        hotkey_manager: HotkeyManager,
        window_manager: Any,
    ) -> None:
        """
        Initializes the SystemHealthManager.

        Args:
            app_state (AppState): Global application state.
            audio_manager (Any): Manager handling audio.
            hotkey_manager (HotkeyManager): Manager handling keyboard hooks.
            window_manager (Any): Manager handling UI windows.
        """
        self.app_state: AppState = app_state
        self.audio_manager: Any = audio_manager
        self.hotkey_manager: HotkeyManager = hotkey_manager
        self.window_manager: Any = window_manager

    def deep_reset(self) -> bool:
        """
        Resets UI, Audio, and Hotkeys to recover from errors.

        Returns:
            bool: True if reset completed successfully, False on crash.
        """
        logging.warning("--- STARTING DEEP RESET ---")

        was_visible: bool = False
        try:
            # Note: Direct Win32 access via window_manager assumed
            window_handle = self.window_manager._find_window(
                self.window_manager.main_window_title
            )
            if window_handle and win32gui.IsWindowVisible(window_handle):
                was_visible = True
        except Exception:
            pass

        try:
            # 1. Reset States
            self.app_state.is_busy = False
            self.app_state.is_recording = False
            self.app_state.ai_recording = False
            logging.info("State locks released.")

            # 2. Reset UI
            if was_visible and self.app_state.window:
                try:
                    self.app_state.window.evaluate_js("resetUI()")
                    self.app_state.window.evaluate_js("setSettingsButtonState(false)")
                except Exception as error:
                    logging.error(f"UI Reset error: {error}")

            # 3. Reset Audio
            logging.info("Restarting Audio service...")
            self.audio_manager.terminate()
            self.audio_manager.initialize()

            # 4. Reset Keyboard
            self.hotkey_manager.register_all()

            logging.warning("--- DEEP RESET FINISHED ---")
            return True

        except Exception as error:
            logging.critical(f"CRASH DURING RESET: {error}", exc_info=True)
            return False

    def run_hotkey_health_monitor(self, stop_event: threading.Event) -> None:
        """
        Worker function: Periodically checks and repairs keyboard hooks.

        Args:
            stop_event (threading.Event): Event to signal the thread to stop.
        """
        logging.info("Hotkey health monitor active.")

        # Quick checks at startup (5s, 10s, 15s)
        for interval in [5, 10, 15]:
            if stop_event.wait(timeout=interval):
                return
            self.hotkey_manager.register_all()

        # Regular checks
        while not stop_event.is_set():
            if stop_event.wait(timeout=60):
                break

            # Avoid reset if app is currently recording
            if not (
                self.app_state.is_busy
                or self.app_state.is_recording
                or self.app_state.ai_recording
            ):
                self.hotkey_manager.register_all()

    def _validate_hotkey_state(self) -> bool:
        """
        Performs a basic test of the keyboard library state.

        Returns:
            bool: True if the keyboard library is responsive.
        """
        try:
            key = self.app_state.hotkeys.get("toggle_visibility", "ctrl+alt").split(
                "+"
            )[-1]
            keyboard.is_pressed(key)
            return True
        except Exception:
            return False


class SystemPowerMonitor:
    """
    Intercepts Windows WM_POWERBROADCAST messages to detect System Resume events.
    Useful for re-hooking keyboards after sleep mode.
    """

    def __init__(self, on_resume_callback: Callable[[], None]) -> None:
        """
        Initializes the PowerMonitor.

        Args:
            on_resume_callback (Callable[[], None]): Function to call when system resumes.
        """
        self.on_resume_callback: Callable[[], None] = on_resume_callback
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts the background thread that listens for Windows messages."""
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()
        logging.info("Power monitor active.")

    def _message_loop(self) -> None:
        """
        Native message loop (Win32) to capture system events.
        Creates a hidden window to receive messages.
        """
        wc = win32gui.WNDCLASS()
        wc.lpszClassName = "OzmozPowerMonitor"  # type: ignore
        wc.hInstance = win32api.GetModuleHandle(None)  # type: ignore
        wc.lpfnWndProc = self._window_procedure  # type: ignore

        try:
            win32gui.RegisterClass(wc)
        except win32gui.error as error:
            if error.winerror != 1410:
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
        """
        Window Procedure (WndProc) callback for processing messages.

        Args:
            window_handle (int): Handle to the window.
            message_id (int): The message identifier.
            parameter_w (int): Additional message info (WPARAM).
            parameter_l (int): Additional message info (LPARAM).

        Returns:
            int: Result of the message processing (usually 0).
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
    Manages asynchronous loading of configuration and resource cleanup
    during application startup and shutdown.
    """

    def __init__(
        self,
        app_state: AppState,
        config_manager: Any,
        audio_manager: Any,
        window_manager: Any,
    ) -> None:
        """
        Initializes the Lifecycle Manager.

        Args:
            app_state (AppState): Global application state.
            config_manager (Any): Manager for configuration loading.
            audio_manager (Any): Manager for audio services.
            window_manager (Any): Manager for UI windows.
        """
        self.app_state: AppState = app_state
        self.config_manager: Any = config_manager
        self.audio_manager: Any = audio_manager
        self.window_manager: Any = window_manager

    def run_background_startup_tasks(self) -> None:
        """Loads remote configuration without blocking the UI thread."""
        logging.info("Background startup tasks started...")

        try:
            self.config_manager.load_and_parse_remote_config()
        except Exception:
            pass

    def cleanup_resources(self) -> None:
        """Stops services and unhooks listeners before exit."""
        logging.info("Stopping services...")
        if self.audio_manager:
            self.audio_manager.terminate()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        logging.info("Cleanup finished.")
