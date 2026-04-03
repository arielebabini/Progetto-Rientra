import { useState, useEffect, useCallback, useRef } from 'react';
import './WorkersPage.css';
import {
  fetchStatus,
  fetchWorkers,
  fetchHealthConditions,
  type ServiceStatus,
  type Worker,
  type HealthCondition,
} from '../api/semanticService';

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
      {/* Animated brain/ontology orb */}
      <div className="wp-loading-orb">
        <div className="wp-orb-ring wp-orb-ring-1" />
        <div className="wp-orb-ring wp-orb-ring-2" />
        <div className="wp-orb-ring wp-orb-ring-3" />
        <div className="wp-orb-core">
          <svg width="36" height="36" viewBox="0 0 64 64" fill="none">
            <circle cx="26" cy="18" r="9" fill="rgba(77,217,192,0.7)" />
            <path d="M10 46c0-9 7-16 16-16s16 7 16 16" fill="rgba(77,217,192,0.7)" />
            <circle cx="38" cy="16" r="7" fill="rgba(77,217,192,0.4)" />
            <path d="M22 44c0-8 6-14 16-14s16 6 16 14" fill="rgba(77,217,192,0.4)" />
          </svg>
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
}

/* ─────────────────────────────────────────────
   Main component
───────────────────────────────────────────── */
export default function WorkersPage({ onNavigateHome }: WorkersPageProps) {
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
  const [searchQuery,  setSearchQuery]  = useState('');
  const [dotsMenuOpen, setDotsMenuOpen] = useState(false);
  const [activeNav,    setActiveNav]    = useState<'workers' | 'jobs-analysis' | 'jobs-positions'>('workers');

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

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div className="wp-page">
      <div className="bg-blob bg-blob-1" />
      <div className="bg-blob bg-blob-2" />
      <div className="bg-blob bg-blob-3" />

      {/* ── Top Navigation Bar ── */}
      <nav className="wp-navbar">
        <div className="wp-nav-brand" onClick={onNavigateHome} role="button" tabIndex={0}
          onKeyDown={e => e.key === 'Enter' && onNavigateHome()}>
          <img src="/logo-rientra.png" alt="Rientra Logo" className="wp-nav-logo" />
          <span className="wp-nav-title">RIENTR@</span>
        </div>
        <div className="wp-nav-links">
          {(['workers', 'jobs-analysis', 'jobs-positions'] as const).map(n => (
            <button key={n} id={`nav-${n}`}
              className={`wp-nav-link ${activeNav === n ? 'active' : ''}`}
              onClick={() => setActiveNav(n)}>
              {n === 'workers' ? 'Workers' : n === 'jobs-analysis' ? 'Jobs Analysis' : 'Jobs Positions'}
            </button>
          ))}
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

      {/* ── Body: Sidebar + Main Panel ── */}
      <div className="wp-body">

        {/* ── Left Sidebar ── */}
        <aside className="wp-sidebar">
          <div className="wp-sidebar-header">
            <span className="wp-sidebar-title">Workers</span>
            <ListIcon />
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
            {!loadingWorkers && filteredWorkers.map(w => (
              <li key={w.id}
                className={`wp-worker-item ${selectedWorker?.id === w.id ? 'selected' : ''}`}
                onClick={() => setSelectedWorker(w)}
                role="button" tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && setSelectedWorker(w)}>
                {displayName(w)}
              </li>
            ))}
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
              <>
                {/* Worker header */}
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

                <div className="wp-divider" />

                {/* Health conditions section */}
                <div className="wp-section">
                  <div className="wp-section-header">
                    <h2 className="wp-section-title">Current Health Conditions</h2>
                    <div className="wp-section-actions">
                      <button className="wp-btn-primary" id="btn-modify-health">
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

                  {/* Table */}
                  <div className="wp-table-wrapper">
                    {loadingConditions ? (
                      <div className="wp-table-loading">
                        <div className="wp-spinner" />
                        <span>Loading health conditions…</span>
                      </div>
                    ) : (
                      <table className="wp-table" id="health-conditions-table">
                        <thead>
                          <tr>
                            <th>ICF Code</th>
                            <th>BF Qualifier</th>
                            <th>AP1 Qualifier</th>
                            <th>Effective Qualifier</th>
                          </tr>
                        </thead>
                        <tbody>
                          {conditions.map((c, i) => {
                            const eff = Math.max(c.bf_qualifier ?? 0, c.ap1_qualifier ?? 0);
                            return (
                              <tr key={`${c.icf_code}-${i}`}>
                                <td><span className="wp-icf-code">{c.icf_code}</span></td>
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
              </>
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
