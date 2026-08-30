#!/usr/bin/env python3
"""Subscription & Link Parser for Ubuntu VPN Client.

Supports:
- happ:// and incy:// custom subscription links and protocols
- HTTP/HTTPS subscription URLs (Happ, Incy, Marzban, Xray, 3X-UI, etc.)
- Base64 encoded subscription payloads
- wireguard:// and awg:// URIs
- Multi-server .conf bundles and JSON configs
"""

from __future__ import annotations

import base64
import json
import logging
import re
import socket
import subprocess
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger("subscription_parser")

# Amnezia obfuscation keys
AWG_KEYS = {"jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4"}


@dataclass
class ParsedServer:
    """Represents a parsed VPN server profile."""

    name: str
    protocol: str  # "WireGuard" or "AmneziaWG"
    conf_content: str
    endpoint: str = ""
    endpoint_ip: str = ""
    dns: str = ""
    is_amnezia: bool = False
    latency_ms: Optional[float] = None
    selected: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def test_latency(self, timeout: float = 3.0) -> Optional[float]:
        """Test ICMP/UDP latency to server endpoint."""
        if not self.endpoint:
            return None
        host = self.endpoint.rsplit(":", 1)[0].strip("[]")
        # Try ping
        try:
            res = subprocess.run(
                ["ping", "-c", "2", "-W", str(int(timeout)), host],
                capture_output=True,
                text=True,
                timeout=timeout + 2,
            )
            if res.returncode == 0:
                m = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", res.stdout)
                if not m:
                    m = re.search(r"round-trip min/avg/max(?:/\w+)? = [\d.]+/([\d.]+)/", res.stdout)
                if m:
                    self.latency_ms = round(float(m.group(1)), 1)
                    return self.latency_ms
        except Exception as exc:
            logger.debug("Ping error to %s: %s", host, exc)

        # Fallback TCP/UDP connect timing to port
        port = 51820
        if ":" in self.endpoint:
            try:
                port = int(self.endpoint.rsplit(":", 1)[1])
            except ValueError:
                pass
        try:
            import time
            start = time.perf_counter()
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.send(b"\x01\x00\x00\x00")  # probe
            elapsed = (time.perf_counter() - start) * 1000
            s.close()
            self.latency_ms = round(elapsed, 1)
            return self.latency_ms
        except Exception:
            pass
        return None


