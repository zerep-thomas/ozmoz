import logging
import os
import subprocess
import tempfile
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pyperclip
import requests
import webview
import win32con
import win32gui

# Qt Imports for UI management
from PySide6.QtWidgets import QApplication

# Internal modules
from modules.config import AppConfig, AppState


class API:
    """
    Interface exposed to JavaScript via pywebview.
    Acts as a bridge between the Frontend (HTML/JS) and the Python Backend.
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
    ):
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

    # --- Lifecycle & Windows ---

    def open_main_window(self) -> None:
        """
        Loads the HTML content into the main window and positions it.
        """
        if self._app_state.window:
            self._app_state.window.load_html(
                self._ui_resource_loader.create_html("templates/index.html")
            )
            self._app_state.window.resize(415, 117)
            self._window_manager.move_main_window(100, 100)

    def get_app_version(self) -> Dict[str, str]:
        """
        Returns the current application version.
        """
        return {"version": AppConfig.VERSION}

    def request_exit(self, icon: Any = None, item: Any = None) -> None:
        """
        Cleanly exits the application (Qt + Webview), ensuring all threads and windows are closed.
        """
        if self._app_state.is_exiting:
            return
        self._app_state.is_exiting = True

        logging.info("API: Requesting exit...")

        if self._app_state.stop_app_event:
            self._app_state.stop_app_event.set()

        q_app = QApplication.instance()
        if q_app:
            q_app.quit()

        try:
            if self._app_state.settings_window:
                self._app_state.settings_window.destroy()
            if self._app_state.window:
                self._app_state.window.destroy()
        except Exception as error:
            logging.error(f"API: Error destroying windows: {error}")

    def get_window_pos(self) -> Dict[str, Any]:
        """
        Retrieves the current X and Y coordinates of the main window.
        """
        try:
            hwnd = win32gui.FindWindow(None, "Ozmoz")
            if not hwnd:
                return {"x": 0, "y": 0, "error": "Window not found"}
            rect = win32gui.GetWindowRect(hwnd)
            # rect[0] is x, rect[1] is y
            return {"x": rect[0], "y": rect[1]}
        except Exception as error:
            logging.error(f"Error in get_window_pos: {error}")
            return {"x": 0, "y": 0, "error": str(error)}

    def move_window(self, x: Union[int, float], y: Union[int, float]) -> None:
        """
        Moves the main window to the specified coordinates.
        """
        self._window_manager.move_main_window(int(x), int(y))

    def drag_window(self, delta_x: int, delta_y: int) -> None:
        """
        Moves the window relative to its current position based on mouse delta.
        """
        try:
            hwnd = win32gui.FindWindow(None, "Ozmoz")
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                current_x, current_y = rect[0], rect[1]

                new_x = current_x + int(delta_x)
                new_y = current_y + int(delta_y)

                self.move_window(new_x, new_y)
        except Exception as error:
            logging.error(f"Drag window error: {error}")

    def resize_window(self, width: int, height: int) -> str:
        """
        Resizes the main window to the specified dimensions.
        """
        if self._app_state.window:
            self._app_state.window.resize(width, height)
            return f"Window resized to {width}x{height}"
        return "Window not available"

    def hide_window(self) -> Dict[str, Union[bool, str]]:
        """
        Hides the main window and re-registers hotkeys to ensure focus isn't lost.
        """
        hwnd = win32gui.FindWindow(None, "Ozmoz")
        if not hwnd:
            return {"success": False, "error": "Window not found."}

        if win32gui.IsWindowVisible(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)

        try:
            self._hotkey_manager.register_all()
        except Exception as error:
            logging.error(f"Error re-registering hotkeys (hide): {error}")

        return {"success": True}

    def show_window(self) -> Dict[str, Union[bool, str]]:
        """
        Shows the window as TopMost without stealing focus (ShowNoActivate).
        """
        try:
            hwnd = win32gui.FindWindow(None, "Ozmoz")
            if hwnd:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWNA)
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
                )
                return {"success": True}
            return {"success": False, "error": "Window not found"}
        except Exception as error:
            logging.error(f"Error in show_window: {error}")
            return {"success": False, "error": str(error)}

    # --- Settings Window ---

    def toggle_settings(self) -> None:
        """
        Toggles the settings window visibility (opens it).
        """
        self.show_settings()

    def show_settings(self) -> None:
        """
        Creates or re-displays the settings window.
        """
        if self._app_state.settings_window:
            try:
                self._app_state.settings_window.show()
                self._window_manager.bring_to_foreground("Ozmoz Settings")
                return
            except Exception:
                self._app_state.settings_window = None

        logging.info("API: Creating settings window...")
        try:

            def on_closing() -> bool:
                if self._app_state.is_exiting:
                    return True

                if self._app_state.settings_window:
                    self._app_state.settings_window.hide()
                return False

            new_window = webview.create_window(
                "Ozmoz Settings",
                html=self._ui_resource_loader.create_html("templates/settings.html"),
                js_api=self,
                width=1015,
                height=650,
                min_size=(744, 534),
                resizable=True,
                frameless=False,
                easy_drag=True,
                background_color="#FFFFFF",
                text_select=True,
                transparent=False,
                hidden=True,
            )

            new_window.events.closing += on_closing
            self._app_state.settings_window = new_window

            def show_smoothly() -> None:
                time.sleep(0.3)
                if self._app_state.settings_window:
                    self._app_state.settings_window.show()
                    self._window_manager.bring_to_foreground("Ozmoz Settings")

            threading.Thread(target=show_smoothly, daemon=True).start()

        except Exception as error:
            logging.critical(
                f"API: Error creating settings window: {error}", exc_info=True
            )

    def restart_settings_window(self) -> None:
        """
        Forces the settings window to be destroyed and recreated (useful when changing language).
        """
        if self._app_state.settings_window:
            self._app_state.settings_window.destroy()
            self._app_state.settings_window = None
            time.sleep(0.3)
            self.show_settings()

    # --- Audio & Transcription ---

    def start_recording(self) -> None:
        """
        Initiates the audio recording process.
        """
        self._audio_manager.start_recording()

    def stop_recording(self) -> None:
        """
        Stops the audio recording and triggers the transcription process.
        """
        self._transcription_manager.stop_recording_and_transcribe()

    # --- Models (AI & Config) ---

    def get_remote_config(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves the remote configuration for models.
        """
        if self._app_state.cached_remote_config is None:
            self._config_manager.load_and_parse_remote_config()
        return self._app_state.cached_remote_config

    def get_available_models(self) -> List[str]:
        """
        Returns a list of all available AI model IDs.
        """
        return self._config_manager.fetch_ai_models()

    def get_filtered_text_models(self) -> List[Dict[str, Any]]:
        """
        Filters and translates available text models for the UI.
        Prioritizes models based on available API keys and configuration.
        """
        logging.info(f"Retrieving text models (Language: {self._app_state.language})")

        available_model_ids = self._config_manager.fetch_ai_models()

        if not self._app_state.cached_remote_config:
            self._config_manager.load_and_parse_remote_config()
        if not self._app_state.cached_remote_config:
            return []

        final_models_list = []
        seen_families = set()

        credential_manager = self._config_manager.credential_manager
        has_any_key = bool(credential_manager.get_api_key("groq_ai")) or bool(
            credential_manager.get_api_key("cerebras")
        )

        for model_item in self._app_state.cached_remote_config:
            if "name" in model_item and isinstance(model_item.get("advantage"), dict):
                name = model_item["name"]
                family = model_item.get("family", name)

                # --- FILTERING LOGIC ---
                if has_any_key:
                    if name not in available_model_ids:
                        continue
                else:
                    if family in seen_families:
                        continue
                    seen_families.add(family)

                # --- DATA CONSTRUCTION ---
                advantage_data = model_item.get("advantage", {})
                translated_advantage = advantage_data.get(
                    self._app_state.language, advantage_data.get("en", "No description")
                )
                provider = model_item.get("provider", "groq")

                model_data = {
                    "id": name,
                    "name": name,
                    "advantage": translated_advantage,
                    "description": model_item.get("description", ""),
                    "is_multimodal": "vision"
                    in (advantage_data.get("en", "") or "").lower()
                    or name in self._app_state.screen_vision_model_list,
                    "is_web_model": name in self._app_state.tool_model_list
                    or "web" in (advantage_data.get("en", "") or "").lower(),
                    "provider": provider,
                    "family": family,
                }
                final_models_list.append(model_data)

        return final_models_list

    def get_translated_audio_models(self) -> List[Dict[str, str]]:
        """
        Translates descriptions for audio models based on the selected language.
        """
        if not self._app_state.cached_remote_config:
            self._config_manager.load_and_parse_remote_config()

        translated_models = []
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
                    self._app_state.language, advantage_data.get("en", "Standard")
                )

                translated_models.append(
                    {
                        "name": model_entry.get("name"),
                        "advantage": translated_advantage,
                        "provider": model_entry.get("provider", "groq"),
                    }
                )

        return translated_models

    def set_model(self, model_ai: str) -> Dict[str, bool]:
        """
        Sets the active AI model.
        """
        self._app_state.model = model_ai
        self._app_state.last_selected_model = model_ai

        self._config_manager.save_local_settings()
        logging.info(f"Model set: {self._app_state.model}")
        return {"success": True}

    def get_current_model(self) -> str:
        """
        Returns the ID of the currently selected AI model.
        """
        return self._app_state.model

    def set_audio_model(self, model_name: str) -> Dict[str, bool]:
        """
        Sets the active audio transcription model.
        """
        self._app_state.audio_model = model_name
        self._config_manager.save_local_settings()
        return {"success": True}

    def get_current_audio_model(self) -> str:
        """
        Returns the ID of the currently selected audio model.
        """
        return self._app_state.audio_model

    # --- AI Generation & Context ---

    def generate_ai_text(self) -> str:
        """
        Triggers the AI text generation process in a separate thread.
        """
        threading.Thread(
            target=self._ai_generation_manager.generate_ai_text, daemon=True
        ).start()
        return "Generating text..."

    def set_ai_response_visible(self, is_visible: bool) -> Dict[str, bool]:
        """
        Updates the visibility state of the AI response window.
        """
        self._app_state.is_ai_response_visible = bool(is_visible)
        if not self._app_state.is_ai_response_visible:
            self.clear_ai_context()
        return {"success": True}

    def clear_ai_context(self) -> Dict[str, bool]:
        """
        Clears the current AI conversation history.
        """
        self._app_state.conversation_history.clear()
        return {"success": True}

    # --- Language ---

    def set_language(self, language: str) -> Dict[str, Any]:
        """
        Sets the application language and adjusts audio models if necessary.
        """
        self._app_state.language = language

        # Languages supported by Nova-3
        nova3_supported_languages = {
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

        language_clean = language.lower().strip()
        language_base = language_clean.split("-")[0]

        # Downgrade to Nova-2 if the language is not supported by Nova-3
        if self._app_state.audio_model == "nova-3":
            if (
                language_clean not in nova3_supported_languages
                and language_base not in nova3_supported_languages
            ):
                self._app_state.audio_model = "nova-2"

        self._config_manager.save_local_settings()
        return {"success": True, "final_audio_model": self._app_state.audio_model}

    def get_current_language(self) -> str:
        """
        Returns the current application language code.
        """
        return self._app_state.language

    # --- Agents ---

    def get_agents(self) -> List[Dict[str, Any]]:
        """
        Loads and returns the list of configured agents.
        """
        return self._agent_manager.load_agents()

    def add_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adds a new agent to the configuration.
        """
        agents = self._agent_manager.load_agents()

        if (
            agent_data.get("model")
            and agent_data["model"] not in self._config_manager.fetch_ai_models()
        ):
            return {
                "success": False,
                "error": f"Model '{agent_data['model']}' unavailable",
            }

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
        return (
            {"success": True}
            if self._agent_manager.save_agents(agents)
            else {"success": False, "error": "Save failed"}
        )

    def update_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates an existing agent's configuration.
        """
        agents = self._agent_manager.load_agents()

        if (
            agent_data.get("model")
            and agent_data["model"] not in self._config_manager.fetch_ai_models()
        ):
            return {
                "success": False,
                "error": f"Model '{agent_data['model']}' unavailable",
            }

        for idx, agent in enumerate(agents):
            if agent.get("id") == agent_data.get("id"):
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
                return (
                    {"success": True}
                    if self._agent_manager.save_agents(agents)
                    else {"success": False, "error": "Save failed"}
                )

        return {"success": False, "error": "Agent not found"}

    def delete_agent(self, agent_id: str) -> bool:
        """
        Deletes an agent by its ID.
        """
        current_agents = self._agent_manager.load_agents()
        updated_agents = [a for a in current_agents if a["id"] != agent_id]
        return self._agent_manager.save_agents(updated_agents)

    def toggle_agent_status(self, agent_id: str, is_active: bool) -> Dict[str, Any]:
        """
        Enables or disables an agent.
        """
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
            return (
                {"success": True}
                if self._agent_manager.save_agents(agents)
                else {"success": False, "error": "Save failed"}
            )
        return {"success": False, "error": "Agent not found"}

    # --- History & Stats ---

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Retrieves the usage history.
        """
        return self._history_manager.get_all()

    def delete_history(self) -> bool:
        """
        Clears the usage history.
        """
        return self._history_manager.clear()

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """
        Retrieves formatted statistics for the dashboard.
        """
        return self._stats_manager.get_formatted_dashboard_stats()

    def get_activity_data(self, days: int = 7) -> Dict[str, Any]:
        """
        Retrieves activity chart data for the specified number of days.
        """
        return self._stats_manager.get_chart_data(days)

    def set_chart_type(self, type_str: str) -> Dict[str, Union[bool, str]]:
        """
        Sets the preferred chart type (line or bar).
        """
        if type_str in ["line", "bar"]:
            self._app_state.chart_type = type_str
            self._config_manager.save_local_settings()
            if self._app_state.settings_window:
                self._app_state.settings_window.evaluate_js(
                    "if (document.getElementById('home').classList.contains('active')) { loadActivityChartData(); }"
                )
            return {"success": True}
        return {"success": False, "error": "Invalid chart type"}

    def set_dashboard_period(
        self, days: Union[str, int]
    ) -> Dict[str, Union[bool, str]]:
        """
        Saves the dashboard period preference (7 or 30 days).
        """
        try:
            days_int = int(days)
            if days_int in [7, 30]:
                self._app_state.dashboard_period = days_int
                self._config_manager.save_local_settings()
                return {"success": True}
            return {"success": False, "error": "Invalid period value"}
        except Exception as error:
            return {"success": False, "error": str(error)}

    # --- Hotkeys ---

    def get_hotkeys(self) -> Dict[str, str]:
        """
        Returns the current hotkey configuration.
        """
        return self._app_state.hotkeys

    def temporarily_disable_all_hotkeys(self) -> Dict[str, Union[bool, str]]:
        """
        Temporarily unhooks all keyboard shortcuts (used when recording new hotkeys).
        """
        with self._app_state.keyboard_lock:
            try:
                import keyboard

                keyboard.unhook_all()
                time.sleep(0.1)
                return {"success": True}
            except Exception as error:
                logging.error(f"Disable hotkeys error: {error}")
                return {"success": False, "error": str(error)}

    def restore_all_hotkeys(self) -> Dict[str, Union[bool, str]]:
        """
        Re-registers all configured hotkeys.
        """
        try:
            self._hotkey_manager.register_all()
            return {"success": True}
        except Exception as error:
            return {"success": False, "error": str(error)}

    def set_hotkey(self, action_name: str, new_combination: str) -> Dict[str, Any]:
        """
        Updates a specific hotkey assignment.
        """
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
        """
        Checks if a new version of the application is available.
        """
        self._update_manager.fetch_remote_version_info()
        remote_version = self._app_state.remote_version

        try:
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
        """
        Starts the update download and installation process.
        """
        if not url:
            return {"success": False, "error": "Missing URL."}
        threading.Thread(target=self._update_worker, args=(url,), daemon=True).start()
        return {"success": True, "message": "Download started."}

    def _update_worker(self, url: str) -> None:
        """
        Background worker to download the update and launch the installer.
        """
        try:
            temp_dir = tempfile.gettempdir()
            file_path = os.path.join(temp_dir, url.split("/")[-1])

            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                downloaded_size = 0
                with open(file_path, "wb") as file_handle:
                    for chunk in response.iter_content(chunk_size=8192):
                        file_handle.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0 and self._app_state.settings_window:
                            self._app_state.settings_window.evaluate_js(
                                f"updateDownloadProgress({(downloaded_size/total_size)*100})"
                            )

            if self._app_state.settings_window:
                self._app_state.settings_window.evaluate_js("finalizeUpdate()")

            subprocess.Popen([file_path, "/SILENT"])
            time.sleep(3)
            self.request_exit()

        except Exception as error:
            if self._app_state.settings_window:
                msg = str(error).replace('"', "'").replace("\n", " ")
                self._app_state.settings_window.evaluate_js(
                    f'showUpdateError("Error: {msg}")'
                )

    # --- Logs & Dev Mode ---

    def set_developer_mode(self, state: bool) -> Dict[str, bool]:
        """
        Enables or disables developer mode.
        """
        self._app_state.developer_mode = bool(state)
        self._config_manager.save_local_settings()
        return {"success": True, "developer_mode": self._app_state.developer_mode}

    def get_developer_mode(self) -> Dict[str, bool]:
        """
        Returns the current status of developer mode.
        """
        return {"developer_mode": self._app_state.developer_mode}

    def get_logs(self) -> List[Dict[str, str]]:
        """
        Retrieves logs from the memory buffer if developer mode is active.
        """
        if not self._app_state.developer_mode:
            return [{"level": "WARNING", "message": "Developer mode disabled."}]

        handler: Any = getattr(self._app_state, "log_handler", None)
        if handler and hasattr(handler, "buffer"):
            return list(handler.buffer)

        return [{"level": "ERROR", "message": "Log handler not found."}]

    def clear_logs(self) -> Dict[str, Union[bool, str]]:
        """
        Clears the log buffer.
        """
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
            if not self._app_state.window:
                return {"success": False, "error": "Window not found"}

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            default_filename = f"ozmoz_logs_{timestamp}.txt"

            result = self._app_state.window.create_file_dialog(
                webview.SAVE_DIALOG, directory="/", save_filename=default_filename
            )

            if result:
                file_path: str = ""

                if isinstance(result, (list, tuple)):
                    if len(result) > 0:
                        file_path = str(result[0])
                elif isinstance(result, str):
                    file_path = result

                if file_path:
                    with open(file_path, "w", encoding="utf-8") as file_handle:
                        file_handle.write("\n".join(logs_to_export))

                    logging.info(f"Logs exported to: {file_path}")
                    return {"success": True, "path": file_path}

            return {"success": False, "message": "Cancelled"}

        except Exception as error:
            logging.error(f"Export logs error: {error}")
            return {"success": False, "error": str(error)}

    # --- Miscellaneous Features (Replacements, Sound, Web Search, OCR) ---

    def get_replacements(self) -> List[Dict[str, str]]:
        """
        Returns the list of configured text replacements.
        """
        return self._replacement_manager.load()

    def add_replacement(self, word1: str, word2: str) -> bool:
        """
        Adds a new text replacement pair.
        """
        replacements = self._replacement_manager.load()
        replacements.append({"word1": word1, "word2": word2})
        return self._replacement_manager.save(replacements)

    def delete_replacement(self, index: int) -> bool:
        """
        Deletes a text replacement by index.
        """
        replacements = self._replacement_manager.load()
        if 0 <= index < len(replacements):
            del replacements[index]
            return self._replacement_manager.save(replacements)
        return False

    def set_sound_enabled(self, state: bool) -> None:
        """
        Enables or disables application sounds.
        """
        self._app_state.sound_enabled = bool(state)
        self._config_manager.save_local_settings()

    def mute_sound(self, state: bool) -> None:
        """
        Mutes or unmutes sounds temporarily.
        """
        self._app_state.mute_sound = bool(state)
        self._config_manager.save_local_settings()

    # --- Utils ---

    def copy_text(self, text: str) -> str:
        """
        Copies the provided text to the system clipboard.
        """
        try:
            pyperclip.copy(text)
            return "Text copied"
        except Exception as error:
            return f"Error: {error}"

    def open_external_link(self, url: str) -> Dict[str, Union[bool, str]]:
        """
        Opens a URL in the default system browser.
        """
        try:
            webbrowser.open_new_tab(url)
            return {"success": True}
        except Exception as error:
            return {"success": False, "error": str(error)}

    # --- API Key Management ---

    def get_api_configuration(self) -> Dict[str, str]:
        """
        Sends existing keys to the frontend to pre-fill fields.
        """
        try:
            return self._config_manager.credential_manager.get_raw_keys_for_ui()
        except Exception as error:
            logging.error(f"Error in get_api_configuration: {error}")
            return {}

    def save_api_keys(self, data: Dict[str, str]) -> Dict[str, Union[bool, str]]:
        """
        Receives data from the settings form and saves API keys.
        data format: { 'api-key-groq-audio': '...', 'api-key-deepgram': '...', ... }
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
                value = data.get(html_id, "").strip()
                clean_data[internal_id] = value

            has_audio = bool(clean_data.get("groq_audio")) or bool(
                clean_data.get("deepgram")
            )

            if not has_audio:
                return {
                    "success": False,
                    "error": "Audio provider (Groq or Deepgram) is required for operation.",
                }

            success = self._config_manager.credential_manager.save_credentials(
                clean_data
            )

            if success:
                self._app_state.cached_models = None
                self._app_state.groq_client = None
                self._app_state.deepgram_client = None
                self._app_state.cerebras_client = None
                return {"success": True}
            else:
                return {"success": False, "error": "File write failed."}

        except Exception as error:
            logging.error(f"API save error: {error}")
            return {"success": False, "error": str(error)}

    def get_providers_status(self) -> Dict[str, bool]:
        """
        Returns the status of API keys to enable/disable UI options.
        """
        credential_manager = self._config_manager.credential_manager
        return {
            "groq_ai": bool(credential_manager.get_api_key("groq_ai")),
            "groq_audio": bool(credential_manager.get_api_key("groq_audio")),
            "cerebras": bool(credential_manager.get_api_key("cerebras")),
            "deepgram": bool(credential_manager.get_api_key("deepgram")),
        }
