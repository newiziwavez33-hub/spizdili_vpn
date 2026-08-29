"""
SPIZDILI_VPN — Community Server Auto-Harvester
Downloads fresh, verified free VLESS Reality & WireGuard servers from public community sources.
Ensures the client always has active, working servers without manual user effort.
"""

import json
import re
import socket
import urllib.request
import urllib.parse
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("harvester")

MIRRORS = [
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/Splitted-By-Protocol/vless.txt",
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/vless",
    "https://raw.githubusercontent.com/yebekhe/TVC/main/subscriptions/xray/normal/vless"
]

def parse_vless_uri(uri: str) -> Optional[Dict[str, Any]]:
    """Parse a vless:// URI into a server dictionary."""
    if not uri.startswith("vless://"):
        return None
    try:
        raw = uri[8:]
        tag = ""
        if "#" in raw:
            raw, tag = raw.split("#", 1)
            tag = urllib.parse.unquote(tag).strip()

        if "@" not in raw:
            return None
        uuid, host_part = raw.split("@", 1)

        query = ""
        if "?" in host_part:
            host_part, query = host_part.split("?", 1)

        if ":" not in host_part:
            return None
        host, port_s = host_part.split(":", 1)
        port = int(port_s)

        params = urllib.parse.parse_qs(query)
        security = params.get("security", ["reality"])[0]
        flow = params.get("flow", [""])[0]
        sni = params.get("sni", [params.get("serverName", [""])[0]])[0]
        pbk = params.get("pbk", [params.get("publicKey", [""])[0]])[0]
        sid = params.get("sid", [params.get("shortId", [""])[0]])[0]
        net = params.get("type", ["tcp"])[0]

        # Only accept reality or tls
        if security not in ["reality", "tls"]:
            return None

        # Clean display name
        display_name = tag if tag else f"🌐 Community ({host})"

        return {
            "id": f"harv_{host}_{port}",
            "name": f"⚡ {display_name}",
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
            "country": "Облако (CDN)",
            "flag": "⚡",
            "city": "Auto"
        }
    except Exception:
        return None


def fetch_fresh_servers(max_count: int = 15, timeout: float = 4.0) -> List[Dict[str, Any]]:
    """Fetch fresh servers from community mirrors and verify TCP reachability."""
    candidates = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for url in MIRRORS:
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
                            if len(candidates) >= 40:
                                break
            if len(candidates) >= 40:
                break
        except Exception as exc:
            logger.debug("Mirror %s failed: %s", url, exc)

    # Test TCP reachability of candidates
    valid_servers = []
    seen_ips = set()
    for s in candidates:
        addr = s.get("address", "")
        port = s.get("port", 443)
        if addr in seen_ips:
            continue
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.2)
            if sock.connect_ex((addr, port)) == 0:
                valid_servers.append(s)
                seen_ips.add(addr)
            sock.close()
        except Exception:
            pass

        if len(valid_servers) >= max_count:
            break

    logger.info("Harvested %d active community servers!", len(valid_servers))
    return valid_servers
