#!/usr/bin/env python3
"""Cloudflare WARP automatic provisioner.

Generates a personal WireGuard config by registering with the
Cloudflare WARP API.  No account is required.

This is the same technique used by open-source projects such as
wgcf (https://github.com/ViRb3/wgcf) and others.

Includes fallback API endpoints for regions where the primary
domain is unreachable.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

__all__ = ["WARPProvisioner", "WARPProvisionError"]

logger = logging.getLogger("warp_provisioner")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Multiple API base URLs — try in order if one is blocked / unreachable.
# The hostname may be DNS-blocked; direct IPs bypass that.
WARP_API_BASES = [
    "https://api.cloudflareclient.com/v0a2223",
    "https://162.159.192.1/v0a2223",
    "https://162.159.193.1/v0a2223",
    "https://162.159.195.1/v0a2223",
    "https://188.114.96.1/v0a2223",
    "https://188.114.97.1/v0a2223",
]

WARP_API_HOSTNAME = "api.cloudflareclient.com"

WARP_API_HEADERS = {
    "User-Agent": "okhttp/3.12.1",
    "CF-Client-Version": "a-6.3-2223",
    "Content-Type": "application/json",
    "Host": WARP_API_HOSTNAME,  # Always send the real Host header
}
REQUEST_TIMEOUT = 15

# Fixed Cloudflare WARP WireGuard endpoints (for the tunnel itself)
WARP_ENDPOINTS = [
    "engage.cloudflareclient.com:2408",
    "162.159.192.1:2408",
    "162.159.193.1:2408",
    "162.159.195.1:2408",
    "188.114.96.1:2408",
    "188.114.97.1:2408",
]

_WARP_DNS_V4 = "1.1.1.1"
_WARP_DNS_V6 = "2606:4700:4700::1111"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class WARPProvisionError(Exception):
    """Raised when WARP provisioning fails."""


# ---------------------------------------------------------------------------
# Key generation helpers
# ---------------------------------------------------------------------------


def _generate_keypair() -> tuple[str, str]:
    """Generate a WireGuard private + public key pair.

    Returns (private_key_base64, public_key_base64).
    Requires wg binary on PATH.
    """
    try:
        priv = subprocess.run(
            ["wg", "genkey"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if priv.returncode != 0:
            raise WARPProvisionError(
                f"wg genkey failed: {priv.stderr.strip()}"
            )
        private_key = priv.stdout.strip()
        if not private_key:
            raise WARPProvisionError("wg genkey returned empty output")

        pub = subprocess.run(
            ["wg", "pubkey"],
            input=private_key,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if pub.returncode != 0:
            raise WARPProvisionError(
                f"wg pubkey failed: {pub.stderr.strip()}"
            )
        public_key = pub.stdout.strip()
        if not public_key:
            raise WARPProvisionError("wg pubkey returned empty output")

        return private_key, public_key

    except FileNotFoundError:
        raise WARPProvisionError(
            "wg (wireguard-tools) is not installed. "
            "Run: sudo apt install wireguard-tools"
        )
    except subprocess.TimeoutExpired:
        raise WARPProvisionError("wg genkey timed out")


# ---------------------------------------------------------------------------
# WARP API client
# ---------------------------------------------------------------------------


class WARPProvisioner:
    """Provisions a personal Cloudflare WARP WireGuard config via the public API.

    Tries multiple API base URLs in case the primary domain is
    DNS-blocked or IP-blocked in the current region.
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(WARP_API_HEADERS)
        # Disable SSL hostname verification for direct-IP endpoints
        # (the TLS cert is valid for *.cloudflareclient.com, not for the IP)
        self._session.verify = False
        # Suppress urllib3 InsecureRequestWarning
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def provision(self, profile_name: str = "cloudflare-warp") -> str:
        """Generate and return a WireGuard .conf string for WARP.

        Steps:
        1. Generate a WireGuard keypair locally.
        2. Try registering the public key with the WARP API via each
           base URL until one succeeds.
        3. Build and return a complete WireGuard config.

        Raises:
            WARPProvisionError: on any failure.
        """
        logger.info("Generating WireGuard keypair…")
        private_key, public_key = _generate_keypair()

        logger.info("Registering with Cloudflare WARP API…")
        reg_data = self._register_with_fallback(public_key)

        device_id: str = reg_data.get("id", "")
        token: str = reg_data.get("token", "")
        if not device_id or not token:
            raise WARPProvisionError(
                f"WARP registration returned unexpected data: "
                f"id={device_id!r}, token present={bool(token)}"
            )

        logger.info("Fetching device config (id=%s)…", device_id[:8])
        config_data = self._get_config_with_fallback(device_id, token)
        conf = self._build_conf(private_key, config_data, profile_name)
        logger.info("WARP provisioning complete")
        return conf

    # ---- API calls with fallback ------------------------------------------

    def _register_with_fallback(self, public_key: str) -> dict[str, Any]:
        """Try /reg on each API base URL until one succeeds."""
        tos_time = time.strftime("%Y-%m-%dT%H:%M:%S.000+0000", time.gmtime())
        install_id = str(uuid.uuid4()).replace("-", "")[:22]
        payload = {
            "key": public_key,
            "install_id": install_id,
            "fcm_token": "",
            "tos": tos_time,
            "model": "PC",
            "serial_number": install_id,
            "locale": "en_US",
        }

        last_error = ""
        for base_url in WARP_API_BASES:
            url = f"{base_url}/reg"
            try:
                logger.debug("Trying POST %s", url)
                resp = self._session.post(
                    url, json=payload, timeout=REQUEST_TIMEOUT
                )
                resp.raise_for_status()
                data = resp.json()
                logger.info("Registration succeeded via %s", base_url)
                self._working_base = base_url
                return data
            except requests.Timeout:
                last_error = f"Timeout connecting to {base_url}"
                logger.debug(last_error)
            except requests.ConnectionError as exc:
                last_error = f"Connection error to {base_url}: {exc}"
                logger.debug(last_error)
            except requests.HTTPError as exc:
                body = ""
                try:
                    body = exc.response.text[:200]
                except Exception:
                    pass
                last_error = f"HTTP {exc.response.status_code} from {base_url}: {body}"
                logger.debug(last_error)
            except ValueError as exc:
                last_error = f"Invalid JSON from {base_url}: {exc}"
                logger.debug(last_error)

        raise WARPProvisionError(
            f"All {len(WARP_API_BASES)} WARP API endpoints unreachable. "
            f"Last error: {last_error}"
        )

    def _get_config_with_fallback(
        self, device_id: str, token: str
    ) -> dict[str, Any]:
        """GET /reg/{device_id} trying each base URL."""
        # Prefer the base that worked for registration
        bases = list(WARP_API_BASES)
        working = getattr(self, "_working_base", None)
        if working and working in bases:
            bases.remove(working)
            bases.insert(0, working)

        last_error = ""
        for base_url in bases:
            url = f"{base_url}/reg/{device_id}"
            try:
                resp = self._session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                return resp.json()
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = f"{base_url}: {exc}"
                logger.debug("Config fetch failed: %s", last_error)
            except requests.HTTPError as exc:
                last_error = f"HTTP {exc.response.status_code} from {base_url}"
                logger.debug("Config fetch failed: %s", last_error)
            except ValueError as exc:
                last_error = f"Bad JSON from {base_url}: {exc}"

        raise WARPProvisionError(
            f"Could not fetch WARP config from any endpoint. "
            f"Last error: {last_error}"
        )

    # ---- Config builder ---------------------------------------------------

    def _build_conf(
        self,
        private_key: str,
        data: dict[str, Any],
        profile_name: str,
    ) -> str:
        """Construct a WireGuard .conf string from the WARP API response."""
        config = data.get("config", {})
        peers = config.get("peers", [])
        iface = config.get("interface", {})
        addresses = iface.get("addresses", {})

        if not peers:
            raise WARPProvisionError(
                "WARP API response contains no peers. "
                "The API may have changed; try again later."
            )

        peer = peers[0]
        peer_pubkey: str = peer.get("public_key", "")
        endpoint_obj = peer.get("endpoint", {})

        # Pick a reachable endpoint; prefer engage hostname, fallback to IPs
        endpoint_host: str = (
            endpoint_obj.get("host", "")
            or endpoint_obj.get("v4", "")
            or WARP_ENDPOINTS[0]
        )

        allowed_ips: str = ", ".join(
            peer.get("allowed_ips", ["0.0.0.0/0", "::/0"])
        )

        client_ipv4: str = addresses.get("v4", "172.16.0.2")
        client_ipv6: str = addresses.get("v6", "")

        if not peer_pubkey:
            raise WARPProvisionError(
                "WARP API did not return a peer public key"
            )

        # Build address field
        addr_parts = [f"{client_ipv4}/32"]
        if client_ipv6:
            addr_parts.append(f"{client_ipv6}/128")
        address_str = ", ".join(addr_parts)

        # Use a direct IP endpoint if the hostname might be blocked
        best_endpoint = self._pick_best_endpoint(endpoint_host)

        lines = [
            f"# Cloudflare WARP — auto-provisioned profile: {profile_name}",
            "# Generated by Ubuntu VPN Client",
            "# This config is personal to your device. Do not share it.",
            "",
            "[Interface]",
            f"PrivateKey = {private_key}",
            f"Address = {address_str}",
            f"DNS = {_WARP_DNS_V4}, {_WARP_DNS_V6}",
            "MTU = 1280",
            "",
            "[Peer]",
            f"PublicKey = {peer_pubkey}",
            f"AllowedIPs = {allowed_ips}",
            f"Endpoint = {best_endpoint}",
            "PersistentKeepalive = 25",
            "",
        ]
        return "\n".join(lines)

    def _pick_best_endpoint(self, api_endpoint: str) -> str:
        """Return the best WireGuard tunnel endpoint.

        If the API-provided hostname resolves and is reachable, use it.
        Otherwise, pick the first reachable direct-IP endpoint.
        """
        # Quick connectivity test on the API-provided endpoint
        host = api_endpoint.split(":")[0]
        port = api_endpoint.split(":")[1] if ":" in api_endpoint else "2408"

        try:
            proc = subprocess.run(
                ["ping", "-c", "1", "-W", "2", host],
                capture_output=True,
                timeout=5,
            )
            if proc.returncode == 0:
                return api_endpoint
        except Exception:
            pass

        # Fallback: try direct IPs
        for ep in WARP_ENDPOINTS:
            ep_host = ep.split(":")[0]
            try:
                proc = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", ep_host],
                    capture_output=True,
                    timeout=5,
                )
                if proc.returncode == 0:
                    logger.info("Using fallback endpoint: %s", ep)
                    return ep
            except Exception:
                continue

        # If nothing responds to ping, use the first direct IP anyway
        # (ICMP may be blocked but UDP 2408 might work)
        logger.warning(
            "No WARP endpoint responded to ping; using %s",
            WARP_ENDPOINTS[0],
        )
        return WARP_ENDPOINTS[0]

    def test_endpoints(self) -> list[tuple[str, bool]]:
        """Ping each known WARP endpoint and return (host:port, reachable) pairs."""
        results: list[tuple[str, bool]] = []
        for ep in WARP_ENDPOINTS:
            host = ep.split(":")[0]
            try:
                proc = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", host],
                    capture_output=True,
                    timeout=5,
                )
                results.append((ep, proc.returncode == 0))
            except Exception:
                results.append((ep, False))
        return results
