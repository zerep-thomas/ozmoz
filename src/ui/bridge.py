import numpy as np
import json
from PySide6.QtCore import QObject, Signal, Property, Slot, QUrl
from PySide6.QtGui import QGuiApplication, QDesktopServices
from datetime import datetime, timedelta
import logging

from src.audio.local_audio import local_whisper
from src.core.system import global_executor

logger = logging.getLogger(__name__)


class UIBridge(QObject):
    activeChanged = Signal(bool)
    levelsChanged = Signal(list)
    showSettingsWindow = Signal()

    statsChanged = Signal()
    changelogChanged = Signal()
    shortcutsChanged = Signal()
    historyChanged = Signal()
    vocabularyChanged = Signal()

    settingsChanged = Signal()
    updateStatusChanged = Signal(str, str)
    modeChanged = Signal()
    credentialsChanged = Signal()

    downloadLocalModelStatusChanged = Signal(str)
    downloadProgressChanged = Signal(float)

    visualizerErrorChanged = Signal(str)
    navigateToConfig = Signal()
    navigateToDefaultMode = Signal()

    showDownloadModalRequested = Signal(str)
    showUpdateModalRequested = Signal(str, str)

    processingChanged = Signal(bool)

    def __init__(self, app_state, event_bus, cred_manager,
                 stats_manager=None, changelog_manager=None, hist_manager=None,
                 vocab_manager=None, settings_manager=None, update_manager=None,
                 mode_manager=None):
        super().__init__()
        self.app_state = app_state
        self.cred_manager = cred_manager
        self.stats_manager = stats_manager
        self.changelog_manager = changelog_manager
        self.hist_manager = hist_manager
        self.vocab_manager = vocab_manager
        self.settings_manager = settings_manager
        self.update_manager = update_manager
        self.mode_manager = mode_manager

        self._active = False
        self._processing = False
        self.NUM_BARS = 9
        self._levels = [2.0] * self.NUM_BARS
        self._smooth = [0.0] * self.NUM_BARS
        self._run_max = 1.0
        self._startup_frames = 0
        self._stats = {"avgSpeed": "0 WPM", "wordsThisWeek": "0", "timeSaved": "0 minutes"}
        self._changelog = []
        self._history_list = []

        if self.stats_manager and self.changelog_manager:
            self.refresh_home_data()

        event_bus.subscribe("recording_started", self.on_recording_started)
        event_bus.subscribe("recording_stopped", self.on_recording_stopped)
        event_bus.subscribe("audio_frame", self.on_audio_frame)
        event_bus.subscribe("history_updated", self.on_history_updated)
        event_bus.subscribe("vocabulary_updated", self.on_vocabulary_updated)
        event_bus.subscribe("visualizer_error", self.on_visualizer_error)

        event_bus.subscribe("settings_updated", lambda d: self.settingsChanged.emit())
        event_bus.subscribe("mode_updated", lambda d: self.modeChanged.emit())

        event_bus.subscribe("processing_started", self.on_processing_started)
        event_bus.subscribe("processing_finished", self.on_processing_finished)

        event_bus.subscribe("update_check_started", lambda d: self.updateStatusChanged.emit("checking", "Checking..."))
        event_bus.subscribe("update_available", self.on_update_available)
        event_bus.subscribe("update_not_available", lambda d: self.updateStatusChanged.emit("up_to_date", "You are up to date"))
        event_bus.subscribe("update_check_failed", lambda d: self.updateStatusChanged.emit("error", "Check failed"))

    def on_processing_started(self, data):
        self._processing = True
        self.processingChanged.emit(self._processing)

    def on_processing_finished(self, data):
        self._processing = False
        self.processingChanged.emit(self._processing)

    @Property(bool, notify=processingChanged)
    def processing(self):
        return self._processing

    @Slot(str)
    def requestShowDownloadModal(self, modelName):
        self.showDownloadModalRequested.emit(modelName)

    @Slot(str, result=bool)
    def isLocalModelInstalled(self, model_name):
        return local_whisper.is_installed(model_name)

    @Slot(str)
    def downloadLocalModel(self, model_name):
        self.downloadLocalModelStatusChanged.emit("downloading")
        self.downloadProgressChanged.emit(0.0)

        def _progress_cb(percentage):
            self.downloadProgressChanged.emit(percentage)

        def _worker():
            success = local_whisper.download(model_name, progress_callback=_progress_cb)
            if success:
                self.downloadLocalModelStatusChanged.emit("done")
                self.modeChanged.emit()
            else:
                self.downloadLocalModelStatusChanged.emit("error")

        global_executor.submit(_worker)

    @Property(str, notify=modeChanged)
    def installedLocalModelsJson(self):
        installed = []
        for m in ["Local Whisper Base", "Local Whisper Small", "Local Whisper Turbo", "Local Distil-Whisper (EN)"]:
            if local_whisper.is_installed(m):
                installed.append(m)
        return json.dumps(installed)

    @Slot(str, result=bool)
    def deleteLocalModel(self, model_name):
        success = local_whisper.delete_model(model_name)
        if success:
            self.modeChanged.emit()
        return success

    @Property(str, notify=modeChanged)
    def defaultModePreset(self):
        return self.mode_manager.get_mode("default").get("preset", "Voice to text") if self.mode_manager else "Voice to text"

    @Slot(str)
    def setDefaultModePreset(self, val):
        if self.mode_manager:
            self.mode_manager.update_mode("default", "preset", val)

    @Property(str, notify=modeChanged)
    def defaultModeLanguage(self):
        return self.mode_manager.get_mode("default").get("language", "English") if self.mode_manager else "English"

    @Slot(str)
    def setDefaultModeLanguage(self, val):
        if self.mode_manager:
            self.mode_manager.update_mode("default", "language", val)

    @Property(str, notify=modeChanged)
    def defaultModeVoiceModel(self):
        return self.mode_manager.get_mode("default").get("voice_model", "Whisper V3 Turbo") if self.mode_manager else "Whisper V3 Turbo"

    @Slot(str)
    def setDefaultModeVoiceModel(self, val):
        if self.mode_manager:
            self.mode_manager.update_mode("default", "voice_model", val)

    @Slot(str, str, str)
    def applyActiveModeSettings(self, preset, language, voice_model):
        if self.mode_manager:
            self.mode_manager.update_mode("system", "active_preset", preset)
            self.mode_manager.update_mode("system", "active_language", language)
            self.mode_manager.update_mode("system", "active_model", voice_model)

    @Slot()
    def setActiveDefaultMode(self):
        if self.mode_manager:
            self.mode_manager.update_mode("system", "current_active", "default")

    @Property(str, notify=modeChanged)
    def customModesJson(self):
        if not self.mode_manager:
            return "[]"
        modes = self.mode_manager.get_custom_modes()
        mode_list = []
        for mode_id, data in modes.items():
            mode_list.append({
                "id": mode_id,
                "modeName": data.get("name", mode_id),
                "modePreset": data.get("preset", "Voice to text"),
                "modeLanguage": data.get("language", "English"),
                "modeVoiceModel": data.get("voice_model", "Whisper V3 Turbo")
            })
        return json.dumps(mode_list)

    @Slot(str, str, str, str, str)
    def addCustomMode(self, mode_id, name, preset, language, voice_model):
        if self.mode_manager:
            self.mode_manager.add_mode(mode_id, name, preset, language, voice_model)

    @Slot(str, str, str)
    def updateCustomMode(self, mode_id, key, value):
        if self.mode_manager:
            self.mode_manager.update_mode(mode_id, key, value)

    @Slot(str)
    def removeCustomMode(self, mode_id):
        if self.mode_manager:
            self.mode_manager.delete_mode(mode_id)

    @Property(str, notify=modeChanged)
    def activeModeId(self):
        if not self.mode_manager:
            return "default"
        return self.mode_manager.get_mode("system").get("current_active", "default")

    @Slot(str)
    def setActiveModeId(self, mode_id):
        if self.mode_manager:
            self.mode_manager.update_mode("system", "current_active", mode_id)
            m = self.mode_manager.get_mode(mode_id)
            self.applyActiveModeSettings(
                m.get("preset", "Voice to text"),
                m.get("language", "English"),
                m.get("voice_model", "Whisper V3 Turbo")
            )

    @Property(bool, notify=settingsChanged)
    def playSounds(self):
        return self.settings_manager.get("play_sounds", True) if self.settings_manager else True

    @Slot(bool)
    def setPlaySounds(self, checked):
        if self.settings_manager:
            self.settings_manager.set("play_sounds", checked)

    @Property(bool, notify=settingsChanged)
    def autoCheckUpdates(self):
        return self.settings_manager.get("auto_check_updates", True) if self.settings_manager else True

    @Slot(bool)
    def setAutoCheckUpdates(self, checked):
        if self.settings_manager:
            self.settings_manager.set("auto_check_updates", checked)

    @Slot()
    def checkUpdatesNow(self):
        if self.update_manager:
            self.update_manager.check_for_updates()

    @Slot()
    def openUpdateUrl(self):
        if self.update_manager and self.update_manager.release_url:
            QDesktopServices.openUrl(QUrl(self.update_manager.release_url))

    @Property(str, notify=vocabularyChanged)
    def vocabularyListJson(self):
        words = self.vocab_manager.get_words() if self.vocab_manager else []
        return json.dumps(words)

    @Slot(str)
    def addVocabularyWord(self, word):
        if self.vocab_manager:
            self.vocab_manager.add_word(word)

    @Slot(int)
    def removeVocabularyWord(self, index):
        if self.vocab_manager:
            self.vocab_manager.remove_word(index)

    def on_vocabulary_updated(self, data):
        self.vocabularyChanged.emit()

    def refresh_home_data(self):
        if self.stats_manager and self.changelog_manager:
            self._stats = self.stats_manager.get_home_stats()
            self._changelog = self.changelog_manager.get_changelog()
            self.statsChanged.emit()
            self.changelogChanged.emit()
        if self.hist_manager:
            self.refresh_history_data()

    def refresh_history_data(self):
        raw_history = self.hist_manager.get_all()
        raw_history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        months_en = ["", "January", "February", "March", "April", "May", "June",
                     "July", "August", "September", "October", "November", "December"]

        formatted = []
        for item in raw_history:
            ts_str = item.get("timestamp", "")
            try:
                dt_obj = datetime.fromisoformat(ts_str)
                dt_date = dt_obj.date()
                if dt_date == today:
                    date_group = "Today"
                elif dt_date == yesterday:
                    date_group = "Yesterday"
                else:
                    date_group = f"{dt_obj.day} {months_en[dt_obj.month]} {dt_obj.year}"
                details_date = f"{dt_obj.day} {months_en[dt_obj.month]} {dt_obj.year} at {dt_obj.strftime('%H:%M')}"
            except Exception:
                date_group = "Unknown Date"
                details_date = ""

            text = item.get("text", "")
            short_text = text[:80] + "..." if len(text) > 80 else text
            entry_id = item.get("id", ts_str)

            formatted.append({
                "entryId": entry_id,
                "dateGroup": date_group,
                "fullText": text,
                "shortText": short_text,
                "detailsDate": details_date,
                "language": item.get("language", "Unknown"),
                "method": item.get("method", "groq-whisper-large-v3-turbo"),
                "audioDuration": item.get("audio_duration_sec", 0),
                "transcriptionDuration": item.get("processing_time_sec", 0)
            })

        self._history_list = formatted
        self.historyChanged.emit()

    def on_history_updated(self, data):
        self.refresh_home_data()

    @Property(str, notify=historyChanged)
    def historyListJson(self):
        return json.dumps(self._history_list)

    @Slot(str)
    def deleteHistoryEntry(self, entry_id):
        if self.hist_manager:
            self.hist_manager.delete_entry(entry_id)

    @Slot()
    def clearAllHistory(self):
        if self.hist_manager:
            try:
                self.hist_manager.filepath.write_text("[]", encoding="utf-8")
                if self.hist_manager.event_bus:
                    self.hist_manager.event_bus.publish("history_updated", None)
                self.refresh_home_data()
            except Exception as e:
                logger.error(f"Error clearing history: {e}")

    @Slot(str)
    def copyToClipboard(self, text):
        QGuiApplication.clipboard().setText(text)

    @Property(str, notify=statsChanged)
    def statAvgSpeed(self):
        return self._stats["avgSpeed"]

    @Property(str, notify=statsChanged)
    def statWordsThisWeek(self):
        return self._stats["wordsThisWeek"]

    @Property(str, notify=statsChanged)
    def statTimeSaved(self):
        return self._stats["timeSaved"]

    @Property(list, notify=changelogChanged)
    def changelogList(self):
        return self._changelog

    @Property(str, notify=shortcutsChanged)
    def recordShortcut1(self):
        combo = self.app_state.hotkeys.get("record_toggle", "ctrl+space")
        parts = [p.capitalize() for p in combo.split("+")]
        return parts[0] if len(parts) > 0 else ""

    @Property(str, notify=shortcutsChanged)
    def recordShortcut2(self):
        combo = self.app_state.hotkeys.get("record_toggle", "ctrl+space")
        parts = [p.capitalize() for p in combo.split("+")]
        return parts[1] if len(parts) > 1 else ""

    @Property(str, notify=credentialsChanged)
    def groqKey(self):
        return self.cred_manager.get_api_key("groq") or ""

    @Property(bool, notify=credentialsChanged)
    def hasGroqKeyProp(self):
        return bool(self.cred_manager.get_api_key("groq"))

    @Slot(str)
    def saveGroqKey(self, key):
        self.cred_manager.save_api_key("groq", key)

        if self.mode_manager:
            if key and key.strip():
                current_model = self.mode_manager.get_mode("default").get("voice_model", "Select a model...")
                if current_model == "Select a model...":
                    self.mode_manager.update_mode("default", "voice_model", "Whisper V3 Turbo")
            else:
                self.mode_manager.update_mode("default", "voice_model", "Select a model...")

                sys_cfg = self.mode_manager.get_mode("system")
                active_model = sys_cfg.get("active_model", "Select a model...")
                if active_model in ["Whisper V3", "Whisper V3 Turbo"]:
                    self.mode_manager.update_mode("system", "active_model", "Select a model...")

        self.credentialsChanged.emit()
        self.modeChanged.emit()

    def on_update_available(self, data):
        self.updateStatusChanged.emit("available", f"Version {data['version']} available!")
        self.showSettingsWindow.emit()
        self.showUpdateModalRequested.emit(data['version'], data['url'])

    @Slot()
    def openSettings(self):
        self.showSettingsWindow.emit()

    @Slot()
    def requestNavigateToConfig(self):
        self.navigateToConfig.emit()

    def on_visualizer_error(self, data):
        self.visualizerErrorChanged.emit(str(data))
        self.showSettingsWindow.emit()
        self.navigateToDefaultMode.emit()

    def on_recording_started(self, data):
        self._active = True
        self._startup_frames = 5
        self.activeChanged.emit(True)

    def on_recording_stopped(self, data):
        self._active = False
        self._levels = [2.0] * self.NUM_BARS
        self.activeChanged.emit(False)
        self.levelsChanged.emit(self._levels)

    def on_audio_frame(self, audio_data: bytes):
        try:
            self._process_audio_frame(audio_data)
        except Exception:
            logger.exception("on_audio_frame failed unexpectedly")

    def _process_audio_frame(self, audio_data: bytes):
        if not self._active:
            return
        data = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(data ** 2)))

        if rms < 20.0:
            self._smooth = [s * 0.55 for s in self._smooth]
            self._levels = [max(2.0, float(s * 26)) for s in self._smooth]
            self.levelsChanged.emit(self._levels)
            return

        N = len(data)
        fft = np.abs(np.fft.rfft(data * np.hanning(N)))

        bin_hz = (16000 / 2) / len(fft)
        lo = int(100 / bin_hz)
        hi = int(4000 / bin_hz)
        speech = fft[lo:hi]

        band_count = len(speech)
        if band_count > 0:
            log_edges = np.round(np.logspace(0, np.log10(band_count), self.NUM_BARS + 1)).astype(int)
            log_edges[0] = 0
            log_edges[-1] = band_count
            for i in range(1, len(log_edges)):
                if log_edges[i] <= log_edges[i - 1]:
                    log_edges[i] = log_edges[i - 1] + 1
        else:
            log_edges = np.linspace(0, 0, self.NUM_BARS + 1).astype(int)

        levels_freq = []
        for i in range(self.NUM_BARS):
            band = speech[log_edges[i]:log_edges[i + 1]]
            raw_val = float(np.sum(band)) if len(band) else 0.0
            compressed = raw_val ** 0.5
            levels_freq.append(compressed)

        peak_freq = max(levels_freq) if max(levels_freq) > 0 else 1e-6
        self._run_max = max(self._run_max * 0.995, peak_freq)
        norm_freq = [l / self._run_max for l in levels_freq]

        norm_rms = min(1.0, (rms / 32768.0) * 15)

        if self._startup_frames > 0:
            self._startup_frames -= 1
            norm_rms = min(norm_rms, 0.15)

        bell_curve = [0.50, 0.65, 0.80, 0.90, 1.0, 0.90, 0.80, 0.65, 0.50]

        final_levels = []
        for i in range(self.NUM_BARS):
            blended = (norm_freq[i] * 0.6) + (norm_rms * 0.4)
            final_levels.append(blended * bell_curve[i])

        self._smooth = [
            0.75 * n + 0.25 * s if n > s else 0.20 * n + 0.80 * s
            for n, s in zip(final_levels, self._smooth)
        ]

        self._levels = [min(26.0, max(2.0, float(s * 26))) for s in self._smooth]
        self.levelsChanged.emit(self._levels)

    @Property(bool, notify=activeChanged)
    def active(self):
        return self._active

    @Property(list, notify=levelsChanged)
    def levels(self):
        return self._levels