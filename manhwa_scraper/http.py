"""Client HTTP dengan retry, backoff, dan polite delay.

Version: 0.2.0
"""

import logging
import random
import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOGGER = logging.getLogger(__name__)

RETRYABLE_STATUS = {403, 408, 429, 500, 502, 503, 504}


def create_session():
    session = requests.Session()
    session.verify = False
    session.headers.update(
        {
            "User-Agent": "ManhwaSectionScraper/0.2.0 (personal use; Python requests)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "id-ID,id;q=0.9",
        }
    )
    return session


class HttpClient:
    def __init__(self, session=None, max_retries=3, backoff_base=2.0, delay_range=(1.0, 2.0)):
        self.session = session or create_session()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.delay_range = delay_range

    def get(self, url):
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=(10, 30))
                if response.status_code in RETRYABLE_STATUS:
                    raise requests.HTTPError(f"Status {response.status_code}")
                response.raise_for_status()
                return response.text
            except requests.RequestException as error:
                if attempt == self.max_retries:
                    LOGGER.warning("Gagal %s setelah %d percobaan: %s", url, attempt, error)
                    raise
                sleep = self.backoff_base**attempt + random.uniform(0, 1)
                LOGGER.warning(
                    "Percobaan %d/%d gagal untuk %s: %s (retry dalam %.1fs)",
                    attempt,
                    self.max_retries,
                    url,
                    error,
                    sleep,
                )
                time.sleep(sleep)

    def polite_delay(self):
        time.sleep(random.uniform(*self.delay_range))
