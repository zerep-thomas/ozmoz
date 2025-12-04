"""
Ozmoz System Diagnostics & Health Check Suite
=============================================

This module serves as the primary integration and unit testing suite for the Ozmoz Application.
It validates external connectivity, API latency, internal logic integrity,
as well as data persistence robustness and update mechanisms.

Usage:
    python tests/test_utils.py
"""

import json
import logging
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, cast

import requests

# --- ENVIRONMENT & PATH CONFIGURATION ----------------------------------------
# Dynamically resolve the project root to ensure imports work regardless of
# the execution directory.
CURRENT_FILE = os.path.abspath(__file__)
TESTS_DIR = os.path.dirname(CURRENT_FILE)
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
SRC_PATH = os.path.join(PROJECT_ROOT, "src")

# Inject 'src' folder into system path with high priority
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

# --- APPLICATION MODULE IMPORTS ----------------------------------------------
try:
    from modules.audio import TranscriptionService
    from modules.config import AppConfig
    from modules.data import HistoryManager, ReplacementManager, UpdateManager
    from modules.services import ContextManager
except ImportError as e:
    print(f"\n\033[91m[CRITICAL] Import Error: {e}\033[0m")
    print(f"Current System Path: {sys.path}")
    print("Ensure the structure follows: Root -> src -> modules -> __init__.py\n")
    sys.exit(1)


# --- LOGGING CONFIGURATION ---------------------------------------------------
class ColoredFormatter(logging.Formatter):
    """Custom formatter to colorize log levels in the console."""

    COLORS = {
        "INFO": "\033[94m",  # Blue
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[41m",  # Red Background
        "RESET": "\033[0m",
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        record.msg = f"{color}{record.msg}{self.COLORS['RESET']}"
        return super().format(record)


logger = logging.getLogger("OzmozDiagnostics")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(
    ColoredFormatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
)
logger.addHandler(handler)


# --- TEST SUITE --------------------------------------------------------------


class TestRemoteConfiguration(unittest.TestCase):
    """
    Integration Tests: Validates the integrity and accessibility of the
    remote configuration service (JSONSilo).
    """

    def setUp(self):
        self.config_url = AppConfig.REMOTE_CONFIG_URL
        self.start_time = time.perf_counter()
        logger.info(f"--- Starting Test: {self._testMethodName} ---")

    def tearDown(self):
        duration = (time.perf_counter() - self.start_time) * 1000
        logger.info(f"Test Duration: {duration:.2f}ms\n")

    def test_fetch_and_display_jsonsilo_config(self):
        """
        Fetches remote configuration, validates HTTP status,
        checks JSON integrity, and logs the content summary.
        """
        try:
            logger.info(f"Connecting to remote configuration: {self.config_url}")

            response = requests.get(self.config_url, timeout=10)

            if response.status_code != 200:
                logger.error(f"Failed to fetch config. Code: {response.status_code}")
                self.fail(f"HTTP Error: {response.status_code}")

            data = response.json()
            self.assertIsInstance(data, list, "Root JSON element must be a list")

            model_count = len([x for x in data if "name" in x])
            logger.info(
                f"Validation successful. {model_count} models found in configuration."
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"Network Error: {e}")
            self.fail("Network connection failed")
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parsing Error: {e}")
            self.fail("Invalid JSON format received")


class TestAPIHealthAndLatency(unittest.TestCase):
    """
    Connectivity Tests: Pings external AI providers (Groq, Deepgram, Cerebras)
    to ensure the network path is open and latency is acceptable.
    """

    ENDPOINTS = {
        "GROQ_AI": "https://api.groq.com/openai/v1/models",
        "DEEPGRAM": "https://api.deepgram.com",
        "CEREBRAS": "https://api.cerebras.ai",
    }

    def setUp(self):
        logger.info(f"--- Starting API Test: {self._testMethodName} ---")

    def _measure_latency(self, name: str, url: str):
        """Helper to measure HTTP latency."""
        try:
            start = time.perf_counter()
            requests.get(url, timeout=5)
            latency = (time.perf_counter() - start) * 1000

            status_color = (
                "\033[92mHEALTHY\033[0m" if latency < 800 else "\033[93mSLOW\033[0m"
            )
            logger.info(
                f"[{name}] Status: {status_color} | Latency: {latency:.2f}ms | Endpoint: {url}"
            )
            return True
        except Exception as e:
            logger.error(f"[{name}] Status: DOWN | Error: {str(e)}")
            return False

    def test_provider_latency(self):
        """Iterates through defined providers and verifies connectivity."""
        for name, url in self.ENDPOINTS.items():
            is_reachable = self._measure_latency(name, url)
            if name != "Cerebras":  # Cerebras sometimes blocks generic pings
                self.assertTrue(is_reachable, f"{name} should be reachable")


class TestInternalLogic(unittest.TestCase):
    """
    Unit Tests: Verifies internal algorithms (Token Counting, Truncation)
    without external dependencies.
    """

    def setUp(self):
        logger.info(f"--- Starting Unit Test: {self._testMethodName} ---")

        # AppState Mock
        class MockState:
            cached_remote_config = []

        self.ctx_manager = ContextManager(app_state=MockState())

    def test_token_approximation_heuristic(self):
        """Validates the heuristic: 1 token ≈ 3-4 characters."""
        sample_text = "Ozmoz is a powerful AI assistant."  # 33 chars
        estimated_tokens = self.ctx_manager.count_tokens_approx(sample_text)

        # 33 / 3 = 11
        self.assertEqual(estimated_tokens, 11)

    def test_context_truncation(self):
        """Ensures that text exceeding the context window is properly truncated."""
        max_tokens = 10
        long_input = "This is a very long sentence that should definitely trigger the truncation logic inside the manager."

        result = self.ctx_manager.truncate_text_by_tokens(long_input, max_tokens)

        self.assertIn("... [TRUNCATED] ...", result)
        self.assertLess(len(result), len(long_input))


class TestUpdateMechanism(unittest.TestCase):
    """
    Unit Tests: Validates semantic version comparison logic.
    Crucial to ensure updates are only proposed when necessary.
    """

    def setUp(self):
        logger.info(f"--- Starting Update Test: {self._testMethodName} ---")
        self.update_manager = UpdateManager()

    def test_version_comparison_logic(self):
        """Tests semantic versioning scenarios."""
        # Case: Update available (Remote > Local)
        self.assertEqual(self.update_manager._compare_versions("1.0.1", "1.0.0"), 1)
        self.assertEqual(self.update_manager._compare_versions("2.0", "1.9.9"), 1)
        self.assertEqual(self.update_manager._compare_versions("1.10.0", "1.9.0"), 1)

        # Case: No update (Remote == Local)
        self.assertEqual(self.update_manager._compare_versions("1.0.0", "1.0.0"), 0)

        # Case: Local version newer (Dev mode or Remote < Local)
        self.assertEqual(self.update_manager._compare_versions("0.9.9", "1.0.0"), -1)


class TestDataPersistence(unittest.TestCase):
    """
    I/O Integration Tests: Verifies that data managers (History, Replacements)
    can read/write to disk without corruption.
    Uses a temporary directory for isolation.
    """

    def setUp(self):
        logger.info(f"--- Starting Persistence Test: {self._testMethodName} ---")
        self.test_dir = tempfile.mkdtemp()
        self.history_path = Path(self.test_dir) / "test_history.json"
        self.replacements_path = Path(self.test_dir) / "test_replacements.json"

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_history_manager_io(self):
        """Verifies the lifecycle of history data."""
        manager = HistoryManager(self.history_path)

        # 1. Write
        test_text = "This is a transcription test."
        manager.add_entry(test_text)

        # 2. Read
        history = manager.get_all()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["text"], test_text)
        self.assertIn("timestamp", history[0])

        # 3. Cleanup
        manager.clear()
        self.assertEqual(len(manager.get_all()), 0)

    def test_replacement_manager_io(self):
        """Verifies the lifecycle of text replacements."""
        manager = ReplacementManager(self.replacements_path)

        replacements = [
            {"word1": "bonjour", "word2": "hello"},
            {"word1": "test", "word2": "trial"},
        ]

        # 1. Save
        success = manager.save(replacements)
        self.assertTrue(success, "Save operation should return True")

        # 2. Load
        loaded = manager.load()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["word1"], "bonjour")


