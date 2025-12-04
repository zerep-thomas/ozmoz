import io
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import keyboard
import numpy as np
import pyaudio
import pyperclip
import win32con
import win32gui

# Patched Popen for Windows to hide console windows
if sys.platform == "win32":
    _original_popen = subprocess.Popen

    class _PatchedPopen(_original_popen):
        def __init__(self, *args, **kwargs):
            if "startupinfo" not in kwargs:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                kwargs["startupinfo"] = startupinfo

            if "creationflags" not in kwargs:
                kwargs["creationflags"] = 0x08000000

            super().__init__(*args, **kwargs)

    subprocess.Popen = _PatchedPopen

from deepgram import DeepgramClient, FileSource, PrerecordedOptions
from groq import Groq

# Correction: Importing from transforms to avoid export error
from text_to_num.transforms import alpha2digit

from modules.config import AppConfig, AppState
from modules.data import (
    CredentialManager,
    HistoryManager,
    ReplacementManager,
    StatsManager,
)
from modules.utils import SoundManager, SuppressStderr

# --- Classes ---


class AudioManager:
    """
    Controls audio recording using PyAudio and manages system volume via the OS interface.
    """

    def __init__(
        self, app_state: AppState, sound_manager: SoundManager, os_interface: Any
    ) -> None:
        self.app_state = app_state
        self.sound_manager = sound_manager
        self.os_interface = os_interface

        self._pyaudio_instance: Optional[pyaudio.PyAudio] = None
        self._audio_stream: Optional[pyaudio.Stream] = None
        self._original_volume: float = 1.0
        self._is_system_muted_by_app: bool = False
        self._silence_callback: Optional[Callable[[], None]] = None

    def warmup(self) -> None:
        """
        Placeholder method for warming up audio components if necessary.
        Kept for compatibility with the main application loop.
        """
        pass

    def initialize(self) -> bool:
        """
        Initializes the PyAudio instance if not already active.
        Returns True if successful, False otherwise.
        """
        if self._pyaudio_instance:
            return True
        logging.info("Initializing PyAudio...")
        try:
            with SuppressStderr():
                self._pyaudio_instance = pyaudio.PyAudio()
            self.app_state.pyaudio_instance = self._pyaudio_instance
            return True
        except Exception as e:
            logging.critical(f"PyAudio init failed: {e}")
            return False

    def terminate(self) -> None:
        """
        Stops the audio stream and terminates the PyAudio instance.
        """
        logging.info("Stopping audio services...")
        if self._audio_stream:
            try:
                if self._audio_stream.is_active():
                    self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception:
                pass
            finally:
                self._audio_stream = None
        if self._pyaudio_instance:
            try:
                self._pyaudio_instance.terminate()
            except Exception:
                pass
            finally:
                self._pyaudio_instance = None

    def start_recording(
        self, on_silence_callback: Optional[Callable[[], None]] = None
    ) -> None:
        """
        Starts the audio recording process in a background thread.
        Triggers UI updates and manages system mute state.
        """
        if not self.app_state.pyaudio_instance and not self.initialize():
            return
        self.app_state.is_busy = True
        self.app_state.is_recording = True
        self.app_state.recording_start_time = time.time()

        self._silence_callback = on_silence_callback

        if self.app_state.window:
            try:
                self.app_state.window.evaluate_js("setSettingsButtonState(true)")
                self.app_state.window.evaluate_js(
                    "window.dispatchEvent(new CustomEvent('pywebview', { detail: 'start_recording' }))"
                )
            except Exception:
                pass

        threading.Thread(
            target=self._play_sound_and_mute_in_background, daemon=True
        ).start()

        temp_path = os.path.join(tempfile.gettempdir(), AppConfig.AUDIO_OUTPUT_FILENAME)
        threading.Thread(
            target=self._record_audio_worker, args=(temp_path,), daemon=True
        ).start()

    def stop_recording(self) -> None:
        """
        Signals the recording loop to stop and restores system volume.
        """
        if self.app_state.is_recording:
            self.app_state.is_recording = False
            self.unmute_system_volume()

    def _play_sound_and_mute_in_background(self) -> None:
        if self.app_state.sound_enabled:
            try:
                self.sound_manager.play("beep_on")
            except Exception:
                pass
        self.app_state.was_muted_during_recording = self.app_state.mute_sound
        if self.app_state.mute_sound:
            self.mute_system_volume()

    def _record_audio_worker(self, filename: str) -> None:
        """
        Background worker that reads audio frames from the stream and saves them to a WAV file.
        Also computes visualizer data for the UI.
        """
        frames: List[bytes] = []
        stream = None

        if self._pyaudio_instance is None:
            logging.error("PyAudio not initialized")
            return

        try:
            stream = self._pyaudio_instance.open(
                format=AppConfig.AUDIO_FORMAT,
                channels=AppConfig.AUDIO_CHANNELS,
                rate=AppConfig.AUDIO_RATE,
                input=True,
                frames_per_buffer=AppConfig.AUDIO_CHUNK,
            )
            self._audio_stream = stream
        except Exception:
            self.app_state.is_recording = False
            return

        viz_enabled = True
        window = self.app_state.window

        try:
            while self.app_state.is_recording:
                try:
                    data = stream.read(
                        AppConfig.AUDIO_CHUNK, exception_on_overflow=False
                    )
                    frames.append(data)

                    if viz_enabled and window:
                        try:
                            audio_array = np.frombuffer(data, dtype=np.int16)
                            # Simple calculation for the visualizer
                            samples = len(audio_array) // AppConfig.VISUALIZER_POINTS
                            if samples > 0:
                                reshaped = audio_array[
                                    : samples * AppConfig.VISUALIZER_POINTS
                                ].reshape(AppConfig.VISUALIZER_POINTS, -1)

                                visualizer_data = (
                                    np.max(np.abs(reshaped), axis=1)
                                    / AppConfig.VISUALIZER_SCALING_FACTOR
                                ).astype(int)

                                np.clip(
                                    visualizer_data,
                                    0,
                                    AppConfig.VISUALIZER_MAX_HEIGHT,
                                    out=visualizer_data,
                                )
                                window.evaluate_js(
                                    f"updateVisualizer({visualizer_data.tolist()})"
                                )
                        except Exception:
                            viz_enabled = False
                except IOError:
                    break
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
                self._audio_stream = None

            if frames:
                try:
                    with wave.open(filename, "wb") as wave_file:
                        wave_file.setnchannels(AppConfig.AUDIO_CHANNELS)
                        wave_file.setsampwidth(
                            self._pyaudio_instance.get_sample_size(
                                AppConfig.AUDIO_FORMAT
                            )
                        )
                        wave_file.setframerate(AppConfig.AUDIO_RATE)
                        wave_file.writeframes(b"".join(frames))
                    logging.info(f"Audio saved: {filename}")
                except Exception as e:
                    logging.critical(f"WAV write error: {e}")

    def mute_system_volume(self) -> None:
        """
        Mutes the system volume if configured to do so.
        """
        if not self.app_state.mute_sound or self._is_system_muted_by_app:
            return
        try:
            self._original_volume = self.os_interface.mute_system_volume()
            self._is_system_muted_by_app = True
        except Exception:
            self._is_system_muted_by_app = False

    def unmute_system_volume(self) -> None:
        """
        Restores the system volume to its original level.
        """
        if not self._is_system_muted_by_app:
            return
        try:
            self.os_interface.unmute_system_volume(self._original_volume)
        except Exception:
            pass
        finally:
            self._is_system_muted_by_app = False


