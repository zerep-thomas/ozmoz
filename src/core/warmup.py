import logging
import os
import sys
import subprocess
import threading
import time
from pydub import AudioSegment

logger = logging.getLogger(__name__)

def preload_ffmpeg() -> None:
    start_time = time.perf_counter()
    
    if not hasattr(AudioSegment, 'converter') or not AudioSegment.converter or not os.path.exists(AudioSegment.converter):
        logger.warning("FFmpeg path not configured. Preload skipped.")
        return

    try:
        subprocess.run(
            [AudioSegment.converter, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            creationflags=0x08000000 if sys.platform == 'win32' else 0
        )
        duration = time.perf_counter() - start_time
        logger.info("FFmpeg preloaded successfully in %.2fs.", duration)
    except Exception:
        logger.exception("FFmpeg preload failed")

def run_ffmpeg_warmup_in_background() -> None:
    warmup_thread = threading.Thread(target=preload_ffmpeg, daemon=True, name="FFmpegWarmup")
    warmup_thread.start()