"""
Open VLESS Reality Community Feed Fetcher & Tester for SPIZDILI_VPN.
Fetches, tests, filters by latency, and adds live VLESS Reality servers automatically.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import socket
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("reality_fetcher")

COMMUNITY_FEEDS = [
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/Splitted-By-Protocol/vless.txt",
    "https://raw.githubusercontent.com/LalatinaHub/Mineral/master/result/nodes",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
]

USER_SERVERS_JSON = Path.home() / ".config" / "wavez-vpn" / "wavez_servers.json"
PROFILES_DIR = Path.home() / ".config" / "wavez-vpn" / "profiles"


def fetch_and_test_reality_servers(
    max_servers: int = 25,
    timeout_per_probe: float = 1.2,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> list[dict[str, Any]]:
    """Fetch open feeds, extract VLESS Reality configs, ping them, and return top responsive servers."""
    if progress_cb:
        progress_cb("Загрузка открытых баз серверов…")

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for feed_url in COMMUNITY_FEEDS:
        try:
            req = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "v2rayN/6.23 SPIZDILI_VPN/1.0.3"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()

            try:
                decoded = base64.b64decode(raw).decode("utf-8", errors="ignore")
            except Exception:
                decoded = raw.decode("utf-8", errors="ignore")

            for line in decoded.splitlines():
                line = line.strip()
                if not line.startswith("vless://") or "security=reality" not in line:
                    continue

                try:
                    u = urllib.parse.urlparse(line)
                    qs = urllib.parse.parse_qs(u.query)
                    addr = u.hostname
                    port = u.port or 443
                    uuid = u.username
                    pbk = qs.get("pbk", [""])[0]
                    sid = qs.get("sid", [""])[0]
                    sni = qs.get("sni", [""])[0]
                    flow = qs.get("flow", [""])[0]
                    fp = qs.get("fp", ["firefox"])[0]

                    if not (addr and port and uuid and pbk and sni):
                        continue

                    key = (addr, port)
                    if key in seen:
                        continue
                    seen.add(key)

                    frag_name = urllib.parse.unquote(u.fragment).strip()
                    candidates.append({
                        "raw_name": frag_name,
                        "address": addr,
                        "port": port,
                        "uuid": uuid,
                        "public_key": pbk,
                        "short_id": sid,
                        "sni": sni,
                        "flow": flow,
                        "fingerprint": fp,
                        "uri": line,
                    })

                    if len(candidates) >= max_servers * 3:
                        break
                except Exception:
                    pass

            if len(candidates) >= max_servers * 2:
                break
        except Exception as exc:
            logger.warning("Feed %s failed: %s", feed_url, exc)

    if not candidates:
        logger.error("No VLESS Reality candidates found in feeds")
        return []

    if progress_cb:
        progress_cb(f"Найдено {len(candidates)} кандидатов. Проверка связи (пинг)…")

    def _ping(s: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            t0 = time.perf_counter()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout_per_probe)
            sock.connect((s["address"], s["port"]))
            sock.close()
            s["latency"] = round((time.perf_counter() - t0) * 1000, 1)
            return s
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=30) as ex:
        live = [s for s in ex.map(_ping, candidates) if s is not None]

    live.sort(key=lambda x: x["latency"])
    selected = live[:max_servers]

    # Format into standard server structures
    formatted_servers: list[dict[str, Any]] = []
    for idx, s in enumerate(selected, start=1):
        clean_sni = s["sni"].replace("www.", "").replace("api.", "")
        display_name = f"⚡ Облако #{idx} ({clean_sni}) 🌐"
        ascii_name = f"Cloud-{idx}"

        full_config = {
            "log": {"loglevel": "warning"},
            "outbounds": [
                {
                    "protocol": "vless",
                    "tag": "proxy",
                    "settings": {
                        "vnext": [
                            {
                                "address": s["address"],
                                "port": s["port"],
                                "users": [
                                    {
                                        "id": s["uuid"],
                                        "encryption": "none",
                                        "flow": s["flow"],
                                    }
                                ],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "serverName": s["sni"],
                            "publicKey": s["public_key"],
                            "shortId": s["short_id"],
                            "fingerprint": s["fingerprint"],
                        },
                    },
                },
                {"protocol": "freedom", "tag": "direct"},
                {"protocol": "blackhole", "tag": "block"},
            ],
            "dns": {
                "servers": ["https://1.1.1.1/dns-query", "8.8.8.8", "1.1.1.1"],
                "queryStrategy": "UseIPv4",
            },
        }

        formatted_servers.append({
            "id": f"cloud-reality-{idx}",
            "name": display_name,
            "ascii_name": ascii_name,
            "protocol": "VLESS",
            "address": s["address"],
            "port": s["port"],
            "uuid": s["uuid"],
            "public_key": s["public_key"],
            "sni": s["sni"],
            "short_id": s["short_id"],
            "flow": s["flow"],
            "fingerprint": s["fingerprint"],
            "security": "reality",
            "network": "tcp",
            "latency": int(s["latency"]),
            "uri": s["uri"],
            "full_config_json": json.dumps(full_config),
        })

    return formatted_servers


def save_servers_to_system(servers: list[dict[str, Any]]) -> int:
    """Save the fetched servers to user database and generate Linux profiles."""
    if not servers:
        return 0

    # 1. Update ~/.config/wavez-vpn/wavez_servers.json
    USER_SERVERS_JSON.parent.mkdir(parents=True, exist_ok=True)
    existing_servers: list[dict[str, Any]] = []

    if USER_SERVERS_JSON.is_file():
        try:
            old_data = json.loads(USER_SERVERS_JSON.read_text(encoding="utf-8"))
            existing_servers = old_data.get("servers", [])
        except Exception:
            pass

    # Merge: prepend new live cloud servers
    merged = servers + [s for s in existing_servers if not s.get("id", "").startswith("cloud-reality-")]
    USER_SERVERS_JSON.write_text(
        json.dumps({"count": len(merged), "servers": merged}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 2. In Linux: write profile .conf files to ~/.config/wavez-vpn/profiles/
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    created_profiles = 0

    for s in servers:
        conf_path = PROFILES_DIR / f"{s['ascii_name']}.conf"
        conf_content = (
            f"# ===================================================================\n"
            f"# Incy Profile: {s['name']}\n"
            f"# Protocol: VLESS\n"
            f"# Endpoint: {s['address']}:{s['port']}\n"
            f"# UUID: {s['uuid']}\n"
            f"# SNI: {s['sni']}\n"
            f"# Reality PublicKey: {s['public_key']}\n"
            f"# ShortID: {s['short_id']}\n"
            f"# Flow: {s['flow']}\n"
            f"# Fingerprint: {s['fingerprint']}\n"
            f"# URI: {s['uri']}\n"
            f"# ===================================================================\n\n"
            f"[Interface]\n"
            f"PrivateKey = KJjdGNIpVYkyiZqGFyUPr0DDU5Y4znFkhd2fLlPLvlw=\n"
            f"Address = 10.0.0.2/32\n"
            f"DNS = 8.8.8.8, 8.8.4.4\n\n"
            f"[Peer]\n"
            f"PublicKey = 9QiBXCR/Iz6GRh6w9JO+oAKK0TyFcEGI9Fs9sywgqDs=\n"
            f"Endpoint = {s['address']}:{s['port']}\n"
            f"AllowedIPs = 0.0.0.0/0\n"
            f"PersistentKeepalive = 25\n"
        )
        conf_path.write_text(conf_content, encoding="utf-8")
        created_profiles += 1

    return created_profiles