class TranscriptionService:
    """
    Handles audio transcription using various providers (Groq/Whisper, Deepgram).
    Also handles post-processing like number conversion and text replacement.
    """

    def __init__(
        self,
        app_state: AppState,
        replacement_manager: ReplacementManager,
        credential_manager: CredentialManager,
    ) -> None:
        self.app_state = app_state
        self.replacement_manager = replacement_manager
        self.credential_manager = credential_manager

    def warmup(self) -> None:
        """
        Pre-initializes API clients in a background thread to reduce latency.
        """

        def _warmup_worker():
            try:
                groq_api_key = self.credential_manager.get_api_key(
                    "groq_audio"
                ) or self.credential_manager.get_api_key("ai")
                if groq_api_key and self.app_state.groq_client is None:
                    self.app_state.groq_client = Groq(api_key=groq_api_key)
                    logging.info("Transcription Service: Groq client warmed up.")

                deepgram_api_key = self.credential_manager.get_api_key("deepgram")
                if deepgram_api_key and self.app_state.deepgram_client is None:
                    self.app_state.deepgram_client = DeepgramClient(deepgram_api_key)
                    logging.info("Transcription Service: Deepgram client warmed up.")
            except Exception:
                pass

        threading.Thread(target=_warmup_worker, daemon=True).start()

    def apply_replacements(self, text: str) -> str:
        """
        Applies user-defined word replacements to the transcript.
        """
        if not text:
            return ""
        try:
            replacements = self.replacement_manager.load()
            for item in replacements:
                if item.get("word1") and item.get("word2"):
                    text = text.replace(item["word1"], item["word2"])
            return text
        except Exception:
            return text

    def convert_numbers(self, transcript: str, language: str) -> str:
        """
        Converts spelled-out numbers to digits based on the language.
        """
        if not transcript:
            return ""
        try:
            # Normalize hyphens for specific languages before conversion
            if language == "fr":
                words_fr = "et|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|quatorze|quinze|seize|vingt|trente|quarante|cinquante|soixante|cent|cents|mille|milles"
                pattern_fr = r"\b((?:{0})(?:-(?:{0}))+)\b".format(words_fr)
                transcript = re.sub(
                    pattern_fr,
                    lambda m: m.group(0).replace("-", " "),
                    transcript,
                    flags=re.IGNORECASE,
                )
            elif language == "en":
                words_en = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million"
                pattern_en = r"\b((?:{0})(?:-(?:{0}))+)\b".format(words_en)
                transcript = re.sub(
                    pattern_en,
                    lambda m: m.group(0).replace("-", " "),
                    transcript,
                    flags=re.IGNORECASE,
                )
            return alpha2digit(transcript, lang=language)
        except Exception:
            return transcript

    def _init_timing(self) -> Tuple[Dict[str, Any], float, Callable[[str, str], None]]:
        """
        Helper to initialize performance tracking.
        """
        tracker: Dict[str, Any] = {}
        start_time = time.perf_counter()
        step_start = start_time

        def log_step(name: str, desc: str = "") -> None:
            nonlocal step_start
            now = time.perf_counter()
            tracker[name] = {"duration": f"{now - step_start:.4f}", "desc": desc}
            logging.debug(f"TIMING [{name}] {now - step_start:.4f}s | {desc}")
            step_start = now

        return tracker, start_time, log_step

    def _optimize_audio_in_memory(self, original_path: str) -> Union[str, io.BytesIO]:
        """
        Reads the WAV file into memory to avoid disk I/O latency during API calls.
        """
        try:
            with open(original_path, "rb") as f:
                file_data = f.read()

            buffer = io.BytesIO(file_data)
            buffer.name = "audio.wav"  # Important for API file type detection

            logging.debug(f"Audio loaded raw ({len(file_data)} bytes).")
            return buffer
        except Exception as e:
            logging.error(f"Failed to load raw audio: {e}")
            return original_path

    def _transcribe_ai(self, filename: str, lang: str, log_step: Callable) -> str:
        """
        Performs transcription using Groq (OpenAI-compatible) API.
        """
        try:
            if self.app_state.groq_client is None:
                api_key = self.credential_manager.get_api_key(
                    "groq_audio"
                ) or self.credential_manager.get_api_key("ai")
                if not api_key:
                    return "Error: Missing Groq Key."
                self.app_state.groq_client = Groq(api_key=api_key)
                log_step("05_ai_init", "Groq client created")
            else:
                log_step("05_ai_init", "Groq client cached")

            client = self.app_state.groq_client
            file_obj = self._optimize_audio_in_memory(filename)

            # Fix: Explicitly type params as Dict[str, Any] to allow tuple assignment
            params: Dict[str, Any] = {"model": self.app_state.audio_model}
            if lang and lang != "autodetect":
                params["language"] = lang

            if isinstance(file_obj, str):
                with open(file_obj, "rb") as f:
                    params["file"] = (os.path.basename(file_obj), f.read())
            else:
                params["file"] = (file_obj.name, file_obj.read())

            log_step("07_ai_read", "Audio prepared")
            transcription = client.audio.transcriptions.create(**params)
            log_step("08_ai_call", "API called")

            return transcription.text or "Error: Empty result."

        except Exception as e:
            logging.error(f"Whisper Error: {e}")
            return "Error: Transcription failed."

    def _transcribe_deepgram(self, filename: str, lang: str, log_step: Callable) -> str:
        """
        Performs transcription using Deepgram API.
        """
        try:
            if self.app_state.deepgram_client is None:
                api_key = self.credential_manager.get_api_key("deepgram")
                if not api_key:
                    return "Error: Deepgram key missing."
                self.app_state.deepgram_client = DeepgramClient(api_key)
                log_step("05_dg_init", "Deepgram client created")
            else:
                log_step("05_dg_init", "Deepgram client cached")

            deepgram_client = self.app_state.deepgram_client
            file_obj = self._optimize_audio_in_memory(filename)

            # Fix: Explicitly type payload as FileSource
            payload: FileSource
            if isinstance(file_obj, str):
                with open(file_obj, "rb") as f:
                    payload = {"buffer": f.read()}
            else:
                payload = {"buffer": file_obj.read()}

            options = PrerecordedOptions(
                model=self.app_state.audio_model,
                language=lang,
                smart_format=True,
                numerals=False,
                punctuate=True,
            )
            response = deepgram_client.listen.rest.v("1").transcribe_file(
                payload, options, timeout=(15, 45)
            )
            log_step("08_dg_call", "API called")

            if response.results and response.results.channels:
                return response.results.channels[0].alternatives[0].transcript
            return "Error: Empty response."

        except Exception as e:
            logging.error(f"Deepgram Error: {e}")
            return "Error: Deepgram failed."

    def transcribe(self, filename: str, lang: str, duration: float) -> str:
        """
        Main entry point for transcription. Selects the appropriate engine.
        """
        tracker, start_time, log_step = self._init_timing()
        log_step("00_start", f"File: {os.path.basename(filename)}")

        try:
            if not os.path.exists(filename) or os.path.getsize(filename) < 1024:
                return "Error: Audio file invalid."

            model = self.app_state.audio_model
            logging.info(f"[AUDIO MODEL] Using model: {model} (Language: {lang})")

            transcript: str = ""
            if model.startswith("whisper"):
                transcript = self._transcribe_ai(filename, lang, log_step)
            elif model.startswith("nova"):
                transcript = self._transcribe_deepgram(filename, lang, log_step)
            else:
                return f"Error: Unknown model '{model}'."

            if transcript.startswith("Error"):
                return transcript

            if lang in {"fr", "en", "es", "pt", "de", "ru"}:
                transcript = self.convert_numbers(transcript, lang)
            log_step("21_numbers", "Numbers converted")

            final_text = self.apply_replacements(transcript)
            log_step("23_final", "Replacements done")

            logging.info(
                f"Transcription finished: {duration:.2f}s audio -> {time.perf_counter() - start_time:.2f}s processing."
            )
            return final_text

        finally:
            if time.perf_counter() - start_time > 5.0:
                logging.warning("Performance: Slow transcription.")


