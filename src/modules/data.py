import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import keyring
import requests
from cryptography.fernet import Fernet

# Internal imports
from modules.config import AppConfig, AppState, app_state
from modules.utils import PathManager

# Constants for file paths
SETTINGS_FILE: Path = PathManager.get_user_data_path("data/settings.json")
HISTORY_FILE: Path = PathManager.get_user_data_path("data/history.json")
REPLACEMENTS_FILE: Path = PathManager.get_user_data_path("data/replacements.json")
ACTIVITY_FILE: Path = PathManager.get_user_data_path("data/activity.json")
AGENTS_FILE: Path = PathManager.get_user_data_path("data/agents.json")


class CredentialManager:
    """
    Manages API keys via the native OS vault.
    Now also manages the Encryption Key for local data.
    """

    SERVICE_NAME: str = "OzmozApp"
    KNOWN_KEYS: List[str] = [
        "groq_audio",
        "deepgram",
        "groq_ai",
        "cerebras",
        "local_encryption_key",
    ]

    def __init__(self) -> None:
        self._cache: Dict[str, str] = {}
        self._load_from_os_store()

    def _load_from_os_store(self) -> None:
        for key_name in self.KNOWN_KEYS:
            try:
                secret: Optional[str] = keyring.get_password(
                    self.SERVICE_NAME, key_name
                )
                if secret:
                    self._cache[key_name] = secret
            except Exception as error:
                logging.error(f"Error loading Keyring ({key_name}): {error}")

    def get_encryption_key(self) -> bytes:
        """
        Retrieves or generates the symmetric encryption key (Fernet).
        """
        key = self._cache.get("local_encryption_key")

        if not key:
            logging.info("Generating new local encryption key...")
            new_key = Fernet.generate_key().decode("utf-8")
            keyring.set_password(self.SERVICE_NAME, "local_encryption_key", new_key)
            self._cache["local_encryption_key"] = new_key
            key = new_key

        return key.encode("utf-8")

    def save_credentials(self, keys_dict: Dict[str, str]) -> bool:
        """
        Saves a dictionary of API keys to the OS vault and updates the cache.

        Args:
            keys_dict: A dictionary where keys are service names (e.g., 'groq_audio')
                       and values are the API keys.

        Returns:
            bool: True if saving was successful, False otherwise.
        """
        try:
            for key_name, key_value in keys_dict.items():
                val_stripped: str = key_value.strip() if key_value else ""

                if val_stripped:
                    # Update or add key
                    keyring.set_password(self.SERVICE_NAME, key_name, val_stripped)
                    self._cache[key_name] = val_stripped
                else:
                    # Remove key if value is empty
                    try:
                        current_val: Optional[str] = keyring.get_password(
                            self.SERVICE_NAME, key_name
                        )
                        if current_val:
                            keyring.delete_password(self.SERVICE_NAME, key_name)
                    except Exception:
                        pass  # Ignore errors during deletion

                    if key_name in self._cache:
                        del self._cache[key_name]

            logging.info("API keys saved to OS vault.")
            return True
        except Exception as error:
            logging.error(f"Error saving Keyring: {error}")
            return False

    def get_api_key(self, service_alias: str) -> Optional[str]:
        """
        Retrieves an API key based on a specific service alias or a generic category.

        Args:
            service_alias: The specific service ('deepgram', 'cerebras')
                           or category ('ai', 'audio_transcription').

        Returns:
            Optional[str]: The API key if found, otherwise None.
        """
        api_key: Optional[str] = None

        # 1. Routing logic for generic categories
        if service_alias == "ai":
            # Priority for text generation: Groq AI > Cerebras > Environment Variables
            api_key = self._cache.get("groq_ai") or self._cache.get("cerebras")
            if not api_key:
                api_key = os.getenv("GROQ_API_KEY") or os.getenv("AI_API_KEY")

        elif service_alias == "audio_transcription":
            # Priority for audio: Groq Audio > Deepgram
            api_key = self._cache.get("groq_audio") or self._cache.get("deepgram")

        # 2. Direct access by specific service name
        else:
            api_key = self._cache.get(service_alias)
            # Fallback to Environment Variables
            if not api_key:
                if service_alias == "deepgram":
                    api_key = os.getenv("DEEPGRAM_API_KEY")
                if service_alias == "groq_audio":
                    api_key = os.getenv("GROQ_API_KEY")
                if service_alias == "groq_ai":
                    api_key = os.getenv("GROQ_API_KEY")

        return api_key

    def get_all_keys_status(self) -> Dict[str, bool]:
        """
        Returns the presence status of keys for the UI (true/false),
        never exposing the actual keys here.
        """
        return {
            "groq_audio": bool(self._cache.get("groq_audio")),
            "deepgram": bool(self._cache.get("deepgram")),
            "groq_ai": bool(self._cache.get("groq_ai")),
            "cerebras": bool(self._cache.get("cerebras")),
        }

    def get_raw_keys_for_ui(self) -> Dict[str, str]:
        """
        Returns the actual keys for display in the settings input fields.
        """
        return {
            "api-key-groq-audio": self._cache.get("groq_audio", ""),
            "api-key-deepgram": self._cache.get("deepgram", ""),
            "api-key-groq-ai": self._cache.get("groq_ai", ""),
            "api-key-cerebras": self._cache.get("cerebras", ""),
        }


