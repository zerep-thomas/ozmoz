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

from src.core.config import AppConfig, GROQ_MODEL_MAPPING
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

def has_real_speech(audio_data: np.ndarray) -> bool:
    rms = float(np.sqrt(np.mean(audio_data ** 2)))
    if rms < 0.0005: 
        return False
    return True

class AudioManager:
    def __init__(self, app_state, sound_manager, event_bus, mode_manager=None, credential_manager=None, settings_manager=None):
        self.app_state = app_state
        self.sound_manager = sound_manager
        self.event_bus = event_bus
        self.mode_manager = mode_manager
        self.credential_manager = credential_manager
        self.settings_manager = settings_manager
        self._pyaudio_instance = None
        self._audio_stream = None  
        self._warm_mic_thread = None
        self._stop_mic = False
        self.frames_lock = threading.Lock()
        self.recorded_frames = []
        
        self.event_bus.subscribe("settings_updated", self._on_settings_updated)

    def _is_stream_active(self) -> bool:
        if not self._audio_stream:
            return False
        try:
            return self._audio_stream.is_active()
        except Exception:
            return False

    def _close_stream(self):
        if self._audio_stream:
            try:
                if self._audio_stream.is_active():
                    self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None

    def _on_settings_updated(self, data):
        if data and data.get("key") == "keep_mic_warm":
            warm = data.get("value")
            def _safe_apply():
                try:
                    if warm:
                        if not self._pyaudio_instance:
                            self.initialize()
                        if not self._audio_stream:
                            self._open_stream()
                        if not self._is_stream_active():
                            self._audio_stream.start_stream()
                        
                        self._stop_mic = False
                        if not self._warm_mic_thread or not self._warm_mic_thread.is_alive():
                            self._warm_mic_thread = threading.Thread(target=self._mic_reader_loop, daemon=True)
                            self._warm_mic_thread.start()
                    else:
                        if not self.app_state.audio.is_recording:
                            self._stop_mic = True
                            self._close_stream()
                except Exception as e:
                    logger.error(f"Error in _on_settings_updated: {e}")
            threading.Thread(target=_safe_apply, daemon=True).start()

    def initialize(self) -> bool:
        if not self._pyaudio_instance:
            try:
                with SuppressStderr():
                    self._pyaudio_instance = pyaudio.PyAudio()
                self.app_state.audio.pyaudio_instance = self._pyaudio_instance
            except Exception as e:
                logger.error(f"Failed to initialize PyAudio: {e}")
                return False

        warm_mic = self.settings_manager.get("keep_mic_warm", False) if self.settings_manager else False
        if warm_mic:
            if not self._audio_stream:
                if not self._open_stream():
                    return False
            try:
                if not self._is_stream_active():
                    self._audio_stream.start_stream()
                self._stop_mic = False
                if not self._warm_mic_thread or not self._warm_mic_thread.is_alive():
                    self._warm_mic_thread = threading.Thread(target=self._mic_reader_loop, daemon=True)
                    self._warm_mic_thread.start()
            except Exception:
                pass

        return True

    def _open_stream(self) -> bool:
        try:
            self._audio_stream = self._pyaudio_instance.open(
                format=AppConfig.AUDIO_FORMAT,
                channels=AppConfig.AUDIO_CHANNELS,
                rate=AppConfig.AUDIO_RATE,
                input=True,
                frames_per_buffer=AppConfig.AUDIO_CHUNK,
                start=False, 
            )
            return True
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}")
            return False

    def terminate(self) -> None:
        self.wait_for_recording()
        self._stop_mic = True
        self._close_stream()
        if self._pyaudio_instance:
            self._pyaudio_instance.terminate()
            self._pyaudio_instance = None

    def _mic_reader_loop(self):
        while not self._stop_mic:
            if not self._audio_stream:
                time.sleep(0.01)
                continue
            try:
                data = self._audio_stream.read(AppConfig.AUDIO_CHUNK, exception_on_overflow=False)
                if self.app_state.audio.is_recording:
                    with self.frames_lock:
                        self.recorded_frames.append(data)
                    self.event_bus.publish("audio_frame", data, threaded=False)
            except Exception:
                time.sleep(0.01)

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

        if not self._pyaudio_instance:
            self.initialize()

        if not self._audio_stream:
            if not self._open_stream():
                return
            try:
                self._audio_stream.start_stream()
            except Exception:
                pass
        else:
            if not self._is_stream_active():
                try:
                    self._audio_stream.start_stream()
                except Exception:
                    self._close_stream()
                    if not self._open_stream():
                        return
                    self._audio_stream.start_stream()

        self._stop_mic = False
        if not self._warm_mic_thread or not self._warm_mic_thread.is_alive():
            self._warm_mic_thread = threading.Thread(target=self._mic_reader_loop, daemon=True)
            self._warm_mic_thread.start()

        with self.frames_lock:
            self.recorded_frames.clear()

        if self.app_state.audio.sound_enabled:
            self.sound_manager.play("beep_on")

        self.event_bus.publish("recording_started", None)
        self.app_state.is_busy = True
        self.app_state.audio.is_recording = True
        self.app_state.audio.recording_start_time = time.time()

    def stop_recording(self):
        self.app_state.audio.is_recording = False
        warm_mic = self.settings_manager.get("keep_mic_warm", False) if self.settings_manager else False
        if not warm_mic:
            self._stop_mic = True
            self._close_stream()

    def get_frames(self):
        with self.frames_lock:
            return list(self.recorded_frames)

    def wait_for_recording(self, timeout: float = 5.0) -> None:
        pass

