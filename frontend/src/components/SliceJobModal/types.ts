import type { PerPrinterProfileConfig, PrintSliceConfigCreate } from '../../api/client';

export interface SliceJobModalProps {
  onClose: () => void;
  /** Pre-select a library file by ID (skips file step) */
  initialLibraryFileId?: number;
}

export interface PerPrinterDraft {
  printer_preset_id: string;
  process_preset_id: string;
  /** slot index → preset id */
  filament_preset_ids: Record<string, string>;
}

export function draftToConfig(draft: PerPrinterDraft): PerPrinterProfileConfig {
  return {
    printer_preset: { source: 'standard', id: draft.printer_preset_id },
    process_preset: { source: 'standard', id: draft.process_preset_id },
    filament_presets: Object.fromEntries(
      Object.entries(draft.filament_preset_ids).map(([slot, id]) => [
        slot,
        { source: 'standard' as const, id },
      ])
    ),
  };
}

export function buildSliceConfig(
  libraryFileId: number,
  plateIndex: number | null,
  eligiblePrinterIds: number[],
  drafts: Record<number, PerPrinterDraft>
): PrintSliceConfigCreate {
  return {
    library_file_id: libraryFileId,
    plate_index: plateIndex,
    eligible_printer_ids: eligiblePrinterIds,
    per_printer_profiles: Object.fromEntries(
      eligiblePrinterIds.map((id) => [String(id), draftToConfig(drafts[id])])
    ),
  };
}
