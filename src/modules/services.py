import concurrent.futures
import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pyautogui
import pyperclip
import win32con
import win32gui
from cerebras.cloud.sdk import Cerebras
from groq import Groq

from modules.config import AppConfig

# --- Configuration Constants ---

PROMPTS = {
    "vision": """# ROLE
You are Ozmoz, a helpful AI assistant capable of seeing the user's screen.
# CONTEXT
Current Date: {date}
# INSTRUCTIONS
- Respond to the user's vocal request based on the visual context provided in the image.
- If the user asks to describe the screen, provide a detailed description.
- Respond in Markdown.
""",
    "web_search": """# ROLE
You are Ozmoz, a direct and efficient desktop AI assistant.
# CONTEXT
Current Date: {date}
# PRIMARY DIRECTIVES
- Respond exclusively in Markdown.
- Be direct.
- Never reveal you are an AI.
# TASK
- If modifying <selected_text>, output ONLY the modified text.
- Respond in the user's language.
# TOOLS
### Internet Search
- Accesses real-time information.
- **MANDATORY:** You **MUST** cite sources (URLs) at the end under "Sources:".
# OPERATIONAL CONTEXT
Answer using web search.
{selection_context}
""",
    "agent_system": """# ROLE & PERSONA
You are Ozmoz, a specialized AI agent.
# FORMATTING
- Markdown.
- LaTeX: Inline `$E=mc^2$`, Block `$$ \\int dx $$`.
# INSTRUCTIONS
{prompt}
# DATA
<user_instruction>User command</user_instruction>
<selected_text>Selection</selected_text>
""",
    "agent_user": """<user_instruction>
{instruction}
</user_instruction>

{selection_block}
""",
    "general": """# ROLE
You are Ozmoz.
# DIRECTIVES
- Respond in Markdown.
- Be direct.
- Never reveal you are an AI.
# TASK
- If modifying text, output ONLY the modified text.
- Use user's language.
# TOOLS
- Internet Search: For current events.
- Code Interpreter: For math/data.
- Cite sources.

# CONTEXT
Date: {date}.
{image_context}
{selection_context}
""",
}


class ContextManager:
    """
    Manages the context window for LLMs.
    """

    def __init__(self, app_state: Any) -> None:
        self.app_state = app_state

    def get_model_context_limit(self, model_id: str) -> int:
        default_limit = 6000
        if not self.app_state.cached_remote_config:
            return default_limit

        for item in self.app_state.cached_remote_config:
            if item.get("name") == model_id:
                return item.get("tokens_per_minute", default_limit)
        return default_limit

    def count_tokens_approx(self, text: str) -> int:
        return len(text) // 3 if text else 0

    def truncate_text_by_tokens(self, text: str, max_tokens: int) -> str:
        if not text or self.count_tokens_approx(text) <= max_tokens:
            return text

        max_chars = int(max_tokens * 3.5)
        if len(text) <= max_chars:
            return text

        text = text[:max_chars]
        if (last_space := text.rfind(" ")) != -1:
            text = text[:last_space]

        return text + "\n... [TRUNCATED] ..."

    def reduce_context_to_fit_limit(
        self,
        fixed_prompt: str,
        history: List[Dict[str, Any]],
        selected_text: str,
        model_limit: int,
    ) -> Tuple[List[Dict[str, Any]], str]:
        RESPONSE_BUFFER = 1024
        target_limit = model_limit - RESPONSE_BUFFER

        def calculate_total_tokens() -> int:
            history_text = "".join(
                [
                    message.get("content", "")
                    for message in history
                    if isinstance(message.get("content"), str)
                ]
            )
            return self.count_tokens_approx(fixed_prompt + history_text + selected_text)

        initial_tokens = calculate_total_tokens()
        if initial_tokens <= target_limit:
            return history, selected_text

        # Compression Strategy
        MIN_HISTORY_TOKENS = 300
        SELECTED_PRIORITY = 0.9

        if history:
            system_messages = [m for m in history if m.get("role") == "system"]
            conversation_pairs = []
            buffer = []

            for message in reversed(history):
                if message.get("role") in ["user", "assistant"]:
                    buffer.append(message)
                    if len(buffer) == 2:
                        conversation_pairs.append(buffer)
                        buffer = []

            keep_pairs = conversation_pairs[:2]
            compressed_history = system_messages + [
                msg for pair in keep_pairs for msg in pair
            ]

            for message in compressed_history:
                if isinstance(message.get("content"), str):
                    message["content"] = self.truncate_text_by_tokens(
                        message["content"], MIN_HISTORY_TOKENS
                    )

            history = compressed_history
            current_tokens = calculate_total_tokens()
        else:
            current_tokens = initial_tokens

        if current_tokens > target_limit and selected_text:
            keep_count = int(
                self.count_tokens_approx(selected_text) * SELECTED_PRIORITY
            )
            selected_text = self.truncate_text_by_tokens(selected_text, keep_count)
            current_tokens = calculate_total_tokens()

        if current_tokens > target_limit and selected_text:
            excess_tokens = current_tokens - target_limit
            cut_amount = max(int(excess_tokens * 3.5), 0)
            selected_text = selected_text[:-cut_amount]

        return history, selected_text


