from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class Printer(Base):
    __tablename__ = "printers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    printer_type: Mapped[str] = mapped_column(String(20), default="bambu")
    ip_address: Mapped[str] = mapped_column(String(253))
    model: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_archive: Mapped[bool] = mapped_column(Boolean, default=True)
    print_hours_offset: Mapped[float] = mapped_column(Float, default=0.0)
    runtime_seconds: Mapped[int] = mapped_column(default=0)
    last_runtime_update: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Legacy Bambu columns — kept nullable for backward compat with existing column selectors
    # in support.py and spoolman_tracking.py.  Canonical data lives in BambuPrinterConfig.
    serial_number: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    access_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nozzle_count: Mapped[int] = mapped_column(default=1)
    # External camera configuration
    external_camera_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_camera_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    external_camera_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Optional single-frame snapshot URL — see #1177
    external_camera_snapshot_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    camera_rotation: Mapped[int] = mapped_column(default=0)
    # Plate detection — works for any printer with a camera
    plate_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    plate_detection_roi_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    plate_detection_roi_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    plate_detection_roi_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    plate_detection_roi_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Universal gate: True after a print finishes/fails until the user clears the plate (#961)
    awaiting_plate_clear: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    archives: Mapped[list["PrintArchive"]] = relationship(back_populates="printer", cascade="all, delete-orphan")
    smart_plugs: Mapped[list["SmartPlug"]] = relationship(back_populates="printer")
    notification_providers: Mapped[list["NotificationProvider"]] = relationship(back_populates="printer")
    maintenance_items: Mapped[list["PrinterMaintenance"]] = relationship(
        back_populates="printer", cascade="all, delete-orphan"
    )
    kprofile_notes: Mapped[list["KProfileNote"]] = relationship(back_populates="printer", cascade="all, delete-orphan")
    ams_history: Mapped[list["AMSSensorHistory"]] = relationship(back_populates="printer", cascade="all, delete-orphan")
    # Vendor-specific config (at most one of these is populated per printer)
    bambu_config: Mapped["BambuPrinterConfig | None"] = relationship(
        back_populates="printer", cascade="all, delete-orphan", uselist=False
    )
    moonraker_config: Mapped["MoonrakerPrinterConfig | None"] = relationship(
        back_populates="printer", cascade="all, delete-orphan", uselist=False
    )
    slicer_config: Mapped["PrinterSlicerConfig | None"] = relationship(
        back_populates="printer", cascade="all, delete-orphan", uselist=False
    )


from backend.app.models.ams_history import AMSSensorHistory  # noqa: E402
from backend.app.models.archive import PrintArchive  # noqa: E402
from backend.app.models.bambu_printer_config import BambuPrinterConfig  # noqa: E402
from backend.app.models.kprofile_note import KProfileNote  # noqa: E402
from backend.app.models.maintenance import PrinterMaintenance  # noqa: E402
from backend.app.models.moonraker_printer_config import MoonrakerPrinterConfig  # noqa: E402
from backend.app.models.notification import NotificationProvider  # noqa: E402
from backend.app.models.printer_slicer_config import PrinterSlicerConfig  # noqa: E402
from backend.app.models.smart_plug import SmartPlug  # noqa: E402
