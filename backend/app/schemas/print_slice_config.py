from pydantic import BaseModel

from backend.app.schemas.slicer import PresetRef


class PerPrinterProfileConfig(BaseModel):
    printer_preset: PresetRef
    process_preset: PresetRef
    # slot index (str) -> PresetRef
    filament_presets: dict[str, PresetRef]


class PrintSliceConfigCreate(BaseModel):
    library_file_id: int
    plate_index: int | None = None
    eligible_printer_ids: list[int]
    # printer_id (str) -> PerPrinterProfileConfig
    per_printer_profiles: dict[str, PerPrinterProfileConfig | dict]
