import json
from datetime import datetime

import pytest
from unittest.mock import AsyncMock, MagicMock


def test_model_has_expected_columns():
    from backend.app.models.printer_profile_preset import PrinterProfilePreset

    cols = {c.key for c in PrinterProfilePreset.__table__.columns}
    assert {"id", "printer_id", "name", "printer_preset", "process_preset",
            "filament_presets", "created_at", "updated_at"} <= cols


def test_preset_create_schema_roundtrip():
    from backend.app.schemas.printer_profile_preset import (
        PrinterProfilePresetCreate,
        PrinterProfilePresetResponse,
    )
    from backend.app.schemas.slicer import PresetRef

    data = PrinterProfilePresetCreate(
        name="Elegoo 0.2mm PLA",
        printer_preset=PresetRef(source="standard", id="Elegoo Centauri Carbon 0.4"),
        process_preset=PresetRef(source="standard", id="0.20mm Quality"),
        filament_presets={"0": PresetRef(source="standard", id="Elegoo PLA 1.75")},
    )
    assert data.name == "Elegoo 0.2mm PLA"
    assert data.filament_presets["0"].source == "standard"


@pytest.mark.asyncio
async def test_list_presets_returns_empty_for_unknown_printer():
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.app.api.routes.printer_profile_presets import list_presets

    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await list_presets(printer_id=999, db=mock_db, current_user=None)
    assert result == []


@pytest.mark.asyncio
async def test_create_preset_stores_serialised_refs():
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.app.api.routes.printer_profile_presets import create_preset
    from backend.app.schemas.printer_profile_preset import PrinterProfilePresetCreate
    from backend.app.schemas.slicer import PresetRef

    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.commit = AsyncMock()

    _now = datetime(2024, 1, 1)

    async def _refresh(obj):
        obj.id = 1
        obj.created_at = _now
        obj.updated_at = _now

    mock_db.refresh = _refresh

    body = PrinterProfilePresetCreate(
        name="Test",
        printer_preset=PresetRef(source="standard", id="Bambu X1C 0.4"),
        process_preset=PresetRef(source="standard", id="0.20mm Standard"),
        filament_presets={"0": PresetRef(source="standard", id="Bambu PLA Basic")},
    )

    captured = {}

    def capture_add(obj):
        captured["obj"] = obj

    mock_db.add = capture_add

    # Mock db.get(Printer, ...) to return a printer
    mock_printer = MagicMock()
    mock_printer.id = 1
    mock_db.get = AsyncMock(return_value=mock_printer)

    await create_preset(printer_id=1, body=body, db=mock_db, current_user=None)

    obj = captured["obj"]
    assert obj.name == "Test"
    stored_pp = json.loads(obj.printer_preset)
    assert stored_pp["source"] == "standard"
    stored_fp = json.loads(obj.filament_presets)
    assert stored_fp["0"]["id"] == "Bambu PLA Basic"
