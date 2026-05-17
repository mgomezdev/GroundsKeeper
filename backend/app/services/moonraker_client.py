"""Moonraker HTTP/WebSocket client for Klipper-based printers.

Moonraker API reference: https://moonraker.readthedocs.io/en/latest/web_api/

All public control methods (start_print, stop_print, etc.) are synchronous to
match the BambuMQTTClient interface.  HTTP calls use httpx's sync client so
they complete inline without blocking the asyncio event loop for long — printer
commands are small, fast requests.

Background status polling runs in a daemon thread that calls the Moonraker
objects/query endpoint on a fixed interval and fires the on_state_change
callback whenever relevant fields change.
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from backend.app.services.abstract_printer_client import AbstractPrinterClient

logger = logging.getLogger(__name__)

# Moonraker printer object subscriptions for status polling
_POLL_OBJECTS = (
    "webhooks",
    "print_stats",
    "display_status",
    "toolhead",
    "extruder",
    "extruder1",
    "heater_bed",
    "fan",
    "gcode_move",
    "virtual_sdcard",
)

# Seconds between background status polls
_POLL_INTERVAL = 5.0


@dataclass
class MoonrakerState:
    """Live state snapshot for a Moonraker/Klipper printer."""

    connected: bool = False
    klippy_state: str = "disconnected"  # "ready" | "startup" | "shutdown" | "error"
    print_state: str = "standby"  # "printing" | "paused" | "complete" | "standby" | "error" | "cancelled"
    filename: str | None = None
    progress: float = 0.0
    layer_num: int | None = None
    total_layers: int | None = None
    print_duration: float = 0.0
    temperatures: dict = field(default_factory=dict)
    fan_speed: float = 0.0
    speed_factor: float = 1.0
    firmware_version: str | None = None
    # raw is excluded from equality comparison so it doesn't suppress change detection
    raw: dict = field(default_factory=dict, compare=False)


class MoonrakerClient(AbstractPrinterClient):
    """Base Moonraker client. Subclass per vendor for any quirks."""

    printer_type = "moonraker"

    def __init__(
        self,
        ip_address: str,
        port: int = 7125,
        api_key: str | None = None,
        on_state_change: Callable[[MoonrakerState], None] | None = None,
        on_print_start: Callable[[dict], None] | None = None,
        on_print_complete: Callable[[dict], None] | None = None,
        on_layer_change: Callable[[int], None] | None = None,
    ):
        self.ip_address = ip_address
        self.port = port
        self.api_key = api_key
        self.on_state_change = on_state_change
        self.on_print_start = on_print_start
        self.on_print_complete = on_print_complete
        self.on_layer_change = on_layer_change

        self.state = MoonrakerState()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._poll_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._http = self._make_http_client()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _make_http_client(self) -> httpx.Client:
        headers = {}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return httpx.Client(
            base_url=f"http://{self.ip_address}:{self.port}",
            headers=headers,
            timeout=10.0,
        )

    def _get(self, path: str, **params) -> dict | None:
        """Return parsed result dict, or None on any error."""
        try:
            r = self._http.get(path, params=params or None)
            r.raise_for_status()
            return r.json().get("result", {})
        except Exception as exc:
            logger.debug("[%s] GET %s failed: %s", self.ip_address, path, exc)
            return None

    def _post(self, path: str, **params) -> dict | str | None:
        """Return parsed result, or None on any error."""
        try:
            r = self._http.post(path, params=params or None)
            r.raise_for_status()
            return r.json().get("result", {})
        except Exception as exc:
            logger.debug("[%s] POST %s failed: %s", self.ip_address, path, exc)
            return None

    def _post_json(self, path: str, body: dict) -> dict | None:
        """Return parsed result, or None on any error."""
        try:
            r = self._http.post(path, json=body)
            r.raise_for_status()
            return r.json().get("result", {})
        except Exception as exc:
            logger.debug("[%s] POST %s failed: %s", self.ip_address, path, exc)
            return None

    # ------------------------------------------------------------------ #
    # Status polling                                                        #
    # ------------------------------------------------------------------ #

    def _parse_state(self, data: dict) -> MoonrakerState:
        s = MoonrakerState()
        s.raw = data

        webhooks = data.get("webhooks", {})
        s.klippy_state = webhooks.get("state", "disconnected")
        s.connected = s.klippy_state == "ready"

        print_stats = data.get("print_stats", {})
        s.print_state = print_stats.get("state", "standby")
        s.filename = print_stats.get("filename") or None
        s.print_duration = print_stats.get("print_duration", 0.0)
        info = print_stats.get("info", {})
        s.layer_num = info.get("current_layer")
        s.total_layers = info.get("total_layer")

        display = data.get("display_status", {})
        s.progress = round((display.get("progress") or 0.0) * 100, 1)

        temps: dict = {}
        extruder = data.get("extruder", {})
        if extruder:
            temps["nozzle"] = extruder.get("temperature", 0)
            temps["nozzle_target"] = extruder.get("target", 0)
        extruder1 = data.get("extruder1", {})
        if extruder1:
            temps["nozzle_2"] = extruder1.get("temperature", 0)
            temps["nozzle_2_target"] = extruder1.get("target", 0)
        bed = data.get("heater_bed", {})
        if bed:
            temps["bed"] = bed.get("temperature", 0)
            temps["bed_target"] = bed.get("target", 0)
        s.temperatures = temps

        fan = data.get("fan", {})
        s.fan_speed = round((fan.get("speed") or 0.0) * 100)

        gcode_move = data.get("gcode_move", {})
        s.speed_factor = gcode_move.get("speed_factor", 1.0)

        return s

    def _poll_loop(self):
        query = ",".join(_POLL_OBJECTS)
        prev_print_state = None
        prev_layer = None

        while not self._stop_event.is_set():
            data = self._get("/printer/objects/query", objects=query)

            if data is None:
                # HTTP failure — mark disconnected and wait before retrying
                self.state.connected = False
                self._stop_event.wait(_POLL_INTERVAL)
                continue

            status = data.get("status", {})
            new_state = self._parse_state(status)

            state_changed = new_state != self.state
            self.state = new_state

            if state_changed and self.on_state_change:
                self.on_state_change(new_state)

            # Print start event
            if new_state.print_state == "printing" and prev_print_state != "printing":
                if self.on_print_start:
                    self.on_print_start({"filename": new_state.filename})

            # Print complete event
            if new_state.print_state == "complete" and prev_print_state == "printing":
                if self.on_print_complete:
                    self.on_print_complete({"filename": new_state.filename})

            # Layer change event
            if (
                new_state.layer_num is not None
                and new_state.layer_num != prev_layer
                and new_state.layer_num > 0
            ):
                if self.on_layer_change:
                    self.on_layer_change(new_state.layer_num)
                prev_layer = new_state.layer_num

            prev_print_state = new_state.print_state
            self._stop_event.wait(_POLL_INTERVAL)

    # ------------------------------------------------------------------ #
    # AbstractPrinterClient interface                                       #
    # ------------------------------------------------------------------ #

    @property
    def connected(self) -> bool:
        return self.state.connected

    def connect(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._loop = loop
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name=f"moonraker-{self.ip_address}")
        self._poll_thread.start()
        logger.info("[%s] MoonrakerClient polling started", self.ip_address)

    def disconnect(self, timeout: float = 0) -> None:
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=max(timeout, 2.0))
        self.state.connected = False
        self._http.close()
        logger.info("[%s] MoonrakerClient disconnected", self.ip_address)

    def check_staleness(self) -> bool:
        # Poll thread updates state continuously; no separate staleness check needed
        return self.state.connected

    def start_print(self, file_name: str) -> bool:
        return self._post("/printer/print/start", filename=file_name) is not None

    def stop_print(self) -> bool:
        return self._post("/printer/print/cancel") is not None

    def pause_print(self) -> bool:
        return self._post("/printer/print/pause") is not None

    def resume_print(self) -> bool:
        return self._post("/printer/print/resume") is not None

    def send_gcode(self, gcode: str) -> bool:
        return self._post("/printer/gcode/script", script=gcode) is not None

    def request_status_update(self) -> bool:
        # Poll thread is continuous; a manual poll on demand is a no-op
        return self.connected

    # ------------------------------------------------------------------ #
    # Connection test (class-level, no instance required)                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def test_connection(cls, ip_address: str, port: int = 7125, api_key: str | None = None) -> dict:
        """Probe Moonraker and return basic printer info."""
        headers = {"X-Api-Key": api_key} if api_key else {}
        try:
            with httpx.Client(timeout=5.0, headers=headers) as client:
                r = client.get(f"http://{ip_address}:{port}/printer/info")
                r.raise_for_status()
                info = r.json().get("result", {})
                return {
                    "success": True,
                    "state": info.get("state"),
                    "model": None,
                }
        except Exception as exc:
            return {"success": False, "state": None, "model": None, "error": str(exc)}
