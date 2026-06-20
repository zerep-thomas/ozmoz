import os
import warnings

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")

import gc
import logging
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import requests
from faster_whisper import WhisperModel
from src.core.utils import PathManager

DOWNLOAD_CHUNK_SIZE = 16384
DOWNLOAD_TIMEOUT_SECONDS = 30
CPU_INFERENCE_THREADS = 4
VAD_MIN_SILENCE_MS = 300
ALLOWED_DOWNLOAD_DOMAIN = "huggingface.co"

logger = logging.getLogger(__name__)

MODELS_CONFIG: dict[str, dict[str, Any]] = {
    "Local Whisper Base": {
        "repo_id": "Systran/faster-whisper-base",
        "files": ["model.bin", "config.json", "vocabulary.txt", "tokenizer.json"],
    },
    "Local Whisper Small": {
        "repo_id": "Systran/faster-whisper-small",
        "files": ["model.bin", "config.json", "vocabulary.txt", "tokenizer.json"],
    },
    "Local Whisper Turbo": {
        "repo_id": "deepdml/faster-whisper-large-v3-turbo-ct2",
        "files": ["model.bin", "config.json", "vocabulary.json", "tokenizer.json", "preprocessor_config.json"],
    },
    "Local Distil-Whisper (EN)": {
        "repo_id": "Systran/faster-distil-whisper-large-v3",
        "files": ["model.bin", "config.json", "vocabulary.json", "tokenizer.json", "preprocessor_config.json"],
    }
}

