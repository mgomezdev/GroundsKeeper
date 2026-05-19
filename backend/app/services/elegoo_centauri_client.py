"""Elegoo Centauri Carbon SDCP WebSocket client.

SDCP (Chitubox Data Communication Protocol) is the proprietary control
protocol used by Elegoo FFF printers.  The printer exposes a WebSocket on
port 3030 (/websocket path) and publishes JSON messages on MQTT-style topics:

  sdcp/status/<MainboardID>     -- live status (temps, print progress)
  sdcp/attributes/<MainboardID> -- static info (firmware version, model name)
  sdcp/response/<MainboardID>   -- command acknowledgements
  sdcp/error/<MainboardID>      -- error events

Outgoing message format:
  {"Id": "", "Data": {"Cmd": <int>, "Data": {}, "RequestID": "<uuid>",
                      "MainboardID": "", "TimeStamp": <unix_sec>, "From": 1}}

Command IDs (Cmd):
  0:   GET_PRINTER_STATUS
  1:   GET_PRINTER_ATTR
  128: SEND_PRINTER_START_PRINT  -- Data: {"Filename": "<path>"}
  129: SEND_PRINTER_SUSPEND_PRINT (pause)
  130: SEND_PRINTER_STOP_PRINT
  131: SEND_PRINTER_RESTORE_PRINT (resume)

Status.CurrentStatus[] codes:
  0: idle/standby
  1: printing (check PrintInfo.Status for pause sub-state)
  8: print complete

Status.PrintInfo.Status sub-state codes:
  0:  idle
  1:  warming up / cancelling
  5:  pausing
  6:  paused
  8:  cancelled
  9:  complete
  13: printing
  14: cancelled (alternate)
  20: bed leveling
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import websocket

from backend.app.services.abstract_printer_client import AbstractPrinterClient

logger = logging.getLogger(__name__)

# SDCP command IDs
_CMD_GET_STATUS = 0
_CMD_GET_ATTR = 1
_CMD_START_PRINT = 128
_CMD_SUSPEND_PRINT = 129
_CMD_STOP_PRINT = 130
_CMD_RESTORE_PRINT = 131
_CMD_EDIT_AXIS_NUMBER = 401        # EDIT_PRINTER_AXIS_NUMBER: {"Axis": "Z", "Step": <mm>}
_CMD_EDIT_AXIS_ZERO = 402          # EDIT_PRINTER_AXIS_ZERO:   {"Axis": "XYZ"}
_CMD_GET_BLACKOUT = 134           # GET_BLACKOUT_STATUS
_CMD_SEND_BLACKOUT = 135          # SEND_BLACKOUT_ACTION (reactive only — printer-initiated)
_CMD_EDIT_VIDEO_STREAMING = 386   # EDIT_PRINTER_VIDEO_STREAMING: Enable=1 start, Enable=0 stop
_CMD_EDIT_STATUS_DATA = 403       # EDIT_PRINTER_STATUS_DATA — proactive light/fan control
_CMD_GET_FILE_LIST = 258          # GET_FILE_LIST: {"Url": "/local/"}
_CMD_DELETE_FILE = 259            # DELETE_FILE: {"FileList": [...], "FolderList": [...]}

# CurrentStatus array codes
_CS_PRINTING = 1
_CS_COMPLETE = 8

# PrintInfo.Status → print_state mapping (OctoEverywhere elegoomodels.py GetCurrentStatus)
# CurrentStatus=[8] (complete) overrides this table; all other states use the table as primary.
_PRINT_STATE_MAP: dict[int, str] = {
    0: "standby",
    1: "warming_up",   # warmup / cancellation warmup
    5: "pausing",
    6: "paused",
    8: "cancelled",
    9: "complete",
    13: "printing",
    14: "cancelled",   # alternate cancelled code
    20: "leveling",    # bed leveling sub-state
}

SDCP_PORT = 3030
_RECONNECT_DELAY = 5.0


@dataclass
class ElegooState:
    """Live state snapshot for an Elegoo Centauri Carbon (SDCP) printer."""

    connected: bool = False
    current_status: list[int] = field(default_factory=list)
    # Mapped print state: "standby" | "warming_up" | "leveling" | "printing" | "pausing" | "paused" | "cancelled" | "complete"
    print_state: str = "standby"
    filename: str | None = None
    task_id: str | None = None
    progress: float = 0.0
    layer_num: int | None = None
    total_layers: int | None = None
    current_ticks: float = 0.0    # elapsed print time, seconds
    total_ticks: float = 0.0      # estimated total print time, seconds
    print_speed_pct: int = 100
    temperatures: dict = field(default_factory=dict)
    fan_model: int = 0            # part-cooling fan 0-100
    fan_aux: int = 0              # auxiliary fan 0-100
    chamber_light: bool = False   # LightStatus.SecondLight
    rgb_light: list = field(default_factory=lambda: [0, 0, 0])  # LightStatus.RgbLight
    video_url: str | None = None  # populated on first successful Cmd 386 response
    firmware_version: str | None = None
    machine_name: str | None = None
    mainboard_id: str | None = None
    # raw is excluded from equality so it never suppresses change detection
    raw: dict = field(default_factory=dict, compare=False)

    @property
    def raw_data(self) -> dict | None:
        """Compat shim: Bambu code guards on 'if state.raw_data'. Always None here so
        those guards skip AMS/vt_tray processing that doesn't apply to Elegoo."""
        return None

    @property
    def state(self) -> str:
        """Compat shim: returns print_state for logging and dedup-key use."""
        return self.print_state