class TranscriptionService:
    def __init__(self, app_state, credential_manager, vocabulary_manager=None, mode_manager=None):
        self.app_state = app_state
        self.credential_manager = credential_manager
        self.vocabulary_manager = vocabulary_manager
        self.mode_manager = mode_manager
        self._groq_client = None
        self._last_api_key = None
        self._RUN_UNIT = re.compile(r"(.{1,5}?)\1{3,}")
        self._RUN_CHAR = re.compile(r"(.)\1{4,}")

    def _get_groq_client(self):
        api_key = self.credential_manager.get_api_key("groq")
        if not api_key:
            return None
        if self._groq_client is None or api_key != self._last_api_key:
            self._groq_client = Groq(api_key=api_key)
            self._last_api_key = api_key
        return self._groq_client

    def _collapse_repeats(self, text: str) -> str:
        text = self._RUN_CHAR.sub(r"\1\1", text)
        text = self._RUN_UNIT.sub(r"\1", text)
        return text

    def transcribe(self, filename: str, duration: float) -> str:
        if not os.path.exists(filename):
            return "⚠️ Error: Audio file not found."

        try:
            with wave.open(filename, 'rb') as wf:
                raw_data = wf.readframes(wf.getnframes())
                audio_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            if not has_real_speech(audio_data):
                return ""

            sys_cfg = self.mode_manager.get_mode("system")
            ui_preset = sys_cfg.get("active_preset", "Voice to text")
            lang_name = sys_cfg.get("active_language", "English").lower()
            lang_iso = LANGUAGES_ISO.get(lang_name, "en")
            ui_model = sys_cfg.get("active_model", "Whisper V3 Turbo")
            api_model = GROQ_MODEL_MAPPING.get(ui_model, "whisper-large-v3-turbo")

            if ui_model == "Select a model...":
                return "⚠️ Error: No model selected."

            if ui_preset == "Equation" and not self.credential_manager.get_api_key("groq"):
                ui_preset = "Voice to text"

            prompt_parts = []
            if ui_preset == "Email Draft":
                prompt_parts.append("Transcribe this audio as a professional email.")
            elif ui_preset == "Equation":
                pass 
            else:
                pass

            if self.vocabulary_manager and ui_preset != "Equation":
                words = self.vocabulary_manager.get_words()
                if words:
                    prompt_parts.append(f"Vocabulary: {', '.join(words)}.")

            prompt = " ".join(prompt_parts)[:244]
            result = ""

            if "Local" in ui_model:
                if not local_whisper.is_installed(ui_model):
                    return f"⚠️ Error: Model '{ui_model}' is not installed."
                result = local_whisper.transcribe(
                    filename, language=lang_iso, model_name=ui_model, prompt=prompt
                )
            else:
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

                        if no_speech > 0.6 or comp_ratio > 2.5:
                            continue
                        if seg_text:
                            valid_text.append(seg_text.strip())
                    result = " ".join(valid_text).strip()
                elif isinstance(transcription, dict):
                    result = transcription.get("text", "").strip()
                else:
                    result = getattr(transcription, "text", str(transcription)).strip()

            if not result:
                return ""

            hallucinations_patterns = [
                r"(?i)sous[\s-]*titrage\s+.*", r"(?i)sous-titres\s+réalisés\s+par.*", r"(?i)merci de votre attention\.?", r"(?i)radio-canada",
                r"(?i)subtitles? by.*", r"(?i)captioned by.*", r"(?i)captions by.*", r"(?i)thanks for watching\.?", r"(?i)please subscribe\.?", r"(?i)subscribe to.*",
                r"(?i)subtítulos\s+por.*", r"(?i)legendas\s+por.*", r"(?i)traducido\s+por.*", r"(?i)tradução\s+por.*",
                r"(?i)untertitel\s+von.*", r"(?i)sottotitoli\s+di.*",
                r"(?i)субтитры\s+.*", r"(?i)спасибо за просмотр\.?",
                r"(?i)amara\.org", r"(?i)www\..*\.com"
            ]
            for pattern in hallucinations_patterns:
                result = re.sub(pattern, '', result).strip()

            isolated_hallucinations = {
                "merci", "thank you", "thanks", "gracias", "danke", "grazie", 
                "obrigado", "obrigada", "спасибо", "شكرا", "arigato", "xiexie", 
                "kamsahamnida", "bye", "au revoir", "adios", "tschüss", "ciao", 
                "oh", "ah", "hmm", "ooo", "mhm"
            }
            clean_result = result.lower().strip('.,!? \t\n')
            if clean_result in isolated_hallucinations and duration > 3.5:
                result = ""
            if not result:
                return ""
            
            result = self._collapse_repeats(result)

            if ui_preset == "Email Draft":
                result = self._format_as_email(result, lang_iso)
            elif ui_preset == "Equation":
                result = self._convert_to_latex(result)
            return result

        except Exception as e:
            logger.error(f"Internal transcription error: {e}")
            return f"❌ Transcription error: {e}"

    def _convert_to_latex(self, text: str) -> str:
        text = text.strip()
        if not text:
            return text
        client = self._get_groq_client()
        if not client:
            return ""
        system_prompt = (
            "You are an expert Math, Physics, and LaTeX formatter. Convert the user's raw dictated "
            "speech (already transcribed by an ASR system) into perfectly formatted text with LaTeX.\n\n"

            "RULE 0 — ASR ERROR CORRECTION (applies everywhere, including pure formulas):\n"
            "The transcription may contain phonetic errors from the speech recognizer. Silently correct "
            "them using mathematical/physical context BEFORE formatting. This includes homophones "
            "('l'accord' -> 'la corde', 'm1' -> 'M_1', 'et' vs 'est'). If the dictation references a "
            "well-known named formula or theorem (Euler, Pythagore, Thalès, etc.), use that name as a "
            "strong prior to resolve ambiguous or garbled fragments — but only when you are genuinely "
            "confident; if unsure, transcribe literally rather than guessing (see RULE 9, no hallucination "
            "still applies: you are correcting recognition errors, never inventing new content).\n"
            "This includes correcting the NAME of a formula/theorem itself when the mathematical content "
            "that follows unambiguously identifies it, even if the name was badly mis-transcribed. "
            "Example: if the spoken content is clearly e^{i*pi}+1=0, then a transcribed name like 'la "
            "formule de l'heure' must be corrected to 'la formule d'Euler' (phonetically close to "
            "'Euler' in French) — do not keep an obviously wrong name when the equation itself proves "
            "which formula was meant.\n\n"

            "RULE 1 — PURE FORMULA (-> $$...$$ block):\n"
            "Use a pure block formula ONLY when the ENTIRE utterance, from start to end, IS the equation "
            "itself with no framing clause — i.e. it has the grammatical shape 'X est égal à Y' or "
            "'la somme de ... est égale à ...', where X and Y are purely mathematical/physical objects.\n"
            "Example: 'le vecteur V est égal à la dérivée du vecteur OM sur dt' -> "
            "$$\\vec{V} = \\frac{d\\vec{OM}}{dt}$$\n"
            "Do NOT use this rule when the sentence has an external framing clause such as 'la formule de "
            "X dit que...', 'selon le théorème de...', 'on sait que...', 'sachant que...'. Those are "
            "sentences ABOUT a formula, not the formula itself — they always fall under RULE 2, and the "
            "framing clause must be kept as plain text.\n"
            "For a short standalone mathematical snippet with no verb and no framing sentence at all "
            "(e.g. just 'racine cubique de vingt-sept'), do NOT force it into a $$ block merely because it "
            "is the only thing said — use inline $...$ unless it is a genuine multi-part equation/definition.\n\n"

            "RULE 2 — MIXED TEXT & MATH (-> inline $...$):\n"
            "For definitions, theorems, or any sentence with a subject/framing clause, output the FULL "
            "sentence naturally, in French, and wrap only the mathematical fragments in single dollars. "
            "NEVER silently drop connecting words or clauses (e.g. 'définie sur', 'dans un triangle "
            "rectangle', 'où x est...') to convert something into pure math — the surrounding French text "
            "is part of the expected output, not noise to eliminate.\n\n"

            "RULE 3 — LETTER CASE:\n"
            "Default every single-letter variable (x, y, n, k, a, b, u...) to LOWERCASE, because French "
            "speech does not distinguish case when spelling a letter. This OVERRIDES whatever case appears "
            "in the raw transcription — the ASR often capitalizes isolated letters by default (e.g. it may "
            "write 'A' or 'B' even though the speaker said a plain lowercase 'a'/'b'), and that "
            "capitalization is NOT a reliable signal of intent. Always force lowercase for single-letter "
            "variables unless the user explicitly says 'majuscule', or for objects with a standard "
            "capitalized convention in the given context (geometric points A, B, M; a named matrix; a "
            "set). Example: transcription 'A sur B' -> $\\frac{a}{b}$, NOT $\\frac{A}{B}$. When in doubt, "
            "lowercase.\n"
            "When an exponent or operation applies to an ENTIRE indexed variable, keep the index and the "
            "exponent as separate, sibling groups — do not nest the exponent inside the subscript. "
            "'u indice n au carré' means (u_n) squared -> $u_n^2$, NOT $u_{n^2}$ (which would mean 'u "
            "indice n carré', a different index). The exponent from 'au carré'/'à la puissance X' spoken "
            "AFTER an index always attaches to the whole indexed symbol, never to the index alone.\n\n"

            "RULE 4 — EXPONENTS:\n"
            "'X puissance moins Y' -> ^{-Y} (always brace negative or multi-character exponents), never "
            "split into a separate subtraction. 'X puissance Y' with Y being a single digit -> ^Y is fine "
            "without braces, but ANY exponent that is negative, a variable, or more than one character "
            "must be wrapped in {}.\n"
            "Example: 'deux puissance moins un' -> $2^{-1}$ (never $2^2-1$).\n\n"

            "RULE 5 — SCOPE OF FRACTIONS, ROOTS, PARENTHESES:\n"
            "Treat commas and clear pauses in the transcription as explicit scope boundaries. "
            "A comma appearing anywhere inside a root/fraction/function argument is a HARD boundary that "
            "closes that argument immediately — treat it exactly like a closing parenthesis, even though "
            "no explicit closing word was spoken. Contrast these two literal transcriptions carefully, "
            "they differ ONLY by the comma and must produce DIFFERENT LaTeX:\n"
            "  - 'racine carrée de x, plus un' -> $\\sqrt{x}+1$  (comma closes the root right after 'x')\n"
            "  - 'racine carrée de x plus un' -> $\\sqrt{x+1}$  (no comma, 'plus un' stays inside)\n"
            "Apply the same logic to fractions ('... sur ...') and any spoken grouping. The marker 'le "
            "tout' always explicitly closes the group up to that point, functioning like the comma above.\n\n"

            "RULE 6 — COMPARATORS & QUANTIFIERS (apply consistently everywhere, not only in simple "
            "inequalities):\n"
            "Always convert comparison phrases into their symbol, even inside quantifier statements: "
            "'supérieur à' -> >, 'supérieur ou égal à' -> \\geq, 'inférieur à' -> <, 'inférieur ou égal à' "
            "-> \\leq, 'différent de' -> \\neq. 'pour tout' -> \\forall, 'il existe' -> \\exists.\n"
            "Example: 'pour tout epsilon supérieur à zéro, il existe delta tel que...' -> "
            "$\\forall \\varepsilon > 0,\\ \\exists\\, \\delta \\text{ tel que...}$ — do not turn 'epsilon "
            "supérieur à zéro' into an index like epsilon_0, and do not capitalize 'delta' into \\Delta "
            "unless 'majuscule' was said.\n\n"

            "RULE 7 — FUNCTIONS & VISUAL FORMATTING:\n"
            "Always wrap function arguments in parentheses for consistency: \\sin(x), \\cos(x), \\tan(x), "
            "\\ln(x), \\log(x) — never \\sin x without parentheses.\n"
            "When parentheses wrap a fraction or another tall element, use \\left( ... \\right) so the "
            "delimiters scale correctly, e.g. \\tan\\left(\\frac{\\pi}{4}\\right) = 1.\n\n"

            "RULE 8 — SYSTEMS OF EQUATIONS:\n"
            "When the user explicitly dictates a 'système' of equations, use \\begin{cases}...\\end{cases} "
            "(single brace notation), not \\begin{aligned}, which does not convey 'system'.\n\n"

            "RULE 9 — STRICT NO HALLUCINATION:\n"
            "Do NOT add mathematical deductions, corollaries, definitions, or equations that were NOT "
            "explicitly spoken. If the user dictates an incomplete theorem, leave it as dictated. STOP "
            "generating when you have transcribed what was spoken. Correcting a garbled ASR fragment "
            "(RULE 0) is allowed; inventing new mathematical content is not.\n\n"

            "OUTPUT: Only the final result. NO markdown code blocks, NO explanations, NO introductory words."
        )
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                model="llama-3.3-70b-versatile",
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
        except Exception:
            return ""

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
        formatted_body = self._format_body_paragraphs(body_sentences)
        parts = [greeting]
        parts.extend(formatted_body)
        parts.append(signoff)
        return "\n\n".join(parts)

    def _default_greeting(self, lang_iso: str) -> str:
        greetings = {
            "fr": "Bonjour,", "en": "Hello,", "es": "Hola,", "de": "Hallo,",
            "it": "Buongiorno,", "pt": "Olá,"
        }
        return greetings.get(lang_iso, "Hello,")

    def _default_signoff(self, lang_iso: str) -> str:
        signoffs = {
            "fr": "Cordialement,", "en": "Best regards,", "es": "Saludos cordiales,",
            "de": "Mit freundlichen Grüßen,", "it": "Cordiali saluti,", "pt": "Atenciosamente,"
        }
        return signoffs.get(lang_iso, "Best regards,")

    def _format_body_paragraphs(self, sentences: list) -> list:
        if not sentences:
            return []
        paragraphs = []
        current_para = []
        transition_patterns = [
            r'^(however|nevertheless|furthermore|moreover|consequently|therefore|meanwhile)',
            r'^(cependant|néanmoins|par\s+ailleurs|de\s+plus|ensuite|enfin|en\s+conclusion)'
        ]
        for sentence in sentences:
            sent_lower = sentence.lower().strip()
            is_transition = any(re.search(pattern, sent_lower) for pattern in transition_patterns)
            if (is_transition and current_para) or len(current_para) >= 2:
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
        audio_duration = time.time() - self.app_state.audio.recording_start_time

        try:
            self._previous_active_window = win32gui.GetForegroundWindow()
        except Exception:
            pass

        self.event_bus.publish("recording_stopped", None)

        def _process_transcription():
            self.event_bus.publish("processing_started", None)
            try:
                self.audio_manager.stop_recording()
                time.sleep(0.1)
                
                frames = self.audio_manager.get_frames()
                if not frames:
                    return

                temp_path = os.path.join(tempfile.gettempdir(), f"ozmoz_full_{uuid.uuid4().hex}.wav")
                try:
                    with wave.open(temp_path, "wb") as wf:
                        wf.setnchannels(AppConfig.AUDIO_CHANNELS)
                        wf.setsampwidth(self.audio_manager._pyaudio_instance.get_sample_size(AppConfig.AUDIO_FORMAT))
                        wf.setframerate(AppConfig.AUDIO_RATE)
                        wf.writeframes(b"".join(frames))
                    
                    start_process_time = time.time()
                    text = self.transcription_service.transcribe(temp_path, duration=audio_duration)
                    processing_time = time.time() - start_process_time
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                
                if text and not (text.startswith("⚠️") or text.startswith("❌")):
                    sys_cfg = self.transcription_service.mode_manager.get_mode("system")
                    ui_model = sys_cfg.get("active_model", "Whisper V3 Turbo")
                    if "Local" in ui_model:
                        used_method = f"local-{ui_model.replace(' ', '-').lower()}"
                    else:
                        active_api_model = GROQ_MODEL_MAPPING.get(ui_model, "whisper-large-v3-turbo")
                        used_method = f"groq-{active_api_model}"

                    self.history_manager.add_entry(
                        text=text.strip(),
                        duration_sec=audio_duration,
                        processing_sec=processing_time,
                        method=used_method
                    )

                    if self.app_state.audio.sound_enabled:
                        self.sound_manager.play("beep_off")

                    time.sleep(0.1)
                    if self._previous_active_window:
                        try:
                            win32gui.SetForegroundWindow(self._previous_active_window)
                            time.sleep(0.15)
                        except Exception:
                            pass
                            
                    self.clipboard_manager.paste_and_clear(text)

            except Exception:
                pass
            finally:
                self.event_bus.publish("processing_finished", None)
                self.app_state.is_busy = False
                self._is_stopping = False

        global_executor.submit(_process_transcription)