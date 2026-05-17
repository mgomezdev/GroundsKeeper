import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, PrinterIcon, Save, Trash2 } from 'lucide-react';
import { api, type SlicerBundle, type PrinterSlicerConfig, type Printer } from '../api/client';
import { Card, CardContent, CardHeader } from './Card';
import { Button } from './Button';
import { useToast } from '../contexts/ToastContext';

// Per-printer row: bundle + printer preset + per-slot filament dropdowns
function PrinterConfigRow({
  printer,
  config,
  bundles,
}: {
  printer: Printer;
  config: PrinterSlicerConfig | undefined;
  bundles: SlicerBundle[];
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [bundleId, setBundleId] = useState(config?.bundle_id ?? '');
  const [printerPreset, setPrinterPreset] = useState(config?.bundle_printer_name ?? '');
  const [filamentPresets, setFilamentPresets] = useState<string[]>(
    config?.bundle_filament_names ?? Array(printer.nozzle_count || 1).fill(''),
  );

  const selectedBundle = bundles.find((b) => b.id === bundleId);

  const saveMutation = useMutation({
    mutationFn: () =>
      api.savePrinterSlicerConfig(printer.id, {
        bundle_id: bundleId,
        bundle_printer_name: printerPreset,
        bundle_filament_names: filamentPresets,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printer-slicer-configs'] });
      showToast('Slicer profile saved', 'success');
    },
    onError: (err: Error) => showToast(`Save failed: ${err.message}`, 'error'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deletePrinterSlicerConfig(printer.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printer-slicer-configs'] });
      setBundleId('');
      setPrinterPreset('');
      setFilamentPresets(Array(printer.nozzle_count || 1).fill(''));
      showToast('Slicer profile cleared', 'success');
    },
    onError: (err: Error) => showToast(`Clear failed: ${err.message}`, 'error'),
  });

  const slotCount = printer.nozzle_count || 1;
  const isBusy = saveMutation.isPending || deleteMutation.isPending;

  const handleBundleChange = (id: string) => {
    setBundleId(id);
    setPrinterPreset('');
    setFilamentPresets(Array(slotCount).fill(''));
  };

  const handleFilamentChange = (idx: number, value: string) => {
    setFilamentPresets((prev) => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });
  };

  return (
    <div className="border border-bambu-dark-tertiary rounded-lg p-3 space-y-3">
      <div className="flex items-center gap-2">
        <PrinterIcon className="w-4 h-4 text-bambu-gray flex-shrink-0" />
        <span className="text-sm font-medium text-white">{printer.name}</span>
        <span className="text-xs text-bambu-gray bg-bambu-dark-tertiary px-1.5 py-0.5 rounded">
          {printer.printer_type}
        </span>
      </div>

      {/* Bundle picker */}
      <div className="space-y-1">
        <label className="text-xs text-bambu-gray">Bundle</label>
        <select
          value={bundleId}
          onChange={(e) => handleBundleChange(e.target.value)}
          disabled={isBusy}
          className="w-full bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded px-2 py-1.5 text-sm text-white disabled:opacity-50"
        >
          <option value="">— Not configured —</option>
          {bundles.map((b) => (
            <option key={b.id} value={b.id}>
              {b.printer_preset_name}
            </option>
          ))}
        </select>
      </div>

      {selectedBundle && (
        <>
          {/* Printer preset picker */}
          <div className="space-y-1">
            <label className="text-xs text-bambu-gray">Printer preset</label>
            <select
              value={printerPreset}
              onChange={(e) => setPrinterPreset(e.target.value)}
              disabled={isBusy}
              className="w-full bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded px-2 py-1.5 text-sm text-white disabled:opacity-50"
            >
              <option value="">— Select printer preset —</option>
              {selectedBundle.printer.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          {/* Per-slot filament pickers */}
          <div className="space-y-1">
            <label className="text-xs text-bambu-gray">
              {slotCount > 1 ? 'Default filament presets (per slot)' : 'Default filament preset'}
            </label>
            <div className="space-y-1.5">
              {Array.from({ length: slotCount }, (_, i) => (
                <div key={i} className="flex items-center gap-2">
                  {slotCount > 1 && (
                    <span className="text-xs text-bambu-gray w-12 flex-shrink-0">Slot {i + 1}</span>
                  )}
                  <select
                    value={filamentPresets[i] ?? ''}
                    onChange={(e) => handleFilamentChange(i, e.target.value)}
                    disabled={isBusy}
                    className="flex-1 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded px-2 py-1.5 text-sm text-white disabled:opacity-50"
                  >
                    <option value="">— Select filament preset —</option>
                    {selectedBundle.filament.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="flex items-center gap-2 pt-1">
        <Button
          variant="primary"
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={isBusy || !bundleId || !printerPreset}
        >
          {saveMutation.isPending ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Saving…
            </>
          ) : (
            <>
              <Save className="w-3.5 h-3.5" />
              Save
            </>
          )}
        </Button>
        {config && (
          <Button
            variant="danger"
            size="sm"
            onClick={() => deleteMutation.mutate()}
            disabled={isBusy}
          >
            {deleteMutation.isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Trash2 className="w-3.5 h-3.5" />
            )}
            Clear
          </Button>
        )}
      </div>
    </div>
  );
}

const NON_BAMBU_TYPES = ['elegoo_centauri', 'snapmaker_u1', 'moonraker'];

export function PrinterSlicerConfigSection() {
  const { data: printers, isLoading: loadingPrinters } = useQuery({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  });
  const { data: bundles, isLoading: loadingBundles } = useQuery({
    queryKey: ['slicer-bundles'],
    queryFn: api.listSlicerBundles,
  });
  const { data: configs, isLoading: loadingConfigs } = useQuery({
    queryKey: ['printer-slicer-configs'],
    queryFn: api.listPrinterSlicerConfigs,
  });

  const nonBambuPrinters = (printers ?? []).filter((p) => NON_BAMBU_TYPES.includes(p.printer_type));

  const isLoading = loadingPrinters || loadingBundles || loadingConfigs;

  if (nonBambuPrinters.length === 0 && !isLoading) return null;

  return (
    <Card>
      <CardHeader>
        <h3 className="text-base font-semibold text-white flex items-center gap-2">
          <PrinterIcon className="w-4 h-4 text-bambu-green" />
          Printer Slicer Profiles
        </h3>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-bambu-gray">
          Assign an OrcaSlicer bundle profile to each non-Bambu printer. The selected presets are used as defaults when
          slicing and printing from the archive library. You can override the process preset and filament slots at print
          time.
        </p>

        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-bambu-gray">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading…
          </div>
        ) : nonBambuPrinters.length === 0 ? (
          <p className="text-sm text-bambu-gray italic">No non-Bambu printers configured.</p>
        ) : (
          <div className="space-y-3">
            {nonBambuPrinters.map((printer) => (
              <PrinterConfigRow
                key={printer.id}
                printer={printer}
                config={(configs ?? []).find((c) => c.printer_id === printer.id)}
                bundles={bundles ?? []}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
