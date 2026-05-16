import asyncio
from abc import ABC, abstractmethod
from typing import ClassVar


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
    def start_print(self, file_name: str) -> bool:
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

    def set_chamber_light(self, on: bool) -> bool:
        """Turn the chamber/work light on or off. Subclasses override if supported."""
        return False