class GenerationController:
    """
    Facade Controller for all generation workflows (Text, Web, Vision).
    """

    def __init__(
        self,
        app_state: Any,
        window: Any,
        audio_manager: Any,
        sound_manager: Any,
        transcription_manager: Any,
        stats_manager: Any,
        system_health_manager: Any,
        hotkey_manager: Any,
        config_manager: Any,
        credential_manager: Any,
    ) -> None:
        self.app_state = app_state
        self.window = window
        self.audio_manager = audio_manager
        self.sound_manager = sound_manager
        self.transcription_manager = transcription_manager
        self.stats_manager = stats_manager
        self.system_health_manager = system_health_manager
        self.hotkey_manager = hotkey_manager
        self.config_manager = config_manager
        self.credential_manager = credential_manager

    def validate_preconditions(self) -> Tuple[bool, Optional[str]]:
        if (
            self.system_health_manager
            and not self.system_health_manager._validate_hotkey_state()
        ):
            self.hotkey_manager.register_all()
            return False, None

        if self.app_state.settings_open:
            return False, None

        if self.app_state.is_busy:
            return False, None

        return True, None

    def warmup(self) -> None:
        def _warmup_worker() -> None:
            try:
                cerebras_key = self.credential_manager.get_api_key("cerebras")
                if cerebras_key and self.app_state.cerebras_client is None:
                    self.app_state.cerebras_client = Cerebras(api_key=cerebras_key)

                groq_key = self.credential_manager.get_api_key("groq_ai")
                if groq_key and self.app_state.groq_client is None:
                    self.app_state.groq_client = Groq(api_key=groq_key)
            except Exception as e:
                logging.warning(f"LLM Client warmup warning: {e}")

        threading.Thread(target=_warmup_worker, daemon=True).start()

    def force_reset_state_after_timeout(self) -> None:
        if self.app_state.is_busy:
            logging.warning("Operation watchdog triggered. Forcing state reset.")
            try:
                if self.window:
                    error_message = "The operation took too long. Please try again."
                    self.window.evaluate_js(
                        f"displayError({json.dumps(error_message)})"
                    )
                    self.window.evaluate_js("setSettingsButtonState(false)")
            except Exception:
                pass

            self.app_state.is_busy = False
            self.app_state.is_recording = False
            self.app_state.ai_recording = False

    def start_recording(self, css_class: str = "ai-recording") -> str:
        if self.app_state.is_recording:
            try:
                self.transcription_manager.stop_recording_and_transcribe()
            except Exception:
                pass
            time.sleep(0.1)

        self.sound_manager.play("beep_on")
        time.sleep(0.1)

        self.app_state.ai_recording = True
        self.app_state.recording_start_time = time.time()
        self.app_state.was_muted_during_recording = self.app_state.mute_sound

        if self.app_state.mute_sound:
            self.audio_manager.mute_system_volume()

        try:
            ai_modes = [
                "ai-recording",
                "screen-vision-recording",
                "web-search-recording",
            ]
            if css_class in ai_modes:
                self.window.evaluate_js("setAIButtonState('recording')")
                self.window.evaluate_js(
                    "window.dispatchEvent(new CustomEvent('pywebview', { detail: 'start_asking' }))"
                )
            else:
                self.window.evaluate_js(
                    "window.dispatchEvent(new CustomEvent('pywebview', { detail: 'start_recording' }))"
                )

            self.window.evaluate_js("startVisualizationOnly()")
        except Exception:
            pass

        self.audio_manager.initialize()
        temp_dir = tempfile.gettempdir()
        audio_file_path = os.path.join(temp_dir, AppConfig.AUDIO_OUTPUT_FILENAME)

        self.app_state.is_recording = True

        def vad_callback() -> None:
            self.app_state.is_recording = False

        threading.Thread(
            target=self.audio_manager._record_audio_worker,
            args=(audio_file_path,),
            daemon=True,
        ).start()

        self.audio_manager._silence_callback = vad_callback
        return audio_file_path

    def stop_recording(self, css_class: str = "ai-recording") -> Tuple[str, float]:
        if self.app_state.sound_enabled:
            self.sound_manager.play("beep_off")

        if self.app_state.was_muted_during_recording:
            self.audio_manager.unmute_system_volume()
            self.app_state.was_muted_during_recording = False

        self.app_state.ai_recording = False
        self.app_state.is_recording = False

        duration = 0.0
        if self.app_state.recording_start_time > 0:
            duration = time.time() - self.app_state.recording_start_time

        try:
            self.window.evaluate_js("stopVisualizationOnly()")
            ai_modes = [
                "ai-recording",
                "screen-vision-recording",
                "web-search-recording",
            ]
            if css_class not in ai_modes:
                self.window.evaluate_js(
                    "window.dispatchEvent(new CustomEvent('pywebview', { detail: 'stop_recording' }))"
                )
        except Exception:
            pass

        time.sleep(0.3)
        audio_file_path = os.path.join(
            tempfile.gettempdir(), AppConfig.AUDIO_OUTPUT_FILENAME
        )

        return audio_file_path, duration

    def cleanup_recording_ui(self, css_class: str = "ai-recording") -> None:
        self.app_state.ai_recording = False
        self.app_state.is_busy = False
        try:
            self.window.evaluate_js("setSettingsButtonState(false)")
            self.window.evaluate_js("stopVisualizationOnly()")
            self.window.evaluate_js(
                "window.dispatchEvent(new CustomEvent('pywebview', { detail: 'stop_recording' }))"
            )
            self.window.evaluate_js("setAIButtonState('idle')")
        except Exception:
            pass

    def show_loading_ui(self) -> None:
        try:
            self.window.evaluate_js(
                """
                window.originalWindowHeight = window.innerHeight;
                const vizContainer = document.getElementById('visualizer-container');
                if (vizContainer) { vizContainer.style.display = 'none'; }
            """
            )
            self.window.evaluate_js(
                """
            let responseContainer = document.getElementById('ai-response-container');
            if (!responseContainer) {
                responseContainer = document.createElement('div');
                responseContainer.id = 'ai-response-container';
                responseContainer.className = 'ai-response-container';
                document.querySelector('.container').insertBefore(responseContainer, document.querySelector('.help-container'));
            }
            responseContainer.style.display = 'flex';
            responseContainer.style.justifyContent = 'flex-start';
            responseContainer.innerHTML = '';

            const mainStyle = document.createElement('style');
            mainStyle.textContent = `
                .loading-container { display: flex; flex-direction: column; width: 100%; height: 150%; position: absolute; top: 0; left: 0; padding: 0; margin: 0; }
                .chatbox { width: 400px; padding: 8px; height: 140px; background-color: #222222; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.3); color: white; max-width: 380px; }
                .loading-line { height: 8px; background: linear-gradient(100deg, #2e2e2e 30%, #444 50%, #2e2e2e 70%); background-size: 200% 100%; animation: loading 1.5s infinite; border-radius: 4px; margin: 6px 0; }
                .loading-line.short { width: 40%; } .loading-line.medium { width: 60%; } .loading-line.long { width: 80%; }
                @keyframes loading { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
            `;
            document.head.appendChild(mainStyle);

            responseContainer.innerHTML = `
                <div class="loading-container">
                    <div class="chatbox"><div class="loading-line long"></div><div class="loading-line medium"></div><div class="loading-line short"></div></div>
                </div>
            `;
            """
            )
            if self.window:
                self.window.resize(415, 114)
        except Exception:
            pass

    def reset_ui_for_new_generation(self) -> None:
        if self.app_state.is_ai_response_visible:
            try:
                self.window.evaluate_js("resetUIForNewGeneration()")
                time.sleep(0.2)
            except Exception:
                pass

    def _get_model_provider(self, model_id: str) -> str:
        if not self.app_state.cached_remote_config:
            self.config_manager.load_and_parse_remote_config()

        for item in self.app_state.cached_remote_config:
            if item.get("name") == model_id:
                return item.get("provider", "groq")
        return "groq"

    def execute_ai_api_call(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        show_streaming: bool = True,
        processing_mode: str = "text",
    ) -> Optional[str]:
        provider = self._get_model_provider(model)
        try:
            stream = None
            if not self.app_state.is_ai_response_visible:
                self.app_state.conversation_history.clear()

            if provider == "cerebras":
                stream = self._call_cerebras(messages, model)
            else:
                stream = self._call_groq(messages, model)

            if show_streaming and self.window:
                self.window.evaluate_js(f"setupStreamingUI('{processing_mode}')")

            result_text = self._process_stream(stream, show_streaming)

            if show_streaming and self.window:
                self.window.evaluate_js("finalizeStreamedContent()")
            try:
                if self.window:
                    self.window.evaluate_js("setAIButtonState('success')")
            except Exception:
                pass

            self.app_state.is_ai_response_visible = True
            return result_text

        except Exception as e:
            logging.critical(f"Generation Error ({provider}): {e}", exc_info=True)
            self._handle_api_error(e)
            return None

    def _call_groq(self, messages: List[Dict[str, Any]], model: str) -> Any:
        if self.app_state.groq_client is None:
            api_key = self.credential_manager.get_api_key("groq_ai")
            if not api_key:
                raise ValueError("Missing Groq API Key")
            self.app_state.groq_client = Groq(api_key=api_key)

        client = self.app_state.groq_client
        extra_headers = (
            {"Groq-Model-Version": "latest"}
            if model in self.app_state.advanced_model_list
            else None
        )
        params = {"model": model, "messages": messages, "stream": True}
        if extra_headers:
            params["extra_headers"] = extra_headers

        if model in self.app_state.advanced_model_list:
            params["model"] = "groq/compound"
            params["max_completion_tokens"] = 2500
        elif model in self.app_state.tool_model_list:
            params["tools"] = [{"type": "browser_search"}]

        return client.chat.completions.create(**params)

    def _call_cerebras(self, messages: List[Dict[str, Any]], model: str) -> Any:
        if self.app_state.cerebras_client is None:
            api_key = self.credential_manager.get_api_key("cerebras")
            if not api_key:
                raise ValueError("Missing Cerebras API Key")
            self.app_state.cerebras_client = Cerebras(api_key=api_key)

        client = self.app_state.cerebras_client
        params = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_completion_tokens": 8192,
            "temperature": 0.7,
            "top_p": 0.95,
        }
        return client.chat.completions.create(**params)

    def _process_stream(self, stream: Any, show_streaming: bool) -> str:
        full_result = ""
        buffer = ""
        is_thinking = None
        START_TAG = "<think>"
        END_TAG = "</think>"

        for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            if is_thinking is False:
                if show_streaming:
                    safe_content = json.dumps(content)
                    self.window.evaluate_js(f"appendaiStreamChunk({safe_content})")
                full_result += content
                continue

            buffer += content
            if is_thinking is None:
                stripped_buffer = buffer.lstrip()
                if stripped_buffer.startswith(START_TAG):
                    is_thinking = True
                elif len(stripped_buffer) >= len(START_TAG) or (
                    stripped_buffer and not START_TAG.startswith(stripped_buffer)
                ):
                    is_thinking = False
                    if show_streaming:
                        self.window.evaluate_js(
                            f"appendaiStreamChunk({json.dumps(buffer)})"
                        )
                    full_result += buffer

            if is_thinking is True and END_TAG in buffer:
                _, _, remainder = buffer.partition(END_TAG)
                is_thinking = False
                if remainder:
                    if show_streaming:
                        self.window.evaluate_js(
                            f"appendaiStreamChunk({json.dumps(remainder)})"
                        )
                    full_result += remainder

        if show_streaming:
            self.window.evaluate_js(f"appendaiStreamChunk({json.dumps('\n')})")
        return full_result

    def _handle_api_error(self, e: Exception) -> None:
        try:
            self.window.evaluate_js("setAIButtonState('idle')")
        except Exception:
            pass
        self.app_state.is_ai_response_visible = False
        msg = "An API error occurred."
        status_code = getattr(e, "status_code", None)
        if status_code == 413:
            msg = "Request too large."
        elif status_code == 429:
            msg = "Rate limit reached."
        elif status_code == 401:
            msg = "Invalid API Key."
        self.window.evaluate_js(f"displayError({json.dumps(msg)})")

    def safe_remove_file(self, path: Optional[str]) -> None:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    def cleanup_temp_files(
        self, audio_path: Optional[str], screenshot_path: Optional[str]
    ) -> None:
        self.safe_remove_file(audio_path)
        self.safe_remove_file(screenshot_path)


