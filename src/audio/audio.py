import io
import logging
import os
import tempfile
import threading
import time
import wave
import re
import uuid
from pathlib import Path

import numpy as np
import pyaudio
import win32gui
from groq import Groq
from pydub import AudioSegment

from src.core.config import AppConfig, AppState, GROQ_MODEL_MAPPING
from src.core.utils import SuppressStderr, PerfTracker
from src.audio.local_audio import local_whisper
from src.core.system import global_executor

logger = logging.getLogger(__name__)

LANGUAGES_ISO = {
    "afrikaans": "af", "albanian": "sq", "amharic": "am", "arabic": "ar", "armenian": "hy",
    "assamese": "as", "azerbaijani": "az", "bashkir": "ba", "basque": "eu", "belarusian": "be",
    "bengali": "bn", "bosnian": "bs", "breton": "br", "bulgarian": "bg", "burmese": "my",
    "catalan": "ca", "chinese": "zh", "croatian": "hr", "czech": "cs", "danish": "da",
    "dutch": "nl", "english": "en", "estonian": "et", "faroese": "fo", "finnish": "fi",
    "french": "fr", "galician": "gl", "georgian": "ka", "german": "de", "greek": "el",
    "gujarati": "gu", "haitian creole": "ht", "hausa": "ha", "hawaiian": "haw", "hebrew": "he",
    "hindi": "hi", "hungarian": "hu", "icelandic": "is", "indonesian": "id", "italian": "it",
    "japanese": "ja", "javanese": "jv", "kannada": "kn", "kazakh": "kk", "khmer": "km",
    "korean": "ko", "lao": "lo", "latin": "la", "latvian": "lv", "lingala": "ln",
    "lithuanian": "lt", "luxembourgish": "lb", "macedonian": "mk", "malagasy": "mg",
    "malay": "ms", "malayalam": "ml", "maltese": "mt", "maori": "mi", "marathi": "mr",
    "mongolian": "mn", "nepali": "ne", "norwegian": "no", "nynorsk": "nn", "occitan": "oc",
    "pashto": "ps", "persian": "fa", "polish": "pl", "portuguese": "pt", "punjabi": "pa",
    "romanian": "ro", "russian": "ru", "sanskrit": "sa", "serbian": "sr", "shona": "sn",
    "sindhi": "sd", "sinhala": "si", "slovak": "sk", "slovenian": "sl", "somali": "so",
    "spanish": "es", "sundanese": "su", "swahili": "sw", "swedish": "sv", "tagalog": "tl",
    "tajik": "tg", "tamil": "ta", "tatar": "tt", "telugu": "te", "thai": "th", "tibetan": "bo",
    "turkish": "tr", "turkmen": "tk", "ukrainian": "uk", "urdu": "ur", "uzbek": "uz",
    "vietnamese": "vi", "welsh": "cy", "yiddish": "yi", "yoruba": "yo"
}


