"""HMRC fraud prevention headers (Gov-Client-* / Gov-Vendor-*).

HMRC legally requires these headers on every MTD API request (VAT Notice 700/22,
Fraud Prevention spec). Ported from the AIAccountant prototype; this is a
desktop/server profile (DESKTOP_APP_DIRECT). The device ID is derived from the
machine so it is stable across runs without ever being written to .env.

Reference: https://developer.service.hmrc.gov.uk/guides/fraud-prevention/
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import uuid
from datetime import datetime, timezone

VENDOR_PRODUCT_NAME = "MTDAgent"
VENDOR_VERSION = "mtd-agent=0.1.0"


def _device_id() -> str:
    """Stable per-machine device id (hardware UUID on macOS, else hostname-derived)."""
    try:
        result = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if "Hardware UUID" in line:
                return line.split(":")[-1].strip()
    except Exception:
        pass
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, platform.node()))


_DEVICE_ID = _device_id()
_VENDOR_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "mtd-agent.local"))


def _local_ip() -> str:
    """Best-effort local IP; HMRC accepts a sensible subset for server apps."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def build_fraud_headers() -> dict[str, str]:
    """Return the HMRC fraud-prevention headers for the current request.

    Attached to every MTD API call by the VAT client.
    """
    tz_offset = datetime.now(timezone.utc).astimezone().strftime("%z")
    if len(tz_offset) == 5:  # +0000 -> +00:00
        tz_offset = f"{tz_offset[:3]}:{tz_offset[3:]}"

    ip = _local_ip()
    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "Gov-Client-Connection-Method": "DESKTOP_APP_DIRECT",
        "Gov-Client-Device-ID": _DEVICE_ID,
        "Gov-Client-User-IDs": f"os={os.getenv('USER', 'unknown')}",
        "Gov-Client-Timezone": f"UTC{tz_offset}",
        "Gov-Client-Local-IPs": ip,
        "Gov-Client-Local-IPs-Timestamp": now_iso,
        "Gov-Client-Screens": "width=1920&height=1080&scaling-factor=1&colour-depth=24",
        "Gov-Client-Window-Size": "width=1920&height=1080",
        "Gov-Client-User-Agent": (
            f"os-family=Macintosh&os-version={platform.mac_ver()[0]}"
            "&device-manufacturer=Apple&device-model=Mac"
        ),
        "Gov-Vendor-Version": VENDOR_VERSION,
        "Gov-Vendor-Product-Name": VENDOR_PRODUCT_NAME,
        "Gov-Vendor-License-IDs": _VENDOR_ID,
        "Gov-Vendor-Public-IP": ip,
    }
