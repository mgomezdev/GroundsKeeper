from datetime import datetime

from pydantic import BaseModel

from backend.app.schemas.slicer import PresetRef


class PrinterProfilePresetCreate(BaseModel):
    name: str
    printer_preset: PresetRef
    process_preset: PresetRef
    # slot index (str) -> PresetRef
    filament_presets: dict[str, PresetRef]


class PrinterProfilePresetUpdate(BaseModel):
    name: str | None = None
    printer_preset: PresetRef | None = None
    process_preset: PresetRef | None = None
    filament_presets: dict[str, PresetRef] | None = None


class PrinterProfilePresetResponse(BaseModel):
    id: int
    printer_id: int
    name: str
    printer_preset: PresetRef
    process_preset: PresetRef
    filament_presets: dict[str, PresetRef]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
