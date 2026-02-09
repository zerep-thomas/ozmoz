"""
Data Management Module for Ozmoz.

This module handles persistent storage and retrieval of application data, including:
- Credential Management (API Keys via System Keyring).
- Configuration Management (Settings JSON).
- Data Persistence (History with Encryption, Agents, Replacements).
- Statistics Tracking (Activity logging).
- Update Checking (GitHub API).
"""

import json
import logging
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# --- Third-Party Imports ---
import keyring
import requests
from cryptography.fernet import Fernet

# --- Local Imports ---
from modules.config import AppConfig, AppState, app_state
from modules.utils import PathManager

# --- Constants ---
SERVICE_NAME = "OzmozApp"
DEFAULT_ENCODING = "utf-8"

# File Paths
SETTINGS_FILE = PathManager.get_user_data_path("data/settings.json")
HISTORY_FILE = PathManager.get_user_data_path("data/history.json")
REPLACEMENTS_FILE = PathManager.get_user_data_path("data/replacements.json")
ACTIVITY_FILE = PathManager.get_user_data_path("data/activity.json")
AGENTS_FILE = PathManager.get_user_data_path("data/agents.json")

# Limits & Defaults
MAX_HISTORY_ENTRIES = 10000
HTTP_TIMEOUT_SECONDS = 10
GITHUB_API_HEADERS = {"Accept": "application/vnd.github+json"}

# Stats Defaults
DEFAULT_WPM_TYPING_SPEED = 40.0
STATS_DEFAULT_PERIOD_DAYS = 7

# Logger
logger = logging.getLogger(__name__)


class DataError(Exception):
    """Base class for data management exceptions."""


class EncryptionError(DataError):
    """Raised when encryption/decryption fails."""


