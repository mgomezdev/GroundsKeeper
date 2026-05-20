"""Factory that instantiates the correct printer client for a given ORM Printer row."""

from __future__ import annotations

import dataclasses
import importlib
import json
import logging
from collections.abc import Callable

from backend.app.services.abstract_printer_client import AbstractPrinterClient

logger = logging.getLogger(__name__)


def _parse_printer_config(printer) -> dict:
    """Return the printer_config JSON dict, or {} if absent/malformed."""
    raw = getattr(printer, "printer_config", None)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("Printer %d has malformed printer_config JSON; ignoring", printer.id)
        return {}

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


# Ordered list of printer types available in the add-printer UI.
# Add new entries here when a new vendor client is ready for users.
_UI_TYPES: list[tuple[str, str]] = [
    ("bambu", "Bambu Lab"),
    ("elegoo_centauri", "Elegoo Centauri"),
]


def get_printer_types_for_ui() -> list[dict]:
    """Return available printer types with display names and connection fields.

    Called by GET /api/v1/printers/types. Reads connection_fields() from each
    registered client class — no DB access needed.
    """
    result = []
    for printer_type, display_name in _UI_TYPES:
        cls = _resolve(printer_type)
        result.append(
            {
                "printer_type": printer_type,
                "display_name": display_name,
                "connection_fields": [
                    dataclasses.asdict(f) for f in cls.connection_fields()
                ],
            }
        )
    return result


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

    # Elegoo Centauri uses SDCP over WebSocket; port defaults to 3030 (firmware-fixed)
    if printer_type == "elegoo_centauri":
        pcfg = _parse_printer_config(printer)
        if not pcfg:
            # Fall back to moonraker_config for installs that haven't migrated yet
            legacy = printer.moonraker_config
            pcfg = {"port": legacy.port if legacy else 3030, "api_key": legacy.api_key if legacy else None}
        return cls(
            ip_address=printer.ip_address,
            port=pcfg.get("port", 3030),
            api_key=pcfg.get("api_key"),
            on_state_change=on_state_change,
            on_print_start=on_print_start,
            on_print_complete=on_print_complete,
            on_layer_change=on_layer_change,
        )

    # All remaining Moonraker-based clients share the same constructor shape
    pcfg = _parse_printer_config(printer)
    if not pcfg:
        # Fall back to moonraker_config for installs that haven't migrated yet
        legacy = printer.moonraker_config
        if legacy is None:
            logger.warning("Printer %d (%s) has no config; using defaults", printer.id, printer_type)
        pcfg = {"port": legacy.port if legacy else 7125, "api_key": legacy.api_key if legacy else None}
    return cls(
        ip_address=printer.ip_address,
        port=pcfg.get("port", 7125),
        api_key=pcfg.get("api_key"),
        on_state_change=on_state_change,
        on_print_start=on_print_start,
        on_print_complete=on_print_complete,
        on_layer_change=on_layer_change,
    )
