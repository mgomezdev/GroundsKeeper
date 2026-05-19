/**
 * Shared types used by both PrinterCard and PrintersPage.
 * Extracted here to avoid circular imports.
 */

export interface SpoolmanSlotAssignmentRow {
  printer_id: number;
  ams_id: number;
  tray_id: number;
  spoolman_spool_id: number;
}

export interface PrinterMaintenanceInfo {
  due_count: number;
  warning_count: number;
  total_print_hours: number;
}

export type ViewMode = 'expanded' | 'compact';

// Map SSDP model codes to display names
export function mapModelCode(ssdpModel: string | null): string {
  if (!ssdpModel) return '';
  const modelMap: Record<string, string> = {
    // H2 Series
    'O1D': 'H2D',
    'O1E': 'H2D Pro',
    'O2D': 'H2D Pro',
    'O1C': 'H2C',
    'O1C2': 'H2C',
    'O1S': 'H2S',
    // X1 Series
    'BL-P001': 'X1C',
    'BL-P002': 'X1',
    'BL-P003': 'X1E',
    // X2 Series
    'N6': 'X2D',
    // P Series
    'C11': 'P1S',
    'C12': 'P1P',
    'C13': 'P2S',
    // A1 Series
    'N2S': 'A1',
    'N1': 'A1 Mini',
    // Direct matches
    'X1C': 'X1C',
    'X1': 'X1',
    'X1E': 'X1E',
    'X2D': 'X2D',
    'P1S': 'P1S',
    'P1P': 'P1P',
    'P2S': 'P2S',
    'A1': 'A1',
    'A1 Mini': 'A1 Mini',
    'H2D': 'H2D',
    'H2D Pro': 'H2D Pro',
    'H2C': 'H2C',
    'H2S': 'H2S',
  };
  return modelMap[ssdpModel] || ssdpModel;
}

// AMS drying presets from BambuStudio filament profiles (idle mode temps)
// Format: { n3f temp, n3s temp, n3f hours, n3s hours }
export const DRYING_PRESETS: Record<string, { n3f: number; n3s: number; n3f_hours: number; n3s_hours: number }> = {
  'PLA':   { n3f: 45, n3s: 45, n3f_hours: 12, n3s_hours: 12 },
  'PETG':  { n3f: 65, n3s: 65, n3f_hours: 12, n3s_hours: 12 },
  'TPU':   { n3f: 65, n3s: 75, n3f_hours: 12, n3s_hours: 18 },
  'ABS':   { n3f: 65, n3s: 80, n3f_hours: 12, n3s_hours: 8 },
  'ASA':   { n3f: 65, n3s: 80, n3f_hours: 12, n3s_hours: 8 },
  'PA':    { n3f: 65, n3s: 85, n3f_hours: 12, n3s_hours: 12 },
  'PC':    { n3f: 65, n3s: 80, n3f_hours: 12, n3s_hours: 8 },
  'PVA':   { n3f: 65, n3s: 85, n3f_hours: 12, n3s_hours: 18 },
};
