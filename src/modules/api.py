"""
API Interface for Ozmoz.

This module acts as the bridge between the Frontend (HTML/JS) running in pywebview
and the Python Backend logic. It exposes methods that can be called directly
from JavaScript via `window.pywebview.api`.
"""

import json
import logging
import subprocess
import tempfile
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, List, Optional, Set, Union
from urllib.parse import urlparse

import pyperclip
import requests
import webview
import win32con
import win32gui

# --- Local Modules ---
from modules.config import AppConfig, AppState
from modules.local_audio import local_whisper

# --- Constants ---
LOGGER = logging.getLogger(__name__)

# Window Dimensions & Positioning
MAIN_WINDOW_WIDTH: Final[int] = 415
MAIN_WINDOW_HEIGHT: Final[int] = 117
MAIN_WINDOW_START_X: Final[int] = 100
MAIN_WINDOW_START_Y: Final[int] = 100

SETTINGS_WINDOW_WIDTH: Final[int] = 1015
SETTINGS_WINDOW_HEIGHT: Final[int] = 650
SETTINGS_MIN_WIDTH: Final[int] = 744
SETTINGS_MIN_HEIGHT: Final[int] = 534

# Delays & Timeouts
WINDOW_ANIMATION_DELAY: Final[float] = 0.3
UPDATE_INSTALL_DELAY: Final[int] = 3
DOWNLOAD_TIMEOUT_SECONDS: Final[int] = 60
DOWNLOAD_CHUNK_SIZE: Final[int] = 8192

# Allowed Update Domains (Security Whitelist)
ALLOWED_UPDATE_DOMAINS: Final[Set[str]] = {
    "github.com",
    "objects.githubusercontent.com",
}

# Nova-3 Supported Languages
NOVA3_SUPPORTED_LANGUAGES: Final[Set[str]] = {
    "en",
    "es",
    "fr",
    "de",
    "hi",
    "ru",
    "pt",
    "ja",
    "it",
    "nl",
    "sv",
    "da",
}


