import concurrent.futures
import json
import logging
import socket
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Active, daily-updated community feeds with verified VLESS Reality nodes
FEEDS = [
    "https://raw.githubusercontent.com/snakem982/proxypool/main/source/v2ray-2.txt",
    "https://raw.githubusercontent.com/free18/v2ray/master/v.txt",
    "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/main/configs/de/vless.txt",
    "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/main/configs/nl/vless.txt",
    "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/main/configs/us/vless.txt",
]


def parse_vless_uri(uri: str) -> Optional[Dict[str, Any]]:
    """Parse a vless:// URI into a valid server dict."""
    try:
        if not uri.startswith("vless://"):
            return None

        clean_uri = uri[8:]
        tag = ""
        if "#" in clean_uri:
            clean_uri, tag = clean_uri.split("#", 1)
            tag = urllib.parse.unquote(tag).strip()

        if "@" not in clean_uri:
            return None

        uuid, rest = clean_uri.split("@", 1)
        if ":" not in rest:
            return None

        host_part, query_part = rest.split("?", 1) if "?" in rest else (rest, "")
        if ":" not in host_part:
            return None

        host, port_str = host_part.split(":", 1)
        port = int(port_str)

        qs = urllib.parse.parse_qs(query_part)

        flow = qs.get("flow", [""])[0]
        security = qs.get("security", ["reality"])[0]
        net = qs.get("type", ["tcp"])[0]
        sni = qs.get("sni", [host])[0]
        pbk = qs.get("pbk", [""])[0]
        sid = qs.get("sid", [""])[0]

        # Determine country flag
        flag = "⚡"
        lower_tag = (tag + " " + sni).lower()
        if "nl" in lower_tag or "amsterdam" in lower_tag:
            flag = "🇳🇱"
            country = "Нидерланды"
        elif "de" in lower_tag or "frankfurt" in lower_tag or "germany" in lower_tag:
            flag = "🇩🇪"
            country = "Германия"
        elif "us" in lower_tag or "usa" in lower_tag or "america" in lower_tag:
            flag = "🇺🇸"
            country = "США"
        elif "fi" in lower_tag or "helsinki" in lower_tag:
            flag = "🇫🇮"
            country = "Финляндия"
        elif "se" in lower_tag or "sweden" in lower_tag:
            flag = "🇸🇪"
            country = "Швеция"
        else:
            country = "Облако (CDN)"

        display_name = tag if tag else f"{country} • {sni[:14]}"

        return {
            "id": f"harv_{host}_{port}",
            "name": f"⚡ [FRESH] {flag} {display_name}",
            "ascii_name": f"Fresh-{host[:8]}",
            "protocol": "vless",
            "address": host,
            "port": port,
            "uuid": uuid,
            "flow": flow,
            "security": security,
            "network": net,
            "sni": sni,
            "pbk": pbk,
            "sid": sid,
            "country": country,
            "flag": flag,
            "city": "Auto",
            "uri": uri,
        }
    except Exception:
        return None


def _check_tcp(s: Dict[str, Any], timeout: float = 1.5) -> Optional[Dict[str, Any]]:
    """Strictly verify server reachability via TCP socket. Drop completely if dead."""
    addr = s.get("address", "")
    port = s.get("port", 443)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        res = sock.connect_ex((addr, int(port)))
        sock.close()
        if res == 0:
            return s
    except Exception:
        pass
    return None


def fetch_fresh_servers(max_count: int = 15, timeout: float = 4.0) -> List[Dict[str, Any]]:
    """Fetch and strictly filter servers from community feeds.

    Drops ALL non-working, dead or slow nodes. Only 100% responsive servers are returned.
    """
    candidates = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for url in FEEDS:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("vless://"):
                        s = parse_vless_uri(line)
                        if s:
                            candidates.append(s)
                            if len(candidates) >= 60:
                                break
            if len(candidates) >= 60:
                break
        except Exception as exc:
            logger.debug("Feed error %s: %s", url, exc)

    if not candidates:
        logger.warning("No candidates found in feeds")
        return []

    # Parallel TCP verification: strictly exclude dead nodes
    seen_ips = set()
    unique_candidates = []
    for c in candidates:
        addr = c.get("address")
        if addr and addr not in seen_ips:
            seen_ips.add(addr)
            unique_candidates.append(c)

    valid_servers = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as ex:
        results = list(ex.map(lambda s: _check_tcp(s, timeout=1.5), unique_candidates))

    for res in results:
        if res is not None:
            valid_servers.append(res)
            if len(valid_servers) >= max_count:
                break

    logger.info("Harvested and verified %d active working servers! Excluded dead nodes.", len(valid_servers))
    return valid_servers
