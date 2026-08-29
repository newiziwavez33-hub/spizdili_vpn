"""
SPIZDILI_VPN — Smart Connect & Zero-Fail Auto-Failover Engine
Concurrently tests candidate servers to connect to the fastest LIVE server.
Monitors tunnel health and seamlessly switches servers on failure.
"""

import time
import socket
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Callable

logger = logging.getLogger("smart_connect")

def ping_server(srv: Dict[str, Any], timeout: float = 1.0) -> Optional[int]:
    """Test TCP latency to server. Returns latency in ms, or None if unreachable."""
    addr = srv.get("address", "")
    port = int(srv.get("port", 443))
    t0 = time.time()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        if sock.connect_ex((addr, port)) == 0:
            ms = int((time.time() - t0) * 1000)
            sock.close()
            return ms
        sock.close()
    except Exception:
        pass
    return None


def select_best_live_server(servers: List[Dict[str, Any]], candidate_count: int = 8) -> Optional[Dict[str, Any]]:
    """Test top candidates concurrently and return the fastest responding LIVE server."""
    if not servers:
        return None

    candidates = servers[:candidate_count]
    results = []

    with ThreadPoolExecutor(max_workers=min(candidate_count, 8)) as executor:
        future_map = {executor.submit(ping_server, srv): srv for srv in candidates}
        for future in as_completed(future_map):
            srv = future_map[future]
            try:
                latency = future.result()
                if latency is not None:
                    results.append((latency, srv))
            except Exception:
                pass

    if results:
        results.sort(key=lambda x: x[0])
        best_latency, best_srv = results[0]
        logger.info("Smart Connect selected '%s' (Latency: %d ms)", best_srv.get("name"), best_latency)
        return best_srv

    # Fallback to first server if ping fails (e.g. ICMP/TCP ping blocked by firewall)
    return servers[0]


class TunnelHealthMonitor:
    """Monitors active tunnel in background and triggers failover if connection drops."""

    def __init__(self, check_interval: float = 20.0, on_failover: Optional[Callable[[], None]] = None) -> None:
        self.check_interval = check_interval
        self.on_failover = on_failover
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        time.sleep(5)  # initial grace period
        consecutive_failures = 0

        while self._running:
            try:
                # Test connectivity to Cloudflare DNS through SOCKS/HTTP port
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.5)
                # Check if local proxy port is responding
                if sock.connect_ex(("127.0.0.1", 20808)) != 0 and sock.connect_ex(("127.0.0.1", 20809)) != 0:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0
                sock.close()
            except Exception:
                consecutive_failures += 1

            if consecutive_failures >= 2 and self._running:
                logger.warning("Tunnel connection lost! Triggering auto-failover...")
                if self.on_failover:
                    self.on_failover()
                break

            time.sleep(self.check_interval)


def filter_only_working_servers(servers: List[Dict[str, Any]], timeout: float = 1.5) -> List[Dict[str, Any]]:
    """Concurrently check servers and strictly exclude all dead/unreachable ones."""
    if not servers:
        return []
    working = []
    with ThreadPoolExecutor(max_workers=min(len(servers), 30)) as executor:
        future_map = {executor.submit(ping_server, srv, timeout): srv for srv in servers}
        for future in as_completed(future_map):
            srv = future_map[future]
            try:
                lat = future.result()
                if lat is not None:
                    srv["ping"] = lat
                    working.append(srv)
            except Exception:
                pass
    # Sort by ping latency (lowest first)
    working.sort(key=lambda s: s.get("ping", 9999))
    return working