class LocalWhisperManager:
    def __init__(self) -> None:
        root_dir = Path(__file__).resolve().parent.parent.parent
        self.base_models_directory: Path = root_dir / "data" / "models"
        
        self.model_instance: Optional[WhisperModel] = None
        self.is_loading: bool = False
        self._lock: threading.Lock = threading.Lock()
        self._current_loaded_model_name: Optional[str] = None
        self.has_cuda: bool = False
        self._detect_cuda_support()

        try:
            self.base_models_directory.mkdir(parents=True, exist_ok=True)
            logger.info("Models directory initialized: %s", self.base_models_directory)
        except Exception:
            logger.exception("Failed to create models directory")

    def _get_model_directory(self, model_name: str) -> Path:
        safe_name = model_name.replace(" ", "_").lower()
        return (self.base_models_directory / safe_name).resolve()

    def setup_portable_cuda(self) -> None:
        try:
            site_packages = next((p for p in sys.path if "site-packages" in p and os.path.isdir(p)), None)
            if not site_packages: return
            nvidia_path = Path(site_packages) / "nvidia"
            if not nvidia_path.exists(): return

            for root, dirs, _ in os.walk(nvidia_path):
                root_path = Path(root)
                if "bin" in dirs:
                    os.environ["PATH"] = str(root_path / "bin") + os.pathsep + os.environ.get("PATH", "")
                if "lib" in dirs:
                    os.environ["PATH"] = str(root_path / "lib") + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass

    def _detect_cuda_support(self) -> None:
        self.setup_portable_cuda()
        try:
            import ctypes.util
            self.has_cuda = ctypes.util.find_library("zlibwapi") is not None
        except Exception:
            self.has_cuda = False

    def is_installed(self, model_name: str) -> bool:
        try:
            model_dir = self._get_model_directory(model_name)
            if not model_dir.exists(): 
                return False
            for file_name in MODELS_CONFIG[model_name]["files"]:
                f_path = model_dir / file_name
                if not f_path.exists() or f_path.stat().st_size < 100:
                    return False
            return True
        except Exception:
            return False

    def download(self, model_name: str, progress_callback=None) -> bool:
        if model_name not in MODELS_CONFIG:
            logger.error("Unknown model: %s", model_name)
            return False

        with self._lock:
            if self.is_loading: return False
            self.is_loading = True

        logger.info("Starting download: %s", model_name)
        
        try:
            model_config = MODELS_CONFIG[model_name]
            repo_id = model_config["repo_id"]
            target_dir = self._get_model_directory(model_name)
            target_dir.mkdir(parents=True, exist_ok=True)
            files_to_download = model_config["files"]

            total_expected_bytes = 0
            for filename in files_to_download:
                url = f"https://{ALLOWED_DOWNLOAD_DOMAIN}/{repo_id}/resolve/main/{filename}"
                try:
                    resp = requests.head(url, timeout=10, allow_redirects=True)
                    total_expected_bytes += int(resp.headers.get("Content-Length", 0))
                except Exception:
                    pass
            
            downloaded_bytes = 0
            for filename in files_to_download:
                dest_path = target_dir / filename
                if dest_path.exists():
                    downloaded_bytes += dest_path.stat().st_size
                    
            if progress_callback and total_expected_bytes > 0:
                progress_callback(min(downloaded_bytes / total_expected_bytes, 1.0))

            last_progress_emit = 0.0

            for filename in files_to_download:
                url = f"https://{ALLOWED_DOWNLOAD_DOMAIN}/{repo_id}/resolve/main/{filename}"
                dest_path = target_dir / filename
                existing_size = dest_path.stat().st_size if dest_path.exists() else 0

                headers = {}
                if existing_size > 0: headers["Range"] = f"bytes={existing_size}-"

                response = requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS, allow_redirects=True)
                
                if response.status_code == 416: 
                    continue
                response.raise_for_status()

                mode = "ab" if existing_size > 0 else "wb"
                with dest_path.open(mode) as f:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            
                            if progress_callback and total_expected_bytes > 0:
                                current_progress = min(downloaded_bytes / total_expected_bytes, 1.0)
                                if current_progress - last_progress_emit >= 0.02 or current_progress == 1.0:
                                    progress_callback(current_progress)
                                    last_progress_emit = current_progress

            logger.info("Download completed: %s", model_name)
            return True

        except Exception:
            logger.exception("Download failed: %s", model_name)
            return False
        finally:
            with self._lock:
                self.is_loading = False

    def load(self, model_name: str) -> bool:
        if not self.is_installed(model_name): 
            logger.warning("Cannot load, %s is not fully downloaded.", model_name)
            return False
            
        if self._current_loaded_model_name == model_name and self.model_instance is not None:
            return True

        self.model_instance = None
        gc.collect()
        self.setup_portable_cuda()
        model_dir = self._get_model_directory(model_name)
        
        logger.info("Loading model into memory: %s", model_name)

        if self.has_cuda:
            try:
                self.model_instance = WhisperModel(str(model_dir), device="cuda", compute_type="float16", local_files_only=True)
                self._current_loaded_model_name = model_name
                logger.info("Model loaded successfully on GPU (CUDA)")
                return True
            except Exception:
                logger.warning("CUDA failed, falling back to CPU")
                self.has_cuda = False

        try:
            self.model_instance = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=CPU_INFERENCE_THREADS, local_files_only=True)
            self._current_loaded_model_name = model_name
            logger.info("Model loaded successfully on CPU")
            return True
        except Exception:
            logger.exception("Failed to load model on CPU")
            return False

    def transcribe(self, audio_file_path: str, language: str = "en", model_name: str = "Local Whisper Base", prompt: str = "") -> str:
        if not self.load(model_name): 
            return "❌ Error: Local model not loaded."
        
        logger.info("Local transcription in progress...")
        try:
            segments, info = self.model_instance.transcribe(
                audio_file_path,
                language=language if language != "autodetect" else None,
                initial_prompt=prompt,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": VAD_MIN_SILENCE_MS},
                temperature=0.0
            )
            text = " ".join(segment.text for segment in segments).strip()
            logger.info("Transcription result: %s...", text[:50])
            return text
        except Exception:
            logger.exception("Internal transcription error")
            return "❌ Transcription error"

    def delete_model(self, model_name: str) -> bool:
        if model_name not in MODELS_CONFIG:
            logger.error("Invalid or unconfigured model: %s", model_name)
            return False

        if self._current_loaded_model_name == model_name:
            logger.info("Unloading model %s before deletion", model_name)
            self.model_instance = None
            self._current_loaded_model_name = None
            gc.collect()

        try:
            target_dir = self._get_model_directory(model_name)
            if target_dir.exists():
                shutil.rmtree(target_dir)
                logger.info("Model %s deleted successfully", model_name)
            return True
        except Exception:
            logger.exception("Failed to delete %s", model_name)
            return False

local_whisper = LocalWhisperManager()