# --- Updates & Configuration ---


class UpdateManager:
    """Manages version checking via GitHub API."""

    @staticmethod
    def _compare_versions(version1: str, version2: str) -> int:
        """
        Compares two semantic version strings.

        Returns:
             1 if version1 > version2
            -1 if version1 < version2
             0 if equal
        """
        try:
            parts1 = [int(p) for p in version1.split(".")]
            parts2 = [int(p) for p in version2.split(".")]
        except (ValueError, AttributeError):
            return 0

        # Normalize length by padding with zeros
        max_length = max(len(parts1), len(parts2))
        parts1.extend([0] * (max_length - len(parts1)))
        parts2.extend([0] * (max_length - len(parts2)))

        for i in range(max_length):
            if parts1[i] > parts2[i]:
                return 1
            if parts1[i] < parts2[i]:
                return -1
        return 0

    def fetch_remote_version_info(self) -> None:
        """Fetches the latest version info from GitHub Releases."""
        if app_state.remote_version is not None:
            return

        try:
            logging.info(
                f"Checking updates via GitHub: {AppConfig.GITHUB_RELEASES_URL}"
            )
            response = requests.get(
                AppConfig.GITHUB_RELEASES_URL,
                headers={"Accept": "application/vnd.github+json"},
                timeout=5,
            )
            response.raise_for_status()

            data = response.json()
            # GitHub returns "tag_name": "v1.1.2". We strip the 'v'.
            latest_version = data.get("tag_name", "").lstrip("v")

            # Find the executable download URL in assets
            update_url = None
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".exe"):
                    update_url = asset.get("browser_download_url")
                    break

            # Fallback: link to release page if no exe found
            if not update_url:
                update_url = data.get("html_url")

            if latest_version:
                app_state.remote_version = latest_version
                app_state.remote_update_url = update_url

        except Exception as error:
            logging.error(f"Error checking GitHub version: {error}")

    def check_for_updates(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Checks if a newer version is available.

        Returns:
            Tuple containing: (update_available: bool, new_version: str, update_url: str)
        """
        self.fetch_remote_version_info()
        if not app_state.remote_version:
            return False, None, None

        if self._compare_versions(app_state.remote_version, AppConfig.VERSION) == 1:
            return True, app_state.remote_version, app_state.remote_update_url
        return False, None, None


class ConfigManager:
    """
    Manages application settings (loading/saving JSON) and
    retrieves available AI models from LOCAL configuration.
    """

    MODEL_LIST_KEYS: Dict[str, str] = {
        "advanced_models": "advanced_model_list",
        "tool_models": "tool_model_list",
        "web_search_models": "web_search_model_list",
        "screen_vision_models": "screen_vision_model_list",
    }

    def __init__(self) -> None:
        self.credential_manager: Optional[CredentialManager] = None

    def set_credential_manager(self, manager: CredentialManager) -> None:
        """Dependency injection for the credential manager."""
        self.credential_manager = manager

    def load_and_parse_remote_config(self) -> None:
        """Loads configuration from the local JSON file instead of remote."""
        if app_state.cached_remote_config:
            return

        try:
            # Path to local models.json (same directory as this file)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, "models.json")

            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                app_state.cached_remote_config = data

                # Map JSON lists to AppState attributes
                for item in data:
                    for json_key, app_attr in self.MODEL_LIST_KEYS.items():
                        if json_key in item:
                            setattr(app_state, app_attr, item[json_key])

                logging.info("Local models configuration loaded successfully.")
            else:
                logging.error(f"Configuration file not found: {config_path}")
                # Use empty fallback
                app_state.cached_remote_config = []

        except Exception as error:
            logging.error(f"Local config loading error: {error}")
            # Reset lists on error
            for app_attr in self.MODEL_LIST_KEYS.values():
                setattr(app_state, app_attr, [])

    def fetch_ai_models(self) -> List[str]:
        """
        Returns a list of available and enabled model IDs.
        Handles provider priority (Cerebras > Groq) using the 'family' field.
        """
        if app_state.cached_models:
            return app_state.cached_models

        try:
            # 1. Load config
            if not app_state.cached_remote_config:
                self.load_and_parse_remote_config()

            if not app_state.cached_remote_config:
                return []

            # 2. Check available keys
            if not self.credential_manager:
                return []

            cred_manager = self.credential_manager
            has_groq = bool(cred_manager.get_api_key("groq_ai"))
            has_cerebras = bool(cred_manager.get_api_key("cerebras"))

            selected_models_map: Dict[str, Dict] = {}

            for item in app_state.cached_remote_config:
                if "name" not in item or not isinstance(item.get("advantage"), dict):
                    continue

                provider = item.get("provider", "groq")
                family = item.get("family", item["name"])

                # Determine if we have the key for this provider
                is_key_present = (provider == "groq" and has_groq) or (
                    provider == "cerebras" and has_cerebras
                )

                if not is_key_present:
                    continue

                # Priority Logic: Prefer Cerebras if available for the same family
                if family not in selected_models_map:
                    selected_models_map[family] = item
                else:
                    current_selection = selected_models_map[family]
                    current_provider = current_selection.get("provider", "groq")

                    if current_provider == "groq" and provider == "cerebras":
                        selected_models_map[family] = item

            # Extract final IDs
            valid_models = [item["name"] for item in selected_models_map.values()]

            # Cache the result
            app_state.cached_models = valid_models
            return valid_models

        except Exception as error:
            logging.error(f"Error fetching AI models: {error}")
            return []

    def load_local_settings(self) -> None:
        """Loads settings from disk into the AppState."""
        with app_state.settings_file_lock:
            try:
                if os.path.exists(SETTINGS_FILE):
                    with open(SETTINGS_FILE, "r", encoding="utf-8") as file_handle:
                        app_state.settings = json.load(file_handle)
                else:
                    app_state.settings = self._get_default_settings()
                    self._save_settings_nolock()

                self._populate_state_from_settings()
            except Exception as error:
                logging.error(f"Error loading settings: {error}")
                app_state.settings = self._get_default_settings()
                self._populate_state_from_settings()

    def save_local_settings(self) -> None:
        """Saves current AppState to the settings file (thread-safe)."""
        with app_state.settings_file_lock:
            self._save_settings_nolock()

    def _get_default_settings(self) -> Dict[str, Any]:
        """Returns the default configuration dictionary."""
        return {
            "version": AppConfig.VERSION,
            "language": AppConfig.DEFAULT_LANGUAGE,
            "model": AppConfig.DEFAULT_AI_MODEL,
            "last_selected_model": AppConfig.DEFAULT_AI_MODEL,
            "audio_model": AppConfig.DEFAULT_AUDIO_MODEL,
            "mute_sound": True,
            "sound_enabled": True,
            "chart_type": "line",
            "dashboard_period": 7,
            "developer_mode": False,
            "stats": {
                "total_words": 0,
                "total_time": 0.0,
                "total_process_time": 0.0,
            },
            "hotkeys": AppConfig.DEFAULT_HOTKEYS.copy(),
        }

    def _populate_state_from_settings(self) -> None:
        """
        Updates the global AppState variables based on the loaded dictionary.
        This syncs the JSON data with the runtime objects.
        """
        settings_dict = app_state.settings

        # Set defaults if keys are missing
        for key, default in [
            ("language", AppConfig.DEFAULT_LANGUAGE),
            ("model", AppConfig.DEFAULT_AI_MODEL),
            ("audio_model", AppConfig.DEFAULT_AUDIO_MODEL),
            ("sound_enabled", True),
            ("mute_sound", True),
            ("chart_type", "line"),
        ]:
            settings_dict.setdefault(key, default)

        # Update global state attributes
        app_state.language = settings_dict["language"]
        app_state.model = settings_dict["model"]
        app_state.last_selected_model = settings_dict.get(
            "last_selected_model", settings_dict["model"]
        )
        app_state.audio_model = settings_dict["audio_model"]
        app_state.sound_enabled = settings_dict["sound_enabled"]
        app_state.mute_sound = settings_dict["mute_sound"]
        app_state.chart_type = settings_dict["chart_type"]
        app_state.dashboard_period = settings_dict.get("dashboard_period", 7)
        app_state.developer_mode = settings_dict.get("developer_mode", False)
        app_state.hotkeys = settings_dict.get(
            "hotkeys", AppConfig.DEFAULT_HOTKEYS.copy()
        )

    def _save_settings_nolock(self) -> None:
        """
        Internal method to save settings without re-acquiring the lock.
        Synchronizes runtime AppState back to the dictionary before saving.
        """
        try:
            settings_dict = app_state.settings
            settings_dict.update(
                {
                    "language": app_state.language,
                    "model": app_state.model,
                    "last_selected_model": app_state.last_selected_model,
                    "audio_model": app_state.audio_model,
                    "mute_sound": app_state.mute_sound,
                    "sound_enabled": app_state.sound_enabled,
                    "hotkeys": app_state.hotkeys,
                    "chart_type": app_state.chart_type,
                    "dashboard_period": app_state.dashboard_period,
                    "developer_mode": app_state.developer_mode,
                    "version": AppConfig.VERSION,
                }
            )

            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as file_handle:
                json.dump(settings_dict, file_handle, indent=4)
        except Exception as error:
            logging.error(f"Error saving settings: {error}")

    def check_if_model_is_multimodal(self, model_id: str) -> bool:
        """Checks if the given model ID supports vision capabilities."""
        if not app_state.cached_remote_config or not model_id:
            return False
        try:
            for item in app_state.cached_remote_config:
                if item.get("name") == model_id:
                    advantage = item.get("advantage", "")
                    description = (
                        advantage.get("en", "")
                        if isinstance(advantage, dict)
                        else advantage
                    )
                    if "vision" in str(description).lower():
                        return True
            return False
        except Exception:
            return False


# --- Data Management (JSON Files) ---


class ReplacementManager:
    """Manages text replacements loaded from a JSON file."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> List[Dict[str, str]]:
        """Loads replacement rules from the file."""
        if self.file_path.exists():
            try:
                return json.loads(self.file_path.read_text(encoding="utf-8")).get(
                    "replacements", []
                )
            except Exception:
                pass
        return []

    def save(self, replacements: List[Dict[str, str]]) -> bool:
        """Saves replacement rules to the file."""
        try:
            with open(self.file_path, "w", encoding="utf-8") as file_handle:
                json.dump({"replacements": replacements}, file_handle, indent=4)
            return True
        except Exception:
            return False


class HistoryManager:
    """
    Manages the history of transcribed or generated text.
    NOW SECURED: Data is encrypted at rest using Fernet (AES-128).
    """

    def __init__(
        self, history_file: Path, credential_manager: CredentialManager
    ) -> None:
        self.history_file = history_file
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        key = credential_manager.get_encryption_key()
        self.fernet = Fernet(key)

    def get_all(self) -> List[Dict[str, Any]]:
        """Retrieves and decrypts the full history list."""
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, "rb") as file_handle:
                file_content = file_handle.read()

            if not file_content:
                return []

            try:
                decrypted_content = self.fernet.decrypt(file_content)
                return json.loads(decrypted_content.decode("utf-8")).get("history", [])
            except Exception:
                logging.warning(
                    "History file appears to be plaintext. Migrating to encrypted storage..."
                )
                try:
                    plain_data = json.loads(file_content.decode("utf-8")).get(
                        "history", []
                    )
                    self.save_history(plain_data)
                    return plain_data
                except Exception as e:
                    logging.error(f"Failed to migrate history: {e}")
                    return []

        except Exception as e:
            logging.error(f"Error reading history: {e}")
            return []

    def save_history(self, history: List[Dict[str, Any]]) -> bool:
        """Helper to encrypt and save data."""
        try:
            json_str = json.dumps({"history": history}, indent=4)
            encrypted_data = self.fernet.encrypt(json_str.encode("utf-8"))

            with open(self.history_file, "wb") as file_handle:
                file_handle.write(encrypted_data)
            return True
        except Exception as e:
            logging.error(f"Error saving encrypted history: {e}")
            return False

    def add_entry(self, text: str) -> None:
        """Adds a new text entry to the history file (Encrypted)."""
        if not text:
            return
        try:
            history = self.get_all()
            new_entry = {
                "id": len(history) + 1,
                "text": text,
                "timestamp": int(time.time() * 1000),
            }
            history.insert(0, new_entry)

            if len(history) > 10000:
                history = history[:10000]

            self.save_history(history)

        except Exception as error:
            logging.error(f"History add error: {error}")

    def clear(self) -> bool:
        """Clears all history."""
        return self.save_history([])


