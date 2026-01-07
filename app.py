"""
Main Application Entry Point for Ozmoz.

This module initializes the application lifecycle, dependency injection container,
and the main GUI loop using pywebview.

It utilizes a performance logging mechanism during imports to track startup latency.
"""

import logging
import time
from typing import Dict, Optional

# --- Performance Logging Setup ---
# We track import times to optimize startup performance.
START_TIME = time.perf_counter()


def log_performance_step(step_name: str) -> None:
    """
    Logs the time elapsed since the script execution started.

    Args:
        step_name (str): A descriptive label for the performance checkpoint.
    """
    elapsed = time.perf_counter() - START_TIME
    logging.info(f"[PERF] {elapsed:.4f}s - {step_name}")


log_performance_step("Script start")

import os  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
from pathlib import Path  # noqa: E402

log_performance_step("Native imports finished")

import webview  # noqa: E402
import win32api  # noqa: E402
import win32event  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

log_performance_step("Heavy third-party imports finished (webview, win32)")

# --- Path Setup ---
# Ensure the 'src' directory is in the python path to allow module resolution.
current_directory: str = os.path.dirname(os.path.abspath(__file__))
src_directory_path: str = os.path.join(current_directory, "src")
sys.path.insert(0, src_directory_path)

# --- Local Modules ---
# Imports are delayed until after path setup to ensure modules are found.
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
from modules.ui import (  # noqa: E402
    SystemTrayManager,
    UIResourceLoader,
    WindowManager,
)
from modules.utils import (  # noqa: E402
    ClipboardManager,
    PathManager,
    ScreenManager,
    SoundManager,
)

log_performance_step("Local module imports finished")

# --- Environment Configuration ---
# Suppress PyGame welcome message and Qt logging spam
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.environ["QT_LOGGING_RULES"] = "qt.qpa.window=false"


class OzmozApp:
    """
    Main application controller.

    Responsibilities:
    1. Orchestrates the initialization of all subsystems (Audio, UI, Data).
    2. Manages the Dependency Injection (DI) graph.
    3. Handles the application lifecycle (Startup, Running, Shutdown).
    """

    def __init__(self) -> None:
        """
        Initializes the application instance.

        Sets up logging, paths, and injects dependencies into managers.
        """
        log_performance_step("OzmozApp.__init__ start")

        # 1. Initialize Logging
        setup_logging()

        # 2. Define Critical File Paths
        self.paths: Dict[str, Path] = {
            "settings": PathManager.get_user_data_path("data/settings.json"),
            "history": PathManager.get_user_data_path("data/history.json"),
            "replacements": PathManager.get_user_data_path("data/replacements.json"),
            "activity": PathManager.get_user_data_path("data/activity.json"),
            "agents": PathManager.get_user_data_path("data/agents.json"),
        }

        logging.info(f"Ozmoz v{AppConfig.VERSION} - Initializing application...")

        # --- Layer 1: Core Infrastructure ---
        self.event_bus = EventBus()
        self.os_adapter = WindowsAdapter()

        log_performance_step("Core Infrastructure initialized")

        # --- Layer 2: Data & Utilities ---
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
        self.history_manager = HistoryManager(
            history_file=self.paths["history"],
            credential_manager=self.credential_manager,
        )
        self.stats_manager = StatsManager(
            app_state=app_state,
            config_manager=self.config_manager,
            activity_file=self.paths["activity"],
        )

        self.ui_resource_loader = UIResourceLoader(app_state)

        log_performance_step("Data Managers initialized")

        # --- Layer 3: System Adapters ---
        self.window_manager = WindowManager(app_state, self.os_adapter)

        self.audio_manager = AudioManager(
            app_state, self.sound_manager, self.os_adapter
        )

        log_performance_step("Audio & Window Managers initialized")

        # --- Layer 4: Audio & Transcription Services ---
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

        log_performance_step("Transcription Services initialized")

        self.context_manager = ContextManager(app_state=app_state)
        self.agent_manager = AgentManager(
            agents_file=self.paths["agents"],
            config_manager=self.config_manager,
        )

        # --- Layer 5: Business Logic Controllers ---
        self.generation_controller = GenerationController(
            app_state=app_state,
            window=None,  # Window injected later
            audio_manager=self.audio_manager,
            sound_manager=self.sound_manager,
            transcription_manager=self.transcription_manager,
            stats_manager=self.stats_manager,
            system_health_manager=None,  # Injected later (Circular dependency)
            hotkey_manager=None,  # Injected later
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

        log_performance_step("AI Controllers initialized")

        # --- Layer 6: Input & System Health ---
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

        # Resolve Circular Dependencies
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

        # --- Layer 7: API & UI Integration ---
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

        log_performance_step("System & Hotkeys initialized")

        self.mutex_handle: Optional[int] = None

        log_performance_step("OzmozApp.__init__ end")

    def _execute_startup_sequence(self) -> None:
        """
        Executes background initialization tasks after the UI is ready.

        Tasks:
        - Initialize and warmup audio subsystems.
        - Fetch remote configurations.
        - Warmup AI services.
        - Open settings window if previously open.
        """
        log_performance_step("Background: Initializing Audio & Sound...")
        self.audio_manager.initialize()
        self.sound_manager._initialize()
        self.lifecycle_manager.run_background_startup_tasks()

        # Warmup critical paths to reduce first-usage latency
        self.audio_manager.warmup()
        self.transcription_service.warmup()
        self.generation_controller.warmup()

        # Allow UI to render before heavy checks
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
        Starts the main application loop.

        Steps:
        1. Enforce single instance via Mutex.
        2. Load environment and resources.
        3. Initialize Windows and System Tray.
        4. Start background threads (Power monitor, Hotkeys).
        5. Launch the blocking Webview loop.
        """
        log_performance_step("OzmozApp.run start")

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

            self.system_tray_manager.run_in_thread()
            time.sleep(0.2)

            log_performance_step("System Tray started")

            # Create Main Toolbar Window
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

            log_performance_step("Main Window created")

            # Create Settings Window (Hidden by default)
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
                """Intercepts settings close event to hide instead of destroy."""
                if app_state.is_exiting:
                    return True
                settings_window.hide()
                return False

            settings_window.events.closing += on_settings_closing
            app_state.settings_window = settings_window

            log_performance_step("Settings Window created")

            # Start background initialization thread
            threading.Thread(target=self._execute_startup_sequence, daemon=True).start()

            self.power_monitor.start()
            self.hotkey_manager.register_all()

            # Start health monitor
            threading.Thread(
                target=self.system_health_manager.run_hotkey_health_monitor,
                args=(app_state.stop_app_event,),
                daemon=True,
            ).start()

            log_performance_step("Background threads started")

            logging.info("System ready. Starting UI loop.")

            log_performance_step("Starting Webview loop (Blocking)")
            webview.start(debug=False)

        except Exception as error:
            logging.critical(f"FATAL APPLICATION CRASH: {error}", exc_info=True)

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
    """Entry point for the script."""
    app = OzmozApp()
    app.run()


if __name__ == "__main__":
    main()
