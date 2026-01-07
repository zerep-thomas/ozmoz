"""
UI Management Module for Ozmoz.

This module handles:
- Loading and processing of static resources (HTML, CSS, JS, Fonts).
- Dynamic injection of assets into web templates.
- Window management (Show, Hide, Move, Focus) via OS adapters.
- System Tray integration using PySide6 (Qt).
"""

import base64
import logging
import os
import re
import sys
import threading
import webbrowser
from typing import Any, Callable, Dict, List, Match, Optional, cast

# --- Qt Framework Imports ---
from PySide6.QtCore import QEvent, QTimer
from PySide6.QtGui import QCursor, QEnterEvent, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

# --- Local Application Imports ---
from modules.config import AppState, app_state
from modules.utils import PathManager


class UIResourceLoader:
    """
    Manages the loading, localization, and injection of UI assets.

    It handles reading files from disk, bundling modular JavaScript files into
    a single script for the frontend, and embedding fonts/images as Base64
    to ensure the UI works within a constrained webview environment.
    """

    def __init__(self, app_state_instance: AppState) -> None:
        """
        Initialize the resource loader.

        Args:
            app_state_instance (AppState): The global application state object.
        """
        self._app_state: AppState = app_state_instance
        self.resources: Dict[str, str] = {
            "index_css": "",
            "index_js": "",
            "settings_css": "",
            "settings_js": "",
            "fonts_css": "",
        }

        # Font configuration for the application (OpenSauceSans)
        self.font_config: List[Dict[str, Any]] = [
            {"file": "OpenSauceSans-Light.ttf", "weight": 300},
            {"file": "OpenSauceSans-Regular.ttf", "weight": 400},
            {"file": "OpenSauceSans-Medium.ttf", "weight": 500},
            {"file": "OpenSauceSans-SemiBold.ttf", "weight": 600},
            {"file": "OpenSauceSans-Bold.ttf", "weight": 700},
            {"file": "OpenSauceSans-ExtraBold.ttf", "weight": 800},
            {"file": "OpenSauceSans-Black.ttf", "weight": 900},
        ]

    def _read_resource_file(self, relative_path: str) -> str:
        """
        Safely reads a text resource file from the disk.

        Args:
            relative_path (str): Path relative to the application root.

        Returns:
            str: The content of the file, or an empty string if reading fails.
        """
        try:
            full_path: str = PathManager.get_resource_path(relative_path)
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as file_handle:
                    return file_handle.read()
            else:
                logging.warning(f"UI Resource not found: {relative_path}")
                return ""
        except Exception as error:
            logging.error(f"Error reading resource '{relative_path}': {error}")
            return ""

    def _bundle_es6_modules(self, file_paths: List[str]) -> str:
        """
        Simulates a JavaScript bundler.

        Reads multiple ES6 files, strips 'import'/'export' statements to make
        them compatible with a standard browser environment (without <script type="module">),
        and concatenates them.

        Args:
            file_paths (List[str]): List of relative file paths to bundle.

        Returns:
            str: The concatenated JavaScript source code.
        """
        bundled_content: List[str] = []
        for file_path in file_paths:
            content: str = self._read_resource_file(file_path)

            # Strip ES6 module syntax
            content = re.sub(r"^\s*import .*?;", "", content, flags=re.MULTILINE)
            content = re.sub(r"^\s*export\s+", "", content, flags=re.MULTILINE)

            bundled_content.append(
                f"\n/* --- Source: {os.path.basename(file_path)} --- */\n{content}"
            )

        return "\n".join(bundled_content)

    def _generate_embedded_fonts_css(self) -> str:
        """
        Generates CSS @font-face rules by embedding font files as Base64 strings.

        This avoids issues with local file loading policies in webviews.

        Returns:
            str: A CSS string containing the @font-face definitions.
        """
        css_rules: List[str] = []
        font_family: str = "OpenSauceSans"
        logging.info("Generating embedded fonts CSS...")

        for font_metadata in self.font_config:
            try:
                relative_path: str = os.path.join(
                    "src", "static", "fonts", font_metadata["file"]
                )
                full_path: str = PathManager.get_resource_path(relative_path)

                if os.path.exists(full_path):
                    with open(full_path, "rb") as font_file:
                        base64_data: str = base64.b64encode(font_file.read()).decode(
                            "utf-8"
                        )

                    file_extension: str = (
                        os.path.splitext(font_metadata["file"])[1]
                        .lower()
                        .replace(".", "")
                    )
                    font_format: str = (
                        "truetype" if file_extension == "ttf" else file_extension
                    )

                    css_rule: str = f"""
                    @font-face {{
                        font-family: '{font_family}';
                        src: url(data:font/{font_format};charset=utf-8;base64,{base64_data}) format('{font_format}');
                        font-weight: {font_metadata["weight"]};
                        font-style: normal;
                        font-display: swap;
                    }}
                    """
                    css_rules.append(css_rule)
                else:
                    logging.warning(f"Font file missing: {relative_path}")
            except Exception as error:
                logging.error(f"Error embedding font {font_metadata['file']}: {error}")

        return "\n".join(css_rules)

    def load_html_content(self) -> None:
        """
        Preloads all UI resources (HTML, CSS, JS, Fonts) into memory.

        This method should be called during application startup to ensure
        fast rendering when windows are created.
        """
        try:
            # 1. Fonts
            self.resources["fonts_css"] = self._generate_embedded_fonts_css()

            # 2. HTML Templates
            self._app_state.settings_html = self._read_resource_file(
                "src/templates/settings.html"
            )
            self._app_state.index_html = self._read_resource_file(
                "src/templates/index.html"
            )

            # 3. CSS
            self.resources["index_css"] = self._read_resource_file(
                "src/static/css/index.css"
            )
            self.resources["settings_css"] = self._read_resource_file(
                "src/static/css/settings.css"
            )

            # 4. JavaScript - Main Window
            index_js_files: List[str] = [
                "src/static/js/api.js",
                "src/static/js/audio-viz.js",
                "src/static/js/ui.js",
                "src/static/js/index.js",
            ]
            self.resources["index_js"] = "\n".join(
                [self._read_resource_file(file) for file in index_js_files]
            )

            # 5. JavaScript - Settings Window (Modular Bundle)
            settings_modules: List[str] = [
                "src/static/js/settings/constants.js",
                "src/static/js/settings/utils.js",
                "src/static/js/settings/i18n.js",
                "src/static/js/settings/api-config.js",
                "src/static/js/settings/dashboard.js",
                "src/static/js/settings/history.js",
                "src/static/js/settings/replacements.js",
                "src/static/js/settings/agents.js",
                "src/static/js/settings/logs.js",
                "src/static/js/settings/updates.js",
                "src/static/js/settings/hotkeys.js",
                "src/static/js/settings/modals.js",
                "src/static/js/settings/navigation.js",
                "src/static/js/settings/main.js",
            ]

            # Vendor Libraries (Dependencies first)
            vendor_files: List[str] = [
                "src/static/js/vendor/chart.min.js",
                "src/static/js/vendor/markdown-it.min.js",
                "src/static/js/vendor/fuse.min.js",
            ]

            vendor_content_list: List[str] = []
            for v_file in vendor_files:
                content = self._read_resource_file(v_file)
                if content:
                    vendor_content_list.append(content)
                else:
                    logging.warning(f"Failed to load vendor library: {v_file}")

            combined_vendor_js = "\n".join(vendor_content_list)
            app_logic_js = self._bundle_es6_modules(settings_modules)

            self.resources["settings_js"] = f"{combined_vendor_js}\n{app_logic_js}"

            logging.debug("All UI resources loaded successfully.")

        except Exception as error:
            logging.critical(
                f"Critical error loading UI resources: {error}", exc_info=True
            )

    def create_html(self, template_path: str) -> str:
        """
        Generates the final HTML for a webview window.

        Injects Fonts, CSS, JS, and converts relative image paths to Base64
        Data URIs to ensure self-contained rendering.

        Args:
            template_path (str): The relative path to the HTML template file.

        Returns:
            str: The fully processed HTML content.
        """
        content: str = ""

        try:
            full_path: str = PathManager.get_resource_path(template_path)
            with open(full_path, "r", encoding="utf-8") as file_handle:
                content = file_handle.read()
        except Exception as error:
            error_message = f"Error reading template '{template_path}': {error}"
            logging.critical(error_message)
            return f"<html><body><h1>Error</h1><p>{error_message}</p></body></html>"

        # --- Image Encoding Handler ---
        def replace_img_src_with_base64(match: Match) -> str:
            """Regex callback to replace relative image src with Base64."""
            relative_image_path: str = match.group(1)
            real_path: str = PathManager.get_resource_path(
                os.path.join("src", "static", relative_image_path)
            )
            try:
                with open(real_path, "rb") as img_file:
                    encoded_string: str = base64.b64encode(img_file.read()).decode(
                        "utf-8"
                    )
                    file_ext: str = (
                        os.path.splitext(real_path)[1].lower().replace(".", "")
                    )
                    mime_type: str = "svg+xml" if file_ext == "svg" else file_ext
                    return f'src="data:image/{mime_type};base64,{encoded_string}"'
            except Exception as img_error:
                logging.error(
                    f"Failed to encode image {relative_image_path}: {img_error}"
                )
                return match.group(0)

        # Apply image replacement (matches src="../static/...")
        content = re.sub(
            r'src="\.\./static/([^"]+)"', replace_img_src_with_base64, content
        )

        # --- Asset Injection ---
        css_content: str = ""
        js_content: str = ""
        is_settings_page: bool = "settings" in template_path
        is_index_page: bool = "index" in template_path or "index" in content

        fonts_style: str = self.resources.get("fonts_css", "")

        if is_settings_page:
            css_content = f"{fonts_style}\n{self.resources['settings_css']}"
            js_content = self.resources["settings_js"]

            # Pre-inject toggle states into HTML to avoid flicker
            try:
                toggles_state_map: Dict[str, bool] = {
                    "toggle-sound": app_state.sound_enabled,
                    "toggle-mute": app_state.mute_sound,
                    "toggle-chart-type": app_state.chart_type == "line",
                    "dashboard-period-toggle": app_state.dashboard_period == 7,
                    "toggle-dev-mode": app_state.developer_mode,
                }
            except AttributeError:
                toggles_state_map = {}

            for element_id, is_checked in toggles_state_map.items():
                if is_checked:
                    content, _ = re.subn(
                        rf'(<input[^>]*id="{element_id}"[^>]*?)>',
                        r"\1 checked>",
                        content,
                    )

            # Pre-reveal logs tab if dev mode is active
            if app_state.developer_mode:
                content = re.sub(
                    r'(class="sidebar-item)\s+hidden-by-default("\s+id="logs-sidebar-tab")',
                    r"\1\2",
                    content,
                )

        elif is_index_page:
            css_content = f"{fonts_style}\n{self.resources['index_css']}"
            js_content = self.resources["index_js"]

        # Inject CSS into <head>
        if css_content:
            style_tag: str = f"<style>\n{css_content}\n</style>\n</head>"
            content = content.replace("</head>", style_tag)

        # Inject JS before </body>
        if js_content:
            script_tag: str = f"<script>\n{js_content}\n</script>\n</body>"
            content = content.replace("</body>", script_tag)

        return content