class VisionManager:
    def __init__(
        self,
        app_state: Any,
        config_manager: Any,
        screen_manager: Any,
        transcription_service: Any,
        stats_manager: Any,
        history_manager: Any,
        credential_manager: Any,
        generation_controller: GenerationController,
    ) -> None:
        self.app_state = app_state
        self.config_manager = config_manager
        self.screen_manager = screen_manager
        self.transcription_service = transcription_service
        self.stats_manager = stats_manager
        self.history_manager = history_manager
        self.credential_manager = credential_manager
        self.generation_controller = generation_controller

    def select_best_vision_model(self) -> str:
        available_models = self.config_manager.fetch_ai_models()
        for model_id in self.app_state.screen_vision_model_list:
            if model_id in available_models:
                return model_id
        if (
            self.app_state.model in available_models
            and self.config_manager.check_if_model_is_multimodal(self.app_state.model)
        ):
            return self.app_state.model
        return available_models[0] if available_models else self.app_state.model

    def process_vision_capture(self, model: str) -> Tuple[Optional[str], Optional[str]]:
        file_path = self.screen_manager.capture()
        base64_image = None
        if file_path:
            if self.config_manager.check_if_model_is_multimodal(model):
                base64_image = self.screen_manager.convert_image_to_base64(file_path)
            else:
                logging.warning("Vision attempted with non-multimodal model.")
        return file_path, base64_image

    def generate_screen_vision_text(self) -> None:
        available_models = self.config_manager.fetch_ai_models()
        compatible_models = [
            m for m in self.app_state.screen_vision_model_list if m in available_models
        ]
        if (
            not compatible_models
            and not self.config_manager.check_if_model_is_multimodal(
                self.app_state.model
            )
        ):
            message = "No vision-capable model available."
            if self.generation_controller.window:
                self.generation_controller.window.evaluate_js(
                    f"displayError({json.dumps(message)})"
                )
            return

        is_valid, error = self.generation_controller.validate_preconditions()
        if not is_valid:
            if error and self.generation_controller.window:
                self.generation_controller.window.evaluate_js(
                    f"displayError({json.dumps(error)})"
                )
            return

        timer = threading.Timer(
            60.0, self.generation_controller.force_reset_state_after_timeout
        )
        timer.start()

        audio_file_path = None
        screen_path = None
        self.app_state.is_busy = True
        self.generation_controller.reset_ui_for_new_generation()

        try:
            if not self.app_state.ai_recording:
                try:
                    audio_file_path = self.generation_controller.start_recording(
                        css_class="screen-vision-recording"
                    )
                    return
                except Exception:
                    self.app_state.is_busy = False
                    return

            audio_file_path, duration = self.generation_controller.stop_recording(
                css_class="screen-vision-recording"
            )
            if not os.path.exists(audio_file_path):
                self.app_state.is_busy = False
                return

            self.generation_controller.show_loading_ui()
            transcript = self.transcription_service.transcribe(
                audio_file_path, self.app_state.language, duration
            )

            if transcript.lower().startswith("error"):
                if self.generation_controller.window:
                    self.generation_controller.window.evaluate_js(
                        f"displayError({json.dumps(transcript)})"
                    )
                return

            self.stats_manager.update_stats(transcript, duration, is_generation=True)
            model = self.select_best_vision_model()
            screen_path, base64_img = self.process_vision_capture(model)

            if not base64_img:
                raise ValueError("Selected model cannot process images.")

            if not self.app_state.is_ai_response_visible:
                self.app_state.conversation_history.clear()

            date_str = datetime.now().strftime("%A, %B %d, %Y")
            system_prompt = PROMPTS["vision"].format(date=date_str)

            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_prompt}
            ]
            messages.extend(self.app_state.conversation_history)
            user_content: List[Dict[str, Any]] = [{"type": "text", "text": transcript}]
            user_content.append({"type": "image_url", "image_url": {"url": base64_img}})
            messages.append({"role": "user", "content": user_content})

            response = self.generation_controller.execute_ai_api_call(
                messages, model, show_streaming=True, processing_mode="vision"
            )

            if response:
                self.history_manager.add_entry(
                    f"[Vision] {transcript}\n[AI] {response}"
                )
                if self.app_state.settings_window:
                    self.app_state.settings_window.evaluate_js("refreshDashboardFull()")
                self.app_state.conversation_history.append(
                    {"role": "user", "content": user_content}
                )
                self.app_state.conversation_history.append(
                    {"role": "assistant", "content": response}
                )

        except Exception as e:
            logging.error(f"Vision Crash: {e}", exc_info=True)
            self.generation_controller.cleanup_recording_ui("screen-vision-recording")
        finally:
            self.app_state.is_busy = False
            if timer.is_alive():
                timer.cancel()
            self.generation_controller.cleanup_temp_files(audio_file_path, screen_path)
            try:
                self.generation_controller.window.evaluate_js(
                    "setSettingsButtonState(false)"
                )
            except Exception:
                pass


