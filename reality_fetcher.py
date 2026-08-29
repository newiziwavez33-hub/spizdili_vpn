"""
Quality Open VLESS Reality Community Feed Fetcher & Live Traffic Tester.
Fetches high-quality open community feeds and verifies 100% working traffic via Xray before adding.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("reality_fetcher")

# High-quality actively updated open community feeds
COMMUNITY_FEEDS = [
    "https://raw.githubusercontent.com/snakem982/proxypool/main/source/v2ray-2.txt",
    "https://raw.githubusercontent.com/free18/v2ray/master/v.txt",
    "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/main/configs/de/vless.txt",
    "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/main/configs/nl/vless.txt",
    "https://raw.githubusercontent.com/ShatakVPN/ConfigForge-V2Ray/main/configs/us/vless.txt",
]

USER_SERVERS_JSON = Path.home() / ".config" / "wavez-vpn" / "wavez_servers.json"
PROFILES_DIR = Path.home() / ".config" / "wavez-vpn" / "profiles"
XRAY_BIN = "/usr/local/bin/xray-core"


def _verify_vless_live_traffic(item: tuple[int, dict[str, Any]], timeout: float = 2.5) -> Optional[dict[str, Any]]:
    """Test actual end-to-end data proxying through Xray on ephemeral port."""
    idx, s = item
    test_port = 10830 + (idx % 25)
    cfg_file = f"/tmp/verify_probe_{test_port}.json"

    stream: dict[str, Any] = {
        "network": s["network"],
        "security": "reality",
        "realitySettings": {
            "serverName": s["sni"],
            "publicKey": s["public_key"],
            "shortId": s["short_id"],
            "fingerprint": s.get("fingerprint", "firefox"),
        },
        "sockopt": {"mark": 51820},
    }

    if s["network"] == "grpc":
        stream["grpcSettings"] = {"serviceName": s.get("serviceName", "")}
    elif s["network"] == "ws":
        stream["wsSettings"] = {
            "path": s.get("ws_path", "/"),
            "headers": {"Host": s.get("ws_host", s["sni"])},
        }

    cfg = {
        "log": {"loglevel": "error"},
        "inbounds": [{"port": test_port, "listen": "127.0.0.1", "protocol": "socks"}],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": s["address"],
                            "port": s["port"],
                            "users": [
                                {
                                    "id": s["uuid"],
                                    "encryption": "none",
                                    "flow": s.get("flow", ""),
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": stream,
            }
        ],
    }

    proc = None
    try:
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        proc = subprocess.Popen(
            [XRAY_BIN, "run", "-c", cfg_file],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.4)

        t0 = time.perf_counter()
        res = subprocess.run(
            [
                "curl",
                "-s",
                "--socks5-hostname",
                f"127.0.0.1:{test_port}",
                "--max-time",
                str(timeout),
                "https://api.ipify.org",
            ],
            capture_output=True,
            text=True,
        )
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        if res.returncode == 0 and res.stdout.strip():
            s["latency"] = elapsed_ms
            s["proxied_ip"] = res.stdout.strip()
            return s
    except Exception as exc:
        logger.debug("Verification error on %s:%s: %s", s["address"], s["port"], exc)
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if os.path.exists(cfg_file):
            try:
                os.remove(cfg_file)
            except Exception:
                pass
    return None


def fetch_and_test_reality_servers(
    max_servers: int = 15,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> list[dict[str, Any]]:
    """Fetch open feeds, extract VLESS Reality candidates, and verify live proxy traffic."""
    if progress_cb:
        progress_cb("Загрузка проверенных баз серверов…")

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for feed_url in COMMUNITY_FEEDS:
        try:
            req = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "v2rayN/6.23 SPIZDILI_VPN/1.0.3"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
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
                    net = qs.get("type", ["tcp"])[0]
                    fp = qs.get("fp", ["firefox"])[0]

                    if not (addr and port and uuid and pbk and sni):
                        continue

                    key = (addr, port)
                    if key in seen:
                        continue
                    seen.add(key)

                    frag = urllib.parse.unquote(u.fragment).strip()
                    candidates.append({
                        "raw_name": frag,
                        "address": addr,
                        "port": port,
                        "uuid": uuid,
                        "public_key": pbk,
                        "short_id": sid,
                        "sni": sni,
                        "flow": flow,
                        "network": net,
                        "fingerprint": fp,
                        "serviceName": qs.get("serviceName", [""])[0],
                        "ws_path": qs.get("path", ["/"])[0],
                        "ws_host": qs.get("host", [sni])[0],
                        "uri": line,
                    })

                    if len(candidates) >= max_servers * 4:
                        break
                except Exception:
                    pass

            if len(candidates) >= max_servers * 3:
                break
        except Exception as exc:
            logger.warning("Feed %s error: %s", feed_url, exc)

    if not candidates:
        logger.error("No candidates found in feeds")
        return []

    if progress_cb:
        progress_cb(f"Найдено {len(candidates)} кандидатов. Тестирование реального трафика…")

    # Run real traffic verification in parallel
    verified: list[dict[str, Any]] = []
    indexed_candidates = list(enumerate(candidates))

    with ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(_verify_vless_live_traffic, indexed_candidates):
            if res:
                verified.append(res)
                if progress_cb:
                    progress_cb(f"✓ Проверен сервер: {res['sni']} ({res['latency']}ms)")
                if len(verified) >= max_servers:
                    break

    verified.sort(key=lambda x: x["latency"])

    # Format into application standard server objects
    formatted_servers: list[dict[str, Any]] = []
    for idx, s in enumerate(verified, start=1):
        clean_sni = s["sni"].replace("www.", "").replace("api.", "")
        
        # Determine flag from fragment or defaults
        flag = "🌐"
        raw = s["raw_name"]
        for emoji in ("🇩🇪", "🇳🇱", "🇺🇸", "🇬🇧", "🇫🇷", "🇸🇪", "🇫🇮", "🇵🇱", "🇹🇷", "🇰🇿", "🇯🇵", "🇸🇬"):
            if emoji in raw:
                flag = emoji
                break
        if flag == "🌐":
            if "us" in raw.lower() or "usa" in raw.lower():
                flag = "🇺🇸"
            elif "de" in raw.lower() or "germany" in raw.lower():
                flag = "🇩🇪"
            elif "nl" in raw.lower() or "netherlands" in raw.lower():
                flag = "🇳🇱"
            else:
                flag = "⚡"

        display_name = f"{flag} Облако #{idx} | {clean_sni} ({int(s['latency'])}ms)"
        ascii_name = f"Fresh-{idx}"

        stream_settings: dict[str, Any] = {
            "network": s["network"],
            "security": "reality",
            "realitySettings": {
                "serverName": s["sni"],
                "publicKey": s["public_key"],
                "shortId": s["short_id"],
                "fingerprint": s["fingerprint"],
            },
        }
        if s["network"] == "grpc":
            stream_settings["grpcSettings"] = {"serviceName": s.get("serviceName", "")}
        elif s["network"] == "ws":
            stream_settings["wsSettings"] = {
                "path": s.get("ws_path", "/"),
                "headers": {"Host": s.get("ws_host", s["sni"])},
            }

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
                    "streamSettings": stream_settings,
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
            "network": s["network"],
            "latency": int(s["latency"]),
            "uri": s["uri"],
            "full_config_json": json.dumps(full_config),
        })

    return formatted_servers


def save_servers_to_system(servers: list[dict[str, Any]]) -> int:
    """Save the verified servers to user database and generate Linux profiles."""
    if not servers:
        return 0

    USER_SERVERS_JSON.parent.mkdir(parents=True, exist_ok=True)
    existing_servers: list[dict[str, Any]] = []

    if USER_SERVERS_JSON.is_file():
        try:
            old_data = json.loads(USER_SERVERS_JSON.read_text(encoding="utf-8"))
            existing_servers = old_data.get("servers", [])
        except Exception:
            pass

    # Merge: prepend new verified cloud servers, keep previous non-cloud servers
    merged = servers + [s for s in existing_servers if not s.get("id", "").startswith("cloud-reality-")]
    USER_SERVERS_JSON.write_text(
        json.dumps({"count": len(merged), "servers": merged}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # In Linux: write profile .conf files
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    created_profiles = 0

    for s in servers:
        ascii_name = s.get("ascii_name") or s.get("id") or "Cloudflare-WARP"
        s["ascii_name"] = ascii_name
        conf_path = PROFILES_DIR / f"{ascii_name}.conf"
        
        if s.get("protocol") == "wireguard":
            priv_k = s.get("secret_key", "")
            pub_k = s.get("public_key", "")
            addrs = s.get("local_address", ["172.16.0.2/32"])
            addr_str = ", ".join(addrs) if isinstance(addrs, list) else str(addrs)
            conf_content = (
                f"# ===================================================================\n"
                f"# Cloudflare WARP Profile: {s.get('name')}\n"
                f"# Protocol: WireGuard\n"
                f"# ===================================================================\n\n"
                f"[Interface]\n"
                f"PrivateKey = {priv_k}\n"
                f"Address = {addr_str}\n"
                f"DNS = 1.1.1.1, 1.0.0.1\n\n"
                f"[Peer]\n"
                f"PublicKey = {pub_k}\n"
                f"Endpoint = {s.get('address')}:{s.get('port', 2408)}\n"
                f"AllowedIPs = 0.0.0.0/0, ::/0\n"
                f"PersistentKeepalive = 25\n"
            )
        else:
            conf_content = (
                f"# ===================================================================\n"
                f"# Incy Profile: {s.get('name')}\n"
                f"# Protocol: VLESS\n"
                f"# Endpoint: {s.get('address')}:{s.get('port')}\n"
                f"# UUID: {s.get('uuid', '')}\n"
                f"# SNI: {s.get('sni', '')}\n"
                f"# Reality PublicKey: {s.get('public_key', '')}\n"
                f"# ShortID: {s.get('short_id', '')}\n"
                f"# Flow: {s.get('flow', '')}\n"
                f"# Fingerprint: {s.get('fingerprint', 'chrome')}\n"
                f"# URI: {s.get('uri', '')}\n"
                f"# ===================================================================\n\n"
                f"[Interface]\n"
                f"PrivateKey = KJjdGNIpVYkyiZqGFyUPr0DDU5Y4znFkhd2fLlPLvlw=\n"
                f"Address = 10.0.0.2/32\n"
                f"DNS = 8.8.8.8, 8.8.4.4\n\n"
                f"[Peer]\n"
                f"PublicKey = 9QiBXCR/Iz6GRh6w9JO+oAKK0TyFcEGI9Fs9sywgqDs=\n"
                f"Endpoint = {s.get('address')}:{s.get('port')}\n"
                f"AllowedIPs = 0.0.0.0/0\n"
                f"PersistentKeepalive = 25\n"
            )
        conf_path.write_text(conf_content, encoding="utf-8")
        created_profiles += 1

    return created_profiles
