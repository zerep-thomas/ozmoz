import io
import json
import logging
import os
import sys
import time
import threading
import win32clipboard
import win32con
import winsound
import ctypes
import ctypes.wintypes as wt
from pathlib import Path
from typing import IO, Optional
from pydub import AudioSegment
from src.core.system import global_executor

logger = logging.getLogger(__name__)

BEEP_ON_FILENAME = "src/static/audio/beep_on.wav"
BEEP_OFF_FILENAME = "src/static/audio/beep_off.wav"

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 32)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", INPUT_UNION)]

def _key_event(vk=0, scan=0, flags=0):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.wScan = scan
    inp.u.ki.dwFlags = flags
    inp.u.ki.time = 0
    inp.u.ki.dwExtraInfo = None
    return inp

def wait_modifiers_released(timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
            return True
        time.sleep(0.01)
    return False

def atomic_write_json(filepath: Path, data: dict | list) -> None:
    try:
        tmp_path = filepath.with_name(filepath.name + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, filepath)
    except Exception:
        pass

class PathManager:
    @staticmethod
    def get_resource_path(relative_path: str) -> str:
        base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
        return os.path.join(base_path, relative_path)

class SuppressStderr:
    def __init__(self) -> None:
        self._original_stderr: Optional[IO[str]] = None
        self._null_file: Optional[IO[str]] = None

    def __enter__(self) -> "SuppressStderr":
        self._original_stderr = sys.stderr
        try:
            self._null_file = open(os.devnull, "w", encoding="utf-8")
            sys.stderr = self._null_file
        except OSError:
            pass
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._null_file is not None:
            self._null_file.close()
        if self._original_stderr is not None:
            sys.stderr = self._original_stderr

class PerfTracker:
    def __init__(self, process_name: str):
        self.process_name = process_name
        self.start_time = time.perf_counter()
        self.last_time = self.start_time

    def step(self, step_name: str):
        self.last_time = time.perf_counter()

class SoundManager:
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    beep_on_bytes: bytes | None = None
    beep_off_bytes: bytes | None = None
    settings_manager = None
 
    def __new__(cls, settings_manager=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    if settings_manager:
                        cls.settings_manager = settings_manager
                    global_executor.submit(cls._instance._initialize)
        return cls._instance
 
    def _initialize(self):
        if SoundManager._initialized:
            return
        with SoundManager._lock:
            if SoundManager._initialized:
                return
            try:
                on_path = PathManager.get_resource_path(BEEP_ON_FILENAME)
                off_path = PathManager.get_resource_path(BEEP_OFF_FILENAME)
                if os.path.exists(on_path):
                    audio_on = AudioSegment.from_wav(on_path) - 10.0
                    buf = io.BytesIO()
                    audio_on.export(buf, format="wav")
                    SoundManager.beep_on_bytes = buf.getvalue()
                if os.path.exists(off_path):
                    audio_off = AudioSegment.from_wav(off_path) - 10.0
                    buf = io.BytesIO()
                    audio_off.export(buf, format="wav")
                    SoundManager.beep_off_bytes = buf.getvalue()
                SoundManager._initialized = True
            except Exception:
                pass
 
    def play(self, sound_name: str) -> None:
        if SoundManager.settings_manager and not SoundManager.settings_manager.get("play_sounds"):
            return
        if not SoundManager._initialized:
            self._initialize()
        sound_bytes = SoundManager.beep_on_bytes if sound_name == "beep_on" else SoundManager.beep_off_bytes
        if not sound_bytes:
            return
        def _blocking_play():
            try:
                winsound.PlaySound(sound_bytes, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
            except Exception:
                pass
        threading.Thread(target=_blocking_play, daemon=True, name=f"SoundPlay-{sound_name}").start()

class ClipboardManager:
    def _get_clipboard_text(self):
        try:
            win32clipboard.OpenClipboard()
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return data
        except Exception:
            return None

    def _set_clipboard_text(self, text):
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return True
        except Exception:
            return False

    def paste_and_clear(self, text: str) -> None:
        if not text:
            return
        def _worker():
            wait_modifiers_released()
            old_text = self._get_clipboard_text()
            if self._set_clipboard_text(text):
                time.sleep(0.05)
                events = [
                    _key_event(vk=VK_CONTROL),
                    _key_event(vk=VK_V),
                    _key_event(vk=VK_V, flags=KEYEVENTF_KEYUP),
                    _key_event(vk=VK_CONTROL, flags=KEYEVENTF_KEYUP),
                ]
                arr = (INPUT * len(events))(*events)
                user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
                time.sleep(0.3)
                if old_text is not None:
                    self._set_clipboard_text(old_text)
        global_executor.submit(_worker)