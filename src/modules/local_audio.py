"""
Local Audio Inference Module for Ozmoz.

This module manages the lifecycle of the local speech-to-text engine using Faster-Whisper.
It handles:
- Portable CUDA setup (injecting NVIDIA libraries from venv).
- Model downloading and verification.
- Intelligent VRAM management and CPU fallback strategies.
- High-performance transcription with VAD (Voice Activity Detection).
"""

import logging
import os
import sys
import threading
import time
from typing import Optional

# --- Third-Party Imports ---
import numpy as np
from faster_whisper import WhisperModel

# --- Local Imports ---
from modules.utils import PathManager


class LocalWhisperManager:
    """
    Singleton manager for the local Faster-Whisper inference engine.

    Features:
    - Thread-safe initialization and execution.
    - Automatic hardware acceleration detection (CUDA vs CPU).
    - Robust fallback mechanism for older hardware.
    """

    # Using the INT8 quantization of the large-v3-turbo model for optimal speed/accuracy balance
    MODEL_ID: str = "deepdml/faster-whisper-large-v3-turbo-ct2"

    def __init__(self) -> None:
        """Initialize the manager and define the storage path for models."""
        self.models_directory: str = str(PathManager.get_user_data_path("data/models"))
        self.model_instance: Optional[WhisperModel] = None
        self.is_loading: bool = False
        self._lock: threading.Lock = threading.Lock()

        # Ensure the directory exists
        try:
            os.makedirs(self.models_directory, exist_ok=True)
        except OSError as error:
            logging.error(f"Failed to create models directory: {error}")

    def setup_portable_cuda(self) -> None:
        """
        Injects NVIDIA libraries found in the Python virtual environment into the system PATH.
        This allows CT2/Faster-Whisper to find cuDNN and Cublas without a system-wide install.
        """
        try:
            # Find site-packages directory
            site_packages = next(
                (p for p in sys.path if "site-packages" in p and os.path.isdir(p)), None
            )

            if site_packages:
                nvidia_path = os.path.join(site_packages, "nvidia")
                if os.path.exists(nvidia_path):
                    injected_count = 0
                    for root, dirs, _ in os.walk(nvidia_path):
                        # Add bin and lib directories to PATH
                        if "bin" in dirs:
                            os.environ["PATH"] += os.pathsep + os.path.join(root, "bin")
                            injected_count += 1
                        if "lib" in dirs:
                            os.environ["PATH"] += os.pathsep + os.path.join(root, "lib")
                            injected_count += 1

                    if injected_count > 0:
                        logging.debug(
                            f"[LocalWhisper] Injected {injected_count} NVIDIA library paths."
                        )
        except Exception as error:
            logging.warning(f"[LocalWhisper] Portable CUDA setup warning: {error}")

    def is_installed(self) -> bool:
        """
        Checks if the model files are present in the data directory.

        Returns:
            bool: True if 'model.bin' exists, False otherwise.
        """
        if not os.path.exists(self.models_directory):
            return False

        # Simple check for the binary weights file
        for _, _, files in os.walk(self.models_directory):
            if "model.bin" in files:
                return True
        return False

    def download(self) -> bool:
        """
        Downloads the model files from HuggingFace Hub.
        This operation is thread-locked to prevent concurrent downloads.

        Returns:
            bool: True if download was successful, False otherwise.
        """
        with self._lock:
            if self.is_loading:
                logging.warning("[LocalWhisper] Download already in progress.")
                return False
            self.is_loading = True

        try:
            logging.info(f"[LocalWhisper] Starting download of {self.MODEL_ID}...")

            # Initialize WhisperModel with download_root triggers the download
            # Using CPU/int8 for the download phase ensures compatibility
            WhisperModel(
                self.MODEL_ID,
                device="cpu",
                compute_type="int8",
                download_root=self.models_directory,
            )

            logging.info("[LocalWhisper] Download completed successfully.")
            return True
        except Exception as error:
            logging.error(f"[LocalWhisper] Download failed: {error}", exc_info=True)
            return False
        finally:
            self.is_loading = False

    def _warmup_engine(self) -> None:
        """
        Performs a dummy inference to load kernels into memory/VRAM.
        """
        active_model = self.model_instance
        if not active_model:
            return

        logging.debug("[LocalWhisper] Warming up inference engine...")
        try:
            # Generate 1 second of silence
            dummy_audio = np.zeros(16000, dtype=np.float32)
            active_model.transcribe(dummy_audio, beam_size=1)

            device_type = active_model.model.device
            logging.info(f"[LocalWhisper] Engine ready on: {device_type.upper()}")
        except Exception as error:
            logging.warning(f"[LocalWhisper] Warmup warning: {error}")

    def load(self) -> bool:
        """
        Initializes the Whisper engine.
        Attempts to load on GPU (auto) with float16 precision.
        Falls back to CPU (int8) if GPU initialization fails.

        Returns:
            bool: True if loaded successfully, False otherwise.
        """
        if not self.is_installed():
            logging.info("[LocalWhisper] Model not installed. Skipping auto-load.")
            return False

        if self.model_instance is not None:
            return True

        self.setup_portable_cuda()
        logging.info("[LocalWhisper] Loading engine...")

        # Attempt 1: High Performance (GPU)
        try:
            self.model_instance = WhisperModel(
                self.MODEL_ID,
                device="auto",
                compute_type="int8_float16",
                download_root=self.models_directory,
            )
            self._warmup_engine()
            return True
        except Exception as error:
            logging.warning(
                f"[LocalWhisper] High-perf load failed ({error}). Switching to compatibility mode."
            )
            self.model_instance = None

        # Attempt 2: Compatibility Mode (CPU)
        try:
            logging.info("[LocalWhisper] Attempting CPU fallback (Int8)...")
            self.model_instance = WhisperModel(
                self.MODEL_ID,
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
                download_root=self.models_directory,
            )
            self._warmup_engine()
            return True
        except Exception as error:
            logging.critical(
                f"[LocalWhisper] Critical: CPU Fallback failed: {error}", exc_info=True
            )
            self.model_instance = None
            return False

    def transcribe(self, audio_file_path: str, language: str = "fr") -> str:
        """
        Transcribes the given audio file using the local model.

        Args:
            audio_file_path (str): Path to the WAV file.
            language (str): Language code (e.g., 'fr', 'en') or 'autodetect'.

        Returns:
            str: The transcribed text or an error message.
        """
        if not self.is_installed():
            return "Error: Local model not found"

        # Lazy loading
        if self.model_instance is None:
            if not self.load():
                return "Error: Local model failed to load (Check logs/hardware)."

        active_model = self.model_instance
        if active_model is None:
            return "Error: Model failed to initialize."

        try:
            start_time = time.time()
            language_arg = language if language and language != "autodetect" else None

            # Optimized parameters for dictation use-case
            segments, info = active_model.transcribe(
                audio_file_path,
                beam_size=1,  # Greedy decoding for speed
                best_of=1,
                temperature=0,
                language=language_arg,
                condition_on_previous_text=False,
                log_prob_threshold=None,
                compression_ratio_threshold=2.4,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=50),
            )

            # Consolidate generator output
            transcribed_text = " ".join([segment.text for segment in segments]).strip()

            duration = time.time() - start_time
            logging.info(
                f"[LocalWhisper] Transcribed in {duration:.2f}s "
                f"(Language: {info.language}, Probability: {info.language_probability:.0%})"
            )

            return transcribed_text

        except Exception as error:
            logging.error(f"[LocalWhisper] Inference error: {error}", exc_info=True)
            return f"Error: {error}"


# Singleton Instance
local_whisper = LocalWhisperManager()
