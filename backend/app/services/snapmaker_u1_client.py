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

    def get_capabilities(self):
        from backend.app.services.abstract_printer_client import PrinterCapabilities
        return PrinterCapabilities(
            ams=False,
            file_upload=True,
            bed_levelling=True,
            flow_calibration=False,
            vibration_cali=False,
            layer_inspect=False,
            timelapse=False,
            chamber_light=False,
            gcode=True,
            pause_resume=True,
            skip_objects=False,
            multi_nozzle=False,
        )
