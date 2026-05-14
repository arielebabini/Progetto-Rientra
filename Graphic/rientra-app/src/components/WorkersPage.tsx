import { useState, useEffect, useCallback, useRef } from 'react';
import './WorkersPage.css';
import JobAnalysisView from './JobAnalysisView';
import {
  fetchStatus,
  fetchWorkers,
  fetchHealthConditions,
  fetchCoreSets,
  selectWorker,
  importWorkers,
  type ServiceStatus,
  type Worker,
  type HealthCondition,
  type ImportWorkersResult,
} from '../api/semanticService';
import HealthConditionWizard from './HealthConditionWizard';


/* ─────────────────────────────────────────────
   Inline SVG icons
───────────────────────────────────────────── */
const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);
const ListIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" />
    <line x1="8" y1="18" x2="21" y2="18" /><line x1="3" y1="6" x2="3.01" y2="6" />
    <line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
  </svg>
);
const PlusIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);
const EditIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
  </svg>
);
const DotsIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
    <circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" />
  </svg>
);
const ArchiveIcon = () => (
  <span style={{
    display: 'inline-block',
    width: 16,
    height: 16,
    backgroundColor: 'currentColor',
    maskImage: 'url(/Archive.png)',
    maskSize: 'contain',
    maskRepeat: 'no-repeat',
    maskPosition: 'center',
    WebkitMaskImage: 'url(/Archive.png)',
    WebkitMaskSize: 'contain',
    WebkitMaskRepeat: 'no-repeat',
    WebkitMaskPosition: 'center'
  }} />
);
const PdfIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
  </svg>
);
const RefreshIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
  </svg>
);
const FilterIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
  </svg>
);
const ArrowRightIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="5" y1="12" x2="19" y2="12"></line>
    <polyline points="12 5 19 12 12 19"></polyline>
  </svg>
);
const XIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18"></line>
    <line x1="6" y1="6" x2="18" y2="18"></line>
  </svg>
);

type ParsedDescription = {
  main: string;
  inclusion: string;
  exclusion: string;
};

function parseConditionDescription(description: string): ParsedDescription {
  const normalized = (description || '').replace(/\r\n/g, '\n').trim();
  if (!normalized) return { main: '', inclusion: '', exclusion: '' };

  const inclusionMatch = normalized.match(/\bInclusions?:/i);
  const exclusionMatch = normalized.match(/\bExclusions?:/i);

  const firstMarkerIndex = [inclusionMatch?.index, exclusionMatch?.index]
    .filter((index): index is number => index != null)
    .sort((a, b) => a - b)[0];

  const main = (firstMarkerIndex == null ? normalized : normalized.slice(0, firstMarkerIndex)).trim();

  let inclusion = '';
  if (inclusionMatch?.index != null) {
    const start = inclusionMatch.index + inclusionMatch[0].length;
    const end = exclusionMatch?.index != null && exclusionMatch.index > inclusionMatch.index
      ? exclusionMatch.index
      : normalized.length;
    inclusion = normalized.slice(start, end).trim();
  }

  let exclusion = '';
  if (exclusionMatch?.index != null) {
    const start = exclusionMatch.index + exclusionMatch[0].length;
    exclusion = normalized.slice(start).trim();
  }

  return { main, inclusion, exclusion };
}

/* ─────────────────────────────────────────────
   Loading / status animation component
───────────────────────────────────────────── */
interface LoadingScreenProps {
  status: ServiceStatus | null;
  error: string | null;
  onRetry: () => void;
}

function LoadingScreen({ status, error, onRetry }: LoadingScreenProps) {
  const [dots, setDots] = useState('');
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setDots(d => d.length >= 3 ? '' : d + '.'), 500);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const t = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(t);
  }, []);

  if (error) {
    return (
      <div className="wp-loading-screen">
        <div className="wp-loading-error-icon">⚠</div>
        <h3 className="wp-loading-title">Service unavailable</h3>
        <p className="wp-loading-sub">{error}</p>
        <button className="wp-btn-primary" onClick={onRetry} style={{ marginTop: 24 }}>
          <RefreshIcon /> Retry
        </button>
      </div>
    );
  }

  const isConnecting = !status;
  const phase = isConnecting
    ? 'Connecting to semantic service…'
    : status?.status === 'loading'
      ? 'Pellet is reasoning over the ontology…'
      : 'Finalising…';

  return (
    <div className="wp-loading-screen">
      {/* Static larger logo loader */}
      <div className="wp-loading-orb">
        <div className="wp-orb-logo-container">
          <img src="/logo-rientra.png" alt="Loading" className="wp-orb-logo-img" />
        </div>
      </div>

      <h3 className="wp-loading-title">
        {isConnecting ? `Waiting for service${dots}` : `Reasoning${dots}`}
      </h3>
      <p className="wp-loading-phase">{phase}</p>

      {/* Stats row */}
      {status?.stats && (
        <div className="wp-loading-stats">
          <div className="wp-loading-stat">
            <span className="wp-loading-stat-val">{status.stats.classes}</span>
            <span className="wp-loading-stat-lbl">Classes</span>
          </div>
          <div className="wp-loading-stat">
            <span className="wp-loading-stat-val">{status.stats.individuals}</span>
            <span className="wp-loading-stat-lbl">Individuals</span>
          </div>
          <div className="wp-loading-stat">
            <span className="wp-loading-stat-val">{status.stats.properties}</span>
            <span className="wp-loading-stat-lbl">Properties</span>
          </div>
        </div>
      )}

      {/* Progress bar — indeterminate */}
      <div className="wp-loading-bar-track">
        <div className="wp-loading-bar-fill" />
      </div>

      <p className="wp-loading-elapsed">
        {elapsed}s elapsed
        {status?.elapsed_pellet ? ` · Pellet took ${status.elapsed_pellet.toFixed(1)}s` : ''}
      </p>

      <p className="wp-loading-hint">
        This runs once per session — subsequent queries are instant.
      </p>
    </div>
  );
}

