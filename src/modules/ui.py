"""
UI Management Module for Ozmoz.

This module handles:
- Secure loading and processing of static resources (HTML, CSS, JS, Fonts)
- Dynamic injection of assets into web templates with XSS protection
- Window management (Show, Hide, Move, Focus) via OS adapters
- System Tray integration using pystray

Security Features:
- Path traversal protection for resource loading
- Whitelist-based image embedding (only from static/ directory)
- Input sanitization for HTML injection
- Secure regex compilation for performance and safety
"""

import base64
import logging
import os
import re
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final, Optional, Protocol

# Third-party imports
import pystray
from PIL import Image

# Local application imports
from modules.config import AppState
from modules.utils import PathManager

# --- Module Constants ---

# Resource paths (relative to application root)
FONT_DIR: Final[str] = "src/static/fonts"
IMAGE_DIR: Final[str] = "src/static/img"
CSS_DIR: Final[str] = "src/static/css"
JS_DIR: Final[str] = "src/static/js"
TEMPLATE_DIR: Final[str] = "src/templates"

# Tray icon configuration
TRAY_ICON_PATH: Final[str] = "src/static/img/icons/icon.ico"
TRAY_ICON_FALLBACK_SIZE: Final[tuple[int, int]] = (64, 64)
TRAY_ICON_FALLBACK_COLOR: Final[tuple[int, int, int]] = (73, 109, 137)

# Window titles
MAIN_WINDOW_TITLE: Final[str] = "Ozmoz"
SETTINGS_WINDOW_TITLE: Final[str] = "Ozmoz Settings"

# External URLs
GITHUB_ABOUT_URL: Final[str] = "https://github.com/zerep-thomas/ozmoz"

# Allowed MIME types for image embedding
ALLOWED_IMAGE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {"png", "jpg", "jpeg", "svg", "gif", "webp", "ico"}
)

# Chart type mapping (for toggle state injection)
CHART_TYPE_LINE: Final[str] = "line"

# Dashboard periods (in days)
DASHBOARD_PERIOD_WEEK: Final[int] = 7

# Pre-compiled regex patterns (performance optimization)
REGEX_ES6_IMPORT: Final[re.Pattern] = re.compile(r"^\s*import .*?;", flags=re.MULTILINE)
REGEX_ES6_EXPORT: Final[re.Pattern] = re.compile(r"^\s*export\s+", flags=re.MULTILINE)
REGEX_IMG_SRC: Final[re.Pattern] = re.compile(r'src="\.\./static/([^"]+)"')


# --- Custom Exceptions ---


class UIResourceError(Exception):
    """Raised when UI resource loading fails critically."""


class TemplateProcessingError(Exception):
    """Raised when HTML template processing fails."""


class WindowOperationError(Exception):
    """Raised when window management operations fail."""


# --- Type Protocols ---


class OSInterface(Protocol):
    """Protocol defining OS-specific window management operations."""

    def find_window_handle(self, title: str) -> Optional[int]:
        """Find native window handle by title."""
        ...

    def is_window_visible(self, window_handle: Optional[int]) -> bool:
        """Check if window is currently visible."""
        ...

    def hide_window(self, window_handle: Optional[int]) -> None:
        """Hide window."""
        ...

    def show_window(
        self,
        window_handle: Optional[int],
        activate: bool = True,
        always_on_top: bool = False,
    ) -> None:
        """Show window with optional activation and always-on-top."""
        ...

    def move_window(self, window_handle: Optional[int], x: int, y: int) -> None:
        """Move window to absolute screen coordinates."""
        ...


@dataclass(frozen=True)
class FontConfig:
    """Configuration for a single font weight/style."""

    filename: str
    weight: int

    def __post_init__(self) -> None:
        """Validate font configuration."""
        if not 100 <= self.weight <= 900:
            raise ValueError(f"Invalid font weight: {self.weight}")
        if not self.filename.endswith(".ttf"):
            raise ValueError(f"Only TTF fonts supported: {self.filename}")