class AgentManager:
    """Manages AI agent configurations."""

    def __init__(self, agents_file: Path, config_manager: ConfigManager) -> None:
        self.agents_file = agents_file
        self.config_manager = config_manager
        self.agents_file.parent.mkdir(parents=True, exist_ok=True)

    def load_agents(self) -> List[Dict[str, Any]]:
        """Loads agents and verifies their models are available."""
        if self.agents_file.exists():
            try:
                agents = json.loads(self.agents_file.read_text(encoding="utf-8")).get(
                    "agents", []
                )
                # Verify model availability for each agent
                available_models = self.config_manager.fetch_ai_models()
                for agent in agents:
                    if agent.get("model") and agent["model"] not in available_models:
                        agent["model"] = ""
                return agents
            except Exception:
                pass
        return []

    def save_agents(self, agents: List[Dict[str, Any]]) -> bool:
        """Saves the list of agents to disk."""
        try:
            with open(self.agents_file, "w", encoding="utf-8") as file_handle:
                json.dump({"agents": agents}, file_handle, indent=4)
            return True
        except Exception:
            return False


class StatsManager:
    """Manages usage statistics and activity logging."""

    def __init__(
        self, app_state: AppState, config_manager: ConfigManager, activity_file: Path
    ) -> None:
        self.app_state = app_state
        self.config_manager = config_manager
        self.activity_file = activity_file
        self.activity_file.parent.mkdir(parents=True, exist_ok=True)

    def _record_daily_activity(self, word_count: int) -> None:
        """Records word count for the current date."""
        today_str = date.today().strftime("%Y-%m-%d")
        activity_data: Dict[str, Any] = {"daily_activity": []}

        if self.activity_file.exists():
            try:
                activity_data = json.loads(
                    self.activity_file.read_text(encoding="utf-8")
                )
            except Exception:
                pass

        entries = activity_data.setdefault("daily_activity", [])
        entry = next((e for e in entries if e.get("date") == today_str), None)

        if entry:
            entry["words"] = entry.get("words", 0) + word_count
        else:
            entries.append({"date": today_str, "words": word_count})

        try:
            with open(self.activity_file, "w", encoding="utf-8") as file_handle:
                json.dump(activity_data, file_handle, indent=2)
        except Exception:
            pass

    def update_stats(
        self,
        transcribed_text: str,
        audio_duration: float,
        process_duration: float = 0.0,
        is_generation: bool = False,
    ) -> None:
        """Updates total statistics (words, time) based on usage."""
        if not transcribed_text:
            return

        word_count = len(transcribed_text.split())
        if word_count == 0:
            return

        try:
            self._record_daily_activity(word_count)
            stats = self.app_state.settings.setdefault("stats", {})
            stats["total_words"] = stats.get("total_words", 0) + word_count
            stats["total_time"] = stats.get("total_time", 0.0) + audio_duration
            stats["total_process_time"] = (
                stats.get("total_process_time", 0.0) + process_duration
            )

            self.config_manager.save_local_settings()
        except Exception as error:
            logging.error(f"Stats error: {error}")

    def get_formatted_dashboard_stats(self) -> Dict[str, Union[int, float]]:
        """Calculates derived stats like Words Per Minute (WPM) and time saved."""
        stats = self.app_state.settings.get("stats", {})
        total_words = stats.get("total_words", 0)
        total_time = stats.get("total_time", 0.0)

        # Derived calculations
        # WPM = Words / (Minutes)
        wpm = (total_words / (total_time / 60.0)) if total_time > 0 else 0

        # Estimate: 40 WPM typing speed vs actual speaking time
        time_saved = (
            (total_words / 40.0) - (total_time / 60.0) if total_words > 0 else 0
        )

        return {
            "total_words": total_words,
            "average_speed": round(wpm),
            "time_saved": round(max(0, time_saved), 2),
        }

    def get_chart_data(self, days: int = 7) -> Dict[str, Any]:
        """Prepares data for the activity chart over the specified number of days."""
        results = {}
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        activity_log: Dict[str, Any] = {}
        if self.activity_file.exists():
            try:
                activity_log = json.loads(
                    self.activity_file.read_text(encoding="utf-8")
                )
            except Exception:
                pass

        daily_map = {
            e.get("date"): e.get("words", 0)
            for e in activity_log.get("daily_activity", [])
        }

        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            results[date_str] = daily_map.get(date_str, 0)
            current += timedelta(days=1)

        return {"data": results, "type": self.app_state.chart_type}
