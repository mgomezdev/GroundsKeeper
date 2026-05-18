from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class PrintSliceConfig(Base):
    """Per-job config for slice-on-dispatch queue items.

    eligible_printer_ids: JSON list[int], e.g. '[1, 3]'
    per_printer_profiles: JSON dict keyed by printer_id (str) ->
        {
          "printer_preset": {"source": "standard", "id": "Elegoo Centauri Carbon 0.4"},
          "process_preset":  {"source": "standard", "id": "0.20mm Quality"},
          "filament_presets": {"0": {"source": "standard", "id": "Elegoo PLA 1.75"}}
        }
    """

    __tablename__ = "print_slice_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_file_id: Mapped[int] = mapped_column(
        ForeignKey("library_files.id", ondelete="CASCADE")
    )
    # 1-indexed plate number; None means the file is single-plate or whole file
    plate_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # JSON list[int] of printer IDs eligible to handle this job
    eligible_printer_ids: Mapped[str] = mapped_column(Text)
    # JSON dict: printer_id (str) -> {printer_preset, process_preset, filament_presets}
    per_printer_profiles: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    library_file: Mapped["LibraryFile"] = relationship()


from backend.app.models.library import LibraryFile  # noqa: E402