class WebSearchManager:
    def __init__(
        self,
        app_state: Any,
        config_manager: Any,
        transcription_service: Any,
        stats_manager: Any,
        history_manager: Any,
        clipboard_manager: Any,
        generation_controller: GenerationController,
    ) -> None:
        self.app_state = app_state
        self.config_manager = config_manager
        self.transcription_service = transcription_service
        self.stats_manager = stats_manager
        self.history_manager = history_manager
        self.clipboard_manager = clipboard_manager
        self.generation_controller = generation_controller

    def select_best_web_model(self) -> str:
        available_models = self.config_manager.fetch_ai_models()
        for model_id in self.app_state.web_search_model_list:
            if model_id in available_models:
                return model_id
        if self.app_state.model in available_models:
            return self.app_state.model
        return available_models[0] if available_models else self.app_state.model

    def generate_web_search_text(self) -> None:
        available_models = self.config_manager.fetch_ai_models()
        compatible_models = [
            m for m in self.app_state.web_search_model_list if m in available_models
        ]
        if not compatible_models:
            message = "No web search model available."
            if self.generation_controller.window:
                self.generation_controller.window.evaluate_js(
                    f"displayError({json.dumps(message)})"
                )
            return

        is_valid, error = self.generation_controller.validate_preconditions()
        if not is_valid:
            return

        timer = threading.Timer(
            60.0, self.generation_controller.force_reset_state_after_timeout
        )
        timer.start()

        audio_file_path = None
        self.app_state.is_busy = True
        self.generation_controller.reset_ui_for_new_generation()

        try:
            if not self.app_state.ai_recording:
                try:
                    audio_file_path = self.generation_controller.start_recording(
                        css_class="web-search-recording"
                    )
                    return
                except Exception:
                    self.app_state.is_busy = False
                    return

            audio_file_path, duration = self.generation_controller.stop_recording(
                css_class="web-search-recording"
            )
            if not os.path.exists(audio_file_path):
                self.app_state.is_busy = False
                return

            self.generation_controller.show_loading_ui()
            transcript = self.transcription_service.transcribe(
                audio_file_path, self.app_state.language, duration
            )

            if transcript.lower().startswith("error"):
                if self.generation_controller.window:
                    self.generation_controller.window.evaluate_js(
                        f"displayError({json.dumps(transcript)})"
                    )
                return

            self.stats_manager.update_stats(transcript, duration, is_generation=True)
            selected_text = self.clipboard_manager.get_selected_text()
            model = self.select_best_web_model()

            date_str = datetime.now().strftime("%A, %B %d, %Y")
            sel_context = ""
            if selected_text:
                sel_context = f"\n<primary_context_from_selection>\n{selected_text}\n</primary_context_from_selection>"

            system_prompt = PROMPTS["web_search"].format(
                date=date_str, selection_context=sel_context
            )

            if not self.app_state.is_ai_response_visible:
                self.app_state.conversation_history.clear()

            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_prompt}
            ]
            messages.extend(self.app_state.conversation_history)
            messages.append({"role": "user", "content": transcript})

            response = self.generation_controller.execute_ai_api_call(
                messages, model, show_streaming=True, processing_mode="web"
            )

            if response:
                self.history_manager.add_entry(f"[Web] {transcript}\n[AI] {response}")
                if self.app_state.settings_window:
                    self.app_state.settings_window.evaluate_js("refreshDashboardFull()")
                self.app_state.conversation_history.append(
                    {"role": "user", "content": transcript}
                )
                self.app_state.conversation_history.append(
                    {"role": "assistant", "content": response}
                )

        except Exception as e:
            logging.error(f"Web Search Crash: {e}", exc_info=True)
            self.generation_controller.cleanup_recording_ui(
                css_class="web-search-recording"
            )
        finally:
            self.app_state.is_busy = False
            if timer.is_alive():
                timer.cancel()
            self.generation_controller.cleanup_temp_files(audio_file_path, None)
            try:
                self.generation_controller.window.evaluate_js(
                    "setSettingsButtonState(false)"
                )
            except Exception:
                pass


