import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.printer import Printer
from backend.app.models.printer_profile_preset import PrinterProfilePreset
from backend.app.models.user import User
from backend.app.schemas.printer_profile_preset import (
    PrinterProfilePresetCreate,
    PrinterProfilePresetResponse,
    PrinterProfilePresetUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["printer-profile-presets"])


def _preset_to_response(preset: PrinterProfilePreset) -> PrinterProfilePresetResponse:
    return PrinterProfilePresetResponse(
        id=preset.id,
        printer_id=preset.printer_id,
        name=preset.name,
        printer_preset=json.loads(preset.printer_preset),
        process_preset=json.loads(preset.process_preset),
        filament_presets=json.loads(preset.filament_presets),
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


@router.get("/printers/{printer_id}/profile-presets", response_model=list[PrinterProfilePresetResponse])
async def list_presets(
    printer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
):
    result = await db.execute(
        select(PrinterProfilePreset)
        .where(PrinterProfilePreset.printer_id == printer_id)
        .order_by(PrinterProfilePreset.name)
    )
    return [_preset_to_response(p) for p in result.scalars().all()]


@router.post("/printers/{printer_id}/profile-presets", response_model=PrinterProfilePresetResponse, status_code=201)
async def create_preset(
    printer_id: int,
    body: PrinterProfilePresetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
):
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(status_code=404, detail="Printer not found")

    preset = PrinterProfilePreset(
        printer_id=printer_id,
        name=body.name,
        printer_preset=body.printer_preset.model_dump_json(),
        process_preset=body.process_preset.model_dump_json(),
        filament_presets=json.dumps({k: v.model_dump() for k, v in body.filament_presets.items()}),
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return _preset_to_response(preset)


@router.patch("/printers/{printer_id}/profile-presets/{preset_id}", response_model=PrinterProfilePresetResponse)
async def update_preset(
    printer_id: int,
    preset_id: int,
    body: PrinterProfilePresetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
):
    preset = await db.get(PrinterProfilePreset, preset_id)
    if preset is None or preset.printer_id != printer_id:
        raise HTTPException(status_code=404, detail="Preset not found")

    if body.name is not None:
        preset.name = body.name
    if body.printer_preset is not None:
        preset.printer_preset = body.printer_preset.model_dump_json()
    if body.process_preset is not None:
        preset.process_preset = body.process_preset.model_dump_json()
    if body.filament_presets is not None:
        preset.filament_presets = json.dumps({k: v.model_dump() for k, v in body.filament_presets.items()})

    await db.commit()
    await db.refresh(preset)
    return _preset_to_response(preset)


@router.delete("/printers/{printer_id}/profile-presets/{preset_id}", status_code=204)
async def delete_preset(
    printer_id: int,
    preset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
):
    preset = await db.get(PrinterProfilePreset, preset_id)
    if preset is None or preset.printer_id != printer_id:
        raise HTTPException(status_code=404, detail="Preset not found")
    await db.delete(preset)
    await db.commit()
