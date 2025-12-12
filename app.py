import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional

import webview
import win32api
import win32event
from dotenv import load_dotenv

# --- Path Setup ---
current_dir: str = os.path.dirname(os.path.abspath(__file__))
src_path: str = os.path.join(current_dir, "src")
sys.path.insert(0, src_path)

# --- Local Modules ---
from modules.api import API  # noqa: E402
from modules.audio import (  # noqa: E402
    AudioManager,
    TranscriptionManager,
    TranscriptionService,
)
from modules.config import AppConfig, app_state, setup_logging  # noqa: E402
from modules.data import (  # noqa: E402
    AgentManager,
    ConfigManager,
    CredentialManager,
    HistoryManager,
    ReplacementManager,
    StatsManager,
    UpdateManager,
)
from modules.os_adapter import WindowsAdapter  # noqa: E402
from modules.services import (  # noqa: E402
    ContextManager,
    GenerationController,
    VisionManager,
    WebSearchManager,
    aiGenerationManager,
)
from modules.system import (  # noqa: E402
    AppLifecycleManager,
    EventBus,
    HotkeyManager,
    SystemHealthManager,
    SystemPowerMonitor,
)
from modules.ui import SystemTrayManager, UIResourceLoader, WindowManager  # noqa: E402
from modules.utils import (  # noqa: E402
    ClipboardManager,
    PathManager,
    ScreenManager,
    SoundManager,
)

# --- Environment Configuration ---
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.environ["QT_LOGGING_RULES"] = "qt.qpa.window=false"