class SubscriptionParser:
    """Universal parser for VPN subscription links and configs."""

    USER_AGENT = "Happ/3.0.0 Incy/2.0.0 v2rayN/6.23 UbuntuVPN/1.0"

    @classmethod
    def fetch_url(cls, url: str, timeout: int = 15) -> tuple[str, dict[str, Any]]:
        """Fetch raw content and headers (subscription info/expiration) from a subscription URL."""
        url = cls._normalize_url(url)
        headers = {
            "User-Agent": cls.USER_AGENT,
            "Accept": "*/*",
        }
        resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
        resp.raise_for_status()

        # Parse Subscription-Userinfo header (e.g. upload=...; download=...; total=...; expire=...)
        user_info: dict[str, Any] = {}
        sub_hdr = resp.headers.get("Subscription-Userinfo") or resp.headers.get("subscription-userinfo") or ""
        if sub_hdr:
            for part in sub_hdr.split(";"):
                if "=" in part:
                    k, _, v = part.partition("=")
                    k_c = k.strip().lower()
                    v_c = v.strip()
                    try:
                        user_info[k_c] = int(v_c)
                    except ValueError:
                        user_info[k_c] = v_c

        # Parse profile-title
        raw_title = resp.headers.get("Profile-Title") or resp.headers.get("profile-title") or ""
        if raw_title.startswith("base64:"):
            try:
                user_info["profile_title"] = cls._try_b64decode(raw_title[7:])
            except Exception:
                user_info["profile_title"] = raw_title[7:]
        elif raw_title:
            user_info["profile_title"] = raw_title

        # Parse announce header
        raw_announce = resp.headers.get("Announce") or resp.headers.get("announce") or ""
        if raw_announce.startswith("base64:"):
            try:
                user_info["announce"] = cls._try_b64decode(raw_announce[7:])
            except Exception:
                user_info["announce"] = raw_announce[7:]
        elif raw_announce:
            user_info["announce"] = raw_announce

        # Parse support-url and web page
        if resp.headers.get("Support-Url"):
            user_info["support_url"] = resp.headers.get("Support-Url")
        if resp.headers.get("Profile-Web-Page-Url"):
            user_info["web_url"] = resp.headers.get("Profile-Web-Page-Url")

        return resp.text.strip(), user_info

    @classmethod
    def _normalize_url(cls, raw_url: str) -> str:
        """Convert happ:// or incy:// or sub:// links to https://."""
        raw_url = raw_url.strip()
        # Remove custom scheme wrappers
        for prefix in ("happ://", "incy://", "sub://", "sub64://"):
            if raw_url.lower().startswith(prefix):
                payload = raw_url[len(prefix):]
                # If payload is base64 encoded URL
                try:
                    decoded = cls._try_b64decode(payload)
                    if decoded.startswith("http://") or decoded.startswith("https://"):
                        return decoded
                except Exception:
                    pass
                if payload.startswith("http://") or payload.startswith("https://"):
                    return payload
                # Otherwise assume https://
                return "https://" + payload
        return raw_url

    @classmethod
    def _try_b64decode(cls, text: str) -> str:
        """Attempt safe base64 decoding with padding fix."""
        text = text.strip()
        padded = text + "=" * ((4 - len(text) % 4) % 4)
        for altchars in (None, b"-_"):
            try:
                decoded_bytes = base64.b64decode(padded.encode("ascii"), altchars=altchars)
                return decoded_bytes.decode("utf-8", errors="replace")
            except Exception:
                pass
        raise ValueError("Not valid base64")

    @classmethod
    def parse(cls, input_data: str, default_name_prefix: str = "Server") -> list[ParsedServer]:
        """Parse text input (URL, base64 blob, single/multiple configs, or URIs)."""
        input_data = input_data.strip()
        if not input_data:
            return []

        # 1. If it's a URL, fetch it
        if input_data.startswith("http://") or input_data.startswith("https://") or \
           input_data.startswith("happ://") or input_data.startswith("incy://"):
            try:
                fetched, user_info = cls.fetch_url(input_data)
                logger.info("Fetched %d bytes from subscription URL (User-Info: %s)", len(fetched), user_info)
                servers = cls.parse(fetched, default_name_prefix=cls._extract_host_name(input_data))
                for s in servers:
                    s.metadata["subscription_info"] = user_info
                return servers
            except Exception as exc:
                logger.error("URL fetch failed: %s", exc)
                raise RuntimeError(f"Ошибка запроса к серверу подписки ({exc})")

        # 2. Try Base64 decoding
        if not input_data.startswith("[Interface]") and not input_data.startswith("wireguard://") and not input_data.startswith("awg://"):
            try:
                decoded = cls._try_b64decode(input_data)
                if decoded and (len(decoded) > 10) and ("\n" in decoded or "://" in decoded or "[Interface]" in decoded):
                    logger.info("Successfully decoded base64 subscription payload")
                    return cls.parse(decoded, default_name_prefix=default_name_prefix)
            except Exception:
                pass

        # 3. Try parsing JSON format (e.g. Happ/Incy/Ghost VPN / Amnezia config JSON or Sing-box/Xray export array/dict)
        if (input_data.startswith("{") and input_data.endswith("}")) or (input_data.startswith("[") and input_data.endswith("]")):
            try:
                data = json.loads(input_data)
                if isinstance(data, list):
                    servers: list[ParsedServer] = []
                    for idx, item in enumerate(data):
                        if isinstance(item, dict):
                            servers.extend(cls._parse_json_config(item, f"{default_name_prefix}_{idx+1}"))
                        elif isinstance(item, str):
                            servers.extend(cls.parse(item, f"{default_name_prefix}_{idx+1}"))
                    if servers:
                        return servers
                elif isinstance(data, dict):
                    servers = cls._parse_json_config(data, default_name_prefix)
                    if servers:
                        return servers
            except Exception as exc:
                logger.debug("JSON parse attempt: %s", exc)

        # 3.1. Try parsing Clash / Mihomo YAML format (e.g. proxies list)
        if "proxies:" in input_data or "proxy-groups:" in input_data:
            try:
                servers = cls._parse_clash_yaml(input_data, default_name_prefix)
                if servers:
                    return servers
            except Exception as exc:
                logger.debug("Clash YAML parse attempt: %s", exc)

        # 4. Multi-line list of URIs or multiple [Interface] blocks
        servers: list[ParsedServer] = []

        # Check if contains multiple [Interface] blocks
        if input_data.count("[Interface]") > 1:
            conf_blocks = re.split(r"(?=\[Interface\])", input_data, flags=re.IGNORECASE)
            for idx, block in enumerate(conf_blocks):
                block = block.strip()
                if not block:
                    continue
                srv = cls._parse_conf_block(block, f"{default_name_prefix}_{idx+1}")
                if srv:
                    servers.append(srv)
            if servers:
                return servers

        # Line-by-line URI parsing (wireguard://, awg://, etc.)
        lines = [line.strip() for line in input_data.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            # Check if line is base64
            if not line.startswith("[") and "://" not in line and len(line) > 30:
                try:
                    dec_line = cls._try_b64decode(line)
                    if dec_line and dec_line != line:
                        sub_servers = cls.parse(dec_line, f"{default_name_prefix}_{idx+1}")
                        servers.extend(sub_servers)
                        continue
                except Exception:
                    pass

            if line.startswith("wireguard://") or line.startswith("awg://"):
                srv = cls._parse_wg_uri(line, f"{default_name_prefix}_{idx+1}")
                if srv:
                    servers.append(srv)
            elif line.startswith("vless://"):
                srv = cls._parse_vless_uri(line, f"{default_name_prefix}_{idx+1}")
                if srv:
                    servers.append(srv)
            elif line.startswith("trojan://") or line.startswith("ss://") or line.startswith("vmess://"):
                srv = cls._parse_generic_proxy_uri(line, f"{default_name_prefix}_{idx+1}")
                if srv:
                    servers.append(srv)
            elif line.startswith("[Interface]"):
                # Single conf block across remaining text
                srv = cls._parse_conf_block(input_data, default_name_prefix)
                if srv:
                    return [srv]
                break

        # If only one conf string
        if not servers and "[Interface]" in input_data:
            srv = cls._parse_conf_block(input_data, default_name_prefix)
            if srv:
                servers.append(srv)

        return servers

    @classmethod
    def _parse_conf_block(cls, conf_text: str, default_name: str) -> Optional[ParsedServer]:
        """Parse standard or Amnezia WireGuard .conf text into ParsedServer."""
        lines = conf_text.strip().splitlines()
        if not lines:
            return None

        # Check for comments with server name (e.g. # Name: NL-01 or # Name = NL)
        name = default_name
        for line in lines[:5]:
            line_s = line.strip()
            if line_s.startswith("#"):
                clean = line_s.lstrip("#").strip()
                if clean.lower().startswith("name:"):
                    name = clean[5:].strip()
                elif clean.lower().startswith("name="):
                    name = clean[5:].strip()
                elif len(clean) > 2 and "=" not in clean:
                    name = clean

        name = cls._sanitize_server_name(name)

        # Detect Amnezia keys
        is_amnezia = False
        endpoint = ""
        dns = ""
        for line in lines:
            if "=" in line:
                k, _, v = line.partition("=")
                k_clean = k.strip().lower()
                v_clean = v.strip()
                if k_clean in AWG_KEYS:
                    is_amnezia = True
                elif k_clean == "endpoint":
                    endpoint = v_clean
                elif k_clean == "dns":
                    dns = v_clean

        protocol = "AmneziaWG" if is_amnezia else "WireGuard"
        return ParsedServer(
            name=name,
            protocol=protocol,
            conf_content=conf_text.strip() + "\n",
            endpoint=endpoint,
            dns=dns,
            is_amnezia=is_amnezia,
        )

    @classmethod
    def _parse_wg_uri(cls, uri: str, default_name: str) -> Optional[ParsedServer]:
        """Parse wireguard:// or awg:// URI into a ParsedServer."""
        try:
            parsed = urllib.parse.urlparse(uri)
            scheme = parsed.scheme.lower()
            privkey = urllib.parse.unquote(parsed.username or "")
            host = parsed.hostname or ""
            port = parsed.port or 51820
            endpoint = f"{host}:{port}" if host else ""

            fragment_name = urllib.parse.unquote(parsed.fragment or "").strip()
            name = fragment_name if fragment_name else default_name
            name = cls._sanitize_server_name(name)

            params = urllib.parse.parse_qs(parsed.query)

            def get_p(key: str, default: str = "") -> str:
                return params.get(key, [default])[0]

            address = get_p("address", get_p("ip", "10.0.0.2/32"))
            pubkey = get_p("publickey", get_p("public_key", get_p("pubkey", "")))
            preshared_key = get_p("presharedkey", get_p("psk", ""))
            dns = get_p("dns", "1.1.1.1, 8.8.8.8")
            mtu = get_p("mtu", "")
            allowed_ips = get_p("allowedips", get_p("allowed_ips", "0.0.0.0/0, ::/0"))
            keepalive = get_p("persistentkeepalive", get_p("keepalive", "25"))

            # Amnezia parameters
            is_amnezia = (scheme == "awg")
            awg_dict: dict[str, str] = {}
            for k in ("jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4"):
                val = get_p(k)
                if val:
                    awg_dict[k.capitalize() if k != "jc" else "Jc"] = val
                    is_amnezia = True

            conf_lines = [
                "[Interface]",
                f"PrivateKey = {privkey}",
                f"Address = {address}",
            ]
            if dns:
                conf_lines.append(f"DNS = {dns}")
            if mtu:
                conf_lines.append(f"MTU = {mtu}")
            for ak, av in awg_dict.items():
                conf_lines.append(f"{ak} = {av}")

            conf_lines.extend([
                "",
                "[Peer]",
                f"PublicKey = {pubkey}",
                f"Endpoint = {endpoint}",
                f"AllowedIPs = {allowed_ips}",
            ])
            if preshared_key:
                conf_lines.append(f"PresharedKey = {preshared_key}")
            if keepalive:
                conf_lines.append(f"PersistentKeepalive = {keepalive}")

            conf_str = "\n".join(conf_lines) + "\n"

            return ParsedServer(
                name=name,
                protocol="AmneziaWG" if is_amnezia else "WireGuard",
                conf_content=conf_str,
                endpoint=endpoint,
                dns=dns,
                is_amnezia=is_amnezia,
            )
        except Exception as exc:
            logger.error("Failed to parse WG/AWG URI %s: %s", uri[:50], exc)
            return None

    @classmethod
    def _parse_json_config(cls, data: dict[str, Any], default_name: str) -> list[ParsedServer]:
        """Parse JSON configs."""
        servers: list[ParsedServer] = []

        if "containers" in data and isinstance(data["containers"], list):
            for c in data["containers"]:
                awg_data = c.get("awg") or c.get("wireguard") or c.get("amneziawg")
                if isinstance(awg_data, dict):
                    conf = awg_data.get("config", "") or awg_data.get("last_config", "")
                    c_name = c.get("name", default_name)
                    if conf:
                        srv = cls._parse_conf_block(conf, c_name)
                        if srv:
                            servers.append(srv)

        if "interface" in data and "peers" in data:
            iface = data["interface"]
            peers = data["peers"]
            name = data.get("name", default_name)
            name = cls._sanitize_server_name(name)
            lines = ["[Interface]"]
            for k, v in iface.items():
                lines.append(f"{k} = {v}")
            for p in peers:
                lines.append("")
                lines.append("[Peer]")
                for k, v in p.items():
                    lines.append(f"{k} = {v}")
            srv = cls._parse_conf_block("\n".join(lines), name)
            if srv:
                servers.append(srv)

        # Single outbound or config with tag/protocol
        if "protocol" in data:
            proto = data.get("protocol", "").lower()
            tag = data.get("remarks") or data.get("tag") or default_name
            name = cls._sanitize_server_name(tag)
            settings = data.get("settings", {})
            stream = data.get("streamSettings", {})
            vnext = settings.get("vnext", [])
            servers_list = settings.get("servers", [])

            addr = ""
            port = 443
            uuid = ""
            if vnext and isinstance(vnext, list):
                v_first = vnext[0]
                addr = v_first.get("address", "")
                port = int(v_first.get("port", 443))
                users = v_first.get("users", [])
                if users:
                    uuid = users[0].get("id", "")
            elif servers_list and isinstance(servers_list, list):
                s_first = servers_list[0]
                addr = s_first.get("address", "")
                port = int(s_first.get("port", 443))
                uuid = s_first.get("password", "") or s_first.get("id", "")

            sec = stream.get("security", "none")
            net = stream.get("network", "tcp")
            reality = stream.get("realitySettings", {})
            tls = stream.get("tlsSettings", {})
            sni = reality.get("serverName") or tls.get("serverName") or addr
            pbk = reality.get("publicKey", "")
            sid = reality.get("shortId", "")
            # Filter out dummy placeholder / ad banners (e.g. 0.0.0.0:1 or zeroed UUIDs)
            if addr and addr not in ("0.0.0.0", "127.0.0.1", "::1") and uuid not in ("00000000-0000-0000-0000-000000000000", ""):
                conf_lines = [
                    f"# Incy Profile: {name}",
                    f"# Endpoint: {addr}:{port}",
                    f"# UUID: {uuid}",
                    f"# Protocol: {proto.upper()} ({sec.upper()})",
                    "[Interface]",
                    "PrivateKey = none",
                    "Address = 10.0.0.2/32",
                    "DNS = 1.1.1.1, 8.8.8.8",
                    "",
                    "[Peer]",
                    "PublicKey = none",
                    f"Endpoint = {addr}:{port}",
                    "AllowedIPs = 0.0.0.0/0, ::/0",
                ]
                meta = {
                    "id": f"sub_json_{abs(hash(str(data))) % 1000000}",
                    "name": name,
                    "ascii_name": name,
                    "protocol": proto,
                    "address": addr,
                    "port": port,
                    "uuid": uuid,
                    "public_key": pbk,
                    "short_id": sid,
                    "sni": sni,
                    "network": net,
                    "security": sec,
                    "fingerprint": fp,
                }
                servers.append(ParsedServer(
                    name=name,
                    protocol=f"{proto.upper()} {sec.capitalize()}" if sec != "none" else proto.upper(),
                    conf_content="\n".join(conf_lines) + "\n",
                    endpoint=f"{addr}:{port}",
                    dns="1.1.1.1, 8.8.8.8",
                    metadata=meta,
                ))

        for key in ("servers", "configs", "profiles", "nodes", "outbounds"):
            if key in data and isinstance(data[key], list):
                for idx, item in enumerate(data[key]):
                    if isinstance(item, str):
                        res = cls.parse(item, f"{default_name}_{idx+1}")
                        servers.extend(res)
                    elif isinstance(item, dict):
                        # Inherit parent remarks if item has no own remarks
                        if "remarks" in data and "remarks" not in item:
                            item["remarks"] = f"{data['remarks']}_{idx+1}" if idx > 0 else data["remarks"]
                        sub = cls._parse_json_config(item, f"{default_name}_{idx+1}")
                        servers.extend(sub)

        return servers

    @classmethod
    def _parse_clash_yaml(cls, yaml_text: str, default_name: str) -> list[ParsedServer]:
        """Parse Clash / Mihomo YAML proxies list."""
        servers: list[ParsedServer] = []
        lines = yaml_text.splitlines()
        in_proxies = False
        cur_proxy: dict[str, Any] = {}

        def commit_cur():
            if cur_proxy and "server" in cur_proxy and "name" in cur_proxy:
                p_addr = str(cur_proxy.get("server", "")).strip()
                p_uuid = str(cur_proxy.get("uuid", "") or cur_proxy.get("password", "")).strip()
                if p_addr in ("0.0.0.0", "127.0.0.1", "::1") or p_uuid in ("00000000-0000-0000-0000-000000000000", ""):
                    return

                p_name = cls._sanitize_server_name(str(cur_proxy.get("name", default_name)))
                p_port = int(cur_proxy.get("port", 443))
                p_type = str(cur_proxy.get("type", "vless")).lower()
                p_sni = str(cur_proxy.get("sni", "") or cur_proxy.get("servername", "") or p_addr)
                p_pbk = str(cur_proxy.get("public-key", "") or cur_proxy.get("pbk", ""))
                p_sid = str(cur_proxy.get("short-id", "") or cur_proxy.get("sid", ""))
                p_net = str(cur_proxy.get("network", "tcp"))
                p_sec = "reality" if p_pbk else ("tls" if cur_proxy.get("tls") else "none")

                conf_lines = [
                    f"# Incy Profile: {p_name}",
                    f"# Endpoint: {p_addr}:{p_port}",
                    f"# UUID: {p_uuid}",
                    f"# Protocol: {p_type.upper()} ({p_sec.upper()})",
                    "[Interface]",
                    "PrivateKey = none",
                    "Address = 10.0.0.2/32",
                    "DNS = 1.1.1.1, 8.8.8.8",
                    "",
                    "[Peer]",
                    "PublicKey = none",
                    f"Endpoint = {p_addr}:{p_port}",
                    "AllowedIPs = 0.0.0.0/0, ::/0",
                ]
                meta = {
                    "id": f"sub_clash_{abs(hash(p_name + p_addr)) % 1000000}",
                    "name": p_name,
                    "ascii_name": p_name,
                    "protocol": p_type,
                    "address": p_addr,
                    "port": p_port,
                    "uuid": p_uuid,
                    "public_key": p_pbk,
                    "short_id": p_sid,
                    "sni": p_sni,
                    "network": p_net,
                    "security": p_sec,
                }
                servers.append(ParsedServer(
                    name=p_name,
                    protocol=f"{p_type.upper()} {p_sec.capitalize()}" if p_sec != "none" else p_type.upper(),
                    conf_content="\n".join(conf_lines) + "\n",
                    endpoint=f"{p_addr}:{p_port}",
                    dns="1.1.1.1, 8.8.8.8",
                    metadata=meta,
                ))

        for raw_line in lines:
            line = raw_line.rstrip()
            if not line or line.strip().startswith("#"):
                continue
            if line.startswith("proxies:"):
                in_proxies = True
                continue
            if in_proxies and not line.startswith(" ") and not line.startswith("\t") and not line.startswith("-"):
                in_proxies = False
                commit_cur()
                cur_proxy = {}
                continue

            if in_proxies:
                stripped = line.strip()
                if stripped.startswith("-"):
                    commit_cur()
                    cur_proxy = {}
                    stripped = stripped[1:].strip()
                if ":" in stripped:
                    k, _, v = stripped.partition(":")
                    k_c = k.strip().lower()
                    v_c = v.strip().strip('"').strip("'")
                    cur_proxy[k_c] = v_c

        commit_cur()
        return servers

    @classmethod
    def _parse_vless_uri(cls, uri: str, default_name: str) -> Optional[ParsedServer]:
        """Parse vless:// URI with Reality or TLS into ParsedServer."""
        try:
            u = urllib.parse.urlparse(uri)
            qs = urllib.parse.parse_qs(u.query)
            addr = u.hostname or ""
            port = u.port or 443
            uuid = u.username or ""
            pbk = qs.get("pbk", [""])[0]
            sid = qs.get("sid", [""])[0]
            sni = qs.get("sni", [addr])[0]
            flow = qs.get("flow", [""])[0]
            net = qs.get("type", ["tcp"])[0]
            sec = qs.get("security", ["reality"])[0]
            fp = qs.get("fp", ["chrome"])[0]

            frag_name = urllib.parse.unquote(u.fragment).strip()
            name = frag_name if frag_name else default_name
            name = cls._sanitize_server_name(name)

            # Build synthetic .conf header so XrayManager can map it directly
            conf_lines = [
                f"# Incy Profile: {name}",
                f"# Endpoint: {addr}:{port}",
                f"# UUID: {uuid}",
                f"# Protocol: VLESS ({sec.upper()})",
                "[Interface]",
                "PrivateKey = none",
                "Address = 10.0.0.2/32",
                "DNS = 1.1.1.1, 8.8.8.8",
                "",
                "[Peer]",
                "PublicKey = none",
                f"Endpoint = {addr}:{port}",
                "AllowedIPs = 0.0.0.0/0, ::/0",
            ]

            meta = {
                "id": f"sub_vless_{abs(hash(uri)) % 1000000}",
                "name": name,
                "ascii_name": name,
                "protocol": "vless",
                "address": addr,
                "port": port,
                "uuid": uuid,
                "public_key": pbk,
                "short_id": sid,
                "sni": sni,
                "flow": flow,
                "network": net,
                "security": sec,
                "fingerprint": fp,
                "uri": uri,
            }

            return ParsedServer(
                name=name,
                protocol="VLESS Reality" if sec == "reality" else "VLESS",
                conf_content="\n".join(conf_lines) + "\n",
                endpoint=f"{addr}:{port}",
                dns="1.1.1.1, 8.8.8.8",
                metadata=meta,
            )
        except Exception as exc:
            logger.error("Failed to parse VLESS URI %s: %s", uri[:50], exc)
            return None

    @classmethod
    def _parse_generic_proxy_uri(cls, uri: str, default_name: str) -> Optional[ParsedServer]:
        """Parse trojan://, ss://, vmess:// URI into ParsedServer."""
        try:
            u = urllib.parse.urlparse(uri)
            addr = u.hostname or ""
            port = u.port or 443
            frag_name = urllib.parse.unquote(u.fragment).strip()
            name = frag_name if frag_name else default_name
            name = cls._sanitize_server_name(name)

            conf_lines = [
                f"# Incy Profile: {name}",
                f"# Endpoint: {addr}:{port}",
                f"# Protocol: {u.scheme.upper()}",
                "[Interface]",
                "PrivateKey = none",
                "Address = 10.0.0.2/32",
                "DNS = 1.1.1.1, 8.8.8.8",
                "",
                "[Peer]",
                "PublicKey = none",
                f"Endpoint = {addr}:{port}",
                "AllowedIPs = 0.0.0.0/0, ::/0",
            ]
            return ParsedServer(
                name=name,
                protocol=u.scheme.upper(),
                conf_content="\n".join(conf_lines) + "\n",
                endpoint=f"{addr}:{port}",
                dns="1.1.1.1, 8.8.8.8",
            )
        except Exception as exc:
            logger.error("Failed to parse proxy URI %s: %s", uri[:50], exc)
            return None

    _COUNTRY_TRANSLATIONS = (
        ("Нидерланды", "Netherlands"),
        ("Германия", "Germany"),
        ("Финляндия", "Finland"),
        ("Швеция", "Sweden"),
        ("Польша", "Poland"),
        ("Эстония", "Estonia"),
        ("Латвия", "Latvia"),
        ("Румыния", "Romania"),
        ("Великобритания", "UK"),
        ("Испания", "Spain"),
        ("Италия", "Italy"),
        ("Люксембург", "Luxembourg"),
        ("США", "USA"),
        ("Япония", "Japan"),
        ("Южная Корея", "Korea"),
        ("Казахстан", "Kazakhstan"),
        ("ОАЭ", "UAE"),
        ("Екатеринбург", "Ekaterinburg"),
        ("Авто", "Auto"),
        ("Белые списки", "Whitelist"),
        ("Самый быстрый", "Fastest"),
        ("Игровой Обход", "Gaming"),
    )

    _TRANSLIT = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }

    @classmethod
    def _sanitize_server_name(cls, raw_name: str) -> str:
        """Sanitize server name to safe ASCII and dashes (max 15 chars for Linux iface)."""
        clean = raw_name
        for rus, eng in cls._COUNTRY_TRANSLATIONS:
            clean = re.sub(re.escape(rus), eng, clean, flags=re.IGNORECASE)

        clean = re.sub(r"\[.*?\]", "", clean)
        clean = re.sub(r"[\(\)]", "", clean)

        chars: list[str] = []
        for ch in clean:
            lower_ch = ch.lower()
            if lower_ch in cls._TRANSLIT:
                chars.append(cls._TRANSLIT[lower_ch].upper() if ch.isupper() else cls._TRANSLIT[lower_ch])
            elif ch in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-":
                chars.append(ch)
            elif ch.isspace() or ch in ".,|/":
                chars.append("-")

        cand = "".join(chars)
        cand = re.sub(r"[-_]+", "-", cand).strip("-_")
        if not cand:
            cand = "server"
        return cand[:15]

    @staticmethod
    def _extract_host_name(url: str) -> str:
        """Extract a readable short name from URL."""
        try:
            p = urllib.parse.urlparse(url)
            host = p.hostname or "server"
            parts = host.split(".")
            if len(parts) >= 2:
                return parts[-2].capitalize()
            return host.capitalize()
        except Exception:
            return "Server"
