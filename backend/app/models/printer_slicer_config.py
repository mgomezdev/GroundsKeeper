from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class PrinterSlicerConfig(Base):
    __tablename__ = "printer_slicer_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), unique=True)
    bundle_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bundle_printer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # JSON array of preset names, one per filament slot e.g. '["Elegoo PLA+ White"]'
    bundle_filament_names: Mapped[str | None] = mapped_column(Text, nullable=True)

    printer: Mapped["Printer"] = relationship(back_populates="slicer_config")
