#!/usr/bin/env python3
"""Incy Server Importer & Converter.

Extracts all servers and ALL connection parameters (VLESS Reality, Hysteria 2, WireGuard)
from Incy's SQLite database (~/.local/share/incy/incy.db) and provides them with full
configuration JSONs, VLESS/Hysteria URIs, and metadata.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from subscription_parser import ParsedServer

logger = logging.getLogger("incy_importer")

INCY_DB_PATH = Path.home() / ".local" / "share" / "incy" / "incy.db"
XRAY_BIN_PATH = Path("/usr/local/bin/xray-core")
EXPORT_JSON_PATH = Path.home() / ".config" / "wavez-vpn" / "wavez_servers.json"
LEGACY_EXPORT_JSON_PATH = Path.home() / ".config" / "ubuntu-vpn" / "incy_servers.json"
BUNDLED_SERVERS_PATH = Path("/usr/local/share/wavez-vpn/wavez_servers.json")
LOCAL_SERVERS_PATH = Path(__file__).resolve().parent / "wavez_servers.json"


@dataclass
class IncyServerData:
    """Full server connection parameters extracted from Incy database."""

    id: str
    name: str
    ascii_name: str
    protocol: str  # VLESS, HYSTERIA2, WIREGUARD
    address: str
    port: int
    uuid: str = ""
    public_key: str = ""
    sni: str = ""
    short_id: str = ""
    flow: str = ""
    fingerprint: str = "firefox"
    security: str = "reality"
    network: str = "tcp"
    latency: Optional[int] = None
    uri: str = ""
    full_config_json: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class IncyImporter:
    """Extracts, formats, and exports all connection parameters from Incy or bundled presets."""

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
    def is_incy_available(cls) -> bool:
        """Return True if Incy database exists."""
        return INCY_DB_PATH.is_file()

    @classmethod
    def get_bundled_servers(cls) -> list[IncyServerData]:
        """Load servers from bundled wavez_servers.json (when Incy is not installed)."""
        candidates = [
            EXPORT_JSON_PATH,
            Path.home() / ".config" / "wavez-vpn" / "incy_servers.json",
            LEGACY_EXPORT_JSON_PATH,
            BUNDLED_SERVERS_PATH,
            LOCAL_SERVERS_PATH,
        ]
        for c in candidates:
            if c.is_file():
                try:
                    data = json.loads(c.read_text(encoding="utf-8"))
                    servers_list = data.get("servers", [])
                    res: list[IncyServerData] = []
                    for item in servers_list:
                        res.append(
                            IncyServerData(
                                id=item.get("id", ""),
                                name=item.get("name", ""),
                                ascii_name=item.get("ascii_name", cls._clean_name(item.get("name", ""))),
                                protocol=item.get("protocol", "VLESS"),
                                address=item.get("address", ""),
                                port=int(item.get("port", 443)),
                                uuid=item.get("uuid", ""),
                                public_key=item.get("public_key", ""),
                                sni=item.get("sni", ""),
                                short_id=item.get("short_id", ""),
                                flow=item.get("flow", ""),
                                fingerprint=item.get("fingerprint", "firefox"),
                                security=item.get("security", "reality"),
                                network=item.get("network", "tcp"),
                                latency=item.get("latency"),
                                uri=item.get("uri", ""),
                                full_config_json=item.get("full_config_json", ""),
                                extra=item.get("extra", {}),
                            )
                        )
                    if res:
                        logger.info("Loaded %d built-in servers from %s", len(res), c)
                        return res
                except Exception as exc:
                    logger.warning("Failed to load servers from %s: %s", c, exc)
        return []

    @classmethod
    def get_raw_servers(cls, db_path: Optional[Path] = None) -> list[IncyServerData]:
        """Fetch all servers with all connection parameters from incy.db or bundled presets."""
        path = db_path or INCY_DB_PATH
        if not path.is_file():
            return cls.get_bundled_servers()

        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            cur = con.cursor()
            cols = [d[0] for d in cur.execute("SELECT * FROM servers LIMIT 1;").description]
            rows = cur.execute("SELECT * FROM servers ORDER BY orderIndex, id;").fetchall()
            con.close()

            servers: list[IncyServerData] = []
            for r in rows:
                d = dict(zip(cols, r))
                name = str(d.get("name", "Incy Server"))
                proto = str(d.get("proxyProtocol", "VLESS")).upper()
                addr = str(d.get("address", ""))
                port = int(d.get("port", 443) or 443)
                uuid_val = str(d.get("uuid", "") or "")
                pubkey = str(d.get("publicKey", "") or "")
                sni_val = str(d.get("sni", "") or "")
                short_id_val = str(d.get("shortId", "") or "")
                flow_val = str(d.get("flow", "") or "")
                fp = str(d.get("fingerprint", "firefox") or "firefox")
                full_json = str(d.get("fullConfigJson", "") or "")
                latency_val = d.get("latency")

                # If UUID is missing in columns, try extracting from fullConfigJson
                if not uuid_val and full_json:
                    try:
                        cfg_obj = json.loads(full_json)
                        for ob in cfg_obj.get("outbounds", []):
                            vnext = ob.get("settings", {}).get("vnext", [])
                            if vnext and vnext[0].get("users"):
                                uuid_val = vnext[0]["users"][0].get("id", "")
                                flow_val = vnext[0]["users"][0].get("flow", flow_val)
                            # Hysteria auth
                            hyst_auth = ob.get("streamSettings", {}).get("hysteriaSettings", {}).get("auth", "")
                            if hyst_auth and not uuid_val:
                                uuid_val = hyst_auth
                    except Exception:
                        pass

                # Build standardized connection URI
                uri = cls._build_uri(
                    protocol=proto,
                    name=name,
                    address=addr,
                    port=port,
                    uuid_val=uuid_val,
                    public_key=pubkey,
                    sni_val=sni_val,
                    short_id_val=short_id_val,
                    flow_val=flow_val,
                    fingerprint=fp,
                )

                ascii_name = cls._clean_name(name)

                servers.append(
                    IncyServerData(
                        id=str(d.get("id", "")),
                        name=name,
                        ascii_name=ascii_name,
                        protocol=proto,
                        address=addr,
                        port=port,
                        uuid=uuid_val,
                        public_key=pubkey,
                        sni=sni_val,
                        short_id=short_id_val,
                        flow=flow_val,
                        fingerprint=fp,
                        latency=int(latency_val) if latency_val is not None else None,
                        uri=uri,
                        full_config_json=full_json,
                        extra={
                            "wgAddress": d.get("wgAddress"),
                            "wgDns": d.get("wgDns"),
                            "hy2Obfs": d.get("hy2Obfs"),
                        },
                    )
                )

            logger.info("Loaded %d full connection profiles from Incy database", len(servers))
            return servers
        except Exception as exc:
            logger.error("Failed to read Incy database: %s", exc)
            return []

    @classmethod
    def _build_uri(
        cls,
        protocol: str,
        name: str,
        address: str,
        port: int,
        uuid_val: str,
        public_key: str,
        sni_val: str,
        short_id_val: str,
        flow_val: str,
        fingerprint: str = "firefox",
    ) -> str:
        """Construct standard VLESS/Hysteria2 shareable URI."""
        encoded_name = urllib.parse.quote(name)

        if protocol == "VLESS":
            query_params = {
                "security": "reality",
                "encryption": "none",
                "pbk": public_key,
                "headerType": "none",
                "fp": fingerprint or "firefox",
                "type": "tcp",
                "sni": sni_val or address,
            }
            if flow_val:
                query_params["flow"] = flow_val
            if short_id_val:
                query_params["sid"] = short_id_val

            query_str = urllib.parse.urlencode(query_params)
            return f"vless://{uuid_val}@{address}:{port}?{query_str}#{encoded_name}"

        elif protocol == "HYSTERIA2":
            return f"hysteria2://{uuid_val}@{address}:{port}/?sni={sni_val or address}&insecure=1#{encoded_name}"

        return f"{protocol.lower()}://{uuid_val}@{address}:{port}#{encoded_name}"

    @classmethod
    def to_parsed_servers(cls, db_path: Optional[Path] = None) -> list[ParsedServer]:
        """Convert all Incy servers to ParsedServer objects with full parameter sets."""
        raw_list = cls.get_raw_servers(db_path)
        parsed: list[ParsedServer] = []

        for item in raw_list:
            endpoint = f"{item.address}:{item.port}"
            conf_str = cls._build_wg_conf_for_incy_server(item)

            srv = ParsedServer(
                name=item.ascii_name,
                protocol=f"{item.protocol} (Incy)",
                conf_content=conf_str,
                endpoint=endpoint,
                dns="8.8.8.8, 8.8.4.4",
                is_amnezia=False,
                latency_ms=float(item.latency) if item.latency is not None and item.latency > 0 else None,
                selected=True,
                metadata={
                    "incy_id": item.id,
                    "display_name": item.name,
                    "ascii_name": item.ascii_name,
                    "protocol": item.protocol,
                    "address": item.address,
                    "port": item.port,
                    "uuid": item.uuid,
                    "public_key": item.public_key,
                    "sni": item.sni,
                    "short_id": item.short_id,
                    "flow": item.flow,
                    "fingerprint": item.fingerprint,
                    "uri": item.uri,
                    "full_config_json": item.full_config_json,
                },
            )
            parsed.append(srv)

        # Also auto-export to JSON file for easy integration
        cls.export_all_parameters(raw_list)

        return parsed

    @classmethod
    def export_all_parameters(
        cls, servers: Optional[list[IncyServerData]] = None, out_path: Optional[Path] = None
    ) -> Path:
        """Export all server parameters to a master JSON file."""
        if servers is None:
            servers = cls.get_raw_servers()

        target = out_path or EXPORT_JSON_PATH
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "count": len(servers),
                "servers": [asdict(s) for s in servers],
                "uris": [s.uri for s in servers if s.uri],
            }
            target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("Exported all %d Incy server parameters to %s", len(servers), target)
        except Exception as exc:
            logger.error("Failed to export Incy parameters JSON: %s", exc)

        return target

    @classmethod
    def _clean_name(cls, raw_name: str) -> str:
        """Create clean ASCII profile name (<=15 chars) for Linux interface."""
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

    @classmethod
    def _build_wg_conf_for_incy_server(cls, srv: IncyServerData) -> str:
        """Build detailed configuration file with full Incy connection parameters stored as comments/headers."""
        priv = "KJjdGNIpVYkyiZqGFyUPr0DDU5Y4znFkhd2fLlPLvlw="
        pub = "9QiBXCR/Iz6GRh6w9JO+oAKK0TyFcEGI9Fs9sywgqDs="
        if srv.public_key and len(srv.public_key.strip()) == 44:
            pub = srv.public_key.strip()

        return (
            f"# ===================================================================\n"
            f"# Incy Profile: {srv.name}\n"
            f"# Protocol: {srv.protocol}\n"
            f"# Endpoint: {srv.address}:{srv.port}\n"
            f"# UUID: {srv.uuid}\n"
            f"# SNI: {srv.sni}\n"
            f"# Reality PublicKey: {srv.public_key}\n"
            f"# ShortID: {srv.short_id}\n"
            f"# Flow: {srv.flow}\n"
            f"# Fingerprint: {srv.fingerprint}\n"
            f"# URI: {srv.uri}\n"
            f"# ===================================================================\n\n"
            f"[Interface]\n"
            f"PrivateKey = {priv}\n"
            f"Address = 10.0.0.2/32\n"
            f"DNS = 8.8.8.8, 8.8.4.4\n\n"
            f"[Peer]\n"
            f"PublicKey = {pub}\n"
            f"Endpoint = {srv.address}:{srv.port}\n"
            f"AllowedIPs = 0.0.0.0/0\n"
            f"PersistentKeepalive = 25\n"
        )
