"""
Service Layer for Ozmoz.

This module orchestrates workflows involving multiple components:
- Context Management: Token counting and history compression.
- Generation Control: Coordinating Audio, UI, and API calls.
- Vision Services: Screen capture and multimodal processing.
- Web Search: Browser-enabled context retrieval.
- AI Orchestration: Managing agents, prompts, and streaming responses.

Security Notes:
    - All user inputs (paths, JS calls) are validated/sanitized.
    - API keys are never logged.
    - Path traversal protection via pathlib.
"""

import concurrent.futures
import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Third-party imports
import pyperclip
import win32con
import win32gui
from cerebras.cloud.sdk import Cerebras
from groq import Groq

# Local imports
from modules.config import AppConfig

# ============================================================================
# CONSTANTS - Configuration & Tuning Parameters
# ============================================================================

# Context Window Management
DEFAULT_CONTEXT_LIMIT_TOKENS = 6000  # Safe fallback for unknown models
RESPONSE_BUFFER_TOKENS = 1024  # Reserved space for model output
MIN_HISTORY_TOKENS = 300  # Minimum tokens to preserve in history compression
SELECTED_TEXT_PRIORITY_RATIO = 0.9  # Proportion of selected text to keep (90%)

# Character to Token Conversion (Heuristic)
# Based on empirical testing: 1 token ≈ 3-3.5 characters for English/Latin scripts
CHARS_PER_TOKEN_ESTIMATE = 3
CHARS_PER_TOKEN_TRUNCATION = 3.5  # Slightly higher for safety margin

# Audio & Recording
# Wait time for OS window compositor to refresh after hiding the UI window
COMPOSITOR_REFRESH_DELAY_SECONDS = 0.3
OPERATION_WATCHDOG_TIMEOUT_SECONDS = 60.0  # Force reset if operation hangs

# UI Update Delays
UI_UPDATE_SLEEP_SECONDS = 0.1  # Brief pause for JS evaluation to complete
UI_RESET_SLEEP_SECONDS = 0.2  # Pause after resetting UI state

# Stream Processing
COT_START_TAG = "<think>"  # Chain-of-Thought reasoning block start marker
COT_END_TAG = "</think>"  # Chain-of-Thought reasoning block end marker

# Agent & Model Defaults
MAX_AGENT_COMPLETION_TOKENS = 2500  # Token limit for advanced model agents

# Logging Filters
LOG_REDACTED_TEXT = "[REDACTED]"  # Placeholder for sensitive data in logs

logger = logging.getLogger(__name__)


# ============================================================================
# SECURITY UTILITIES
# ============================================================================


def sanitize_for_js(value: Any) -> str:
    """
    Safely encode a Python value for JavaScript evaluation.

    Prevents XSS injection by JSON-encoding all values passed to evaluate_js().

    Args:
        value: Any Python object (str, dict, list, etc.)

    Returns:
        JSON-encoded string safe for JS insertion.

    Example:
        >>> sanitize_for_js("Hello 'World'")
        '"Hello \'World\'"'
    """
    return json.dumps(value, ensure_ascii=False)


def validate_temp_file_path(filepath: str, expected_filename: str) -> Path:
    """
    Validate that a file path is within the system temp directory.

    Prevents path traversal attacks when handling temporary files.

    Args:
        filepath: Path to validate.
        expected_filename: Expected filename (security check).

    Returns:
        Validated Path object.

    Raises:
        ValueError: If path traversal detected or filename mismatch.

    Example:
        >>> validate_temp_file_path("/tmp/audio.wav", "audio.wav")
        Path('/tmp/audio.wav')
    """
    temp_base = Path(tempfile.gettempdir()).resolve()
    target_path = Path(filepath).resolve()

    if not target_path.is_relative_to(temp_base):
        raise ValueError(f"Path traversal detected: {filepath}")

    if target_path.name != expected_filename:
        raise ValueError(
            f"Filename mismatch: expected {expected_filename}, got {target_path.name}"
        )

    return target_path


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================


class ContextOverflowError(Exception):
    """Raised when context exceeds model's token limit after optimization."""


class TranscriptionError(Exception):
    """Raised when audio transcription fails."""


class ModelUnavailableError(Exception):
    """Raised when requested AI model is not available."""


class VisionCapabilityError(Exception):
    """Raised when vision operation requested on non-multimodal model."""


# ============================================================================
# CONTEXT MANAGER
# ============================================================================


