from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class PrinterTypeSchema(Base):
    """Reference table: JSON Schema definition for each printer type's config.

    The ``config_schema`` column stores a JSON Schema (as text) that validates
    the ``printer_config`` JSON stored on the ``Printer`` row. This gives us a
    single authoritative definition of what config a printer type needs without
    baking those requirements into UI code.
    """

    __tablename__ = "printer_type_schemas"
    __table_args__ = (UniqueConstraint("printer_type", name="uq_printer_type_schema"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    printer_type: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    config_schema: Mapped[str] = mapped_column(Text, nullable=False)
