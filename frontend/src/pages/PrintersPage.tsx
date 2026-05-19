import { useState, useEffect, useLayoutEffect, useMemo, useRef, useCallback } from 'react';
import { compareFwVersions } from '../utils/firmwareVersion';
import { formatPrintName } from '../utils/printName';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../contexts/ThemeContext';
import { useAuth } from '../contexts/AuthContext';
import {
  Plus,
  Link,
  Unlink,
  Signal,
  Clock,
  MoreVertical,
  Trash2,
  RefreshCw,
  RotateCw,
  Box,
  HardDrive,
  AlertTriangle,
  AlertCircle,
  Terminal,
  Power,
  PowerOff,
  Zap,
  Wrench,
  ChevronDown,
  Filter,
  Pencil,
  ArrowUp,
  ArrowDown,
  Layers,
  Video,
  Search,
  Loader2,
  Square,
  Pause,
  Play,
  X,
  Fan,
  Wind,
  AirVent,
  Download,
  ScanSearch,
  CheckCircle,
  CheckSquare,
  XCircle,
  User,
  Home,
  Printer as PrinterIcon,
  Info,
  Cable,
  Flame,
  Snowflake,
  Gauge,
  DoorOpen,
  DoorClosed,
  MoveVertical,
  LogIn,
  LogOut,
  MoreHorizontal,
  SlidersHorizontal,
} from 'lucide-react';

import { useNavigate } from 'react-router-dom';
import { api, discoveryApi, firmwareApi, withStreamToken } from '../api/client';
import { formatDateOnly, formatETA, formatDuration, parseUTCDate } from '../utils/date';
import type { Printer, PrinterCreate, PrinterStatus, AMSUnit, DiscoveredPrinter, FirmwareUpdateInfo, FirmwareUploadStatus, LinkedSpoolInfo, SpoolAssignment, HMSError, InventorySpool, SmartPlug } from '../api/client';
import { Card, CardContent } from '../components/Card';
import { Button } from '../components/Button';
import { ConfirmModal } from '../components/ConfirmModal';
import { BulkPrinterToolbar, type PrinterState } from '../components/BulkPrinterToolbar';
import { FileManagerModal } from '../components/FileManagerModal';
import { EmbeddedCameraViewer } from '../components/EmbeddedCameraViewer';
import { MQTTDebugModal } from '../components/MQTTDebugModal';
import { HMSErrorModal, filterKnownHMSErrors } from '../components/HMSErrorModal';
import { PrinterQueueWidget } from '../components/PrinterQueueWidget';
import { AMSHistoryModal } from '../components/AMSHistoryModal';
import { FilamentHoverCard, EmptySlotHoverCard } from '../components/FilamentHoverCard';
import { LinkSpoolModal } from '../components/LinkSpoolModal';
import { AssignSpoolModal } from '../components/AssignSpoolModal';
import { ConfigureAmsSlotModal } from '../components/ConfigureAmsSlotModal';
import { useToast } from '../contexts/ToastContext';
import { ChamberLight } from '../components/icons/ChamberLight';
import { PlateClearedIcon } from '../components/icons/PlateClearedIcon';
import { SkipObjectsModal, SkipObjectsIcon } from '../components/SkipObjectsModal';
import { FileUploadModal } from '../components/FileUploadModal';
import { PrintModal } from '../components/PrintModal';
import { PrinterInfoModal } from '../components/PrinterInfoModal';
import { getGlobalTrayId, getFillBarColor, getSpoolmanFillLevel, getFallbackSpoolTag, isBambuLabSpool } from '../utils/amsHelpers';
import { getPrinterImage, getWifiStrength, filterCompatibleQueueItems } from '../utils/printer';
import { FilamentSlotCircle } from '../components/FilamentSlotCircle';
import { Collapsible } from '../components/Collapsible';
import { getColorName, parseFilamentColor, isLightColor } from '../utils/colors';
import { PrinterCard } from '../components/PrinterCard';
import { AmsNameHoverCard } from '../components/AmsNameHoverCard';
export { AmsNameHoverCard };
export type { SpoolmanSlotAssignmentRow, PrinterMaintenanceInfo, ViewMode } from '../components/PrinterCard/types';
export { DRYING_PRESETS } from '../components/PrinterCard/types';
import type { SpoolmanSlotAssignmentRow, PrinterMaintenanceInfo } from '../components/PrinterCard/types';
import { DRYING_PRESETS } from '../components/PrinterCard/types';

// Color names resolve via getColorName() which reads the backend color_catalog
// (loaded once by ColorCatalogProvider). No hardcoded tables here — see #857.

