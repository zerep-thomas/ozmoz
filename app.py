"""
Main Application Entry Point for Ozmoz.

This module initializes the application lifecycle, dependency injection container,
and the main GUI loop using pywebview.

Security features:
- Single instance enforcement via named mutex
- Path traversal protection for user data files
- Graceful degradation on component failures

Performance features:
- Lazy loading of heavy dependencies
- Performance tracking for startup optimization
- Background initialization to minimize perceived latency
"""

# Standard library imports
import logging
import os
import sys
import threading
import time
from pathlib import Path

# Type hints
from typing import Any, Dict, Optional

# --- Performance Logging Setup ---
# Track import times to identify and optimize startup bottlenecks.
START_TIME = time.perf_counter()

# Performance monitoring constants
PERF_LOG_PRECISION_SECONDS = 4  # Decimal places for performance logs


def log_performance_step(step_name: str) -> None:
    """
    Log elapsed time since script start for performance profiling.

    Used to identify slow initialization steps during application startup.
    Logs at DEBUG level to avoid cluttering production logs.

    Args:
        step_name: Descriptive label for the checkpoint (e.g., "Audio Manager init").

    Example:
        >>> log_performance_step("Database connection established")
        [PERF] 0.1234s - Database connection established
    """
    elapsed = time.perf_counter() - START_TIME
    logging.debug(f"[PERF] {elapsed:.{PERF_LOG_PRECISION_SECONDS}f}s - {step_name}")


log_performance_step("Script start")

# Third-party imports (heavy dependencies)
import webview  # noqa: E402
import win32api  # noqa: E402
import win32event  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

log_performance_step("Heavy third-party imports finished (webview, win32)")

# --- Path Setup ---
# Ensure 'src' directory is on Python path for module resolution.
# This allows importing from 'modules.*' without package installation.
current_directory: str = os.path.dirname(os.path.abspath(__file__))
src_directory_path: str = os.path.join(current_directory, "src")
sys.path.insert(0, src_directory_path)

# --- Local Application Imports ---
# Delayed until after path setup to ensure correct module resolution.
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
    AIGenerationManager,
    ContextManager,
    GenerationController,
    VisionManager,
    WebSearchManager,
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

# --- Configuration Constants ---
# UI Window dimensions (optimized for typical 1080p displays)
MAIN_WINDOW_WIDTH = 350
MAIN_WINDOW_HEIGHT = 138
SETTINGS_WINDOW_WIDTH = 1015
SETTINGS_WINDOW_HEIGHT = 650
SETTINGS_WINDOW_MIN_WIDTH = 744
SETTINGS_WINDOW_MIN_HEIGHT = 534

# Timing constants
# Allow UI compositor to fully render before heavy operations
UI_SETTLE_DELAY_SECONDS = 2.5
# Brief pause to ensure system tray icon renders before continuing
SYSTEM_TRAY_INIT_DELAY_SECONDS = 0.2

# UI Colors
WINDOW_BACKGROUND_COLOR = "#FFFFFF"


class ApplicationInitializationError(Exception):
    """Raised when critical application components fail to initialize."""