class CredentialManager:
    """
    Manages sensitive credentials using the operating system's native keyring service.
    Also manages the local symmetric encryption key for securing history data.
    """

    KNOWN_KEYS: List[str] = [
        "groq_audio",
        "deepgram",
        "groq_ai",
        "cerebras",
        "local_encryption_key",
    ]

    def __init__(self) -> None:
        """Initialize the manager and load existing keys into memory cache."""
        self._credential_cache: Dict[str, str] = {}
        self._load_from_os_store()

    def _load_from_os_store(self) -> None:
        """Loads known keys from the system keyring into the internal cache."""
        for key_name in self.KNOWN_KEYS:
            try:
                secret: Optional[str] = keyring.get_password(SERVICE_NAME, key_name)
                if secret:
                    self._credential_cache[key_name] = secret
            except Exception as error:
                logger.error(
                    "failed_to_load_credential",
                    extra={"key": key_name, "error": str(error)},
                )

    def get_encryption_key(self) -> bytes:
        """
        Retrieves or generates the symmetric encryption key (Fernet).

        Returns:
            bytes: The encryption key.

        Note:
            If keyring fails, this generates an ephemeral key. Data persisted
            with an ephemeral key will be lost upon application restart.
        """
        key = self._credential_cache.get("local_encryption_key")

        if not key:
            logger.info("generating_new_encryption_key")
            new_key = Fernet.generate_key().decode("utf-8")
            try:
                keyring.set_password(SERVICE_NAME, "local_encryption_key", new_key)
                self._credential_cache["local_encryption_key"] = new_key
                key = new_key
            except Exception as error:
                logger.critical(
                    "encryption_key_save_failed",
                    extra={
                        "error": str(error),
                        "impact": "Data will be lost on restart",
                    },
                )
                # Fallback to ephemeral key (Warning: Data persistence is broken)
                return Fernet.generate_key()

        return key.encode("utf-8")

    def save_credentials(self, keys_dict: Dict[str, str]) -> bool:
        """
        Saves a dictionary of API keys to the OS vault and updates the cache.

        Args:
            keys_dict: Map of service names to API keys.

        Returns:
            bool: True if saving was successful, False otherwise.
        """
        try:
            for key_name, key_value in keys_dict.items():
                sanitized_value: str = key_value.strip() if key_value else ""

                if sanitized_value:
                    # Update or add key
                    keyring.set_password(SERVICE_NAME, key_name, sanitized_value)
                    self._credential_cache[key_name] = sanitized_value
                else:
                    # Remove key if value is empty
                    self._delete_credential(key_name)

            logger.info("credentials_saved_to_vault")
            return True
        except Exception as error:
            logger.error("credential_save_failed", extra={"error": str(error)})
            return False

    def _delete_credential(self, key_name: str) -> None:
        """Safe deletion of a credential from keyring and cache."""
        try:
            current_val: Optional[str] = keyring.get_password(SERVICE_NAME, key_name)
            if current_val:
                keyring.delete_password(SERVICE_NAME, key_name)
        except Exception as e:
            logger.warning(
                "credential_deletion_error", extra={"key": key_name, "error": str(e)}
            )

        if key_name in self._credential_cache:
            del self._credential_cache[key_name]

    def get_api_key(self, service_alias: str) -> Optional[str]:
        """
        Retrieves an API key based on a specific service alias or a generic category.

        Priority:
        1. System Keyring (Cached)
        2. Environment Variables

        Args:
            service_alias: The specific service ('deepgram', 'cerebras')
                           or category ('ai', 'audio_transcription').

        Returns:
            Optional[str]: The API key if found, otherwise None.
        """
        api_key: Optional[str] = None

        # 1. Routing logic for generic categories
        if service_alias == "ai":
            api_key = (
                self._credential_cache.get("groq_ai")
                or self._credential_cache.get("cerebras")
                or os.getenv("GROQ_API_KEY")
                or os.getenv("AI_API_KEY")
            )

        elif service_alias == "audio_transcription":
            api_key = self._credential_cache.get(
                "groq_audio"
            ) or self._credential_cache.get("deepgram")

        # 2. Direct access by specific service name
        else:
            api_key = self._credential_cache.get(service_alias)

            # Fallback to Environment Variables
            if not api_key:
                env_map = {
                    "deepgram": "DEEPGRAM_API_KEY",
                    "groq_audio": "GROQ_API_KEY",
                    "groq_ai": "GROQ_API_KEY",
                }
                if env_var := env_map.get(service_alias):
                    api_key = os.getenv(env_var)

        return api_key

    def get_all_keys_status(self) -> Dict[str, bool]:
        """
        Returns the presence status of keys for the UI (true/false).

        Returns:
            Dict[str, bool]: Status map (True if key exists).
        """
        return {
            key: bool(self._credential_cache.get(key))
            for key in ["groq_audio", "deepgram", "groq_ai", "cerebras"]
        }

    def get_raw_keys_for_ui(self) -> Dict[str, str]:
        """
        Returns the actual keys for display in the settings input fields.

        Returns:
            Dict[str, str]: Map of HTML input IDs to key values.
        """
        return {
            "api-key-groq-audio": self._credential_cache.get("groq_audio", ""),
            "api-key-deepgram": self._credential_cache.get("deepgram", ""),
            "api-key-groq-ai": self._credential_cache.get("groq_ai", ""),
            "api-key-cerebras": self._credential_cache.get("cerebras", ""),
        }