class ContextManager:
    """
    Manages the context window for Large Language Models (LLMs).

    Responsibilities:
    - Token counting approximation (heuristic based).
    - Dynamic history compression (FIFO with semantic preservation).
    - Payload truncation to ensure API compliance.

    Thread Safety:
        This class is NOT thread-safe. Ensure single-threaded access.
    """

    def __init__(self, app_state: Any) -> None:
        """
        Initialize the ContextManager.

        Args:
            app_state: Global application state object.
        """
        self.app_state = app_state

    def get_model_context_limit(self, model_id: str) -> int:
        """
        Retrieve the effective token limit for a specific model from configuration.

        Args:
            model_id: The identifier of the AI model.

        Returns:
            The maximum tokens per minute (TPM) or safe default.

        Example:
            >>> manager.get_model_context_limit("llama-3.3-70b")
            8000
        """
        if not self.app_state.cached_remote_config:
            logger.warning(
                f"No cached config for model {model_id}, using default limit"
            )
            return DEFAULT_CONTEXT_LIMIT_TOKENS

        for item in self.app_state.cached_remote_config:
            if item.get("name") == model_id:
                limit = item.get("tokens_per_minute", DEFAULT_CONTEXT_LIMIT_TOKENS)
                logger.debug(f"Model {model_id} context limit: {limit} tokens")
                return limit

        logger.warning(f"Model {model_id} not found in config, using default limit")
        return DEFAULT_CONTEXT_LIMIT_TOKENS

    def count_tokens_approx(self, text: str) -> int:
        """
        Heuristic token counting (approx. 1 token ≈ 3 chars).

        Used for low-latency pre-flight checks before API calls.
        Note: This is an approximation. Actual tokenization may vary by model.

        Args:
            text: The text to estimate.

        Returns:
            Estimated token count.

        Example:
            >>> manager.count_tokens_approx("Hello world")
            3
        """
        if not text:
            return 0
        token_count = len(text) // CHARS_PER_TOKEN_ESTIMATE
        logger.debug(f"Estimated {token_count} tokens for {len(text)} chars")
        return token_count

    def truncate_text_by_tokens(self, text: str, max_tokens: int) -> str:
        """
        Hard truncation of text to fit within a specific token budget.

        Attempts to cut at word boundaries for legibility.

        Args:
            text: The input text.
            max_tokens: The maximum allowed tokens.

        Returns:
            The truncated text string with truncation marker if cut.

        Example:
            >>> manager.truncate_text_by_tokens("Hello world this is a test", 3)
            'Hello world...'
        """
        if not text or self.count_tokens_approx(text) <= max_tokens:
            return text

        max_chars = int(max_tokens * CHARS_PER_TOKEN_TRUNCATION)
        if len(text) <= max_chars:
            return text

        # Initial hard cut
        truncated_text = text[:max_chars]

        # Attempt to cut at the last space to avoid splitting words
        last_space_index = truncated_text.rfind(" ")
        if last_space_index != -1:
            truncated_text = truncated_text[:last_space_index]

        logger.info(f"Text truncated from {len(text)} to {len(truncated_text)} chars")
        return truncated_text + "\n... [TRUNCATED] ..."

    def reduce_context_to_fit_limit(
        self,
        fixed_prompt: str,
        history: List[Dict[str, Any]],
        selected_text: str,
        model_limit: int,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Optimize the payload to fit within the model's context window.

        Strategy:
        1. Calculate total estimated load.
        2. If over limit, compress History (keep System + last exchange).
        3. If still over limit, truncate User Selection.

        Args:
            fixed_prompt: Immutable system/user instructions.
            history: Conversation history.
            selected_text: Context from clipboard/selection.
            model_limit: The target token limit.

        Returns:
            Tuple of (optimized_history, optimized_selected_text).

        Raises:
            ContextOverflowError: If context cannot be reduced sufficiently.
        """
        target_limit = model_limit - RESPONSE_BUFFER_TOKENS

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
        logger.debug(
            f"Initial context: {initial_tokens} tokens (limit: {target_limit})"
        )

        if initial_tokens <= target_limit:
            return history, selected_text

        # Strategy 1: History Compression (Keep System + last exchange)
        if history:
            system_messages = [m for m in history if m.get("role") == "system"]
            conversation_pairs: List[List[Dict[str, Any]]] = []
            buffer: List[Dict[str, Any]] = []

            # Iterate backwards to find the most recent conversation pairs
            for message in reversed(history):
                if message.get("role") in ["user", "assistant"]:
                    buffer.append(message)
                    if len(buffer) == 2:
                        conversation_pairs.append(list(reversed(buffer)))
                        buffer = []

            # Keep only the last complete pair (user/assistant)
            keep_pairs = conversation_pairs[:2]
            compressed_history = system_messages + [
                msg for pair in reversed(keep_pairs) for msg in pair
            ]

            # Truncate content within the kept history messages
            for message in compressed_history:
                if isinstance(message.get("content"), str):
                    message["content"] = self.truncate_text_by_tokens(
                        message["content"], MIN_HISTORY_TOKENS
                    )

            history = compressed_history
            current_tokens = calculate_total_tokens()
            logger.info(
                f"History compressed: {initial_tokens} → {current_tokens} tokens"
            )
        else:
            current_tokens = initial_tokens

        # Strategy 2: Selection Reduction
        if current_tokens > target_limit and selected_text:
            keep_count = int(
                self.count_tokens_approx(selected_text) * SELECTED_TEXT_PRIORITY_RATIO
            )
            selected_text = self.truncate_text_by_tokens(selected_text, keep_count)
            current_tokens = calculate_total_tokens()
            logger.info(f"Selection reduced: current tokens = {current_tokens}")

        # Strategy 3: Final Safety Cut
        if current_tokens > target_limit and selected_text:
            excess_tokens = current_tokens - target_limit
            cut_amount = max(int(excess_tokens * CHARS_PER_TOKEN_TRUNCATION), 0)
            if cut_amount < len(selected_text):
                selected_text = selected_text[:-cut_amount]
            else:
                selected_text = ""
            logger.warning(
                f"Emergency cut applied: removed {cut_amount} chars from selection"
            )

        final_tokens = calculate_total_tokens()
        logger.info(f"Context optimized: {initial_tokens} → {final_tokens} tokens")

        if final_tokens > target_limit:
            raise ContextOverflowError(
                f"Context still exceeds limit after optimization: {final_tokens} > {target_limit}"
            )

        return history, selected_text


# ============================================================================
# GENERATION CONTROLLER
# ============================================================================


class GenerationController:
    """
    Facade Controller for all generation workflows (Text, Web, Vision).

    Responsibilities:
    - State validation (Hotkeys, UI Locks).
    - Audio Lifecycle (Recording, VAD hooks).
    - API Client Warmup (Latency reduction).
    - UI Feedback (Streaming, Loading states).

    Thread Safety:
        Some methods spawn background threads. Ensure proper synchronization
        when accessing shared state (app_state).
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
        """
        Initialize the GenerationController with dependency injection.

        Args:
            app_state: Global application state.
            window: UI window handler.
            audio_manager: Audio capture manager.
            sound_manager: Sound effects manager.
            transcription_manager: Speech-to-text manager.
            stats_manager: Usage statistics tracker.
            system_health_manager: System health monitor.
            hotkey_manager: Keyboard shortcut manager.
            config_manager: Configuration manager.
            credential_manager: API credentials manager.
        """
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

    # --- Validation & State Management ---

    def validate_preconditions(self) -> Tuple[bool, Optional[str]]:
        """
        Ensure the system is in a valid state to start a generation cycle.

        Checks for hotkey stability and concurrent operations.

        Returns:
            Tuple of (is_valid, error_message). If not valid, error_message
            may be None (silent failure) or a string (user-facing error).

        Example:
            >>> valid, error = controller.validate_preconditions()
            >>> if not valid:
            ...     print(error or "System not ready")
        """
        start_time = time.time()

        if (
            self.system_health_manager
            and not self.system_health_manager._validate_hotkey_state()
        ):
            logger.warning("Unstable hotkeys detected. Forcing re-registration.")
            try:
                self.hotkey_manager.register_all()
            except Exception as e:
                logger.error(f"Failed to re-register hotkeys: {e}")
                return False, "Hotkey registration failed."
            return False, None

        if self.app_state.ui.settings_open:
            logger.debug("Generation blocked: Settings window is open")
            return False, None

        if self.app_state.is_busy:
            logger.debug("Generation skipped: Application busy lock active")
            return False, None

        logger.debug(f"Preconditions validated in {time.time() - start_time:.3f}s")
        return True, None

    def warmup(self) -> None:
        """
        Asynchronously initialize LLM clients (Cerebras/Groq).

        Eliminates first-request latency spikes (Cold Start mitigation).
        This is a fire-and-forget operation that runs in a background thread.

        Note:
            Errors during warmup are logged but do not fail the operation.
        """

        def _warmup_worker() -> None:
            try:
                cerebras_key = self.credential_manager.get_api_key("cerebras")
                if cerebras_key and self.app_state.cerebras_client is None:
                    self.app_state.cerebras_client = Cerebras(api_key=cerebras_key)
                    logger.info("Cerebras client warmed up successfully")

                groq_key = self.credential_manager.get_api_key("groq_ai")
                if groq_key and self.app_state.groq_client is None:
                    self.app_state.groq_client = Groq(api_key=groq_key)
                    logger.info("Groq client warmed up successfully")

            except Exception as error:
                logger.warning(f"LLM client warmup failed: {error}", exc_info=True)

        threading.Thread(
            target=_warmup_worker, daemon=True, name="ClientWarmup"
        ).start()

    def force_reset_state_after_timeout(self) -> None:
        """
        Watchdog mechanism to release application locks if an operation hangs.

        Prevents the UI from becoming permanently unresponsive.
        This should only be called when an operation exceeds expected timeout.
        """
        if self.app_state.is_busy:
            logger.warning("Operation watchdog triggered - forcing state reset")
            try:
                if self.window:
                    error_message = "The operation took too long. Please try again."
                    self._safe_js_call("displayError", error_message)
                    self._safe_js_call("setSettingsButtonState", False)
            except Exception as error:
                logger.error(f"Failed to update UI during timeout reset: {error}")

            self.app_state.is_busy = False
            self.app_state.audio.is_recording = False
            self.app_state.ai_recording = False

    def _safe_js_call(self, function_name: str, *args: Any) -> None:
        """
        Execute JavaScript function with sanitized arguments.

        Prevents XSS injection by JSON-encoding all parameters.

        Args:
            function_name: JavaScript function name (must be alphanumeric).
            *args: Arguments to pass (will be JSON-encoded).

        Raises:
            ValueError: If function_name contains invalid characters.
        """
        if not function_name.replace("_", "").isalnum():
            raise ValueError(f"Invalid JS function name: {function_name}")

        params = ",".join(sanitize_for_js(arg) for arg in args)
        js_code = f"{function_name}({params})"

        try:
            self.window.evaluate_js(js_code)
        except Exception as e:
            logger.error(f"JS call failed: {function_name}, error: {e}")

    # --- Audio Workflow ---

    def start_recording(self, css_class: str = "ai-recording") -> str:
        """
        Initiate the audio capture workflow with immediate UI feedback.

        Args:
            css_class: CSS class for UI state visualization.

        Returns:
            Path to the audio file that will be recorded.

        Raises:
            OSError: If audio initialization fails.
        """
        logger.info(f"Starting recording with UI class: {css_class}")

        def update_ui_in_background() -> None:
            """Background thread for non-blocking UI updates."""
            try:
                if self.app_state.audio.is_recording:
                    self.transcription_manager.stop_recording_and_transcribe()
                    time.sleep(UI_UPDATE_SLEEP_SECONDS)

                ai_modes = [
                    "ai-recording",
                    "screen-vision-recording",
                    "web-search-recording",
                ]

                if self.window:
                    if css_class in ai_modes:
                        self._safe_js_call("setAIButtonState", "recording")
                        # Dispatch custom event for AI mode
                        self.window.evaluate_js(
                            "window.dispatchEvent(new CustomEvent('pywebview', "
                            "{ detail: 'start_asking' }))"
                        )
                    else:
                        self.window.evaluate_js(
                            "window.dispatchEvent(new CustomEvent('pywebview', "
                            "{ detail: 'start_recording' }))"
                        )
                    self._safe_js_call("startVisualizationOnly")

            except Exception as error:
                logger.error(f"UI update failed during recording start: {error}")

        threading.Thread(
            target=update_ui_in_background, daemon=True, name="RecordingUIUpdate"
        ).start()

        # Play audio feedback if enabled
        if self.app_state.audio.sound_enabled:
            try:
                self.sound_manager.play("beep_on")
            except Exception as e:
                logger.warning(f"Failed to play beep sound: {e}")

        # Store mute state for restoration later
        self.app_state.audio.was_muted_during_recording = (
            self.app_state.audio.mute_sound
        )

        if self.app_state.audio.mute_sound:
            threading.Thread(
                target=self.audio_manager.mute_system_volume,
                daemon=True,
                name="SystemMute",
            ).start()

        self.app_state.ai_recording = True
        self.app_state.audio.recording_start_time = time.time()

        # Initialize audio subsystem
        try:
            self.audio_manager.initialize()
        except Exception as e:
            logger.error(f"Audio manager initialization failed: {e}")
            raise OSError(f"Failed to initialize audio: {e}") from e

        # Setup recording file path
        temp_dir = tempfile.gettempdir()
        audio_file_path = os.path.join(temp_dir, AppConfig.AUDIO_OUTPUT_FILENAME)

        # Validate path for security
        try:
            validate_temp_file_path(audio_file_path, AppConfig.AUDIO_OUTPUT_FILENAME)
        except ValueError as e:
            logger.error(f"Audio file path validation failed: {e}")
            raise

        self.app_state.audio.is_recording = True

        def vad_callback() -> None:
            """Voice Activity Detection callback for silence detection."""
            logger.info("VAD silence detected - triggering stop")
            self.app_state.audio.is_recording = False

        # Start audio recording worker thread
        threading.Thread(
            target=self.audio_manager._record_audio_worker,
            args=(audio_file_path,),
            daemon=True,
            name="AudioRecorder",
        ).start()

        self.audio_manager._silence_callback = vad_callback
        return audio_file_path

    def stop_recording(self, css_class: str = "ai-recording") -> Tuple[str, float]:
        """
        Finalize the recording session, restore system volume, and update UI.

        Args:
            css_class: CSS class for UI feedback.

        Returns:
            Tuple of (audio_file_path, duration_seconds).
        """
        logger.info(f"Stopping recording with UI class: {css_class}")

        # Play stop sound feedback
        if self.app_state.audio.sound_enabled:
            try:
                self.sound_manager.play("beep_off")
            except Exception as e:
                logger.warning(f"Failed to play stop beep: {e}")

        # Restore system volume if it was muted during recording
        if self.app_state.audio.was_muted_during_recording:
            try:
                self.audio_manager.unmute_system_volume()
            except Exception as e:
                logger.error(f"Failed to unmute system volume: {e}")
            self.app_state.audio.was_muted_during_recording = False

        # Update recording flags
        self.app_state.ai_recording = False
        self.app_state.audio.is_recording = False

        # Calculate recording duration
        duration = 0.0
        if self.app_state.audio.recording_start_time > 0:
            duration = time.time() - self.app_state.audio.recording_start_time
            logger.debug(f"Recording duration: {duration:.2f}s")

        # Update UI state
        try:
            self._safe_js_call("stopVisualizationOnly")

            ai_modes = [
                "ai-recording",
                "screen-vision-recording",
                "web-search-recording",
            ]

            if css_class not in ai_modes:
                self.window.evaluate_js(
                    "window.dispatchEvent(new CustomEvent('pywebview', "
                    "{ detail: 'stop_recording' }))"
                )
        except Exception as e:
            logger.error(f"UI update failed during recording stop: {e}")

        # Wait for compositor refresh on Windows
        time.sleep(COMPOSITOR_REFRESH_DELAY_SECONDS)

        # Get audio file path
        audio_file_path = os.path.join(
            tempfile.gettempdir(), AppConfig.AUDIO_OUTPUT_FILENAME
        )

        return audio_file_path, duration

    def cleanup_recording_ui(self, css_class: str = "ai-recording") -> None:
        """
        Emergency cleanup of UI elements if recording is aborted or fails.

        Args:
            css_class: CSS class identifier for the recording type.
        """
        logger.info(f"Cleaning up recording UI for class: {css_class}")

        self.app_state.ai_recording = False
        self.app_state.is_busy = False

        try:
            self._safe_js_call("setSettingsButtonState", False)
            self._safe_js_call("stopVisualizationOnly")
            self.window.evaluate_js(
                "window.dispatchEvent(new CustomEvent('pywebview', "
                "{ detail: 'stop_recording' }))"
            )
            self._safe_js_call("setAIButtonState", "idle")
        except Exception as e:
            logger.error(f"UI cleanup failed: {e}")

    # --- UI Helpers (Loader & Reset) ---

    def show_loading_ui(self) -> None:
        """
        Inject and render the indeterminate loading state (Thinking animation).

        Creates a loading skeleton UI with animated gradient lines.
        """
        try:
            # Hide visualizer and prepare container
            self.window.evaluate_js(
                """
                window.originalWindowHeight = window.innerHeight;
                const vizContainer = document.getElementById('visualizer-container');
                if (vizContainer) { vizContainer.style.display = 'none'; }
                """
            )

            # Create or reuse response container
            self.window.evaluate_js(
                """
                let responseContainer = document.getElementById('ai-response-container');
                if (!responseContainer) {
                    responseContainer = document.createElement('div');
                    responseContainer.id = 'ai-response-container';
                    responseContainer.className = 'ai-response-container';
                    document.querySelector('.container').insertBefore(
                        responseContainer, 
                        document.querySelector('.help-container')
                    );
                }
                responseContainer.style.display = 'flex';
                responseContainer.style.justifyContent = 'flex-start';
                responseContainer.innerHTML = '';
                """
            )

            # Inject loading animation styles
            self.window.evaluate_js(
                """
                const mainStyle = document.createElement('style');
                mainStyle.textContent = `
                    .loading-container { 
                        display: flex; 
                        flex-direction: column; 
                        width: 100%; 
                        height: 150%; 
                        position: absolute; 
                        top: 0; 
                        left: 0; 
                        padding: 0; 
                        margin: 0; 
                    }
                    .chatbox { 
                        width: 400px; 
                        padding: 8px; 
                        height: 140px; 
                        background-color: #222222; 
                        border-radius: 8px; 
                        box-shadow: 0 2px 4px rgba(0,0,0,0.3); 
                        color: white; 
                        max-width: 380px; 
                    }
                    .loading-line { 
                        height: 8px; 
                        background: linear-gradient(
                            100deg, 
                            #2e2e2e 30%, 
                            #444 50%, 
                            #2e2e2e 70%
                        ); 
                        background-size: 200% 100%; 
                        animation: loading 1.5s infinite; 
                        border-radius: 4px; 
                        margin: 6px 0; 
                    }
                    .loading-line.short { width: 40%; } 
                    .loading-line.medium { width: 60%; } 
                    .loading-line.long { width: 80%; }
                    @keyframes loading { 
                        0% { background-position: 200% 0; } 
                        100% { background-position: -200% 0; } 
                    }
                `;
                document.head.appendChild(mainStyle);
                """
            )

            # Insert loading skeleton HTML
            self.window.evaluate_js(
                """
                const container = document.getElementById('ai-response-container');
                container.innerHTML = `
                    <div class="loading-container">
                        <div class="chatbox">
                            <div class="loading-line long"></div>
                            <div class="loading-line medium"></div>
                            <div class="loading-line short"></div>
                        </div>
                    </div>
                `;
                """
            )

            # Resize window for loading state
            if self.window:
                self.window.resize(415, 114)

        except Exception as error:
            logger.error(f"Failed to display loading UI: {error}", exc_info=True)

    def reset_ui_for_new_generation(self) -> None:
        """
        Clear previous AI responses and reset the UI layout for a fresh interaction.
        """
        if self.app_state.conversation.is_ai_response_visible:
            try:
                self._safe_js_call("resetUIForNewGeneration")
                time.sleep(UI_RESET_SLEEP_SECONDS)
            except Exception as e:
                logger.error(f"UI reset failed: {e}")

    # --- AI API & Streaming ---

    def _get_model_provider(self, model_id: str) -> str:
        """
        Resolve the provider (Groq/Cerebras) for a given model ID based on config.

        Args:
            model_id: Model identifier string.

        Returns:
            Provider name ("groq" or "cerebras").
        """
        if not self.app_state.cached_remote_config:
            logger.warning("No cached remote config, loading now")
            self.config_manager.load_and_parse_remote_config()

        for item in self.app_state.cached_remote_config:
            if item.get("name") == model_id:
                provider = item.get("provider", "groq")
                logger.debug(f"Model {model_id} provider: {provider}")
                return provider

        logger.warning(f"Provider not found for model {model_id}, defaulting to groq")
        return "groq"

    def execute_ai_api_call(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        show_streaming: bool = True,
        processing_mode: str = "text",
    ) -> Optional[str]:
        """
        Execute the AI API call with Server-Sent Events (Streaming).

        Updates the Frontend in real-time as tokens are received.

        Args:
            messages: Conversation history with role/content structure.
            model: Model identifier.
            show_streaming: If True, streams tokens to UI in real-time.
            processing_mode: One of 'text', 'vision', or 'web'.

        Returns:
            The complete response text, or None if error occurred.

        Raises:
            ModelUnavailableError: If model is not accessible.
            Exception: For API errors (handled internally).
        """
        start_time = time.time()

        provider = self._get_model_provider(model)
        logger.info(
            f"Starting API call - Provider: {provider.upper()}, Mode: {processing_mode}, Model: {model}"
        )

        try:
            stream = None

            if not self.app_state.conversation.is_ai_response_visible:
                self.app_state.conversation.conversation_history.clear()

            # Route to appropriate provider
            if provider == "cerebras":
                stream = self._call_cerebras(messages, model)
            else:
                stream = self._call_groq(messages, model)

            # Setup streaming UI if enabled
            if show_streaming and self.window:
                self._safe_js_call("setupStreamingUI", processing_mode)

            # Process the streaming response
            result_text = self._process_stream(stream, show_streaming)

            # Finalize UI
            if show_streaming and self.window:
                self._safe_js_call("finalizeStreamedContent")

            try:
                if self.window:
                    self._safe_js_call("setAIButtonState", "success")
            except Exception as e:
                logger.warning(f"Failed to set success state: {e}")

            elapsed = time.time() - start_time
            logger.info(f"API call completed in {elapsed:.3f}s")

            self.app_state.conversation.is_ai_response_visible = True

            return result_text

        except Exception as error:
            logger.critical(f"API call failed ({provider}): {error}", exc_info=True)
            self._handle_api_error(error)
            return None

    def _call_groq(self, messages: List[Dict[str, Any]], model: str) -> Any:
        """
        Groq-specific API implementation with client caching.

        Args:
            messages: Conversation messages.
            model: Model identifier.

        Returns:
            Groq streaming response object.

        Raises:
            ValueError: If API key is missing.
        """
        if self.app_state.groq_client is None:
            api_key = self.credential_manager.get_api_key("groq_ai")
            if not api_key:
                raise ValueError("Missing Groq API Key")
            self.app_state.groq_client = Groq(api_key=api_key)
            logger.info("Groq client initialized")

        client = self.app_state.groq_client

        # Base parameters
        params: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        # Advanced model configuration
        if model in self.app_state.models.advanced_model_list:
            params["extra_headers"] = {"Groq-Model-Version": "latest"}
            params["model"] = "groq/compound"
            params["max_completion_tokens"] = MAX_AGENT_COMPLETION_TOKENS
            logger.debug(f"Using advanced model config for {model}")

        # Tool-enabled models
        elif model in self.app_state.models.tool_model_list:
            params["tools"] = [{"type": "browser_search"}]
            logger.debug(f"Enabled browser search tool for {model}")

        return client.chat.completions.create(**params)

    def _call_cerebras(self, messages: List[Dict[str, Any]], model: str) -> Any:
        """
        Cerebras-specific API implementation with client caching.

        Args:
            messages: Conversation messages.
            model: Model identifier.

        Returns:
            Cerebras streaming response object.

        Raises:
            ValueError: If API key is missing.
        """
        if self.app_state.cerebras_client is None:
            api_key = self.credential_manager.get_api_key("cerebras")
            if not api_key:
                raise ValueError("Missing Cerebras API Key")
            self.app_state.cerebras_client = Cerebras(api_key=api_key)
            logger.info("Cerebras client initialized")

        client = self.app_state.cerebras_client

        params: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_completion_tokens": 8192,
            "temperature": 0.7,
            "top_p": 0.95,
        }

        return client.chat.completions.create(**params)

    def _process_stream(self, stream: Any, show_streaming: bool) -> str:
        """
        Consume the API stream, handle Chain-of-Thought tags, and update UI buffer.

        Filters out <think>...</think> blocks from the displayed output while
        preserving the complete response text.

        Args:
            stream: Streaming response from API.
            show_streaming: Whether to update UI in real-time.

        Returns:
            Complete response text (excluding thinking blocks).
        """
        full_result = ""
        buffer = ""
        is_thinking: Optional[bool] = None

        for chunk in stream:
            content = chunk.choices[0].delta.content or ""

            # Standard streaming path (outside thinking blocks)
            if is_thinking is False:
                if show_streaming:
                    self._safe_js_call("appendaiStreamChunk", content)
                full_result += content
                continue

            buffer += content

            # Detect start of thinking block
            if is_thinking is None:
                stripped_buffer = buffer.lstrip()
                if stripped_buffer.startswith(COT_START_TAG):
                    is_thinking = True
                    logger.debug("Chain-of-Thought block detected")
                # Buffer has content but doesn't start with tag
                elif len(stripped_buffer) >= len(COT_START_TAG) or (
                    stripped_buffer and not COT_START_TAG.startswith(stripped_buffer)
                ):
                    is_thinking = False
                    if show_streaming:
                        self._safe_js_call("appendaiStreamChunk", buffer)
                    full_result += buffer
                    buffer = ""

            # Detect end of thinking block
            if is_thinking is True and COT_END_TAG in buffer:
                _, _, remainder = buffer.partition(COT_END_TAG)
                is_thinking = False
                buffer = ""
                logger.debug("Chain-of-Thought block ended")

                if remainder:
                    if show_streaming:
                        self._safe_js_call("appendaiStreamChunk", remainder)
                    full_result += remainder

        # Append final newline for formatting
        if show_streaming:
            self._safe_js_call("appendaiStreamChunk", "\n")

        logger.debug(f"Stream processing complete - {len(full_result)} chars")
        return full_result

    def _handle_api_error(self, error: Exception) -> None:
        """
        Handle API errors with user-friendly messages and logging.

        Args:
            error: Exception raised during API call.
        """
        logger.error(f"API error handler invoked: {type(error).__name__}: {error}")

        try:
            self._safe_js_call("setAIButtonState", "idle")
        except Exception as e:
            logger.error(f"Failed to reset UI state after API error: {e}")

        self.app_state.conversation.is_ai_response_visible = False

        # Map HTTP status codes to user messages
        msg = "An API error occurred. Please try again."
        status_code = getattr(error, "status_code", None)

        if status_code == 413:
            msg = "Request too large. Try reducing context or selection."
        elif status_code == 429:
            msg = "Rate limit reached. Please wait a moment."
        elif status_code == 401:
            msg = "Invalid API Key. Check your credentials."
        elif status_code == 503:
            msg = "Service temporarily unavailable. Try again later."

        try:
            self._safe_js_call("displayError", msg)
        except Exception as e:
            logger.error(f"Failed to display error message: {e}")

    # --- File Utilities ---

    def safe_remove_file(self, path: Optional[str]) -> None:
        """
        Remove a file if it exists, ignoring OS errors (Best Effort).

        Args:
            path: File path to remove (can be None).
        """
        if not path:
            return

        try:
            file_path = Path(path)
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Removed temporary file: {path}")
        except Exception as e:
            logger.warning(f"Failed to remove file {path}: {e}")

    def cleanup_temp_files(
        self, audio_path: Optional[str], screenshot_path: Optional[str]
    ) -> None:
        """
        Clean up temporary files generated during the process.

        Args:
            audio_path: Path to temporary audio file.
            screenshot_path: Path to temporary screenshot file.
        """
        self.safe_remove_file(audio_path)
        self.safe_remove_file(screenshot_path)
        logger.debug("Temporary files cleanup completed")