class WindowManager:
    """
    Manages application window states, positioning, and visibility.

    Acts as an abstraction layer over OS-specific window management calls.
    """

    def __init__(self, app_state_instance: AppState, os_interface: Any) -> None:
        """
        Initialize the window manager.

        Args:
            app_state_instance (AppState): Global app state.
            os_interface (Any): Adapter for OS-specific API calls.
        """
        self.app_state: AppState = app_state_instance
        self.os_interface: Any = os_interface
        self.main_window_title: str = "Ozmoz"
        self.settings_window_title: str = "Ozmoz Settings"

    def _get_window_handle(self, title: str) -> Optional[int]:
        """Retrieves the native window handle (HWND on Windows)."""
        return self.os_interface.find_window_handle(title)

    def toggle_main_window_visibility(self) -> None:
        """
        Toggles the visibility of the main application window.

        Prevents toggling if a critical operation (recording) is active.
        """
        if app_state.is_recording or app_state.ai_recording:
            return

        window_handle: Optional[int] = self._get_window_handle(self.main_window_title)
        if window_handle:
            if self.os_interface.is_window_visible(window_handle):
                self.os_interface.hide_window(window_handle)
            else:
                self.os_interface.show_window(
                    window_handle, activate=False, always_on_top=True
                )

    def bring_to_foreground(self, title: str) -> bool:
        """
        Activates a window and brings it to the foreground.

        Args:
            title (str): Title of the window.

        Returns:
            bool: True if successful, False otherwise.
        """
        window_handle: Optional[int] = self._get_window_handle(title)
        if not window_handle:
            return False

        try:
            self.os_interface.show_window(window_handle, activate=True)
            return True
        except Exception as error:
            logging.error(f"Error focusing window '{title}': {error}")
            return False

    def is_visible(self) -> bool:
        """Checks if the main window is currently visible."""
        window_handle: Optional[int] = self._get_window_handle(self.main_window_title)
        return (
            self.os_interface.is_window_visible(window_handle)
            if window_handle
            else False
        )

    def move_main_window(self, x: int, y: int) -> None:
        """
        Moves the main window to absolute screen coordinates.

        Args:
            x (int): X coordinate.
            y (int): Y coordinate.
        """
        handle = self._get_window_handle(self.main_window_title)
        if handle:
            self.os_interface.move_window(handle, x, y)


