import { useState } from 'react';
import { Settings, ChevronDown, ChevronUp } from 'lucide-react';
import type { PrinterCapabilities } from '../../api/client';
import type { PrintOptionsProps, PrintOptions as PrintOptionsType } from './types';

const PRINT_OPTIONS_CONFIG: Array<{
  key: keyof PrintOptionsType;
  label: string;
  desc: string;
  capabilityKey: keyof PrinterCapabilities;
}> = [
  { key: 'bed_levelling', label: 'Bed Levelling', desc: 'Auto-level bed before print', capabilityKey: 'bed_levelling' },
  { key: 'flow_cali', label: 'Flow Calibration', desc: 'Calibrate extrusion flow', capabilityKey: 'flow_calibration' },
  { key: 'vibration_cali', label: 'Vibration Calibration', desc: 'Reduce ringing artifacts', capabilityKey: 'vibration_cali' },
  { key: 'layer_inspect', label: 'First Layer Inspection', desc: 'AI inspection of first layer', capabilityKey: 'layer_inspect' },
  { key: 'timelapse', label: 'Timelapse', desc: 'Record timelapse video', capabilityKey: 'timelapse' },
];

export function PrintOptionsPanel({
  options,
  onChange,
  defaultExpanded = false,
  capabilities,
}: PrintOptionsProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const handleToggle = (key: keyof PrintOptionsType, supported: boolean) => {
    if (!supported) return;
    onChange({ ...options, [key]: !options[key] });
  };

  return (
    <div className="mb-4">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 text-sm text-bambu-gray hover:text-white transition-colors w-full"
      >
        <Settings className="w-4 h-4" />
        <span>Print Options</span>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 ml-auto" />
        ) : (
          <ChevronDown className="w-4 h-4 ml-auto" />
        )}
      </button>
      {isExpanded && (
        <div className="mt-2 bg-bambu-dark rounded-lg p-3 space-y-2">
          {PRINT_OPTIONS_CONFIG.map(({ key, label, desc, capabilityKey }) => {
            const supported = !capabilities || capabilities[capabilityKey] !== false;
            return (
              <label
                key={key}
                className={`flex items-center justify-between group ${supported ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'}`}
                title={!supported ? 'Not supported by this printer' : undefined}
              >
                <div>
                  <span className="text-sm text-white">{label}</span>
                  <p className="text-xs text-bambu-gray">
                    {supported ? desc : 'Not supported by this printer'}
                  </p>
                </div>
                <div
                  className={`relative w-10 h-5 rounded-full transition-colors ${
                    supported && options[key] ? 'bg-bambu-green' : 'bg-bambu-dark-tertiary'
                  }`}
                  onClick={() => handleToggle(key, supported)}
                >
                  <div
                    className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      supported && options[key] ? 'translate-x-5' : 'translate-x-0.5'
                    }`}
                  />
                </div>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}
