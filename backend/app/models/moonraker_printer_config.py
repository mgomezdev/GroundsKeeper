from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class MoonrakerPrinterConfig(Base):
    __tablename__ = "moonraker_printer_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), unique=True)
    port: Mapped[int] = mapped_column(default=7125)
    api_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    printer: Mapped["Printer"] = relationship(back_populates="moonraker_config")
