import base64
import logging
import os
import re
import sys
import threading
import webbrowser
from typing import Any, Callable, Dict, List, Match, Optional, cast

# Qt Framework
from PySide6.QtCore import QEvent, QTimer
from PySide6.QtGui import QCursor, QEnterEvent, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

# Local Modules
from modules.config import AppState, app_state
from modules.utils import PathManager


class UIResourceLoader:
    """
    Manages loading, localization, and dynamic injection into HTML templates.
    Handles reading files, bundling JS/CSS, and embedding fonts/images.
    """

    def __init__(self, app_state_instance: AppState) -> None:
        self._app_state: AppState = app_state_instance
        self.resources: Dict[str, str] = {
            "index_css": "",
            "index_js": "",
            "settings_css": "",
            "settings_js": "",
            "fonts_css": "",
        }

        self.font_config: List[Dict[str, Any]] = [
            {"file": "OpenSauceSans-Light.ttf", "weight": 300},
            {"file": "OpenSauceSans-Regular.ttf", "weight": 400},
            {"file": "OpenSauceSans-Medium.ttf", "weight": 500},
            {"file": "OpenSauceSans-SemiBold.ttf", "weight": 600},
            {"file": "OpenSauceSans-Bold.ttf", "weight": 700},
            {"file": "OpenSauceSans-ExtraBold.ttf", "weight": 800},
            {"file": "OpenSauceSans-Black.ttf", "weight": 900},
        ]

    def _read_resource(self, relative_path: str) -> str:
        """
        Reads a text resource file safely from the disk.

        Args:
            relative_path (str): Path relative to the application root.

        Returns:
            str: The content of the file or an empty string if failed.
        """
        try:
            full_path: str = PathManager.get_resource_path(relative_path)
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as file_handle:
                    return file_handle.read()
            else:
                logging.warning(f"Resource not found: {relative_path}")
                return ""
        except Exception as error:
            logging.error(f"Error reading resource {relative_path}: {error}")
            return ""

    def _load_and_bundle_es6(self, file_list: List[str]) -> str:
        """
        Reads multiple ES6 files, removes 'import'/'export' keywords,
        and concatenates them to emulate a bundler.

        Args:
            file_list (List[str]): List of relative file paths to bundle.

        Returns:
            str: The concatenated JavaScript content.
        """
        bundled_content: List[str] = []
        for file_path in file_list:
            content: str = self._read_resource(file_path)

            # Remove ES6 module syntax for browser compatibility without a build step
            content = re.sub(r"^\s*import .*?;", "", content, flags=re.MULTILINE)
            content = re.sub(r"^\s*export\s+", "", content, flags=re.MULTILINE)

            bundled_content.append(
                f"\n/* --- Source: {os.path.basename(file_path)} --- */\n{content}"
            )

        return "\n".join(bundled_content)

    def _generate_fonts_css(self) -> str:
        """
        Generates CSS @font-face rules by embedding font files as base64 strings.

        Returns:
            str: CSS string containing the font definitions.
        """
        css_parts: List[str] = []
        font_family: str = "OpenSauceSans"
        logging.info("Generating fonts CSS from base64...")

        for font_entry in self.font_config:
            try:
                relative_path: str = os.path.join(
                    "src", "static", "fonts", font_entry["file"]
                )
                full_path: str = PathManager.get_resource_path(relative_path)

                if os.path.exists(full_path):
                    with open(full_path, "rb") as font_file:
                        base64_data: str = base64.b64encode(font_file.read()).decode(
                            "utf-8"
                        )

                    file_extension: str = (
                        os.path.splitext(font_entry["file"])[1].lower().replace(".", "")
                    )
                    font_format: str = (
                        "truetype" if file_extension == "ttf" else file_extension
                    )

                    css_rule: str = f"""
                    @font-face {{
                        font-family: '{font_family}';
                        src: url(data:font/{font_format};charset=utf-8;base64,{base64_data}) format('{font_format}');
                        font-weight: {font_entry["weight"]};
                        font-style: normal;
                        font-display: swap;
                    }}
                    """
                    css_parts.append(css_rule)
                else:
                    logging.warning(f"Font file not found: {relative_path}")
            except Exception as error:
                logging.error(f"Error loading font {font_entry['file']}: {error}")

        return "\n".join(css_parts)

    def load_html_content(self) -> None:
        """
        Preloads HTML, CSS, JS, and Fonts into memory.
        This ensures resources are ready before the UI is shown.
        """
        try:
            self.resources["fonts_css"] = self._generate_fonts_css()
            self._app_state.settings_html = self._read_resource(
                "src/templates/settings.html"
            )
            self._app_state.index_html = self._read_resource("src/templates/index.html")

            self.resources["index_css"] = self._read_resource(
                "src/static/css/index.css"
            )
            self.resources["settings_css"] = self._read_resource(
                "src/static/css/settings.css"
            )

            index_js_files: List[str] = [
                "src/static/js/api.js",
                "src/static/js/audio-viz.js",
                "src/static/js/ui.js",
                "src/static/js/index.js",
            ]
            self.resources["index_js"] = "\n".join(
                [self._read_resource(file) for file in index_js_files]
            )

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

            chart_library: str = self._read_resource(
                "src/static/js/vendor/chart.min.js"
            )
            settings_logic: str = self._load_and_bundle_es6(settings_modules)

            self.resources["settings_js"] = f"{chart_library}\n{settings_logic}"

            logging.debug("All UI resources (HTML/CSS/JS/Fonts) loaded.")

        except Exception as error:
            logging.critical(
                f"Critical error loading resources: {error}", exc_info=True
            )

    def create_html(self, file_name: str) -> str:
        """
        Prepares final HTML by injecting Fonts, CSS, JS, and encoding images to Base64.

        Args:
            file_name (str): The name or path of the target template file.

        Returns:
            str: The fully processed HTML string.
        """
        target_path: str = file_name
        content: str = ""

        try:
            full_path: str = PathManager.get_resource_path(target_path)
            with open(full_path, "r", encoding="utf-8") as file_handle:
                content = file_handle.read()
        except Exception as error:
            error_message: str = f"Error reading template '{target_path}': {error}"
            logging.critical(error_message)
            return f"<html><body><h1>Error</h1><p>{error_message}</p></body></html>"

        def replace_img_b64(match: Match) -> str:
            """Callback to replace relative image paths with base64 data."""
            relative_path: str = match.group(1)
            real_path: str = PathManager.get_resource_path(
                os.path.join("src", "static", relative_path)
            )
            try:
                with open(real_path, "rb") as img_file:
                    encoded_string: str = base64.b64encode(img_file.read()).decode(
                        "utf-8"
                    )
                    file_extension: str = (
                        os.path.splitext(real_path)[1].lower().replace(".", "")
                    )
                    mime_type: str = (
                        "svg+xml" if file_extension == "svg" else file_extension
                    )
                    return f'src="data:image/{mime_type};base64,{encoded_string}"'
            except Exception as error:
                logging.error(f"Unable to encode image {relative_path}: {error}")
                return match.group(0)

        # Regex to find src="../static/..."
        content = re.sub(r'src="\.\./static/([^"]+)"', replace_img_b64, content)

        css_content: str = ""
        js_content: str = ""
        is_settings: bool = "settings" in target_path
        is_index: bool = "index" in target_path or "index" in content

        fonts_style: str = self.resources.get("fonts_css", "")

        if is_settings:
            css_content = fonts_style + "\n" + self.resources["settings_css"]
            js_content = self.resources["settings_js"]

            try:
                # Map HTML IDs to AppState booleans for checkbox pre-checking
                toggles_map: Dict[str, bool] = {
                    "toggle": app_state.sound_enabled,
                    "toggle-mute": app_state.mute_sound,
                    "toggle-chart-type": app_state.chart_type == "line",
                    "dashboard-period-toggle": app_state.dashboard_period == 7,
                    "toggle-dev-mode": app_state.developer_mode,
                }
            except AttributeError:
                toggles_map = {}

            for toggle_id, is_enabled in toggles_map.items():
                if is_enabled:
                    content, _ = re.subn(
                        rf'(<input[^>]*id="{toggle_id}"[^>]*?)>',
                        r"\1 checked>",
                        content,
                    )

            if app_state.developer_mode:
                content = re.sub(
                    r'(class="sidebar-item)\s+hidden-by-default("\s+id="logs-sidebar-tab")',
                    r"\1\2",
                    content,
                )

        elif is_index:
            css_content = fonts_style + "\n" + self.resources["index_css"]
            js_content = self.resources["index_js"]

        # Inject CSS
        if css_content:
            style_tag: str = f"<style>\n{css_content}\n</style>\n</head>"
            content = content.replace("</head>", style_tag)

        # Inject JS
        if js_content:
            script_tag: str = f"<script>\n{js_content}\n</script>\n</body>"
            content = content.replace("</body>", script_tag)

        return content


