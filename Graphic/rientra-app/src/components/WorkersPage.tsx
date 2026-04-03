import { useState } from 'react';
import './WorkersPage.css';

/* ─────────────────────────────────────────────
   Minimal SVG icons (inline, no external deps)
───────────────────────────────────────────── */
const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

const ListIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="8" y1="6" x2="21" y2="6" />
    <line x1="8" y1="12" x2="21" y2="12" />
    <line x1="8" y1="18" x2="21" y2="18" />
    <line x1="3" y1="6" x2="3.01" y2="6" />
    <line x1="3" y1="12" x2="3.01" y2="12" />
    <line x1="3" y1="18" x2="3.01" y2="18" />
  </svg>
);

const PlusIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
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
    <circle cx="5" cy="12" r="2" />
    <circle cx="12" cy="12" r="2" />
    <circle cx="19" cy="12" r="2" />
  </svg>
);

const ArchiveIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="21 8 21 21 3 21 3 8" />
    <rect x="1" y="3" width="22" height="5" />
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

/* ─────────────────────────────────────────────
   Types
───────────────────────────────────────────── */
interface WorkersPageProps {
  onNavigateHome: () => void;
}

/* ─────────────────────────────────────────────
   Component
───────────────────────────────────────────── */
export default function WorkersPage({ onNavigateHome }: WorkersPageProps) {
  const [searchQuery, setSearchQuery] = useState('');
  // selectedWorkerId will be set when worker list populates from the ontology
  const [selectedWorkerId, setSelectedWorkerId] = useState<string | null>(null);
  void setSelectedWorkerId; // wired up when ontology data is integrated
  const [dotsMenuOpen, setDotsMenuOpen] = useState(false);
  const [activeNav, setActiveNav] = useState<'workers' | 'jobs-analysis' | 'jobs-positions'>('workers');

  /* No worker selected → show empty state in main panel */
  const hasSelection = selectedWorkerId !== null;

  return (
    <div className="wp-page">
      {/* Animated background blobs — same palette as home */}
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
          <button
            className={`wp-nav-link ${activeNav === 'workers' ? 'active' : ''}`}
            onClick={() => setActiveNav('workers')}
            id="nav-workers"
          >
            Workers
          </button>
          <button
            className={`wp-nav-link ${activeNav === 'jobs-analysis' ? 'active' : ''}`}
            onClick={() => setActiveNav('jobs-analysis')}
            id="nav-jobs-analysis"
          >
            Jobs Analysis
          </button>
          <button
            className={`wp-nav-link ${activeNav === 'jobs-positions' ? 'active' : ''}`}
            onClick={() => setActiveNav('jobs-positions')}
            id="nav-jobs-positions"
          >
            Jobs Positions
          </button>
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

          {/* Search */}
          <div className="wp-search-wrapper">
            <span className="wp-search-icon"><SearchIcon /></span>
            <input
              id="worker-search"
              type="text"
              className="wp-search-input"
              placeholder="Search"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Column label */}
          <div className="wp-sidebar-col-label">ID Number</div>

          {/* Worker list — empty, ready for data */}
          <ul className="wp-worker-list" id="worker-list">
            {/* Workers will be populated from the ontology query */}
          </ul>

          {/* Add Worker */}
          <button className="wp-add-btn" id="btn-add-worker">
            <PlusIcon />
            Add Worker
          </button>
        </aside>

        {/* ── Main Panel ── */}
        <main className="wp-main">
          <div className="wp-panel">

            {hasSelection ? (
              /* ── Selected worker view ── */
              <>
                {/* Worker header */}
                <div className="wp-worker-header">
                  <div className="wp-worker-id">
                    <span className="wp-worker-id-label">ID Number:</span>
                    <span className="wp-worker-id-value">{selectedWorkerId}</span>
                  </div>
                  <div className="wp-worker-meta">
                    <span>Age: <strong>—</strong></span>
                    <span>Gender: <strong>—</strong></span>
                  </div>
                </div>

                <div className="wp-divider" />

                {/* Health conditions section */}
                <div className="wp-section">
                  <div className="wp-section-header">
                    <h2 className="wp-section-title">Current Health Conditions</h2>
                    <div className="wp-section-actions">
                      <button className="wp-btn-primary" id="btn-modify-health">
                        <EditIcon />
                        Modify Health Conditions
                      </button>

                      {/* Dots / overflow menu */}
                      <div className="wp-dots-wrapper">
                        <button
                          className={`wp-btn-dots ${dotsMenuOpen ? 'active' : ''}`}
                          id="btn-overflow-menu"
                          onClick={() => setDotsMenuOpen(v => !v)}
                          aria-label="More options"
                        >
                          <DotsIcon />
                        </button>
                        {dotsMenuOpen && (
                          <div className="wp-dropdown" id="overflow-dropdown">
                            <button className="wp-dropdown-item" id="btn-archive">
                              <ArchiveIcon /> Move to archive
                            </button>
                            <button className="wp-dropdown-item" id="btn-save-pdf">
                              <PdfIcon /> Save PDF
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Health conditions table */}
                  <div className="wp-table-wrapper">
                    <table className="wp-table" id="health-conditions-table">
                      <thead>
                        <tr>
                          <th>ICF Code</th>
                          <th>Code Name</th>
                          <th>Qualifier</th>
                          <th>Date Added</th>
                        </tr>
                      </thead>
                      <tbody>
                        {/* Rows will be populated from the ontology query */}
                      </tbody>
                    </table>

                    {/* Empty state for the table */}
                    <div className="wp-table-empty visible">
                      <p>No health conditions on record for this worker.</p>
                      <p className="wp-table-empty-hint">Data will be loaded from the ontology.</p>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              /* ── No worker selected — empty state ── */
              <div className="wp-empty-state">
                <div className="wp-empty-icon">
                  <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
                    <circle cx="26" cy="18" r="9" fill="rgba(77,217,192,0.4)" />
                    <path d="M10 46c0-9 7-16 16-16s16 7 16 16" fill="rgba(77,217,192,0.4)" />
                    <circle cx="36" cy="16" r="8" fill="rgba(60,200,176,0.3)" />
                    <path d="M20 44c0-8.5 6.7-15 15-15s15 6.5 15 15" fill="rgba(60,200,176,0.3)" />
                  </svg>
                </div>
                <h3 className="wp-empty-title">No worker selected</h3>
                <p className="wp-empty-subtitle">
                  Select a worker from the list on the left, or add a new one to get started.
                </p>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
