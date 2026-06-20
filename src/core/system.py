import logging
import threading
from typing import Callable, Final, Protocol, TypeAlias, cast

from pynput import keyboard as pynput_keyboard
from pynput.keyboard import Key, KeyCode

from src.core.config import AppState

PynputKey: TypeAlias = Key | KeyCode
EventCallback: TypeAlias = Callable[[object], None]
SimpleCallback: TypeAlias = Callable[[], None]
ConditionCallback: TypeAlias = Callable[[], bool]

HOTKEY_THREAD_NAME_PREFIX: Final[str] = "HotkeyAction"

class AudioManagerProtocol(Protocol):
    def start_recording(self) -> None: ...

class TranscriptionManagerProtocol(Protocol):
    def stop_recording_and_transcribe(self) -> None: ...

class HotkeyRegistrationError(Exception): pass

class DualModeHotKey:
    def __init__(
        self,
        trigger_keys: set[PynputKey],
        on_activate: SimpleCallback | None = None,
        on_deactivate: SimpleCallback | None = None,
    ) -> None:
        self._trigger_keys = trigger_keys
        self._currently_pressed_keys: set[PynputKey] = set()
        self._on_activate = on_activate
        self._on_deactivate = on_deactivate
        self._is_active = False

    def press(self, key: PynputKey) -> None:
        if key in self._trigger_keys:
            self._currently_pressed_keys.add(key)
            if self._currently_pressed_keys == self._trigger_keys:
                if not self._is_active:
                    self._is_active = True
                    if self._on_activate:
                        self._on_activate()

    def release(self, key: PynputKey) -> None:
        if key in self._trigger_keys:
            self._currently_pressed_keys.discard(key)
            if self._is_active:
                self._is_active = False
                if self._on_deactivate:
                    self._on_deactivate()

class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventCallback]] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger(__name__)

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def publish(self, event_type: str, data: object = None) -> None:
        with self._lock:
            callbacks = self._subscribers.get(event_type, [])[:]
        for callback in callbacks:
            try:
                thread = threading.Thread(target=callback, args=(data,), daemon=True, name=f"EventBus-{event_type}")
                thread.start()
            except Exception:
                self._logger.exception("EventBus callback execution failed")

class HotkeyManager:
    _SPECIAL_KEYS_MAP: Final[dict[str, str]] = {
        "ctrl": "<ctrl>", "alt": "<alt>", "shift": "<shift>", "space": "<space>"
    }

    def __init__(
        self, app_state: AppState,
        audio_manager: AudioManagerProtocol, transcription_manager: TranscriptionManagerProtocol,
    ) -> None:
        self.app_state = app_state
        self.audio_manager = audio_manager
        self.transcription_manager = transcription_manager
        self._listener = None
        self._registered_hotkeys = []
        self._logger = logging.getLogger(__name__)
        self._thread_counter = 0

    def _convert_to_pynput_format(self, combination_string: str) -> str:
        if not combination_string: return ""
        parts = combination_string.lower().split("+")
        formatted_parts = []
        for part in parts:
            part = part.strip()
            if part in self._SPECIAL_KEYS_MAP:
                formatted_parts.append(self._SPECIAL_KEYS_MAP[part])
            elif len(part) == 1 and part.isalnum():
                formatted_parts.append(part)
            else:
                formatted_parts.append(f"<{part}>")
        return "+".join(formatted_parts)

    def _execute_action_safely(self, action_callback, condition_callback=None):
        def worker():
            try:
                if condition_callback and not condition_callback(): return
                if action_callback: action_callback()
            except Exception:
                self._logger.exception("Action failed")
        self._thread_counter += 1
        threading.Thread(target=worker, daemon=True, name=f"{HOTKEY_THREAD_NAME_PREFIX}-{self._thread_counter}").start()

    def stop_listening(self):
        if self._listener:
            try:
                self._listener.stop()
                self._listener = None
                self._registered_hotkeys.clear()
            except Exception:
                pass

    def register_all(self) -> bool:
        self.stop_listening()
        hotkeys_config = self.app_state.hotkeys

        actions = {
            "record_toggle": (
                self.audio_manager.start_recording,
                self.transcription_manager.stop_recording_and_transcribe,
                lambda: not self.app_state.audio.is_recording and not self.app_state.is_busy,
                lambda: self.app_state.audio.is_recording,
            )
        }

        for name, (on_press, on_release, cond_press, cond_release) in actions.items():
            if raw_combo := hotkeys_config.get(name):
                try:
                    formatted_combo = self._convert_to_pynput_format(raw_combo)
                    if formatted_combo:
                        trigger_keys = set(pynput_keyboard.HotKey.parse(formatted_combo))
                        dual_hotkey = DualModeHotKey(
                            trigger_keys=cast(set[PynputKey], trigger_keys),
                            on_activate=lambda a=on_press, c=cond_press: self._execute_action_safely(a, c),
                            on_deactivate=lambda a=on_release, c=cond_release: self._execute_action_safely(a, c),
                        )
                        self._registered_hotkeys.append(dual_hotkey)
                except Exception:
                    self._logger.exception("Error registering %s", name)

        try:
            def for_canonical(func):
                return lambda k: func(self._listener.canonical(k)) if self._listener and k is not None else None

            self._listener = pynput_keyboard.Listener(
                on_press=for_canonical(self._handle_press),
                on_release=for_canonical(self._handle_release),
            )
            self._listener.start()
            return True
        except Exception as error:
            raise HotkeyRegistrationError(f"Listener error: {error}")

    def _handle_press(self, key: PynputKey) -> None:
        for hk in self._registered_hotkeys: hk.press(key)

    def _handle_release(self, key: PynputKey) -> None:
        for hk in self._registered_hotkeys: hk.release(key)