class OzmozApp:
    """
    Main application class.
    Handles component initialization, dependency injection, lifecycle, and execution.
    """

    def __init__(self) -> None:
        """
        Initialize the application components, managers, and services.
        Sets up the dependency injection graph.
        """
        # 1. Logging setup
        setup_logging()

        # 2. Path definitions
        self.paths: Dict[str, Path] = {
            "settings": PathManager.get_user_data_path("data/settings.json"),
            "history": PathManager.get_user_data_path("data/history.json"),
            "replacements": PathManager.get_user_data_path("data/replacements.json"),
            "activity": PathManager.get_user_data_path("data/activity.json"),
            "agents": PathManager.get_user_data_path("data/agents.json"),
        }

        logging.info(f"Ozmoz v{AppConfig.VERSION} - Initializing application...")

        # --- Core Infrastructure ---
        self.event_bus = EventBus()
        self.os_adapter = WindowsAdapter()

        # 3. Data & Utilities Initialization
        self.credential_manager = CredentialManager()
        self.config_manager = ConfigManager()
        self.config_manager.set_credential_manager(self.credential_manager)

        self.sound_manager = SoundManager()
        self.update_manager = UpdateManager()
        self.screen_manager = ScreenManager()
        self.clipboard_manager = ClipboardManager()

        self.replacement_manager = ReplacementManager(
            file_path=self.paths["replacements"]
        )
        self.history_manager = HistoryManager(history_file=self.paths["history"])
        self.stats_manager = StatsManager(
            app_state=app_state,
            config_manager=self.config_manager,
            activity_file=self.paths["activity"],
        )

        self.ui_resource_loader = UIResourceLoader(app_state)

        # Inject OS Interface into Managers
        self.window_manager = WindowManager(app_state, self.os_adapter)

        self.audio_manager = AudioManager(
            app_state, self.sound_manager, self.os_adapter
        )

        # 4. Audio & Transcription Services
        self.transcription_service = TranscriptionService(
            app_state=app_state,
            replacement_manager=self.replacement_manager,
            credential_manager=self.credential_manager,
        )

        self.transcription_manager = TranscriptionManager(
            app_state=app_state,
            audio_manager=self.audio_manager,
            sound_manager=self.sound_manager,
            stats_manager=self.stats_manager,
            history_manager=self.history_manager,
            transcription_service=self.transcription_service,
            event_bus=self.event_bus,
        )

        self.context_manager = ContextManager(app_state=app_state)
        self.agent_manager = AgentManager(
            agents_file=self.paths["agents"], config_manager=self.config_manager
        )

        # 5. Controllers & Intelligence Logic
        self.generation_controller = GenerationController(
            app_state=app_state,
            window=None,
            audio_manager=self.audio_manager,
            sound_manager=self.sound_manager,
            transcription_manager=self.transcription_manager,
            stats_manager=self.stats_manager,
            system_health_manager=None,
            hotkey_manager=None,
            config_manager=self.config_manager,
            credential_manager=self.credential_manager,
        )

        self.vision_manager = VisionManager(
            app_state=app_state,
            config_manager=self.config_manager,
            screen_manager=self.screen_manager,
            transcription_service=self.transcription_service,
            stats_manager=self.stats_manager,
            history_manager=self.history_manager,
            credential_manager=self.credential_manager,
            generation_controller=self.generation_controller,
        )

        self.web_search_manager = WebSearchManager(
            app_state=app_state,
            config_manager=self.config_manager,
            transcription_service=self.transcription_service,
            stats_manager=self.stats_manager,
            history_manager=self.history_manager,
            clipboard_manager=self.clipboard_manager,
            generation_controller=self.generation_controller,
        )

        self.ai_generation_manager = aiGenerationManager(
            app_state=app_state,
            config_manager=self.config_manager,
            context_manager=self.context_manager,
            transcription_service=self.transcription_service,
            stats_manager=self.stats_manager,
            history_manager=self.history_manager,
            clipboard_manager=self.clipboard_manager,
            screen_manager=self.screen_manager,
            agent_manager=self.agent_manager,
            credential_manager=self.credential_manager,
            generation_controller=self.generation_controller,
        )

        # 6. System & Hotkeys
        self.hotkey_manager = HotkeyManager(
            app_state=app_state,
            window_manager=self.window_manager,
            audio_manager=self.audio_manager,
            transcription_manager=self.transcription_manager,
        )

        self.hotkey_manager.set_managers(
            ai_gen=self.ai_generation_manager,
            web_search=self.web_search_manager,
            vision=self.vision_manager,
        )

        self.system_health_manager = SystemHealthManager(
            app_state=app_state,
            audio_manager=self.audio_manager,
            hotkey_manager=self.hotkey_manager,
            window_manager=self.window_manager,
        )

        # Final injection for circular dependencies
        self.generation_controller.system_health_manager = self.system_health_manager
        self.generation_controller.hotkey_manager = self.hotkey_manager

        self.lifecycle_manager = AppLifecycleManager(
            app_state=app_state,
            config_manager=self.config_manager,
            audio_manager=self.audio_manager,
            window_manager=self.window_manager,
        )

        self.power_monitor = SystemPowerMonitor(
            on_resume_callback=self.hotkey_manager.system_resume_handler
        )

        # 7. API & System Tray
        self.api = API(
            app_state=app_state,
            config_manager=self.config_manager,
            window_manager=self.window_manager,
            audio_manager=self.audio_manager,
            transcription_manager=self.transcription_manager,
            hotkey_manager=self.hotkey_manager,
            replacement_manager=self.replacement_manager,
            update_manager=self.update_manager,
            stats_manager=self.stats_manager,
            history_manager=self.history_manager,
            agent_manager=self.agent_manager,
            ai_generation_manager=self.ai_generation_manager,
            ui_resource_loader=self.ui_resource_loader,
        )

        self.system_tray_manager = SystemTrayManager(
            app_state,
            self.hotkey_manager,
            self.api.show_settings,
            self.api.request_exit,
        )

        self.mutex_handle: Optional[int] = None

    def _startup_sequence(self) -> None:
        """
        Execute background tasks after UI initialization.
        Warms up services and opens settings if configured.
        """
        self.lifecycle_manager.run_background_startup_tasks()
        self.audio_manager.warmup()
        self.transcription_service.warmup()
        self.generation_controller.warmup()
        time.sleep(2.5)

        if app_state.settings_window:
            logging.info("Opening settings window.")
            app_state.settings_window.show()
            try:
                self.window_manager.bring_to_foreground("Ozmoz Settings")
            except Exception:
                pass

    def run(self) -> None:
        """
        Main execution entry point:
        - Single instance check
        - UI & Config loading
        - Window creation
        - Thread starting
        - Webview loop start
        """
        try:
            self.mutex_handle = self.os_adapter.create_single_instance_mutex(
                AppConfig.MUTEX_ID
            )
        except RuntimeError:
            logging.warning("Application already running. Exiting.")
            sys.exit(0)

        logging.info(f"Ozmoz v{AppConfig.VERSION} starting...")
        load_dotenv()

        try:
            self.ui_resource_loader.load_html_content()
            self.config_manager.load_local_settings()

            self.audio_manager.initialize()
            self.sound_manager._initialize()

            self.system_tray_manager.run_in_thread()
            time.sleep(0.2)

            main_window = webview.create_window(
                "Ozmoz",
                html=self.ui_resource_loader.create_html("src/templates/index.html"),
                js_api=self.api,
                width=350,
                height=138,
                resizable=True,
                frameless=True,
                easy_drag=True,
                background_color="#ffffff",
                text_select=True,
                transparent=False,
                hidden=True,
                on_top=True,
            )
            app_state.window = main_window
            self.generation_controller.window = main_window

            settings_window = webview.create_window(
                "Ozmoz Settings",
                html=self.ui_resource_loader.create_html("src/templates/settings.html"),
                js_api=self.api,
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

            def on_settings_closing() -> bool:
                if app_state.is_exiting:
                    return True
                settings_window.hide()
                return False

            settings_window.events.closing += on_settings_closing
            app_state.settings_window = settings_window

            threading.Thread(target=self._startup_sequence, daemon=True).start()

            self.power_monitor.start()
            self.hotkey_manager.register_all()

            threading.Thread(
                target=self.system_health_manager.run_hotkey_health_monitor,
                args=(app_state.stop_app_event,),
                daemon=True,
            ).start()

            logging.info("System ready. Starting UI loop.")
            webview.start(debug=True)

        except Exception as e:
            logging.critical(f"FATAL APPLICATION CRASH: {e}", exc_info=True)

        finally:
            logging.info("Stopping application...")
            if hasattr(self, "lifecycle_manager"):
                self.lifecycle_manager.cleanup_resources()

            if self.mutex_handle:
                try:
                    win32event.ReleaseMutex(self.mutex_handle)
                    win32api.CloseHandle(self.mutex_handle)
                except Exception:
                    pass
            logging.info("Bye.")


def main() -> None:
    app = OzmozApp()
    app.run()


if __name__ == "__main__":
    main()