class UpdateManager:
    """Manages application version checking via GitHub API."""

    @staticmethod
    def _compare_versions(version_a: str, version_b: str) -> int:
        """
        Compares two semantic version strings.

        Args:
            version_a: First version string (e.g., "1.0.0").
            version_b: Second version string.

        Returns:
             1 if version_a > version_b
            -1 if version_a < version_b
             0 if equal
        """
        try:
            parts_a = [int(p) for p in version_a.split(".")]
            parts_b = [int(p) for p in version_b.split(".")]
        except (ValueError, AttributeError):
            return 0

        max_length = max(len(parts_a), len(parts_b))
        parts_a.extend([0] * (max_length - len(parts_a)))
        parts_b.extend([0] * (max_length - len(parts_b)))

        for i in range(max_length):
            if parts_a[i] > parts_b[i]:
                return 1
            if parts_a[i] < parts_b[i]:
                return -1
        return 0

    def fetch_remote_version_info(self) -> None:
        """Fetches the latest version info from GitHub Releases and caches it."""
        if app_state.remote_version is not None:
            return

        try:
            logger.info(
                "checking_updates", extra={"url": AppConfig.GITHUB_RELEASES_URL}
            )

            response = requests.get(
                AppConfig.GITHUB_RELEASES_URL,
                headers=GITHUB_API_HEADERS,
                timeout=HTTP_TIMEOUT_SECONDS,
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

            if not update_url:
                update_url = data.get("html_url")

            if latest_version:
                app_state.remote_version = latest_version
                app_state.remote_update_url = update_url

        except requests.RequestException as error:
            logger.warning("update_check_failed", extra={"error": str(error)})
        except Exception as error:
            logger.error("update_check_error", extra={"error": str(error)})

    def check_for_updates(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Checks if a newer version is available.

        Returns:
            Tuple: (update_available, new_version, update_url)
        """
        self.fetch_remote_version_info()

        current_version = AppConfig.VERSION
        remote_version = app_state.remote_version

        if not remote_version:
            return False, None, None

        if self._compare_versions(remote_version, current_version) == 1:
            return True, remote_version, app_state.remote_update_url

        return False, None, None


class ConfigManager:
    """
    Manages application settings (loading/saving JSON) and
    retrieves available AI models from the local configuration file.
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
        """Loads configuration from the local 'models.json' file."""
        if app_state.cached_remote_config:
            return

        try:
            current_dir = Path(__file__).parent.resolve()
            config_path = current_dir / "models.json"

            if config_path.exists():
                with open(config_path, "r", encoding=DEFAULT_ENCODING) as f:
                    data = json.load(f)

                app_state.cached_remote_config = data

                for item in data:
                    for json_key, app_attr in self.MODEL_LIST_KEYS.items():
                        if json_key in item:
                            setattr(app_state, app_attr, item[json_key])

                logger.info("local_models_config_loaded")
            else:
                logger.error("config_file_not_found", extra={"path": str(config_path)})
                app_state.cached_remote_config = []

        except Exception as error:
            logger.error("config_loading_error", extra={"error": str(error)})
            for app_attr in self.MODEL_LIST_KEYS.values():
                setattr(app_state, app_attr, [])

    def fetch_ai_models(self) -> List[str]:
        """
        Returns a list of available and enabled model IDs.
        """
        if app_state.models.cached_models:
            return app_state.models.cached_models

        try:
            if not app_state.cached_remote_config:
                self.load_and_parse_remote_config()

            if not app_state.cached_remote_config or not self.credential_manager:
                return []

            has_groq = bool(self.credential_manager.get_api_key("groq_ai"))
            has_cerebras = bool(self.credential_manager.get_api_key("cerebras"))

            selected_models_map: Dict[str, Dict] = {}

            for item in app_state.cached_remote_config:
                if "name" not in item or not isinstance(item.get("advantage"), dict):
                    continue

                provider = item.get("provider", "groq")
                family = item.get("family", item["name"])

                is_key_present = (provider == "groq" and has_groq) or (
                    provider == "cerebras" and has_cerebras
                )

                if not is_key_present:
                    continue

                # Priority Logic: Prefer Cerebras if available
                if family not in selected_models_map:
                    selected_models_map[family] = item
                else:
                    current = selected_models_map[family]
                    if current.get("provider") == "groq" and provider == "cerebras":
                        selected_models_map[family] = item

            valid_models = [item["name"] for item in selected_models_map.values()]
            app_state.models.cached_models = valid_models
            return valid_models

        except Exception as error:
            logger.error("fetch_ai_models_error", extra={"error": str(error)})
            return []

    def load_local_settings(self) -> None:
        """Loads settings from disk into the AppState."""
        with app_state.threading.settings_file_lock:
            try:
                if SETTINGS_FILE.exists():
                    with open(SETTINGS_FILE, "r", encoding=DEFAULT_ENCODING) as f:
                        app_state.settings = json.load(f)
                else:
                    app_state.settings = self._get_default_settings()
                    self._save_settings_nolock()

                self._populate_state_from_settings()
            except Exception as error:
                logger.error("settings_load_error", extra={"error": str(error)})
                app_state.settings = self._get_default_settings()
                self._populate_state_from_settings()

    def save_local_settings(self) -> None:
        """Saves current AppState to the settings file (thread-safe)."""
        with app_state.threading.settings_file_lock:
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
            "dashboard_period": STATS_DEFAULT_PERIOD_DAYS,
            "developer_mode": False,
            "stats": {
                "total_words": 0,
                "total_time": 0.0,
                "total_process_time": 0.0,
            },
            "hotkeys": AppConfig.DEFAULT_HOTKEYS.copy(),
        }

    def _populate_state_from_settings(self) -> None:
        """Syncs the JSON dictionary with runtime AppState objects."""
        settings = app_state.settings
        defaults = self._get_default_settings()

        for key, default_val in defaults.items():
            if key not in settings:
                settings[key] = default_val

        app_state.models.language = settings["language"]
        app_state.models.model = settings["model"]
        app_state.models.last_selected_model = settings.get(
            "last_selected_model", settings["model"]
        )
        app_state.models.audio_model = settings["audio_model"]
        app_state.audio.sound_enabled = settings["sound_enabled"]
        app_state.audio.mute_sound = settings["mute_sound"]
        app_state.ui.chart_type = settings["chart_type"]
        app_state.ui.dashboard_period = settings.get(
            "dashboard_period", STATS_DEFAULT_PERIOD_DAYS
        )
        app_state.developer_mode = settings.get("developer_mode", False)
        app_state.hotkeys = settings.get("hotkeys", AppConfig.DEFAULT_HOTKEYS.copy())

    def _save_settings_nolock(self) -> None:
        """Atomic save of settings without re-acquiring the lock."""
        try:
            settings_dict = app_state.settings
            settings_dict.update(
                {
                    "language": app_state.models.language,
                    "model": app_state.models.model,
                    "last_selected_model": app_state.models.last_selected_model,
                    "audio_model": app_state.models.audio_model,
                    "mute_sound": app_state.audio.mute_sound,
                    "sound_enabled": app_state.audio.sound_enabled,
                    "hotkeys": app_state.hotkeys,
                    "chart_type": app_state.ui.chart_type,
                    "dashboard_period": app_state.ui.dashboard_period,
                    "developer_mode": app_state.developer_mode,
                    "version": AppConfig.VERSION,
                }
            )

            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write pattern
            tmp_file = SETTINGS_FILE.with_suffix(".tmp")
            with open(tmp_file, "w", encoding=DEFAULT_ENCODING) as f:
                json.dump(settings_dict, f, indent=4)
            tmp_file.replace(SETTINGS_FILE)

        except Exception as error:
            logger.error("settings_save_error", extra={"error": str(error)})

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


class ReplacementManager:
    """Manages text replacements loaded from a JSON file."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> List[Dict[str, str]]:
        """Loads replacement rules from the file."""
        if self.file_path.exists():
            try:
                content = self.file_path.read_text(encoding=DEFAULT_ENCODING)
                return json.loads(content).get("replacements", [])
            except Exception as error:
                logger.warning("replacements_load_warning", extra={"error": str(error)})
        return []

    def save(self, replacements: List[Dict[str, str]]) -> bool:
        """Saves replacement rules to the file."""
        try:
            tmp_file = self.file_path.with_suffix(".tmp")
            with open(tmp_file, "w", encoding=DEFAULT_ENCODING) as f:
                json.dump({"replacements": replacements}, f, indent=4)
            tmp_file.replace(self.file_path)
            return True
        except Exception as error:
            logger.error("replacements_save_error", extra={"error": str(error)})
            return False


class HistoryManager:
    """
    Manages the history of transcribed or generated text.
    Security: Data is encrypted at rest using Fernet (AES-128).
    Thread-safe implementation for concurrent writes.
    """

    def __init__(
        self, history_file: Path, credential_manager: CredentialManager
    ) -> None:
        self.history_file = history_file
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.fernet = Fernet(credential_manager.get_encryption_key())
        self._lock = threading.Lock()

    def get_all(self) -> List[Dict[str, Any]]:
        """Retrieves and decrypts the full history list."""
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, "rb") as f:
                file_content = f.read()

            if not file_content:
                return []

            try:
                decrypted_content = self.fernet.decrypt(file_content)
                return json.loads(decrypted_content.decode(DEFAULT_ENCODING)).get(
                    "history", []
                )
            except Exception:
                logger.warning("decryption_failed_migrating_plaintext")
                # Attempt to read as plaintext (migration path)
                try:
                    plain_data = json.loads(file_content.decode(DEFAULT_ENCODING)).get(
                        "history", []
                    )
                    self.save_history(plain_data)
                    return plain_data
                except Exception as e:
                    logger.error("history_migration_failed", extra={"error": str(e)})
                    return []

        except Exception as e:
            logger.error("history_read_error", extra={"error": str(e)})
            return []

    def save_history(self, history: List[Dict[str, Any]]) -> bool:
        """Encrypts and saves history data securely."""
        with self._lock:
            try:
                json_str = json.dumps({"history": history}, indent=4)
                encrypted_data = self.fernet.encrypt(json_str.encode(DEFAULT_ENCODING))

                tmp_file = self.history_file.with_suffix(".tmp")
                with open(tmp_file, "wb") as f:
                    f.write(encrypted_data)
                tmp_file.replace(self.history_file)
                return True
            except Exception as e:
                logger.error("history_save_error", extra={"error": str(e)})
                return False

    def add_entry(self, text: str) -> None:
        """
        Adds a new text entry to the history file.
        Uses a lock to prevent race conditions during read-modify-write.
        """
        if not text:
            return

        # We need the lock to span the read AND write to avoid lost updates
        with self._lock:
            try:
                # 1. Read directly inside lock (simulating get_all behavior but under lock)
                history = []
                if self.history_file.exists():
                    with open(self.history_file, "rb") as f:
                        file_content = f.read()
                    if file_content:
                        try:
                            decrypted = self.fernet.decrypt(file_content)
                            history = json.loads(
                                decrypted.decode(DEFAULT_ENCODING)
                            ).get("history", [])
                        except Exception:
                            # Fallback logic simplified for lock context
                            try:
                                history = json.loads(
                                    file_content.decode(DEFAULT_ENCODING)
                                ).get("history", [])
                            except Exception:
                                history = []

                # 2. Modify
                new_entry = {
                    "id": len(history) + 1,
                    "text": text,
                    "timestamp": int(time.time() * 1000),
                }
                history.insert(0, new_entry)

                if len(history) > MAX_HISTORY_ENTRIES:
                    history = history[:MAX_HISTORY_ENTRIES]

                # 3. Write
                json_str = json.dumps({"history": history}, indent=4)
                encrypted_data = self.fernet.encrypt(json_str.encode(DEFAULT_ENCODING))

                tmp_file = self.history_file.with_suffix(".tmp")
                with open(tmp_file, "wb") as f:
                    f.write(encrypted_data)
                tmp_file.replace(self.history_file)

            except Exception as error:
                logger.error("history_add_entry_error", extra={"error": str(error)})

    def clear(self) -> bool:
        """Clears all history."""
        return self.save_history([])


class AgentManager:
    """Manages AI agent configurations stored in JSON."""

    def __init__(self, agents_file: Path, config_manager: ConfigManager) -> None:
        self.agents_file = agents_file
        self.config_manager = config_manager
        self.agents_file.parent.mkdir(parents=True, exist_ok=True)

    def load_agents(self) -> List[Dict[str, Any]]:
        """Loads agents and validates their models."""
        if self.agents_file.exists():
            try:
                content = self.agents_file.read_text(encoding=DEFAULT_ENCODING)
                agents = json.loads(content).get("agents", [])

                available_models = self.config_manager.fetch_ai_models()
                for agent in agents:
                    if agent.get("model") and agent["model"] not in available_models:
                        agent["model"] = ""
                return agents
            except Exception as e:
                logger.warning("agents_load_warning", extra={"error": str(e)})
        return []

    def save_agents(self, agents: List[Dict[str, Any]]) -> bool:
        """Saves the list of agents to disk."""
        try:
            tmp_file = self.agents_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding=DEFAULT_ENCODING) as f:
                json.dump({"agents": agents}, f, indent=4)
            tmp_file.replace(self.agents_file)
            return True
        except Exception as e:
            logger.error("agents_save_error", extra={"error": str(e)})
            return False


class StatsManager:
    """Manages usage statistics and daily activity logging."""

    def __init__(
        self,
        app_state_ref: AppState,
        config_manager: ConfigManager,
        activity_file: Path,
    ) -> None:
        self.app_state = app_state_ref
        self.config_manager = config_manager
        self.activity_file = activity_file
        self.activity_file.parent.mkdir(parents=True, exist_ok=True)

    def _record_daily_activity(self, word_count: int) -> None:
        """Records word count for the current date in the activity file."""
        today_str = date.today().strftime("%Y-%m-%d")
        activity_data: Dict[str, Any] = {"daily_activity": []}

        if self.activity_file.exists():
            try:
                content = self.activity_file.read_text(encoding=DEFAULT_ENCODING)
                activity_data = json.loads(content)
            except Exception:
                pass  # Start fresh on corruption

        entries = activity_data.setdefault("daily_activity", [])

        # Optimize search using next with default
        entry = next((e for e in entries if e.get("date") == today_str), None)

        if entry:
            entry["words"] = entry.get("words", 0) + word_count
        else:
            entries.append({"date": today_str, "words": word_count})

        try:
            tmp_file = self.activity_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding=DEFAULT_ENCODING) as f:
                json.dump(activity_data, f, indent=2)
            tmp_file.replace(self.activity_file)
        except Exception as e:
            logger.error("daily_stats_save_error", extra={"error": str(e)})

    def update_stats(
        self,
        transcribed_text: str,
        audio_duration: float,
        process_duration: float = 0.0,
        is_generation: bool = False,
    ) -> None:
        """Updates cumulative statistics (total words, time)."""
        if not transcribed_text:
            return

        word_count = len(transcribed_text.split())
        if word_count == 0:
            return

        try:
            self._record_daily_activity(word_count)

            with self.app_state.threading.settings_file_lock:
                stats = self.app_state.settings.setdefault("stats", {})
                stats["total_words"] = stats.get("total_words", 0) + word_count
                stats["total_time"] = stats.get("total_time", 0.0) + audio_duration
                stats["total_process_time"] = (
                    stats.get("total_process_time", 0.0) + process_duration
                )
                self.config_manager._save_settings_nolock()

        except Exception as error:
            logger.error("stats_update_error", extra={"error": str(error)})

    def get_formatted_dashboard_stats(self) -> Dict[str, Union[int, float]]:
        """Calculates derived stats for the UI dashboard."""
        stats = self.app_state.settings.get("stats", {})
        total_words = stats.get("total_words", 0)
        total_time_seconds = stats.get("total_time", 0.0)

        minutes = total_time_seconds / 60.0
        # Avoid division by zero
        wpm = (total_words / minutes) if minutes > 0 else 0

        # Saved = (Time to type) - (Time to speak)
        typing_minutes_estimated = total_words / DEFAULT_WPM_TYPING_SPEED
        time_saved_minutes = (
            typing_minutes_estimated - minutes if total_words > 0 else 0
        )

        return {
            "total_words": total_words,
            "average_speed": round(wpm),
            "time_saved": round(max(0, time_saved_minutes), 2),
        }

    def get_chart_data(self, days: int = STATS_DEFAULT_PERIOD_DAYS) -> Dict[str, Any]:
        """Prepares activity data for the frontend chart."""
        results = {}
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        activity_log: Dict[str, Any] = {}
        if self.activity_file.exists():
            try:
                content = self.activity_file.read_text(encoding=DEFAULT_ENCODING)
                activity_log = json.loads(content)
            except Exception:
                pass

        daily_map = {
            e.get("date"): e.get("words", 0)
            for e in activity_log.get("daily_activity", [])
        }

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            results[date_str] = daily_map.get(date_str, 0)
            current_date += timedelta(days=1)

        return {"data": results, "type": self.app_state.ui.chart_type}
