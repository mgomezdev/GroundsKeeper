from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class PrinterProfilePreset(Base):
    """Named slicer profile combo (printer + process + filaments) saved per printer.

    printer_preset / process_preset / filament_presets store serialised PresetRef
    JSON so the sidecar resolver path is unchanged at dispatch time.

    filament_presets shape: '{"0": {"source": "standard", "id": "Bambu PLA Basic"}}'
    — slot index (str) maps to a PresetRef dict.
    """

    __tablename__ = "printer_profile_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    # Serialised PresetRef JSON, e.g. '{"source": "standard", "id": "Bambu X1C 0.4"}'
    printer_preset: Mapped[str] = mapped_column(Text)
    process_preset: Mapped[str] = mapped_column(Text)
    # Slot-indexed map of PresetRef, e.g. '{"0": {"source": "standard", "id": "..."}}'
    filament_presets: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
