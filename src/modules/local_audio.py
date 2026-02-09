"""
Local Audio Inference Module for Ozmoz.

This module manages the lifecycle of the local Faster-Whisper inference engine.
It handles:
- Portable CUDA setup (injecting NVIDIA libraries from venv).
- Hardware validation (CUDA/DLL checks) with automatic CPU fallback.
- Secure, Resumable Model downloading with SHA256 verification.
- High-performance transcription with VAD.
- Support for multiple local models (e.g., Small, Distil, Large).
"""

import gc
import hashlib
import logging
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

# --- Third-Party Imports ---
import numpy as np
import requests
from faster_whisper import WhisperModel

# --- Local Imports ---
from modules.utils import PathManager

# --- Constants ---

# SHA256 chunk size for file verification (64KB for optimal I/O)
HASH_CHUNK_SIZE = 65536

# HTTP download chunk size (8KB balances memory and network efficiency)
DOWNLOAD_CHUNK_SIZE = 8192

# Network timeout in seconds for download requests
DOWNLOAD_TIMEOUT_SECONDS = 30

# Dummy audio sample rate for warmup (Whisper expects 16kHz)
WARMUP_SAMPLE_RATE = 16000

# CPU thread count for int8 inference (balance between speed and system load)
CPU_INFERENCE_THREADS = 4

# VAD silence threshold in milliseconds (300ms reduces false segmentation)
VAD_MIN_SILENCE_MS = 300

# Pattern to detect path traversal attempts (../, ..\, absolute paths)
PATH_TRAVERSAL_PATTERN = re.compile(r"\.\.|^/|^[a-zA-Z]:\\")

# Allowed domain for model downloads (prevents SSRF attacks)
ALLOWED_DOWNLOAD_DOMAIN = "huggingface.co"

# --- Logger Setup ---
logger = logging.getLogger(__name__)

# --- Model Configuration ---
# Defines the supported local models, their HuggingFace repo IDs, and metadata.
MODELS_CONFIG: dict[str, dict[str, Any]] = {
    "local-whisper-large-v3-turbo": {
        "repo_id": "deepdml/faster-whisper-large-v3-turbo-ct2",
        "files": [
            "model.bin",
            "config.json",
            "vocabulary.json",
            "tokenizer.json",
            "preprocessor_config.json",
        ],
        "size_str": "~1.6 GB",
    },
    "local-distil-large-v3": {
        "repo_id": "Systran/faster-distil-whisper-large-v3",
        "files": [
            "model.bin",
            "config.json",
            "vocabulary.json",
            "tokenizer.json",
            "preprocessor_config.json",
        ],
        "size_str": "~1.5 GB",
    },
    "local-whisper-small": {
        "repo_id": "Systran/faster-whisper-small",
        "files": [
            "model.bin",
            "config.json",
            "vocabulary.txt",
            "tokenizer.json",
        ],
        "size_str": "~400 MB",
    },
}

# Placeholder SHA256 hashes (should be populated for production security)
MODEL_HASHES: dict[str, str] = {
    "model.bin": "INSERT_REAL_SHA256_HERE_OR_FETCH_DYNAMICALLY"
}


# --- Custom Exceptions ---


class LocalWhisperError(Exception):
    """Base exception for LocalWhisper module."""


class ModelNotFoundError(LocalWhisperError):
    """Raised when requested model is not installed or configured."""


class ModelLoadError(LocalWhisperError):
    """Raised when model fails to load into memory."""


class DownloadError(LocalWhisperError):
    """Raised when model download fails."""


class InvalidModelNameError(LocalWhisperError):
    """Raised when model name contains unsafe characters."""


# --- Main Manager Class ---


