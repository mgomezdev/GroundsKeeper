"""Snapmaker U1 printer client (Snapmaker extended Klipper firmware).

Extends MoonrakerClient for the Snapmaker U1 running the Snapmaker extended
custom firmware (Klipper-based with Moonraker API).  This subclass is the
extension point for any Snapmaker-specific API differences discovered during
integration testing.
"""

from backend.app.services.moonraker_client import MoonrakerClient


class SnapmakerU1Client(MoonrakerClient):
    """Moonraker client for the Snapmaker U1 (Snapmaker extended Klipper firmware)."""

    printer_type = "snapmaker_u1"