class WindowManager:
    """
    Abstract wrapper to manage application display, focus, and window handles.
    """

    def __init__(self, app_state_instance: AppState, os_interface: Any) -> None:
        self.app_state: AppState = app_state_instance
        self.os_interface: Any = os_interface
        self.main_window_title: str = "Ozmoz"
        self.settings_window_title: str = "Ozmoz Settings"

    def _get_window_handle(self, title: str) -> Optional[int]:
        """Finds the window handle (HWND on Windows) by title."""
        return self.os_interface.find_window_handle(title)

    def toggle_main_window_visibility(self) -> None:
        """
        Toggles the main window's visibility state.
        Does nothing if recording is in progress.
        """
        if app_state.is_recording or app_state.ai_recording:
            return

        window_handle: Optional[int] = self._get_window_handle("Ozmoz")
        if window_handle:
            if self.os_interface.is_window_visible(window_handle):
                self.os_interface.hide_window(window_handle)
            else:
                self.os_interface.show_window(
                    window_handle, activate=False, always_on_top=True
                )

    def bring_to_foreground(self, title: str) -> bool:
        """
        Attempts to bring the window with the specified title to the foreground.

        Args:
            title (str): The window title to search for.

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
            logging.error(f"Error focusing '{title}': {error}")
            return False

    def is_visible(self) -> bool:
        """Checks if the main application window is currently visible."""
        window_handle: Optional[int] = self._get_window_handle(self.main_window_title)
        return (
            self.os_interface.is_window_visible(window_handle)
            if window_handle
            else False
        )

    def move_main_window(self, x: int, y: int) -> None:
        """
        Moves the main application window to the specified coordinates.
        """
        handle = self._get_window_handle(self.main_window_title)
        if handle:
            self.os_interface.move_window(handle, x, y)


class SystemTrayManager:
    """
    Manages the taskbar icon (System Tray) and its context menu.
    """

    class _AutoCloseMenu(QMenu):
        """Custom QMenu that automatically closes after a delay if inactive."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.close_timer: QTimer = QTimer(self)
            self.close_timer.setSingleShot(True)
            self.close_timer.timeout.connect(self.close)

        def enterEvent(self, event: QEnterEvent) -> None:
            """Stop close timer when mouse enters the menu."""
            self.close_timer.stop()
            super().enterEvent(event)

        def leaveEvent(self, event: QEvent) -> None:
            """Start close timer when mouse leaves the menu."""
            self.close_timer.start(800)
            super().leaveEvent(event)

    def __init__(
        self,
        app_state_instance: AppState,
        hotkey_manager: Any,
        show_settings_callback: Callable[[], None],
        exit_app_callback: Callable[[], None],
    ) -> None:
        self.app_state: AppState = app_state_instance
        self.hotkey_manager: Any = hotkey_manager
        self.show_settings_callback: Callable[[], None] = show_settings_callback
        self.exit_app_callback: Callable[[], None] = exit_app_callback
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self.menu: Optional[QMenu] = None

    def _show_about(self) -> None:
        """Opens the About page in the default web browser."""
        try:
            webbrowser.open("https://github.com/zerep-thomas/ozmoz")
        except Exception:
            pass

    def _create_menu(self) -> QMenu:
        """Creates and styles the context menu for the system tray."""
        menu = self._AutoCloseMenu()
        menu.setStyleSheet(
            """
            QMenu { background-color: #1e1e1e; color: white; border: 1px solid #444; border-radius: 8px; padding: 5px; font-size: 12px; }
            QMenu::item { padding: 8px 25px 8px 20px; border-radius: 5px; }
            QMenu::item:selected { background-color: #3a3a3a; }
            QMenu::separator { height: 1px; background-color: #444; margin: 5px 10px; }
        """
        )

        menu.addAction("About").triggered.connect(self._show_about)
        menu.addAction("Settings").triggered.connect(self.show_settings_callback)
        menu.addSeparator()
        menu.addAction("Exit").triggered.connect(self.exit_app_callback)

        return menu

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """
        Handles clicks on the tray icon.
        Opens the menu on right-click/context, temporarily disabling keyboard hooks.
        """
        if reason == QSystemTrayIcon.ActivationReason.Context:
            with self.app_state.keyboard_lock:
                try:
                    import keyboard

                    keyboard.unhook_all()
                except Exception:
                    pass

            if self.menu:
                self.menu.exec_(QCursor.pos())

            try:
                self.hotkey_manager.register_all()
            except Exception:
                pass

    def _setup_tray_icon(self, qt_application: QApplication) -> None:
        """Configures the tray icon and connects signals."""
        self.menu = self._create_menu()
        icon_path: str = PathManager.get_resource_path("src/static/img/icons/icon.ico")
        self.tray_icon = QSystemTrayIcon(QIcon(icon_path), qt_application)
        self.tray_icon.setToolTip("Ozmoz")
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
        self.app_state.tray_icon_qt = self.tray_icon

    def run_in_thread(self) -> None:
        """
        Runs the Qt event loop in a separate daemon thread to avoid blocking the main app.
        """

        def run_pyqt_app() -> None:
            try:
                # Ensure only one QApplication exists
                app = cast(
                    QApplication, QApplication.instance() or QApplication(sys.argv)
                )
                app.setQuitOnLastWindowClosed(False)
                self._setup_tray_icon(app)
                app.exec()
            except Exception as error:
                logging.critical(f"Tray Thread Error: {error}")

        threading.Thread(target=run_pyqt_app, daemon=True).start()
        logging.info("System Tray activated.")
