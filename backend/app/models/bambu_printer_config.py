from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class BambuPrinterConfig(Base):
    __tablename__ = "bambu_printer_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), unique=True)
    serial_number: Mapped[str] = mapped_column(String(50), unique=True)
    access_code: Mapped[str] = mapped_column(String(20))
    nozzle_count: Mapped[int] = mapped_column(default=1)

    printer: Mapped["Printer"] = relationship(back_populates="bambu_config")