// Status summary bar component - uses queryClient to read cached statuses
function StatusSummaryBar({ printers }: { printers: Printer[] | undefined }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  // Subscribe to query cache changes to re-render when status updates
  // Throttled to prevent rapid re-renders from causing tab crashes
  const [cacheTick, setCacheTick] = useState(0);
  useEffect(() => {
    let pending = false;
    const unsubscribe = queryClient.getQueryCache().subscribe(() => {
      if (!pending) {
        pending = true;
        requestAnimationFrame(() => {
          setCacheTick(t => t + 1);
          pending = false;
        });
      }
    });
    return () => unsubscribe();
  }, [queryClient]);

  const { counts, nextFinish } = useMemo(() => {
    let printing = 0;
    let paused = 0;
    let finished = 0;
    let idle = 0;
    let offline = 0;
    let loading = 0;
    let error = 0;
    let nextPrinterName: string | null = null;
    let nextRemainingMin: number | null = null;
    let nextProgress: number = 0;

    printers?.forEach((printer) => {
      const status = queryClient.getQueryData<{ connected: boolean; state: string | null; remaining_time: number | null; progress: number | null; hms_errors?: HMSError[] }>(['printerStatus', printer.id]);
      if (status === undefined) {
        // Status not yet loaded - don't count as offline yet
        loading++;
      } else if (!status.connected) {
        offline++;
      } else {
        // Count printers with active HMS errors as problems
        const knownHmsCount =
          status.hms_errors ? filterKnownHMSErrors(status.hms_errors).length : 0;
        if (knownHmsCount > 0) {
          error++;
        }
        switch (status.state) {
          case 'RUNNING':
            printing++;
            if (status.remaining_time != null && status.remaining_time > 0) {
              if (nextRemainingMin === null || status.remaining_time < nextRemainingMin) {
                nextRemainingMin = status.remaining_time;
                nextPrinterName = printer.name;
                nextProgress = status.progress || 0;
              }
            }
            break;
          case 'PAUSE':
            paused++;
            break;
          case 'FINISH':
            finished++;
            break;
          case 'FAILED':
            // FAILED is the printer's terminal gcode_state after a print stops —
            // including user cancellations, where there's no actual fault. Only
            // count it as a "problem" when an HMS error is also active; otherwise
            // it's just a print that ended unsuccessfully and the plate needs
            // clearing (same as FINISH from the operator's perspective).
            if (knownHmsCount > 0) {
              // Already counted above
            } else {
              finished++;
            }
            break;
          default:
            idle++;
            break;
        }
      }
    });

    return {
      counts: { printing, paused, finished, idle, offline, loading, error, total: (printers?.length || 0) },
      nextFinish: nextPrinterName && nextRemainingMin ? { name: nextPrinterName, remainingMin: nextRemainingMin, progress: nextProgress } : null,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [printers, queryClient, cacheTick]);

  if (!printers?.length) return null;

  const badges: { count: number; dot: string; label: string }[] = [
    { count: counts.printing, dot: 'bg-bambu-green animate-pulse', label: t('printers.status.printing').toLowerCase() },
    { count: counts.paused, dot: 'bg-status-warning', label: t('printers.status.paused', 'paused').toLowerCase() },
    { count: counts.finished, dot: 'bg-blue-400', label: t('printers.status.finished', 'finished').toLowerCase() },
    { count: counts.idle, dot: counts.idle > 0 ? 'bg-bambu-green' : 'bg-gray-500', label: t('printers.status.available').toLowerCase() },
    { count: counts.error, dot: 'bg-status-error', label: t('printers.status.problem').toLowerCase() },
    { count: counts.offline, dot: 'bg-gray-400', label: t('printers.status.offline').toLowerCase() },
  ];

  return (
    <div className="mt-1 flex flex-wrap items-center gap-4 gap-y-2 text-bambu-gray">
      {badges.map(({ count, dot, label }) => count > 0 && (
        <div key={label} className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full ${dot}`} />
          <span className="text-bambu-gray">
            <span className="text-white font-medium">{count}</span> {label}
          </span>
        </div>
      ))}
      {nextFinish && (
        <>
          <div className="w-px h-4 bg-bambu-dark-tertiary" />
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
            <div className="flex items-center gap-2">
              <span className="text-bambu-green font-medium">{t('printers.nextAvailable')}:</span>
              <span className="text-white font-medium">{nextFinish.name}</span>
            </div>
            <div className="flex items-center gap-2 w-full sm:w-auto">
              <div className="w-full sm:w-16 bg-bambu-dark-tertiary rounded-full h-1.5">
                <div
                  className="bg-bambu-green h-1.5 rounded-full transition-all"
                  style={{ width: `${nextFinish.progress}%` }}
                />
              </div>
              <span className="text-white font-medium">{Math.round(nextFinish.progress)}%</span>
              <span className="text-bambu-gray">({formatDuration(nextFinish.remainingMin * 60)})</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

type SortOption = 'name' | 'status' | 'model' | 'location';
// ViewMode is re-exported from '../components/PrinterCard/types'

type ToolbarDropdownOption<T extends string> = {
  value: T;
  label: string;
};

function ToolbarDropdown<T extends string>({
  value,
  options,
  onChange,
  fullWidth = false,
}: {
  value: T;
  options: ToolbarDropdownOption<T>[];
  onChange: (value: T) => void;
  fullWidth?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedOption = options.find(option => option.value === value) ?? options[0];

  return (
    <div className={`relative ${fullWidth ? 'w-full min-w-0' : ''}`}>
      <button
        type="button"
        onClick={() => setIsOpen(open => !open)}
        className={`h-8 px-2 rounded-lg border bg-bambu-dark border-bambu-dark-tertiary text-white text-sm font-medium transition-colors hover:bg-bambu-dark-tertiary focus:outline-none focus:border-bambu-green flex items-center justify-between gap-2 ${fullWidth ? 'w-full' : 'min-w-28'}`}
      >
        <span className="truncate">{selectedOption?.label}</span>
        <ChevronDown className={`w-4 h-4 text-bambu-gray transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute left-0 top-full z-20 mt-1 min-w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary py-1 shadow-xl">
            {options.map(option => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  onChange(option.value);
                  setIsOpen(false);
                }}
                className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-bambu-dark-tertiary ${
                  option.value === value ? 'text-bambu-green' : 'text-white'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ToolbarMenu({
  label,
  icon,
  children,
}: {
  label: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(open => !open)}
        className="h-8 w-8 rounded-lg border bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary transition-colors flex items-center justify-center"
        aria-label={label}
        title={label}
      >
        {icon}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 top-full z-20 mt-1 min-w-40 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary p-2 shadow-xl">
            {children}
          </div>
        </>
      )}
    </div>
  );
}

const STATUS_GROUP_ORDER: string[] = ['error', 'printing', 'paused', 'finished', 'idle', 'offline'];

const STATUS_GROUP_META: Record<string, { labelKey: string; dot: string }> = {
  error:    { labelKey: 'printers.status.problem',   dot: 'bg-status-error' },
  printing: { labelKey: 'printers.status.printing',  dot: 'bg-bambu-green animate-pulse' },
  paused:   { labelKey: 'printers.status.paused',    dot: 'bg-status-warning' },
  finished: { labelKey: 'printers.status.finished',  dot: 'bg-blue-400' },
  idle:     { labelKey: 'printers.status.idle',       dot: 'bg-bambu-green' },
  offline:  { labelKey: 'printers.status.offline',   dot: 'bg-gray-400' },
};

/** Classify a printer into one of the UI status buckets. */
function classifyPrinterStatus(
  status: { connected: boolean; state: string | null; hms_errors?: HMSError[] } | undefined,
): PrinterState {
  if (!status?.connected) return 'offline';
  const hmsErrors = status.hms_errors ? filterKnownHMSErrors(status.hms_errors) : [];
  if (hmsErrors.length > 0) return 'error';
  switch (status.state) {
    case 'RUNNING': return 'printing';
    case 'PAUSE':   return 'paused';
    case 'FINISH':  return 'finished';
    // FAILED without an active HMS error is the printer's terminal state after
    // any unsuccessful end — including user-cancellations. Treat the same as
    // FINISH for grouping/badging purposes; only escalate to "error" when an
    // HMS code is actually attached (handled by the early-return above).
    case 'FAILED':  return 'finished';
    default:        return 'idle';
  }
}


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


function AddPrinterModal({
  onClose,
  onAdd,
  existingSerials,
}: {
  onClose: () => void;
  onAdd: (data: PrinterCreate) => void;
  existingSerials: string[];
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<PrinterCreate>({
    name: '',
    serial_number: '',
    ip_address: '',
    access_code: '',
    model: '',
    location: '',
    auto_archive: true,
  });

  // Discovery state
  const [discovering, setDiscovering] = useState(false);
  const [discovered, setDiscovered] = useState<DiscoveredPrinter[]>([]);
  const [discoveryError, setDiscoveryError] = useState('');
  const [hasScanned, setHasScanned] = useState(false);
  const [isDocker, setIsDocker] = useState(false);
  const [detectedSubnets, setDetectedSubnets] = useState<string[]>([]);
  const [subnet, setSubnet] = useState('');
  const [scanProgress, setScanProgress] = useState({ scanned: 0, total: 0 });

  // Fetch discovery info on mount
  useEffect(() => {
    discoveryApi.getInfo().then(info => {
      setIsDocker(info.is_docker);
      if (info.subnets.length > 0) {
        setDetectedSubnets(info.subnets);
        setSubnet(info.subnets[0]);
      }
    }).catch(() => {
      // Ignore errors, assume not Docker
    });
  }, []);

  // Filter out already-added printers
  const newPrinters = discovered.filter(p => !existingSerials.includes(p.serial));

  const startDiscovery = async () => {
    setDiscoveryError('');
    setDiscovered([]);
    setDiscovering(true);
    setHasScanned(false);
    setScanProgress({ scanned: 0, total: 0 });

    try {
      if (isDocker) {
        // Use subnet scanning for Docker
        await discoveryApi.startSubnetScan(subnet);

        // Poll for scan status and results
        const pollInterval = setInterval(async () => {
          try {
            const status = await discoveryApi.getScanStatus();
            setScanProgress({ scanned: status.scanned, total: status.total });

            const printers = await discoveryApi.getDiscoveredPrinters();
            setDiscovered(printers);

            if (!status.running) {
              clearInterval(pollInterval);
              setDiscovering(false);
              setHasScanned(true);
            }
          } catch (e) {
            console.error('Failed to get scan status:', e);
          }
        }, 500);
      } else {
        // Use SSDP discovery for native installs
        await discoveryApi.startDiscovery(10);

        // Poll for discovered printers every second
        const pollInterval = setInterval(async () => {
          try {
            const printers = await discoveryApi.getDiscoveredPrinters();
            setDiscovered(printers);
          } catch (e) {
            console.error('Failed to get discovered printers:', e);
          }
        }, 1000);

        // Stop after 10 seconds
        setTimeout(async () => {
          clearInterval(pollInterval);
          try {
            await discoveryApi.stopDiscovery();
          } catch {
            // Ignore stop errors
          }
          setDiscovering(false);
          setHasScanned(true);
          // Final fetch
          try {
            const printers = await discoveryApi.getDiscoveredPrinters();
            setDiscovered(printers);
          } catch (e) {
            console.error('Failed to get final discovered printers:', e);
          }
        }, 10000);
      }
    } catch (e) {
      console.error('Failed to start discovery:', e);
      setDiscoveryError(e instanceof Error ? e.message : t('printers.discovery.failedToStart'));
      setDiscovering(false);
      setHasScanned(true);
    }
  };

  // Reuse module-level mapModelCode

  const selectPrinter = (printer: DiscoveredPrinter) => {
    // Don't pre-fill serial if it's a placeholder (unknown-*) - user needs to enter actual serial
    const serialNumber = printer.serial.startsWith('unknown-') ? '' : printer.serial;
    setForm({
      ...form,
      name: printer.name || '',
      serial_number: serialNumber,
      ip_address: printer.ip_address,
      model: mapModelCode(printer.model),
    });
    // Clear discovery results after selection
    setDiscovered([]);
  };

  // Cleanup discovery on unmount
  useEffect(() => {
    return () => {
      discoveryApi.stopDiscovery().catch(() => {});
      discoveryApi.stopSubnetScan().catch(() => {});
    };
  }, []);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-start sm:items-center justify-center z-50 p-4 overflow-y-auto"
      onClick={onClose}
    >
      <Card className="w-full max-w-md my-auto max-h-[calc(100vh-2rem)] overflow-y-auto" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
        <CardContent>
          <h2 className="text-xl font-semibold mb-4">{t('printers.addPrinter')}</h2>

          {/* Discovery Section */}
          <div className="mb-4 pb-4 border-b border-bambu-dark-tertiary">
            {isDocker && (
              <div className="mb-3">
                <label className="block text-sm text-bambu-gray mb-1">
                  {t('printers.discovery.subnetToScan')}
                </label>
                {detectedSubnets.length > 0 ? (
                  <select
                    className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none text-sm"
                    value={subnet}
                    onChange={(e) => setSubnet(e.target.value)}
                    disabled={discovering}
                  >
                    {detectedSubnets.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none text-sm"
                    value={subnet}
                    onChange={(e) => setSubnet(e.target.value)}
                    placeholder="192.168.1.0/24"
                    disabled={discovering}
                  />
                )}
                <p className="mt-1 text-xs text-bambu-gray">
                  {t('printers.discovery.dockerNote')}
                </p>
              </div>
            )}

            <Button
              type="button"
              variant="secondary"
              onClick={startDiscovery}
              disabled={discovering}
              className="w-full"
            >
              {discovering ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {isDocker && scanProgress.total > 0
                    ? t('printers.discovery.scanProgress', { scanned: scanProgress.scanned, total: scanProgress.total })
                    : t('printers.discovery.scanning')}
                </>
              ) : (
                <>
                  <Search className="w-4 h-4" />
                  {isDocker ? t('printers.discovery.scanSubnet') : t('printers.discovery.discoverNetwork')}
                </>
              )}
            </Button>

            {discoveryError && (
              <div className="mt-2 text-sm text-red-400">{discoveryError}</div>
            )}

            {newPrinters.length > 0 && (
              <div className="mt-3 space-y-2 max-h-40 overflow-y-auto">
                {newPrinters.map((printer) => (
                  <div
                    key={printer.serial}
                    className="flex items-center justify-between p-2 bg-bambu-dark rounded-lg hover:bg-bambu-dark-secondary cursor-pointer transition-colors"
                    onClick={() => selectPrinter(printer)}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-white text-sm truncate">
                        {printer.name || printer.serial}
                      </p>
                      <p className="text-xs text-bambu-gray truncate">
                        {mapModelCode(printer.model) || t('printers.discovery.unknown')} • {printer.ip_address}
                        {printer.serial.startsWith('unknown-') && (
                          <span className="text-yellow-500"> • {t('printers.discovery.serialRequired')}</span>
                        )}
                      </p>
                    </div>
                    <ChevronDown className="w-4 h-4 text-bambu-gray -rotate-90 flex-shrink-0 ml-2" />
                  </div>
                ))}
              </div>
            )}

            {discovering && (
              <p className="mt-2 text-sm text-bambu-gray text-center">
                {isDocker ? t('printers.discovery.scanningSubnet') : t('printers.discovery.scanningNetwork')}
              </p>
            )}

            {hasScanned && !discovering && discovered.length === 0 && (
              <p className="mt-2 text-sm text-bambu-gray text-center">
                {isDocker ? t('printers.discovery.noPrintersFoundSubnet') : t('printers.discovery.noPrintersFoundNetwork')}
              </p>
            )}

            {hasScanned && !discovering && discovered.length > 0 && newPrinters.length === 0 && (
              <p className="mt-2 text-sm text-bambu-gray text-center">
                {t('printers.discovery.allConfigured')}
              </p>
            )}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              onAdd(form);
            }}
            className="space-y-4"
          >
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.name')}</label>
              <input
                type="text"
                required
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder={t('printers.modal.myPrinter')}
              />
            </div>
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.ipAddress')}</label>
              <input
                type="text"
                required
                pattern="(\d{1,3}(\.\d{1,3}){3}|[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*)"
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.ip_address}
                onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
                placeholder="192.168.1.100 or printer.local"
              />
            </div>
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.serialNumber')}</label>
              <input
                type="text"
                required
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.serial_number}
                onChange={(e) => setForm({ ...form, serial_number: e.target.value })}
                placeholder="01P00A000000000"
              />
            </div>
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.accessCode')}</label>
              <input
                type="password"
                required
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.access_code}
                onChange={(e) => setForm({ ...form, access_code: e.target.value })}
                placeholder={t('printers.modal.fromPrinterSettings')}
              />
            </div>
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.modal.modelOptional')}</label>
              <select
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.model || ''}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
              >
                <option value="">{t('printers.modal.selectModel')}</option>
                <optgroup label="H2 Series">
                  <option value="H2C">H2C</option>
                  <option value="H2D">H2D</option>
                  <option value="H2D Pro">H2D Pro</option>
                  <option value="H2S">H2S</option>
                </optgroup>
                <optgroup label="X2 Series">
                  <option value="X2D">X2D</option>
                </optgroup>
                <optgroup label="X1 Series">
                  <option value="X1E">X1E</option>
                  <option value="X1C">X1 Carbon</option>
                  <option value="X1">X1</option>
                </optgroup>
                <optgroup label="P Series">
                  <option value="P2S">P2S</option>
                  <option value="P1S">P1S</option>
                  <option value="P1P">P1P</option>
                </optgroup>
                <optgroup label="A1 Series">
                  <option value="A1">A1</option>
                  <option value="A1 Mini">A1 Mini</option>
                </optgroup>
              </select>
            </div>
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.modal.locationGroup')}</label>
              <input
                type="text"
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.location || ''}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder={t('printers.modal.locationPlaceholder')}
              />
              <p className="text-xs text-bambu-gray mt-1">{t('printers.locationHelp')}</p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="auto_archive"
                checked={form.auto_archive}
                onChange={(e) => setForm({ ...form, auto_archive: e.target.checked })}
                className="rounded border-bambu-dark-tertiary bg-bambu-dark text-bambu-green focus:ring-bambu-green"
              />
              <label htmlFor="auto_archive" className="text-sm text-bambu-gray">
                {t('printers.modal.autoArchiveLabel')}
              </label>
            </div>
            <div className="flex gap-3 pt-4">
              <Button type="button" variant="secondary" onClick={onClose} className="flex-1">
                {t('common.cancel')}
              </Button>
              <Button type="submit" className="flex-1">
                {t('printers.addPrinter')}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}



