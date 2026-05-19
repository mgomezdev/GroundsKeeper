# Slice-on-Dispatch Print Queue

**Date:** 2026-05-17
**Branch:** feature/slice-on-dispatch (to be created from dev)

## Problem

Users must manually slice files in a desktop slicer before queueing a print. There is no way to queue a raw file (STL, un-sliced 3MF) and have the system pick the right printer from an eligible set and slice it automatically at dispatch time using the correct profiles for that printer.

## Goal

Allow a user to queue a raw library file for printing by specifying which printers are eligible and what slicer profiles to use per printer. When an eligible printer becomes idle, the system slices the file for that specific printer and dispatches the job — no manual slicer step required.

## Scope

- Single-filament and multi-filament prints (AMS, and tool changers in future)
- Plate selection for multi-plate 3MF files
- Saved per-printer profile presets for quick reuse
- Failure handling: mark failed, allow re-queue
- Entry point: "Add Job" button on the Queue page
- OrcaSlicer sidecar required (`preferred_slicer = orcaslicer`)

Out of scope: automatic re-slicing when profiles change after queuing, slicer sidecar health checks, support for non-library file uploads directly to the queue.

---

## Data Model

### New: `PrinterProfilePreset`

Named, reusable slicer profile combo saved per printer.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `printer_id` | int FK → Printer | |
| `name` | str | e.g. "Elegoo 0.2mm PLA" |
| `printer_profile` | str | Slicer printer profile name |
| `process_profile` | str | Slicer process/quality profile name |
| `filament_profiles` | JSON | `{slot_index: profile_name}` — slot-indexed map |
| `created_at` | datetime | |
| `updated_at` | datetime | |

`filament_profiles` example for a 2-color print:
```json
{"0": "Elegoo PLA 1.75", "1": "Elegoo PETG 1.75"}
```
Single-filament: `{"0": "Elegoo PLA 1.75"}`. Tool changers use the same shape — slot index maps to tool.

### New: `PrintSliceConfig`

Per-job config binding a raw file to printer eligibility and per-printer profiles.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `library_file_id` | int FK → LibraryFile | Raw source file |
| `plate_index` | int \| None | 1-indexed plate; None = whole file / single-plate |
| `eligible_printer_ids` | JSON | `list[int]` — first idle printer from this list wins |
| `per_printer_profiles` | JSON | `{printer_id: {printer_profile, process_profile, filament_profiles}}` |
| `created_at` | datetime | |

`per_printer_profiles` example:
```json
{
  "1": {
    "printer_profile": "Elegoo Centauri Carbon 0.4",
    "process_profile": "0.20mm Quality",
    "filament_profiles": {"0": "Elegoo PLA 1.75", "1": "Elegoo PETG 1.75"}
  },
  "3": {
    "printer_profile": "Bambu X1C 0.4",
    "process_profile": "0.20mm Standard",
    "filament_profiles": {"0": "Bambu PLA Basic", "1": "Bambu PETG Basic"}
  }
}
```

### Extended: `PrintQueueItem`

Two new nullable columns:

| Column | Type | Notes |
|---|---|---|
| `slice_config_id` | int FK \| None | Set → item needs slicing; cleared on success |
| `slice_error` | text \| None | Populated when `status = failed` due to slice error |

Items with `slice_config_id` set have `archive_id = None` until slicing succeeds. `printer_id` is also null until dispatch time assigns one from the eligible set.

---

## Backend

### New API Endpoints

```
GET    /printers/{id}/profile-presets
POST   /printers/{id}/profile-presets
PATCH  /printers/{id}/profile-presets/{preset_id}
DELETE /printers/{id}/profile-presets/{preset_id}
```

Standard CRUD. Response shape mirrors `PrinterProfilePreset` columns.

### Extended: `POST /queue/`

Accepts a new optional `slice_config` field in the request body, mutually exclusive with `archive_id` / `library_file_id`:

```json
{
  "slice_config": {
    "library_file_id": 42,
    "plate_index": 1,
    "eligible_printer_ids": [1, 3],
    "per_printer_profiles": { ... }
  }
}
```

When present:
1. Validate `library_file_id` exists and is a sliceable format
2. Create `PrintSliceConfig` row
3. Create `PrintQueueItem` with `slice_config_id` set, `archive_id = None`, `printer_id = None`
4. Return queue item as normal