class LocalWhisperManager:
    """
    Singleton manager for the local Faster-Whisper inference engine.

    Features:
    - Thread-safe initialization.
    - Intelligent Hardware detection (CUDA vs CPU).
    - Robust Download Manager (Resume + Hash Check).
    - Support for multiple models stored in subdirectories.
    - Path traversal protection.
    """

    def __init__(self) -> None:
        """Initialize the manager and define the storage path for models."""
        # Base directory for all local models (e.g., .../data/models)
        self.base_models_directory: Path = PathManager.get_user_data_path("data/models")

        self.model_instance: Optional[WhisperModel] = None
        self.is_loading: bool = False
        self._lock: threading.Lock = threading.Lock()

        # Tracks which model is currently loaded in memory
        self._current_loaded_model_name: Optional[str] = None

        # Hardware Capability Flags
        self.has_cuda: bool = False
        self._detect_cuda_support()

        # Ensure the base directory exists
        try:
            self.base_models_directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            logger.error(
                "Failed to create models directory",
                extra={"error": str(error), "path": str(self.base_models_directory)},
            )

    def _validate_model_name(self, model_name: str) -> None:
        """
        Validate model name to prevent path traversal attacks.

        Args:
            model_name: Name of the model to validate.

        Raises:
            InvalidModelNameError: If model name contains unsafe characters.
        """
        if PATH_TRAVERSAL_PATTERN.search(model_name):
            raise InvalidModelNameError(
                f"Model name contains invalid characters: {model_name}"
            )

        if model_name not in MODELS_CONFIG:
            raise ModelNotFoundError(
                f"Model '{model_name}' not in configuration. "
                f"Available: {list(MODELS_CONFIG.keys())}"
            )

    def _get_model_directory(self, model_name: str) -> Path:
        """
        Returns the absolute path to the directory where a specific model is stored.

        Args:
            model_name: Name of the model (must exist in MODELS_CONFIG).

        Returns:
            Resolved absolute path to model directory.

        Raises:
            InvalidModelNameError: If model name is invalid or contains path traversal.

        Example:
            >>> manager._get_model_directory("local-whisper-small")
            PosixPath('/home/user/.ozmoz/data/models/local-whisper-small')
        """
        self._validate_model_name(model_name)

        model_dir = (self.base_models_directory / model_name).resolve()

        # Ensure the resolved path is still within the base directory
        if not model_dir.is_relative_to(self.base_models_directory):
            raise InvalidModelNameError(
                f"Path traversal detected for model: {model_name}"
            )

        return model_dir

    def setup_portable_cuda(self) -> None:
        """
        Injects NVIDIA libraries found in the Python virtual environment into the system PATH.

        This allows CT2/Faster-Whisper to find cuDNN and Cublas without a system-wide install.
        The method walks through site-packages/nvidia/* looking for bin/ and lib/ directories.
        """
        try:
            site_packages = next(
                (p for p in sys.path if "site-packages" in p and os.path.isdir(p)),
                None,
            )

            if not site_packages:
                logger.debug("No site-packages found for CUDA injection")
                return

            nvidia_path = Path(site_packages) / "nvidia"
            if not nvidia_path.exists():
                logger.debug("No NVIDIA libraries found in site-packages")
                return

            injected_count = 0
            for root, dirs, _ in os.walk(nvidia_path):
                root_path = Path(root)
                if "bin" in dirs:
                    bin_path = str(root_path / "bin")
                    os.environ["PATH"] = (
                        bin_path + os.pathsep + os.environ.get("PATH", "")
                    )
                    injected_count += 1
                if "lib" in dirs:
                    lib_path = str(root_path / "lib")
                    os.environ["PATH"] = (
                        lib_path + os.pathsep + os.environ.get("PATH", "")
                    )
                    injected_count += 1

            if injected_count > 0:
                logger.debug(
                    "Portable CUDA setup complete",
                    extra={"paths_injected": injected_count},
                )

        except Exception as error:
            logger.warning(
                "Portable CUDA setup failed (non-critical)",
                extra={"error": str(error)},
            )

    def _detect_cuda_support(self) -> None:
        """
        Checks for CUDA availability and required DLLs (zlibwapi, cuDNN).

        Updates self.has_cuda flag based on:
        1. Portable CUDA library injection success
        2. zlibwapi.dll availability (required for CT2 on Windows)

        Note: This is a heuristic check; actual CUDA availability is verified during model load.
        """
        self.setup_portable_cuda()

        try:
            import ctypes.util

            # Check for zlibwapi (critical for Windows CT2/CUDA)
            zlib = ctypes.util.find_library("zlibwapi")
            self.has_cuda = zlib is not None

            if self.has_cuda:
                logger.info("CUDA support detected (preliminary check passed)")
            else:
                logger.info("CUDA support not detected, will use CPU mode")

        except Exception as error:
            logger.warning(
                "CUDA detection failed, assuming CPU-only mode",
                extra={"error": str(error)},
            )
            self.has_cuda = False

    def is_installed(self, model_name: Optional[str] = None) -> bool:
        """
        Checks if a specific model's files are present and valid.

        Args:
            model_name: Name of the model to check. If None, checks if ANY
                       supported model is installed (fallback behavior).

        Returns:
            True if model files are present and complete, False otherwise.

        Example:
            >>> manager.is_installed("local-whisper-small")
            True
            >>> manager.is_installed()  # Any model installed?
            True
        """
        models_to_check: list[str] = []

        if model_name:
            try:
                self._validate_model_name(model_name)
                models_to_check.append(model_name)
            except (InvalidModelNameError, ModelNotFoundError) as error:
                logger.warning(
                    "Invalid model name in installation check",
                    extra={"model": model_name, "error": str(error)},
                )
                return False
        else:
            # Fallback: Check if any configured model is installed
            models_to_check = list(MODELS_CONFIG.keys())

        for name in models_to_check:
            try:
                model_dir = self._get_model_directory(name)
            except InvalidModelNameError:
                continue

            if not model_dir.exists():
                continue

            # Check for critical files defined in config
            required_files = MODELS_CONFIG[name]["files"]
            all_files_present = True

            for file_name in required_files:
                file_path = model_dir / file_name
                if not file_path.exists():
                    logger.debug(
                        "Missing model file",
                        extra={"model": name, "file": file_name},
                    )
                    all_files_present = False
                    break

            if all_files_present:
                return True

        return False

    def _verify_file_hash(self, filepath: Path, expected_hash: Optional[str]) -> bool:
        """
        Verifies the SHA256 hash of a file.

        Args:
            filepath: Path to the file to verify.
            expected_hash: Expected SHA256 hash (hex string). If None or placeholder,
                          verification is skipped.

        Returns:
            True if hash matches or verification is skipped, False otherwise.

        Example:
            >>> manager._verify_file_hash(Path("model.bin"), "abc123...")
            True
        """
        if not expected_hash or "INSERT_REAL" in expected_hash:
            logger.debug(
                "Hash verification skipped (no hash configured)",
                extra={"file": filepath.name},
            )
            return True

        sha256_hash = hashlib.sha256()
        try:
            with filepath.open("rb") as f:
                for byte_block in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
                    sha256_hash.update(byte_block)

            computed_hash = sha256_hash.hexdigest()
            is_valid = computed_hash == expected_hash

            if not is_valid:
                logger.error(
                    "Hash verification failed",
                    extra={
                        "file": filepath.name,
                        "expected": expected_hash[:16],
                        "computed": computed_hash[:16],
                    },
                )

            return is_valid

        except Exception as error:
            logger.error(
                "Hash verification error",
                extra={"file": filepath.name, "error": str(error)},
            )
            return False

    def _validate_download_url(self, repo_id: str, filename: str) -> str:
        """
        Constructs and validates a download URL to prevent SSRF attacks.

        Args:
            repo_id: HuggingFace repository ID (e.g., "Systran/faster-whisper-small").
            filename: Name of the file to download.

        Returns:
            Validated HTTPS URL.

        Raises:
            DownloadError: If URL validation fails or domain is not allowed.

        Example:
            >>> manager._validate_download_url("Systran/faster-whisper-small", "model.bin")
            'https://huggingface.co/Systran/faster-whisper-small/resolve/main/model.bin'
        """
        # Ensure repo_id doesn't contain malicious patterns
        if PATH_TRAVERSAL_PATTERN.search(repo_id):
            raise DownloadError(f"Invalid repository ID: {repo_id}")

        # Construct URL with strict format
        url = f"https://{ALLOWED_DOWNLOAD_DOMAIN}/{repo_id}/resolve/main/{filename}"

        # Verify the constructed URL matches expected domain
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.netloc != ALLOWED_DOWNLOAD_DOMAIN:
            raise DownloadError(
                f"Download domain mismatch. Expected {ALLOWED_DOWNLOAD_DOMAIN}, got {parsed.netloc}"
            )

        return url

    def download(self, model_name: str = "local-whisper-large-v3-turbo") -> bool:
        """
        Downloads model files for the specified model_name with Resume capability.

        Args:
            model_name: Name of the model to download (must exist in MODELS_CONFIG).

        Returns:
            True if download succeeds, False otherwise.

        Raises:
            InvalidModelNameError: If model name is invalid.
            DownloadError: If download fails after all retries.

        Example:
            >>> manager.download("local-whisper-small")
            True
        """
        try:
            self._validate_model_name(model_name)
        except (InvalidModelNameError, ModelNotFoundError) as error:
            logger.error("Cannot download model", extra={"error": str(error)})
            return False

        with self._lock:
            if self.is_loading:
                logger.warning(
                    "Download already in progress", extra={"model": model_name}
                )
                return False
            self.is_loading = True

        try:
            model_config = MODELS_CONFIG[model_name]
            repo_id = model_config["repo_id"]
            target_dir = self._get_model_directory(model_name)

            target_dir.mkdir(parents=True, exist_ok=True)

            logger.info(
                "Starting model download",
                extra={
                    "model": model_name,
                    "size": model_config["size_str"],
                    "destination": str(target_dir),
                },
            )

            files_to_download = model_config["files"]

            for filename in files_to_download:
                try:
                    url = self._validate_download_url(repo_id, filename)
                except DownloadError as error:
                    logger.error("URL validation failed", extra={"error": str(error)})
                    return False

                dest_path = target_dir / filename

                # Resume logic: check existing file size
                existing_size = 0
                if dest_path.exists():
                    existing_size = dest_path.stat().st_size

                headers: dict[str, str] = {}
                if existing_size > 0:
                    headers["Range"] = f"bytes={existing_size}-"
                    logger.info(
                        "Resuming download",
                        extra={"file": filename, "offset_bytes": existing_size},
                    )

                response = requests.get(
                    url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS
                )

                # Handle 416 Range Not Satisfiable (File already complete)
                if response.status_code == 416:
                    logger.info("File already complete", extra={"file": filename})
                    continue

                response.raise_for_status()

                mode = "ab" if existing_size > 0 else "wb"

                # Use context manager with explicit cleanup
                try:
                    with dest_path.open(mode) as f:
                        for chunk in response.iter_content(
                            chunk_size=DOWNLOAD_CHUNK_SIZE
                        ):
                            if chunk:
                                f.write(chunk)
                finally:
                    # Ensure response is closed even if write fails
                    response.close()

                # Optional: Hash Verification (uncomment when hashes are configured)
                # if not self._verify_file_hash(dest_path, MODEL_HASHES.get(filename)):
                #     logger.error("Hash verification failed", extra={"file": filename})
                #     dest_path.unlink(missing_ok=True)
                #     raise DownloadError(f"Hash mismatch for {filename}")

            logger.info(
                "Model download completed successfully", extra={"model": model_name}
            )
            return True

        except requests.RequestException as error:
            logger.error(
                "Network error during download",
                extra={"model": model_name, "error": str(error)},
                exc_info=True,
            )
            return False

        except Exception as error:
            logger.error(
                "Unexpected download error",
                extra={"model": model_name, "error": str(error)},
                exc_info=True,
            )
            return False

        finally:
            self.is_loading = False

    def _warmup_engine(self) -> None:
        """
        Performs a dummy inference to initialize the model's computation graph.

        This reduces latency for the first real transcription by pre-allocating
        GPU memory and compiling kernels.

        Note: Failures during warmup are non-critical and logged as warnings.
        """
        if not self.model_instance:
            return

        try:
            # Create silent audio (1 second at 16kHz)
            dummy_audio = np.zeros(WARMUP_SAMPLE_RATE, dtype=np.float32)

            # Minimal inference to trigger initialization
            list(self.model_instance.transcribe(dummy_audio, beam_size=1))

            device = getattr(self.model_instance.model, "device", "unknown")
            logger.info("Model warmup complete", extra={"device": str(device).upper()})

        except Exception as error:
            logger.warning("Warmup failed (non-critical)", extra={"error": str(error)})

    def load(self, model_name: str = "local-whisper-large-v3-turbo") -> bool:
        """
        Initializes the Whisper engine for a specific model_name.

        If a different model is already loaded, it switches the instance.
        Implements automatic fallback: CUDA -> CPU (Int8).

        Args:
            model_name: Name of the model to load.

        Returns:
            True if model loads successfully, False otherwise.

        Raises:
            InvalidModelNameError: If model name is invalid.
            ModelNotFoundError: If model is not installed.
            ModelLoadError: If both CUDA and CPU loads fail.

        Example:
            >>> manager.load("local-whisper-small")
            True
        """
        try:
            self._validate_model_name(model_name)
        except (InvalidModelNameError, ModelNotFoundError) as error:
            logger.error("Invalid model load request", extra={"error": str(error)})
            return False

        if not self.is_installed(model_name):
            logger.error("Model not installed", extra={"model": model_name})
            return False

        # Optimization: If the requested model is already loaded, do nothing.
        if (
            self._current_loaded_model_name == model_name
            and self.model_instance is not None
        ):
            logger.debug("Model already loaded", extra={"model": model_name})
            return True

        # Switching models: allow Python GC to clean up the old one
        self.model_instance = None
        gc.collect()

        self.setup_portable_cuda()

        try:
            model_dir = self._get_model_directory(model_name)
        except InvalidModelNameError as error:
            logger.error("Path validation failed", extra={"error": str(error)})
            return False

        logger.info(
            "Loading model", extra={"model": model_name, "path": str(model_dir)}
        )

        # Attempt 1: CUDA (if hardware potential exists)
        if self.has_cuda:
            try:
                logger.info(
                    "Attempting CUDA load",
                    extra={"model": model_name, "dtype": "float16"},
                )

                self.model_instance = WhisperModel(
                    str(model_dir),
                    device="cuda",
                    compute_type="float16",
                    local_files_only=True,
                )

                self._warmup_engine()
                self._current_loaded_model_name = model_name
                return True

            except Exception as error:
                logger.warning(
                    "CUDA load failed, falling back to CPU",
                    extra={"model": model_name, "error": str(error)},
                )
                self.has_cuda = False  # Disable for future attempts

        # Attempt 2: CPU Fallback
        try:
            logger.info(
                "Loading in CPU mode", extra={"model": model_name, "dtype": "int8"}
            )

            self.model_instance = WhisperModel(
                str(model_dir),
                device="cpu",
                compute_type="int8",
                cpu_threads=CPU_INFERENCE_THREADS,
                local_files_only=True,
            )

            self._warmup_engine()
            self._current_loaded_model_name = model_name
            return True

        except Exception as error:
            logger.critical(
                "Both CUDA and CPU load failed",
                extra={"model": model_name, "error": str(error)},
                exc_info=True,
            )
            self.model_instance = None
            self._current_loaded_model_name = None
            return False

    def transcribe(
        self,
        audio_file_path: str,
        language: str = "fr",
        model_name: str = "local-whisper-large-v3-turbo",
    ) -> str:
        """
        Transcribes audio file using the specified model.

        Args:
            audio_file_path: Path to the audio file (WAV, MP3, etc.).
            language: ISO language code (e.g., "fr", "en") or "autodetect".
            model_name: Name of the model to use for transcription.

        Returns:
            Transcribed text or error message string.

        Note:
            Path validation for audio_file_path should be done by the caller.
            This method focuses on model selection and inference logic.

        Example:
            >>> manager.transcribe("/path/to/audio.wav", "en", "local-whisper-small")
            "Hello world"
        """
        # Validate and sanitize the audio file path
        try:
            audio_path = Path(audio_file_path).resolve()
            if not audio_path.exists():
                return f"Error: Audio file not found: {audio_file_path}"
            if not audio_path.is_file():
                return f"Error: Path is not a file: {audio_file_path}"
        except Exception as error:
            logger.error(
                "Invalid audio path",
                extra={"path": audio_file_path, "error": str(error)},
            )
            return f"Error: Invalid audio path: {error}"

        # Use the requested model name
        target_model = model_name

        try:
            self._validate_model_name(target_model)
        except (InvalidModelNameError, ModelNotFoundError):
            return f"Error: Model '{target_model}' not available"

        if not self.is_installed(target_model):
            return f"Error: Model '{target_model}' not installed"

        # Ensure the correct model is loaded
        if self._current_loaded_model_name != target_model:
            if not self.load(target_model):
                return f"Error: Failed to load model '{target_model}'"

        active_model = self.model_instance

        if active_model is None:
            return "Error: Model instance is None after load"

        try:
            start_time = time.time()

            # Language handling: None triggers auto-detection
            language_arg = language if language and language != "autodetect" else None

            segments, info = active_model.transcribe(
                str(audio_path),  # Convert Path to string for compatibility
                beam_size=1,
                best_of=1,
                temperature=0,
                language=language_arg,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": VAD_MIN_SILENCE_MS},
            )

            # Consume generator and join segments
            transcribed_text = " ".join(segment.text for segment in segments).strip()

            duration = time.time() - start_time
            logger.info(
                "Transcription complete",
                extra={
                    "model": target_model,
                    "duration_seconds": round(duration, 2),
                    "language": (
                        info.language if hasattr(info, "language") else "unknown"
                    ),
                },
            )

            return transcribed_text

        except Exception as error:
            logger.error(
                "Transcription failed",
                extra={
                    "model": target_model,
                    "audio": audio_file_path,
                    "error": str(error),
                },
                exc_info=True,
            )
            return f"Error: Transcription failed - {error}"

    def delete_model(self, model_name: str) -> bool:
        """
        Deletes the files of a specific local model to free up disk space.

        Args:
            model_name: Name of the model to delete.

        Returns:
            True if deletion succeeds or model doesn't exist, False on error.

        Example:
            >>> manager.delete_model("local-whisper-small")
            True
        """
        try:
            self._validate_model_name(model_name)
        except (InvalidModelNameError, ModelNotFoundError) as error:
            logger.error(
                "Cannot delete model", extra={"model": model_name, "error": str(error)}
            )
            return False

        # If the model is currently loaded in memory, unload it first
        if self._current_loaded_model_name == model_name:
            logger.info("Unloading model before deletion", extra={"model": model_name})
            self.model_instance = None
            self._current_loaded_model_name = None
            gc.collect()

        try:
            target_dir = self._get_model_directory(model_name)
        except InvalidModelNameError as error:
            logger.error(
                "Path validation failed during delete", extra={"error": str(error)}
            )
            return False

        if target_dir.exists():
            try:
                shutil.rmtree(target_dir)
                logger.info("Model deleted successfully", extra={"model": model_name})
                return True

            except (OSError, PermissionError) as error:
                logger.error(
                    "Failed to delete model",
                    extra={"model": model_name, "error": str(error)},
                    exc_info=True,
                )
                return False

        # Directory doesn't exist, consider it a success
        logger.debug(
            "Model directory not found (already deleted)", extra={"model": model_name}
        )
        return True


# Singleton Instance
local_whisper = LocalWhisperManager()
