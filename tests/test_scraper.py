"""Test scraper — versi 1.0.0.

Sumber data berubah dari HTML Komiku ke API JSON Shinigami. Test lama yang
menguji parsing DOM Komiku sudah usang; suite ini didelegasikan ke
test_scraper_v1.py agar import yang berubah tidak memecahkan apa pun dan
seluruh behavior scraper baru tetap teruji.
"""

from test_scraper_v1 import (  # noqa: F401
    TestDeduplicate,
    TestScraper,
    TestStripInternal,
)

__all__ = ["TestDeduplicate", "TestScraper", "TestStripInternal"]