// Component to check if a printer is offline (for power dropdown)
function usePrinterOfflineStatus(printerId: number) {
  const { data: status } = useQuery({
    queryKey: ['printerStatus', printerId],
    queryFn: () => api.getPrinterStatus(printerId),
    refetchInterval: 30000,
  });
  return !status?.connected;
}

// Power dropdown item for an offline printer
function PowerDropdownItem({
  printer,
  plug,
  onPowerOn,
  isPowering,
}: {
  printer: Printer;
  plug: { id: number; name: string };
  onPowerOn: (plugId: number) => void;
  isPowering: boolean;
}) {
  const isOffline = usePrinterOfflineStatus(printer.id);

  // Fetch plug status
  const { data: plugStatus } = useQuery({
    queryKey: ['smartPlugStatus', plug.id],
    queryFn: () => api.getSmartPlugStatus(plug.id),
    refetchInterval: 10000,
  });

  // Only show if printer is offline
  if (!isOffline) {
    return null;
  }

  return (
    <div className="flex items-center justify-between px-3 py-2 hover:bg-gray-100 dark:hover:bg-bambu-dark-tertiary">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-sm text-gray-900 dark:text-white truncate">{printer.name}</span>
        {plugStatus && (
          <span
            className={`text-xs px-1.5 py-0.5 rounded ${
              plugStatus.state === 'ON'
                ? 'bg-bambu-green/20 text-bambu-green'
                : 'bg-red-500/20 text-red-400'
            }`}
          >
            {plugStatus.state || '?'}
          </span>
        )}
      </div>
      <button
        onClick={() => onPowerOn(plug.id)}
        disabled={isPowering || plugStatus?.state === 'ON'}
        className={`px-2 py-1 text-xs rounded transition-colors flex items-center gap-1 ${
          plugStatus?.state === 'ON'
            ? 'bg-bambu-green/20 text-bambu-green cursor-default'
            : 'bg-bambu-green/20 text-bambu-green hover:bg-bambu-green hover:text-white'
        }`}
      >
        <Power className="w-3 h-3" />
        {isPowering ? '...' : 'On'}
      </button>
    </div>
  );
}

