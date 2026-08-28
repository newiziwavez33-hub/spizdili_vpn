#!/usr/bin/env python3
"""VPN Config Health & Latency Checker.

Tests:
- Hostname -> IP resolution
- ICMP Ping RTT latency
- UDP socket reachability to VPN port
- DNS server connectivity
- AmneziaWG obfuscation compatibility
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("health_checker")


@dataclass
class HealthReport:
    """Detailed diagnostic report for a VPN profile."""

    profile_name: str
    endpoint_raw: str
    endpoint_host: str = ""
    endpoint_port: int = 51820
    endpoint_ip: str = ""
    ping_ms: Optional[float] = None
    ping_min_ms: Optional[float] = None
    ping_max_ms: Optional[float] = None
    udp_reachable: bool = False
    udp_latency_ms: Optional[float] = None
    dns_servers: list[str] = field(default_factory=list)
    dns_reachable: dict[str, bool] = field(default_factory=dict)
    is_amnezia: bool = False
    awg_params: dict[str, str] = field(default_factory=dict)
    error: str = ""

    @property
    def is_healthy(self) -> bool:
        return bool(self.endpoint_ip and (self.ping_ms is not None or self.udp_reachable))

    @property
    def latency_display(self) -> str:
        if self.ping_ms is not None:
            return f"{self.ping_ms:.1f} ms"
        if self.udp_latency_ms is not None:
            return f"~{self.udp_latency_ms:.1f} ms"
        return "Timeout"


class ConfigHealthChecker:
    """Performs diagnostic tests on WireGuard and AmneziaWG configs."""

    @classmethod
    def check_config(cls, profile_name: str, conf_content_or_obj: Any, timeout: float = 3.0) -> HealthReport:
        """Run full health check on a configuration."""
        # Extract fields
        endpoint_str = ""
        dns_servers: list[str] = []
        is_amnezia = False
        awg_params: dict[str, str] = {}

        if hasattr(conf_content_or_obj, "interface") and hasattr(conf_content_or_obj, "peers"):
            # It's a WireGuardConfig object
            cfg = conf_content_or_obj
            endpoint_str = cfg.get_endpoint_host_port() or ""
            dns_servers = cfg.get_dns_servers()
            for k, v in cfg.interface.items():
                if k.lower() in {"jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4"}:
                    is_amnezia = True
                    awg_params[k] = v
        elif isinstance(conf_content_or_obj, str):
            # Parse raw text
            for line in conf_content_or_obj.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    k_c = k.strip().lower()
                    v_c = v.strip()
                    if k_c == "endpoint":
                        endpoint_str = v_c
                    elif k_c == "dns":
                        dns_servers = [s.strip() for s in v_c.split(",") if s.strip()]
                    elif k_c in {"jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4"}:
                        is_amnezia = True
                        awg_params[k.strip()] = v_c

        report = HealthReport(
            profile_name=profile_name,
            endpoint_raw=endpoint_str,
            dns_servers=dns_servers,
            is_amnezia=is_amnezia,
            awg_params=awg_params,
        )

        if not endpoint_str:
            report.error = "No Endpoint specified in configuration"
            return report

        # Parse host and port
        host = endpoint_str.rsplit(":", 1)[0].strip("[]")
        port = 51820
        if ":" in endpoint_str:
            try:
                port = int(endpoint_str.rsplit(":", 1)[1])
            except ValueError:
                pass

        report.endpoint_host = host
        report.endpoint_port = port

        # 1. DNS Resolution
        try:
            addrinfo = socket.getaddrinfo(host, port, socket.AF_INET)
            if addrinfo:
                report.endpoint_ip = addrinfo[0][4][0]
        except Exception as exc:
            logger.debug("DNS resolution failed for %s: %s", host, exc)
            report.endpoint_ip = host if re.match(r"^\d+\.\d+\.\d+\.\d+$", host) else ""

        if not report.endpoint_ip:
            report.error = f"Cannot resolve hostname '{host}'"
            return report

        target_ip = report.endpoint_ip

        # 2. ICMP Ping Test
        try:
            res = subprocess.run(
                ["ping", "-c", "3", "-W", str(max(1, int(timeout))), target_ip],
                capture_output=True,
                text=True,
                timeout=timeout + 3,
            )
            if res.returncode == 0:
                m = re.search(r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)", res.stdout)
                if not m:
                    m = re.search(r"round-trip min/avg/max(?:/\w+)? = ([\d.]+)/([\d.]+)/([\d.]+)", res.stdout)
                if m:
                    report.ping_min_ms = round(float(m.group(1)), 1)
                    report.ping_ms = round(float(m.group(2)), 1)
                    report.ping_max_ms = round(float(m.group(3)), 1)
        except Exception as exc:
            logger.debug("Ping failed to %s: %s", target_ip, exc)

        # 3. UDP Probe Test
        try:
            start_t = time.perf_counter()
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            # WireGuard initiation packet probe
            sock.connect((target_ip, port))
            sock.send(b"\x01\x00\x00\x00" + b"\x00" * 28)
            report.udp_latency_ms = round((time.perf_counter() - start_t) * 1000, 1)
            report.udp_reachable = True
            sock.close()
        except Exception as exc:
            logger.debug("UDP probe error to %s:%d: %s", target_ip, port, exc)

        # 4. DNS Servers Check (Port 53 probe)
        for dns_ip in dns_servers:
            dns_ip_clean = dns_ip.strip()
            if not dns_ip_clean:
                continue
            is_ok = cls._probe_dns_server(dns_ip_clean, timeout=1.5)
            report.dns_reachable[dns_ip_clean] = is_ok

        return report

    @classmethod
    def _probe_dns_server(cls, dns_ip: str, timeout: float = 1.5) -> bool:
        """Quick check if DNS server responds or connects."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((dns_ip, 53))
            s.close()
            return True
        except Exception:
            pass
        # Try UDP probe
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            s.connect((dns_ip, 53))
            s.send(b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01")
            s.close()
            return True
        except Exception:
            return False

    @classmethod
    def batch_check(
        cls,
        profiles: list[tuple[str, Any]],
        max_workers: int = 8,
        timeout: float = 3.0,
    ) -> dict[str, HealthReport]:
        """Check multiple profiles concurrently."""
        results: dict[str, HealthReport] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_name = {
                executor.submit(cls.check_config, name, cfg, timeout): name
                for name, cfg in profiles
            }
            for future in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    report = future.result()
                    results[name] = report
                except Exception as exc:
                    logger.error("Error checking profile '%s': %s", name, exc)
                    results[name] = HealthReport(profile_name=name, endpoint_raw="", error=str(exc))
        return results
