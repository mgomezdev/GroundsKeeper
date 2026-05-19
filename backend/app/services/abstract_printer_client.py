import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


@dataclass
class PrinterCapabilities:
    """Feature flags reported by each printer client.

    All fields default to False. Each concrete implementation overrides only
    the flags it supports. The frontend reads these from the printer status
    response to enable/disable UI options without hardcoding printer type
    strings.
    """

    ams: bool = False
    file_upload: bool = False
    bed_levelling: bool = False
    flow_calibration: bool = False
    vibration_cali: bool = False
    layer_inspect: bool = False
    timelapse: bool = False
    chamber_light: bool = False
    gcode: bool = False
    pause_resume: bool = False
    skip_objects: bool = False
    multi_nozzle: bool = False


@dataclass
class StartPrintOptions:
    """Vendor-agnostic options for starting a print job. Unsupported fields are ignored."""

    plate_id: int = 1
    ams_mapping: list[int] | None = None
    bed_levelling: bool = True
    flow_cali: bool = False
    vibration_cali: bool = True
    layer_inspect: bool = False
    timelapse: bool = False
    use_ams: bool = True


class AbstractPrinterClient(ABC):
    """Vendor-agnostic interface for all printer client implementations.

    Each concrete subclass must declare a class-level ``printer_type`` string
    (e.g. ``"bambu"``, ``"moonraker"``) that the factory and status API use as
    the discriminator.  Constructor signatures are intentionally left to each
    subclass — credentials and connection parameters are vendor-specific and
    are passed by the factory, not the abstract interface.
    """

    printer_type: ClassVar[str]

    # ------------------------------------------------------------------ #
    # Connection lifecycle                                                  #
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def connected(self) -> bool:
        """True when the printer is reachable and reporting status."""

    @abstractmethod
    def connect(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Establish the connection and start background communication."""

    @abstractmethod
    def disconnect(self, timeout: float = 0) -> None:
        """Tear down the connection and stop background work."""

    @abstractmethod
    def check_staleness(self) -> bool:
        """Assess whether the connection has gone stale; update and return ``connected``."""

    # ------------------------------------------------------------------ #
    # Print control                                                         #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def start_print(self, file_name: str, options: StartPrintOptions | None = None) -> bool:
        """Initiate a print job. Returns True if the command was accepted."""

    @abstractmethod
    def stop_print(self) -> bool:
        """Cancel the active print job."""

    @abstractmethod
    def pause_print(self) -> bool:
        """Pause the active print job."""

    @abstractmethod
    def resume_print(self) -> bool:
        """Resume a paused print job."""

    # ------------------------------------------------------------------ #
    # Command interface                                                     #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def send_gcode(self, gcode: str) -> bool:
        """Send a raw G-code command to the printer."""

    @abstractmethod
    def request_status_update(self) -> bool:
        """Ask the printer to push a full status refresh immediately."""

    @property
    def gcode_supported(self) -> bool:
        """True if this client can accept raw G-code via send_gcode(). Default True."""
        return True

    def home(self) -> bool:
        """Home all axes. Default: G28 via send_gcode. Subclasses override if needed."""
        return self.send_gcode("G28")

    def jog_z(self, distance_mm: float, force: bool = False) -> bool:
        """Jog the Z axis by distance_mm. Default: relative G1 via send_gcode.

        force=True disables soft endstops (M211) for the move — Bambu-specific;
        subclasses that use native protocols may ignore it.
        """
        lines = []
        if force:
            lines.append("M211 S0")
        lines += ["G91", f"G1 Z{distance_mm:.2f} F600", "G90"]
        if force:
            lines.append("M211 S1")
        return self.send_gcode("\n".join(lines))

    def set_chamber_light(self, on: bool) -> bool:
        """Turn the chamber/work light on or off. Subclasses override if supported."""
        return False

    # ------------------------------------------------------------------ #
    # File management (optional — subclasses override when supported)      #
    # ------------------------------------------------------------------ #

    @property
    def file_upload_supported(self) -> bool:
        """True if this client supports direct file upload via upload_file()."""
        return False

    file_listing_supported: bool = False
    """True if this client supports listing and deleting printer files."""

    def upload_file(self, file_data: bytes, filename: str) -> bool:
        """Upload file bytes to the printer. Returns False by default."""
        return False

    def list_files(self, directory: str = "/") -> list[dict]:
        """List files in *directory*. Returns empty list by default."""
        return []

    def delete_file(self, remote_path: str) -> bool:
        """Delete a file by path. Returns False by default."""
        return False

    def storage_info(self) -> dict | None:
        """Return storage usage info or None if unsupported."""
        return None

    def get_loaded_filaments(self) -> list[dict]:
        """Return loaded filaments in normalized format. Empty list means unknown."""
        return []

    async def upload_file_async(
        self,
        file_path: Path,
        remote_path: str,
        progress_callback: Callable[[int, int], None] | None = None,
        non_retry_exceptions: tuple[type, ...] = (),
    ) -> bool:
        """Async file upload to the printer. Returns True on success.

        Subclasses override this to implement their vendor-specific upload
        protocol (FTP for Bambu, HTTP multipart for Centauri, etc.).
        ``non_retry_exceptions`` is forwarded to retry wrappers so callers
        can prevent specific exceptions (e.g. DispatchJobCancelled) from
        being retried.
        """
        return False

    async def delete_remote_file(self, remote_path: str) -> bool:
        """Delete a remote file before re-uploading. Best-effort, no-op by default."""
        return False

    def get_capabilities(self) -> PrinterCapabilities:
        """Return the feature capability set for this printer implementation."""
        return PrinterCapabilities()

    def on_forced_offline(self) -> None:
        """Called by PrinterManager when power loss is detected (e.g. smart plug).
        Override to reset vendor-specific state fields beyond connected=False."""

    @property
    def is_idle(self) -> bool:
        """True when the printer has no active job and can accept a new one."""
        return False

    @property
    def is_printing(self) -> bool:
        """True when the printer is actively printing (including warmup/leveling/pausing)."""
        return False