# ============================================================================
# VISION MANAGER
# ============================================================================


class VisionManager:
    """
    Manages screen capture and payload preparation for Multimodal LLMs.

    Security Note:
        - Captures are only performed if a Multimodal model is selected.
        - No third-party OCR is involved.
        - Legacy OCR fallback has been completely removed.
    """

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
        """
        Initialize the VisionManager.

        Args:
            app_state: Global application state.
            config_manager: Configuration manager.
            screen_manager: Screen capture manager.
            transcription_service: Audio transcription service.
            stats_manager: Usage statistics tracker.
            history_manager: Conversation history manager.
            credential_manager: API credentials manager.
            generation_controller: Generation workflow controller.
        """
        self.app_state = app_state
        self.config_manager = config_manager
        self.screen_manager = screen_manager
        self.transcription_service = transcription_service
        self.stats_manager = stats_manager
        self.history_manager = history_manager
        self.credential_manager = credential_manager
        self.generation_controller = generation_controller

    def select_best_vision_model(self) -> str:
        """
        Auto-select the optimal vision-capable model based on availability.

        Selection Logic (Priority Order):
        1. If current model is already in the vision model list → use it
        2. If current model is multimodal (supports vision) → use it
        3. Auto-select first available dedicated vision model from the list
        4. Search for any multimodal model in available models
        5. Fallback to any available model (will likely fail, but with clear error)

        Returns:
            Model identifier string.

        Raises:
            ModelUnavailableError: If no models are available at all.

        Example:
            >>> vision_mgr = VisionManager(...)
            >>> model = vision_mgr.select_best_vision_model()
            >>> # Returns "llama-3.2-90b-vision-preview" if available and suitable
        """
        available_models = self.config_manager.fetch_ai_models()
        current_model = self.app_state.models.model

        # Priority 1: Current model is already a dedicated vision model
        if (
            current_model in available_models
            and current_model in self.app_state.models.screen_vision_model_list
        ):
            logger.info(
                f"Using current vision model: {current_model} "
                f"(already in vision model list)"
            )
            return current_model

        # Priority 2: Current model is multimodal (even if not in preferred list)
        if (
            current_model in available_models
            and self.config_manager.check_if_model_is_multimodal(current_model)
        ):
            logger.info(
                f"Using current multimodal model for vision: {current_model} "
                f"(supports vision capabilities)"
            )
            return current_model

        # Priority 3: Auto-select first available dedicated vision model
        for model_id in self.app_state.models.screen_vision_model_list:
            if model_id in available_models:
                logger.info(
                    f"Auto-selecting vision model: {model_id} "
                    f"(current model '{current_model}' is not vision-capable)"
                )
                return model_id

        # Priority 4: Find any multimodal model in available models
        for model_id in available_models:
            if self.config_manager.check_if_model_is_multimodal(model_id):
                logger.warning(
                    f"No dedicated vision model found. "
                    f"Using multimodal model: {model_id} "
                    f"(not in preferred vision model list)"
                )
                return model_id

        # Priority 5: Last resort - use any available model (will likely fail)
        if available_models:
            fallback_model = available_models[0]
            logger.warning(
                f"No vision-capable model available. "
                f"Falling back to: {fallback_model} "
                f"(this will likely fail as model doesn't support vision)"
            )
            return fallback_model

        # No models available at all
        raise ModelUnavailableError(
            "No AI models available. Please check your API keys in Settings."
        )

    def process_vision_capture(self, model: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Capture the screen and encode it to Base64 for the API.

        Security Note:
            Captures are only performed if the model supports multimodal input.
            No third-party OCR is involved - the LLM processes the image directly.

        Args:
            model: Model identifier to validate multimodal capability.

        Returns:
            Tuple of (file_path, base64_image).
            - file_path: Path to temporary screenshot file (for cleanup)
            - base64_image: Data URI string with base64-encoded image, or None if
                        model is not multimodal or capture failed.

        Raises:
            VisionCapabilityError: If vision requested on non-multimodal model.

        Example:
            >>> vision_mgr = VisionManager(...)
            >>> path, base64 = vision_mgr.process_vision_capture("llama-3.2-90b-vision")
            >>> if base64:
            ...     # Image successfully captured and encoded
            ...     send_to_api(base64)
        """
        # Capture the screen first
        file_path = self.screen_manager.capture()
        base64_image = None

        if not file_path:
            logger.error("Screen capture failed - no file path returned")
            return None, None

        # Verify file actually exists
        if not os.path.exists(file_path):
            logger.error(f"Screen capture file not found: {file_path}")
            return None, None

        # Check if the model supports multimodal input (vision)
        if self.config_manager.check_if_model_is_multimodal(model):
            try:
                base64_image = self.screen_manager.convert_image_to_base64(file_path)
                if base64_image:
                    logger.info(
                        f"Screen captured and encoded successfully: {file_path} "
                        f"(Base64 length: {len(base64_image)} chars)"
                    )
                else:
                    logger.error(f"Failed to encode image to base64: {file_path}")
                    # Clean up the file since we can't use it
                    self.generation_controller.safe_remove_file(file_path)
                    return None, None
            except Exception as e:
                logger.error(
                    f"Error converting image to base64: {e}",
                    exc_info=True,
                    extra={"file_path": file_path},
                )
                # Clean up the file since encoding failed
                self.generation_controller.safe_remove_file(file_path)
                return None, None
        else:
            logger.warning(
                f"Vision attempted with non-multimodal model: {model}. "
                f"Capture aborted to prevent data leak. "
                f"Available multimodal models: {self.app_state.models.screen_vision_model_list}"
            )
            # Clean up captured file since we're not using it
            self.generation_controller.safe_remove_file(file_path)
            return None, None

        return file_path, base64_image

    def build_vision_system_prompt(self) -> str:
        """
        Construct the system prompt specialized for visual analysis.

        The prompt is designed to:
        - Set clear expectations for vision-based tasks
        - Enforce output quality standards
        - Match user's language automatically
        - Use markdown formatting for readability

        Returns:
            System prompt string with current date and output rules.

        Example:
            >>> vision_mgr = VisionManager(...)
            >>> prompt = vision_mgr.build_vision_system_prompt()
            >>> # Returns prompt with current date and formatting rules
        """
        date_str = datetime.now().strftime("%Y-%m-%d")

        prompt = f"""# SYSTEM_ROLE
    Visual Analysis Engine with Multimodal Understanding. Date: {date_str}.

    # CAPABILITIES
    - Image Analysis: Detect objects, read text (OCR), identify patterns, analyze layouts
    - Visual Reasoning: Understand context, relationships, and implicit information
    - Code Recognition: Read and explain code from screenshots
    - Document Processing: Extract information from forms, tables, diagrams

    # STRICT_OUTPUT_RULES
    1. NO filler phrases ("I see", "The image shows", "As an AI", "Based on the image")
    2. Direct answer ONLY - get straight to the point
    3. Language: DETECT and MATCH the user's audio language perfectly
    4. Format: Use Markdown for structure (headings, lists, code blocks)
    5. Accuracy: If uncertain about visual details, acknowledge uncertainty
    6. Privacy: Never identify real people by name from images

    # OUTPUT_FORMAT
    - For text extraction: Provide clean, formatted text
    - For analysis: Lead with key findings, then supporting details
    - For code: Use proper syntax highlighting in code blocks
    - For tables: Preserve structure using markdown tables
    """
        return prompt

    def generate_screen_vision_text(self) -> None:
        """
        Execute the Vision Workflow: Record → Transcribe → Capture Screen → Analyze.

        This is the main entry point for vision-based generation.

        Workflow Steps:
        1. Validate vision model availability
        2. Check preconditions (not busy, settings closed, etc.)
        3. Start/stop recording based on current state
        4. Transcribe audio input
        5. Capture screen and encode to base64
        6. Build vision-specific prompt with image context
        7. Execute API call with streaming
        8. Update history and statistics

        Raises:
            ModelUnavailableError: If no vision model is available.
            TranscriptionError: If audio transcription fails.
            VisionCapabilityError: If selected model cannot process images.
        """
        start_time = time.time()
        logger.info("Vision workflow started")

        # Validate that we have at least ONE available model
        available_models = self.config_manager.fetch_ai_models()

        if not available_models:
            message = "No AI models available. Please check your API keys in Settings."
            logger.error(message)
            if self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", message)
            return

        # Check vision capability across all available models
        current_model = self.app_state.models.model
        has_vision_model = any(
            m in available_models
            for m in self.app_state.models.screen_vision_model_list
        )
        current_is_vision = (
            current_model in self.app_state.models.screen_vision_model_list
        )
        current_is_multimodal = (
            current_model in available_models
            and self.config_manager.check_if_model_is_multimodal(current_model)
        )
        has_any_multimodal = any(
            self.config_manager.check_if_model_is_multimodal(m)
            for m in available_models
        )

        # Log diagnostic information
        logger.info(
            f"Vision capability check - "
            f"Current model: {current_model}, "
            f"Is vision model: {current_is_vision}, "
            f"Is multimodal: {current_is_multimodal}, "
            f"Available vision models: {has_vision_model}, "
            f"Any multimodal available: {has_any_multimodal}"
        )

        # We need at least ONE model with vision capability
        if (
            not has_vision_model
            and not current_is_multimodal
            and not has_any_multimodal
        ):
            message = (
                "No vision-capable model available. "
                "Please select a multimodal model (e.g., Llama 3.2 Vision) in Settings, "
                "or add a Groq API key to access vision models."
            )
            logger.error(message)
            if self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", message)
            return

        # Validate preconditions (not busy, settings closed, etc.)
        is_valid, error = self.generation_controller.validate_preconditions()
        if not is_valid:
            if error and self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", error)
            return

        # Setup watchdog timer to prevent hanging
        timer = threading.Timer(
            OPERATION_WATCHDOG_TIMEOUT_SECONDS,
            self.generation_controller.force_reset_state_after_timeout,
        )
        timer.start()

        audio_file_path: Optional[str] = None
        screen_path: Optional[str] = None
        self.app_state.is_busy = True
        self.generation_controller.reset_ui_for_new_generation()

        try:
            # Lock settings button to prevent conflicts
            try:
                self.generation_controller._safe_js_call("setSettingsButtonState", True)
            except Exception as e:
                logger.warning(f"Failed to lock settings button: {e}")

            # Handle recording state (toggle behavior)
            if not self.app_state.ai_recording:
                try:
                    audio_file_path = self.generation_controller.start_recording(
                        css_class="screen-vision-recording"
                    )
                    return  # Exit here, will be called again when recording stops
                except Exception as e:
                    logger.error(f"Failed to start recording: {e}")
                    self.app_state.is_busy = False
                    return

            # Stop recording and retrieve audio file path
            audio_file_path, duration = self.generation_controller.stop_recording(
                css_class="screen-vision-recording"
            )

            # Validate audio file exists before proceeding
            if not os.path.exists(audio_file_path):
                logger.error(f"Audio file not found: {audio_file_path}")
                self.app_state.is_busy = False
                return

            # Show loading UI (thinking animation)
            self.generation_controller.show_loading_ui()

            # Transcribe audio to text
            logger.debug("Sending audio to transcription service")
            transcript = self.transcription_service.transcribe(
                audio_file_path, self.app_state.models.language, duration
            )

            # Check for transcription errors
            if transcript.lower().startswith("error"):
                raise TranscriptionError(transcript)

            # Update statistics (tracking usage)
            self.stats_manager.update_stats(transcript, duration, is_generation=True)

            # Select best vision model (with auto-selection logic)
            try:
                model = self.select_best_vision_model()
                logger.info(f"Using model for vision analysis: {model}")
            except ModelUnavailableError as error:
                logger.error(f"Model selection failed: {error}")
                if self.generation_controller.window:
                    self.generation_controller._safe_js_call(
                        "displayError",
                        "No suitable model available for vision. Please check Settings.",
                    )
                return

            # Capture screen and encode to base64
            screen_path, base64_img = self.process_vision_capture(model)

            # Verify that we successfully captured and encoded the image
            if not base64_img:
                raise VisionCapabilityError(
                    f"Selected model '{model}' cannot process images, "
                    f"or screen capture failed"
                )

            # Clear conversation history if starting new conversation
            if not self.app_state.conversation.is_ai_response_visible:
                self.app_state.conversation.conversation_history.clear()

            # Build vision-specific system prompt
            system_prompt = self.build_vision_system_prompt()

            # Construct message array with system prompt and history
            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_prompt}
            ]
            messages.extend(self.app_state.conversation.conversation_history)

            # Construct user message with both text and image
            user_content: List[Dict[str, Any]] = [{"type": "text", "text": transcript}]
            if base64_img:
                user_content.append(
                    {"type": "image_url", "image_url": {"url": base64_img}}
                )

            messages.append({"role": "user", "content": user_content})

            # Execute API call with streaming enabled
            response = self.generation_controller.execute_ai_api_call(
                messages, model, show_streaming=True, processing_mode="vision"
            )

            # Save to history and update UI if successful
            if response:
                # Add entry to history manager
                self.history_manager.add_entry(
                    f"[Vision] {transcript}\n[AI] {response}"
                )

                # Refresh dashboard if settings window is open
                if self.app_state.ui.settings_window:
                    try:
                        self.app_state.ui.settings_window.evaluate_js(
                            "refreshDashboardFull()"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to refresh dashboard: {e}")

                # Update conversation history for context in follow-up questions
                self.app_state.conversation.conversation_history.append(
                    {"role": "user", "content": user_content}
                )
                self.app_state.conversation.conversation_history.append(
                    {"role": "assistant", "content": response}
                )

        except TranscriptionError as error:
            logger.error(f"Transcription failed: {error}")
            if self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", str(error))

        except (ModelUnavailableError, VisionCapabilityError) as error:
            logger.error(f"Vision capability error: {error}")
            if self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", str(error))

        except Exception as error:
            logger.error(f"Vision workflow crashed: {error}", exc_info=True)
            try:
                self.generation_controller._safe_js_call(
                    "displayError", "Unexpected error during vision analysis."
                )
            except Exception as e:
                logger.error(f"Failed to display error: {e}")

            self.generation_controller.cleanup_recording_ui("screen-vision-recording")

        finally:
            # Reset busy state
            self.app_state.is_busy = False

            # Cancel watchdog timer if still running
            if timer.is_alive():
                timer.cancel()

            # Cleanup temporary files (audio and screenshot)
            self.generation_controller.cleanup_temp_files(audio_file_path, screen_path)

            # Unlock settings button
            try:
                self.generation_controller._safe_js_call(
                    "setSettingsButtonState", False
                )
            except Exception as e:
                logger.warning(f"Failed to unlock settings button: {e}")

            # Log performance metrics
            elapsed = time.time() - start_time
            logger.info(f"Vision workflow completed in {elapsed:.3f}s")


# ============================================================================
# WEB SEARCH MANAGER
# ============================================================================


class WebSearchManager:
    """
    Manages web search context, model selection, and prompting.

    Handles the workflow for web-augmented generation with browser search tools.
    """

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
        """
        Initialize the WebSearchManager.

        Args:
            app_state: Global application state.
            config_manager: Configuration manager.
            transcription_service: Audio transcription service.
            stats_manager: Usage statistics tracker.
            history_manager: Conversation history manager.
            clipboard_manager: Clipboard/selection manager.
            generation_controller: Generation workflow controller.
        """
        self.app_state = app_state
        self.config_manager = config_manager
        self.transcription_service = transcription_service
        self.stats_manager = stats_manager
        self.history_manager = history_manager
        self.clipboard_manager = clipboard_manager
        self.generation_controller = generation_controller

    def build_web_search_system_prompt(self, selected_text: str) -> str:
        """
        Create a prompt specialized for web searching agents.

        Args:
            selected_text: User-selected context from clipboard.

        Returns:
            System prompt string with search instructions and context.
        """
        date_str = datetime.now().strftime("%A, %B %d, %Y")

        base_prompt = f"""# SYSTEM_ROLE
Web Intelligence Engine. Date: {date_str}.

# OPERATIONAL_MANDATES
1. Response style: Information-dense, neutral, direct.
2. CITATIONS: Mandatory. Use [Source](url) format at the bottom.
3. NO META-TALK: Never say "I searched for", "Here is what I found".
4. Language: STRICTLY match to user's input language.
5. Format: Markdown.
"""
        context = base_prompt

        if selected_text:
            context += f"\n<user_context_focus>\n{selected_text}\n</user_context_focus>"

        return context

    def select_best_web_model(self) -> str:
        """
        Select a model capable of web search (Tools or Browsing capabilities).

        Logic:
        1. If current model is already a web search model, use it
        2. Otherwise, auto-select the first available web search model
        3. Fall back to current model if no dedicated web model available

        Returns:
            Model identifier string.

        Raises:
            ModelUnavailableError: If no web search model is available.
        """
        available_models = self.config_manager.fetch_ai_models()

        # Check if current model is already a web search model
        current_model = self.app_state.models.model
        if (
            current_model in available_models
            and current_model in self.app_state.models.web_search_model_list
        ):
            logger.info(f"Using current web search model: {current_model}")
            return current_model

        # Try to auto-select first available web search model
        for model_id in self.app_state.models.web_search_model_list:
            if model_id in available_models:
                logger.info(
                    f"Auto-selecting web search model: {model_id} "
                    f"(current model '{current_model}' is not web-capable)"
                )
                return model_id

        # Fall back to current model if it's available
        if current_model in available_models:
            logger.warning(
                f"No dedicated web search model found. "
                f"Using current model: {current_model} "
                f"(may have limited web search capabilities)"
            )
            return current_model

        # Last resort: use any available model
        if available_models:
            fallback_model = available_models[0]
            logger.warning(
                f"No web search model available. "
                f"Falling back to first available model: {fallback_model}"
            )
            return fallback_model

        raise ModelUnavailableError("No AI models available")

    def generate_web_search_text(self) -> None:
        """
        Execute Web Search Workflow: Record → Transcribe → Get Selection → Generate.

        This is the main entry point for web search-augmented generation.

        Raises:
            ModelUnavailableError: If no web search model is available.
            TranscriptionError: If audio transcription fails.
        """
        start_time = time.time()
        logger.info("Web Search workflow started")

        # Validate that we have at least ONE available model
        available_models = self.config_manager.fetch_ai_models()

        if not available_models:
            message = "No AI models available. Please check your API keys in Settings."
            logger.error(message)
            if self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", message)
            return

        # Check web search capability
        current_model = self.app_state.models.model
        has_web_model = any(
            m in available_models for m in self.app_state.models.web_search_model_list
        )
        current_is_web = current_model in self.app_state.models.web_search_model_list
        current_is_available = current_model in available_models

        # Log diagnostic information
        logger.info(
            f"Web search capability check - "
            f"Current model: {current_model}, "
            f"Is web model: {current_is_web}, "
            f"Available web models: {has_web_model}, "
            f"Current available: {current_is_available}"
        )

        # We can proceed if we have ANY available model
        # The select_best_web_model() will handle the selection logic
        if not has_web_model and not current_is_available:
            message = (
                "No web search model available with your current API keys. "
                "Please add a Groq or Cerebras API key in Settings to enable web search."
            )
            logger.warning(message)
            if self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", message)
            return

        # Validate preconditions
        is_valid, error = self.generation_controller.validate_preconditions()
        if not is_valid:
            if error and self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", error)
            return

        # Setup watchdog timer
        timer = threading.Timer(
            OPERATION_WATCHDOG_TIMEOUT_SECONDS,
            self.generation_controller.force_reset_state_after_timeout,
        )
        timer.start()

        audio_file_path: Optional[str] = None
        self.app_state.is_busy = True
        self.generation_controller.reset_ui_for_new_generation()

        try:
            # Lock settings button
            try:
                self.generation_controller._safe_js_call("setSettingsButtonState", True)
            except Exception as e:
                logger.warning(f"Failed to lock settings button: {e}")

            # Handle recording state
            if not self.app_state.ai_recording:
                try:
                    audio_file_path = self.generation_controller.start_recording(
                        css_class="web-search-recording"
                    )
                    return
                except Exception as e:
                    logger.error(f"Failed to start recording: {e}")
                    self.app_state.is_busy = False
                    return

            # Stop recording and get audio file
            audio_file_path, duration = self.generation_controller.stop_recording(
                css_class="web-search-recording"
            )

            if not os.path.exists(audio_file_path):
                logger.error(f"Audio file not found: {audio_file_path}")
                self.app_state.is_busy = False
                return

            # Show loading UI
            self.generation_controller.show_loading_ui()

            # Transcribe audio
            logger.debug("Sending audio to transcription service")
            transcript = self.transcription_service.transcribe(
                audio_file_path, self.app_state.models.language, duration
            )

            if transcript.lower().startswith("error"):
                raise TranscriptionError(transcript)

            # Update statistics
            self.stats_manager.update_stats(transcript, duration, is_generation=True)

            # Get selected text from clipboard
            selected_text = self.clipboard_manager.get_selected_text()

            # Select best web model (with auto-selection logic)
            try:
                model = self.select_best_web_model()
                logger.info(f"Using model for web search: {model}")
            except ModelUnavailableError as error:
                logger.error(f"Model selection failed: {error}")
                if self.generation_controller.window:
                    self.generation_controller._safe_js_call(
                        "displayError",
                        "No suitable model available for web search. Please check Settings.",
                    )
                return

            # Build system prompt
            system_prompt = self.build_web_search_system_prompt(selected_text)

            # Clear history if starting new conversation
            if not self.app_state.conversation.is_ai_response_visible:
                self.app_state.conversation.conversation_history.clear()

            # Build messages
            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_prompt}
            ]
            messages.extend(self.app_state.conversation.conversation_history)
            messages.append({"role": "user", "content": transcript})

            # Execute API call
            response = self.generation_controller.execute_ai_api_call(
                messages, model, show_streaming=True, processing_mode="web"
            )

            # Save to history if successful
            if response:
                self.history_manager.add_entry(f"[Web] {transcript}\n[AI] {response}")

                # Refresh dashboard if settings window is open
                if self.app_state.ui.settings_window:
                    try:
                        self.app_state.ui.settings_window.evaluate_js(
                            "refreshDashboardFull()"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to refresh dashboard: {e}")

                # Update conversation history
                self.app_state.conversation.conversation_history.append(
                    {"role": "user", "content": transcript}
                )
                self.app_state.conversation.conversation_history.append(
                    {"role": "assistant", "content": response}
                )

        except TranscriptionError as error:
            logger.error(f"Transcription failed: {error}")
            if self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", str(error))

        except ModelUnavailableError as error:
            logger.error(f"Model unavailable: {error}")
            if self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", str(error))

        except Exception as error:
            logger.error(f"Web search workflow crashed: {error}", exc_info=True)
            if self.generation_controller.window:
                self.generation_controller._safe_js_call(
                    "displayError", "Unexpected error during web search."
                )
            self.generation_controller.cleanup_recording_ui(
                css_class="web-search-recording"
            )

        finally:
            self.app_state.is_busy = False

            if timer.is_alive():
                timer.cancel()

            self.generation_controller.cleanup_temp_files(audio_file_path, None)

            try:
                self.generation_controller._safe_js_call(
                    "setSettingsButtonState", False
                )
            except Exception as e:
                logger.warning(f"Failed to unlock settings button: {e}")

            elapsed = time.time() - start_time
            logger.info(f"Web Search workflow completed in {elapsed:.3f}s")


# ============================================================================
# AI GENERATION MANAGER
# ============================================================================


class AIGenerationManager:
    """
    Manages text generation, Agent execution, and Context Aggregation.

    Refactored: Legacy OCR logic has been completely removed.
    Context is now strictly derived from System Clipboard and Multimodal Vision.

    This is the main orchestrator for all AI generation workflows.
    """

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
        """
        Initialize the AIGenerationManager.

        Args:
            app_state: Global application state.
            config_manager: Configuration manager.
            context_manager: Token/context management.
            transcription_service: Audio transcription service.
            stats_manager: Usage statistics tracker.
            history_manager: Conversation history manager.
            clipboard_manager: Clipboard/selection manager.
            screen_manager: Screen capture manager.
            agent_manager: Agent configuration manager.
            credential_manager: API credentials manager.
            generation_controller: Generation workflow controller.
        """
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
        """
        Gather context (Clipboard, Vision) required by a specific Agent.

        Args:
            agent: Agent configuration dictionary.
            model: Model identifier for capability validation.

        Returns:
            Dictionary with 'selected_text' and 'image_data_url' keys.

        Raises:
            VisionCapabilityError: If vision requested on non-multimodal model.
        """
        context: Dict[str, Any] = {
            "selected_text": self.clipboard_manager.get_selected_text(),
            "image_data_url": None,
        }

        # Secure Vision Capture (only if model supports it)
        if agent.get("screen_vision"):
            path = self.screen_manager.capture()
            if path:
                if self.config_manager.check_if_model_is_multimodal(model):
                    context["image_data_url"] = (
                        self.screen_manager.convert_image_to_base64(path)
                    )
                    logger.info(
                        f"Vision context captured for agent: {agent.get('name')}"
                    )
                else:
                    logger.warning(
                        f"Agent {agent.get('name')} requested vision with "
                        f"non-multimodal model: {model}"
                    )
                    raise VisionCapabilityError(
                        f"Agent requires multimodal model but {model} is not compatible"
                    )

                self.generation_controller.safe_remove_file(path)

        return context

    def capture_context_for_general(self) -> Dict[str, Any]:
        """
        Capture general context: User Selection only.

        Returns:
            Dictionary with 'selected_text', 'image_data_url', and 'screenshot_path' keys.
        """
        context: Dict[str, Any] = {
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
        except Exception as e:
            logger.warning(f"Failed to get window selection: {e}")

        # Fallback to clipboard if window selection is empty
        if not context["selected_text"]:
            context["selected_text"] = self.clipboard_manager.get_selected_text()

        logger.debug(
            f"Captured context - {len(context['selected_text'])} chars selected"
        )
        return context

    def find_triggered_agent(self, text: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Scan transcribed text for Agent trigger phrases.

        Args:
            text: Transcribed user input.

        Returns:
            Tuple of (agent_config, stripped_instruction_text).
            Returns (None, original_text) if no agent triggered.
        """
        agents = [
            a
            for a in self.agent_manager.load_agents()
            if a.get("active") and a.get("trigger")
        ]

        lower_text = text.lower()

        for agent in agents:
            trigger_phrase_raw = agent.get("trigger")
            if not trigger_phrase_raw:
                continue

            trigger_phrase = trigger_phrase_raw.strip().lower()
            if trigger_phrase and lower_text.startswith(trigger_phrase):
                instruction = text[len(trigger_phrase) :].strip()
                logger.info(
                    f"Agent triggered: {agent['name']}, "
                    f"Instruction: {instruction[:50]}..."
                )
                return agent, instruction

        return None, text

    def execute_agent(
        self, agent: Dict[str, Any], instruction: str, full_text: str, duration: float
    ) -> Optional[str]:
        """
        Orchestrate the execution of a custom Agent.

        Handles prompt construction, context injection, and result pasting.

        Args:
            agent: Agent configuration dictionary.
            instruction: Extracted instruction text (trigger phrase removed).
            full_text: Original transcribed text.
            duration: Recording duration (for stats).

        Returns:
            Generated response text, or None if execution failed.

        Raises:
            ModelUnavailableError: If agent's model is not available.
            VisionCapabilityError: If vision requested on incompatible model.
        """
        model = agent.get("model", self.app_state.models.model)

        if model not in self.config_manager.fetch_ai_models():
            raise ModelUnavailableError(f"Agent model '{model}' unavailable")

        logger.info(f"Executing agent: {agent['name']} with model: {model}")

        try:
            context = self.capture_context_for_agent(agent, model)
        except VisionCapabilityError as error:
            if self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", str(error))
            return None

        # Build prompts
        sys_prompt = self.build_agent_system_prompt(agent)
        usr_prompt = self.build_agent_user_prompt(instruction, context)

        # Construct messages
        msgs: List[Dict[str, Any]] = [{"role": "system", "content": sys_prompt}]
        msgs.extend(self.app_state.conversation.conversation_history)

        # Add user message with optional image
        u_content: List[Dict[str, Any]] = [{"type": "text", "text": full_text}]
        if context["image_data_url"]:
            u_content.append(
                {"type": "image_url", "image_url": {"url": context["image_data_url"]}}
            )

        msgs.append({"role": "user", "content": u_content})

        # Determine processing mode and autopaste setting
        mode = "vision" if agent.get("screen_vision") else "text"
        autopaste = agent.get("autopaste", True)

        # Execute API call
        response = self.generation_controller.execute_ai_api_call(
            msgs, model, show_streaming=not autopaste, processing_mode=mode
        )

        if response:
            # Update conversation history
            self.app_state.conversation.conversation_history.append(
                {"role": "user", "content": usr_prompt}
            )
            self.app_state.conversation.conversation_history.append(
                {"role": "assistant", "content": response}
            )

            # Handle autopaste or copy to clipboard
            if autopaste:
                self.handle_autopaste(response)
            else:
                try:
                    pyperclip.copy(response)
                    logger.info("Agent response copied to clipboard")
                except Exception as e:
                    logger.error(f"Failed to copy to clipboard: {e}")

            # Save to history
            self.history_manager.add_entry(
                f"[Agent {agent['name']}] {instruction}\n[AI] {response}"
            )

            # Refresh dashboard if settings window is open
            if self.app_state.ui.settings_window:
                self.app_state.ui.settings_window.evaluate_js("refreshDashboardFull()")

        return response

    def build_agent_system_prompt(self, agent: Dict[str, Any]) -> str:
        """
        Construct the system prompt based on agent configuration.

        Args:
            agent: Agent configuration dictionary.

        Returns:
            System prompt string with agent persona and instructions.
        """
        return f"""# AGENT_CORE
Role: {agent['name']} (Specialized AI).
Output_Mode: Direct Execution.

# FORMATTING
- Markdown enabled.
- Math: Inline `$E=mc^2$`, Block `$$ ... $$`.

# USER_DEFINED_INSTRUCTIONS
{agent['prompt']}

# GLOBAL_CONSTRAINTS
- Language: Match user input.
- No conversational filler.
"""

    def build_agent_user_prompt(self, instruction: str, context: Dict[str, Any]) -> str:
        """
        Construct the user message part for the agent.

        Args:
            instruction: User instruction text.
            context: Context dictionary with selected_text and image data.

        Returns:
            User prompt string with structured context.
        """
        prompt = f"<user_instruction>\n{instruction}\n</user_instruction>\n\n"

        if context["selected_text"]:
            prompt += (
                f"<selected_text>\n{context['selected_text']}\n</selected_text>\n\n"
            )

        return prompt.strip()

    def handle_autopaste(self, result_text: str) -> None:
        """
        Simulate pasting the agent result using centralized method.

        Hides the Ozmoz window and pastes the result into the active application.

        Args:
            result_text: Text to paste.
        """
        logger.info("Autopaste triggered")

        try:
            # Reset UI first
            self.generation_controller.reset_ui_for_new_generation()
            time.sleep(UI_UPDATE_SLEEP_SECONDS)

            # Hide Ozmoz window
            window_handle = win32gui.FindWindow(None, "Ozmoz")
            if window_handle:
                win32gui.ShowWindow(window_handle, win32con.SW_HIDE)
                logger.debug("Ozmoz window hidden for autopaste")

            # Execute paste operation
            self.clipboard_manager.paste_and_clear(result_text)
            logger.info("Autopaste completed successfully")

        except Exception as error:
            logger.error(f"Autopaste failed: {error}", exc_info=True)

    def execute_general_generation(
        self, text_input: str, context: Dict[str, Any], duration: float
    ) -> Optional[str]:
        """
        Execute a standard chat generation with context reduction.

        Args:
            text_input: User's transcribed input.
            context: Context dictionary with selected text and image data.
            duration: Recording duration (for stats).

        Returns:
            Generated response text, or None if execution failed.

        Raises:
            ContextOverflowError: If context cannot be reduced to fit model.
        """
        logger.info("Executing standard generation")

        # Get model context limit and reduce if necessary
        limit = self.context_manager.get_model_context_limit(
            self.app_state.models.model
        )
        base_prompt = self.get_base_prompt() + text_input

        try:
            history, selected_text = self.context_manager.reduce_context_to_fit_limit(
                fixed_prompt=base_prompt,
                history=self.app_state.conversation.conversation_history,
                selected_text=context["selected_text"],
                model_limit=limit,
            )
        except ContextOverflowError as e:
            logger.error(f"Context optimization failed: {e}")
            if self.generation_controller.window:
                self.generation_controller._safe_js_call(
                    "displayError",
                    "Context too large. Please reduce selection or clear history.",
                )
            return None

        # Update state with optimized context
        self.app_state.conversation.conversation_history = history
        context["selected_text"] = selected_text

        # Build system prompt with context
        system_prompt = self.build_general_system_prompt(context)
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(self.app_state.conversation.conversation_history)

        # Construct user message
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": text_input}]
        if context["image_data_url"]:
            user_content.append(
                {"type": "image_url", "image_url": {"url": context["image_data_url"]}}
            )
        messages.append({"role": "user", "content": user_content})

        # Execute API call
        response = self.generation_controller.execute_ai_api_call(
            messages,
            self.app_state.models.model,
            show_streaming=True,
            processing_mode="text",
        )

        if response:
            # Update conversation history
            self.app_state.conversation.conversation_history.append(
                {"role": "user", "content": text_input}
            )
            self.app_state.conversation.conversation_history.append(
                {"role": "assistant", "content": response}
            )

            # Save to history
            self.history_manager.add_entry(
                f"[User] {text_input}\n[AI] {response.strip()}"
            )

            # Refresh dashboard if settings window is open
            if self.app_state.ui.settings_window:
                self.app_state.ui.settings_window.evaluate_js("refreshDashboardFull()")

        return response

    def get_base_prompt(self) -> str:
        """
        Return the immutable core instructions.

        Returns:
            Base system prompt string.
        """
        return """# SYSTEM_CORE
Role: Desktop Assistant & Text Processor.

# IMMUTABLE_RULES
1. NO FILLER: Ban phrases like "As an AI", "Sure", "Here is the text".
2. EDITING: If user asks to modify text, output ONLY the result.
3. LANGUAGE: Detect user input language and match it 100%.
4. FORMAT: Markdown.
"""

    def build_general_system_prompt(self, context: Dict[str, Any]) -> str:
        """
        Dynamically build the system prompt based on available context.

        Args:
            context: Context dictionary with image and text data.

        Returns:
            Complete system prompt with capabilities and context.
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        base_prompt = self.get_base_prompt()

        # Add capabilities based on model type
        if (
            self.app_state.models.model in self.app_state.models.advanced_model_list
            or self.app_state.models.model in self.app_state.models.tool_model_list
        ):
            base_prompt += "\n# CAPABILITIES\n- Web Search: Enabled (Cite sources).\n- Code: Enabled."

        # Structured Context Injection using XML-like tags
        context_string = f"\n# CURRENT_CONTEXT\nDate: {date_str}.\n"

        if context["image_data_url"]:
            context_string += "[Input contains Image Data]\n"

        if context["selected_text"]:
            # Strong demarcation to prevent model confusion
            context_string += f"""
<selected_content_to_process>
{context['selected_text']}
</selected_content_to_process>
Instruction: Apply user request to the content above.
"""
        else:
            context_string += "Mode: General Knowledge / Chat."

        return base_prompt + context_string

    def generate_ai_text(self) -> None:
        """
        Public Entry Point for AI Generation.

        Workflow: Validation → Recording → Async Context Aggregation → Generation

        This method orchestrates the entire AI generation pipeline including
        recording, transcription, context capture, agent detection, and response
        generation.
        """
        start_time = time.time()
        logger.info("AI text generation started")

        # Step 1: Validation
        is_valid, error = self.generation_controller.validate_preconditions()
        if not is_valid:
            if error and self.generation_controller.window:
                self.generation_controller._safe_js_call("displayError", error)
            return

        # Setup watchdog timer
        timer = threading.Timer(
            OPERATION_WATCHDOG_TIMEOUT_SECONDS,
            self.generation_controller.force_reset_state_after_timeout,
        )
        timer.start()

        audio_file_path: Optional[str] = None
        screen_path: Optional[str] = None
        self.app_state.is_busy = True
        self.generation_controller.reset_ui_for_new_generation()

        try:
            # Lock settings button
            if self.generation_controller.window:
                self.generation_controller._safe_js_call("setSettingsButtonState", True)

            # Step 2: Recording
            if not self.app_state.ai_recording:
                try:
                    audio_file_path = self.generation_controller.start_recording()
                except Exception as e:
                    logger.error(f"Failed to start recording: {e}")
                    self.app_state.is_busy = False
                    try:
                        self.generation_controller._safe_js_call(
                            "setSettingsButtonState", False
                        )
                    except Exception:
                        pass
                    return
                return

            # Stop recording and get audio file
            audio_file_path, duration = self.generation_controller.stop_recording()

            if not os.path.exists(audio_file_path):
                logger.error(f"Audio file not found: {audio_file_path}")
                self.app_state.is_busy = False
                self.generation_controller.cleanup_recording_ui()
                return

            # Step 3: Parallel Execution - Transcription + Context Capture
            self.generation_controller.show_loading_ui()

            transcript: str = ""
            generation_context: Optional[Dict[str, Any]] = None

            # Concurrency: Run Network I/O and Local I/O in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                logger.debug("Starting parallel tasks: Transcription & Context Capture")

                future_transcription = executor.submit(
                    self.transcription_service.transcribe,
                    audio_file_path,
                    self.app_state.models.language,
                    duration,
                )

                future_context = executor.submit(self.capture_context_for_general)

                # Barrier: Wait for both tasks
                try:
                    transcript = future_transcription.result()
                    generation_context = future_context.result()
                except Exception as e:
                    logger.error(f"Parallel execution failed: {e}", exc_info=True)
                    raise

            # Handle Transcription Errors
            if transcript and transcript.lower().startswith("error"):
                logger.error(f"Transcription error: {transcript}")
                timer.cancel()
                self.app_state.is_busy = False
                self.app_state.conversation.is_ai_response_visible = False

                if self.generation_controller.window:
                    self.generation_controller._safe_js_call("displayError", transcript)

                self.generation_controller.safe_remove_file(audio_file_path)
                if generation_context and generation_context.get("screenshot_path"):
                    self.generation_controller.safe_remove_file(
                        generation_context["screenshot_path"]
                    )
                return

            # Update statistics in background
            threading.Thread(
                target=self.stats_manager.update_stats,
                args=(transcript, duration),
                daemon=True,
                name="StatsUpdate",
            ).start()

            # Step 4: Check for Agent Triggers
            agent, instruction = self.find_triggered_agent(transcript)

            if agent:
                try:
                    # Cleanup: If agent doesn't use vision, delete pre-captured screenshot
                    if (
                        not agent.get("screen_vision")
                        and generation_context
                        and generation_context.get("screenshot_path")
                    ):
                        self.generation_controller.safe_remove_file(
                            generation_context["screenshot_path"]
                        )

                    self.execute_agent(agent, instruction, transcript, duration)
                    return

                except Exception as error:
                    logger.error(f"Agent execution failed: {error}", exc_info=True)
                    return

            # Step 5: General Generation
            if generation_context:
                screen_path = generation_context.get("screenshot_path")
                self.execute_general_generation(
                    transcript, generation_context, duration
                )

        except Exception as error:
            logger.error(f"AI generation crashed: {error}", exc_info=True)
            self.app_state.audio.is_recording = False
            self.app_state.ai_recording = False
            self.generation_controller.cleanup_recording_ui()

        finally:
            self.app_state.is_busy = False

            if timer.is_alive():
                timer.cancel()

            self.generation_controller.cleanup_temp_files(audio_file_path, screen_path)

            try:
                self.generation_controller._safe_js_call(
                    "setSettingsButtonState", False
                )
            except Exception as e:
                logger.warning(f"Failed to unlock settings button: {e}")

            elapsed = time.time() - start_time
            logger.info(f"AI text generation completed in {elapsed:.3f}s")