class OzmozApp:
    """
    Main application controller and dependency injection container.

    Responsibilities:
    1. Orchestrate initialization of all subsystems in correct dependency order
    2. Manage application lifecycle (startup, running, shutdown)
    3. Provide centralized access to all managers and services
    4. Enforce single-instance execution via mutex

    The initialization follows a layered approach:
    - Layer 1: Core infrastructure (EventBus, OS adapters)
    - Layer 2: Data managers and utilities
    - Layer 3: System adapters (Audio, Windows)
    - Layer 4: Audio and transcription services
    - Layer 5: Business logic controllers
    - Layer 6: Input handling and system health
    - Layer 7: API and UI integration

    Attributes:
        paths: Dictionary mapping data file purposes to secure filesystem paths
        event_bus: Central event dispatcher for loosely-coupled components
        mutex_handle: Win32 mutex handle for single-instance enforcement

    Raises:
        ApplicationInitializationError: If critical components fail to initialize
        RuntimeError: If application is already running (mutex check)
    """

    def __init__(self) -> None:
        """
        Initialize application and all subsystems.

        Constructs the complete dependency graph, ensuring each component
        receives all required dependencies. Follows strict initialization
        order to prevent accessing uninitialized components.

        Raises:
            ApplicationInitializationError: If any manager fails to initialize
        """
        log_performance_step("OzmozApp.__init__ start")

        # 1. Initialize Logging
        setup_logging()

        # 2. Validate and secure critical file paths
        self.paths: Dict[str, Path] = self._initialize_secure_paths()

        logging.info(f"Ozmoz v{AppConfig.VERSION} - Initializing application...")

        # --- Layer 1: Core Infrastructure ---
        self.event_bus: EventBus = EventBus()
        self.os_adapter: WindowsAdapter = WindowsAdapter()

        log_performance_step("Core Infrastructure initialized")

        # --- Layer 2: Data & Utilities ---
        self._initialize_data_layer()
        log_performance_step("Data Managers initialized")

        # --- Layer 3: System Adapters ---
        self._initialize_system_adapters()
        log_performance_step("Audio & Window Managers initialized")

        # --- Layer 4: Audio & Transcription Services ---
        self._initialize_transcription_services()
        log_performance_step("Transcription Services initialized")

        self.context_manager: ContextManager = ContextManager(app_state=app_state)
        self.agent_manager: AgentManager = AgentManager(
            agents_file=self.paths["agents"],
            config_manager=self.config_manager,
        )

        # --- Layer 5: Business Logic Controllers ---
        self._initialize_business_controllers()
        log_performance_step("AI Controllers initialized")

        # --- Layer 6: Input & System Health ---
        self._initialize_system_health()
        log_performance_step("System & Hotkeys initialized")

        # --- Layer 7: API & UI Integration ---
        self._initialize_ui_layer()

        # Mutex handle for single-instance enforcement (initialized in run())
        self.mutex_handle: Optional[Any] = None

        log_performance_step("OzmozApp.__init__ end")

    def _initialize_secure_paths(self) -> Dict[str, Path]:
        """
        Initialize and validate all user data file paths.

        Ensures paths are within expected user data directory to prevent
        path traversal attacks if PathManager is compromised.

        Returns:
            Dictionary mapping logical names to validated Path objects.

        Raises:
            ApplicationInitializationError: If paths are invalid or inaccessible.
        """
        try:
            base_data_dir = PathManager.get_user_data_path("data")

            paths = {
                "settings": PathManager.get_user_data_path("data/settings.json"),
                "history": PathManager.get_user_data_path("data/history.json"),
                "replacements": PathManager.get_user_data_path(
                    "data/replacements.json"
                ),
                "activity": PathManager.get_user_data_path("data/activity.json"),
                "agents": PathManager.get_user_data_path("data/agents.json"),
            }

            # Validate all paths are within the expected data directory
            for name, path in paths.items():
                resolved_path = path.resolve()
                if not resolved_path.is_relative_to(base_data_dir.resolve()):
                    raise ApplicationInitializationError(
                        f"Security violation: {name} path outside data directory: {resolved_path}"
                    )

            return paths

        except (OSError, ValueError) as e:
            raise ApplicationInitializationError(
                f"Failed to initialize secure paths: {e}"
            ) from e

    def _initialize_data_layer(self) -> None:
        """
        Initialize all data managers and utility services.

        Order matters: CredentialManager must be created before ConfigManager
        since ConfigManager depends on it for encrypted settings.
        """
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
            app_state_ref=app_state,
            config_manager=self.config_manager,
            activity_file=self.paths["activity"],
        )

        self.ui_resource_loader = UIResourceLoader(app_state)

    def _initialize_system_adapters(self) -> None:
        """Initialize OS-level adapters for window and audio management."""
        self.window_manager = WindowManager(app_state, self.os_adapter)  # type: ignore[arg-type]
        self.audio_manager = AudioManager(
            app_state, self.sound_manager, self.os_adapter
        )

    def _initialize_transcription_services(self) -> None:
        """
        Initialize audio transcription pipeline.

        Sets up the service layer for converting audio to text,
        including replacement rules and history tracking.
        """
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
            clipboard_manager=self.clipboard_manager,
            event_bus=self.event_bus,
        )

    def _initialize_business_controllers(self) -> None:
        """
        Initialize AI and business logic controllers.

        Note: Some dependencies (system_health_manager, hotkey_manager) are
        injected later to break circular dependencies.
        """
        self.generation_controller = GenerationController(
            app_state=app_state,
            window=None,  # Injected after webview window creation
            audio_manager=self.audio_manager,
            sound_manager=self.sound_manager,
            transcription_manager=self.transcription_manager,
            stats_manager=self.stats_manager,
            system_health_manager=None,  # Circular dependency - injected later
            hotkey_manager=None,  # Circular dependency - injected later
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

        self.ai_generation_manager = AIGenerationManager(
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

    def _initialize_system_health(self) -> None:
        """
        Initialize input handling and system monitoring.

        Resolves circular dependencies by injecting managers after creation.
        """
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

        # Resolve circular dependencies
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

    def _initialize_ui_layer(self) -> None:
        """Initialize API bridge and system tray integration."""
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

    def _execute_startup_sequence(self) -> None:
        """
        Execute background initialization tasks after UI is ready.

        Runs in separate thread to avoid blocking the main UI loop.
        Tasks include:
        - Audio subsystem initialization and warmup
        - Remote configuration fetching
        - AI service warmup (reduces first-use latency)
        - Restore previous settings window state

        This is run after a delay to allow the UI to render first,
        improving perceived startup performance.
        """
        try:
            log_performance_step("Background: Initializing Audio & Sound...")

            self.audio_manager.initialize()
            self.sound_manager._initialize()
            self.lifecycle_manager.run_background_startup_tasks()

            # Warmup critical paths to reduce first-usage latency
            # These operations load models/libraries into memory
            self.audio_manager.warmup()
            self.transcription_service.warmup()
            self.generation_controller.warmup()

            # Allow UI compositor to fully render before heavy checks
            # This delay ensures the main window is visible before we
            # potentially show the settings window on top
            time.sleep(UI_SETTLE_DELAY_SECONDS)

            # Restore settings window if it was open on last shutdown
            if app_state.ui.settings_window:
                logging.info("Restoring settings window from previous session")
                app_state.ui.settings_window.show()
                try:
                    self.window_manager.bring_to_foreground("Ozmoz Settings")
                except Exception as e:
                    logging.warning(
                        f"Failed to bring settings window to foreground: {e}"
                    )

        except Exception as e:
            logging.error(
                "Background startup sequence failed",
                exc_info=True,
                extra={"error": str(e)},
            )
            # Don't crash the app - background init failures are non-critical

    def _create_main_window(self) -> Any:
        """
        Create the main toolbar window.

        Returns:
            Webview window instance.

        Raises:
            RuntimeError: If window creation fails.
        """
        try:
            return webview.create_window(
                "Ozmoz",
                html=self.ui_resource_loader.create_html("src/templates/index.html"),
                js_api=self.api,
                width=MAIN_WINDOW_WIDTH,
                height=MAIN_WINDOW_HEIGHT,
                resizable=True,
                frameless=True,
                easy_drag=True,
                background_color=WINDOW_BACKGROUND_COLOR,
                text_select=True,
                transparent=False,
                hidden=True,  # Start hidden, shown after initialization
                on_top=True,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create main window: {e}") from e

    def _create_settings_window(self) -> Any:
        """
        Create the settings window with close event handler.

        The close handler prevents window destruction, instead hiding it
        so it can be quickly reshown without reinitializing.

        Returns:
            Webview window instance.

        Raises:
            RuntimeError: If window creation fails.
        """
        try:
            settings_window = webview.create_window(
                "Ozmoz Settings",
                html=self.ui_resource_loader.create_html("src/templates/settings.html"),
                js_api=self.api,
                width=SETTINGS_WINDOW_WIDTH,
                height=SETTINGS_WINDOW_HEIGHT,
                min_size=(SETTINGS_WINDOW_MIN_WIDTH, SETTINGS_WINDOW_MIN_HEIGHT),
                resizable=True,
                frameless=False,
                easy_drag=True,
                background_color=WINDOW_BACKGROUND_COLOR,
                text_select=True,
                transparent=False,
                hidden=True,  # Hidden by default, shown on user request
            )

            def on_settings_closing() -> bool:
                """
                Handle settings window close event.

                Instead of destroying the window, we hide it to preserve
                state and enable fast reopening.

                Returns:
                    True to allow closing during app shutdown,
                    False to prevent destruction during normal operation.
                """
                if app_state.is_exiting:
                    return True  # Allow destruction during shutdown

                settings_window.hide()
                return False  # Prevent destruction, just hide

            settings_window.events.closing += on_settings_closing
            return settings_window

        except Exception as e:
            raise RuntimeError(f"Failed to create settings window: {e}") from e

    def _cleanup_resources(self) -> None:
        """
        Clean up all application resources.

        Called during shutdown to ensure proper resource disposal.
        Failures are logged but don't prevent shutdown.
        """
        logging.info("Cleaning up application resources...")

        try:
            if hasattr(self, "lifecycle_manager"):
                self.lifecycle_manager.cleanup_resources()
        except Exception as e:
            logging.error(f"Lifecycle manager cleanup failed: {e}", exc_info=True)

        # Release mutex to allow future instances
        if self.mutex_handle:
            try:
                win32event.ReleaseMutex(self.mutex_handle)
                win32api.CloseHandle(self.mutex_handle)
                logging.debug("Mutex released successfully")
            except Exception as e:
                logging.warning(f"Failed to release mutex: {e}")

    def run(self) -> None:
        """
        Start the main application event loop.

        Execution flow:
        1. Enforce single instance via Win32 mutex
        2. Load environment variables and user settings
        3. Initialize UI resources and windows
        4. Start background services (system tray, power monitor, hotkeys)
        5. Launch blocking webview event loop
        6. Clean up resources on exit

        Raises:
            SystemExit: If another instance is already running.
        """
        log_performance_step("OzmozApp.run start")

        # Enforce single instance
        try:
            self.mutex_handle = self.os_adapter.create_single_instance_mutex(
                AppConfig.MUTEX_ID
            )
        except RuntimeError as e:
            logging.warning(f"Application already running: {e}")
            sys.exit(0)

        logging.info(f"Ozmoz v{AppConfig.VERSION} starting...")
        load_dotenv()

        try:
            # Load UI templates and user configuration
            self.ui_resource_loader.load_html_content()
            self.config_manager.load_local_settings()

            # Start system tray in background thread
            self.system_tray_manager.run_in_thread()
            # Brief pause to ensure tray icon renders
            time.sleep(SYSTEM_TRAY_INIT_DELAY_SECONDS)

            log_performance_step("System Tray started")

            # Create main toolbar window
            main_window = self._create_main_window()
            app_state.ui.window = main_window
            self.generation_controller.window = main_window

            log_performance_step("Main Window created")

            # Create settings window (hidden initially)
            settings_window = self._create_settings_window()
            app_state.ui.settings_window = settings_window

            log_performance_step("Settings Window created")

            # Start background initialization in separate thread
            # This allows the UI to render while we warm up services
            threading.Thread(
                target=self._execute_startup_sequence,
                daemon=True,
                name="StartupSequence",
            ).start()

            # Start system monitors
            self.power_monitor.start()
            self.hotkey_manager.register_all()

            # Start health monitoring for hotkey recovery
            threading.Thread(
                target=self.system_health_manager.run_hotkey_health_monitor,
                args=(app_state.threading.stop_app_event,),
                daemon=True,
                name="HealthMonitor",
            ).start()

            log_performance_step("Background threads started")

            logging.info("System ready. Starting UI event loop.")
            log_performance_step("Starting Webview loop (Blocking)")

            # This call blocks until all windows are closed
            webview.start(debug=False)

        except KeyboardInterrupt:
            logging.info("Shutdown requested via keyboard interrupt")
        except Exception as error:
            logging.critical(
                "Fatal application crash",
                exc_info=True,
                extra={"error": str(error)},
            )
        finally:
            self._cleanup_resources()
            logging.info("Application shutdown complete. Goodbye.")


def main() -> None:
    """
    Application entry point.

    Creates and runs the main application instance.
    All initialization and cleanup is handled by OzmozApp.
    """
    app = OzmozApp()
    app.run()


if __name__ == "__main__":
    main()