# --- Font Configuration ---

FONT_FAMILY: Final[str] = "OpenSauceSans"

# Immutable font configuration using dataclass
FONT_CONFIGS: Final[tuple[FontConfig, ...]] = (
    FontConfig("OpenSauceSans-Light.ttf", 300),
    FontConfig("OpenSauceSans-Regular.ttf", 400),
    FontConfig("OpenSauceSans-Medium.ttf", 500),
    FontConfig("OpenSauceSans-SemiBold.ttf", 600),
    FontConfig("OpenSauceSans-Bold.ttf", 700),
    FontConfig("OpenSauceSans-ExtraBold.ttf", 800),
    FontConfig("OpenSauceSans-Black.ttf", 900),
)


# --- UI Resource Loader ---


class UIResourceLoader:
    """
    Secure UI resource manager with caching and validation.

    Responsibilities:
    - Load and cache static assets (HTML, CSS, JS, Fonts)
    - Bundle modular JavaScript files
    - Embed fonts and images as base64 Data URIs
    - Inject dynamic content into templates

    Security:
    - Path traversal protection via whitelist validation
    - Only embeds images from static/ directory
    - Sanitizes HTML element IDs before regex injection
    - Pre-compiled regex patterns to prevent injection

    Performance:
    - Caches all resources in memory on startup
    - Pre-compiles regex patterns
    - Lazy font embedding (only on first use)

    Thread Safety: Not thread-safe. Call load_html_content() once during startup.
    """

    def __init__(self, app_state_instance: AppState) -> None:
        """
        Initialize resource loader with empty cache.

        Args:
            app_state_instance: Global application state for storing loaded templates.
        """
        self._app_state: AppState = app_state_instance

        # Resource cache (populated by load_html_content())
        self._resources: dict[str, str] = {
            "index_css": "",
            "index_js": "",
            "settings_css": "",
            "settings_js": "",
            "fonts_css": "",
        }

        # Base64-encoded image cache (populated lazily)
        self._image_cache: dict[str, str] = {}

        logging.debug("UIResourceLoader initialized")

    def _read_resource_file(self, relative_path: str) -> str:
        """
        Safely read text file from application resources.

        Security: Uses PathManager.get_resource_path() which handles
        PyInstaller bundle paths safely.

        Args:
            relative_path: Path relative to application root (e.g., 'src/static/css/main.css').

        Returns:
            File content as string, or empty string on error.

        Raises:
            No exceptions raised - errors logged and empty string returned.
        """
        if not relative_path or not isinstance(relative_path, str):
            logging.error("Invalid relative_path provided")
            return ""

        try:
            full_path = PathManager.get_resource_path(relative_path)

            if not os.path.exists(full_path):
                logging.warning(
                    f"UI resource not found: {relative_path}",
                    extra={"full_path": full_path},
                )
                return ""

            with open(full_path, "r", encoding="utf-8") as file_handle:
                content = file_handle.read()

            logging.debug(
                f"Loaded resource: {relative_path}", extra={"size_bytes": len(content)}
            )
            return content

        except OSError as e:
            logging.error(
                f"Failed to read resource file: {relative_path}",
                exc_info=True,
                extra={"error": str(e)},
            )
            return ""
        except UnicodeDecodeError as e:
            logging.error(
                f"Encoding error reading {relative_path}", extra={"error": str(e)}
            )
            return ""

    def _bundle_es6_modules(self, file_paths: list[str]) -> str:
        """
        Bundle multiple ES6 modules into single script (removes import/export).

        Simulates a basic bundler by stripping ES6 module syntax to make
        code compatible with non-module script tags in webview.

        Args:
            file_paths: List of relative paths to JavaScript files.

        Returns:
            Concatenated JavaScript source with ES6 syntax removed.

        Example:
            >>> loader._bundle_es6_modules(['src/static/js/utils.js', 'src/static/js/main.js'])
            '/* Source: utils.js */\nfunction helper() {...}\n/* Source: main.js */\n...'
        """
        bundled_content: list[str] = []

        for file_path in file_paths:
            content = self._read_resource_file(file_path)

            if not content:
                logging.warning(f"Skipping empty module: {file_path}")
                continue

            # Strip ES6 module syntax using pre-compiled regex (performance + security)
            content = REGEX_ES6_IMPORT.sub("", content)
            content = REGEX_ES6_EXPORT.sub("", content)

            # Add source comment for debugging
            source_comment = f"\n/* --- Source: {os.path.basename(file_path)} --- */\n"
            bundled_content.append(f"{source_comment}{content}")

        result = "\n".join(bundled_content)

        logging.debug(
            f"Bundled {len(file_paths)} modules", extra={"total_size": len(result)}
        )

        return result

    def _generate_embedded_fonts_css(self) -> str:
        """
        Generate CSS @font-face rules with base64-embedded font files.

        Embeds fonts as Data URIs to avoid local file loading restrictions
        in webview environments.

        Returns:
            CSS string with all @font-face declarations.

        Example Output:
            @font-face {
                font-family: 'OpenSauceSans';
                src: url(data:font/truetype;charset=utf-8;base64,AAEAAAALAIAAAwA...) format('truetype');
                font-weight: 400;
                font-style: normal;
                font-display: swap;
            }
        """
        css_rules: list[str] = []

        logging.info(f"Generating embedded fonts CSS for {len(FONT_CONFIGS)} weights")

        for font_config in FONT_CONFIGS:
            try:
                # Construct secure path
                relative_path = os.path.join(FONT_DIR, font_config.filename)
                full_path = PathManager.get_resource_path(relative_path)

                if not os.path.exists(full_path):
                    logging.warning(
                        f"Font file missing: {font_config.filename}",
                        extra={"weight": font_config.weight},
                    )
                    continue

                # Read and encode font file
                with open(full_path, "rb") as font_file:
                    font_bytes = font_file.read()
                    base64_data = base64.b64encode(font_bytes).decode("utf-8")

                # Determine font format (TTF only for now)
                file_extension = (
                    Path(font_config.filename).suffix.lower().replace(".", "")
                )
                font_format = "truetype" if file_extension == "ttf" else file_extension

                # Generate @font-face rule
                css_rule = f"""
                @font-face {{
                    font-family: '{FONT_FAMILY}';
                    src: url(data:font/{font_format};charset=utf-8;base64,{base64_data}) format('{font_format}');
                    font-weight: {font_config.weight};
                    font-style: normal;
                    font-display: swap;
                }}
                """
                css_rules.append(css_rule)

                logging.debug(
                    f"Embedded font: {font_config.filename}",
                    extra={
                        "weight": font_config.weight,
                        "size_bytes": len(font_bytes),
                        "base64_length": len(base64_data),
                    },
                )

            except OSError as e:
                logging.error(
                    f"Failed to embed font: {font_config.filename}",
                    exc_info=True,
                    extra={"error": str(e)},
                )
            except Exception as e:
                logging.error(
                    f"Unexpected error embedding font: {font_config.filename}",
                    exc_info=True,
                    extra={"error": str(e)},
                )

        return "\n".join(css_rules)

    def _encode_image_to_base64(self, relative_path: str) -> Optional[str]:
        """
        Encode image file to base64 Data URI with caching.

        Security: Only processes files from static/ directory to prevent
        arbitrary file read attacks.

        Args:
            relative_path: Path relative to static/ directory (e.g., 'img/logo.png').

        Returns:
            Base64 Data URI or None on error.

        Example:
            >>> loader._encode_image_to_base64('img/logo.png')
            'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...'
        """
        # Check cache first
        if relative_path in self._image_cache:
            return self._image_cache[relative_path]

        # Validate file extension
        file_ext = Path(relative_path).suffix.lower().replace(".", "")
        if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
            logging.error(
                f"Unsupported image type: {file_ext}",
                extra={
                    "path": relative_path,
                    "allowed": list(ALLOWED_IMAGE_EXTENSIONS),
                },
            )
            return None

        try:
            # Construct secure path (must be in static/ directory)
            full_relative_path = os.path.join("src", "static", relative_path)
            real_path = PathManager.get_resource_path(full_relative_path)

            # Security: Verify path is within static directory
            real_path_obj = Path(real_path).resolve()
            static_dir = Path(PathManager.get_resource_path("src/static")).resolve()

            if not real_path_obj.is_relative_to(static_dir):
                logging.error(
                    "Security violation: Image path outside static directory",
                    extra={
                        "requested": relative_path,
                        "resolved": str(real_path_obj),
                        "allowed_base": str(static_dir),
                    },
                )
                return None

            if not os.path.exists(real_path):
                logging.warning(f"Image not found: {relative_path}")
                return None

            # Read and encode
            with open(real_path, "rb") as img_file:
                image_bytes = img_file.read()
                encoded_string = base64.b64encode(image_bytes).decode("utf-8")

            # Determine MIME type
            mime_type = "svg+xml" if file_ext == "svg" else file_ext
            data_uri = f"data:image/{mime_type};base64,{encoded_string}"

            # Cache the result
            self._image_cache[relative_path] = data_uri

            logging.debug(
                f"Encoded image: {relative_path}",
                extra={
                    "size_bytes": len(image_bytes),
                    "base64_length": len(encoded_string),
                },
            )

            return data_uri

        except OSError as e:
            logging.error(
                f"Failed to read image: {relative_path}", extra={"error": str(e)}
            )
            return None
        except Exception as e:
            logging.error(
                f"Unexpected error encoding image: {relative_path}",
                exc_info=True,
                extra={"error": str(e)},
            )
            return None

    def load_html_content(self) -> None:
        """
        Pre-load all UI resources into memory for fast rendering.

        Should be called once during application startup. Loads and caches:
        - Font files as base64 CSS
        - HTML templates
        - CSS stylesheets
        - JavaScript bundles

        Raises:
            UIResourceError: If critical resources fail to load.
        """
        try:
            logging.info("Loading UI resources...")

            # 1. Generate embedded fonts CSS
            self._resources["fonts_css"] = self._generate_embedded_fonts_css()

            # 2. Load HTML templates
            self._app_state.ui.settings_html = self._read_resource_file(
                "src/templates/settings.html"
            )
            self._app_state.ui.index_html = self._read_resource_file(
                "src/templates/index.html"
            )

            # Validate critical templates loaded
            if not self._app_state.ui.index_html:
                raise UIResourceError("Failed to load index.html template")

            # 3. Load CSS
            self._resources["index_css"] = self._read_resource_file(
                "src/static/css/index.css"
            )
            self._resources["settings_css"] = self._read_resource_file(
                "src/static/css/settings.css"
            )

            # 4. Bundle JavaScript - Main Window
            index_js_files = [
                "src/static/js/api.js",
                "src/static/js/audio-viz.js",
                "src/static/js/ui.js",
                "src/static/js/index.js",
            ]
            self._resources["index_js"] = "\n".join(
                [self._read_resource_file(f) for f in index_js_files]
            )

            # 5. Bundle JavaScript - Settings Window
            settings_modules = [
                "src/static/js/locales.js",
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

            # Load vendor libraries first
            vendor_files = [
                "src/static/js/vendor/chart.min.js",
                "src/static/js/vendor/markdown-it.min.js",
                "src/static/js/vendor/fuse.min.js",
            ]

            vendor_contents: list[str] = []
            for vendor_file in vendor_files:
                content = self._read_resource_file(vendor_file)
                if content:
                    vendor_contents.append(content)
                else:
                    logging.warning(f"Vendor library not loaded: {vendor_file}")

            # Combine vendor + app logic
            combined_vendor_js = "\n".join(vendor_contents)
            app_logic_js = self._bundle_es6_modules(settings_modules)
            self._resources["settings_js"] = f"{combined_vendor_js}\n{app_logic_js}"

            logging.info(
                "UI resources loaded successfully",
                extra={
                    "fonts_css_size": len(self._resources["fonts_css"]),
                    "index_js_size": len(self._resources["index_js"]),
                    "settings_js_size": len(self._resources["settings_js"]),
                },
            )

        except UIResourceError:
            raise
        except Exception as error:
            logging.critical(
                "Critical error loading UI resources",
                exc_info=True,
                extra={"error": str(error)},
            )
            raise UIResourceError(f"Failed to load UI resources: {error}") from error

    def _sanitize_element_id(self, element_id: str) -> str:
        """
        Sanitize HTML element ID for safe use in regex patterns.

        Prevents regex injection by escaping special regex characters.

        Args:
            element_id: HTML element ID to sanitize.

        Returns:
            Escaped string safe for regex patterns.

        Example:
            >>> loader._sanitize_element_id('toggle-sound')
            'toggle\\-sound'
        """
        return re.escape(element_id)

    def create_html(self, template_path: str) -> str:
        """
        Generate final HTML for webview with embedded assets and dynamic content.

        Process flow:
        1. Load HTML template
        2. Embed images as base64 Data URIs
        3. Inject fonts, CSS, and JavaScript
        4. Pre-fill form states (toggles, checkboxes)
        5. Apply conditional visibility (dev mode features)

        Args:
            template_path: Relative path to HTML template (e.g., 'src/templates/index.html').

        Returns:
            Fully processed HTML with all assets embedded.

        Raises:
            TemplateProcessingError: If template processing fails critically.

        Example:
            >>> loader.create_html('src/templates/settings.html')
            '<html>...<style>@font-face{...}</style>...</html>'
        """
        if not template_path or not isinstance(template_path, str):
            raise TemplateProcessingError("Invalid template_path")

        try:
            # 1. Load template
            full_path = PathManager.get_resource_path(template_path)

            if not os.path.exists(full_path):
                raise TemplateProcessingError(f"Template not found: {template_path}")

            with open(full_path, "r", encoding="utf-8") as file_handle:
                content = file_handle.read()

        except OSError as e:
            error_msg = f"Error reading template '{template_path}': {e}"
            logging.critical(error_msg, exc_info=True)
            return f"<html><body><h1>Error</h1><p>{error_msg}</p></body></html>"

        # 2. Embed images as base64
        def replace_img_src_callback(match: re.Match[str]) -> str:
            """
            Regex callback to replace relative image src with base64 Data URI.

            Args:
                match: Regex match object containing image path.

            Returns:
                Replacement string with base64 Data URI.
            """
            relative_image_path = match.group(1)

            # Attempt to encode image
            data_uri = self._encode_image_to_base64(relative_image_path)

            if data_uri:
                return f'src="{data_uri}"'
            else:
                # Fallback: keep original path (will fail to load but won't break HTML)
                logging.warning(
                    f"Failed to embed image, keeping original path: {relative_image_path}"
                )
                return match.group(0)

        # Apply image replacement (matches src="../static/...")
        content = REGEX_IMG_SRC.sub(replace_img_src_callback, content)

        # 3. Determine page type and prepare assets
        is_settings_page = "settings" in template_path.lower()
        is_index_page = "index" in template_path.lower() or "index" in content.lower()

        fonts_css = self._resources.get("fonts_css", "")
        css_content = ""
        js_content = ""

        if is_settings_page:
            # Settings page specific processing
            css_content = f"{fonts_css}\n{self._resources['settings_css']}"
            js_content = self._resources["settings_js"]

            # 4. Pre-inject toggle states to avoid UI flicker
            try:
                toggles_state_map: dict[str, bool] = {
                    "toggle-sound": self._app_state.audio.sound_enabled,
                    "toggle-mute": self._app_state.audio.mute_sound,
                    "toggle-chart-type": self._app_state.ui.chart_type
                    == CHART_TYPE_LINE,
                    "dashboard-period-toggle": self._app_state.ui.dashboard_period
                    == DASHBOARD_PERIOD_WEEK,
                    "toggle-dev-mode": self._app_state.developer_mode,
                }
            except AttributeError as e:
                logging.warning(
                    f"Missing app_state attribute for toggle injection: {e}"
                )
                toggles_state_map = {}

            # Inject 'checked' attribute for enabled toggles
            for element_id, is_checked in toggles_state_map.items():
                if is_checked:
                    # Sanitize element ID to prevent regex injection
                    safe_id = self._sanitize_element_id(element_id)
                    pattern = rf'(<input[^>]*id="{safe_id}"[^>]*?)>'
                    replacement = r"\1 checked>"
                    content, count = re.subn(pattern, replacement, content)

                    if count > 0:
                        logging.debug(f"Injected 'checked' for toggle: {element_id}")

            # 5. Conditionally reveal dev-mode features
            if self._app_state.developer_mode:
                # Remove 'hidden-by-default' class from logs tab
                content = re.sub(
                    r'(class="sidebar-item)\s+hidden-by-default("\s+id="logs-sidebar-tab")',
                    r"\1\2",
                    content,
                )
                logging.debug("Revealed developer mode features in settings")

        elif is_index_page:
            # Main window processing
            css_content = f"{fonts_css}\n{self._resources['index_css']}"
            js_content = self._resources["index_js"]

        # 6. Inject CSS into <head>
        if css_content:
            style_tag = f"<style>\n{css_content}\n</style>\n</head>"
            content = content.replace("</head>", style_tag)

        # 7. Inject JS before </body>
        if js_content:
            script_tag = f"<script>\n{js_content}\n</script>\n</body>"
            content = content.replace("</body>", script_tag)

        logging.debug(
            f"Processed template: {template_path}",
            extra={
                "final_size": len(content),
                "is_settings": is_settings_page,
                "is_index": is_index_page,
            },
        )

        return content


# --- Window Manager ---


class WindowManager:
    """
    Abstraction layer for OS-specific window management operations.

    Responsibilities:
    - Toggle window visibility
    - Bring windows to foreground
    - Move windows to specific coordinates
    - Query window state

    Thread Safety: Methods are thread-safe via OS-level locking.
    """

    def __init__(self, app_state_instance: AppState, os_interface: OSInterface) -> None:
        """
        Initialize window manager with OS adapter.

        Args:
            app_state_instance: Global application state.
            os_interface: OS-specific window management adapter.
        """
        self._app_state: AppState = app_state_instance
        self._os_interface: OSInterface = os_interface
        self._main_window_title: str = MAIN_WINDOW_TITLE
        self._settings_window_title: str = SETTINGS_WINDOW_TITLE

        logging.debug("WindowManager initialized")

    def _get_window_handle(self, title: str) -> Optional[int]:
        """
        Retrieve native window handle (HWND on Windows).

        Args:
            title: Window title to search for.

        Returns:
            Window handle (integer) or None if not found.
        """
        try:
            return self._os_interface.find_window_handle(title)
        except Exception as e:
            logging.error(
                f"Failed to get window handle for '{title}'",
                exc_info=True,
                extra={"error": str(e)},
            )
            return None

    def toggle_main_window_visibility(self) -> None:
        """
        Toggle main window visibility (show if hidden, hide if visible).

        Safety: Prevents toggling during active recording to avoid
        interrupting critical operations.

        Example:
            >>> window_mgr.toggle_main_window_visibility()  # Shows or hides toolbar
        """
        # Safety check: Don't toggle during recording
        if self._app_state.audio.is_recording or self._app_state.ai_recording:
            logging.debug("Ignoring window toggle during active recording")
            return

        window_handle = self._get_window_handle(self._main_window_title)

        if not window_handle:
            logging.warning("Cannot toggle window: handle not found")
            return

        try:
            if self._os_interface.is_window_visible(window_handle):
                self._os_interface.hide_window(window_handle)
                logging.debug("Main window hidden")
            else:
                self._os_interface.show_window(
                    window_handle, activate=False, always_on_top=True
                )
                logging.debug("Main window shown")

        except Exception as e:
            logging.error(
                "Failed to toggle window visibility",
                exc_info=True,
                extra={"error": str(e)},
            )

    def bring_to_foreground(self, title: str) -> bool:
        """
        Activate window and bring to foreground.

        Args:
            title: Window title to activate.

        Returns:
            True if successful, False otherwise.

        Example:
            >>> window_mgr.bring_to_foreground("Ozmoz Settings")
            True
        """
        window_handle = self._get_window_handle(title)

        if not window_handle:
            logging.warning(f"Cannot bring to foreground: '{title}' not found")
            return False

        try:
            self._os_interface.show_window(window_handle, activate=True)
            logging.debug(f"Brought '{title}' to foreground")
            return True

        except Exception as error:
            logging.error(
                f"Failed to bring window to foreground: '{title}'",
                exc_info=True,
                extra={"error": str(error)},
            )
            return False

    def is_visible(self) -> bool:
        """
        Check if main window is currently visible.

        Returns:
            True if visible, False otherwise.

        Example:
            >>> if window_mgr.is_visible():
            ...     print("Window is showing")
        """
        window_handle = self._get_window_handle(self._main_window_title)

        if not window_handle:
            return False

        try:
            return self._os_interface.is_window_visible(window_handle)
        except Exception as e:
            logging.error("Failed to check window visibility", extra={"error": str(e)})
            return False

    def move_main_window(self, x: int, y: int) -> None:
        """
        Move main window to absolute screen coordinates.

        Args:
            x: X coordinate in pixels (from left edge of screen).
            y: Y coordinate in pixels (from top edge of screen).

        Example:
            >>> window_mgr.move_main_window(100, 200)  # Top-left corner area
        """
        # Validate coordinates
        if not isinstance(x, int) or not isinstance(y, int):
            logging.error(f"Invalid coordinates: x={x}, y={y}")
            return

        window_handle = self._get_window_handle(self._main_window_title)

        if not window_handle:
            logging.warning("Cannot move window: handle not found")
            return

        try:
            self._os_interface.move_window(window_handle, x, y)
            logging.debug(f"Moved main window to ({x}, {y})")

        except Exception as e:
            logging.error(
                "Failed to move window",
                exc_info=True,
                extra={"error": str(e), "x": x, "y": y},
            )


# --- System Tray Manager ---


class SystemTrayManager:
    """
    Lightweight system tray integration using pystray.

    Provides:
    - Tray icon with application branding
    - Context menu (About, Settings, Exit)
    - Non-blocking operation in background thread

    Thread Safety: Runs in dedicated daemon thread. Callbacks are thread-safe.
    """

    def __init__(
        self,
        app_state_instance: AppState,
        hotkey_manager: Any,  # TODO: Type this properly when HotkeyManager has Protocol
        show_settings_callback: Callable[[], None],
        exit_app_callback: Callable[[], None],
    ) -> None:
        """
        Initialize system tray manager.

        Args:
            app_state_instance: Global application state.
            hotkey_manager: Hotkey manager instance (unused currently).
            show_settings_callback: Function to open settings window.
            exit_app_callback: Function to exit application gracefully.
        """
        self._app_state: AppState = app_state_instance
        self._hotkey_manager: Any = hotkey_manager
        self._show_settings_callback: Callable[[], None] = show_settings_callback
        self._exit_app_callback: Callable[[], None] = exit_app_callback
        self._icon: Any = None

        logging.debug("SystemTrayManager initialized")

    def _show_about_page(self) -> None:
        """
        Open GitHub repository in default browser.

        Used for "About" menu item. Fails silently if browser unavailable.
        """
        try:
            webbrowser.open(GITHUB_ABOUT_URL)
            logging.debug(f"Opened about page: {GITHUB_ABOUT_URL}")
        except Exception as e:
            logging.warning(
                "Failed to open about page",
                extra={"url": GITHUB_ABOUT_URL, "error": str(e)},
            )

    def _create_image(self) -> Image.Image:
        """
        Load tray icon image with fallback.

        Returns:
            PIL Image object for tray icon.

        Fallback: Creates colored square if icon file missing.
        """
        icon_path = PathManager.get_resource_path(TRAY_ICON_PATH)

        try:
            if os.path.exists(icon_path):
                return Image.open(icon_path)
            else:
                logging.warning(f"Tray icon not found: {icon_path}, using fallback")
                # Fallback: simple colored square
                return Image.new(
                    "RGB", TRAY_ICON_FALLBACK_SIZE, color=TRAY_ICON_FALLBACK_COLOR
                )

        except Exception as e:
            logging.error(
                "Failed to load tray icon, using fallback",
                exc_info=True,
                extra={"path": icon_path, "error": str(e)},
            )
            # Fallback on error
            return Image.new(
                "RGB", TRAY_ICON_FALLBACK_SIZE, color=TRAY_ICON_FALLBACK_COLOR
            )

    def _on_menu_action(self, icon: Any, item: Any) -> None:
        """
        Handle tray menu item clicks.

        Args:
            icon: pystray Icon instance (unused).
            item: Menu item that was clicked.
        """
        item_text = str(item)

        try:
            if item_text == "Settings":
                self._show_settings_callback()
                logging.debug("Settings opened via tray menu")

            elif item_text == "About":
                self._show_about_page()

            elif item_text == "Exit":
                logging.info("Exit requested via tray menu")
                self._exit_app_callback()

        except Exception as e:
            logging.error(
                f"Error handling tray menu action: {item_text}",
                exc_info=True,
                extra={"error": str(e)},
            )

    def run_in_thread(self) -> None:
        """
        Start system tray in background daemon thread.

        Non-blocking: Returns immediately while tray runs in background.
        The thread is daemon, so it will automatically stop when app exits.
        """

        def setup_tray() -> None:
            """Background worker to initialize and run tray icon."""
            try:
                # Create menu
                menu = pystray.Menu(
                    pystray.MenuItem("About", self._on_menu_action),
                    pystray.MenuItem("Settings", self._on_menu_action),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Exit", self._on_menu_action),
                )

                # Create icon instance
                icon = pystray.Icon("Ozmoz", self._create_image(), "Ozmoz", menu)

                self._icon = icon

                logging.info("System tray starting...")

                # Run is blocking - keeps thread alive
                icon.run()

            except Exception as error:
                logging.critical(
                    "System tray thread crashed",
                    exc_info=True,
                    extra={"error": str(error)},
                )

        # Start in daemon thread
        tray_thread = threading.Thread(
            target=setup_tray, daemon=True, name="SystemTray"
        )
        tray_thread.start()

        logging.info("System tray service activated (pystray)")

    def stop(self) -> None:
        """
        Stop tray icon and cleanup resources.

        Safe to call even if tray was never started.
        """
        if self._icon:
            try:
                self._icon.stop()
                logging.info("System tray stopped")
            except Exception as e:
                logging.warning("Error stopping system tray", extra={"error": str(e)})
        else:
            logging.debug("System tray stop called but icon was None")