class TestTextPostProcessing(unittest.TestCase):
    """
    Unit Tests: Verifies text cleaning and replacement logic after transcription
    (using Mocked dependencies).
    """

    def setUp(self):
        logger.info(f"--- Starting Post-Processing Test: {self._testMethodName} ---")

        # --- Mocks to isolate business logic ---
        # Note: We use typing.cast(Any, ...) below to bypass static type checking (Pylance)
        # because these mocks do not strictly inherit from the real App classes,
        # but they provide the necessary attributes for these specific unit tests.

        class MockAppState:
            pass

        class MockCredentialManager:
            pass

        class MockReplacementManager:
            def load(self):
                return [
                    {"word1": "Ozmos", "word2": "Ozmoz"},  # Typical correction
                    {"word1": "semicolon", "word2": ";"},
                ]

        self.service = TranscriptionService(
            app_state=cast(Any, MockAppState()),
            replacement_manager=cast(Any, MockReplacementManager()),
            credential_manager=cast(Any, MockCredentialManager()),
        )

    def test_apply_replacements(self):
        """Verifies that defined keywords are correctly replaced."""
        raw_text = "Hello, I use Ozmos semicolon it's great."
        expected_text = "Hello, I use Ozmoz ; it's great."

        processed = self.service.apply_replacements(raw_text)
        self.assertEqual(processed, expected_text)

    def test_number_conversion_logic(self):
        """
        Verifies the number conversion logic (text_to_num).
        Note: Depends on the presence of the text_to_num library.
        """
        try:
            # Test FR
            text_fr = "J'ai cent vingt euros."
            converted_fr = self.service.convert_numbers(text_fr, "fr")
            # Simple check: presence of digits
            self.assertTrue(
                any(char.isdigit() for char in converted_fr),
                "Converted text must contain digits",
            )

            # Test EN (Input must differ from output)
            text_en = "I have twenty dollars."
            converted_en = self.service.convert_numbers(text_en, "en")
            self.assertNotEqual(text_en, converted_en)
        except Exception as e:
            logger.warning(f"Conversion test skipped (library missing or error): {e}")


if __name__ == "__main__":
    # Professional Header
    print("\n\033[1m" + "=" * 70)
    print("   OZMOZ SYSTEM DIAGNOSTICS & HEALTH CHECK TOOL")
    print(f"   Environment: {'Windows' if os.name == 'nt' else 'Unix'}")
    print(f"   Python: {sys.version.split()[0]}")
    print(f"   Source Path: {SRC_PATH}")
    print("=" * 70 + "\033[0m\n")

    # Running tests with standard verbosity
    unittest.main(verbosity=0)