class SystemTrayManager:
    """
    Manages the System Tray icon and context menu using PySide6 (Qt).
    """

    class _AutoCloseMenu(QMenu):
        """
        A custom QMenu that automatically closes itself after a delay when
        the mouse leaves, improving UX for tray menus.
        """

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.close_timer: QTimer = QTimer(self)
            self.close_timer.setSingleShot(True)
            self.close_timer.timeout.connect(self.close)

        def enterEvent(self, event: QEnterEvent) -> None:
            """Stop the auto-close timer when mouse enters."""
            self.close_timer.stop()
            super().enterEvent(event)

        def leaveEvent(self, event: QEvent) -> None:
            """Start the auto-close timer when mouse leaves."""
            self.close_timer.start(800)  # 800ms delay
            super().leaveEvent(event)

    def __init__(
        self,
        app_state_instance: AppState,
        hotkey_manager: Any,
        show_settings_callback: Callable[[], None],
        exit_app_callback: Callable[[], None],
    ) -> None:
        """
        Initialize the system tray manager.

        Args:
            app_state_instance (AppState): Global app state.
            hotkey_manager (Any): Manager for hotkeys (dependency).
            show_settings_callback (Callable): Action to open settings.
            exit_app_callback (Callable): Action to exit the app.
        """
        self.app_state: AppState = app_state_instance
        self.hotkey_manager: Any = hotkey_manager
        self.show_settings_callback: Callable[[], None] = show_settings_callback
        self.exit_app_callback: Callable[[], None] = exit_app_callback
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self.menu: Optional[QMenu] = None

    def _show_about_page(self) -> None:
        """Opens the GitHub repository/About page in the browser."""
        try:
            webbrowser.open("https://github.com/zerep-thomas/ozmoz")
        except Exception:
            pass

    def _create_context_menu(self) -> QMenu:
        """
        Creates and styles the context menu.

        Returns:
            QMenu: The configured menu object.
        """
        menu = self._AutoCloseMenu()

        # Dark theme styling for the menu
        menu.setStyleSheet(
            """
            QMenu { background-color: #1e1e1e; color: white; border: 1px solid #444; border-radius: 8px; padding: 5px; font-size: 12px; }
            QMenu::item { padding: 8px 25px 8px 20px; border-radius: 5px; }
            QMenu::item:selected { background-color: #3a3a3a; }
            QMenu::separator { height: 1px; background-color: #444; margin: 5px 10px; }
            """
        )

        menu.addAction("About").triggered.connect(self._show_about_page)
        menu.addAction("Settings").triggered.connect(self.show_settings_callback)
        menu.addSeparator()
        menu.addAction("Exit").triggered.connect(self.exit_app_callback)

        return menu

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handles click events on the tray icon."""
        if reason == QSystemTrayIcon.ActivationReason.Context:
            if self.menu:
                self.menu.exec_(QCursor.pos())

    def _setup_tray_icon(self, qt_application: QApplication) -> None:
        """Configures the visual tray icon and connects signals."""
        self.menu = self._create_context_menu()
        icon_path: str = PathManager.get_resource_path("src/static/img/icons/icon.ico")

        self.tray_icon = QSystemTrayIcon(QIcon(icon_path), qt_application)
        self.tray_icon.setToolTip("Ozmoz")
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

        self.app_state.tray_icon_qt = self.tray_icon

    def run_in_thread(self) -> None:
        """
        Runs the Qt event loop in a separate daemon thread.

        This allows the PySide6 UI components (System Tray) to run concurrently
        with the main application loop (pywebview).
        """

        def run_pyqt_app() -> None:
            try:
                # Use existing instance or create a new one
                app = cast(
                    QApplication, QApplication.instance() or QApplication(sys.argv)
                )
                app.setQuitOnLastWindowClosed(False)
                self._setup_tray_icon(app)
                app.exec()
            except Exception as error:
                logging.critical(f"System Tray Thread Error: {error}")

        threading.Thread(target=run_pyqt_app, daemon=True).start()
        logging.info("System Tray service activated.")