class AiGenerationManager:
    def __init__(
        self,
        app_state: Any,
        config_manager: Any,
        context_manager: ContextManager,
        transcription_service: Any,
        stats_manager: Any,
        history_manager: Any,
        clipboard_manager: Any,
        screen_manager: Any,
        agent_manager: Any,
        credential_manager: Any,
        generation_controller: GenerationController,
    ) -> None:
        self.app_state = app_state
        self.config_manager = config_manager
        self.context_manager = context_manager
        self.transcription_service = transcription_service
        self.stats_manager = stats_manager
        self.history_manager = history_manager
        self.clipboard_manager = clipboard_manager
        self.screen_manager = screen_manager
        self.agent_manager = agent_manager
        self.credential_manager = credential_manager
        self.generation_controller = generation_controller

    def capture_context_for_agent(
        self, agent: Dict[str, Any], model: str
    ) -> Dict[str, Any]:
        context = {
            "selected_text": self.clipboard_manager.get_selected_text(),
            "image_data_url": None,
        }
        if agent.get("screen_vision"):
            path = self.screen_manager.capture()
            if path:
                if self.config_manager.check_if_model_is_multimodal(model):
                    context["image_data_url"] = (
                        self.screen_manager.convert_image_to_base64(path)
                    )
                self.generation_controller.safe_remove_file(path)
        return context

    def capture_context_for_general(self) -> Dict[str, Any]:
        context = {
            "selected_text": "",
            "image_data_url": None,
            "screenshot_path": None,
        }
        try:
            if self.generation_controller.window:
                context["selected_text"] = (
                    self.generation_controller.window.evaluate_js(
                        "window.getSelection().toString()"
                    )
                )
        except Exception:
            pass
        if not context["selected_text"]:
            context["selected_text"] = self.clipboard_manager.get_selected_text()
        return context

    def find_triggered_agent(self, text: str) -> Tuple[Optional[Dict[str, Any]], str]:
        agents = [
            a
            for a in self.agent_manager.load_agents()
            if a.get("active") and a.get("trigger")
        ]
        lower_text = text.lower()
        for agent in agents:
            trigger_phrase = agent.get("trigger").strip().lower()
            if trigger_phrase and lower_text.startswith(trigger_phrase):
                return agent, text[len(trigger_phrase) :].strip()
        return None, text

    def execute_agent(
        self, agent: Dict[str, Any], instruction: str, full_text: str, duration: float
    ) -> Optional[str]:
        model = agent.get("model", self.app_state.model)
        if model not in self.config_manager.fetch_ai_models():
            return None

        try:
            context = self.capture_context_for_agent(agent, model)
        except PermissionError as e:
            if self.generation_controller.window:
                self.generation_controller.window.evaluate_js(
                    f"displayError({json.dumps(str(e))})"
                )
            return None

        sys_prompt = PROMPTS["agent_system"].format(prompt=agent["prompt"])

        sel_text = context["selected_text"] if context["selected_text"] else ""
        sel_block = f"<selected_text>\n{sel_text}\n</selected_text>" if sel_text else ""
        usr_prompt = PROMPTS["agent_user"].format(
            instruction=instruction, selection_block=sel_block
        )

        msgs: List[Dict[str, Any]] = [{"role": "system", "content": sys_prompt}]
        msgs.extend(self.app_state.conversation_history)

        u_content: List[Dict[str, Any]] = [{"type": "text", "text": full_text}]
        if context["image_data_url"]:
            u_content.append(
                {"type": "image_url", "image_url": {"url": context["image_data_url"]}}
            )
        msgs.append({"role": "user", "content": u_content})

        mode = "vision" if agent.get("screen_vision") else "text"
        autopaste = agent.get("autopaste", True)

        response = self.generation_controller.execute_ai_api_call(
            msgs, model, show_streaming=not autopaste, processing_mode=mode
        )

        if response:
            self.app_state.conversation_history.append(
                {"role": "user", "content": usr_prompt}
            )
            self.app_state.conversation_history.append(
                {"role": "assistant", "content": response}
            )
            if autopaste:
                self.handle_autopaste(response)
            else:
                pyperclip.copy(response)
            self.history_manager.add_entry(
                f"[Agent {agent['name']}] {instruction}\n[AI] {response}"
            )
            if self.app_state.settings_window:
                self.app_state.settings_window.evaluate_js("refreshDashboardFull()")
        return response

    def handle_autopaste(self, result_text: str) -> None:
        try:
            self.generation_controller.reset_ui_for_new_generation()
            time.sleep(0.1)
            window_handle = win32gui.FindWindow(None, "Ozmoz")
            if window_handle:
                win32gui.ShowWindow(window_handle, win32con.SW_HIDE)
            previous_clipboard = pyperclip.paste()
            pyperclip.copy(result_text)
            pyautogui.hotkey("ctrl", "v")
            threading.Timer(0.5, lambda: pyperclip.copy(previous_clipboard)).start()
        except Exception as e:
            logging.error(f"Autopaste Error: {e}")

    def execute_general_generation(
        self, text_input: str, context: Dict[str, Any], duration: float
    ) -> Optional[str]:
        limit = self.context_manager.get_model_context_limit(self.app_state.model)
        history, selected_text = self.context_manager.reduce_context_to_fit_limit(
            fixed_prompt=text_input,
            history=self.app_state.conversation_history,
            selected_text=context["selected_text"],
            model_limit=limit,
        )
        self.app_state.conversation_history = history
        context["selected_text"] = selected_text

        date_str = datetime.now().strftime("%A, %B %d, %Y")
        img_ctx = "IMAGE provided." if context["image_data_url"] else ""
        sel_ctx = (
            f"Mission: Apply instruction to selection.\n<sel>\n{context['selected_text']}\n</sel>"
            if context["selected_text"]
            else "Mission: General knowledge."
        )

        system_prompt = PROMPTS["general"].format(
            date=date_str, image_context=img_ctx, selection_context=sel_ctx
        )

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(self.app_state.conversation_history)
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": text_input}]
        if context["image_data_url"]:
            user_content.append(
                {"type": "image_url", "image_url": {"url": context["image_data_url"]}}
            )
        messages.append({"role": "user", "content": user_content})

        response = self.generation_controller.execute_ai_api_call(
            messages, self.app_state.model, show_streaming=True, processing_mode="text"
        )

        if response:
            self.app_state.conversation_history.append(
                {"role": "user", "content": text_input}
            )
            self.app_state.conversation_history.append(
                {"role": "assistant", "content": response}
            )
            self.history_manager.add_entry(
                f"[User] {text_input}\n[AI] {response.strip()}"
            )
            if self.app_state.settings_window:
                self.app_state.settings_window.evaluate_js("refreshDashboardFull()")
        return response

    def generate_ai_text(self) -> None:
        is_valid, error = self.generation_controller.validate_preconditions()
        if not is_valid:
            if error and self.generation_controller.window:
                self.generation_controller.window.evaluate_js(
                    f"displayError({json.dumps(error)})"
                )
            return

        timer = threading.Timer(
            60.0, self.generation_controller.force_reset_state_after_timeout
        )
        timer.start()

        audio_file_path = None
        screen_path = None
        self.app_state.is_busy = True
        self.generation_controller.reset_ui_for_new_generation()

        try:
            if self.generation_controller.window:
                self.generation_controller.window.evaluate_js(
                    "setSettingsButtonState(true)"
                )

            if not self.app_state.ai_recording:
                try:
                    audio_file_path = self.generation_controller.start_recording()
                except Exception:
                    self.app_state.is_busy = False
                    return
                return

            audio_file_path, duration = self.generation_controller.stop_recording()
            if not os.path.exists(audio_file_path):
                self.app_state.is_busy = False
                self.generation_controller.cleanup_recording_ui()
                return

            self.generation_controller.show_loading_ui()
            transcript = None
            generation_context = None

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_transcription = executor.submit(
                    self.transcription_service.transcribe,
                    audio_file_path,
                    self.app_state.language,
                    duration,
                )
                future_context = executor.submit(self.capture_context_for_general)
                transcript = future_transcription.result()
                generation_context = future_context.result()

            if transcript.lower().startswith("error"):
                timer.cancel()
                self.app_state.is_busy = False
                self.app_state.is_ai_response_visible = False
                if self.generation_controller.window:
                    self.generation_controller.window.evaluate_js(
                        f"displayError({json.dumps(transcript)})"
                    )
                self.generation_controller.safe_remove_file(audio_file_path)
                return

            threading.Thread(
                target=self.stats_manager.update_stats,
                args=(transcript, duration),
                daemon=True,
            ).start()

            agent, instruction = self.find_triggered_agent(transcript)
            if agent:
                try:
                    self.execute_agent(agent, instruction, transcript, duration)
                    return
                except Exception as e:
                    logging.error(f"Agent Error: {e}")
                    return

            screen_path = generation_context.get("screenshot_path")
            self.execute_general_generation(transcript, generation_context, duration)

        except Exception as e:
            logging.error(f"AI Crash: {e}", exc_info=True)
            self.generation_controller.cleanup_recording_ui()
        finally:
            self.app_state.is_busy = False
            if timer.is_alive():
                timer.cancel()
            self.generation_controller.cleanup_temp_files(audio_file_path, screen_path)
            try:
                self.generation_controller.window.evaluate_js(
                    "setSettingsButtonState(false)"
                )
            except Exception:
                pass