class ElegooCentauriClient(AbstractPrinterClient):
    """Elegoo Centauri Carbon SDCP client.

    Connects to ws://<ip>:3030/websocket, sends GET_STATUS and GET_ATTR
    on connect, then processes incoming sdcp/status and sdcp/attributes
    messages in a background daemon thread.  Reconnects automatically on
    unexpected disconnection.
    """

    printer_type = "elegoo_centauri"

    @classmethod
    def connection_fields(cls) -> list:
        from backend.app.services.abstract_printer_client import ConnectionField
        return [
            ConnectionField(
                name="port",
                label="Port",
                field_type="number",
                required=True,
                default=SDCP_PORT,
                placeholder=str(SDCP_PORT),
                help_text="SDCP WebSocket port (default 3030)",
            ),
        ]

    def __init__(
        self,
        ip_address: str,
        port: int = SDCP_PORT,
        api_key: str | None = None,  # not used by SDCP; accepted for compat
        on_state_change: Callable[[ElegooState], None] | None = None,
        on_print_start: Callable[[dict], None] | None = None,
        on_print_complete: Callable[[dict], None] | None = None,
        on_layer_change: Callable[[int], None] | None = None,
    ):
        self.ip_address = ip_address
        self.port = port
        self.on_state_change = on_state_change
        self.on_print_start = on_print_start
        self.on_print_complete = on_print_complete
        self.on_layer_change = on_layer_change

        self.state = ElegooState()
        self._ws: websocket.WebSocketApp | None = None
        self._ws_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._mainboard_id: str | None = None
        self._prev_print_state: str = "standby"
        self._prev_layer: int | None = None
        self._lock = threading.Lock()
        self._video_url_event = threading.Event()
        self._pending_video_url: str | None = None
        self._pending_acks: dict[str, threading.Event] = {}
        self._ack_results: dict[str, int] = {}
        self._response_data: dict[str, dict] = {}

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _build_cmd(self, cmd: int, data: dict | None = None, request_id: str | None = None) -> str:
        return json.dumps({
            "Id": "",
            "Data": {
                "Cmd": cmd,
                "Data": data or {},
                "RequestID": request_id or uuid.uuid4().hex,
                "MainboardID": self._mainboard_id or "",
                "TimeStamp": int(time.time()),
                "From": 1,
            },
        })

    def _send(self, cmd: int, data: dict | None = None, wait_ack: bool = False, ack_timeout: float = 10.0) -> bool:
        ws = self._ws
        if ws is None:
            return False
        request_id = uuid.uuid4().hex
        event = threading.Event()
        if wait_ack:
            self._pending_acks[request_id] = event
        try:
            ws.send(self._build_cmd(cmd, data, request_id))
            if not wait_ack:
                return True
            if not event.wait(timeout=ack_timeout):
                self._pending_acks.pop(request_id, None)
                self._ack_results.pop(request_id, None)
                self._response_data.pop(request_id, None)
                logger.debug("[%s] SDCP ack timeout for cmd=%d", self.ip_address, cmd)
                return False
            self._response_data.pop(request_id, None)
            return self._ack_results.pop(request_id, -1) == 0
        except Exception as exc:
            self._pending_acks.pop(request_id, None)
            logger.debug("[%s] SDCP send cmd=%d failed: %s", self.ip_address, cmd, exc)
            return False

    def _send_with_response(self, cmd: int, data: dict | None = None, timeout: float = 10.0) -> tuple[bool, dict]:
        """Send a command and return (success, response_data_dict)."""
        ws = self._ws
        if ws is None:
            return False, {}
        request_id = uuid.uuid4().hex
        event = threading.Event()
        self._pending_acks[request_id] = event
        try:
            ws.send(self._build_cmd(cmd, data, request_id))
            if not event.wait(timeout=timeout):
                self._pending_acks.pop(request_id, None)
                self._ack_results.pop(request_id, None)
                self._response_data.pop(request_id, None)
                logger.debug("[%s] SDCP response timeout for cmd=%d", self.ip_address, cmd)
                return False, {}
            ack = self._ack_results.pop(request_id, -1)
            resp = self._response_data.pop(request_id, {})
            return ack == 0, resp
        except Exception as exc:
            self._pending_acks.pop(request_id, None)
            logger.debug("[%s] SDCP send cmd=%d failed: %s", self.ip_address, cmd, exc)
            return False, {}

    def _run_sdcp_keepalive(self) -> None:
        while not self._stop_event.wait(50):
            self._send(_CMD_GET_STATUS)

    def _parse_status_msg(self, msg: dict) -> ElegooState:
        s = ElegooState()
        s.raw = msg
        s.connected = True
        status = msg.get("Status", {})

        cs = status.get("CurrentStatus", [])
        s.current_status = cs

        print_info = status.get("PrintInfo", {})
        ps = print_info.get("Status", 0)

        # CurrentStatus=[8] is a definitive printer-level "complete" signal.
        # Otherwise use PrintInfo.Status as the primary discriminator, with
        # CurrentStatus=[1] as a fallback for unknown sub-states mid-print.
        if _CS_COMPLETE in cs:
            s.print_state = "complete"
        elif ps in _PRINT_STATE_MAP:
            s.print_state = _PRINT_STATE_MAP[ps]
        elif _CS_PRINTING in cs:
            s.print_state = "printing"
        else:
            s.print_state = "standby"

        s.filename = print_info.get("Filename") or None
        s.task_id = print_info.get("TaskId") or None
        s.progress = float(print_info.get("Progress", 0))
        s.layer_num = print_info.get("CurrentLayer")
        s.total_layers = print_info.get("TotalLayer")
        s.current_ticks = float(print_info.get("CurrentTicks", 0))
        s.total_ticks = float(print_info.get("TotalTicks", 0))
        s.print_speed_pct = int(print_info.get("PrintSpeedPct", 100))

        temps: dict = {}
        for sdcp_key, field_name in (
            ("TempOfNozzle", "nozzle"),
            ("TempTargetNozzle", "nozzle_target"),
            ("TempOfHotbed", "bed"),
            ("TempTargetHotbed", "bed_target"),
            ("TempOfBox", "chamber"),
            ("TempTargetBox", "chamber_target"),
        ):
            val = status.get(sdcp_key)
            if val is not None:
                temps[field_name] = round(float(val), 1)
        s.temperatures = temps

        fans = status.get("CurrentFanSpeed", {})
        s.fan_model = int(fans.get("ModelFan", 0))
        s.fan_aux = int(fans.get("AuxiliaryFan", 0))

        light = status.get("LightStatus", {})
        s.chamber_light = bool(light.get("SecondLight", 0))
        if "RgbLight" in light:
            s.rgb_light = light["RgbLight"]

        # Carry over persistent attrs not present in the status message
        with self._lock:
            s.firmware_version = self.state.firmware_version
            s.machine_name = self.state.machine_name
            s.mainboard_id = self._mainboard_id or self.state.mainboard_id

        return s

    def _parse_response_msg(self, msg: dict) -> None:
        # Response envelope: {"Data": {"Cmd": N, "Data": {"Ack": N, ...}, "RequestID": "...", ...}, ...}
        outer = msg.get("Data", {})
        inner = outer.get("Data", {})
        request_id = outer.get("RequestID", "")
        ack = inner.get("Ack", -1)

        # Resolve any waiting caller
        event = self._pending_acks.pop(request_id, None)
        if event is not None:
            self._ack_results[request_id] = ack
            self._response_data[request_id] = inner
            event.set()

        if outer.get("Cmd") != _CMD_EDIT_VIDEO_STREAMING:
            return
        logger.debug("[%s] SDCP video stream response: %s", self.ip_address, inner)
        if ack == 0:
            url = inner.get("VideoUrl") or f"http://{self.ip_address}:3031/video"
            if not url.startswith("http"):
                url = f"http://{url}"
            self._pending_video_url = url
            with self._lock:
                self.state.video_url = url
            self._video_url_event.set()

    def _parse_error_msg(self, msg: dict) -> None:
        data = msg.get("Data", {})
        inner = data.get("Data", {})
        cmd = data.get("Cmd", -1)
        ack = inner.get("Ack", -1)
        logger.warning("[%s] SDCP error: cmd=%d ack=%d payload=%s", self.ip_address, cmd, ack, inner)
        # Unblock any caller waiting on this request so it gets the error ack
        # instead of timing out (prevents 10-second hangs on printer rejection).
        request_id = data.get("RequestID", "")
        event = self._pending_acks.pop(request_id, None)
        if event is not None:
            self._ack_results[request_id] = ack
            self._response_data[request_id] = inner
            event.set()

    def _parse_attr_msg(self, msg: dict) -> None:
        attrs = msg.get("Attributes", {})
        logger.debug("[%s] SDCP attributes keys: %s", self.ip_address, list(attrs.keys()))
        mid = attrs.get("MainboardID")
        if mid:
            self._mainboard_id = mid
        with self._lock:
            self.state.firmware_version = attrs.get("FirmwareVersion")
            self.state.machine_name = attrs.get("MachineName") or attrs.get("Name") or attrs.get("ModelName")
            self.state.mainboard_id = mid or self.state.mainboard_id

    # ------------------------------------------------------------------ #
    # WebSocket callbacks                                                   #
    # ------------------------------------------------------------------ #

    def _on_ws_open(self, ws: websocket.WebSocketApp) -> None:
        logger.info("[%s] SDCP WebSocket connected", self.ip_address)
        ws.send(self._build_cmd(_CMD_GET_STATUS))
        ws.send(self._build_cmd(_CMD_GET_ATTR))

    def _on_ws_message(self, ws: websocket.WebSocketApp, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return

        topic = msg.get("Topic", "")

        if "sdcp/status" in topic:
            new_state = self._parse_status_msg(msg)
            state_changed = new_state != self.state
            with self._lock:
                self.state = new_state

            if state_changed and self.on_state_change:
                self.on_state_change(new_state)

            prev = self._prev_print_state
            if new_state.print_state == "printing" and prev != "printing":
                if self.on_print_start:
                    self.on_print_start({"filename": new_state.filename})
            elif new_state.print_state == "complete" and prev == "printing":
                if self.on_print_complete:
                    self.on_print_complete({"filename": new_state.filename})

            if (
                new_state.layer_num is not None
                and new_state.layer_num != self._prev_layer
                and new_state.layer_num > 0
            ):
                if self.on_layer_change:
                    self.on_layer_change(new_state.layer_num)
                self._prev_layer = new_state.layer_num

            self._prev_print_state = new_state.print_state

        elif "sdcp/attributes" in topic:
            self._parse_attr_msg(msg)

        elif "sdcp/response" in topic:
            self._parse_response_msg(msg)

        elif "sdcp/error" in topic:
            self._parse_error_msg(msg)

    def _on_ws_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        logger.debug("[%s] SDCP WebSocket error: %s", self.ip_address, error)

    def _on_ws_close(self, ws: websocket.WebSocketApp, close_code, close_msg) -> None:
        logger.debug("[%s] SDCP WebSocket closed (code=%s)", self.ip_address, close_code)
        with self._lock:
            self.state.connected = False
        if self.on_state_change and not self._stop_event.is_set():
            self.on_state_change(self.state)

    def _run_ws(self) -> None:
        url = f"ws://{self.ip_address}:{self.port}/websocket"
        while not self._stop_event.is_set():
            try:
                ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_ws_open,
                    on_message=self._on_ws_message,
                    on_error=self._on_ws_error,
                    on_close=self._on_ws_close,
                )
                self._ws = ws
                ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as exc:
                logger.debug("[%s] SDCP run_forever error: %s", self.ip_address, exc)
            finally:
                self._ws = None
            if not self._stop_event.is_set():
                self._stop_event.wait(_RECONNECT_DELAY)

    # ------------------------------------------------------------------ #
    # AbstractPrinterClient interface                                       #
    # ------------------------------------------------------------------ #

    @property
    def connected(self) -> bool:
        return self.state.connected

    def connect(self, loop=None) -> None:
        self._stop_event.clear()
        self._ws_thread = threading.Thread(
            target=self._run_ws,
            daemon=True,
            name=f"elegoo-{self.ip_address}",
        )
        self._ws_thread.start()
        threading.Thread(
            target=self._run_sdcp_keepalive,
            daemon=True,
            name=f"elegoo-ka-{self.ip_address}",
        ).start()
        logger.info(
            "[%s] ElegooCentauriClient started (SDCP ws port %d)",
            self.ip_address,
            self.port,
        )

    def disconnect(self, timeout: float = 0) -> None:
        self._stop_event.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=max(timeout, 3.0))
        with self._lock:
            self.state.connected = False
        logger.info("[%s] ElegooCentauriClient stopped", self.ip_address)

    def check_staleness(self) -> bool:
        return self.state.connected

    def start_print(self, file_name: str, options=None) -> bool:
        return self._send(_CMD_START_PRINT, {"Filename": file_name}, wait_ack=True)

    def stop_print(self) -> bool:
        return self._send(_CMD_STOP_PRINT, wait_ack=True)

    def pause_print(self) -> bool:
        return self._send(_CMD_SUSPEND_PRINT, wait_ack=True)

    def resume_print(self) -> bool:
        return self._send(_CMD_RESTORE_PRINT, wait_ack=True)

    @property
    def gcode_supported(self) -> bool:
        return False

    def home(self) -> bool:
        # Cmd 402 EDIT_PRINTER_AXIS_ZERO: homes all axes (confirmed via ELEGOO SDK + OctoEverywhere)
        return self._send(_CMD_EDIT_AXIS_ZERO, {"Axis": "XYZ"}, wait_ack=True)

    def jog_z(self, distance_mm: float, force: bool = False) -> bool:
        # Cmd 401 EDIT_PRINTER_AXIS_NUMBER: step Z by distance_mm (payload confirmed via ELEGOO SDK)
        return self._send(_CMD_EDIT_AXIS_NUMBER, {"Axis": "Z", "Step": distance_mm}, wait_ack=True)

    def send_gcode(self, gcode: str) -> bool:
        logger.warning(
            "[%s] send_gcode not supported on Elegoo Centauri (no raw GCode channel)",
            self.ip_address,
        )
        return False

    def start_video_stream(self, timeout: float = 5.0) -> str:
        """Activate the MJPEG stream (Cmd 386) and return the stream URL.

        Falls back to the conventional port-3031 URL if the printer doesn't
        return a VideoUrl in its response within *timeout* seconds.
        """
        self._video_url_event.clear()
        self._pending_video_url = None
        self._send(_CMD_EDIT_VIDEO_STREAMING, {"Enable": 1})
        self._video_url_event.wait(timeout=timeout)
        url = self._pending_video_url or f"http://{self.ip_address}:3031/video"
        return f"{url}?timestamp={int(time.time())}"

    def ping_video_stream(self) -> None:
        """Re-send the stream activation command to reset the printer's 60-second inactivity timer."""
        self._send(_CMD_EDIT_VIDEO_STREAMING, {"Enable": 1})

    def stop_video_stream(self) -> None:
        """Deactivate the MJPEG stream (Cmd 386 with Enable=0)."""
        self._send(_CMD_EDIT_VIDEO_STREAMING, {"Enable": 0})

    def set_chamber_light(self, on: bool) -> bool:
        # EDIT_PRINTER_STATUS_DATA (403): preserve current RgbLight to avoid resetting accent colour
        with self._lock:
            rgb = list(self.state.rgb_light)
        success = self._send(
            _CMD_EDIT_STATUS_DATA,
            {"LightStatus": {"SecondLight": on, "RgbLight": rgb}},
            wait_ack=True,
        )
        if success:
            with self._lock:
                self.state.chamber_light = on
        return success

    # ------------------------------------------------------------------ #
    # File management                                                       #
    # ------------------------------------------------------------------ #

    @property
    def file_upload_supported(self) -> bool:
        return True

    file_listing_supported = True

    def upload_file(self, file_data: bytes, filename: str) -> bool:
        """Upload a file to /local/<filename> via HTTP multipart POST."""
        import hashlib

        import httpx

        url = f"http://{self.ip_address}:{self.port}/uploadFile/upload"
        md5 = hashlib.md5(file_data).hexdigest()  # nosec B324
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    url,
                    data={
                        "TotalSize": str(len(file_data)),
                        "Uuid": uuid.uuid4().hex,
                        "Offset": "0",
                        "Check": "1",
                        "S-File-MD5": md5,
                    },
                    files={"File": (filename, file_data, "application/octet-stream")},
                )
            result = resp.json()
            ok = result.get("success") is True or result.get("code") == "000000"
            if not ok:
                logger.error("[%s] Upload rejected: %s", self.ip_address, result)
            return ok
        except Exception as exc:
            logger.error("[%s] File upload failed: %s", self.ip_address, exc)
            return False

    async def upload_file_async(
        self,
        file_path,
        remote_path: str,
        progress_callback=None,
        non_retry_exceptions: tuple = (),
    ) -> bool:
        """Async file upload via HTTP multipart POST (runs sync upload in executor)."""
        import asyncio
        filename = remote_path.lstrip("/")
        file_path_obj = file_path if hasattr(file_path, "read_bytes") else __import__("pathlib").Path(file_path)
        file_data = file_path_obj.read_bytes()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.upload_file, file_data, filename)

    async def delete_remote_file(self, remote_path: str) -> bool:
        """Delete a remote file via SDCP Cmd 259 (best-effort)."""
        import asyncio
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self.delete_file, remote_path)
        except Exception:
            return False

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
            chamber_light=True,
            gcode=False,
            pause_resume=True,
            skip_objects=False,
            multi_nozzle=False,
        )

    def list_files(self, directory: str = "/local/") -> list[dict]:
        """Return normalized file list for *directory* via SDCP Cmd 258."""
        ok, data = self._send_with_response(_CMD_GET_FILE_LIST, {"Url": directory})
        if not ok:
            return []
        prefix = directory.rstrip("/")
        return [
            {
                "name": f.get("FileName", ""),
                "size": f.get("FileSize", 0),
                "path": f"{prefix}/{f.get('FileName', '')}",
                "is_directory": False,
            }
            for f in data.get("FileList", [])
        ]

    def delete_file(self, remote_path: str) -> bool:
        """Delete a single file by its full path via SDCP Cmd 259."""
        return self._send(_CMD_DELETE_FILE, {"FileList": [remote_path], "FolderList": []}, wait_ack=True)

    def get_loaded_filaments(self) -> list[dict]:
        """Elegoo has a single external spool with unknown filament type."""
        return [
            {
                "type": "",
                "color": "#808080",
                "tray_info_idx": "",
                "tray_sub_brands": "",
                "extruder_id": None,
                "is_external": True,
            }
        ]

    @property
    def is_idle(self) -> bool:
        return self.state.print_state in ("standby", "complete", "cancelled")

    @property
    def is_printing(self) -> bool:
        return self.state.print_state in ("printing", "warming_up", "leveling", "pausing")

    def request_status_update(self) -> bool:
        return self._send(_CMD_GET_STATUS)

    # ------------------------------------------------------------------ #
    # Connection test (class-level, no instance required)                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def test_connection(cls, ip_address: str, port: int = SDCP_PORT, api_key: str | None = None) -> dict:
        """Connect and retrieve attributes to verify connectivity."""
        result: dict = {"success": False, "state": None, "model": None}
        ev = threading.Event()

        def on_open(ws):
            ws.send(json.dumps({
                "Id": "",
                "Data": {
                    "Cmd": _CMD_GET_ATTR,
                    "Data": {},
                    "RequestID": uuid.uuid4().hex,
                    "MainboardID": "",
                    "TimeStamp": int(time.time()),
                    "From": 1,
                },
            }))

        def on_message(ws, raw):
            try:
                msg = json.loads(raw)
                if "sdcp/attributes" in msg.get("Topic", ""):
                    attrs = msg.get("Attributes", {})
                    result["success"] = True
                    result["model"] = attrs.get("MachineName")
                    result["state"] = "ready"
                    ev.set()
                    ws.close()
            except Exception:
                pass

        def on_error(ws, error):
            result["error"] = str(error)
            ev.set()

        ws = websocket.WebSocketApp(
            f"ws://{ip_address}:{port}/websocket",
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
        )
        t = threading.Thread(target=ws.run_forever)
        t.daemon = True
        t.start()
        ev.wait(timeout=8)
        try:
            ws.close()
        except Exception:
            pass
        return result
