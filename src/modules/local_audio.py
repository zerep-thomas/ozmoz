"""
Handles local speech-to-text inference using Faster-Whisper.
Manages portable CUDA setup, model lifecycle, and robust fallback strategies.
Optimized for maximum throughput and low latency.
"""

import logging
import os
import sys
import threading
import time
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

from modules.utils import PathManager


class LocalWhisperManager:
    """
    Singleton manager for the local Faster-Whisper model.
    Handles download, VRAM loading, and transcription requests with CPU fallback.
    """

    MODEL_ID = "deepdml/faster-whisper-large-v3-turbo-ct2"

    def __init__(self) -> None:
        self.models_dir = PathManager.get_user_data_path("data/models")
        self.model: Optional[WhisperModel] = None
        self.is_loading = False
        self._lock = threading.Lock()

        os.makedirs(self.models_dir, exist_ok=True)

    def setup_portable_cuda(self) -> None:
        """
        Injects NVIDIA libraries found in the Python virtual environment into the system PATH.
        """
        try:
            site_packages = next(
                (p for p in sys.path if "site-packages" in p and os.path.isdir(p)), None
            )
            if site_packages:
                nvidia_path = os.path.join(site_packages, "nvidia")
                if os.path.exists(nvidia_path):
                    count = 0
                    for root, dirs, _ in os.walk(nvidia_path):
                        if "bin" in dirs:
                            os.environ["PATH"] += os.pathsep + os.path.join(root, "bin")
                            count += 1
                        if "lib" in dirs:
                            os.environ["PATH"] += os.pathsep + os.path.join(root, "lib")
                            count += 1
                    if count > 0:
                        logging.debug(f"[LocalWhisper] Injected {count} NVIDIA paths.")
        except Exception as e:
            logging.warning(f"[LocalWhisper] CUDA setup warning: {e}")

    def is_installed(self) -> bool:
        if not os.path.exists(self.models_dir):
            return False
        for _, _, files in os.walk(self.models_dir):
            if "model.bin" in files:
                return True
        return False

    def download(self) -> bool:
        with self._lock:
            if self.is_loading:
                logging.warning("[LocalWhisper] Download already in progress.")
                return False
            self.is_loading = True

        try:
            logging.info(f"[LocalWhisper] Starting download of {self.MODEL_ID}...")

            WhisperModel(
                self.MODEL_ID,
                device="cpu",
                compute_type="int8",
                download_root=str(self.models_dir),
            )

            logging.info("[LocalWhisper] Download completed successfully.")
            return True
        except Exception as e:
            logging.error(f"[LocalWhisper] Download failed: {e}", exc_info=True)
            return False
        finally:
            self.is_loading = False

    def _warmup_engine(self) -> None:
        local_model = self.model
        if not local_model:
            return
        logging.debug("[LocalWhisper] Warming up engine...")
        dummy_audio = np.zeros(16000, dtype=np.float32)
        local_model.transcribe(dummy_audio, beam_size=1)
        device = local_model.model.device
        logging.info(f"[LocalWhisper] Engine ready on: {device.upper()}")

    def load(self) -> bool:
        if not self.is_installed():
            logging.info("[LocalWhisper] Model not installed. Skipping auto-load.")
            return False

        if self.model is not None:
            return True

        self.setup_portable_cuda()
        logging.info("[LocalWhisper] Loading engine...")

        try:
            self.model = WhisperModel(
                self.MODEL_ID,
                device="auto",
                compute_type="int8_float16",
                download_root=str(self.models_dir),
            )
            self._warmup_engine()
            return True
        except Exception as e:
            logging.warning(
                f"[LocalWhisper] High-perf load failed ({e}). Switching to compatibility mode."
            )
            self.model = None

        try:
            logging.info("[LocalWhisper] Attempting CPU fallback (Int8)...")
            self.model = WhisperModel(
                self.MODEL_ID,
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
                download_root=str(self.models_dir),
            )
            self._warmup_engine()
            return True
        except Exception as e:
            logging.error(
                f"[LocalWhisper] Critical: CPU Fallback failed: {e}", exc_info=True
            )
            self.model = None
            return False

    def transcribe(self, audio_path: str, lang: str = "fr") -> str:
        if not self.is_installed():
            return "Error: Local model not found"

        if self.model is None:
            if not self.load():
                return "Error: Local model failed to load (Check logs/hardware)."

        active_model = self.model
        if active_model is None:
            return "Error: Model failed to initialize."

        try:
            start_time = time.time()
            language_arg = lang if lang and lang != "autodetect" else None

            segments, info = active_model.transcribe(
                audio_path,
                beam_size=1,
                best_of=1,
                temperature=0,
                language=language_arg,
                condition_on_previous_text=False,
                log_prob_threshold=None,
                compression_ratio_threshold=2.4,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=50),
            )

            text = " ".join([s.text for s in segments]).strip()

            duration = time.time() - start_time
            logging.info(
                f"[LocalWhisper] Transcribed in {duration:.2f}s (Conf: {info.language_probability:.0%})"
            )

            return text

        except Exception as e:
            logging.error(f"[LocalWhisper] Inference error: {e}", exc_info=True)
            return f"Error: {e}"


local_whisper = LocalWhisperManager()