class TranscriptionManager:
    """
    Orchestrates the flow: Stop Recording -> Transcribe -> Paste -> Update Stats.
    """

    def __init__(
        self,
        app_state: AppState,
        audio_manager: AudioManager,
        sound_manager: SoundManager,
        stats_manager: StatsManager,
        history_manager: HistoryManager,
        transcription_service: TranscriptionService,
        event_bus: Any,
    ) -> None:
        self.app_state = app_state
        self.audio_manager = audio_manager
        self.sound_manager = sound_manager
        self.stats_manager = stats_manager
        self.history_manager = history_manager
        self.transcription_service = transcription_service
        self.event_bus = event_bus
        self.temp_dir = tempfile.gettempdir()
        self.audio_file = os.path.join(self.temp_dir, AppConfig.AUDIO_OUTPUT_FILENAME)

    def _restore_clipboard_worker(self, content: str) -> None:
        """
        Attempts to restore the clipboard to its previous state.
        """
        for _ in range(5):
            try:
                pyperclip.copy(content)
                if pyperclip.paste() == content:
                    return
            except Exception:
                pass
            time.sleep(0.2)

    def _wait_for_file(self, filepath: str) -> bool:
        """
        Waits briefly for the audio file to be written to disk.
        """
        start = time.time()
        while time.time() - start < 2.0:
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                return True
            time.sleep(0.05)
        return False

    def stop_recording_and_transcribe(
        self, timing_tracker: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Stops the recording, triggers transcription, pastes the result,
        and updates application stats.
        """
        start_time = time.perf_counter()
        local_clipboard = ""

        if timing_tracker is None:
            timing_tracker = {}

        def log_timing_step(step_name: str, description: str = "") -> None:
            elapsed = time.perf_counter() - start_time
            timing_tracker[step_name] = {
                "duration_s": f"{elapsed:.6f}",
                "description": description,
            }

        if not self.app_state.is_recording:
            return timing_tracker

        rec_duration = time.time() - self.app_state.recording_start_time
        self.app_state.is_recording = False

        self.event_bus.publish("transcription_started", None)
        if self.app_state.window:
            try:
                self.app_state.window.evaluate_js(
                    "window.dispatchEvent(new CustomEvent('pywebview', { detail: 'stop_recording' }))"
                )
            except Exception:
                pass

        try:
            hwnd = win32gui.FindWindow(None, "Ozmoz")
            if hwnd and win32gui.IsWindowVisible(hwnd):
                time.sleep(0.1)
                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
        except Exception:
            pass

        try:
            local_clipboard = pyperclip.paste()
        except Exception:
            pass

        transcribed_text: Optional[str] = None
        try:
            if self.app_state.was_muted_during_recording:
                self.audio_manager.unmute_system_volume()
                self.app_state.was_muted_during_recording = False

            if self.app_state.sound_enabled:
                self.sound_manager.play("beep_off")
            if not self._wait_for_file(self.audio_file):
                return timing_tracker

            transcribed_text = self.transcription_service.transcribe(
                self.audio_file, self.app_state.language, rec_duration
            )

            if not transcribed_text or transcribed_text.startswith("Error"):
                pyperclip.copy("Error: Transcription failed.")
            else:
                pyperclip.copy(transcribed_text)

            keyboard.press_and_release("ctrl+v")
            time.sleep(0.25)
            threading.Thread(
                target=self._restore_clipboard_worker,
                args=(local_clipboard,),
                daemon=True,
            ).start()

            def update_stats():
                try:
                    if transcribed_text:
                        self.stats_manager.update_stats(
                            transcribed_text,
                            rec_duration,
                            time.perf_counter() - start_time,
                            False,
                        )
                        self.history_manager.add_entry(transcribed_text)
                    if self.app_state.settings_window:
                        self.app_state.settings_window.evaluate_js(
                            "refreshDashboardFull()"
                        )
                except Exception:
                    pass

            threading.Thread(target=update_stats, daemon=True).start()
            self.event_bus.publish(
                "transcription_complete",
                {"text": transcribed_text, "source": "dictation"},
            )

        except Exception as e:
            logging.critical(f"Workflow error: {e}")
            pyperclip.copy(f"Error: {e}")
            keyboard.press_and_release("ctrl+v")
            threading.Thread(
                target=self._restore_clipboard_worker,
                args=(local_clipboard,),
                daemon=True,
            ).start()

        finally:
            self.app_state.is_busy = False
            self.app_state.recording_start_time = 0.0
            try:
                if os.path.exists(self.audio_file):
                    threading.Thread(
                        target=os.remove, args=(self.audio_file,), daemon=True
                    ).start()
                if self.app_state.window:
                    self.app_state.window.evaluate_js("setSettingsButtonState(false);")
            except Exception:
                pass

            log_timing_step("99_cleanup_complete", "Finished")

        return timing_tracker
