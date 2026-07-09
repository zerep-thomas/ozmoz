import logging
import os
import subprocess
import sys
import ctypes
import threading

if sys.platform == 'win32' and getattr(sys, 'frozen', False):
    f = open(os.devnull, 'w')
    sys.stdout = f
    sys.stderr = f

log_file = os.path.join(
    os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__),
    "debug.log"
)

from src.core.config import SECRET_PATTERNS


class RedactSecretsFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.msg, str):
            msg = record.getMessage()
            for pattern in SECRET_PATTERNS:
                msg = pattern.sub(lambda m: m.group(0).replace(m.group(1), "REDACTED"), msg)
            record.msg = msg
            record.args = ()
        return True

file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.WARNING)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)

redact_filter = RedactSecretsFilter()
file_handler.addFilter(redact_filter)
stream_handler.addFilter(redact_filter)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from PySide6.QtQml import QQmlApplicationEngine
from pydub import AudioSegment

from src.audio.audio import AudioManager, TranscriptionManager, TranscriptionService
from src.core.config import AppConfig, AppState
from src.core.data import ChangelogManager, CredentialManager, HistoryManager, StatsManager
from src.core.modes import ModeManager
from src.core.settings import SettingsManager
from src.core.system import EventBus, HotkeyManager
from src.core.updater import UpdateManager
from src.core.utils import ClipboardManager, PathManager, SoundManager
from src.core.vocabulary import VocabularyManager
from src.ui.bridge import UIBridge

if sys.platform == 'win32':
    _orig_popen = subprocess.Popen

    def _patched_popen(*args, **kwargs):
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = 0x08000000
        return _orig_popen(*args, **kwargs)

    subprocess.Popen = _patched_popen

def set_windows11_titlebar_color(window, hex_color: str) -> None:
    try:
        hwnd = int(window.winId())
        h = hex_color.lstrip('#')
        r, g, b = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        color_ref = r | (g << 8) | (b << 16)
        DWMWA_CAPTION_COLOR = 35
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(ctypes.c_int(color_ref)), 4
        )
    except Exception:
        logger.debug("Could not set Windows 11 titlebar color", exc_info=True)


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon_path = PathManager.get_resource_path("src/ui/qml/icons/app_icon.png")
    app_icon = QIcon(icon_path)
    app.setWindowIcon(app_icon)

    app_state = AppState()
    event_bus = EventBus()

    settings_manager = SettingsManager(event_bus)
    update_manager = UpdateManager(event_bus)
    mode_manager = ModeManager(event_bus)
    sound_manager = SoundManager(settings_manager)
    clipboard_manager = ClipboardManager()
    cred_manager = CredentialManager()
    hist_manager = HistoryManager(event_bus)
    stats_manager = StatsManager(hist_manager)
    changelog_manager = ChangelogManager()
    vocab_manager = VocabularyManager(event_bus)

    audio_manager = AudioManager(app_state, sound_manager, event_bus, mode_manager, cred_manager)
    threading.Thread(target=audio_manager.initialize, daemon=True, name="AudioDriverWarmup").start()

    transcription_service = TranscriptionService(
        app_state, cred_manager, vocab_manager, mode_manager
    )
    transcription_manager = TranscriptionManager(
        app_state, audio_manager, sound_manager, stats_manager,
        hist_manager, transcription_service, clipboard_manager, event_bus
    )

    hotkey_manager = HotkeyManager(app_state, audio_manager, transcription_manager)
    hotkey_manager.app_state.hotkeys["record_toggle"] = "ctrl+space"
    hotkey_manager.register_all()

    bridge = UIBridge(
        app_state, event_bus, cred_manager, stats_manager,
        changelog_manager, hist_manager, vocab_manager,
        settings_manager, update_manager, mode_manager
    )

    tray_icon = QSystemTrayIcon()
    tray_icon.setIcon(app_icon)
    tray_icon.setToolTip("Ozmoz")

    menu = QMenu()
    settings_action = QAction("Settings", app)
    settings_action.triggered.connect(bridge.openSettings)
    menu.addAction(settings_action)
    menu.addSeparator()
    quit_action = QAction("Quit", app)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray_icon.setContextMenu(menu)
    tray_icon.show()

    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            bridge.openSettings()
    tray_icon.activated.connect(on_tray_activated)

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("uiBridge", bridge)
    geo = app.primaryScreen().availableGeometry()
    WIN_W, WIN_H = 130, 48
    engine.rootContext().setContextProperty("WIN_X", geo.x() + (geo.width() - WIN_W) // 2)
    engine.rootContext().setContextProperty("WIN_Y", geo.y() + geo.height() - WIN_H)
    engine.rootContext().setContextProperty("WIN_W", WIN_W)
    engine.rootContext().setContextProperty("WIN_H", WIN_H)

    visualizer_qml_path = PathManager.get_resource_path("src/ui/qml/visualizer.qml")
    settings_qml_path = PathManager.get_resource_path("src/ui/qml/settings.qml")

    engine.load(QUrl.fromLocalFile(visualizer_qml_path))
    engine.load(QUrl.fromLocalFile(settings_qml_path))

    if not engine.rootObjects():
        sys.exit(-1)

    app.root_windows = engine.rootObjects()

    visualizer_window = None
    for obj in app.root_windows:
        if hasattr(obj, "title") and obj.title() == "Ozmoz":
            set_windows11_titlebar_color(obj, "#494c4d")
            def make_visibility_callback(window):
                def callback(is_visible):
                    if is_visible:
                        set_windows11_titlebar_color(window, "#494c4d")
                return callback
            obj.visibleChanged.connect(make_visibility_callback(obj))
        else:
            visualizer_window = obj

    if settings_manager.get("auto_check_updates"):
        update_manager.check_for_updates()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()