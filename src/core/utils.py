import io
import logging
import os
import sys
import time
import threading
import tempfile
import win32clipboard
import win32con
import keyboard
import winsound
import pywintypes
from pathlib import Path
from typing import IO, Optional
from pydub import AudioSegment

logger = logging.getLogger(__name__)

BEEP_ON_FILENAME = "src/static/audio/beep_on.wav"
BEEP_OFF_FILENAME = "src/static/audio/beep_off.wav"
CLIPBOARD_MAX_RETRIES = 10
CLIPBOARD_CLEAR_DELAY_SECONDS = 0.5

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
        logger.debug("PERF START: %s", self.process_name)

    def step(self, step_name: str):
        now = time.perf_counter()
        elapsed = now - self.last_time
        total = now - self.start_time
        logger.debug("PERF %s | %s | Step: %.4fs | Total: %.4fs", self.process_name, step_name, elapsed, total)
        self.last_time = now

class SoundManager:
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    beep_on_path = None
    beep_off_path = None
    settings_manager = None

    def __new__(cls, settings_manager=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    if settings_manager:
                        cls.settings_manager = settings_manager
                    
                    # Pre-load and process sounds in background during startup
                    threading.Thread(target=cls._instance._initialize, daemon=True, name="SoundPreloader").start()
        return cls._instance

    def _initialize(self):
        if SoundManager._initialized: return
        with SoundManager._lock:
            if SoundManager._initialized: return
            try:
                on_path = PathManager.get_resource_path(BEEP_ON_FILENAME)
                off_path = PathManager.get_resource_path(BEEP_OFF_FILENAME)
                
                temp_dir = tempfile.gettempdir()
                out_on_path = os.path.join(temp_dir, "ozmoz_beep_on.wav")
                out_off_path = os.path.join(temp_dir, "ozmoz_beep_off.wav")
                
                # Set default fallbacks to the original sound files
                SoundManager.beep_on_path = on_path
                SoundManager.beep_off_path = off_path

                if os.path.exists(on_path):
                    try:
                        audio_on = AudioSegment.from_wav(on_path) - 10.0
                        audio_on.export(out_on_path, format="wav")
                        if os.path.exists(out_on_path):
                            SoundManager.beep_on_path = out_on_path
                    except Exception as e:
                        logger.error(f"Failed to lower volume for beep_on: {e}")
                
                if os.path.exists(off_path):
                    try:
                        audio_off = AudioSegment.from_wav(off_path) - 10.0
                        audio_off.export(out_off_path, format="wav")
                        if os.path.exists(out_off_path):
                            SoundManager.beep_off_path = out_off_path
                    except Exception as e:
                        logger.error(f"Failed to lower volume for beep_off: {e}")
                    
                SoundManager._initialized = True
            except Exception:
                logger.exception("Failed to initialize sound manager")

    def play(self, sound_name: str) -> None:
        if SoundManager.settings_manager and not SoundManager.settings_manager.get("play_sounds"):
            return
        if not SoundManager._initialized: self._initialize()
        
        sound_path = SoundManager.beep_on_path if sound_name == "beep_on" else SoundManager.beep_off_path
        if not sound_path or not os.path.exists(sound_path): return
        
        try:
            # Play standard WAV file asynchronously using SND_FILENAME safely
            winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_NODEFAULT | winsound.SND_ASYNC)
        except Exception:
            logger.exception("Failed to play sound")

class ClipboardManager:
    def paste_and_clear(self, text: str) -> None:
        if not text: return
        def _paste_worker():
            success = False
            for _ in range(CLIPBOARD_MAX_RETRIES):
                try:
                    win32clipboard.OpenClipboard()
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
                    win32clipboard.CloseClipboard()
                    success = True
                    break
                except pywintypes.error:
                    time.sleep(0.01)
            
            if not success:
                logger.error("Paste failed: Could not access Windows clipboard.")
                return

            time.sleep(0.1)
            try:
                keyboard.send("ctrl+v")
            except Exception:
                logger.exception("Keystroke failed")

            time.sleep(CLIPBOARD_CLEAR_DELAY_SECONDS)
            
            for _ in range(CLIPBOARD_MAX_RETRIES):
                try:
                    win32clipboard.OpenClipboard()
                    win32clipboard.EmptyClipboard()
                    win32clipboard.CloseClipboard()
                    break
                except pywintypes.error:
                    time.sleep(0.01)

        threading.Thread(target=_paste_worker, daemon=True).start()