class AudioManager:
    def __init__(self, app_state, sound_manager, event_bus, mode_manager=None, credential_manager=None):
        self.app_state = app_state
        self.sound_manager = sound_manager
        self.event_bus = event_bus
        self.mode_manager = mode_manager
        self.credential_manager = credential_manager
        self._pyaudio_instance = None
        self._audio_stream = None
        self._recording_thread = None

    def initialize(self) -> bool:
        if self._pyaudio_instance:
            return True
        try:
            with SuppressStderr():
                self._pyaudio_instance = pyaudio.PyAudio()
            self.app_state.audio.pyaudio_instance = self._pyaudio_instance
            return True
        except Exception:
            logger.exception("Failed to initialize PyAudio")
            return False

    def terminate(self) -> None:
        self.wait_for_recording()
        if self._audio_stream:
            self._audio_stream.stop_stream()
            self._audio_stream.close()
            self._audio_stream = None
        if self._pyaudio_instance:
            self._pyaudio_instance.terminate()
            self._pyaudio_instance = None

    def start_recording(self) -> None:
        if self.mode_manager and self.credential_manager:
            sys_cfg = self.mode_manager.get_mode("system")
            ui_model = sys_cfg.get("active_model", "Whisper V3 Turbo")

            if ui_model == "Select a model...":
                self.event_bus.publish("visualizer_error", "Choose a model")
                return
            if "Local" in ui_model:
                if not local_whisper.is_installed(ui_model):
                    self.event_bus.publish("visualizer_error", "Choose a model")
                    return
            else:
                if not self.credential_manager.get_api_key("groq"):
                    self.event_bus.publish("visualizer_error", "Choose a model")
                    return

        if not self.app_state.audio.pyaudio_instance:
            if not self.initialize():
                return

        try:
            pre_stream = self._pyaudio_instance.open(
                format=AppConfig.AUDIO_FORMAT,
                channels=AppConfig.AUDIO_CHANNELS,
                rate=AppConfig.AUDIO_RATE,
                input=True,
                frames_per_buffer=AppConfig.AUDIO_CHUNK,
            )
            self._audio_stream = pre_stream
        except Exception:
            logger.exception("Failed to pre-open audio stream")
            return

        if self.app_state.audio.sound_enabled:
            self.sound_manager.play("beep_on")

        self.event_bus.publish("recording_started", None)

        self.app_state.is_busy = True
        self.app_state.audio.is_recording = True
        self.app_state.audio.recording_start_time = time.time()

        temp_dir = Path(tempfile.gettempdir()).resolve()
        temp_path = temp_dir / f"ozmoz_rec_{uuid.uuid4().hex}.wav"
        self.app_state.audio.current_recording_path = str(temp_path)

        self._recording_thread = threading.Thread(
            target=self._record_audio_worker, args=(str(temp_path),), daemon=True
        )
        self._recording_thread.start()

    def _record_audio_worker(self, filename: str) -> None:
        frames = []
        try:
            stream = self._audio_stream
            while self.app_state.audio.is_recording:
                data = stream.read(AppConfig.AUDIO_CHUNK, exception_on_overflow=False)
                frames.append(data)

                self.event_bus.publish("audio_frame", data, threaded=False)
        except Exception:
            logger.exception("Audio recording failed unexpectedly")
        finally:
            if self._audio_stream:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
                self._audio_stream = None
            if frames:
                self._write_wav_file(filename, frames)

    def _write_wav_file(self, filename: str, frames: list) -> None:
        try:
            with wave.open(filename, "wb") as wave_file:
                wave_file.setnchannels(AppConfig.AUDIO_CHANNELS)
                wave_file.setsampwidth(self._pyaudio_instance.get_sample_size(AppConfig.AUDIO_FORMAT))
                wave_file.setframerate(AppConfig.AUDIO_RATE)
                wave_file.writeframes(b"".join(frames))
        except Exception:
            logger.exception(f"Failed to write audio to {filename}")

    def wait_for_recording(self, timeout: float = 5.0) -> None:
        if self._recording_thread and self._recording_thread.is_alive():
            self._recording_thread.join(timeout=timeout)
        self._recording_thread = None


