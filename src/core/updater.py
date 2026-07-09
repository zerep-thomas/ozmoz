import logging
import requests

from src.core.config import AppConfig
from src.core.system import global_executor

logger = logging.getLogger(__name__)


def _version_tuple(v: str) -> tuple:
    return tuple(int(p) for p in v.lstrip('v').split(".") if p.isdigit())


class UpdateManager:
    """Checks for new application versions on GitHub."""

    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.latest_version = None
        self.release_url = None
        self.is_checking = False
        self.last_check_result = None

    def check_for_updates(self):
        if self.is_checking:
            return

        self.is_checking = True
        self.event_bus.publish("update_check_started")

        def _check_worker():
            try:
                response = requests.get(AppConfig.GITHUB_RELEASES_URL, timeout=10)
                response.raise_for_status()
                data = response.json()

                self.latest_version = data.get("tag_name", "").lstrip('v')
                self.release_url = data.get("html_url")

                if self.latest_version and self.release_url:
                    if _version_tuple(self.latest_version) > _version_tuple(AppConfig.VERSION):
                        self.last_check_result = "available"
                        self.event_bus.publish("update_available", {
                            "version": self.latest_version,
                            "url": self.release_url
                        })
                    else:
                        self.last_check_result = "up_to_date"
                        self.event_bus.publish("update_not_available")
                else:
                    raise ValueError("Invalid API response format")

            except requests.RequestException:
                logger.exception("Update check failed (network error)")
                self.last_check_result = "error"
                self.event_bus.publish("update_check_failed")
            except Exception:
                logger.exception("Update check failed (processing error)")
                self.last_check_result = "error"
                self.event_bus.publish("update_check_failed")
            finally:
                self.is_checking = False
                self.event_bus.publish("update_check_finished")

        global_executor.submit(_check_worker)