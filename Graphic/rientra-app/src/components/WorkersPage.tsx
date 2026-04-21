import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import './WorkersPage.css';
import JobAnalysisView from './JobAnalysisView';
import {
  fetchStatus,
  fetchWorkers,
  fetchHealthConditions,
  fetchCoreSets,
  selectWorker,
  type ServiceStatus,
  type Worker,
  type HealthCondition,
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
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="21 8 21 21 3 21 3 8" /><rect x="1" y="3" width="22" height="5" />
    <line x1="10" y1="12" x2="14" y2="12" />
  </svg>
);
const PdfIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
  </svg>
);
const HomeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <polyline points="9 22 9 12 15 12 15 22" />
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
  const [serviceStatus, setServiceStatus]   = useState<ServiceStatus | null>(null);
  const [serviceError,  setServiceError]    = useState<string | null>(null);
  const [isReady,       setIsReady]         = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── data state ─────────────────────────────────────────────────────
  const [workers,          setWorkers]          = useState<Worker[]>([]);
  const [loadingWorkers,   setLoadingWorkers]   = useState(false);
  const [selectedWorker,   setSelectedWorker]   = useState<Worker | null>(null);
  const [conditions,       setConditions]       = useState<HealthCondition[]>([]);
  const [loadingConditions,setLoadingConditions]= useState(false);

  // ── UI state ───────────────────────────────────────────────────────
  const [searchQuery,          setSearchQuery]          = useState('');
  const [conditionSearchQuery, setConditionSearchQuery] = useState('');
  const [dotsMenuOpen,         setDotsMenuOpen]         = useState(false);
  const [coreSetFilterOpen,    setCoreSetFilterOpen]    = useState(false);
  const [selectedCoreSets,     setSelectedCoreSets]     = useState<string[]>([]);
  const [allCoreSets,          setAllCoreSets]          = useState<string[]>([]);
  const [activeNav,            setActiveNav]            = useState<'workers' | 'jobs-analysis' | 'jobs-positions'>(initialNav);

  const [switchingWorkerId,setSwitchingWorkerId] = useState<string | null>(null);
  const [isWizardOpen,     setIsWizardOpen]     = useState(false);
  const [isSidebarOpen,    setIsSidebarOpen]    = useState(true);

  // ── Table sort state ───────────────────────────────────────────────
  // icf_code cycles: 'b-asc' → 'b-desc' → 'd-asc' → 'd-desc' → null
  // name / eff_qualifier cycle: 'asc' → 'desc' → null
  type SortCol = 'icf_code' | 'name' | 'eff_qualifier' | null;
  type SortDir = 'asc' | 'desc' | 'b-asc' | 'b-desc' | 'd-asc' | 'd-desc' | null;
  const [sortCol, setSortCol] = useState<SortCol>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);

  const handleSort = (col: SortCol) => {
    if (col === 'icf_code') {
      if (sortCol !== 'icf_code') { setSortCol('icf_code'); setSortDir('b-asc'); return; }
      const cycle: SortDir[] = ['b-asc', 'b-desc', 'd-asc', 'd-desc', null];
      const next = cycle[(cycle.indexOf(sortDir) + 1) % cycle.length];
      setSortDir(next); if (next === null) setSortCol(null);
    } else {
      if (sortCol !== col) { setSortCol(col); setSortDir('asc'); return; }
      const cycle: SortDir[] = ['asc', 'desc', null];
      const next = cycle[(cycle.indexOf(sortDir) + 1) % cycle.length];
      setSortDir(next); if (next === null) setSortCol(null);
    }
  };

  const sortedConditions = [...conditions].sort((a, b) => {
    if (!sortCol || !sortDir) return 0;
    if (sortCol === 'icf_code') {
      const prefix = sortDir.startsWith('b') ? 'b' : 'd';
      const dir    = sortDir.endsWith('asc') ? 1 : -1;
      const aP = a.icf_code.toLowerCase().startsWith(prefix) ? 0 : 1;
      const bP = b.icf_code.toLowerCase().startsWith(prefix) ? 0 : 1;
      if (aP !== bP) return aP - bP;
      return dir * a.icf_code.localeCompare(b.icf_code);
    }
    if (sortCol === 'name') {
      const dir = sortDir === 'asc' ? 1 : -1;
      return dir * (a.icf_name || '').localeCompare(b.icf_name || '');
    }
    if (sortCol === 'eff_qualifier') {
      const dir = sortDir === 'asc' ? 1 : -1;
      const effA = Math.max(a.bf_qualifier ?? 0, a.ap1_qualifier ?? 0);
      const effB = Math.max(b.bf_qualifier ?? 0, b.ap1_qualifier ?? 0);
      return dir * (effA - effB);
    }
    return 0;
  });

  const sortIcon = (col: SortCol) => {
    if (col === 'icf_code') {
      type IcfDir = 'b-asc' | 'b-desc' | 'd-asc' | 'd-desc';
      const labels: Record<IcfDir, string> = { 'b-asc': 'b↑', 'b-desc': 'b↓', 'd-asc': 'd↑', 'd-desc': 'd↓' };
      return sortCol === 'icf_code' && sortDir && sortDir !== 'asc' && sortDir !== 'desc'
        ? <span className="wp-sort-badge">{labels[sortDir as IcfDir]}</span>
        : <span className="wp-sort-icon">⇅</span>;
    }
    if (sortCol === col) return <span className="wp-sort-badge">{sortDir === 'asc' ? '↑' : '↓'}</span>;
    return <span className="wp-sort-icon">⇅</span>;
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
      (c.core_sets || []).some(cs => selectedCoreSets.includes(cs));
    return matchesSearch && matchesFilter;
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
    setLoadingConditions(true);
    fetchHealthConditions(selectedWorker.id)
      .then(r => setConditions(r.conditions))
      .catch(e => console.error('fetchHealthConditions:', e))
      .finally(() => setLoadingConditions(false));
  }, [selectedWorker]);

  // ── Filtered worker list ───────────────────────────────────────────
  const filteredWorkers = workers.filter(w => {
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
        <div className="wp-breadcrumbs">
          {(() => {
            const navTitle = activeNav === 'workers' ? 'Worker Information' : activeNav === 'jobs-analysis' ? 'Job Analysis' : 'Job Positions';
            const breadcrumbItems = [];
            breadcrumbItems.push({ label: 'Home', onClick: onNavigateHome });
            breadcrumbItems.push({ label: navTitle, onClick: isWizardOpen ? () => setIsWizardOpen(false) : undefined });
            if (activeNav === 'workers' && isWizardOpen) {
              breadcrumbItems.push({ label: 'Modify Health Conditions' });
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

        {/* Service status pill */}
        <div className={`wp-service-badge wp-service-badge--${serviceStatus?.status ?? 'loading'}`}>
          <span className="wp-service-dot" />
          {serviceStatus?.status === 'ready'
            ? 'Online'
            : serviceStatus?.status === 'error'
              ? 'Error'
              : 'Starting…'}
        </div>

        <button className="wp-nav-home-btn" onClick={onNavigateHome} title="Back to Home" id="btn-home">
          <HomeIcon />
        </button>
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
              placeholder="Search" value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)} />
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
              <li className="wp-worker-item wp-worker-item--empty">No results</li>
            )}
          </ul>

          <button className="wp-add-btn" id="btn-add-worker">
            <PlusIcon /> Add Worker
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
                        <div className="wp-worker-meta">
                          {(selectedWorker.first_name || selectedWorker.surname) && (
                            <span>
                              Name: <strong>
                                {[selectedWorker.first_name, selectedWorker.surname].filter(Boolean).join(' ')}
                              </strong>
                            </span>
                          )}
                          <span>Jobs evaluated: <strong>{selectedWorker.evaluated_for_jobs.length}</strong></span>
                          <span className={`wp-selected-badge ${selectedWorker.is_selected ? 'active' : ''}`}>
                            {selectedWorker.is_selected ? '● Selected' : '○ Not selected'}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Health Conditions */}
                    {isWizardOpen ? (
                      <div className="wp-section wp-section--wizard">
                        <HealthConditionWizard
                          workerId={selectedWorker.id}
                          workerDisplayName={displayName(selectedWorker)}
                          currentConditions={conditions}
                          onClose={() => setIsWizardOpen(false)}
                          onSaved={() => {
                            setLoadingConditions(true);
                            fetchHealthConditions(selectedWorker.id)
                              .then(r => setConditions(r.conditions))
                              .catch(e => console.error('fetchHealthConditions:', e))
                              .finally(() => setLoadingConditions(false));
                          }}
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
                          <div className="wp-dots-wrapper" style={{ position: 'relative' }}>
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
                            <button className="wp-btn-primary" id="btn-modify-health" onClick={() => setIsWizardOpen(true)}>
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
                                  <button className="wp-dropdown-item" id="btn-archive"
                                    onClick={() => setDotsMenuOpen(false)}>
                                    <ArchiveIcon /> Move to archive
                                  </button>
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
                              <thead>
                                <tr>
                                  <th
                                    className={`wp-th-sortable${sortCol === 'icf_code' ? ' wp-th-sorted' : ''}`}
                                    onClick={() => handleSort('icf_code')}
                                    title="Sort by ICF Code (cycles: b↑ → b↓ → d↑ → d↓ → unsorted)"
                                  >
                                    ICF Code {sortIcon('icf_code')}
                                  </th>
                                  <th
                                    className={`wp-th-sortable${sortCol === 'name' ? ' wp-th-sorted' : ''}`}
                                    onClick={() => handleSort('name')}
                                    title="Sort by Name"
                                  >
                                    Name {sortIcon('name')}
                                  </th>
                                  <th>Core Set</th>
                                  <th>BF Qualifier</th>
                                  <th>AP1 Qualifier</th>
                                  <th
                                    className={`wp-th-sortable${sortCol === 'eff_qualifier' ? ' wp-th-sorted' : ''}`}
                                    onClick={() => handleSort('eff_qualifier')}
                                    title="Sort by Effective Qualifier"
                                  >
                                    Effective Qualifier {sortIcon('eff_qualifier')}
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {filteredConditions.map((c, i) => {
                                  const eff = Math.max(c.bf_qualifier ?? 0, c.ap1_qualifier ?? 0);
                                  return (
                                    <tr key={`${c.icf_code}-${i}`}>
                                      <td><span className="wp-icf-code">{c.icf_code}</span></td>
                                      <td><span className="wp-icf-name">{c.icf_name || '—'}</span></td>
                                      <td><span className="wp-icf-category" style={{ fontSize: '0.75rem', opacity: 0.8 }}>{(c.core_sets || []).join(', ') || '—'}</span></td>
                                      <td>
                                        {c.bf_qualifier != null
                                          ? <span className="wp-qualifier-badge">{c.bf_qualifier}</span>
                                          : <span className="wp-na">—</span>}
                                      </td>
                                      <td>
                                        {c.ap1_qualifier != null
                                          ? <span className="wp-qualifier-badge">{c.ap1_qualifier}</span>
                                          : <span className="wp-na">—</span>}
                                      </td>
                                      <td>
                                        <span className={`wp-qualifier-badge wp-qualifier-badge--eff wp-eff-${eff}`}>
                                          {eff}
                                        </span>
                                      </td>
                                    </tr>
                                  );
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
                <div className="wp-empty-icon">
                  <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
                    <circle cx="26" cy="18" r="9" fill="rgba(77,217,192,0.4)" />
                    <path d="M10 46c0-9 7-16 16-16s16 7 16 16" fill="rgba(77,217,192,0.4)" />
                    <circle cx="36" cy="16" r="8" fill="rgba(60,200,176,0.3)" />
                    <path d="M20 44c0-8.5 6.7-15 15-15s15 6.5 15 15" fill="rgba(60,200,176,0.3)" />
                  </svg>
                </div>
                <h3 className="wp-empty-title">
                  {workers.length === 0 ? 'No workers in ontology' : 'No worker selected'}
                </h3>
                <p className="wp-empty-subtitle">
                  {workers.length === 0
                    ? 'The ontology does not contain any Person individuals with job evaluations.'
                    : 'Select a worker from the list on the left to view their health conditions.'}
                </p>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