/* ─────────────────────────────────────────────
   Types & props
───────────────────────────────────────────── */
interface WorkersPageProps {
  onNavigateHome: () => void;
  initialNav?: 'workers' | 'jobs-analysis' | 'jobs-positions';
}

/* ─────────────────────────────────────────────
   Main component
───────────────────────────────────────────── */
export default function WorkersPage({ onNavigateHome, initialNav = 'workers' }: WorkersPageProps) {
  // ── service state ──────────────────────────────────────────────────
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── data state ─────────────────────────────────────────────────────
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [loadingWorkers, setLoadingWorkers] = useState(false);
  const [selectedWorker, setSelectedWorker] = useState<Worker | null>(null);
  
  const [archivedWorkerIds, setArchivedWorkerIds] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem('archivedWorkers');
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch {
      return new Set();
    }
  });

  useEffect(() => {
    localStorage.setItem('archivedWorkers', JSON.stringify(Array.from(archivedWorkerIds)));
  }, [archivedWorkerIds]);
  const [conditions, setConditions] = useState<HealthCondition[]>([]);
  const [loadingConditions, setLoadingConditions] = useState(false);

  // ── UI state ───────────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState('');
  const [conditionSearchQuery, setConditionSearchQuery] = useState('');
  const [dotsMenuOpen, setDotsMenuOpen] = useState(false);
  const [coreSetFilterOpen, setCoreSetFilterOpen] = useState(false);
  const [selectedCoreSets, setSelectedCoreSets] = useState<string[]>([]);
  const [allCoreSets, setAllCoreSets] = useState<string[]>([]);
  const [activeNav] = useState<'workers' | 'jobs-analysis' | 'jobs-positions'>(initialNav);
  const [expandedConditionCode, setExpandedConditionCode] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'active' | 'archived'>('active');
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  const [switchingWorkerId, setSwitchingWorkerId] = useState<string | null>(null);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [healthWizardStep, setHealthWizardStep] = useState<'select' | 'review' | 'saving' | 'done'>('select');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // ── Import modal state ────────────────────────────────────────────────────
  type ImportPhase = 'idle' | 'picking' | 'uploading' | 'done' | 'error';
  const [importPhase, setImportPhase] = useState<ImportPhase>('idle');
  const [importResult, setImportResult] = useState<ImportWorkersResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importModalOpen, setImportModalOpen] = useState(false);

  // ── Click outside / Escape logic for dropdown ──
  const coreSetDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (coreSetFilterOpen && coreSetDropdownRef.current && !coreSetDropdownRef.current.contains(event.target as Node)) {
        setCoreSetFilterOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (coreSetFilterOpen && event.key === 'Escape') {
        setCoreSetFilterOpen(false);
      }
    }

    if (coreSetFilterOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [coreSetFilterOpen]);
  // ── Table sort state ───────────────────────────────────────────────
  // icf_code cycles: 'b' → 'd' → removed
  // name / eff_qualifier cycle: 'asc' → 'desc' → removed
  type SortCol = 'icf_code' | 'name' | 'eff_qualifier';
  type SortDir = 'asc' | 'desc' | 'b-first' | 'd-first';
  type SortRule = { col: SortCol; dir: SortDir };
  const [sortRules, setSortRules] = useState<SortRule[]>([]);

  const handleSort = (col: SortCol) => {
    setSortRules(prev => {
      const existing = prev.find(rule => rule.col === col);
      const cycle = col === 'icf_code'
        ? ['b-first', 'd-first', null] as const
        : ['asc', 'desc', null] as const;
      const currentIndex = existing ? cycle.indexOf(existing.dir as any) : -1;
      const next = cycle[(currentIndex + 1) % cycle.length];

      if (next === null) {
        return prev.filter(rule => rule.col !== col);
      }

      const remainingRules = prev.filter(rule => rule.col !== col);
      return [{ col, dir: next }, ...remainingRules];
    });
  };

  const compareConditions = (a: HealthCondition, b: HealthCondition, rule: SortRule) => {
    if (rule.col === 'icf_code') {
      const prefix = rule.dir === 'b-first' ? 'b' : 'd';
      const aP = a.icf_code.toLowerCase().startsWith(prefix) ? 0 : 1;
      const bP = b.icf_code.toLowerCase().startsWith(prefix) ? 0 : 1;
      if (aP !== bP) return aP - bP;
      return a.icf_code.localeCompare(b.icf_code);
    }

    if (rule.col === 'name') {
      const dir = rule.dir === 'asc' ? 1 : -1;
      return dir * (a.icf_name || '').localeCompare(b.icf_name || '');
    }

    const dir = rule.dir === 'asc' ? 1 : -1;
    const effA = Math.max(a.bf_qualifier ?? 0, a.ap1_qualifier ?? 0);
    const effB = Math.max(b.bf_qualifier ?? 0, b.ap1_qualifier ?? 0);
    return dir * (effA - effB);
  };

  const sortedConditions = [...conditions].sort((a, b) => {
    for (const rule of sortRules) {
      const result = compareConditions(a, b, rule);
      if (result !== 0) return result;
    }
    return 0;
  });

  const sortIcon = (col: SortCol) => {
    const ruleIndex = sortRules.findIndex(rule => rule.col === col);
    if (ruleIndex === -1) return <span className="wp-sort-icon">⇅</span>;

    const rule = sortRules[ruleIndex];
    const label = col === 'icf_code'
      ? (rule.dir === 'b-first' ? 'b' : 'd')
      : (rule.dir === 'asc' ? '↑' : '↓');

    return <span className="wp-sort-badge">{`${label}${ruleIndex + 1}`}</span>;
  };

  // All available core set labels — fetched from API, not derived from conditions
  const availableCoreSets = allCoreSets;

  const filteredConditions = sortedConditions.filter(c => {
    const q = conditionSearchQuery.toLowerCase();
    const matchesSearch = (
      c.icf_code.toLowerCase().includes(q) ||
      (c.icf_name || '').toLowerCase().includes(q) ||
      (c.core_sets || []).join(' ').toLowerCase().includes(q)
    );
    const matchesFilter =
      selectedCoreSets.length === 0 ||
      selectedCoreSets.every(cs => (c.core_sets || []).includes(cs));
    const icfSortRule = sortRules.find(rule => rule.col === 'icf_code');
    const matchesIcfPrefix =
      !icfSortRule ||
      c.icf_code.toLowerCase().startsWith(icfSortRule.dir === 'b-first' ? 'b' : 'd');
    return matchesSearch && matchesFilter && matchesIcfPrefix;
  });


  // ── Polling /status until ready ────────────────────────────────────
  const poll = useCallback(async () => {
    try {
      const s = await fetchStatus();
      setServiceStatus(s);
      setServiceError(null);
      if (s.status === 'ready') {
        setIsReady(true);
        return; // stop polling
      }
      if (s.status === 'error') {
        setServiceError(s.message);
        return;
      }
      // still loading — poll again in 2.5s
      pollRef.current = setTimeout(poll, 2500);
    } catch (err) {
      // service not yet reachable (still booting) — retry faster
      pollRef.current = setTimeout(poll, 1500);
    }
  }, []);

  useEffect(() => {
    poll();
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, [poll]);

  // ── Fetch workers once service is ready ────────────────────────────
  useEffect(() => {
    if (!isReady) return;
    setLoadingWorkers(true);
    fetchWorkers()
      .then(setWorkers)
      .catch(e => console.error('fetchWorkers:', e))
      .finally(() => setLoadingWorkers(false));
    // Also fetch all available core set labels once (for the filter dropdown)
    fetchCoreSets()
      .then(setAllCoreSets)
      .catch(e => console.error('fetchCoreSets:', e));
  }, [isReady]);

  // ── Fetch health conditions when a worker is selected ──────────────
  useEffect(() => {
    if (!selectedWorker) return;
    setConditions([]);
    setExpandedConditionCode(null);
    setLoadingConditions(true);
    fetchHealthConditions(selectedWorker.id)
      .then(r => setConditions(r.conditions))
      .catch(e => console.error('fetchHealthConditions:', e))
      .finally(() => setLoadingConditions(false));
  }, [selectedWorker]);

  const toggleArchiveStatus = (workerId: string) => {
    setArchivedWorkerIds(prev => {
      const next = new Set(prev);
      if (next.has(workerId)) {
        next.delete(workerId);
      } else {
        next.add(workerId);
      }
      return next;
    });
  };

  // ── Filtered worker list ───────────────────────────────────────────
  const activeWorkers = workers.filter(w => !archivedWorkerIds.has(w.id));
  const archivedWorkersList = workers.filter(w => archivedWorkerIds.has(w.id));
  const displayedWorkers = activeTab === 'active' ? activeWorkers : archivedWorkersList;

  const filteredWorkers = displayedWorkers.filter(w => {
    const q = searchQuery.toLowerCase();
    return (
      w.id.toLowerCase().includes(q) ||
      w.first_name.toLowerCase().includes(q) ||
      w.surname.toLowerCase().includes(q)
    );
  });

  const displayName = (w: Worker) =>
    [w.first_name, w.surname].filter(Boolean).join(' ') || w.id;

  // Await the selection API so the ontology is flipped BEFORE JobAnalysisView
  // fires its /match request. Without this, the SPARQL FILTER(?selected = true)
  // would still point to the old worker and return empty results.
  const handleSelectWorker = async (w: Worker) => {
    if (w.id === selectedWorker?.id || switchingWorkerId) return;
    setSwitchingWorkerId(w.id);
    try {
      await selectWorker(w.id);   // POST /workers/select — flips isSelected
      // Optimistically update the is_selected flag in the local list
      setWorkers(prev =>
        prev.map(x => ({ ...x, is_selected: x.id === w.id }))
      );
      setSelectedWorker({ ...w, is_selected: true });
    } catch (e) {
      console.error('selectWorker failed:', e);
      // Even on API error, still show the worker (health tab works fine;
      // Job Analysis will display its own error message if /match fails).
      setSelectedWorker(w);
    } finally {
      setSwitchingWorkerId(null);
    }
  };


  // ── Add Worker: open native dialog → upload SQL → reload workers ───────
  const handleAddWorker = async () => {
    if (importPhase === 'uploading') return;

    // 1. Open native file dialog via Electron IPC
    const electronAPI = (window as any).electronAPI;
    if (!electronAPI?.showOpenDialog) {
      setImportError('File dialog not available (Electron API missing).');
      setImportModalOpen(true);
      return;
    }

    setImportPhase('picking');
    setImportModalOpen(true);
    setImportResult(null);
    setImportError(null);

    const dialogResult = await electronAPI.showOpenDialog({
      title: 'Select SQL Dataset',
      filters: [{ name: 'SQL Files', extensions: ['sql'] }],
      properties: ['openFile'],
    });

    if (dialogResult.canceled || !dialogResult.filePaths?.length) {
      setImportPhase('idle');
      setImportModalOpen(false);
      return;
    }

    const filePath = dialogResult.filePaths[0];
    const fileName = filePath.split('/').pop() || 'dataset.sql';

    // 2. Read file bytes via Electron IPC
    setImportPhase('uploading');
    const readResult = await electronAPI.readFileBuffer(filePath);
    if (!readResult.ok) {
      setImportError(`Cannot read file: ${readResult.error}`);
      setImportPhase('error');
      return;
    }

    // 3. Upload to Python service
    try {
      const result = await importWorkers(readResult.data as number[], fileName);
      setImportResult(result);
      setImportPhase('done');

      // 4. Reload worker list
      if (result.persons_added > 0) {
        fetchWorkers()
          .then(setWorkers)
          .catch(e => console.error('fetchWorkers after import:', e));
      }
    } catch (err: any) {
      setImportError(err?.message ?? 'Import failed.');
      setImportPhase('error');
    }
  };


  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div className="wp-page">
      <div className="bg-blob bg-blob-1" />
      <div className="bg-blob bg-blob-2" />
      <div className="bg-blob bg-blob-3" />

      {/* ── Top Navigation Bar ── */}
      <nav className="wp-navbar">
        <div className="wp-nav-brand-container">
          {!isSidebarOpen && (
            <button
              className="wp-nav-home-btn"
              style={{ marginRight: '16px', padding: '6px 8px' }}
              onClick={() => setIsSidebarOpen(true)}
              aria-label="Open sidebar"
            >
              <ListIcon />
            </button>
          )}
          <div className="wp-nav-brand" onClick={onNavigateHome} role="button" tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && onNavigateHome()}>
            <img src="/logo-rientra.png" alt="Rientra Logo" className="wp-nav-logo" />
            <span className="wp-nav-title">RIENTR@</span>
          </div>
        </div>
        <div className="wp-breadcrumbs-container">
          <button
            className="wp-breadcrumb-back-btn"
            onClick={onNavigateHome}
            aria-label="Back to Home"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"></line>
              <polyline points="12 19 5 12 12 5"></polyline>
            </svg>
          </button>
          <div className="wp-breadcrumbs-box">
          {(() => {
            const navTitle = activeNav === 'workers' ? 'Worker Information' : activeNav === 'jobs-analysis' ? 'Job Analysis' : 'Job Positions';
            const breadcrumbItems = [];
            breadcrumbItems.push({ label: 'Home', onClick: onNavigateHome });
            breadcrumbItems.push({ label: navTitle, onClick: isWizardOpen ? () => setIsWizardOpen(false) : undefined });
            if (activeNav === 'workers' && isWizardOpen) {
              breadcrumbItems.push({ label: 'Modify Health Conditions' });
            }
            if (activeNav === 'workers' && isWizardOpen && healthWizardStep === 'review') {
              breadcrumbItems.push({ label: 'Assign Points & Review Changes' });
            }

            return breadcrumbItems.map((item, index) => {
              const isCurrent = index === breadcrumbItems.length - 1;
              const isLastBeforeCurrent = index === breadcrumbItems.length - 2;

              return (
                <span key={index} className="wp-breadcrumb-segment">
                  <span
                    className={`wp-breadcrumb-text ${isCurrent ? 'current' : ''} ${isLastBeforeCurrent ? 'last-before-current' : ''}`}
                    onClick={item.onClick}
                    role={item.onClick ? "button" : undefined}
                    tabIndex={item.onClick ? 0 : undefined}
                  >
                    {item.label}
                  </span>
                  {!isCurrent && (
                    <span className="wp-breadcrumb-separator">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="9 18 15 12 9 6"></polyline>
                      </svg>
                    </span>
                  )}
                </span>
              );
            });
          })()}
          </div>
        </div>

        {/* Service status pill */}
        <div className={`wp-service-badge wp-service-badge--${serviceStatus?.status ?? 'loading'}`}>
          <span className="wp-service-dot" />
          {serviceStatus?.status === 'ready'
            ? 'Online'
            : serviceStatus?.status === 'error'
              ? 'Error'
              : 'Starting…'}
        </div>
      </nav>

      {/* ── Body ── */}
      <div className="wp-body">

        {/* ── Left Sidebar ── */}
        <aside className={`wp-sidebar ${isSidebarOpen ? '' : 'wp-sidebar--closed'}`}>
          <div className="wp-sidebar-header">
            <span className="wp-sidebar-title">Workers</span>
            <button className="wp-icon-button" onClick={() => setIsSidebarOpen(false)} aria-label="Close sidebar">
              <ListIcon />
            </button>
          </div>
          <div className="wp-search-wrapper">
            <span className="wp-search-icon"><SearchIcon /></span>
            <input id="worker-search" type="text" className="wp-search-input"
              placeholder="Search by ID number" value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onFocus={() => setIsSearchFocused(true)}
              onBlur={() => setIsSearchFocused(false)} />
            {searchQuery.length > 0 ? (
              <span className="wp-search-action-icon" onMouseDown={(e) => { e.preventDefault(); setSearchQuery(''); }}>
                <XIcon />
              </span>
            ) : isSearchFocused ? (
              <span className="wp-search-action-icon">
                <ArrowRightIcon />
              </span>
            ) : null}
          </div>

          <div className="wp-archive-toggle">
            <button
              className={`wp-toggle-btn ${activeTab === 'active' ? 'active' : ''}`}
              onClick={() => setActiveTab('active')}
            >
              Active ({activeWorkers.length})
            </button>
            <button
              className={`wp-toggle-btn ${activeTab === 'archived' ? 'active' : ''}`}
              onClick={() => setActiveTab('archived')}
            >
              <ArchiveIcon /> Archived ({archivedWorkersList.length})
            </button>
          </div>

          <div className="wp-sidebar-col-label">ID Number</div>

          <ul className="wp-worker-list" id="worker-list">
            {loadingWorkers && (
              <li className="wp-worker-item wp-worker-item--skeleton" aria-label="loading">
                <span className="wp-skeleton-line" />
              </li>
            )}
            {!loadingWorkers && filteredWorkers.map(w => {
              const isSwitching = switchingWorkerId === w.id;
              return (
                <li key={w.id}
                  className={`wp-worker-item ${selectedWorker?.id === w.id ? 'selected' : ''} ${isSwitching ? 'wp-worker-item--switching' : ''}`}
                  onClick={() => handleSelectWorker(w)}
                  role="button" tabIndex={0}
                  aria-busy={isSwitching}
                  onKeyDown={e => e.key === 'Enter' && handleSelectWorker(w)}>
                  {isSwitching
                    ? <span className="wp-worker-switching-label">{displayName(w)}<span className="wp-worker-switching-dot" /></span>
                    : displayName(w)
                  }
                </li>
              );
            })}

            {!loadingWorkers && isReady && filteredWorkers.length === 0 && (
              <li className="wp-worker-item wp-worker-item--empty">
                {activeTab === 'archived' && searchQuery.length === 0 ? 'No archived workers' : 'No results'}
              </li>
            )}
          </ul>

          <button
            className="wp-add-btn"
            id="btn-add-worker"
            onClick={handleAddWorker}
            disabled={importPhase === 'uploading'}
          >
            {importPhase === 'uploading'
              ? <><span className="wp-spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Importing…</>
              : <><PlusIcon /> Add Worker</>
            }
          </button>
        </aside>

        {/* ── Main Panel ── */}
        <main className="wp-main">
          <div className="wp-panel">

            {/* ── Loading / Error screen ── */}
            {!isReady ? (
              <LoadingScreen
                status={serviceStatus}
                error={serviceError}
                onRetry={() => { setServiceError(null); poll(); }}
              />
            ) : selectedWorker ? (
              /* ── Selected worker view ── */
              <div key={activeNav} className="wp-content-fade">
                {/* ── Jobs Analysis nav: show JobAnalysisView (no tab bar) ── */}
                {activeNav === 'jobs-analysis' ? (
                  <div className="wp-section" style={{ gap: 0, padding: 0 }}>
                    <JobAnalysisView
                      workerId={selectedWorker.id}
                      workerDisplayName={
                        [selectedWorker.first_name, selectedWorker.surname].filter(Boolean).join(' ')
                        || selectedWorker.id
                      }
                    />
                  </div>
                ) : (
                  /* ── Workers nav: Health Conditions only ── */
                  <>
                    {/* Worker header — hidden when Wizard is active */}
                    {!isWizardOpen && (
                      <div className="wp-worker-header">
                        <div className="wp-worker-id">
                          <span className="wp-worker-id-label">ID Number:</span>
                          <span className="wp-worker-id-value">{selectedWorker.id}</span>
                        </div>
                        <div className="wp-worker-meta" style={{ flex: 1 }}>
                          {(selectedWorker.first_name || selectedWorker.surname) && (
                            <span>
                              Name: <strong>
                                {[selectedWorker.first_name, selectedWorker.surname].filter(Boolean).join(' ')}
                              </strong>
                            </span>
                          )}
                          <span>Jobs evaluated: <strong>{selectedWorker.evaluated_for_jobs.length}</strong></span>
                        </div>
                        <button
                          className="wp-btn-secondary"
                          onClick={() => toggleArchiveStatus(selectedWorker.id)}
                          style={{ alignSelf: 'center', display: 'flex', alignItems: 'center', gap: '6px' }}
                        >
                          <ArchiveIcon />
                          {archivedWorkerIds.has(selectedWorker.id) ? 'Unarchive Worker' : 'Archive Worker'}
                        </button>
                      </div>
                    )}

                    {/* Health Conditions */}
                    {isWizardOpen ? (
                      <div className="wp-section wp-section--wizard">
                        <HealthConditionWizard
                          workerId={selectedWorker.id}
                          currentConditions={conditions}
                          allCoreSets={allCoreSets}
                          onClose={() => {
                            setIsWizardOpen(false);
                            setHealthWizardStep('select');
                          }}
                          onSaved={() => {
                            setLoadingConditions(true);
                            fetchHealthConditions(selectedWorker.id)
                              .then(r => setConditions(r.conditions))
                              .catch(e => console.error('fetchHealthConditions:', e))
                              .finally(() => setLoadingConditions(false));
                          }}
                          onStepChange={setHealthWizardStep}
                        />
                      </div>
                    ) : (
                      <div className="wp-section">
                        <div className="wp-section-header">
                          <h2 className="wp-section-title">Current Health Conditions</h2>

                          <div className="wp-search-wrapper" style={{ flex: 1, maxWidth: 300, marginBottom: 0 }}>
                            <span className="wp-search-icon"><SearchIcon /></span>
                            <input type="text" className="wp-search-input"
                              placeholder="Search conditions..." value={conditionSearchQuery}
                              onChange={e => setConditionSearchQuery(e.target.value)} />
                          </div>

                          {/* Core Set filter dropdown */}
                          <div className="wp-dots-wrapper" style={{ position: 'relative' }} ref={coreSetDropdownRef}>
                            <button
                              className={`wp-btn-dots ${coreSetFilterOpen || selectedCoreSets.length > 0 ? 'active' : ''}`}
                              id="btn-coreset-filter"
                              onClick={() => setCoreSetFilterOpen(v => !v)}
                              aria-label="Filter by Core Set"
                              title="Filter by Core Set"
                              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', width: 'auto' }}
                            >
                              <FilterIcon />
                              <span style={{ fontSize: '0.8rem', fontWeight: 500 }}>Core Set</span>
                              {selectedCoreSets.length > 0 && (
                                <span style={{
                                  background: '#4DD9C0', color: '#0f2233', borderRadius: '99px',
                                  fontSize: '0.7rem', fontWeight: 700, padding: '1px 7px', marginLeft: 2
                                }}>{selectedCoreSets.length}</span>
                              )}
                            </button>
                            {coreSetFilterOpen && (
                              <div className="wp-dropdown" id="coreset-filter-dropdown" style={{ minWidth: 260, maxHeight: 340, overflowY: 'auto' }}>
                                <div style={{ padding: '6px 12px 4px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Filter by Core Set</span>
                                  {selectedCoreSets.length > 0 && (
                                    <button
                                      onClick={() => setSelectedCoreSets([])}
                                      style={{ background: 'none', border: 'none', color: '#4DD9C0', cursor: 'pointer', fontSize: '0.75rem', padding: 0 }}
                                    >Clear all</button>
                                  )}
                                </div>
                                <div style={{ height: 1, background: 'rgba(255,255,255,0.08)', margin: '4px 0' }} />
                                {availableCoreSets.length === 0 ? (
                                  <div style={{ padding: '10px 12px', color: 'rgba(255,255,255,0.4)', fontSize: '0.82rem' }}>No core sets available</div>
                                ) : (
                                  availableCoreSets.map(cs => {
                                    const checked = selectedCoreSets.includes(cs);
                                    return (
                                      <button
                                        key={cs}
                                        className="wp-dropdown-item"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setSelectedCoreSets(prev =>
                                            checked ? prev.filter(x => x !== cs) : [...prev, cs]
                                          );
                                        }}
                                        style={{ display: 'flex', alignItems: 'center', gap: 10 }}
                                      >
                                        <span style={{
                                          width: 16, height: 16, borderRadius: 4, flexShrink: 0,
                                          border: `2px solid ${checked ? '#4DD9C0' : 'rgba(255,255,255,0.3)'}`,
                                          background: checked ? '#4DD9C0' : 'transparent',
                                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                                          transition: 'all 0.15s',
                                          pointerEvents: 'none',
                                        }}>
                                          {checked && (
                                            <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                                              <polyline points="2 6 5 9 10 3" stroke="#0f2233" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                            </svg>
                                          )}
                                        </span>
                                        <span style={{ fontSize: '0.82rem' }}>{cs}</span>
                                      </button>
                                    );
                                  })
                                )}
                              </div>
                            )}
                          </div>

                          <div className="wp-section-actions">
                            <button className="wp-btn-primary" id="btn-modify-health" onClick={() => {
                              setHealthWizardStep('select');
                              setIsWizardOpen(true);
                            }}>
                              <EditIcon /> Modify Health Conditions
                            </button>
                            <div className="wp-dots-wrapper">
                              <button className={`wp-btn-dots ${dotsMenuOpen ? 'active' : ''}`}
                                id="btn-overflow-menu"
                                onClick={() => setDotsMenuOpen(v => !v)}
                                aria-label="More options">
                                <DotsIcon />
                              </button>
                              {dotsMenuOpen && (
                                <div className="wp-dropdown" id="overflow-dropdown">
                                  <button className="wp-dropdown-item" id="btn-save-pdf"
                                    onClick={() => setDotsMenuOpen(false)}>
                                    <PdfIcon /> Save PDF
                                  </button>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="wp-table-wrapper" style={{ position: 'relative' }}>
                          {loadingConditions && conditions.length > 0 && (
                            <div className="wp-table-loading" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(26, 42, 74, 0.4)', zIndex: 10 }}>
                              <div className="wp-spinner" />
                            </div>
                          )}
                          {loadingConditions && conditions.length === 0 ? (
                            <div className="wp-table-loading">
                              <div className="wp-spinner" />
                              <span>Loading health conditions…</span>
                            </div>
                          ) : (
                            <table className="wp-table" id="health-conditions-table" style={{ opacity: loadingConditions ? 0.6 : 1, transition: 'opacity 0.2s' }}>
                              <colgroup>
                                <col style={{ width: '15%' }} />
                                <col style={{ width: '40%' }} />
                                <col style={{ width: '30%' }} />
                                <col style={{ width: '15%' }} />
                              </colgroup>
                              <thead>
                                <tr>
                                  <th
                                    className={`wp-th-sortable${sortRules.some(rule => rule.col === 'icf_code') ? ' wp-th-sorted' : ''}`}
                                    onClick={() => handleSort('icf_code')}
                                    title="Sort by ICF Code (cycles: b first → d first → unsorted)"
                                  >
                                    ICF Code {sortIcon('icf_code')}
                                  </th>
                                  <th
                                    className={`wp-th-sortable${sortRules.some(rule => rule.col === 'name') ? ' wp-th-sorted' : ''}`}
                                    onClick={() => handleSort('name')}
                                    title="Sort by Code Name"
                                  >
                                    Code Name {sortIcon('name')}
                                  </th>
                                  <th>Core Set</th>
                                  <th
                                    className={`wp-th-sortable${sortRules.some(rule => rule.col === 'eff_qualifier') ? ' wp-th-sorted' : ''}`}
                                    onClick={() => handleSort('eff_qualifier')}
                                    title="Sort by Qualifier"
                                  >
                                    Qualifier {sortIcon('eff_qualifier')}
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {filteredConditions.map((c, i) => {
                                  const eff = Math.max(c.bf_qualifier ?? 0, c.ap1_qualifier ?? 0);
                                  const isExpanded = expandedConditionCode === c.icf_code;
                                  const parsedDescription = parseConditionDescription(c.description || '');
                                  return [
                                    <tr
                                      key={`${c.icf_code}-${i}`}
                                      className={`wp-condition-row${isExpanded ? ' is-expanded' : ''}`}
                                      onClick={() => setExpandedConditionCode(prev => prev === c.icf_code ? null : c.icf_code)}
                                    >
                                      <td>
                                        <div className="wp-icf-code-cell">
                                          <span className={`wp-row-expander-arrow${isExpanded ? ' is-expanded' : ''}`} aria-hidden="true">
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                              <polyline points="6 9 12 15 18 9"></polyline>
                                            </svg>
                                          </span>
                                          <span className="wp-icf-code">{c.icf_code}</span>
                                        </div>
                                      </td>
                                      <td>
                                        <div className="wp-icf-name-cell">
                                          <span className="wp-icf-name">{c.icf_name || '—'}</span>
                                        </div>
                                      </td>
                                      <td><span className="wp-icf-category" style={{ fontSize: '0.75rem', opacity: 0.8 }}>{(c.core_sets || []).join(', ') || '—'}</span></td>
                                      <td>
                                        <span className={`wp-qualifier-badge wp-qualifier-badge--eff wp-eff-${eff}`}>
                                          {eff}
                                        </span>
                                      </td>
                                    </tr>,
                                    isExpanded ? (
                                      <tr key={`${c.icf_code}-${i}-detail`} className="wp-condition-detail-row">
                                        <td />
                                        <td colSpan={1}>
                                          <div className="wp-condition-description">
                                            {c.description ? (
                                              <>
                                                {parsedDescription.main && (
                                                  <p className="wp-condition-description-main">{parsedDescription.main}</p>
                                                )}
                                                {parsedDescription.inclusion && (
                                                  <div className="wp-condition-description-section">
                                                    <div className="wp-condition-description-label">Inclusion</div>
                                                    <p className="wp-condition-description-text">{parsedDescription.inclusion}</p>
                                                  </div>
                                                )}
                                                {parsedDescription.exclusion && (
                                                  <div className="wp-condition-description-section">
                                                    <div className="wp-condition-description-label">Exclusion</div>
                                                    <p className="wp-condition-description-text">{parsedDescription.exclusion}</p>
                                                  </div>
                                                )}
                                              </>
                                            ) : (
                                              'No ontology description available for this ICF code.'
                                            )}
                                          </div>
                                        </td>
                                        <td />
                                        <td />
                                      </tr>
                                    ) : null,
                                  ];
                                })}
                              </tbody>
                            </table>
                          )}

                          {!loadingConditions && conditions.length === 0 && (
                            <div className="wp-table-empty visible">
                              <p>No health conditions recorded for this worker.</p>
                              <p className="wp-table-empty-hint">
                                Data is loaded from the ontology — ensure this worker has
                                <code> isInHealthCondition</code> triples.
                              </p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>

            ) : (
              /* ── No worker selected ── */
              <div className="wp-empty-state">
                {activeTab === 'archived' && archivedWorkersList.length === 0 ? (
                  <>
                    <div className="wp-empty-icon" style={{ opacity: 0.9 }}>
                      <div style={{
                        width: 64, height: 64,
                        backgroundColor: 'rgba(77,217,192,0.8)',
                        maskImage: 'url(/Vector.png)',
                        maskSize: 'contain',
                        maskRepeat: 'no-repeat',
                        maskPosition: 'center',
                        WebkitMaskImage: 'url(/Vector.png)',
                        WebkitMaskSize: 'contain',
                        WebkitMaskRepeat: 'no-repeat',
                        WebkitMaskPosition: 'center'
                      }} />
                    </div>
                    <h3 className="wp-empty-title">
                      No workers are archived yet!
                    </h3>
                    <p className="wp-empty-subtitle">
                      To archive a worker, open their information screen, click the Archive button.
                    </p>
                  </>
                ) : (
                  <>
                    <div className="wp-empty-icon" style={{ opacity: 0.9 }}>
                      <div style={{
                        width: 64, height: 64,
                        backgroundColor: 'rgba(77,217,192,0.8)',
                        maskImage: 'url(/User_scan_fill.png)',
                        maskSize: 'contain',
                        maskRepeat: 'no-repeat',
                        maskPosition: 'center',
                        WebkitMaskImage: 'url(/User_scan_fill.png)',
                        WebkitMaskSize: 'contain',
                        WebkitMaskRepeat: 'no-repeat',
                        WebkitMaskPosition: 'center'
                      }} />
                    </div>
                    <h3 className="wp-empty-title">
                      {workers.length === 0 ? 'No workers in ontology' : 'No worker selected'}
                    </h3>
                    <p className="wp-empty-subtitle">
                      {workers.length === 0
                        ? 'The ontology does not contain any Person individuals with job evaluations.'
                        : 'Select a worker from the list on the left to view their health conditions.'}
                    </p>
                  </>
                )}
              </div>
            )}
          </div>
        </main>
      </div>

      {/* ── Import Workers Modal ── */}
      {importModalOpen && (
        <div
          className="wp-modal-backdrop"
          onClick={() => {
            if (importPhase === 'done' || importPhase === 'error') {
              setImportModalOpen(false);
              setImportPhase('idle');
            }
          }}
        >
          <div className="wp-modal" onClick={e => e.stopPropagation()}>
            {/* Uploading */}
            {importPhase === 'uploading' && (
              <>
                <div className="wp-modal-icon">
                  <div className="wp-spinner" style={{ width: 40, height: 40, borderWidth: 3 }} />
                </div>
                <h3 className="wp-modal-title">Importing Dataset…</h3>
                <p className="wp-modal-sub">
                  Running R2RML pipeline. This may take a few seconds.
                </p>
              </>
            )}

            {/* Picking file */}
            {importPhase === 'picking' && (
              <>
                <div className="wp-modal-icon" style={{ fontSize: 40 }}>📂</div>
                <h3 className="wp-modal-title">Opening file dialog…</h3>
              </>
            )}

            {/* Success */}
            {importPhase === 'done' && importResult && (
              <>
                <div className="wp-modal-icon" style={{ fontSize: 36 }}>
                  {importResult.persons_added > 0 ? '✅' : 'ℹ️'}
                </div>
                <h3 className="wp-modal-title">
                  {importResult.persons_added > 0
                    ? `${importResult.persons_added} worker${importResult.persons_added > 1 ? 's' : ''} imported`
                    : 'No new workers to import'}
                </h3>
                <div className="wp-modal-stats">
                  {importResult.new_person_ids.length > 0 && (
                    <div className="wp-modal-stat-row">
                      <span>Added</span>
                      <span className="wp-modal-stat-val" style={{ color: '#4DD9C0' }}>
                        {importResult.new_person_ids.join(', ')}
                      </span>
                    </div>
                  )}
                  {importResult.skipped_ids.length > 0 && (
                    <div className="wp-modal-stat-row">
                      <span>Already present (skipped)</span>
                      <span className="wp-modal-stat-val">
                        {importResult.skipped_ids.join(', ')}
                      </span>
                    </div>
                  )}
                  <div className="wp-modal-stat-row">
                    <span>ICF descriptors valid</span>
                    <span className="wp-modal-stat-val">{importResult.icf_valid}</span>
                  </div>
                  {importResult.icf_skipped > 0 && (
                    <div className="wp-modal-stat-row">
                      <span>ICF codes not in ontology</span>
                      <span className="wp-modal-stat-val" style={{ color: '#f59e0b' }}>
                        {importResult.icf_skipped}
                      </span>
                    </div>
                  )}
                  <div className="wp-modal-stat-row">
                    <span>Job links valid</span>
                    <span className="wp-modal-stat-val">{importResult.jobs_valid}</span>
                  </div>
                  {importResult.jobs_skipped > 0 && (
                    <div className="wp-modal-stat-row">
                      <span>Unknown jobs skipped</span>
                      <span className="wp-modal-stat-val" style={{ color: '#f59e0b' }}>
                        {importResult.jobs_skipped}
                      </span>
                    </div>
                  )}
                </div>
                {importResult.persons_added > 0 && (
                  <p className="wp-modal-note">
                    The ontology has been updated. Restart the service or reload the app to run
                    the reasoner on the new data.
                  </p>
                )}
                <button
                  className="wp-btn-primary"
                  style={{ marginTop: 20, width: '100%' }}
                  onClick={() => { setImportModalOpen(false); setImportPhase('idle'); }}
                >
                  Close
                </button>
              </>
            )}

            {/* Error */}
            {importPhase === 'error' && (
              <>
                <div className="wp-modal-icon" style={{ fontSize: 36 }}>⚠️</div>
                <h3 className="wp-modal-title">Import failed</h3>
                <p className="wp-modal-sub" style={{ color: '#ef4444', wordBreak: 'break-word' }}>
                  {importError}
                </p>
                <button
                  className="wp-btn-primary"
                  style={{ marginTop: 20, width: '100%' }}
                  onClick={() => { setImportModalOpen(false); setImportPhase('idle'); }}
                >
                  Close
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