class TranscriptionService:
    def __init__(self, app_state, credential_manager, vocabulary_manager=None, mode_manager=None):
        self.app_state = app_state
        self.credential_manager = credential_manager
        self.vocabulary_manager = vocabulary_manager
        self.mode_manager = mode_manager
        self._groq_client = None
        self._last_api_key = None

    def _get_groq_client(self):
        api_key = self.credential_manager.get_api_key("groq")
        if not api_key:
            return None
        if self._groq_client is None or api_key != self._last_api_key:
            self._groq_client = Groq(api_key=api_key)
            self._last_api_key = api_key
        return self._groq_client

    def transcribe(self, filename: str, duration: float) -> str:
        if not os.path.exists(filename):
            return "⚠️ Error: Audio file not found."

        try:
            sys_cfg = self.mode_manager.get_mode("system")
            ui_preset = sys_cfg.get("active_preset", "Voice to text")
            lang_name = sys_cfg.get("active_language", "English").lower()
            lang_iso = LANGUAGES_ISO.get(lang_name, "en")
            ui_model = sys_cfg.get("active_model", "Whisper V3 Turbo")
            api_model = GROQ_MODEL_MAPPING.get(ui_model, "whisper-large-v3-turbo")

            if ui_model == "Select a model...":
                return "⚠️ Error: No model selected."

            if ui_preset == "Equation" and not self.credential_manager.get_api_key("groq"):
                logger.warning("Equation mode requested but no Groq API Key found. Forced fallback to text.")
                ui_preset = "Voice to text"

            logger.info(
                "Transcription starting | Preset: %s | Model: %s | Lang: %s",
                ui_preset, ui_model, lang_iso
            )

            if ui_preset == "Email Draft":
                prompt = (
                    "Transcribe this audio as a professional email. "
                    "Use formal language, proper punctuation, and clear paragraph structure. "
                    "Do not include filler words, silence markers, or meta-text like 'Subtitles by...'. "
                    "Format with a greeting, body paragraphs, and a sign-off."
                )
            elif ui_preset == "Equation":
                prompt = (
                    "Math dictation. Symbols, equations, variables, Greek letters, "
                    "fractions, integrals, superscripts, subscripts. "
                    "Example: integral from zero to infinity of x squared dx equals pi."
                )
            else:
                prompt = ""

            if self.vocabulary_manager:
                words = self.vocabulary_manager.get_words()
                if words:
                    if prompt:
                        prompt += " Vocabulary: " + ", ".join(words) + "."
                    else:
                        prompt = ", ".join(words)

            if len(prompt) > 500:
                prompt = prompt[:500]

            result = ""

            if "Local" in ui_model:
                logger.info("Sending audio to LOCAL engine...")
                if not local_whisper.is_installed(ui_model):
                    return f"⚠️ Error: Model '{ui_model}' is not installed."

                result = local_whisper.transcribe(
                    filename, language=lang_iso, model_name=ui_model, prompt=prompt
                )
            else:
                logger.info("Sending audio to CLOUD engine (Groq API)...")
                client = self._get_groq_client()
                if not client:
                    return "⚠️ Error: Groq API key missing."

                with open(filename, "rb") as file_obj:
                    audio_content = file_obj.read()

                kwargs = {
                    "model": api_model,
                    "file": (Path(filename).name, audio_content),
                    "response_format": "verbose_json",
                    "temperature": 0.0
                }
                if lang_iso:
                    kwargs["language"] = lang_iso
                if prompt:
                    kwargs["prompt"] = prompt

                transcription = client.audio.transcriptions.create(**kwargs)

                valid_text = []
                segments = None
                if isinstance(transcription, dict):
                    segments = transcription.get("segments")
                elif hasattr(transcription, "segments"):
                    segments = transcription.segments

                if segments:
                    for seg in segments:
                        if isinstance(seg, dict):
                            no_speech = seg.get('no_speech_prob', 0)
                            comp_ratio = seg.get('compression_ratio', 0)
                            seg_text = seg.get('text', '')
                        else:
                            no_speech = getattr(seg, 'no_speech_prob', 0)
                            comp_ratio = getattr(seg, 'compression_ratio', 0)
                            seg_text = getattr(seg, 'text', '')

                        if no_speech > 0.6:
                            continue
                        if comp_ratio > 2.5:
                            continue
                        if seg_text:
                            valid_text.append(seg_text.strip())

                    result = " ".join(valid_text).strip()
                elif isinstance(transcription, dict):
                    result = transcription.get("text", "").strip()
                else:
                    result = getattr(transcription, "text", str(transcription)).strip()

                word_count = len(re.findall(r'\w+', result))
                if duration > 4.0 and word_count <= 2:
                    result = ""

            if not result:
                return "⚠️ Error: No audio or result detected (silence or noise)."

            if ui_preset == "Email Draft":
                result = self._format_as_email(result, lang_iso)
            elif ui_preset == "Equation":
                result = self._convert_to_latex(result)

            return result

        except Exception as e:
            logger.exception("Internal transcription error")
            return f"❌ Internal error during transcription: {e}"

    def _convert_to_latex(self, text: str) -> str:
        text = text.strip()
        if not text:
            return text

        client = self._get_groq_client()
        if not client:
            return "⚠️ Error: Groq API key missing for Equation mode."

        system_prompt = (
            "You are a highly accurate audio-to-LaTeX converter. "
            "Convert the user's spoken math dictation into clean, valid LaTeX code. "
            "Output ONLY the raw LaTeX code. Do not include markdown formatting like ```latex. "
            "Do not include any explanations, greetings, or filler text. "
            "Distinguish carefully between spoken words meant for the equation and conversational filler. "
            "Do not wrap the output in \\[ or $$ unless explicitly requested by the user."
        )

        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                model="llama-3.1-8b-instant",
                temperature=0.0,
            )
            latex_result = chat_completion.choices[0].message.content.strip()

            if latex_result.startswith("```latex"):
                latex_result = latex_result[8:]
            elif latex_result.startswith("```"):
                latex_result = latex_result[3:]
            if latex_result.endswith("```"):
                latex_result = latex_result[:-3]

            return latex_result.strip()
        except Exception as e:
            logger.exception("LLM conversion to LaTeX failed")
            return f"⚠️ LLM Error: {str(e)}"

    def _format_as_email(self, text: str, lang_iso: str) -> str:
        text = text.strip()
        if not text:
            return text

        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if not sentences:
            return text

        first_sent = sentences[0]
        first_sent_clean = first_sent.lower().strip('.,;:!?')

        has_greeting = False
        words_first = first_sent_clean.split()
        if len(words_first) <= 4:
            if first_sent.endswith((',', ':', '!')) or len(words_first) <= 2:
                has_greeting = True

        last_sent = sentences[-1]
        last_sent_clean = last_sent.lower().strip('.,;:!?')
        words_last = last_sent_clean.split()

        has_signoff = False
        if len(words_last) <= 5:
            if last_sent.endswith(('.', ',')) or len(words_last) <= 3:
                has_signoff = True

        body_sentences = sentences[:]
        greeting = ""
        signoff = ""

        if has_greeting:
            greeting = first_sent
            body_sentences = body_sentences[1:]

        if has_signoff and body_sentences:
            signoff = last_sent
            body_sentences = body_sentences[:-1]

        greeting = greeting or self._default_greeting(lang_iso)
        signoff = signoff or self._default_signoff(lang_iso)

        formatted_body = self._format_body_paragraphs(body_sentences, lang_iso)

        parts = [greeting]
        parts.extend(formatted_body)
        parts.append(signoff)

        return "\n\n".join(parts)

    def _default_greeting(self, lang_iso: str) -> str:
        greetings = {
            "fr": "Bonjour,", "en": "Hello,", "es": "Hola,", "de": "Hallo,",
            "it": "Buongiorno,", "pt": "Olá,", "nl": "Hallo,", "pl": "Dzień dobry,",
            "ru": "Здравствуйте,", "zh": "您好，", "ja": "こんにちは、", "ko": "안녕하세요,",
            "ar": "مرحباً،", "hi": "नमस्ते,", "tr": "Merhaba,", "sv": "Hej,",
            "da": "Hej,", "no": "Hei,", "fi": "Hei,", "cs": "Dobrý den,",
            "hu": "Tisztelt Címzett!", "el": "Γεια σας,", "he": "שלום,", "th": "สวัสดีครับ/ค่ะ,",
            "vi": "Xin chào,", "id": "Halo,", "ms": "Helo,", "uk": "Вітаю,", "ro": "Bună ziua,"
        }
        return greetings.get(lang_iso, "Hello,")

    def _default_signoff(self, lang_iso: str) -> str:
        signoffs = {
            "fr": "Cordialement,", "en": "Best regards,", "es": "Saludos cordiales,",
            "de": "Mit freundlichen Grüßen,", "it": "Cordiali saluti,", "pt": "Atenciosamente,",
            "nl": "Met vriendelijke groet,", "pl": "Z poważaniem,", "ru": "С уважением,",
            "zh": "此致敬礼，", "ja": "よろしくお願いいたします。", "ko": "감사합니다.",
            "ar": "مع التحية，", "hi": "धन्यवाद,", "tr": "Saygılarımla,", "sv": "Med vänliga hälsningar,",
            "da": "Med venlig hilsen,", "no": "Med vennlig hilsen,", "fi": "Ystävällisin terveisin,",
            "cs": "S pozdravem,", "hu": "Üdvözlettel,", "el": "Με εκτίμηση,", "he": "בברכה,",
            "th": "ด้วยความเคารพ,", "vi": "Trân trọng,", "id": "Hormat saya,", "ms": "Yang benar,",
            "uk": "З повагою,", "ro": "Cu stimă,"
        }
        return signoffs.get(lang_iso, "Best regards,")

    def _format_body_paragraphs(self, sentences: list, lang_iso: str) -> list:
        if not sentences:
            return []

        paragraphs = []
        current_para = []

        transition_patterns = [
            r'^(however|nevertheless|furthermore|moreover|additionally|consequently|therefore|meanwhile|alternatively|specifically|finally|in\s+conclusion|to\s+conclude|on\s+the\s+other\s+hand|firstly|secondly|thirdly)',
            r'^(cependant|néanmoins|par\s+ailleurs|de\s+plus|ensuite|enfin|en\s+conclusion|d\'autre\s+part|toutefois|premièrement|deuxièmement)',
            r'^(sin\s+embargo|además|por\s+lo\s+tanto|en\s+conclusión|por\s+outro\s+lado|finalmente)',
            r'^(jedoch|außerdem|darüber\s+hinaus|zusammenfassend|schließlich|andererseits)',
            r'^(tuttavia|inoltre|pertanto|in\s+conclusione|d\'alta\s+parte|infine)',
            r'^(no\s+entanto|além\s+disso|portanto|em\s+conclusão|por\s+outro\s+lado|finalmente)',
        ]

        para_size_target = 2

        for i, sentence in enumerate(sentences):
            sent_lower = sentence.lower().strip()
            is_transition = any(re.search(pattern, sent_lower) for pattern in transition_patterns)

            if (is_transition and current_para) or len(current_para) >= para_size_target:
                paragraphs.append(" ".join(current_para))
                current_para = [sentence]
            else:
                current_para.append(sentence)

        if current_para:
            paragraphs.append(" ".join(current_para))

        formatted = []
        for p in paragraphs:
            if p:
                p = p[0].upper() + p[1:] if len(p) > 1 else p.upper()
                formatted.append(p)

        return formatted if formatted else [" ".join(sentences)]