class API:
    """
    Interface exposed to JavaScript via pywebview.

    This class handles:
    - Window management (move, resize, hide, show).
    - Settings logic (language, API keys, models).
    - Application lifecycle (update, exit).
    - Feature triggers (recording, AI generation, logs).
    """

    def __init__(
        self,
        app_state: AppState,
        config_manager: Any,
        window_manager: Any,
        audio_manager: Any,
        transcription_manager: Any,
        hotkey_manager: Any,
        replacement_manager: Any,
        update_manager: Any,
        stats_manager: Any,
        history_manager: Any,
        agent_manager: Any,
        ai_generation_manager: Any,
        ui_resource_loader: Any,
    ) -> None:
        """
        Initialize the API with all necessary service dependencies.
        """
        self._app_state = app_state
        self._config_manager = config_manager
        self._window_manager = window_manager
        self._audio_manager = audio_manager
        self._transcription_manager = transcription_manager
        self._hotkey_manager = hotkey_manager
        self._replacement_manager = replacement_manager
        self._update_manager = update_manager
        self._stats_manager = stats_manager
        self._history_manager = history_manager
        self._agent_manager = agent_manager
        self._ai_generation_manager = ai_generation_manager
        self._ui_resource_loader = ui_resource_loader

    # --- Helper Methods (Internal) ---

    def _evaluate_js_safe(self, window: Any, func_name: str, *args: Any) -> None:
        """
        Safely executes a JavaScript function in the given window with JSON-serialized arguments.
        Prevents JS injection attacks.

        Args:
            window: The webview window instance.
            func_name: The name of the JS function to call.
            *args: Arguments to pass to the function.
        """
        if not window:
            return

        try:
            # Serialize all arguments to JSON to handle quotes/escapes safely
            serialized_args = ",".join(json.dumps(arg) for arg in args)
            js_code = f"{func_name}({serialized_args})"
            window.evaluate_js(js_code)
        except Exception as e:
            LOGGER.error(f"Failed to evaluate JS '{func_name}': {e}")

    def _get_window_handle(self, title: str = "Ozmoz") -> int:
        """
        Retrieves the Windows HWND handle for a window by title.

        Args:
            title: Window title to search for.

        Returns:
            int: Window handle or 0 if not found.
        """
        try:
            return win32gui.FindWindow(None, title)
        except Exception as e:
            LOGGER.error(f"Error finding window '{title}': {e}")
            return 0

    # --- Lifecycle & Windows ---

    def open_main_window(self) -> None:
        """
        Loads the main HTML content and positions the window.
        """
        if self._app_state.ui.window:
            html_content = self._ui_resource_loader.create_html(
                "src/templates/index.html"
            )
            self._app_state.ui.window.load_html(html_content)
            self._app_state.ui.window.resize(MAIN_WINDOW_WIDTH, MAIN_WINDOW_HEIGHT)
            self._window_manager.move_main_window(
                MAIN_WINDOW_START_X, MAIN_WINDOW_START_Y
            )

    def get_app_version(self) -> Dict[str, str]:
        """
        Returns the current application version.

        Returns:
            Dict[str, str]: {"version": "x.y.z"}
        """
        return {"version": AppConfig.VERSION}

    def request_exit(self, icon: Any = None, item: Any = None) -> None:
        """
        Cleanly exits the application by destroying all windows.
        This will unblock webview.start() in the main thread.
        """
        if self._app_state.is_exiting:
            return
        self._app_state.is_exiting = True

        LOGGER.info("API: Requesting exit...")

        if getattr(self._app_state.threading, "stop_app_event", None):
            self._app_state.threading.stop_app_event.set()

        try:
            import webview

            for window in list(webview.windows):
                window.destroy()
        except Exception as error:
            LOGGER.error(f"API: Error destroying windows: {error}")

    def get_window_pos(self) -> Dict[str, Any]:
        """
        Retrieves the current X and Y coordinates of the main window.

        Returns:
            Dict[str, Any]: {"x": int, "y": int} or {"error": str}.
        """
        handle = self._get_window_handle("Ozmoz")
        if not handle:
            return {"x": 0, "y": 0, "error": "Window not found"}

        try:
            rect = win32gui.GetWindowRect(handle)
            # rect[0] is x, rect[1] is y
            return {"x": rect[0], "y": rect[1]}
        except Exception as error:
            LOGGER.error(f"Error in get_window_pos: {error}")
            return {"x": 0, "y": 0, "error": str(error)}

    def move_window(self, x: Union[int, float], y: Union[int, float]) -> None:
        """Moves the main window to the specified coordinates."""
        self._window_manager.move_main_window(int(x), int(y))

    def drag_window(self, delta_x: int, delta_y: int) -> None:
        """
        Moves the window relative to its current position based on mouse delta.
        """
        handle = self._get_window_handle("Ozmoz")
        if not handle:
            return

        try:
            rect = win32gui.GetWindowRect(handle)
            current_x, current_y = rect[0], rect[1]

            new_x = current_x + int(delta_x)
            new_y = current_y + int(delta_y)

            self.move_window(new_x, new_y)
        except Exception as error:
            LOGGER.error(f"Drag window error: {error}")

    def resize_window(self, width: int, height: int) -> str:
        """Resizes the main window to the specified dimensions."""
        if self._app_state.ui.window:
            self._app_state.ui.window.resize(width, height)
            return f"Window resized to {width}x{height}"
        return "Window not available"

    def hide_window(self) -> Dict[str, Union[bool, str]]:
        """Hides the main window."""
        handle = self._get_window_handle("Ozmoz")
        if not handle:
            return {"success": False, "error": "Window not found."}

        if win32gui.IsWindowVisible(handle):
            win32gui.ShowWindow(handle, win32con.SW_HIDE)

        return {"success": True}

    def show_window(self) -> Dict[str, Union[bool, str]]:
        """
        Shows the window as TopMost without stealing focus (ShowNoActivate).
        """
        handle = self._get_window_handle("Ozmoz")
        if not handle:
            return {"success": False, "error": "Window not found"}

        try:
            win32gui.ShowWindow(handle, win32con.SW_SHOWNA)
            win32gui.SetWindowPos(
                handle,
                win32con.HWND_TOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
            )
            return {"success": True}
        except Exception as error:
            LOGGER.error(f"Error in show_window: {error}")
            return {"success": False, "error": str(error)}

    # --- Settings Window ---

    def toggle_settings(self) -> None:
        """Toggles the settings window visibility (opens it)."""
        self.show_settings()

    def show_settings(self) -> None:
        """Creates or re-displays the settings window."""
        if self._app_state.ui.settings_window:
            try:
                self._app_state.ui.settings_window.show()
                self._window_manager.bring_to_foreground("Ozmoz Settings")
                return
            except Exception:
                self._app_state.ui.settings_window = None

        LOGGER.info("API: Creating settings window dynamically...")
        try:

            def on_closing() -> bool:
                if self._app_state.is_exiting:
                    return True
                self._app_state.ui.settings_window = None
                import gc

                gc.collect()
                return True

            # 1. On crée la fenêtre mais on la garde CACHÉE (hidden=True)
            new_window = webview.create_window(
                "Ozmoz Settings",
                html=self._ui_resource_loader.create_html(
                    "src/templates/settings.html"
                ),
                js_api=self,
                width=SETTINGS_WINDOW_WIDTH,
                height=SETTINGS_WINDOW_HEIGHT,
                min_size=(SETTINGS_MIN_WIDTH, SETTINGS_MIN_HEIGHT),
                resizable=True,
                frameless=False,
                easy_drag=True,
                background_color="#FFFFFF",
                text_select=True,
                transparent=False,
                hidden=True,  
            )

            def on_loaded():
                new_window.show()
                self._window_manager.bring_to_foreground("Ozmoz Settings")

            new_window.events.loaded += on_loaded
            new_window.events.closing += on_closing
            
            self._app_state.ui.settings_window = new_window

        except Exception:
            LOGGER.critical("API: Error creating settings window", exc_info=True)

    def restart_settings_window(self) -> None:
        """Forces the settings window to be destroyed and recreated."""
        if self._app_state.ui.settings_window:
            self._app_state.ui.settings_window.destroy()
            self._app_state.ui.settings_window = None
            time.sleep(WINDOW_ANIMATION_DELAY)
            self.show_settings()

    # --- Audio & Transcription ---

    def start_recording(self) -> None:
        """Initiates the audio recording process."""
        self._audio_manager.start_recording()

    def stop_recording(self) -> None:
        """Stops the audio recording and triggers the transcription process."""
        self._transcription_manager.stop_recording_and_transcribe()

    # --- Models (AI & Config) ---

    def get_remote_config(self) -> Optional[List[Dict[str, Any]]]:
        """Retrieves the remote configuration for models."""
        if self._app_state.cached_remote_config is None:
            self._config_manager.load_and_parse_remote_config()
        return self._app_state.cached_remote_config

    def get_available_models(self) -> List[str]:
        """Returns a list of all available AI model IDs."""
        return self._config_manager.fetch_ai_models()

    def get_filtered_text_models(self) -> List[Dict[str, Any]]:
        """
        Filters and translates available text models for the UI.
        Prioritizes models based on available API keys and configuration.
        """
        LOGGER.info(
            f"Retrieving text models (Language: {self._app_state.models.language})"
        )

        available_model_ids = self._config_manager.fetch_ai_models()

        if not self._app_state.cached_remote_config:
            self._config_manager.load_and_parse_remote_config()
        if not self._app_state.cached_remote_config:
            return []

        final_models_list: List[Dict[str, Any]] = []
        seen_families: Set[str] = set()

        cred_mgr = self._config_manager.credential_manager
        has_any_key = bool(cred_mgr.get_api_key("groq_ai")) or bool(
            cred_mgr.get_api_key("cerebras")
        )

        for model_item in self._app_state.cached_remote_config:
            if "name" in model_item and isinstance(model_item.get("advantage"), dict):
                name = model_item["name"]
                family = model_item.get("family", name)

                if has_any_key:
                    if name not in available_model_ids:
                        continue
                else:
                    if family in seen_families:
                        continue
                    seen_families.add(family)

                advantage_data = model_item.get("advantage", {})
                translated_advantage = advantage_data.get(
                    self._app_state.models.language,
                    advantage_data.get("en", "No description"),
                )

                is_multimodal = (
                    "vision" in (advantage_data.get("en", "") or "").lower()
                    or name in self._app_state.models.screen_vision_model_list
                )
                is_web_model = (
                    name in self._app_state.models.tool_model_list
                    or "web" in (advantage_data.get("en", "") or "").lower()
                )

                final_models_list.append(
                    {
                        "id": name,
                        "name": name,
                        "advantage": translated_advantage,
                        "description": model_item.get("description", ""),
                        "is_multimodal": is_multimodal,
                        "is_web_model": is_web_model,
                        "provider": model_item.get("provider", "groq"),
                        "family": family,
                    }
                )

        return final_models_list

    def get_translated_audio_models(self) -> List[Dict[str, Any]]:
        """Translates descriptions for audio models and injects the hardcoded Local Models."""
        if not self._app_state.cached_remote_config:
            self._config_manager.load_and_parse_remote_config()

        translated_models = [
            {
                "name": "local-whisper-large-v3-turbo",
                "advantage": "Local",
                "provider": "local",
                "is_local": True,
                "size": "~1.6 GB",
            },
            {
                "name": "local-distil-large-v3",
                "advantage": "Local",
                "provider": "local",
                "is_local": True,
                "size": "~1.5 GB",
            },
            {
                "name": "local-whisper-small",
                "advantage": "Local",
                "provider": "local",
                "is_local": True,
                "size": "~400 MB",
            },
        ]

        audio_config_data = next(
            (
                item
                for item in (self._app_state.cached_remote_config or [])
                if "audio_models" in item
            ),
            None,
        )

        if audio_config_data:
            for model_entry in audio_config_data.get("audio_models", []):
                advantage_data = model_entry.get("advantage", {})
                translated_advantage = advantage_data.get(
                    self._app_state.models.language,
                    advantage_data.get("en", "Standard"),
                )

                translated_models.append(
                    {
                        "name": model_entry.get("name"),
                        "advantage": translated_advantage,
                        "provider": model_entry.get("provider", "groq"),
                    }
                )

        return translated_models

    def get_local_model_status(self) -> Dict[str, Any]:
        """Returns the current installation status for EACH local model."""
        local_models = [
            "local-whisper-large-v3-turbo",
            "local-distil-large-v3",
            "local-whisper-small",
        ]

        return {
            "installed": {
                name: local_whisper.is_installed(name) for name in local_models
            },
            "loading": local_whisper.is_loading,
        }

    def install_local_model(
        self, model_name: str = "local-whisper-large-v3-turbo"
    ) -> Dict[str, Any]:
        """
        Initiates the download process in a background thread.
        Notifies the UI upon completion via safe JavaScript execution.
        """
        if local_whisper.is_loading:
            return {"success": False, "error": "Download already in progress."}

        def run_install() -> None:
            success = local_whisper.download(model_name)
            if self._app_state.ui.settings_window:
                status = "success" if success else "error"
                # Securely call JS with JSON serialization
                self._evaluate_js_safe(
                    self._app_state.ui.settings_window,
                    "window.onLocalModelInstallFinished",
                    status,
                    model_name,
                )

        threading.Thread(target=run_install, daemon=True).start()
        return {"success": True, "message": f"Installation of {model_name} started"}

    def set_model(self, model_ai: str) -> Dict[str, bool]:
        """Sets the active AI model."""
        self._app_state.models.model = model_ai
        self._app_state.models.last_selected_model = model_ai
        self._config_manager.save_local_settings()
        LOGGER.info(f"Model set: {self._app_state.models.model}")
        return {"success": True}

    def get_current_model(self) -> str:
        """Returns the ID of the currently selected AI model."""
        return self._app_state.models.model

    def set_audio_model(self, model_name: str) -> Dict[str, bool]:
        """Sets the active audio transcription model."""
        self._app_state.models.audio_model = model_name
        self._config_manager.save_local_settings()
        return {"success": True}

    def get_current_audio_model(self) -> str:
        """Returns the ID of the currently selected audio model."""
        return self._app_state.models.audio_model

    # --- AI Generation & Context ---

    def generate_ai_text(self) -> str:
        """Triggers the AI text generation process in a separate thread."""
        threading.Thread(
            target=self._ai_generation_manager.generate_ai_text, daemon=True
        ).start()
        return "Generating text..."

    def set_ai_response_visible(self, is_visible: bool) -> Dict[str, bool]:
        """Updates the visibility state of the AI response window."""
        self._app_state.conversation.is_ai_response_visible = bool(is_visible)
        if not self._app_state.conversation.is_ai_response_visible:
            self.clear_ai_context()
        return {"success": True}

    def clear_ai_context(self) -> Dict[str, bool]:
        """Clears the current AI conversation history."""
        self._app_state.conversation.conversation_history.clear()
        return {"success": True}

    # --- Language ---

    def set_language(self, language: str) -> Dict[str, Any]:
        """Sets the application language and adjusts audio models if necessary."""
        self._app_state.models.language = language

        language_clean = language.lower().strip()
        language_base = language_clean.split("-")[0]

        # Downgrade to Nova-2 if the language is not supported by Nova-3
        if self._app_state.models.audio_model == "nova-3":
            if (
                language_clean not in NOVA3_SUPPORTED_LANGUAGES
                and language_base not in NOVA3_SUPPORTED_LANGUAGES
            ):
                self._app_state.models.audio_model = "nova-2"

        self._config_manager.save_local_settings()
        return {
            "success": True,
            "final_audio_model": self._app_state.models.audio_model,
        }

    def get_current_language(self) -> str:
        """Returns the current application language code."""
        return self._app_state.models.language

    # --- Agents ---

    def get_agents(self) -> List[Dict[str, Any]]:
        """Loads and returns the list of configured agents."""
        return self._agent_manager.load_agents()

    def add_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Adds a new agent to the configuration."""
        agents = self._agent_manager.load_agents()

        model_id = agent_data.get("model")
        if model_id and model_id not in self._config_manager.fetch_ai_models():
            return {"success": False, "error": f"Model '{model_id}' unavailable"}

        new_agent = {
            "id": str(uuid.uuid4()),
            "name": agent_data["name"],
            "trigger": agent_data.get("trigger"),
            "prompt": agent_data["prompt"],
            "model": agent_data.get("model", ""),
            "active": False,
            "autopaste": agent_data.get("autopaste", True),
            "screen_vision": agent_data.get("screen_vision", False),
        }
        agents.append(new_agent)

        saved = self._agent_manager.save_agents(agents)
        return (
            {"success": True} if saved else {"success": False, "error": "Save failed"}
        )

    def update_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates an existing agent's configuration."""
        agents = self._agent_manager.load_agents()

        model_id = agent_data.get("model")
        if model_id and model_id not in self._config_manager.fetch_ai_models():
            return {"success": False, "error": f"Model '{model_id}' unavailable"}

        agent_id = agent_data.get("id")
        for idx, agent in enumerate(agents):
            if agent.get("id") == agent_id:
                agents[idx].update(
                    {
                        "name": agent_data["name"],
                        "trigger": agent_data.get("trigger"),
                        "prompt": agent_data["prompt"],
                        "model": agent_data.get("model", ""),
                        "autopaste": agent_data.get("autopaste", True),
                        "screen_vision": agent_data.get("screen_vision", False),
                    }
                )
                saved = self._agent_manager.save_agents(agents)
                return (
                    {"success": True}
                    if saved
                    else {"success": False, "error": "Save failed"}
                )

        return {"success": False, "error": "Agent not found"}

    def delete_agent(self, agent_id: str) -> bool:
        """Deletes an agent by its ID."""
        current_agents = self._agent_manager.load_agents()
        updated_agents = [a for a in current_agents if a["id"] != agent_id]
        return self._agent_manager.save_agents(updated_agents)

    def toggle_agent_status(self, agent_id: str, is_active: bool) -> Dict[str, Any]:
        """Enables or disables an agent."""
        agents = self._agent_manager.load_agents()
        updated = False

        for agent in agents:
            if agent["id"] == agent_id:
                if is_active and agent.get("model"):
                    if agent["model"] not in self._config_manager.fetch_ai_models():
                        return {
                            "success": False,
                            "error": f"Model '{agent['model']}' unavailable",
                        }
                agent["active"] = is_active
                updated = True
                break

        if updated:
            saved = self._agent_manager.save_agents(agents)
            return (
                {"success": True}
                if saved
                else {"success": False, "error": "Save failed"}
            )

        return {"success": False, "error": "Agent not found"}

    # --- History & Stats ---

    def get_history(self) -> List[Dict[str, Any]]:
        """Retrieves the usage history."""
        return self._history_manager.get_all()

    def delete_history(self) -> bool:
        """Clears the usage history."""
        return self._history_manager.clear()

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Retrieves formatted statistics for the dashboard."""
        return self._stats_manager.get_formatted_dashboard_stats()

    def get_activity_data(self, days: int = 7) -> Dict[str, Any]:
        """Retrieves activity chart data for the specified number of days."""
        return self._stats_manager.get_chart_data(days)

    def set_chart_type(self, type_str: str) -> Dict[str, Union[bool, str]]:
        """Sets the preferred chart type (line or bar)."""
        if type_str in ["line", "bar"]:
            self._app_state.ui.chart_type = type_str
            self._config_manager.save_local_settings()
            if self._app_state.ui.settings_window:
                self._app_state.ui.settings_window.evaluate_js(
                    "if (document.getElementById('home').classList.contains('active')) { loadActivityChartData(); }"
                )
            return {"success": True}
        return {"success": False, "error": "Invalid chart type"}

    def set_dashboard_period(
        self, days: Union[str, int]
    ) -> Dict[str, Union[bool, str]]:
        """Saves the dashboard period preference (7 or 30 days)."""
        try:
            days_int = int(days)
            if days_int in [7, 30]:
                self._app_state.ui.dashboard_period = days_int
                self._config_manager.save_local_settings()
                return {"success": True}
            return {"success": False, "error": "Invalid period value"}
        except ValueError as error:
            return {"success": False, "error": str(error)}

    # --- Hotkeys ---

    def get_hotkeys(self) -> Dict[str, str]:
        """Returns the current hotkey configuration."""
        return self._app_state.hotkeys

    def temporarily_disable_all_hotkeys(self) -> Dict[str, Union[bool, str]]:
        """Cleanly stops the hotkey listener to allow recording a new combination."""
        try:
            self._hotkey_manager.stop_listening()
            LOGGER.info("Hotkeys successfully disabled.")
            return {"success": True}
        except Exception as error:
            LOGGER.error(f"Failed to temporarily disable hotkeys: {error}")
            return {"success": False, "error": str(error)}

    def restore_all_hotkeys(self) -> Dict[str, Union[bool, str]]:
        """Restarts the hotkey listener by re-registering all defined hotkeys."""
        try:
            self._hotkey_manager.register_all()
            LOGGER.info("Hotkeys successfully restored and listener restarted.")
            return {"success": True}
        except Exception as error:
            LOGGER.error(f"Failed to restore and register hotkeys: {error}")
            return {"success": False, "error": str(error)}

    def set_hotkey(self, action_name: str, new_combination: str) -> Dict[str, Any]:
        """Updates a specific hotkey assignment."""
        previous_hotkeys = self._app_state.hotkeys.copy()
        if action_name not in AppConfig.DEFAULT_HOTKEYS or not new_combination:
            return {"success": False, "error": "Invalid input"}

        self._app_state.hotkeys[action_name] = new_combination.lower()
        self._config_manager.save_local_settings()
        try:
            self._hotkey_manager.register_all()
            return {"success": True, "new_hotkeys": self._app_state.hotkeys}
        except Exception:
            self._app_state.hotkeys = previous_hotkeys
            self._app_state.settings["hotkeys"] = previous_hotkeys
            self._config_manager.save_local_settings()
            self.restore_all_hotkeys()
            return {"success": False, "error": "Registration failed"}

    # --- Updates ---

    def check_for_updates(self) -> Dict[str, Any]:
        """Checks if a new version of the application is available."""
        try:
            self._update_manager.fetch_remote_version_info()
            remote_version = self._app_state.remote_version

            if (
                remote_version
                and self._update_manager._compare_versions(
                    remote_version, AppConfig.VERSION
                )
                == 1
            ):
                return {
                    "update_available": True,
                    "remote_version": remote_version,
                    "update_url": self._app_state.remote_update_url,
                }
            return {"update_available": False}
        except Exception as error:
            return {"update_available": False, "error": str(error)}

    def download_and_run_update(self, url: str) -> Dict[str, Any]:
        """Starts the update download and installation process."""
        if not url:
            return {"success": False, "error": "Missing URL."}
        threading.Thread(target=self._update_worker, args=(url,), daemon=True).start()
        return {"success": True, "message": "Download started."}

    def _update_worker(self, url: str) -> None:
        """
        Background worker to download the update and launch the installer.

        SECURITY: Enforces strict URL validation (HTTPS + Whitelisted Domains).
        """
        try:
            parsed_url = urlparse(url)

            # 1. Protocol Validation
            if parsed_url.scheme != "https":
                raise ValueError("Security Violation: Update must use HTTPS.")

            # 2. Domain Validation
            hostname = parsed_url.hostname or ""
            if not any(
                hostname == domain or hostname.endswith(f".{domain}")
                for domain in ALLOWED_UPDATE_DOMAINS
            ):
                raise ValueError(
                    f"Security Violation: Update URL domain '{hostname}' not whitelisted."
                )

            # 3. Safe Path Construction
            temp_dir = Path(tempfile.gettempdir())
            filename = Path(parsed_url.path).name
            if not filename.lower().endswith(".exe"):
                filename += ".exe"

            # Simple sanitization of filename (keeping only alphanumeric/dots/dashes)
            safe_filename = "".join(c for c in filename if c.isalnum() or c in ".-_")
            file_path = (temp_dir / safe_filename).resolve()

            if not file_path.is_relative_to(temp_dir):
                raise ValueError("Path traversal detected in update filename.")

            LOGGER.info(f"Starting secure update download from: {url} to {file_path}")

            with requests.get(
                url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS
            ) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                downloaded_size = 0

                with file_path.open("wb") as file_handle:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        file_handle.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0 and self._app_state.ui.settings_window:
                            progress_percent = (downloaded_size / total_size) * 100
                            self._evaluate_js_safe(
                                self._app_state.ui.settings_window,
                                "updateDownloadProgress",
                                progress_percent,
                            )

            if self._app_state.ui.settings_window:
                self._evaluate_js_safe(
                    self._app_state.ui.settings_window, "finalizeUpdate"
                )

            # Launch the installer
            subprocess.Popen([str(file_path), "/SILENT"])
            time.sleep(UPDATE_INSTALL_DELAY)
            self.request_exit()

        except Exception as error:
            LOGGER.error(f"Update failed: {error}")
            if self._app_state.ui.settings_window:
                self._evaluate_js_safe(
                    self._app_state.ui.settings_window,
                    "showUpdateError",
                    f"Error: {str(error)}",
                )

    # --- Logs & Dev Mode ---

    def set_developer_mode(self, state: bool) -> Dict[str, bool]:
        """Enables or disables developer mode."""
        self._app_state.developer_mode = bool(state)
        self._config_manager.save_local_settings()
        return {"success": True, "developer_mode": self._app_state.developer_mode}

    def get_developer_mode(self) -> Dict[str, bool]:
        """Returns the current status of developer mode."""
        return {"developer_mode": self._app_state.developer_mode}

    def get_logs(self) -> List[Dict[str, str]]:
        """Retrieves logs from the memory buffer if developer mode is active."""
        if not self._app_state.developer_mode:
            return [{"level": "WARNING", "message": "Developer mode disabled."}]

        handler: Any = getattr(self._app_state, "log_handler", None)
        # Check if handler exists and has a buffer attribute
        if handler and hasattr(handler, "buffer"):
            # Ensure thread safety if the handler supports it
            if hasattr(handler, "acquire") and hasattr(handler, "release"):
                handler.acquire()
                try:
                    return list(handler.buffer)
                finally:
                    handler.release()
            return list(handler.buffer)

        return [{"level": "ERROR", "message": "Log handler not found."}]

    def clear_logs(self) -> Dict[str, Union[bool, str]]:
        """Clears the log buffer."""
        handler: Any = getattr(self._app_state, "log_handler", None)
        if handler and hasattr(handler, "buffer"):
            handler.buffer.clear()
            return {"success": True}
        return {"success": False, "error": "Log handler not found."}

    def export_logs(self, logs_to_export: List[str]) -> Dict[str, Any]:
        """
        Opens a save dialog to export logs to a text file.
        """
        try:
            if not self._app_state.ui.window:
                return {"success": False, "error": "Window not found"}

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            default_filename = f"ozmoz_logs_{timestamp}.txt"

            result = self._app_state.ui.window.create_file_dialog(
                webview.SAVE_DIALOG, directory="/", save_filename=default_filename
            )

            if not result:
                return {"success": False, "message": "Cancelled"}

            # Handle different return types from pywebview (tuple, list, str)
            file_path_str: str = ""
            if isinstance(result, (list, tuple)) and len(result) > 0:
                file_path_str = str(result[0])
            elif isinstance(result, str):
                file_path_str = result

            if not file_path_str:
                return {"success": False, "message": "Invalid path selected"}

            file_path = Path(file_path_str)

            # Write with explicit encoding
            with file_path.open("w", encoding="utf-8") as file_handle:
                file_handle.write("\n".join(logs_to_export))

            LOGGER.info(f"Logs exported to: {file_path}")
            return {"success": True, "path": str(file_path)}

        except Exception as error:
            LOGGER.error(f"Export logs error: {error}")
            return {"success": False, "error": str(error)}

    # --- Miscellaneous Features (Replacements, Sound, Web Search, OCR) ---

    def get_replacements(self) -> List[Dict[str, str]]:
        """Returns the list of configured text replacements."""
        return self._replacement_manager.load()

    def add_replacement(self, word1: str, word2: str) -> bool:
        """Adds a new text replacement pair."""
        replacements = self._replacement_manager.load()
        replacements.append({"word1": word1, "word2": word2})
        return self._replacement_manager.save(replacements)

    def delete_replacement(self, index: int) -> bool:
        """Deletes a text replacement by index."""
        replacements = self._replacement_manager.load()
        if 0 <= index < len(replacements):
            del replacements[index]
            return self._replacement_manager.save(replacements)
        return False

    def set_sound_enabled(self, state: bool) -> None:
        """Enables or disables application sounds."""
        self._app_state.audio.sound_enabled = bool(state)
        self._config_manager.save_local_settings()

    def mute_sound(self, state: bool) -> None:
        """Mutes or unmutes sounds temporarily."""
        self._app_state.audio.mute_sound = bool(state)
        self._config_manager.save_local_settings()

    # --- Utils ---

    def copy_text(self, text: str) -> str:
        """Copies the provided text to the system clipboard."""
        try:
            pyperclip.copy(text)
            return "Text copied"
        except Exception as error:
            return f"Error: {error}"

    def open_external_link(self, url: str) -> Dict[str, Union[bool, str]]:
        """
        Opens a URL in the default system browser.
        Validates the URL scheme to prevent arbitrary command execution.
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Invalid protocol")

            webbrowser.open_new_tab(url)
            return {"success": True}
        except Exception as error:
            return {"success": False, "error": str(error)}

    # --- API Key Management ---

    def get_api_configuration(self) -> Dict[str, str]:
        """
        Sends existing keys to the frontend masked for security.
        """
        try:
            raw_keys = self._config_manager.credential_manager.get_raw_keys_for_ui()
            masked_keys = {}

            for key, value in raw_keys.items():
                masked_keys[key] = "************************" if value else ""

            return masked_keys
        except Exception as error:
            LOGGER.error(f"Error in get_api_configuration: {error}")
            return {}

    def save_api_keys(self, data: Dict[str, str]) -> Dict[str, Union[bool, str]]:
        """
        Receives data from the settings form and saves API keys.
        Ignores fields that contain the security mask.
        """
        try:
            mapping = {
                "api-key-groq-audio": "groq_audio",
                "api-key-deepgram": "deepgram",
                "api-key-groq-ai": "groq_ai",
                "api-key-cerebras": "cerebras",
            }

            clean_data = {}

            for html_id, internal_id in mapping.items():
                new_value = data.get(html_id, "").strip()

                if new_value == "************************":
                    continue

                clean_data[internal_id] = new_value

            success = self._config_manager.credential_manager.save_credentials(
                clean_data
            )

            if success:
                self._app_state.models.cached_models = None
                self._app_state.groq_client = None
                self._app_state.deepgram_client = None
                self._app_state.cerebras_client = None
                return {"success": True}
            else:
                return {"success": False, "error": "File write failed."}

        except Exception as error:
            LOGGER.error(f"API save error: {error}")
            return {"success": False, "error": str(error)}

    def get_providers_status(self) -> Dict[str, bool]:
        """Returns the status of API keys to enable/disable UI options."""
        cred_mgr = self._config_manager.credential_manager
        return {
            "groq_ai": bool(cred_mgr.get_api_key("groq_ai")),
            "groq_audio": bool(cred_mgr.get_api_key("groq_audio")),
            "cerebras": bool(cred_mgr.get_api_key("cerebras")),
            "deepgram": bool(cred_mgr.get_api_key("deepgram")),
        }

    def delete_local_model(self, model_name: str) -> Dict[str, bool]:
        """Deletes a local model."""
        success = local_whisper.delete_model(model_name)

        if success and self._app_state.models.audio_model == model_name:
            self._app_state.models.audio_model = "nova-2"
            self._config_manager.save_local_settings()

        return {"success": success}

    def minimize_window(self) -> Dict[str, bool]:
        """Minimizes the settings window."""
        try:
            if self._app_state.ui.settings_window:
                handle = self._get_window_handle("Ozmoz Settings")
                if handle:
                    win32gui.ShowWindow(handle, win32con.SW_MINIMIZE)
                    return {"success": True}
            return {"success": False}
        except Exception as e:
            LOGGER.error(f"Failed to minimize: {e}")
            return {"success": False}

    def toggle_maximize(self) -> Dict[str, bool]:
        """Toggles maximize/restore for settings window."""
        try:
            handle = self._get_window_handle("Ozmoz Settings")
            if handle:
                placement = win32gui.GetWindowPlacement(handle)
                if placement[1] == win32con.SW_MAXIMIZE:
                    win32gui.ShowWindow(handle, win32con.SW_RESTORE)
                else:
                    win32gui.ShowWindow(handle, win32con.SW_MAXIMIZE)
                return {"success": True}
            return {"success": False}
        except Exception as e:
            LOGGER.error(f"Failed to toggle maximize: {e}")
            return {"success": False}

    def close_settings_window(self) -> Dict[str, bool]:
        """Closes and destroys the settings window to free RAM."""
        if self._app_state.ui.settings_window:
            self._app_state.ui.settings_window.destroy()
            self._app_state.ui.settings_window = None

            import gc

            gc.collect()

            return {"success": True}
        return {"success": False}
