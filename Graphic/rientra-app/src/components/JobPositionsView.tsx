import { useState, useEffect, useMemo, useCallback } from 'react';
import './JobPositionsView.css';
import {
  fetchAllJobs,
  fetchJobImportance,
  fetchJobProfile,
  fetchWorkers,
  type JobEntry,
  type ImportanceEntry,
  type JobSkillEntry,
  type Worker,
} from '../api/semanticService';

/* ─────────────────────────────────────────────
   Icons
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

const XIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const ToolIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#4DD9C0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
);

const RefreshIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
  </svg>
);

const LayersIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="12 2 2 7 12 12 22 7 12 2" />
    <polyline points="2 17 12 22 22 17" />
    <polyline points="2 12 12 17 22 12" />
  </svg>
);

const UsersIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);

const TableIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <line x1="3" y1="9" x2="21" y2="9" />
    <line x1="3" y1="15" x2="21" y2="15" />
    <line x1="9" y1="3" x2="9" y2="21" />
  </svg>
);

/* ─────────────────────────────────────────────
   Loading Screen Component
   ───────────────────────────────────────────── */
interface LoadingScreenProps {
  status: any;
  error?: string | null;
  onRetry?: () => void;
}

function LoadingScreen({ status, error, onRetry }: LoadingScreenProps) {
  const [dots, setDots] = useState('');

  useEffect(() => {
    const t = setInterval(() => setDots(d => d.length >= 3 ? '' : d + '.'), 500);
    return () => clearInterval(t);
  }, []);

  if (error) {
    return (
      <div className="wp-loading-screen">
        <div className="wp-loading-error-icon">⚠</div>
        <h3 className="wp-loading-title">Service unavailable</h3>
        <p className="wp-loading-sub">{error}</p>
        {onRetry && (
          <button className="wp-btn-primary" onClick={onRetry} style={{ marginTop: 24 }}>
            <RefreshIcon /> Retry
          </button>
        )}
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
      <div className="wp-loading-orb">
        <div className="wp-orb-logo-container">
          <img src="./logo-rientra.png" alt="Loading" className="wp-orb-logo-img" />
        </div>
      </div>
      <h3 className="wp-loading-title">
        {phase}
        <span className="wp-loading-dots">{dots}</span>
      </h3>
      <p className="wp-loading-sub">
        {status?.message || 'Initialising Pellet OWL-DL reasoner and dataset snapshot cache…'}
      </p>
    </div>
  );
}

/* ─────────────────────────────────────────────
   Helpers
   ───────────────────────────────────────────── */
function formatLabel(id: string): string {
  return id
    .replace(/^Job_/, '')
    .replace(/([A-Z])/g, ' $1')
    .replace(/_/g, ' ')
    .trim();
}

type SkillDomain = 'Physical & Motor' | 'Sensory & Perceptual' | 'Cognitive & Mental' | 'Psychomotor & Control' | 'General Skill';

function categorizeSkill(skillId: string): SkillDomain {
  const s = skillId.toLowerCase();
  if (
    s.includes('strength') || s.includes('stamina') || s.includes('flexibility') ||
    s.includes('equilibrium') || s.includes('body') || s.includes('effort') ||
    s.includes('lift') || s.includes('climb') || s.includes('bend')
  ) {
    return 'Physical & Motor';
  }
  if (
    s.includes('vision') || s.includes('hearing') || s.includes('sound') ||
    s.includes('auditory') || s.includes('depth') || s.includes('glare') ||
    s.includes('speech') || s.includes('color') || s.includes('sens')
  ) {
    return 'Sensory & Perceptual';
  }
  if (
    s.includes('reasoning') || s.includes('attention') || s.includes('memory') ||
    s.includes('ordering') || s.includes('problem') || s.includes('math') ||
    s.includes('comprehension') || s.includes('idea') || s.includes('spatial') ||
    s.includes('originality') || s.includes('perceptualspeed')
  ) {
    return 'Cognitive & Mental';
  }
  if (
    s.includes('dexterity') || s.includes('steadiness') || s.includes('coordination') ||
    s.includes('speed') || s.includes('reaction') || s.includes('precision') ||
    s.includes('finger') || s.includes('wrist') || s.includes('arm') || s.includes('rate')
  ) {
    return 'Psychomotor & Control';
  }
  return 'General Skill';
}

interface FlattenedSkill {
  id: string;
  name: string;
  category: SkillDomain;
  score: number;
  anchor: number; // 0, 1, 2, 4
  importanceLabel: 'Very Important' | 'Important' | 'Somewhat Important' | 'Less Important';
}

/* ─────────────────────────────────────────────
   Props & Main Component: JobPositionsView
   ───────────────────────────────────────────── */
interface JobPositionsViewProps {
  isReady?: boolean;
  serviceStatus?: any;
  serviceError?: string | null;
  onRetry?: () => void;
  onSelectWorker?: (workerId: string) => void;
  isSidebarOpen?: boolean;
  onToggleSidebar?: () => void;
  selectedJobId?: string | null;
  onSelectJobId?: (jobId: string | null) => void;
}

export default function JobPositionsView({
  isReady = true,
  serviceStatus,
  serviceError,
  onRetry,
  onSelectWorker,
  isSidebarOpen = true,
  onToggleSidebar,
  selectedJobId: propSelectedJobId,
  onSelectJobId: propOnSelectJobId,
}: JobPositionsViewProps) {
  const [jobs, setJobs] = useState<JobEntry[]>([]);
  const [internalSelectedJobId, setInternalSelectedJobId] = useState<string | null>(null);
  const selectedJobId = propSelectedJobId !== undefined ? propSelectedJobId : internalSelectedJobId;
  const setSelectedJobId = (id: string | null) => {
    if (propOnSelectJobId) {
      propOnSelectJobId(id);
    } else {
      setInternalSelectedJobId(id);
    }
  };
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [jobsError, setJobsError] = useState<string | null>(null);

  // Detail state for selected job
  const [importanceData, setImportanceData] = useState<ImportanceEntry[]>([]);
  const [profileData, setProfileData] = useState<JobSkillEntry[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // UI state
  const [searchQuery, setSearchQuery] = useState('');
  const [skillSearchQuery, setSkillSearchQuery] = useState('');
  const [workerSearchQuery, setWorkerSearchQuery] = useState('');
  const [expandedSkillCode, setExpandedSkillCode] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'matrix' | 'workers' | 'table'>('matrix');
  const [selectedTierFilter, setSelectedTierFilter] = useState<string | 'all'>('all');

  // Sorting for Table tab
  type SortCol = 'code' | 'name' | 'category' | 'score';
  const [sortCol, setSortCol] = useState<SortCol>('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Import Modal
  const [importModalOpen, setImportModalOpen] = useState(false);

  /* ── Initial Load ── */
  const loadInitialData = useCallback(async () => {
    setLoadingJobs(true);
    setJobsError(null);
    try {
      const [fetchedJobs, fetchedWorkers] = await Promise.all([
        fetchAllJobs(),
        fetchWorkers().catch(() => [] as Worker[]),
      ]);
      setJobs(fetchedJobs);
      setWorkers(fetchedWorkers);
    } catch (err: any) {
      setJobsError(err?.message ?? 'Failed to load job positions.');
    } finally {
      setLoadingJobs(false);
    }
  }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  /* ── Load Job Details ── */
  useEffect(() => {
    if (!selectedJobId) return;
    let isCancelled = false;

    const loadDetails = async () => {
      setLoadingDetail(true);
      try {
        const [importance, profile] = await Promise.all([
          fetchJobImportance(selectedJobId).catch(() => [] as ImportanceEntry[]),
          fetchJobProfile(selectedJobId).catch(() => [] as JobSkillEntry[]),
        ]);
        if (!isCancelled) {
          setImportanceData(importance);
          setProfileData(profile);
        }
      } catch (e) {
        console.error('Error loading job details:', e);
      } finally {
        if (!isCancelled) setLoadingDetail(false);
      }
    };

    loadDetails();
    return () => {
      isCancelled = true;
    };
  }, [selectedJobId]);

  /* ── Global ESC Key to Deselect Job ── */
  useEffect(() => {
    function handleGlobalKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        if (importModalOpen) {
          setImportModalOpen(false);
          return;
        }
        if (selectedJobId !== null) {
          setSelectedJobId(null);
        }
      }
    }

    document.addEventListener('keydown', handleGlobalKeyDown);
    return () => {
      document.removeEventListener('keydown', handleGlobalKeyDown);
    };
  }, [selectedJobId, importModalOpen]);

  /* ── Computed Data ── */
  const selectedJob = useMemo(() => {
    return jobs.find(j => j.id === selectedJobId) ?? null;
  }, [jobs, selectedJobId]);

  const filteredJobs = useMemo(() => {
    if (!searchQuery.trim()) return jobs;
    const q = searchQuery.toLowerCase();
    return jobs.filter(
      j => j.id.toLowerCase().includes(q) || formatLabel(j.id).toLowerCase().includes(q)
    );
  }, [jobs, searchQuery]);

  const evaluatedWorkers = useMemo(() => {
    if (!selectedJobId) return [];
    return workers.filter(w => w.evaluated_for_jobs && w.evaluated_for_jobs.includes(selectedJobId));
  }, [workers, selectedJobId]);

  const filteredEvaluatedWorkers = useMemo(() => {
    if (!workerSearchQuery.trim()) return evaluatedWorkers;
    const q = workerSearchQuery.toLowerCase();
    return evaluatedWorkers.filter(w => {
      const fullName = [w.first_name, w.surname].filter(Boolean).join(' ').toLowerCase();
      return fullName.includes(q) || w.id.toLowerCase().includes(q);
    });
  }, [evaluatedWorkers, workerSearchQuery]);

  // Combine importance and profile data into flat list
  const allSkills: FlattenedSkill[] = useMemo(() => {
    const map = new Map<string, FlattenedSkill>();

    importanceData.forEach(entry => {
      const level = entry.importance_level;
      let anchor = 1;
      let importanceLabel: FlattenedSkill['importanceLabel'] = 'Somewhat Important';

      if (level === 'isVeryImportantFor') {
        anchor = 4;
        importanceLabel = 'Very Important';
      } else if (level === 'isImportantFor') {
        anchor = 2;
        importanceLabel = 'Important';
      } else if (level === 'isSomewhatImportantFor') {
        anchor = 1;
        importanceLabel = 'Somewhat Important';
      } else if (level === 'isLessImportantFor') {
        anchor = 0;
        importanceLabel = 'Less Important';
      }

      entry.skills.forEach(s => {
        map.set(s.id, {
          id: s.id,
          name: formatLabel(s.id),
          category: categorizeSkill(s.id),
          score: s.score,
          anchor,
          importanceLabel,
        });
      });
    });

    profileData.forEach(p => {
      if (!map.has(p.id)) {
        let anchor = 0;
        let importanceLabel: FlattenedSkill['importanceLabel'] = 'Less Important';
        if (p.score >= 75) { anchor = 4; importanceLabel = 'Very Important'; }
        else if (p.score >= 50) { anchor = 2; importanceLabel = 'Important'; }
        else if (p.score >= 25) { anchor = 1; importanceLabel = 'Somewhat Important'; }

        map.set(p.id, {
          id: p.id,
          name: formatLabel(p.id),
          category: categorizeSkill(p.id),
          score: p.score,
          anchor,
          importanceLabel,
        });
      }
    });

    return Array.from(map.values());
  }, [importanceData, profileData]);

  // Filter skills based on search & active tier pill
  const filteredSkills = useMemo(() => {
    return allSkills.filter(s => {
      if (selectedTierFilter !== 'all' && s.importanceLabel !== selectedTierFilter) {
        return false;
      }
      if (skillSearchQuery.trim()) {
        const q = skillSearchQuery.toLowerCase();
        return (
          s.id.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q) ||
          s.category.toLowerCase().includes(q) ||
          s.importanceLabel.toLowerCase().includes(q)
        );
      }
      return true;
    }).sort((a, b) => {
      const mult = sortDir === 'asc' ? 1 : -1;
      if (sortCol === 'code') return mult * a.id.localeCompare(b.id);
      if (sortCol === 'name') return mult * a.name.localeCompare(b.name);
      if (sortCol === 'category') return mult * a.category.localeCompare(b.category);
      return mult * (a.score - b.score);
    });
  }, [allSkills, selectedTierFilter, skillSearchQuery, sortCol, sortDir]);

  // Group skills by Tier for the Card Matrix view
  const tierGroups = useMemo(() => {
    const tiers = [
      {
        key: 'Very Important',
        label: 'Very Important',
        desc: 'High priority core capabilities (Score ≥ 75 / Anchor 3)',
        dotClass: 'very-important',
        barColor: '#ef4444',
        skills: filteredSkills.filter(s => s.importanceLabel === 'Very Important'),
      },
      {
        key: 'Important',
        label: 'Important',
        desc: 'Essential operational skills (Score 50–74 / Anchor 2)',
        dotClass: 'important',
        barColor: '#f59e0b',
        skills: filteredSkills.filter(s => s.importanceLabel === 'Important'),
      },
      {
        key: 'Somewhat Important',
        label: 'Somewhat Important',
        desc: 'Secondary support capabilities (Score 25–49 / Anchor 1)',
        dotClass: 'somewhat-important',
        barColor: '#3b82f6',
        skills: filteredSkills.filter(s => s.importanceLabel === 'Somewhat Important'),
      },
      {
        key: 'Less Important',
        label: 'Less Important',
        desc: 'Supplementary skills (Score < 25 / Anchor 0)',
        dotClass: 'less-important',
        barColor: '#94a3b8',
        skills: filteredSkills.filter(s => s.importanceLabel === 'Less Important'),
      },
    ];

    if (selectedTierFilter !== 'all') {
      return tiers.filter(t => t.key === selectedTierFilter);
    }
    return tiers;
  }, [filteredSkills, selectedTierFilter]);

  // Counts for pills
  const counts = useMemo(() => ({
    all: allSkills.length,
    veryImportant: allSkills.filter(s => s.importanceLabel === 'Very Important').length,
    important: allSkills.filter(s => s.importanceLabel === 'Important').length,
    somewhatImportant: allSkills.filter(s => s.importanceLabel === 'Somewhat Important').length,
    lessImportant: allSkills.filter(s => s.importanceLabel === 'Less Important').length,
  }), [allSkills]);

  const handleSort = (col: SortCol) => {
    if (sortCol === col) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(col);
      setSortDir('desc');
    }
  };

  const sortIcon = (col: SortCol) => {
    if (sortCol !== col) return '⇅';
    return sortDir === 'asc' ? '▲' : '▼';
  };

  return (
    <>
      {/* ── Left Sidebar (Coherent with WorkersPage) ── */}
      <aside
        className={`wp-sidebar ${isSidebarOpen ? '' : 'wp-sidebar--closed'}`}
      >
        <div className="wp-sidebar-header">
          <span className="wp-sidebar-title">Job Positions</span>
          <button className="wp-icon-button" onClick={onToggleSidebar} aria-label="Close sidebar">
            <ListIcon />
          </button>
        </div>

        <div className="wp-search-wrapper">
          <span className="wp-search-icon"><SearchIcon /></span>
          <input
            id="job-search"
            type="text"
            className="wp-search-input"
            placeholder="Search by job name"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
          {searchQuery.length > 0 && (
            <span
              className="wp-search-action-icon"
              onMouseDown={(e) => { e.preventDefault(); setSearchQuery(''); }}
            >
              <XIcon />
            </span>
          )}
        </div>

        <div className="wp-sidebar-col-label">JOB POSITION</div>

        <ul className="wp-worker-list" id="job-list">
          {loadingJobs && (
            <li className="wp-worker-item wp-worker-item--skeleton" aria-label="loading">
              <span className="wp-skeleton-line" />
            </li>
          )}

          {!loadingJobs && filteredJobs.map(j => {
            const isSelected = selectedJobId === j.id;
            return (
              <li
                key={j.id}
                className={`wp-worker-item ${isSelected ? 'selected' : ''}`}
                onClick={() => setSelectedJobId(j.id)}
                role="button"
                onKeyDown={e => e.key === 'Enter' && setSelectedJobId(j.id)}
              >
                <span className="wp-worker-name">{formatLabel(j.id)}</span>
              </li>
            );
          })}

          {!loadingJobs && filteredJobs.length === 0 && (
            <li className="wp-worker-item wp-worker-item--empty">
              {jobsError ? 'Error loading jobs' : 'No results'}
            </li>
          )}
        </ul>

        <button
          className="wp-add-btn"
          id="btn-import-jobs"
          onClick={() => setImportModalOpen(true)}
        >
          <PlusIcon /> Import Jobs
        </button>
      </aside>

      {/* ── Main Panel ── */}
      <main className="wp-main">
        <div className="wp-panel">
          {!isReady ? (
            <LoadingScreen
              status={serviceStatus}
              error={serviceError}
              onRetry={onRetry}
            />
          ) : selectedJob ? (
            <div className="wp-content-fade">
              {/* Job Header */}
              <div className="wp-worker-header">
                <div className="wp-worker-id">
                  <span className="wp-worker-id-label">Job ID:</span>
                  <span className="wp-worker-id-value">{selectedJob.id}</span>
                </div>
                <div className="wp-worker-meta" style={{ flex: 1 }}>
                  <span>Title: <strong>{formatLabel(selectedJob.id)}</strong></span>
                </div>
              </div>

              {/* Main Content Section */}
              <div className="wp-section">
                {/* ── View Switcher Tabs ── */}
                <div className="jp-tab-bar">
                  <button
                    className={`jp-tab-btn ${activeTab === 'matrix' ? 'active' : ''}`}
                    onClick={() => setActiveTab('matrix')}
                  >
                    <LayersIcon />
                    Skill Requirements
                    <span className="jp-tab-badge">{allSkills.length}</span>
                  </button>

                  <button
                    className={`jp-tab-btn ${activeTab === 'workers' ? 'active' : ''}`}
                    onClick={() => setActiveTab('workers')}
                  >
                    <UsersIcon />
                    Evaluated Workers
                    <span className="jp-tab-badge">{evaluatedWorkers.length}</span>
                  </button>

                  <button
                    className={`jp-tab-btn ${activeTab === 'table' ? 'active' : ''}`}
                    onClick={() => setActiveTab('table')}
                  >
                    <TableIcon />
                    Table View
                  </button>
                </div>

                {/* Section Controls */}
                <div className="wp-section-header" style={{ marginBottom: 12 }}>
                  {activeTab === 'workers' ? (
                    <div className="wp-search-wrapper" style={{ flex: 1, maxWidth: 320, marginBottom: 0 }}>
                      <span className="wp-search-icon"><SearchIcon /></span>
                      <input
                        type="text"
                        className="wp-search-input"
                        placeholder="Search workers by name or ID..."
                        value={workerSearchQuery}
                        onChange={e => setWorkerSearchQuery(e.target.value)}
                      />
                      {workerSearchQuery.length > 0 && (
                        <span
                          className="wp-search-action-icon"
                          onMouseDown={(e) => { e.preventDefault(); setWorkerSearchQuery(''); }}
                        >
                          <XIcon />
                        </span>
                      )}
                    </div>
                  ) : (
                    <>
                      <div className="wp-search-wrapper" style={{ flex: 1, maxWidth: 280, marginBottom: 0 }}>
                        <span className="wp-search-icon"><SearchIcon /></span>
                        <input
                          type="text"
                          className="wp-search-input"
                          placeholder="Search skills or abilities..."
                          value={skillSearchQuery}
                          onChange={e => setSkillSearchQuery(e.target.value)}
                        />
                        {skillSearchQuery.length > 0 && (
                          <span
                            className="wp-search-action-icon"
                            onMouseDown={(e) => { e.preventDefault(); setSkillSearchQuery(''); }}
                          >
                            <XIcon />
                          </span>
                        )}
                      </div>

                      {/* Tier Filter Pills */}
                      <div className="jp-tier-pills">
                        <button
                          className={`jp-tier-pill ${selectedTierFilter === 'all' ? 'active' : ''}`}
                          onClick={() => setSelectedTierFilter('all')}
                        >
                          All ({counts.all})
                        </button>
                        <button
                          className={`jp-tier-pill ${selectedTierFilter === 'Very Important' ? 'active' : ''}`}
                          onClick={() => setSelectedTierFilter('Very Important')}
                        >
                          <span className="jp-tier-pill-dot very-important" />
                          Very Important ({counts.veryImportant})
                        </button>
                        <button
                          className={`jp-tier-pill ${selectedTierFilter === 'Important' ? 'active' : ''}`}
                          onClick={() => setSelectedTierFilter('Important')}
                        >
                          <span className="jp-tier-pill-dot important" />
                          Important ({counts.important})
                        </button>
                        <button
                          className={`jp-tier-pill ${selectedTierFilter === 'Somewhat Important' ? 'active' : ''}`}
                          onClick={() => setSelectedTierFilter('Somewhat Important')}
                        >
                          <span className="jp-tier-pill-dot somewhat-important" />
                          Somewhat ({counts.somewhatImportant})
                        </button>
                      </div>
                    </>
                  )}
                </div>

                {/* ── TAB 1: Skill Matrix & Cards ── */}
                {activeTab === 'matrix' && (
                  <div className="jp-tab-content-scroll" style={{ position: 'relative' }}>
                    {loadingDetail && (
                      <div className="wp-table-loading" style={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(26, 42, 74, 0.4)', zIndex: 10 }}>
                        <div className="wp-spinner" />
                      </div>
                    )}

                    <div className="jp-tier-sections">
                      {tierGroups.map(tier => {
                        if (selectedTierFilter === 'all' && tier.skills.length === 0) return null;

                        return (
                          <div key={tier.key} className="jp-tier-block">
                            <div className="jp-tier-block-header">
                              <div className="jp-tier-block-title-wrap">
                                <span className={`jp-tier-block-dot ${tier.dotClass}`} />
                                <div>
                                  <span className="jp-tier-block-title">{tier.label}</span>
                                  <span className="jp-tier-block-desc" style={{ marginLeft: 8 }}>{tier.desc}</span>
                                </div>
                              </div>
                              <span className="jp-tier-block-badge">{tier.skills.length} Descriptors</span>
                            </div>

                            {tier.skills.length === 0 ? (
                              <div style={{ padding: '16px', color: 'rgba(255,255,255,0.4)', fontSize: '0.78rem', textAlign: 'center' }}>
                                No skills in this category
                              </div>
                            ) : (
                              <div className="jp-skills-card-grid">
                                {tier.skills.map(s => (
                                  <div
                                    key={s.id}
                                    className="jp-skill-card-item"
                                  >
                                    <div className="jp-skill-card-header">
                                      <span className="jp-skill-card-name">{s.name}</span>
                                      <span className="jp-skill-card-score">{s.score} / 100</span>
                                    </div>

                                    <div className="jp-skill-card-bar-wrap">
                                      <div
                                        className="jp-skill-card-bar-fill"
                                        style={{ width: `${s.score}%`, background: tier.barColor }}
                                      />
                                    </div>

                                    <div className="jp-skill-card-footer">
                                      <span className="jp-skill-card-cat-tag">{s.category}</span>
                                      <span className="jp-skill-card-id-tag" title={s.id}>{s.id}</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}

                      {!loadingDetail && selectedTierFilter === 'all' && filteredSkills.length === 0 && (
                        <div className="wp-table-empty visible">
                          <p>No skills or abilities match the search query.</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* ── TAB 2: Evaluated Workers ── */}
                {activeTab === 'workers' && (
                  <div className="jp-tab-content-scroll">
                    {evaluatedWorkers.length === 0 ? (
                      <div className="wp-empty-state" style={{ padding: '40px 20px' }}>
                        <div className="wp-empty-icon"><UsersIcon /></div>
                        <h3 className="wp-empty-title">No workers evaluated for this position</h3>
                        <p className="wp-empty-subtitle">
                          None of the registered workers have been assigned to <strong>{formatLabel(selectedJob.id)}</strong>.
                        </p>
                      </div>
                    ) : filteredEvaluatedWorkers.length === 0 ? (
                      <div className="wp-table-empty visible" style={{ marginTop: 24 }}>
                        <p>No workers match the search criteria &ldquo;{workerSearchQuery}&rdquo;.</p>
                      </div>
                    ) : (
                      <div className="jp-workers-card-grid">
                        {filteredEvaluatedWorkers.map(w => (
                          <div
                            key={w.id}
                            className="jp-worker-item-card"
                            onClick={() => onSelectWorker?.(w.id)}
                            role="button"
                            tabIndex={0}
                            onKeyDown={e => e.key === 'Enter' && onSelectWorker?.(w.id)}
                            style={{ cursor: onSelectWorker ? 'pointer' : 'default' }}
                            title={`Open Worker Information for ${[w.first_name, w.surname].filter(Boolean).join(' ') || w.id}`}
                          >
                            <div className="jp-worker-avatar-box">
                              {w.first_name ? w.first_name[0] : w.id[0]}
                            </div>
                            <div className="jp-worker-info-box" style={{ flex: 1 }}>
                              <span className="jp-worker-name-text">
                                {[w.first_name, w.surname].filter(Boolean).join(' ') || w.id}
                              </span>
                              <span className="jp-worker-id-text">ID: {w.id}</span>
                            </div>
                            <div style={{ color: 'rgba(255,255,255,0.4)', display: 'flex', alignItems: 'center' }}>
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <polyline points="9 18 15 12 9 6"></polyline>
                              </svg>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* ── TAB 4: Raw Table View ── */}
                {activeTab === 'table' && (
                  <div className="wp-table-wrapper" style={{ position: 'relative' }}>
                    {loadingDetail && (
                      <div className="wp-table-loading" style={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(26, 42, 74, 0.4)', zIndex: 10 }}>
                        <div className="wp-spinner" />
                      </div>
                    )}

                    <table className="wp-table" id="job-skills-table" style={{ opacity: loadingDetail ? 0.6 : 1 }}>
                      <colgroup>
                        <col style={{ width: '22%' }} />
                        <col style={{ width: '38%' }} />
                        <col style={{ width: '25%' }} />
                        <col style={{ width: '15%' }} />
                      </colgroup>
                      <thead>
                        <tr>
                          <th className={`wp-th-sortable${sortCol === 'code' ? ' wp-th-sorted' : ''}`} onClick={() => handleSort('code')}>
                            SKILL / ABILITY {sortIcon('code')}
                          </th>
                          <th className={`wp-th-sortable${sortCol === 'name' ? ' wp-th-sorted' : ''}`} onClick={() => handleSort('name')}>
                            NAME {sortIcon('name')}
                          </th>
                          <th className={`wp-th-sortable${sortCol === 'category' ? ' wp-th-sorted' : ''}`} onClick={() => handleSort('category')}>
                            CATEGORY {sortIcon('category')}
                          </th>
                          <th className={`wp-th-sortable${sortCol === 'score' ? ' wp-th-sorted' : ''}`} onClick={() => handleSort('score')}>
                            O*NET SCORE {sortIcon('score')}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredSkills.map((s, i) => {
                          const isExpanded = expandedSkillCode === s.id;
                          return [
                            <tr
                              key={`${s.id}-${i}`}
                              className={`wp-condition-row${isExpanded ? ' is-expanded' : ''}`}
                              onClick={() => setExpandedSkillCode(prev => prev === s.id ? null : s.id)}
                            >
                              <td>
                                <div className="wp-icf-code-cell">
                                  <span className={`wp-row-expander-arrow${isExpanded ? ' is-expanded' : ''}`} aria-hidden="true">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                      <polyline points="6 9 12 15 18 9"></polyline>
                                    </svg>
                                  </span>
                                  <span className="wp-icf-code">{s.id}</span>
                                </div>
                              </td>
                              <td>
                                <div className="wp-icf-name-cell">
                                  <span className="wp-icf-name">{s.name}</span>
                                </div>
                              </td>
                              <td>
                                <span className="wp-icf-category" style={{ fontSize: '0.75rem', opacity: 0.8 }}>
                                  {s.category}
                                </span>
                              </td>
                              <td>
                                <span className={`wp-qualifier-badge wp-qualifier-badge--eff wp-eff-${s.anchor}`} title={`${s.importanceLabel} (${s.score}/100)`}>
                                  {s.score}
                                </span>
                              </td>
                            </tr>,
                            isExpanded ? (
                              <tr key={`${s.id}-${i}-detail`} className="wp-condition-detail-row">
                                <td />
                                <td colSpan={3}>
                                  <div className="wp-condition-description">
                                    <p className="wp-condition-description-main">
                                      <strong>O*NET Demand Level:</strong> {s.score} / 100 — Classified under SWRL as <strong>{s.importanceLabel}</strong> (Anchor weight: {s.anchor}).
                                    </p>
                                  </div>
                                </td>
                              </tr>
                            ) : null
                          ];
                        })}
                      </tbody>
                    </table>

                    {!loadingDetail && filteredSkills.length === 0 && (
                      <div className="wp-table-empty visible">
                        <p>No skills or abilities match the current search or filter criteria.</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="wp-empty-state">
              <div className="wp-empty-icon" style={{ opacity: 0.9 }}>
                <img src="./employee.png" alt="No job selected" style={{ width: 64, height: 64, objectFit: 'contain' }} />
              </div>
              <h3 className="wp-empty-title">No job selected</h3>
              <p className="wp-empty-subtitle">
                Select a job from the list on the left to view its required skills and abilities.
              </p>
            </div>
          )}
        </div>
      </main>

      {/* ── Import Jobs: Not Yet Implemented Modal ── */}
      {importModalOpen && (
        <div className="wp-modal-backdrop" onClick={() => setImportModalOpen(false)}>
          <div
            className="wp-modal jp-not-implemented-modal"
            onClick={e => e.stopPropagation()}
            style={{ maxWidth: 460, position: 'relative' }}
          >
            <button
              className="wp-modal-header-close-btn"
              onClick={() => setImportModalOpen(false)}
              aria-label="Close"
            >
              <XIcon />
            </button>

            <div
              className="wp-modal-success-circle"
              style={{
                background: 'rgba(77, 217, 192, 0.1)',
                borderColor: 'rgba(77, 217, 192, 0.25)',
                marginBottom: 14,
              }}
            >
              <ToolIcon />
            </div>

            <div className="jp-modal-badge">
              Coming Soon
            </div>

            <h3 className="wp-modal-title" style={{ marginTop: 6, marginBottom: 8, fontSize: '1.2rem' }}>
              Feature Not Yet Implemented
            </h3>

            <p
              className="wp-modal-sub"
              style={{
                fontSize: '0.86rem',
                color: 'rgba(255, 255, 255, 0.7)',
                lineHeight: 1.55,
                marginBottom: 18,
              }}
            >
              The <strong>Import Jobs</strong> feature is currently not yet implemented. Support for importing custom O*NET job positions and ontology datasets will be available in an upcoming release.
            </p>

            <div className="jp-modal-info-card">
              <div className="jp-modal-info-row">
                <span className="jp-modal-info-label">Module:</span>
                <span className="jp-modal-info-val">Job Position Ingestion</span>
              </div>
              <div className="jp-modal-info-row">
                <span className="jp-modal-info-label">Status:</span>
                <span className="jp-modal-info-val" style={{ color: '#4DD9C0' }}>Under Development</span>
              </div>
            </div>

            <button
              className="wp-modal-close-btn"
              style={{ marginTop: 20 }}
              onClick={() => setImportModalOpen(false)}
            >
              Got it
            </button>
          </div>
        </div>
      )}
    </>
  );
}
