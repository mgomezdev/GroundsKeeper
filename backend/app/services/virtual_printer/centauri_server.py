"""Virtual Elegoo Centauri server (SDCP WebSocket + HTTP upload).

Simulates an Elegoo Centauri Carbon printer so that Elegoo-compatible slicers
can discover and upload prints to GroundsKeeper without a real Centauri on the
network.  File routing (archive / review queue / print queue) mirrors
VirtualPrinterInstance behaviour.

Protocol summary
----------------
WebSocket at  ws://<host>:<port>/websocket
  Receives Cmd packets from the slicer; responds with Topic messages
  (sdcp/status, sdcp/attributes, sdcp/response).

HTTP at       http://<host>:<port>/uploadFile/upload
  Accepts multipart POST uploads in Elegoo's format, saves to upload_dir,
  then routes the file according to ``mode``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

_DEFAULT_SDCP_PORT = 3030

# SDCP Cmd IDs (same as ElegooCentauriClient)
_CMD_GET_STATUS = 0
_CMD_GET_ATTR = 1
_CMD_START_PRINT = 128
_CMD_SUSPEND_PRINT = 129
_CMD_STOP_PRINT = 130
_CMD_RESTORE_PRINT = 131


class CentauriVirtualInstance:
    """Virtual Elegoo Centauri printer.

    Runs an aiohttp-based SDCP WebSocket server and HTTP upload endpoint so
    Elegoo slicers can send files to GroundsKeeper the same way they would
    send to a real Centauri.
    """

    def __init__(
        self,
        *,
        vp_id: int,
        name: str,
        mode: str,
        sdcp_port: int = _DEFAULT_SDCP_PORT,
        bind_ip: str = "",
        target_printer_id: int | None = None,
        auto_dispatch: bool = True,
        queue_force_color_match: bool = False,
        upload_dir: Path,
        session_factory: Callable | None = None,
        printer_manager=None,
    ):
        self.id = vp_id
        self.name = name
        self.mode = mode
        self.sdcp_port = sdcp_port
        self.bind_ip = bind_ip or "0.0.0.0"
        self.target_printer_id = target_printer_id
        self.auto_dispatch = auto_dispatch
        self.queue_force_color_match = queue_force_color_match
        self.upload_dir = upload_dir
        self._session_factory = session_factory
        self._printer_manager = printer_manager

        # Synthetic mainboard ID for this virtual printer
        self._mainboard_id = f"vp-centauri-{vp_id:04d}"

        self._pending_files: dict[str, Path] = {}
        self._runner = None
        self._site = None
        self._task: asyncio.Task | None = None

        self.upload_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public interface (matches VirtualPrinterInstance API surface used   #
    # by VirtualPrinterManager and the API routes)                        #
    # ------------------------------------------------------------------ #

    @property
    def is_proxy(self) -> bool:
        return False

    @property
    def is_running(self) -> bool:
        return self._runner is not None

    def get_status(self) -> dict:
        return {
            "running": self.is_running,
            "pending_files": len(self._pending_files),
        }

    async def start_server(self) -> None:
        try:
            from aiohttp import web
        except ImportError:
            logger.error("aiohttp is required for virtual Centauri support; install it with 'pip install aiohttp'")
            return

        from aiohttp import web

        app = web.Application()
        app.router.add_get("/websocket", self._ws_handler)
        app.router.add_post("/uploadFile/upload", self._upload_handler)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.bind_ip, self.sdcp_port)
        await self._site.start()
        logger.info("[VP %s] Centauri server started on %s:%d", self.name, self.bind_ip, self.sdcp_port)

    async def stop_server(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
        logger.info("[VP %s] Centauri server stopped", self.name)

    # ------------------------------------------------------------------ #
    # SDCP WebSocket handler                                               #
    # ------------------------------------------------------------------ #

    async def _ws_handler(self, request) -> None:
        from aiohttp import WSMsgType, web

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        peer = request.remote
        logger.info("[VP %s] SDCP client connected from %s", self.name, peer)

        # Push initial status + attributes immediately on connect
        await ws.send_str(self._build_status_msg())
        await ws.send_str(self._build_attr_msg())

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                await self._handle_sdcp_msg(ws, msg.data)
            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break

        logger.info("[VP %s] SDCP client disconnected from %s", self.name, peer)
        return ws

    async def _handle_sdcp_msg(self, ws, raw: str) -> None:
        try:
            pkt = json.loads(raw)
        except Exception:
            return

        outer = pkt.get("Data", {})
        cmd = outer.get("Cmd")
        request_id = outer.get("RequestID", "")

        if cmd == _CMD_GET_STATUS:
            await ws.send_str(self._build_status_msg())
        elif cmd == _CMD_GET_ATTR:
            await ws.send_str(self._build_attr_msg())
        elif cmd in (_CMD_START_PRINT, _CMD_SUSPEND_PRINT, _CMD_STOP_PRINT, _CMD_RESTORE_PRINT):
            # Acknowledge all control commands with Ack=0 (success) but take no action.
            # The virtual printer only receives files via HTTP upload; commands from
            # the slicer are acknowledged to keep the protocol happy.
            await ws.send_str(self._build_response_msg(cmd, request_id, ack=0))
        else:
            # Unknown command — acknowledge with Ack=0 to avoid slicer hangs
            await ws.send_str(self._build_response_msg(cmd, request_id, ack=0))

    def _build_status_msg(self) -> str:
        return json.dumps({
            "Topic": f"sdcp/status/{self._mainboard_id}",
            "Status": {
                "CurrentStatus": [0],  # 0=idle
                "PrintInfo": {
                    "Status": 0,
                    "Progress": 0,
                    "CurrentLayer": 0,
                    "TotalLayer": 0,
                    "Filename": "",
                    "TaskId": "",
                    "CurrentTicks": 0,
                    "TotalTicks": 0,
                    "PrintSpeedPct": 100,
                },
                "TempOfNozzle": 25.0,
                "TempTargetNozzle": 0,
                "TempOfHotbed": 25.0,
                "TempTargetHotbed": 0,
                "CurrentFanSpeed": {"ModelFan": 0, "AuxiliaryFan": 0},
                "LightStatus": {"SecondLight": 0},
            },
        })

    def _build_attr_msg(self) -> str:
        return json.dumps({
            "Topic": f"sdcp/attributes/{self._mainboard_id}",
            "Attributes": {
                "MainboardID": self._mainboard_id,
                "FirmwareVersion": "1.0.0-virtual",
                "MachineName": f"Virtual Centauri ({self.name})",
                "ModelName": "Centauri Carbon",
            },
        })

    def _build_response_msg(self, cmd: int, request_id: str, ack: int = 0) -> str:
        return json.dumps({
            "Topic": f"sdcp/response/{self._mainboard_id}",
            "Data": {
                "Cmd": cmd,
                "Data": {"Ack": ack},
                "RequestID": request_id,
                "MainboardID": self._mainboard_id,
                "TimeStamp": int(time.time()),
                "From": 0,
            },
        })

    # ------------------------------------------------------------------ #
    # HTTP file upload handler                                             #
    # ------------------------------------------------------------------ #

    async def _upload_handler(self, request) -> None:
        from aiohttp import web

        try:
            reader = await request.multipart()
            saved_path: Path | None = None
            filename: str | None = None

            async for part in reader:
                if part.name == "File":
                    filename = part.filename or f"upload_{uuid.uuid4().hex}.3mf"
                    dest = self.upload_dir / filename
                    with dest.open("wb") as f:
                        while True:
                            chunk = await part.read_chunk(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                    saved_path = dest

            if saved_path is None or not saved_path.exists():
                logger.warning("[VP %s] Upload: no file received", self.name)
                return web.Response(
                    content_type="application/json",
                    text=json.dumps({"success": False, "message": "no file received"}),
                )

            logger.info("[VP %s] Received upload: %s (%d bytes)", self.name, filename, saved_path.stat().st_size)
            self._pending_files[saved_path.name] = saved_path

            # Route the file without blocking the HTTP response
            source_ip = request.remote or "unknown"
            asyncio.create_task(self._route_file(saved_path, source_ip))

            return web.Response(
                content_type="application/json",
                text=json.dumps({"success": True, "code": "000000"}),
            )

        except Exception as exc:
            logger.error("[VP %s] Upload error: %s", self.name, exc)
            return web.Response(
                content_type="application/json",
                text=json.dumps({"success": False, "message": str(exc)}),
            )

    # ------------------------------------------------------------------ #
    # File routing (mirrors VirtualPrinterInstance logic)                  #
    # ------------------------------------------------------------------ #

    async def _route_file(self, file_path: Path, source_ip: str) -> None:
        if self.mode == "immediate":
            await self._archive_file(file_path, source_ip)
        elif self.mode == "review":
            await self._queue_file(file_path, source_ip)
        elif self.mode == "print_queue":
            await self._add_to_print_queue(file_path, source_ip)
        else:
            await self._archive_file(file_path, source_ip)

    async def _archive_file(self, file_path: Path, source_ip: str) -> None:
        if not self._session_factory:
            logger.error("[VP %s] Cannot archive: no session factory", self.name)
            return

        if file_path.suffix.lower() != ".3mf":
            self._pending_files.pop(file_path.name, None)
            file_path.unlink(missing_ok=True)
            return

        try:
            from backend.app.api.routes.settings import get_setting
            from backend.app.services.archive import ArchiveService

            async with self._session_factory() as db:
                name_source = await get_setting(db, "virtual_printer_archive_name_source")
                service = ArchiveService(db)
                archive = await service.archive_print(
                    printer_id=None,
                    source_file=file_path,
                    print_data={"status": "archived", "source": "virtual_printer", "source_ip": source_ip},
                    prefer_filename_for_name=(name_source == "filename"),
                )
                if archive:
                    logger.info("[VP %s] Archived: %s - %s", self.name, archive.id, archive.print_name)
                    await self._broadcast_archive_created(archive)
                    file_path.unlink(missing_ok=True)
                    self._pending_files.pop(file_path.name, None)
                else:
                    logger.error("[VP %s] Failed to archive: %s", self.name, file_path.name)
        except Exception as e:
            logger.error("[VP %s] Archive error: %s", self.name, e)

    async def _queue_file(self, file_path: Path, source_ip: str) -> None:
        if not self._session_factory:
            logger.error("[VP %s] Cannot queue: no session factory", self.name)
            return

        if file_path.suffix.lower() != ".3mf":
            self._pending_files.pop(file_path.name, None)
            file_path.unlink(missing_ok=True)
            return

        metadata_print_name: str | None = None
        try:
            from backend.app.services.archive import ThreeMFParser
            parsed = ThreeMFParser(file_path).parse()
            raw_name = parsed.get("print_name")
            if isinstance(raw_name, str) and raw_name.strip():
                metadata_print_name = raw_name.strip()[:255]
        except Exception as e:
            logger.debug("[VP %s] Metadata peek failed for %s: %s", self.name, file_path.name, e)

        try:
            from backend.app.models.pending_upload import PendingUpload

            async with self._session_factory() as db:
                pending = PendingUpload(
                    filename=file_path.name,
                    file_path=str(file_path),
                    file_size=file_path.stat().st_size,
                    source_ip=source_ip,
                    status="pending",
                    uploaded_at=datetime.now(timezone.utc),
                    metadata_print_name=metadata_print_name,
                )
                db.add(pending)
                await db.commit()
                logger.info("[VP %s] Queued: %s - %s", self.name, pending.id, file_path.name)
                self._pending_files.pop(file_path.name, None)
        except Exception as e:
            logger.error("[VP %s] Queue error: %s", self.name, e)

    async def _add_to_print_queue(self, file_path: Path, source_ip: str) -> None:
        if not self._session_factory:
            logger.error("[VP %s] Cannot add to print queue: no session factory", self.name)
            return

        if file_path.suffix.lower() != ".3mf":
            self._pending_files.pop(file_path.name, None)
            file_path.unlink(missing_ok=True)
            return

        try:
            from backend.app.api.routes.settings import get_setting
            from backend.app.models.print_queue import PrintQueueItem
            from backend.app.services.archive import ArchiveService
            from backend.app.services.filament_requirements import extract_filament_requirements

            async with self._session_factory() as db:
                name_source = await get_setting(db, "virtual_printer_archive_name_source")

                def _bool_setting(value, default: bool) -> bool:
                    return value.lower() == "true" if value is not None else default

                bed_levelling = _bool_setting(await get_setting(db, "default_bed_levelling"), True)
                flow_cali = _bool_setting(await get_setting(db, "default_flow_cali"), False)
                vibration_cali = _bool_setting(await get_setting(db, "default_vibration_cali"), True)
                layer_inspect = _bool_setting(await get_setting(db, "default_layer_inspect"), False)
                timelapse = _bool_setting(await get_setting(db, "default_timelapse"), False)

                service = ArchiveService(db)
                archive = await service.archive_print(
                    printer_id=None,
                    source_file=file_path,
                    print_data={"status": "archived", "source": "virtual_printer", "source_ip": source_ip},
                    prefer_filename_for_name=(name_source == "filename"),
                )
                if not archive:
                    logger.error("[VP %s] Failed to archive: %s", self.name, file_path.name)
                    return

                logger.info("[VP %s] Archived: %s - %s", self.name, archive.id, archive.print_name)

                plate_id = self._extract_plate_id(file_path)
                requirements = extract_filament_requirements(file_path, plate_id)
                required_filament_types_json: str | None = None
                filament_overrides_json: str | None = None
                if requirements:
                    types = sorted({r["type"] for r in requirements if r.get("type")})
                    if types:
                        required_filament_types_json = json.dumps(types)
                    if self.queue_force_color_match:
                        overrides = [
                            {"slot_id": r["slot_id"], "type": r.get("type", ""), "color": r.get("color", ""), "force_color_match": True}
                            for r in requirements if r.get("type") and r.get("color")
                        ]
                        if overrides:
                            filament_overrides_json = json.dumps(overrides)

                queue_item = PrintQueueItem(
                    printer_id=self.target_printer_id,
                    archive_id=archive.id,
                    plate_id=plate_id,
                    position=1,
                    status="pending",
                    manual_start=not self.auto_dispatch,
                    required_filament_types=required_filament_types_json,
                    filament_overrides=filament_overrides_json,
                    bed_levelling=bed_levelling,
                    flow_cali=flow_cali,
                    vibration_cali=vibration_cali,
                    layer_inspect=layer_inspect,
                    timelapse=timelapse,
                )
                db.add(queue_item)
                await db.commit()
                logger.info("[VP %s] Added to queue: %s", self.name, queue_item.id)
                await self._broadcast_archive_created(archive)
                file_path.unlink(missing_ok=True)
                self._pending_files.pop(file_path.name, None)
        except Exception as e:
            logger.error("[VP %s] Print queue error: %s", self.name, e)

    async def _broadcast_archive_created(self, archive) -> None:
        try:
            from backend.app.core.websocket import ws_manager
            await ws_manager.send_archive_created({
                "id": archive.id,
                "printer_id": archive.printer_id,
                "filename": archive.filename,
            })
        except Exception as e:
            logger.debug("[VP %s] Broadcast failed: %s", self.name, e)

    @staticmethod
    def _extract_plate_id(file_path: Path) -> int | None:
        try:
            import zipfile
            with zipfile.ZipFile(file_path) as z:
                names = z.namelist()
            for name in names:
                if "Metadata/plate_" in name and name.endswith(".gcode"):
                    stem = name.split("plate_")[1].split(".")[0]
                    return int(stem)
        except Exception:
            pass
        return None
