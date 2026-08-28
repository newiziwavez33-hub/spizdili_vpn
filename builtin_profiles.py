#!/usr/bin/env python3
"""Ubuntu VPN Client — Built-in Free Server Profiles.

Provides a set of ready-to-use WireGuard configurations for public
free VPN servers.  Each profile uses a freshly generated keypair.

These are community/demo servers.  For production use, obtain a
WireGuard config from a trusted VPN provider.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

__all__ = ["get_builtin_profiles", "generate_fresh_profile"]

logger = logging.getLogger("builtin_profiles")

# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


def _genkey() -> tuple[str, str]:
    """Generate a WireGuard private/public key pair."""
    priv = subprocess.run(
        ["wg", "genkey"], capture_output=True, text=True, timeout=10
    )
    private = priv.stdout.strip()
    pub = subprocess.run(
        ["wg", "pubkey"], input=private, capture_output=True, text=True, timeout=10
    )
    public = pub.stdout.strip()
    return private, public


# ---------------------------------------------------------------------------
# Server catalogue
# ---------------------------------------------------------------------------

# These are well-known public/community WireGuard servers.
# Each entry contains only the SERVER-side info; a fresh client keypair
# is generated for every imported profile.

SERVERS = [
    {
        "name": "warp-eu",
        "description": "Cloudflare WARP (Europe, direct IP)",
        "endpoint": "162.159.193.1:2408",
        "server_pubkey": "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
        "dns": "1.1.1.1, 2606:4700:4700::1111",
        "allowed_ips": "0.0.0.0/0, ::/0",
        "mtu": "1280",
        "keepalive": "25",
        "address_v4_template": "172.16.0.2/32",
    },
    {
        "name": "warp-us",
        "description": "Cloudflare WARP (US, direct IP)",
        "endpoint": "162.159.192.1:2408",
        "server_pubkey": "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
        "dns": "1.1.1.1, 2606:4700:4700::1111",
        "allowed_ips": "0.0.0.0/0, ::/0",
        "mtu": "1280",
        "keepalive": "25",
        "address_v4_template": "172.16.0.2/32",
    },
    {
        "name": "warp-asia",
        "description": "Cloudflare WARP (Asia, direct IP)",
        "endpoint": "188.114.97.1:2408",
        "server_pubkey": "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
        "dns": "1.1.1.1, 2606:4700:4700::1111",
        "allowed_ips": "0.0.0.0/0, ::/0",
        "mtu": "1280",
        "keepalive": "25",
        "address_v4_template": "172.16.0.2/32",
    },
]


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def generate_fresh_profile(server_index: int = 0) -> tuple[str, str]:
    """Generate a .conf string with a fresh keypair for a built-in server.

    Args:
        server_index: index into the SERVERS list.

    Returns:
        (profile_name, conf_content) tuple.

    Raises:
        IndexError: if server_index is out of range.
        RuntimeError: if key generation fails.
    """
    if server_index < 0 or server_index >= len(SERVERS):
        raise IndexError(
            f"Server index {server_index} out of range (0..{len(SERVERS) - 1})"
        )
    srv = SERVERS[server_index]

    try:
        private_key, public_key = _genkey()
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Key generation failed: {exc}") from exc

    name = srv["name"].lower()
    lines = [
        f"# {srv['description']}",
        f"# Client pubkey: {public_key}",
        "# NOTE: You must register this pubkey with the server for the tunnel to work.",
        "# For Cloudflare WARP, use the WARP API or 'wgcf register' first.",
        "",
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {srv['address_v4_template']}",
        f"DNS = {srv['dns']}",
        f"MTU = {srv['mtu']}",
        "",
        "[Peer]",
        f"PublicKey = {srv['server_pubkey']}",
        f"AllowedIPs = {srv['allowed_ips']}",
        f"Endpoint = {srv['endpoint']}",
        f"PersistentKeepalive = {srv['keepalive']}",
        "",
    ]
    return name, "\n".join(lines)


def get_builtin_profiles() -> list[dict]:
    """Return list of server metadata dicts for UI display."""
    return [
        {
            "name": s["name"],
            "description": s["description"],
            "endpoint": s["endpoint"],
            "index": i,
        }
        for i, s in enumerate(SERVERS)
    ]
