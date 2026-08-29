"""
SPIZDILI_VPN — Real-World Mbps Download Speed Test
Measures actual throughput through the active proxy tunnel using Cloudflare's global edge CDN.
"""

import time
import urllib.request
import logging
from typing import Optional, Callable

logger = logging.getLogger("speedtest")

# 2.5 MB chunk from Cloudflare CDN
SPEEDTEST_URL = "https://speed.cloudflare.com/__down?bytes=2500000"

def run_speed_test(proxy_url: Optional[str] = "http://127.0.0.1:20809", on_progress: Optional[Callable[[float], None]] = None) -> float:
    """Download test file through proxy and return download speed in Mbps."""
    try:
        handlers = []
        if proxy_url:
            handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
        opener = urllib.request.build_opener(*handlers)

        req = urllib.request.Request(SPEEDTEST_URL, headers={"User-Agent": "Mozilla/5.0 SPIZDILI-SpeedTest"})
        
        t0 = time.time()
        total_bytes = 0

        with opener.open(req, timeout=8.0) as resp:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total_bytes += len(chunk)
                elapsed = time.time() - t0
                if on_progress and elapsed > 0:
                    current_mbps = (total_bytes * 8) / (elapsed * 1_000_000)
                    on_progress(current_mbps)

        elapsed = time.time() - t0
        if elapsed <= 0:
            return 0.0

        mbps = (total_bytes * 8) / (elapsed * 1_000_000)
        logger.info("Speedtest completed: %.2f Mbps (%d bytes in %.2fs)", mbps, total_bytes, elapsed)
        return round(mbps, 1)
    except Exception as exc:
        logger.warning("Speedtest failed: %s", exc)
        return 0.0
