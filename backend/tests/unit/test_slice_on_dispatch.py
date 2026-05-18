import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_print_slice_config_has_expected_columns():
    from backend.app.models.print_slice_config import PrintSliceConfig

    cols = {c.key for c in PrintSliceConfig.__table__.columns}
    assert {"id", "library_file_id", "plate_index",
            "eligible_printer_ids", "per_printer_profiles", "created_at"} <= cols


def test_print_queue_item_has_slice_columns():
    from backend.app.models.print_queue import PrintQueueItem

    cols = {c.key for c in PrintQueueItem.__table__.columns}
    assert "slice_config_id" in cols
    assert "slice_error" in cols


def test_slice_config_create_schema():
    from backend.app.schemas.print_slice_config import PrintSliceConfigCreate

    cfg = PrintSliceConfigCreate(
        library_file_id=1,
        plate_index=1,
        eligible_printer_ids=[1, 2],
        per_printer_profiles={
            "1": {
                "printer_preset": {"source": "standard", "id": "Elegoo Centauri Carbon 0.4"},
                "process_preset": {"source": "standard", "id": "0.20mm Quality"},
                "filament_presets": {"0": {"source": "standard", "id": "Elegoo PLA 1.75"}},
            }
        },
    )
    assert cfg.eligible_printer_ids == [1, 2]
    v = cfg.per_printer_profiles["1"]
    # May be a PerPrinterProfileConfig or a raw dict, depending on Pydantic coercion
    if isinstance(v, dict):
        assert v["printer_preset"]["source"] == "standard"
    else:
        assert v.printer_preset.source == "standard"


def test_queue_item_create_accepts_slice_config():
    from backend.app.schemas.print_queue import PrintQueueItemCreate
    from backend.app.schemas.print_slice_config import PrintSliceConfigCreate

    item = PrintQueueItemCreate(
        slice_config=PrintSliceConfigCreate(
            library_file_id=1,
            eligible_printer_ids=[1],
            per_printer_profiles={
                "1": {
                    "printer_preset": {"source": "standard", "id": "Bambu X1C 0.4"},
                    "process_preset": {"source": "standard", "id": "0.20mm Standard"},
                    "filament_presets": {"0": {"source": "standard", "id": "Bambu PLA Basic"}},
                }
            },
        )
    )
    assert item.slice_config is not None
    assert item.archive_id is None


@pytest.mark.asyncio
async def test_scheduler_skips_slice_item_when_no_eligible_printer_idle():
    from backend.app.services.print_scheduler import PrintScheduler

    scheduler = PrintScheduler.__new__(PrintScheduler)

    mock_item = MagicMock()
    mock_item.slice_config_id = 42
    mock_item.printer_id = None
    mock_item.status = "pending"

    mock_config = MagicMock()
    mock_config.eligible_printer_ids = json.dumps([1, 2])

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_config)

    scheduler._is_printer_idle = MagicMock(return_value=False)
    scheduler._printers = {1: MagicMock(), 2: MagicMock()}

    result = await scheduler._dispatch_slice_item(db=mock_db, item=mock_item)
    assert result is False
    assert mock_item.printer_id is None


@pytest.mark.asyncio
async def test_run_slice_and_print_marks_failed_on_slicer_error():
    from unittest.mock import patch, AsyncMock, MagicMock
    from pathlib import Path

    from backend.app.services.background_dispatch import BackgroundDispatchService
    from backend.app.services.slicer_api import SlicerApiError

    svc = BackgroundDispatchService.__new__(BackgroundDispatchService)

    mock_item = MagicMock()
    mock_item.id = 1
    mock_item.printer_id = 1
    mock_item.slice_config_id = 10
    mock_item.created_by_id = None

    mock_config = MagicMock()
    mock_config.library_file_id = 5
    mock_config.plate_index = None
    mock_config.per_printer_profiles = json.dumps({
        "1": {
            "printer_preset": {"source": "standard", "id": "Bambu X1C 0.4"},
            "process_preset": {"source": "standard", "id": "0.20mm Standard"},
            "filament_presets": {"0": {"source": "standard", "id": "Bambu PLA Basic"}},
        }
    })

    mock_lib_file = MagicMock()
    mock_lib_file.filename = "test.stl"
    mock_lib_file.file_path = "test.stl"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(side_effect=[mock_item, mock_config, mock_lib_file])
    mock_db.commit = AsyncMock()

    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.read_bytes.return_value = b"fake stl bytes"

    with patch("backend.app.services.background_dispatch.async_session", return_value=mock_session_ctx):
        with patch("backend.app.services.background_dispatch.Path") as mock_path_cls:
            mock_path_cls.return_value.__truediv__.return_value = mock_path
            with patch("backend.app.services.background_dispatch.SlicerApiService") as mock_slicer_cls:
                mock_slicer = AsyncMock()
                mock_slicer.slice_with_profiles = AsyncMock(side_effect=SlicerApiError("slicer exploded"))
                mock_slicer.__aenter__ = AsyncMock(return_value=mock_slicer)
                mock_slicer.__aexit__ = AsyncMock(return_value=False)
                mock_slicer_cls.return_value = mock_slicer

                with patch("backend.app.services.background_dispatch.resolve_preset_ref", AsyncMock(return_value="{}")):
                    with patch("backend.app.api.routes.settings.get_setting", AsyncMock(side_effect=["orcaslicer", "http://slicer:8080"])):
                        await svc._run_slice_and_print(item_id=1)

    assert mock_item.status == "failed"
    assert "slicer exploded" in mock_item.slice_error
