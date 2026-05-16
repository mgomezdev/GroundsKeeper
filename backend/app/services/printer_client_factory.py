"""Factory that instantiates the correct printer client for a given ORM Printer row."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable

from backend.app.services.abstract_printer_client import AbstractPrinterClient

logger = logging.getLogger(__name__)

# Registry maps printer_type string → client class.
# Each class is imported lazily to avoid circular imports at module load time.
_REGISTRY: dict[str, str] = {
    "bambu": "backend.app.services.bambu_mqtt.BambuMQTTClient",
    "moonraker": "backend.app.services.moonraker_client.MoonrakerClient",
    "elegoo_centauri": "backend.app.services.elegoo_centauri_client.ElegooCentauriClient",
    "snapmaker_u1": "backend.app.services.snapmaker_u1_client.SnapmakerU1Client",
}


def _resolve(printer_type: str):
    """Import and return the client class for the given printer_type."""
    dotted = _REGISTRY.get(printer_type)
    if not dotted:
        raise ValueError(f"Unknown printer_type '{printer_type}'. Registered types: {list(_REGISTRY)}")
    module_path, cls_name = dotted.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, cls_name)


def create_client(
    printer,  # backend.app.models.printer.Printer ORM instance
    on_state_change: Callable | None = None,
    on_print_start: Callable | None = None,
    on_print_complete: Callable | None = None,
    on_ams_change: Callable | None = None,
    on_layer_change: Callable | None = None,
    on_bed_temp_update: Callable | None = None,
) -> AbstractPrinterClient:
    """Instantiate the appropriate client for *printer* and wire up callbacks.

    Each vendor class receives only the constructor kwargs it understands;
    Bambu-specific callbacks (on_ams_change, on_bed_temp_update) are silently
    dropped for non-Bambu clients.
    """
    printer_type = printer.printer_type
    if not printer_type:
        raise ValueError(f"Printer {printer.id} has no printer_type set")
    cls = _resolve(printer_type)

    if printer_type == "bambu":
        cfg = printer.bambu_config
        if cfg is None:
            raise ValueError(f"Printer {printer.id} has printer_type='bambu' but no BambuPrinterConfig row")
        return cls(
            ip_address=printer.ip_address,
            serial_number=cfg.serial_number,
            access_code=cfg.access_code,
            model=printer.model,
            on_state_change=on_state_change,
            on_print_start=on_print_start,
            on_print_complete=on_print_complete,
            on_ams_change=on_ams_change,
            on_layer_change=on_layer_change,
            on_bed_temp_update=on_bed_temp_update,
        )

    # Elegoo Centauri uses SDCP over WebSocket on a fixed port (3030)
    if printer_type == "elegoo_centauri":
        cfg = printer.moonraker_config
        api_key = cfg.api_key if cfg else None
        return cls(
            ip_address=printer.ip_address,
            port=3030,  # SDCP WebSocket port is hardcoded in Elegoo firmware
            api_key=api_key,
            on_state_change=on_state_change,
            on_print_start=on_print_start,
            on_print_complete=on_print_complete,
            on_layer_change=on_layer_change,
        )

    # All remaining Moonraker-based clients share the same constructor shape
    cfg = printer.moonraker_config
    if cfg is None:
        logger.warning("Printer %d (%s) has no MoonrakerPrinterConfig row; using defaults", printer.id, printer_type)
    port = cfg.port if cfg else 7125
    api_key = cfg.api_key if cfg else None
    return cls(
        ip_address=printer.ip_address,
        port=port,
        api_key=api_key,
        on_state_change=on_state_change,
        on_print_start=on_print_start,
        on_print_complete=on_print_complete,
        on_layer_change=on_layer_change,
    )