class TranscriptionManager:
    def __init__(self, app_state, audio_manager, sound_manager, stats_manager,
                 history_manager, transcription_service, clipboard_manager, event_bus):
        self.app_state = app_state
        self.audio_manager = audio_manager
        self.sound_manager = sound_manager
        self.stats_manager = stats_manager
        self.history_manager = history_manager
        self.transcription_service = transcription_service
        self.clipboard_manager = clipboard_manager
        self.event_bus = event_bus
        self._previous_active_window = None
        self._is_stopping = False

    def stop_recording_and_transcribe(self) -> None:
        if getattr(self, "_is_stopping", False) or not self.app_state.audio.is_recording:
            return

        self._is_stopping = True
        tracker = PerfTracker("Transcription Flow")
        tracker.step("Hotkey released")

        audio_duration = time.time() - self.app_state.audio.recording_start_time

        try:
            self._previous_active_window = win32gui.GetForegroundWindow()
        except Exception:
            logger.debug("Failed to store foreground window", exc_info=True)

        self.event_bus.publish("recording_stopped", None)

        def _process_transcription():
            self.event_bus.publish("processing_started", None)
            try:
                time.sleep(0.05)

                self.app_state.audio.is_recording = False
                self.audio_manager.wait_for_recording()

                wav_file = self.app_state.audio.current_recording_path

                if wav_file and os.path.exists(wav_file):
                    audio_file_to_send = wav_file

                    start_process_time = time.time()
                    text = self.transcription_service.transcribe(
                        audio_file_to_send, duration=audio_duration
                    )
                    processing_time = time.time() - start_process_time

                    if os.path.exists(audio_file_to_send):
                        os.remove(audio_file_to_send)

                    if not (text.startswith("⚠️") or text.startswith("❌")):
                        sys_cfg = self.transcription_service.mode_manager.get_mode("system")
                        ui_model = sys_cfg.get("active_model", "Whisper V3 Turbo")

                        if "Local" in ui_model:
                            used_method = f"local-{ui_model.replace(' ', '-').lower()}"
                        else:
                            active_api_model = GROQ_MODEL_MAPPING.get(ui_model, "whisper-large-v3-turbo")
                            used_method = f"groq-{active_api_model}"

                        self.history_manager.add_entry(
                            text=text,
                            duration_sec=audio_duration,
                            processing_sec=processing_time,
                            method=used_method
                        )

                        if self.app_state.audio.sound_enabled:
                            self.sound_manager.play("beep_off")

                        time.sleep(0.2)

                        if self._previous_active_window:
                            try:
                                win32gui.SetForegroundWindow(self._previous_active_window)
                                time.sleep(0.15)
                            except Exception:
                                logger.debug("Failed to set foreground window", exc_info=True)

                        self.clipboard_manager.paste_and_clear(text)

            except Exception as e:
                logger.error(f"FATAL THREAD ERROR: {e}")
            finally:
                self.event_bus.publish("processing_finished", None)
                self.app_state.is_busy = False
                self._is_stopping = False
                tracker.step("Process finished (cleaned up)")

        global_executor.submit(_process_transcription)