Existing callers passing `archive_id` / `library_file_id` are unaffected.

### Dispatch Changes (`print_scheduler.py`)

In `check_queue()`, items with `slice_config_id` set get a new branch before the existing idle-printer check:

1. Load `PrintSliceConfig` — get `eligible_printer_ids` and `per_printer_profiles`
2. Walk `eligible_printer_ids` in order; call `_is_printer_idle()` for each
3. **None idle** → record `waiting_reason = "No eligible printer available"`, skip item (same pattern as model-based assignment)
4. **One found** → assign `item.printer_id = chosen_printer.id`, enqueue `BackgroundDispatchService._run_slice_and_print(item)`

In `BackgroundDispatchService`, new task `_run_slice_and_print()`:

1. Fetch `PrintSliceConfig`; look up library file path
2. Call `SlicerApiService.slice(file, printer_profile, process_profile, filament_profiles)` on the preferred OrcaSlicer sidecar
3. **Success** → create `PrintArchive` from result bytes; set `item.archive_id`, clear `item.slice_config_id`; proceed with normal `_dispatch_archive()` path (FTP upload → MQTT start)
4. **Failure** → set `item.status = "failed"`, `item.slice_error = error_message`; release printer dispatch hold

The slice call is inside `BackgroundDispatchService` (async background job), not in the 30-second polling loop, so a slow slicer does not block other items from being evaluated.

### Error Handling

| Failure | Outcome |
|---|---|
| Slicer returns error | `status = failed`, `slice_error = message`, printer hold released |
| Slicer sidecar unreachable | Same as above |
| Library file deleted before dispatch | Same as above — file-not-found caught in background task |
| No eligible printer becomes idle | Item stays pending indefinitely; user can cancel or edit |

Failed items can be re-queued via the existing Re-queue modal flow (step 2 pre-filled from stored `PrintSliceConfig`).

---

## Frontend

### Entry Point

"Add Job" button (+ icon) in the Queue page header. Always visible, not gated on selection state.

### Add Print Job Modal (2-step)

**Step 1 — File:**
- Scrollable, searchable list of library files (sliceable formats only)
- Selecting a multi-plate 3MF shows an inline plate picker (reuses existing `PlateSelector`)
- "Next →" advances to step 2

**Step 2 — Printers & Profiles:**
- Multi-select list of printers; selected printers become cards
- Each card shows:
  - Printer name
  - **Printer profile** dropdown (from `GET /slicer/presets` standard tier)
  - **Process profile** dropdown
  - **Filament slots** — one row per slot required by the file/plate, each with a filament profile dropdown
  - **Load preset** button — popover listing `PrinterProfilePreset` rows for this printer; selecting fills all fields
  - **Save as preset** button — names and saves current card config as a new `PrinterProfilePreset`
- "Add to Queue" submits `POST /queue/` with `slice_config` body

### Queue Page — Slice-Pending Items

Slice-pending items display differently from archive-backed items:

| Element | Slice-pending | Normal |
|---|---|---|
| Name | Raw file name | Archive name |
| Thumbnail | File thumbnail if available | Archive thumbnail |
| Status badge | "Awaiting slicer" (yellow) | "Pending" |
| Printer | Eligible printer chips | Single assigned printer |

On slice failure:
- Badge: "Slice failed" (red)
- Collapsed error message under "Show error" toggle
- "Re-queue" button reopens the modal at step 2, pre-filled from stored `PrintSliceConfig`

### Printer Profile Preset Management

- Lives in the printer detail / settings panel — no separate management page
- Simple list: preset name + profile summary, edit and delete inline
- Create/edit also available from inside the Add Job modal ("Save as preset")

---

## Key Constraints

- OrcaSlicer sidecar must be running and `preferred_slicer = orcaslicer` — jobs requiring slicing that are dispatched when the sidecar is down will fail with a clear error
- Plate metadata (slot count, filament types) is read from the library file at step 2 of the modal using the existing plate inspection API
- `per_printer_profiles` is stored as-is at queue time — profile name changes in the slicer after queuing are not retroactively applied
- `PrintSliceConfig` rows are retained after dispatch (for re-queue reference) and deleted when the associated `PrintQueueItem` is deleted
