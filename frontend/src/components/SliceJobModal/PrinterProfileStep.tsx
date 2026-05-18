import { useQuery } from '@tanstack/react-query';
import { ChevronDown, Loader2, Printer } from 'lucide-react';
import { api, type Printer as PrinterType, type PrinterProfilePreset } from '../../api/client';
import type { PerPrinterDraft } from './types';

interface PrinterProfileStepProps {
  eligiblePrinterIds: number[];
  drafts: Record<number, PerPrinterDraft>;
  onTogglePrinter: (printerId: number) => void;
  onUpdateDraft: (printerId: number, patch: Partial<PerPrinterDraft>) => void;
}

interface PrinterCardProps {
  printer: PrinterType;
  enabled: boolean;
  draft: PerPrinterDraft;
  presets: PrinterProfilePreset[];
  onToggle: () => void;
  onUpdateDraft: (patch: Partial<PerPrinterDraft>) => void;
}

function PresetSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-gray-400">{label}</label>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full appearance-none bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white pr-8 focus:outline-none focus:border-blue-500"
        >
          {value === '' && <option value="">— select —</option>}
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
        <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
      </div>
    </div>
  );
}

function PrinterCard({ printer, enabled, draft, presets, onToggle, onUpdateDraft }: PrinterCardProps) {
  const { data: allPresets } = useQuery({
    queryKey: ['slicer-presets'],
    queryFn: api.getSlicerPresets,
  });

  const printerOptions = allPresets
    ? [
        ...allPresets.standard.printer.map((p) => p.id),
        ...allPresets.local.printer.map((p) => p.id),
        ...allPresets.cloud.printer.map((p) => p.id),
      ]
    : [];

  const processOptions = allPresets
    ? [
        ...allPresets.standard.process.map((p) => p.id),
        ...allPresets.local.process.map((p) => p.id),
        ...allPresets.cloud.process.map((p) => p.id),
      ]
    : [];

  const filamentOptions = allPresets
    ? [
        ...allPresets.standard.filament.map((p) => p.id),
        ...allPresets.local.filament.map((p) => p.id),
        ...allPresets.cloud.filament.map((p) => p.id),
      ]
    : [];

  const savedPresetOptions = presets.map((p) => p.name);

  function applyPreset(name: string) {
    const preset = presets.find((p) => p.name === name);
    if (!preset) return;
    onUpdateDraft({
      printer_preset_id: preset.printer_preset.id,
      process_preset_id: preset.process_preset.id,
      filament_preset_ids: Object.fromEntries(
        Object.entries(preset.filament_presets).map(([slot, ref]) => [slot, ref.id])
      ),
    });
  }

  return (
    <div
      className={`rounded-lg border transition-colors ${
        enabled ? 'border-blue-500 bg-gray-800/60' : 'border-gray-700 bg-gray-900/40'
      }`}
    >
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
      >
        <div
          className={`w-4 h-4 rounded border-2 flex-shrink-0 transition-colors ${
            enabled ? 'bg-blue-600 border-blue-600' : 'border-gray-600'
          }`}
        />
        <Printer className="w-4 h-4 text-gray-400 flex-shrink-0" />
        <span className="text-sm font-medium text-white">{printer.name}</span>
        {printer.location && (
          <span className="text-xs text-gray-500 ml-1">({printer.location})</span>
        )}
      </button>

      {enabled && (
        <div className="px-4 pb-4 flex flex-col gap-3">
          {savedPresetOptions.length > 0 && (
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400">Load saved preset</label>
              <div className="relative">
                <select
                  defaultValue=""
                  onChange={(e) => applyPreset(e.target.value)}
                  className="w-full appearance-none bg-gray-700 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-white pr-8 focus:outline-none focus:border-blue-500"
                >
                  <option value="">— choose a saved preset —</option>
                  {savedPresetOptions.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
            </div>
          )}

          <PresetSelect
            label="Printer preset"
            value={draft.printer_preset_id}
            options={printerOptions}
            onChange={(v) => onUpdateDraft({ printer_preset_id: v })}
          />
          <PresetSelect
            label="Process preset"
            value={draft.process_preset_id}
            options={processOptions}
            onChange={(v) => onUpdateDraft({ process_preset_id: v })}
          />
          <PresetSelect
            label="Filament (slot 0)"
            value={draft.filament_preset_ids['0'] ?? ''}
            options={filamentOptions}
            onChange={(v) =>
              onUpdateDraft({ filament_preset_ids: { ...draft.filament_preset_ids, '0': v } })
            }
          />
        </div>
      )}
    </div>
  );
}

export function PrinterProfileStep({
  eligiblePrinterIds,
  drafts,
  onTogglePrinter,
  onUpdateDraft,
}: PrinterProfileStepProps) {
  const { data: printers, isLoading } = useQuery({
    queryKey: ['printers'],
    queryFn: () => api.getPrinters(),
  });

  const printerPresetsQueries = useQuery({
    queryKey: ['profile-presets-all'],
    queryFn: async () => {
      if (!printers) return {};
      const entries = await Promise.all(
        printers.map(async (p) => {
          const presets = await api.getProfilePresets(p.id);
          return [p.id, presets] as const;
        })
      );
      return Object.fromEntries(entries);
    },
    enabled: !!printers,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    );
  }

  const allPrinters = printers ?? [];

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-gray-400">
        Select which printers are eligible to run this job. Each eligible printer needs a slicer
        profile configured.
      </p>
      {allPrinters.map((printer) => {
        const enabled = eligiblePrinterIds.includes(printer.id);
        const draft = drafts[printer.id] ?? {
          printer_preset_id: '',
          process_preset_id: '',
          filament_preset_ids: {},
        };
        const savedPresets = printerPresetsQueries.data?.[printer.id] ?? [];

        return (
          <PrinterCard
            key={printer.id}
            printer={printer}
            enabled={enabled}
            draft={draft}
            presets={savedPresets}
            onToggle={() => onTogglePrinter(printer.id)}
            onUpdateDraft={(patch) => onUpdateDraft(printer.id, patch)}
          />
        );
      })}
    </div>
  );
}