export function PrintersPage() {
  const { t } = useTranslation();
  const [showAddModal, setShowAddModal] = useState(false);
  const [hideDisconnected, setHideDisconnected] = useState(() => {
    return localStorage.getItem('hideDisconnectedPrinters') === 'true';
  });
  const [showPowerDropdown, setShowPowerDropdown] = useState(false);
  const [poweringOn, setPoweringOn] = useState<number | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>(() => {
    return (localStorage.getItem('printerSortBy') as SortOption) || 'name';
  });
  const [sortAsc, setSortAsc] = useState<boolean>(() => {
    return localStorage.getItem('printerSortAsc') !== 'false';
  });
  // Card size: 1=small, 2=medium, 3=large, 4=xl
  const [cardSize, setCardSize] = useState<number>(() => {
    const saved = localStorage.getItem('printerCardSize');
    return saved ? parseInt(saved, 10) : 2; // Default to medium
  });
  // Derive viewMode from cardSize: S=compact, M/L/XL=expanded
  const viewMode: ViewMode = cardSize === 1 ? 'compact' : 'expanded';
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [locationFilter, setLocationFilter] = useState<string>('all');
  const [statusCacheVersion, setStatusCacheVersion] = useState(0);
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>(() => {
    try {
      const saved = localStorage.getItem('printerCollapsedSections');
      return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
  });
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { hasPermission } = useAuth();
  // Embedded camera viewer state - supports multiple simultaneous viewers
  // Persisted to localStorage so cameras reopen after navigation
  const [embeddedCameraPrinters, setEmbeddedCameraPrinters] = useState<Map<number, { id: number; name: string }>>(() => {
    // Initialize from localStorage if camera_view_mode is embedded
    const saved = localStorage.getItem('openEmbeddedCameras');
    if (saved) {
      try {
        const cameras = JSON.parse(saved) as Array<{ id: number; name: string }>;
        return new Map(cameras.map(c => [c.id, c]));
      } catch {
        return new Map();
      }
    }
    return new Map();
  });

  // Persist open cameras to localStorage when they change
  useEffect(() => {
    const cameras = Array.from(embeddedCameraPrinters.values());
    if (cameras.length > 0) {
      localStorage.setItem('openEmbeddedCameras', JSON.stringify(cameras));
    } else {
      localStorage.removeItem('openEmbeddedCameras');
    }
  }, [embeddedCameraPrinters]);

  const { data: printers, isLoading } = useQuery({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  });

  // Fetch app settings for AMS thresholds
  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
  });

  // Compute drying presets: user-configured (from settings) merged over built-in defaults
  const effectiveDryingPresets = useMemo(() => {
    if (settings?.drying_presets) {
      try {
        const userPresets = JSON.parse(settings.drying_presets);
        if (typeof userPresets === 'object' && userPresets !== null && Object.keys(userPresets).length > 0) {
          return { ...DRYING_PRESETS, ...userPresets };
        }
      } catch { /* ignore parse errors, use defaults */ }
    }
    return DRYING_PRESETS;
  }, [settings?.drying_presets]);

  // Close embedded cameras if mode changes to 'window'
  useEffect(() => {
    if (settings?.camera_view_mode === 'window' && embeddedCameraPrinters.size > 0) {
      setEmbeddedCameraPrinters(new Map());
    }
  }, [settings?.camera_view_mode, embeddedCameraPrinters.size]);

  // Fetch all smart plugs to know which printers have them
  const { data: smartPlugs } = useQuery({
    queryKey: ['smart-plugs'],
    queryFn: api.getSmartPlugs,
  });

  // Fetch maintenance overview for all printers to show badges
  const { data: maintenanceOverview } = useQuery({
    queryKey: ['maintenanceOverview'],
    queryFn: api.getMaintenanceOverview,
    staleTime: 60 * 1000, // 1 minute
  });

  // Fetch Spoolman status to enable link spool feature
  const { data: spoolmanStatus } = useQuery({
    queryKey: ['spoolman-status'],
    queryFn: api.getSpoolmanStatus,
    staleTime: 60 * 1000, // 1 minute
  });
  const spoolmanEnabled = spoolmanStatus?.enabled && spoolmanStatus?.connected;

  // Fetch Spoolman settings to get sync mode
  const { data: spoolmanSettings } = useQuery({
    queryKey: ['spoolman-settings'],
    queryFn: api.getSpoolmanSettings,
    enabled: !!spoolmanEnabled,
    staleTime: 60 * 1000, // 1 minute
  });
  const spoolmanSyncMode = spoolmanSettings?.spoolman_sync_mode;

  // Fetch unlinked spools to know if link button should be enabled
  const { data: unlinkedSpools } = useQuery({
    queryKey: ['unlinked-spools'],
    queryFn: api.getUnlinkedSpools,
    enabled: !!spoolmanEnabled,
    staleTime: 30 * 1000, // 30 seconds
  });
  const hasUnlinkedSpools = unlinkedSpools && unlinkedSpools.length > 0;

  // Fetch linked spools map (tag -> spool_id) to know which spools are already in Spoolman
  const { data: linkedSpoolsData } = useQuery({
    queryKey: ['linked-spools'],
    queryFn: api.getLinkedSpools,
    enabled: !!spoolmanEnabled,
    staleTime: 30 * 1000, // 30 seconds
  });
  const linkedSpools = linkedSpoolsData?.linked;

  // Fetch spool assignments for inventory feature
  const { data: spoolAssignments } = useQuery({
    queryKey: ['spool-assignments'],
    queryFn: () => api.getAssignments(),
    enabled: hasPermission('inventory:view_assignments'),
    staleTime: 30 * 1000,
  });

  const unassignMutation = useMutation({
    mutationFn: ({ printerId, amsId, trayId }: { printerId: number; amsId: number; trayId: number }) =>
      api.unassignSpool(printerId, amsId, trayId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spool-assignments'] });
    },
  });

  const { data: spoolmanSpools, isLoading: spoolmanSpoolsLoading } = useQuery({
    queryKey: ['spoolman-inventory-spools'],
    queryFn: () => api.getSpoolmanInventorySpools(false),
    enabled: !!spoolmanEnabled,
    staleTime: 30 * 1000,
  });

  const { data: spoolmanSlotAssignments, isLoading: spoolmanAssignmentsLoading } = useQuery({
    queryKey: ['spoolman-slot-assignments'],
    queryFn: () => api.getSpoolmanSlotAssignments(),
    enabled: !!spoolmanEnabled,
    staleTime: 30 * 1000,
  });

  const unassignSpoolmanMutation = useMutation({
    mutationFn: (spoolmanSpoolId: number) => api.unassignSpoolmanSlot(spoolmanSpoolId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spoolman-inventory-spools'] });
      queryClient.invalidateQueries({ queryKey: ['spoolman-slot-assignments'] });
    },
  });

  // Helper to find assignment for a specific slot
  const getAssignment = (printerId: number, amsId: number | string, trayId: number | string): SpoolAssignment | undefined => {
    return spoolAssignments?.find(
      (a) => a.printer_id === printerId && a.ams_id === Number(amsId) && a.tray_id === Number(trayId)
    );
  };

  // Create a map of printer_id -> maintenance info for quick lookup
  const maintenanceByPrinter = maintenanceOverview?.reduce(
    (acc, overview) => {
      acc[overview.printer_id] = {
        due_count: overview.due_count,
        warning_count: overview.warning_count,
        total_print_hours: overview.total_print_hours,
      };
      return acc;
    },
    {} as Record<number, PrinterMaintenanceInfo>
  ) || {};

  // Create a map of printer_id -> smart plug
  const smartPlugByPrinter = smartPlugs?.reduce(
    (acc, plug) => {
      if (plug.printer_id) {
        acc[plug.printer_id] = plug;
      }
      return acc;
    },
    {} as Record<number, typeof smartPlugs[0]>
  ) || {};

  const addMutation = useMutation({
    mutationFn: api.createPrinter,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] });
      queryClient.invalidateQueries({ queryKey: ['maintenanceOverview'] });
      setShowAddModal(false);
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToAdd'), 'error'),
  });

  const powerOnMutation = useMutation({
    mutationFn: (plugId: number) => api.controlSmartPlug(plugId, 'on'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plugs'] });
      setPoweringOn(null);
    },
    onError: () => {
      setPoweringOn(null);
    },
  });

  // Bulk selection state
  const [selectedPrinterIds, setSelectedPrinterIds] = useState<Set<number>>(new Set());
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [bulkConfirmAction, setBulkConfirmAction] = useState<'stop' | 'pause' | 'clearPlate' | null>(null);
  const [bulkActionPending, setBulkActionPending] = useState(false);
  const selectionMode = isSelectionMode || selectedPrinterIds.size > 0;

  const toggleSelect = useCallback((id: number) => {
    setSelectedPrinterIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedPrinterIds(new Set());
    setIsSelectionMode(false);
  }, []);

  // Escape key exits selection mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && selectionMode) {
        clearSelection();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectionMode, clearSelection]);

  const executeBulkAction = useCallback(async (action: 'stop' | 'pause' | 'resume' | 'clearPlate' | 'clearHMS') => {
    setBulkActionPending(true);
    const ids = Array.from(selectedPrinterIds);

    // Filter to only applicable printers based on cached state
    const applicableIds = ids.filter(id => {
      const status = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', id]);
      if (!status?.connected) return false;
      switch (action) {
        case 'stop': return status.state === 'RUNNING' || status.state === 'PAUSE';
        case 'pause': return status.state === 'RUNNING';
        case 'resume': return status.state === 'PAUSE';
        case 'clearPlate': return !!(status as { awaiting_plate_clear?: boolean }).awaiting_plate_clear;
        case 'clearHMS': return status.hms_errors && filterKnownHMSErrors(status.hms_errors).length > 0;
        default: return false;
      }
    });

    if (applicableIds.length === 0) {
      showToast(t('printers.bulk.noneApplicable'), 'error');
      setBulkActionPending(false);
      setBulkConfirmAction(null);
      return;
    }

    const apiCall = {
      stop: api.stopPrint,
      pause: api.pausePrint,
      resume: api.resumePrint,
      clearPlate: api.clearPlate,
      clearHMS: api.clearHMSErrors,
    }[action];

    const results = await Promise.allSettled(
      applicableIds.map(id => apiCall(id))
    );

    const succeeded = results.filter(r => r.status === 'fulfilled').length;
    const failed = results.filter(r => r.status === 'rejected').length;

    if (failed === 0) {
      showToast(t('printers.bulk.success', { action: t(`printers.bulk.actions.${action}`), count: succeeded }));
    } else {
      showToast(t('printers.bulk.partial', { succeeded, failed }), 'error');
    }

    // Invalidate status queries for affected printers
    applicableIds.forEach(id => {
      queryClient.invalidateQueries({ queryKey: ['printerStatus', id] });
    });

    setBulkActionPending(false);
    setBulkConfirmAction(null);
  }, [selectedPrinterIds, queryClient, showToast, t]);

  const handleBulkAction = useCallback((action: 'stop' | 'pause' | 'resume' | 'clearPlate' | 'clearHMS') => {
    // Actions that need confirmation
    if (action === 'stop' || action === 'pause' || action === 'clearPlate') {
      setBulkConfirmAction(action);
    } else {
      executeBulkAction(action);
    }
  }, [executeBulkAction]);

  const toggleHideDisconnected = () => {
    const newValue = !hideDisconnected;
    setHideDisconnected(newValue);
    localStorage.setItem('hideDisconnectedPrinters', String(newValue));
  };

  const handleSortChange = (newSort: SortOption) => {
    setSortBy(newSort);
    localStorage.setItem('printerSortBy', newSort);
  };

  const toggleSortDirection = () => {
    const newAsc = !sortAsc;
    setSortAsc(newAsc);
    localStorage.setItem('printerSortAsc', String(newAsc));
  };

  // Grid classes based on card size (1=small, 2=medium, 3=large, 4=xl)
  const getGridClasses = () => {
    switch (cardSize) {
      case 1: return 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5'; // S: many small cards
      case 2: return 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3'; // M: medium cards
      case 3: return 'grid-cols-1 lg:grid-cols-2'; // L: large cards, 2 columns max
      case 4: return 'grid-cols-1'; // XL: single column, full width
      default: return 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3';
    }
  };

  const cardSizeLabels = ['S', 'M', 'L', 'XL'];

  // Increment version counter whenever a printer status cache entry is updated so
  // filteredPrinters re-computes reactively on WebSocket-driven status changes.
  useEffect(() => {
    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      if (
        event.type === 'updated' &&
        Array.isArray(event.query.queryKey) &&
        event.query.queryKey[0] === 'printerStatus'
      ) {
        setStatusCacheVersion(v => v + 1);
      }
    });
    return unsubscribe;
  }, [queryClient]);

  // Filter printers by search term, status, and location
  const filteredPrinters = useMemo(() => {
    if (!printers) return [];
    let result = printers;

    // Text search
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter(p =>
        p.name.toLowerCase().includes(q) ||
        (p.model || '').toLowerCase().includes(q) ||
        (p.location || '').toLowerCase().includes(q) ||
        (p.serial_number || '').toLowerCase().includes(q)
      );
    }

    // Location filter
    if (locationFilter !== 'all') {
      result = result.filter(p => (p.location || '') === locationFilter);
    }

    // Status filter
    if (statusFilter !== 'all') {
      result = result.filter(p => {
        const status = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', p.id]);
        if (!status?.connected) return statusFilter === 'offline';
        const hmsErrors = status.hms_errors ? filterKnownHMSErrors(status.hms_errors) : [];
        switch (statusFilter) {
          case 'printing': return status.state === 'RUNNING';
          case 'paused':   return status.state === 'PAUSE';
          case 'finished': return status.state === 'FINISH';
          case 'error':    return status.state === 'FAILED' || hmsErrors.length > 0;
          case 'idle':     return status.state !== 'RUNNING' && status.state !== 'PAUSE' && status.state !== 'FINISH' && status.state !== 'FAILED' && hmsErrors.length === 0;
          case 'offline':  return false; // Connected printers are never offline
          default:         return true;
        }
      });
    }

    return result;
  // eslint-disable-next-line react-hooks/exhaustive-deps -- statusCacheVersion is intentional: it forces recompute when WebSocket updates printer status cache
  }, [printers, search, statusFilter, locationFilter, queryClient, statusCacheVersion]);

  // Derive unique locations for the location filter dropdown
  const availableLocations = useMemo(() => {
    if (!printers) return [];
    return [...new Set(printers.map(p => p.location || '').filter(Boolean))].sort();
  }, [printers]);

  // Sort printers based on selected option
  const sortedPrinters = useMemo(() => {
    const sorted = [...filteredPrinters];

    switch (sortBy) {
      case 'name':
        sorted.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case 'model':
        sorted.sort((a, b) => (a.model || '').localeCompare(b.model || ''));
        break;
      case 'location':
        // Sort by location, with ungrouped printers last
        sorted.sort((a, b) => {
          const locA = a.location || '';
          const locB = b.location || '';
          if (!locA && locB) return 1;
          if (locA && !locB) return -1;
          return locA.localeCompare(locB) || a.name.localeCompare(b.name);
        });
        break;
      case 'status':
        // Sort by status: HMS errors > printing > idle > offline
        sorted.sort((a, b) => {
          const statusA = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', a.id]);
          const statusB = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', b.id]);

          const getPriority = (s: typeof statusA) => {
            if (!s?.connected) return 3; // offline
            const hmsErrors = s.hms_errors ? filterKnownHMSErrors(s.hms_errors) : [];
            if (hmsErrors.length > 0) return 0; // HMS errors - top priority
            if (s.state === 'RUNNING') return 1; // printing
            return 2; // idle
          };

          return getPriority(statusA) - getPriority(statusB);
        });
        break;
    }

    // Apply ascending/descending
    if (!sortAsc) {
      sorted.reverse();
    }

    return sorted;
  }, [filteredPrinters, sortBy, sortAsc, queryClient]);

  const selectAll = useCallback(() => {
    setSelectedPrinterIds(new Set(sortedPrinters.map(p => p.id)));
    setIsSelectionMode(true);
  }, [sortedPrinters]);

  const selectByState = useCallback((state: PrinterState) => {
    setSelectedPrinterIds(prev => {
      const next = new Set(prev);
      sortedPrinters.forEach(p => {
        const status = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', p.id]);
        if (classifyPrinterStatus(status) === state) next.add(p.id);
      });
      return next;
    });
    setIsSelectionMode(true);
  }, [sortedPrinters, queryClient]);

  const selectByLocation = useCallback((location: string) => {
    setSelectedPrinterIds(prev => {
      const next = new Set(prev);
      sortedPrinters.filter(p => (p.location || '') === location).forEach(p => next.add(p.id));
      return next;
    });
    setIsSelectionMode(true);
  }, [sortedPrinters]);

  const selectByModel = useCallback((model: string) => {
    setSelectedPrinterIds(prev => {
      const next = new Set(prev);
      sortedPrinters.filter(p => (p.model || 'Unknown') === model).forEach(p => next.add(p.id));
      return next;
    });
    setIsSelectionMode(true);
  }, [sortedPrinters]);

  const toggleSectionCollapse = useCallback((key: string) => {
    setCollapsedSections(prev => {
      const next = { ...prev, [key]: !prev[key] };
      try { localStorage.setItem('printerCollapsedSections', JSON.stringify(next)); } catch { /* quota exceeded / private mode */ }
      return next;
    });
  }, []);

  // Group printers when sorted by location, status, or model
  const groupedPrinters = useMemo(() => {
    if (sortBy === 'name') return null;

    const groups: Record<string, typeof sortedPrinters> = {};

    if (sortBy === 'location') {
      sortedPrinters.forEach(printer => {
        const location = printer.location || 'Ungrouped';
        if (!groups[location]) groups[location] = [];
        groups[location].push(printer);
      });
    } else if (sortBy === 'model') {
      sortedPrinters.forEach(printer => {
        const model = printer.model || 'Unknown';
        if (!groups[model]) groups[model] = [];
        groups[model].push(printer);
      });
    } else if (sortBy === 'status') {
      sortedPrinters.forEach(printer => {
        const status = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', printer.id]);
        const group = classifyPrinterStatus(status);
        if (!groups[group]) groups[group] = [];
        groups[group].push(printer);
      });
    }

    return groups;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- classifyPrinterStatus & filterKnownHMSErrors are stable module-level functions, not reactive deps; statusCacheVersion forces recompute on WebSocket status updates
  }, [sortBy, sortedPrinters, queryClient, statusCacheVersion]);

  const toolbarRef = useRef<HTMLDivElement>(null);
  const expandedToolbarControlsRef = useRef<HTMLDivElement>(null);
  const expandedToolbarWidthRef = useRef(0);
  const [compactToolbar, setCompactToolbar] = useState(false);

  const measureToolbar = useCallback(() => {
    const toolbar = toolbarRef.current;
    if (!toolbar) return;

    const measuredControlsWidth = expandedToolbarControlsRef.current?.offsetWidth;
    if (measuredControlsWidth) {
      expandedToolbarWidthRef.current = measuredControlsWidth;
    }

    const searchMinimumWidth = 220;
    const gapWidth = 8;
    const shouldCompact = expandedToolbarWidthRef.current > 0 && toolbar.clientWidth < expandedToolbarWidthRef.current + searchMinimumWidth + gapWidth;
    setCompactToolbar(prev => (prev === shouldCompact ? prev : shouldCompact));
  }, []);

  const smartPlugCount = Object.keys(smartPlugByPrinter).length;
  useLayoutEffect(() => {
    measureToolbar();

    const toolbar = toolbarRef.current;
    if (!toolbar) return;

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measureToolbar);
      return () => window.removeEventListener('resize', measureToolbar);
    }

    const resizeObserver = new ResizeObserver(() => measureToolbar());
    resizeObserver.observe(toolbar);
    window.addEventListener('resize', measureToolbar);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', measureToolbar);
    };
  }, [
    measureToolbar,
    printers?.length,
    availableLocations.length,
    hideDisconnected,
    smartPlugCount,
  ]);

  const renderFilterControls = (inMenu = false) => (
    <>
      {/* Status filter */}
      {printers && printers.length > 0 && (
        <ToolbarDropdown
          value={statusFilter}
          onChange={setStatusFilter}
          fullWidth={inMenu}
          options={[
            { value: 'all', label: t('printers.filter.allStatuses') },
            { value: 'printing', label: t('printers.status.printing') },
            { value: 'paused', label: t('printers.status.paused') },
            { value: 'idle', label: t('printers.status.idle') },
            { value: 'finished', label: t('printers.status.finished') },
            { value: 'error', label: t('printers.status.error') },
            { value: 'offline', label: t('printers.status.offline') },
          ]}
        />
      )}

      {/* Location filter — only shown when at least one printer has a location */}
      {printers && printers.length > 0 && availableLocations.length > 0 && (
        <ToolbarDropdown
          value={locationFilter}
          onChange={setLocationFilter}
          fullWidth={inMenu}
          options={[
            { value: 'all', label: t('printers.filter.allLocations') },
            ...availableLocations.map(loc => ({ value: loc, label: loc })),
          ]}
        />
      )}

      <button
        type="button"
        onClick={toggleHideDisconnected}
        aria-pressed={hideDisconnected}
        className={`h-8 px-2 rounded-lg border text-sm font-medium transition-colors ${inMenu ? 'w-full' : ''} ${
          hideDisconnected
            ? 'bg-bambu-green border-bambu-green text-white'
            : 'bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary'
        }`}
      >
        {t('printers.hideOffline')}
      </button>
    </>
  );

  const renderViewControls = (inMenu = false) => (
    <>
      {/* Sort dropdown */}
      <div className={`flex items-center gap-1 ${inMenu ? 'w-full' : ''}`}>
        <ToolbarDropdown<SortOption>
          value={sortBy}
          onChange={handleSortChange}
          fullWidth={inMenu}
          options={[
            { value: 'name', label: t('printers.sort.name') },
            { value: 'status', label: t('printers.sort.status') },
            { value: 'model', label: t('printers.sort.model') },
            { value: 'location', label: t('printers.sort.location') },
          ]}
        />
        <button
          onClick={toggleSortDirection}
          className="h-8 shrink-0 px-2 rounded-lg border bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary transition-colors flex items-center justify-center"
          title={sortAsc ? t('printers.sort.descending') : t('printers.sort.ascending')}
        >
          {sortAsc ? (
            <ArrowUp className="w-4 h-4 text-white" />
          ) : (
            <ArrowDown className="w-4 h-4 text-white" />
          )}
        </button>
      </div>

      {/* Card size selector */}
      <div className={`flex h-8 items-center bg-bambu-dark rounded-lg border border-bambu-dark-tertiary ${inMenu ? 'w-full' : ''}`}>
        {cardSizeLabels.map((label, index) => {
          const size = index + 1;
          const isSelected = cardSize === size;
          return (
            <button
              key={label}
              onClick={() => {
                setCardSize(size);
                localStorage.setItem('printerCardSize', String(size));
              }}
              className={`h-full px-2 text-xs font-medium transition-colors ${inMenu ? 'flex-1' : ''} ${
                index === 0 ? 'rounded-l-lg' : ''
              } ${
                index === cardSizeLabels.length - 1 ? 'rounded-r-lg' : ''
              } ${
                isSelected
                  ? 'bg-bambu-green text-white'
                  : 'text-white hover:bg-bambu-dark-tertiary'
              }`}
              title={label === 'S' ? t('printers.cardSize.small') : label === 'M' ? t('printers.cardSize.medium') : label === 'L' ? t('printers.cardSize.large') : t('printers.cardSize.extraLarge')}
            >
              {label}
            </button>
          );
        })}
      </div>
    </>
  );

  const renderActionControls = (inMenu = false) => (
    <>
      {/* Bulk select toggle */}
      <button
        onClick={() => {
          if (selectionMode) clearSelection();
          else setIsSelectionMode(true);
        }}
        className={`h-8 px-2 rounded-lg border transition-colors ${inMenu ? 'w-full justify-center gap-1.5 text-sm font-medium flex items-center' : ''} ${
          selectionMode
            ? 'bg-bambu-green border-bambu-green text-white'
            : 'bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary'
        }`}
        title={t('printers.bulk.select')}
        disabled={!hasPermission('printers:control')}
      >
        <CheckSquare className="w-4 h-4" />
        {inMenu && <span>{t('printers.bulk.select')}</span>}
      </button>

      {/* Power dropdown for offline printers with smart plugs */}
      {hideDisconnected && Object.keys(smartPlugByPrinter).length > 0 && (
        <div className={`relative ${inMenu ? 'w-full' : ''}`}>
          <button
            onClick={() => setShowPowerDropdown(!showPowerDropdown)}
            className={`h-8 flex items-center gap-1.5 px-2 text-sm rounded-lg border transition-colors ${
              inMenu
                ? 'w-full justify-between bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary hover:text-white'
                : 'bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <Power className="w-4 h-4" />
              {t('printers.powerOn')}
            </span>
            <ChevronDown className={`w-3 h-3 transition-transform ${showPowerDropdown ? 'rotate-180' : ''}`} />
          </button>
          {showPowerDropdown && (
            <>
              {/* Backdrop to close dropdown */}
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowPowerDropdown(false)}
              />
              <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-bambu-dark-secondary border border-gray-200 dark:border-bambu-dark-tertiary rounded-lg shadow-lg z-20 py-1">
                <div className="px-3 py-2 text-xs text-gray-500 dark:text-bambu-gray border-b border-gray-200 dark:border-bambu-dark-tertiary">
                  {t('printers.offlinePrintersWithPlugs')}
                </div>
                {printers?.filter(p => smartPlugByPrinter[p.id]).map(printer => (
                  <PowerDropdownItem
                    key={printer.id}
                    printer={printer}
                    plug={smartPlugByPrinter[printer.id]}
                    onPowerOn={(plugId) => {
                      setPoweringOn(plugId);
                      powerOnMutation.mutate(plugId);
                    }}
                    isPowering={poweringOn === smartPlugByPrinter[printer.id]?.id}
                  />
                ))}
                {printers?.filter(p => smartPlugByPrinter[p.id]).length === 0 && (
                  <div className="px-3 py-2 text-sm text-bambu-gray">
                    No printers with smart plugs
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
      <Button
        onClick={() => setShowAddModal(true)}
        disabled={!hasPermission('printers:create')}
        title={!hasPermission('printers:create') ? t('printers.permission.noAdd') : undefined}
        className={`!h-8 !min-h-8 px-2 py-0 ${inMenu ? 'w-full' : ''}`}
      >
        <Plus className="w-4 h-4" />
        {t('printers.addPrinter')}
      </Button>
    </>
  );

  return (
    <div className="p-4 md:p-8">
      <div className="space-y-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <PrinterIcon className="w-7 h-7 text-bambu-green" />
            {t('printers.title')}
          </h1>
          <StatusSummaryBar printers={printers} />
        </div>
        <div ref={toolbarRef} className="relative flex items-center gap-2">
          {/* Only show search bar when printers exist */}
          {printers && printers.length > 0 && (
            <div className="relative min-w-0 flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bambu-gray/50" />
              <input
                type="search"
                name="printer-search"
                autoComplete="off"
                data-1p-ignore
                data-lpignore="true"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('printers.search')}
                aria-label={t('printers.search')}
                className="w-full h-8 pl-9 pr-8 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm placeholder:text-bambu-gray/50 focus:outline-none focus:border-bambu-green"
              />
              {search && (
                <button
                  type="button"
                  aria-label={t('common.clear')}
                  onClick={() => setSearch('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-bambu-gray hover:text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          )}
          <div
            ref={expandedToolbarControlsRef}
            aria-hidden={compactToolbar}
            inert={compactToolbar}
            className={`${compactToolbar ? 'absolute -left-[9999px] top-0 flex w-max pointer-events-none opacity-0' : 'flex'} ml-auto items-center justify-end gap-2 flex-nowrap [&>*]:shrink-0`}
          >
            <div className="h-6 w-px bg-bambu-dark-tertiary" />
            <div className="flex items-center gap-2">{renderFilterControls()}</div>
            <div className="h-6 w-px bg-bambu-dark-tertiary" />
            <div className="flex items-center gap-2">{renderViewControls()}</div>
            <div className="h-6 w-px bg-bambu-dark-tertiary" />
            <div className="flex items-center gap-2">{renderActionControls()}</div>
          </div>

          {compactToolbar && (
            <div className="ml-auto flex items-center justify-end gap-1">
              <ToolbarMenu label={t('printers.toolbar.filters', 'Filters')} icon={<Filter className="w-4 h-4" />}>
                <div className="flex w-48 flex-col gap-2">{renderFilterControls(true)}</div>
              </ToolbarMenu>
              <ToolbarMenu label={t('printers.toolbar.view', 'View')} icon={<SlidersHorizontal className="w-4 h-4" />}>
                <div className="flex w-48 flex-col gap-2">{renderViewControls(true)}</div>
              </ToolbarMenu>
              <ToolbarMenu label={t('printers.toolbar.actions', 'Actions')} icon={<MoreHorizontal className="w-4 h-4" />}>
                <div className="flex w-48 flex-col gap-2">{renderActionControls(true)}</div>
              </ToolbarMenu>
            </div>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-bambu-gray">{t('common.loading')}</div>
      ) : printers?.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12">
            <p className="text-bambu-gray mb-4">{t('printers.noPrintersConfigured')}</p>
            <Button
              onClick={() => setShowAddModal(true)}
              disabled={!hasPermission('printers:create')}
              title={!hasPermission('printers:create') ? t('printers.permission.noAdd') : undefined}
            >
              <Plus className="w-4 h-4" />
              {t('printers.addPrinter')}
            </Button>
          </CardContent>
        </Card>
      ) : sortedPrinters.length === 0 && (search.trim() || statusFilter !== 'all' || locationFilter !== 'all') ? (
        <Card>
          <CardContent className="text-center py-12">
            <p className="text-bambu-gray">{t('printers.noSearchResults')}</p>
          </CardContent>
        </Card>
      ) : groupedPrinters ? (
        /* Grouped view (location, status, or model) */
        <div className="space-y-6">
          {(() => {
            const keys = sortBy === 'status'
              ? STATUS_GROUP_ORDER.filter(k => groupedPrinters[k]?.length > 0)
              : Object.keys(groupedPrinters);
            // For status grouping, asc/desc flips the fixed priority order
            // (asc = error→offline, desc = offline→error). This matches the
            // sort-toggle behaviour for other groupings.
            return (sortAsc ? keys : [...keys].reverse());
          })().map((groupKey) => {
            const groupPrinters = groupedPrinters[groupKey];
            const collapseKey = `${sortBy}:${groupKey}`;
            const isOpen = !collapsedSections[collapseKey];

            const dot = sortBy === 'status'
              ? STATUS_GROUP_META[groupKey]?.dot || 'bg-bambu-green'
              : 'bg-bambu-green';
            const label = sortBy === 'status'
              ? t(STATUS_GROUP_META[groupKey]?.labelKey || groupKey)
              : groupKey;

            return (
              <Collapsible
                key={groupKey}
                open={isOpen}
                onToggle={() => toggleSectionCollapse(collapseKey)}
                summaryClassName="py-1"
                summary={
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${dot}`} />
                    {label}
                    <span className="text-sm font-normal text-bambu-gray">({groupPrinters.length})</span>
                    {selectionMode && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (sortBy === 'location') selectByLocation(groupKey === 'Ungrouped' ? '' : groupKey);
                          else if (sortBy === 'status') selectByState(groupKey as PrinterState);
                          else if (sortBy === 'model') selectByModel(groupKey);
                        }}
                        className="text-xs text-bambu-green hover:text-bambu-green-light transition-colors ml-1"
                      >
                        {t('printers.bulk.selectAll')}
                      </button>
                    )}
                  </h2>
                }
              >
                <div className={`grid gap-4 ${cardSize >= 3 ? 'gap-6' : ''} ${getGridClasses()}`}>
                  {groupPrinters.map((printer) => (
                    <PrinterCard
                      key={printer.id}
                      printer={printer}
                      hideIfDisconnected={hideDisconnected}
                      maintenanceInfo={maintenanceByPrinter[printer.id]}
                      viewMode={viewMode}
                      cardSize={cardSize}
                      amsThresholds={settings ? {
                        humidityGood: Number(settings.ams_humidity_good) || 40,
                        humidityFair: Number(settings.ams_humidity_fair) || 60,
                        tempGood: Number(settings.ams_temp_good) || 28,
                        tempFair: Number(settings.ams_temp_fair) || 35,
                      } : undefined}
                      spoolmanEnabled={spoolmanEnabled}
                      hasUnlinkedSpools={hasUnlinkedSpools}
                      linkedSpools={linkedSpools}
                      spoolmanUrl={spoolmanStatus?.url}
                      spoolmanSyncMode={spoolmanSyncMode}
                      onGetAssignment={getAssignment}
                      onUnassignSpool={(pid, aid, tid) => unassignMutation.mutate({ printerId: pid, amsId: aid, trayId: tid })}
                      spoolmanSpools={spoolmanSpools}
                      spoolmanSlotAssignments={spoolmanSlotAssignments}
                      spoolmanLoading={spoolmanSpoolsLoading || spoolmanAssignmentsLoading}
                      onUnassignSpoolmanSpool={(id) => unassignSpoolmanMutation.mutate(id)}
                      timeFormat={settings?.time_format || 'system'}
                      cameraViewMode={settings?.camera_view_mode || 'window'}
                      onOpenEmbeddedCamera={(id, name) => setEmbeddedCameraPrinters(prev => new Map(prev).set(id, { id, name }))}
                      checkPrinterFirmware={settings?.check_printer_firmware !== false}
                      dryingPresets={effectiveDryingPresets}
                      requirePlateClear={settings?.require_plate_clear === true}
                      selectionMode={selectionMode}
                      isSelected={selectedPrinterIds.has(printer.id)}
                      onToggleSelect={toggleSelect}
                    />
                  ))}
                </div>
              </Collapsible>
            );
          })}
        </div>
      ) : (
        /* Regular grid view */
        <div className={`grid gap-4 ${cardSize >= 3 ? 'gap-6' : ''} ${getGridClasses()}`}>
          {sortedPrinters.map((printer) => (
            <PrinterCard
              key={printer.id}
              printer={printer}
              hideIfDisconnected={hideDisconnected}
              maintenanceInfo={maintenanceByPrinter[printer.id]}
              viewMode={viewMode}
              cardSize={cardSize}
              spoolmanEnabled={spoolmanEnabled}
              hasUnlinkedSpools={hasUnlinkedSpools}
              linkedSpools={linkedSpools}
              spoolmanUrl={spoolmanStatus?.url}
              spoolmanSyncMode={spoolmanSyncMode}
              onGetAssignment={getAssignment}
              onUnassignSpool={(pid, aid, tid) => unassignMutation.mutate({ printerId: pid, amsId: aid, trayId: tid })}
              spoolmanSpools={spoolmanSpools}
              spoolmanSlotAssignments={spoolmanSlotAssignments}
              spoolmanLoading={spoolmanSpoolsLoading || spoolmanAssignmentsLoading}
              onUnassignSpoolmanSpool={(id) => unassignSpoolmanMutation.mutate(id)}
              amsThresholds={settings ? {
                humidityGood: Number(settings.ams_humidity_good) || 40,
                humidityFair: Number(settings.ams_humidity_fair) || 60,
                tempGood: Number(settings.ams_temp_good) || 28,
                tempFair: Number(settings.ams_temp_fair) || 35,
              } : undefined}
              timeFormat={settings?.time_format || 'system'}
              cameraViewMode={settings?.camera_view_mode || 'window'}
              onOpenEmbeddedCamera={(id, name) => setEmbeddedCameraPrinters(prev => new Map(prev).set(id, { id, name }))}
              checkPrinterFirmware={settings?.check_printer_firmware !== false}
              dryingPresets={effectiveDryingPresets}
              requirePlateClear={settings?.require_plate_clear === true}
              selectionMode={selectionMode}
              isSelected={selectedPrinterIds.has(printer.id)}
              onToggleSelect={toggleSelect}
            />
          ))}
        </div>
      )}

      {showAddModal && (
        <AddPrinterModal
          onClose={() => setShowAddModal(false)}
          onAdd={(data) => addMutation.mutate(data)}
          existingSerials={printers?.map(p => p.serial_number) || []}
        />
      )}

      {/* Bulk selection toolbar */}
      {selectionMode && printers && (
        <BulkPrinterToolbar
          selectedIds={selectedPrinterIds}
          printers={printers}
          onClose={clearSelection}
          onSelectAll={selectAll}
          onSelectByLocation={selectByLocation}
          onSelectByState={selectByState}
          onAction={handleBulkAction}
          actionPending={bulkActionPending}
        />
      )}

      {/* Bulk action confirmation modals */}
      {bulkConfirmAction === 'stop' && (
        <ConfirmModal
          title={t('printers.bulk.confirm.stopTitle', { count: selectedPrinterIds.size })}
          message={t('printers.bulk.confirm.stopMessage', { count: selectedPrinterIds.size })}
          confirmText={t('printers.bulk.confirm.stopButton')}
          variant="danger"
          isLoading={bulkActionPending}
          onConfirm={() => executeBulkAction('stop')}
          onCancel={() => setBulkConfirmAction(null)}
        />
      )}
      {bulkConfirmAction === 'pause' && (
        <ConfirmModal
          title={t('printers.bulk.confirm.pauseTitle', { count: selectedPrinterIds.size })}
          message={t('printers.bulk.confirm.pauseMessage', { count: selectedPrinterIds.size })}
          confirmText={t('printers.bulk.confirm.pauseButton')}
          isLoading={bulkActionPending}
          onConfirm={() => executeBulkAction('pause')}
          onCancel={() => setBulkConfirmAction(null)}
        />
      )}
      {bulkConfirmAction === 'clearPlate' && (
        <ConfirmModal
          title={t('printers.bulk.confirm.clearPlateTitle', { count: selectedPrinterIds.size })}
          message={t('printers.bulk.confirm.clearPlateMessage', { count: selectedPrinterIds.size })}
          confirmText={t('printers.bulk.confirm.clearPlateButton')}
          isLoading={bulkActionPending}
          onConfirm={() => executeBulkAction('clearPlate')}
          onCancel={() => setBulkConfirmAction(null)}
        />
      )}

      {/* Embedded Camera Viewers - multiple viewers can be open simultaneously */}
      {Array.from(embeddedCameraPrinters.values()).map((camera, index) => (
        <EmbeddedCameraViewer
          key={camera.id}
          printerId={camera.id}
          printerName={camera.name}
          viewerIndex={index}
          onClose={() => setEmbeddedCameraPrinters(prev => {
            const next = new Map(prev);
            next.delete(camera.id);
            return next;
          })}
        />
      ))}
    </div>
  );
}
