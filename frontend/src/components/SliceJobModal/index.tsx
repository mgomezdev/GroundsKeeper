import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, Loader2, X } from 'lucide-react';
import { api, type LibraryFileListItem } from '../../api/client';
import { useToast } from '../../contexts/ToastContext';
import { FileStep } from './FileStep';
import { PrinterProfileStep } from './PrinterProfileStep';
import { buildSliceConfig } from './types';
import type { PerPrinterDraft, SliceJobModalProps } from './types';

type Step = 'file' | 'printers';

export function SliceJobModal({ onClose, initialLibraryFileId }: SliceJobModalProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [step, setStep] = useState<Step>(initialLibraryFileId ? 'printers' : 'file');
  const [selectedFile, setSelectedFile] = useState<LibraryFileListItem | null>(null);
  const selectedFileId = initialLibraryFileId ?? selectedFile?.id ?? null;

  const [eligiblePrinterIds, setEligiblePrinterIds] = useState<number[]>([]);
  const [drafts, setDrafts] = useState<Record<number, PerPrinterDraft>>({});

  function togglePrinter(printerId: number) {
    setEligiblePrinterIds((prev) =>
      prev.includes(printerId) ? prev.filter((id) => id !== printerId) : [...prev, printerId]
    );
  }

  function updateDraft(printerId: number, patch: Partial<PerPrinterDraft>) {
    setDrafts((prev) => ({
      ...prev,
      [printerId]: { ...(prev[printerId] ?? defaultDraft()), ...patch },
    }));
  }

  const addMutation = useMutation({
    mutationFn: () => {
      if (!selectedFileId) throw new Error('No file selected');
      const sliceConfig = buildSliceConfig(selectedFileId, null, eligiblePrinterIds, drafts);
      return api.addToQueue({ slice_config: sliceConfig });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['print-queue'] });
      showToast('Slice job added to queue', 'success');
      onClose();
    },
    onError: (err: Error) => {
      showToast(`Failed to queue job: ${err.message}`, 'error');
    },
  });

  const canAdvanceFile = selectedFileId !== null;
  const canSubmit =
    eligiblePrinterIds.length > 0 &&
    eligiblePrinterIds.every(
      (id) =>
        drafts[id]?.printer_preset_id &&
        drafts[id]?.process_preset_id
    );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="relative bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg mx-4 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700">
          <h2 className="text-base font-semibold text-white">Queue Slice Job</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-800">
          {(['file', 'printers'] as Step[]).map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              {i > 0 && <div className="w-8 h-px bg-gray-700" />}
              <div
                className={`flex items-center gap-1.5 text-xs font-medium ${
                  step === s ? 'text-blue-400' : 'text-gray-500'
                }`}
              >
                <span
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                    step === s ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400'
                  }`}
                >
                  {i + 1}
                </span>
                {s === 'file' ? 'Select file' : 'Configure printers'}
              </div>
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {step === 'file' ? (
            <FileStep
              selectedFileId={selectedFileId}
              onSelect={(f) => setSelectedFile(f)}
            />
          ) : (
            <PrinterProfileStep
              eligiblePrinterIds={eligiblePrinterIds}
              drafts={drafts}
              onTogglePrinter={togglePrinter}
              onUpdateDraft={updateDraft}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-4 border-t border-gray-700">
          {step === 'printers' && !initialLibraryFileId ? (
            <button
              onClick={() => setStep('file')}
              className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
          ) : (
            <div />
          )}

          {step === 'file' ? (
            <button
              onClick={() => setStep('printers')}
              disabled={!canAdvanceFile}
              className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              Next
              <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={() => addMutation.mutate()}
              disabled={!canSubmit || addMutation.isPending}
              className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              {addMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : null}
              Queue job
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function defaultDraft(): PerPrinterDraft {
  return { printer_preset_id: '', process_preset_id: '', filament_preset_ids: {} };
}
