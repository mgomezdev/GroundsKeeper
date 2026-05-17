import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { AlertCircle, Loader2, Play } from 'lucide-react';
import { api } from '../api/client';
import { Button } from './Button';
import { useToast } from '../contexts/ToastContext';

interface Props {
  archiveId: number;
  archiveName: string;
  printerId: number;
  onClose: () => void;
}

export function ElegooPrintModal({ archiveId, archiveName, printerId, onClose }: Props) {
  const { showToast } = useToast();

  const [plateId, setPlateId] = useState(1);
  const [useEmbedded, setUseEmbedded] = useState(false);
  const [processName, setProcessName] = useState('');
  const [filamentOverrides, setFilamentOverrides] = useState<string[]>([]);

  const { data: config, isLoading: loadingConfig, error: configError } = useQuery({
    queryKey: ['printer-slicer-config', printerId],
    queryFn: () => api.getPrinterSlicerConfig(printerId),
  });

  const { data: bundle, isLoading: loadingBundle } = useQuery({
    queryKey: ['slicer-bundle', config?.bundle_id],
    queryFn: () => api.getSlicerBundle(config!.bundle_id),
    enabled: !!config?.bundle_id,
  });

  // Sync filament overrides when config loads
  const effectiveFilaments =
    filamentOverrides.length > 0
      ? filamentOverrides
      : config?.bundle_filament_names ?? [];

  const handleFilamentChange = (idx: number, value: string) => {
    setFilamentOverrides((prev) => {
      const next = prev.length > 0 ? [...prev] : [...(config?.bundle_filament_names ?? [])];
      while (next.length <= idx) next.push('');
      next[idx] = value;
      return next;
    });
  };

  const printMutation = useMutation({
    mutationFn: () =>
      api.elegooprint(printerId, {
        archive_id: archiveId,
        plate_id: plateId,
        process_name: useEmbedded ? '' : processName,
        filament_names: useEmbedded ? null : (filamentOverrides.length > 0 ? filamentOverrides : null),
        use_embedded_settings: useEmbedded,
      }),
    onSuccess: () => {
      showToast(`Slice & print dispatched for ${archiveName}`, 'success');
      onClose();
    },
    onError: (err: Error) => showToast(`Failed: ${err.message}`, 'error'),
  });

  const isLoading = loadingConfig || loadingBundle;
  const canPrint = useEmbedded || !!processName;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-bambu-dark-primary border border-bambu-dark-tertiary rounded-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-bambu-dark-tertiary">
          <div>
            <h2 className="text-base font-semibold text-white">Elegoo Slice & Print</h2>
            <p className="text-xs text-bambu-gray mt-0.5 truncate max-w-xs">{archiveName}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-bambu-gray hover:text-white p-1"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-4">
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-bambu-gray">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading profile…
            </div>
          ) : configError || !config ? (
            <div className="flex items-start gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-400">
                No slicer profile configured for this printer. Go to{' '}
                <strong>Settings → Slicer → Printer Slicer Profiles</strong> to set one up.
              </p>
            </div>
          ) : (
            <>
              {/* Plate picker */}
              <div className="space-y-1">
                <label className="text-xs text-bambu-gray">Plate</label>
                <input
                  type="number"
                  min={1}
                  value={plateId}
                  onChange={(e) => setPlateId(Math.max(1, parseInt(e.target.value) || 1))}
                  className="w-full bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded px-2 py-1.5 text-sm text-white"
                />
              </div>

              {/* Embedded settings toggle */}
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={useEmbedded}
                  onChange={(e) => setUseEmbedded(e.target.checked)}
                  className="mt-0.5 accent-bambu-green"
                />
                <span className="text-sm text-white">
                  Use file's embedded OrcaSlicer profiles
                  <span className="block text-xs text-bambu-gray mt-0.5">
                    Enable if this 3MF was already sliced in OrcaSlicer for this Elegoo printer
                  </span>
                </span>
              </label>

              {!useEmbedded && bundle && (
                <>
                  {/* Process preset */}
                  <div className="space-y-1">
                    <label className="text-xs text-bambu-gray">Process preset</label>
                    <select
                      value={processName}
                      onChange={(e) => setProcessName(e.target.value)}
                      className="w-full bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded px-2 py-1.5 text-sm text-white"
                    >
                      <option value="">— Select process profile —</option>
                      {bundle.process.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Filament slots */}
                  {effectiveFilaments.length > 0 && (
                    <div className="space-y-1">
                      <label className="text-xs text-bambu-gray">
                        {effectiveFilaments.length > 1 ? 'Filament slots' : 'Filament preset'}
                      </label>
                      <div className="space-y-1.5">
                        {effectiveFilaments.map((name, i) => (
                          <div key={i} className="flex items-center gap-2">
                            {effectiveFilaments.length > 1 && (
                              <span className="text-xs text-bambu-gray w-12 flex-shrink-0">Slot {i + 1}</span>
                            )}
                            <select
                              value={name}
                              onChange={(e) => handleFilamentChange(i, e.target.value)}
                              className="flex-1 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded px-2 py-1.5 text-sm text-white"
                            >
                              <option value="">— Select filament —</option>
                              {bundle.filament.map((fn) => (
                                <option key={fn} value={fn}>
                                  {fn}
                                </option>
                              ))}
                            </select>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-bambu-dark-tertiary">
          <Button variant="secondary" onClick={onClose} disabled={printMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => printMutation.mutate()}
            disabled={printMutation.isPending || isLoading || !config || !canPrint}
          >
            {printMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Dispatching…
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                Slice & Print
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
