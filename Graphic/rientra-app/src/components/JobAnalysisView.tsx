import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import './JobAnalysisView.css';
import './HealthConditionWizard.css';
import {
  fetchMatchResults,
  fetchSkillDetail,
  fetchAllJobs,
  updateWorkerJobs,
  type MatchResult,
  type SkillDetailResponse,
  type JobEntry,
} from '../api/semanticService';


/* ═══════════════════════════════════════════════════════════════
   Scatter plot — layout constants
   PAD is in SVG user-units and stays fixed so labels never scale.
═══════════════════════════════════════════════════════════════ */
const PAD = { l: 62, r: 24, t: 20, b: 50 };

/** Round v up to the nearest multiple of step, with a minimum of min. */
function axisMax(v: number, step: number, min: number): number {
  return Math.max(min, Math.ceil(v / step) * step);
}
/** Generate evenly-spaced tick marks from 0 to max, inclusive. */
function makeTicks(max: number, step: number): number[] {
  const ticks: number[] = [];
  for (let t = 0; t <= max; t += step) ticks.push(t);
  return ticks;
}

/* ═══════════════════════════════════════════════════════════════
   ScatterPlot component
   Tracks its container's real pixel size with ResizeObserver so
   the viewBox grows with the space — dots / labels stay the same
   visual size because PAD values are in fixed SVG user-units.
═══════════════════════════════════════════════════════════════ */
interface ScatterPlotProps {
  matchResults: MatchResult[];
  jobA: string | null;
  jobB: string | null;
  onSelect: (id: string) => void;
}
function ScatterPlot({ matchResults, jobA, jobB, onSelect }: ScatterPlotProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 600, h: 300 });
  const [tooltip, setTooltip] = useState<{ dataX: number; dataY: number; result: MatchResult } | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        const { width, height } = e.contentRect;
        if (width > 10 && height > 10) setSize({ w: Math.round(width), h: Math.round(height) });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  /* ── Dynamic axis ranges — always show all data points ── */
  const X_MAX = useMemo(() => {
    const dataMax = matchResults.length ? Math.max(...matchResults.map(r => r.aisa_pct)) : 0;
    return axisMax(dataMax + 2, 10, 55);   // minimum 55 so threshold lines always fit
  }, [matchResults]);
  const Y_MAX = useMemo(() => {
    const dataMax = matchResults.length ? Math.max(...matchResults.map(r => r.gcs_pct)) : 0;
    return axisMax(dataMax + 1, 5, 25);    // minimum 25
  }, [matchResults]);

  const X_TICKS = useMemo(() => makeTicks(X_MAX, 10), [X_MAX]);
  const Y_TICKS = useMemo(() => makeTicks(Y_MAX, 5), [Y_MAX]);

  const { w, h } = size;
  const PW = w - PAD.l - PAD.r;
  const PH = h - PAD.t - PAD.b;
  const toX = (a: number) => PAD.l + (a / X_MAX) * PW;
  const toY = (g: number) => PAD.t + PH - (g / Y_MAX) * PH;

  /* ── Suitability threshold line endpoints, clipped to the visible plot ── */
  // NOT SUITABLE:     GCS = -0.5*AISA + 21  →  x-intercept at AISA=42
  // WITH PRECAUTIONS: GCS = -0.5*AISA + 15.5 → x-intercept at AISA=31
  const nsX2 = Math.min(42, X_MAX);   // clip to visible range
  const wpX2 = Math.min(31, X_MAX);

  return (
    <div ref={wrapRef} style={{ flex: 1, minHeight: 0, minWidth: 0, position: 'relative' }}>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        width={w} height={h}
        style={{ display: 'block', overflow: 'visible' }}
        aria-label="Job suitability scatter plot"
      >
        <defs>
          <clipPath id="ja-clip">
            <rect x={PAD.l} y={PAD.t} width={PW} height={PH} />
          </clipPath>
        </defs>

        {/* plot area */}
        <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="rgba(0,0,0,0.15)" rx="3" />

        {/* dashed grid */}
        {X_TICKS.map(t => <line key={`xg${t}`} x1={toX(t)} y1={PAD.t} x2={toX(t)} y2={PAD.t + PH} stroke="rgba(255,255,255,0.09)" strokeWidth="0.6" strokeDasharray="3,5" />)}
        {Y_TICKS.map(t => <line key={`yg${t}`} x1={PAD.l} y1={toY(t)} x2={PAD.l + PW} y2={toY(t)} stroke="rgba(255,255,255,0.09)" strokeWidth="0.6" strokeDasharray="3,5" />)}

        {/* border */}
        <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="none" stroke="rgba(255,255,255,0.10)" strokeWidth="0.8" rx="3" />

        {/* suitability threshold lines — visible dashed diagonals */}
        <g clipPath="url(#ja-clip)">
          {/* NOT SUITABLE boundary */}
          <line x1={toX(0)} y1={toY(21)} x2={toX(nsX2)} y2={toY(Math.max(0, 21 - 0.5 * nsX2))} stroke="#ef4444" strokeWidth="1.8" strokeDasharray="6,4" opacity="0.85" />
          {/* WITH PRECAUTIONS boundary */}
          <line x1={toX(0)} y1={toY(15.5)} x2={toX(wpX2)} y2={toY(Math.max(0, 15.5 - 0.5 * wpX2))} stroke="#f59e0b" strokeWidth="1.8" strokeDasharray="6,4" opacity="0.85" />
        </g>

        {/* X axis */}
        {X_TICKS.map(t => (
          <g key={`xt${t}`}>
            <line x1={toX(t)} y1={PAD.t + PH} x2={toX(t)} y2={PAD.t + PH + 5} stroke="rgba(255,255,255,0.35)" strokeWidth="0.8" />
            <text x={toX(t)} y={PAD.t + PH + 15} textAnchor="middle" fontSize="9.5" fontWeight="500" fill="#ffffff" opacity="0.85">{t}</text>
          </g>
        ))}

        {/* Y axis */}
        {Y_TICKS.map(t => (
          <g key={`yt${t}`}>
            <line x1={PAD.l - 5} y1={toY(t)} x2={PAD.l} y2={toY(t)} stroke="rgba(255,255,255,0.35)" strokeWidth="0.8" />
            <text x={PAD.l - 8} y={toY(t) + 3} textAnchor="end" fontSize="9.5" fontWeight="500" fill="#ffffff" opacity="0.85">{t}</text>
          </g>
        ))}

        {/* axis labels */}
        <text x={PAD.l + PW / 2} y={h - 6} textAnchor="middle" fontSize="9.5" fontWeight="600" fill="#ffffff" opacity="0.9" letterSpacing="0.6">
          AMOUNT OF IMPAIRED SKILLS &amp; ABILITIES — AISA (%)
        </text>
        <text x={14} y={PAD.t + PH / 2} textAnchor="middle" fontSize="9.5" fontWeight="600" fill="#ffffff" opacity="0.9" letterSpacing="0.6"
          transform={`rotate(-90,14,${PAD.t + PH / 2})`}>
          GENERAL CRITICALITY SCORE — GCS (%)
        </text>

        {/* data points — clipped so they never overflow the plot area */}
        <g clipPath="url(#ja-clip)">
          {matchResults.map(r => {
            const cx = toX(r.aisa_pct), cy = toY(r.gcs_pct);
            const active = r.job_id === jobA || r.job_id === jobB;
            return (
              <g key={r.job_id} style={{ cursor: 'pointer' }}
                onClick={() => onSelect(r.job_id)}
                onMouseEnter={() => setTooltip({ dataX: r.aisa_pct, dataY: r.gcs_pct, result: r })}
                onMouseLeave={() => setTooltip(null)}>
                {active && <circle cx={cx} cy={cy} r="11" fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth="1.4" />}
                <circle cx={cx} cy={cy} r={active ? 7 : 5.5} fill={r.suitability_color} opacity={active ? 1 : 0.82} />
              </g>
            );
          })}
        </g>

        {/* Crosshair guide lines on hover */}
        {tooltip && (
          <g style={{ pointerEvents: 'none' }}>
            <line x1={toX(tooltip.dataX)} y1={PAD.t} x2={toX(tooltip.dataX)} y2={PAD.t + PH} stroke="rgba(255,255,255,0.12)" strokeWidth="0.8" strokeDasharray="4,3" clipPath="url(#ja-clip)" />
            <line x1={PAD.l} y1={toY(tooltip.dataY)} x2={PAD.l + PW} y2={toY(tooltip.dataY)} stroke="rgba(255,255,255,0.12)" strokeWidth="0.8" strokeDasharray="4,3" clipPath="url(#ja-clip)" />
          </g>
        )}
      </svg>

      {/* Modern Glassmorphism Floating Pop-up */}
      {tooltip && (() => {
        const r = tooltip.result;
        const jobTitle = r.job_id.replace(/_/g, ' ');
        const px = toX(tooltip.dataX);
        const py = toY(tooltip.dataY);

        const tooltipWidth = 216;
        const isOnRightHalf = px > w - tooltipWidth - 30;
        const leftPos = isOnRightHalf ? px - tooltipWidth - 14 : px + 14;
        const topPos = Math.max(10, Math.min(py - 44, h - 96));

        const icon = r.suitability === 'SUITABLE' ? '✔' : r.suitability === 'SUITABLE WITH PRECAUTIONS' ? '⚠' : '✘';

        return (
          <div
            style={{
              position: 'absolute',
              left: leftPos,
              top: topPos,
              width: tooltipWidth,
              background: '#182c4a',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              borderRadius: '10px',
              padding: '11px 13px',
              boxShadow: '0 12px 30px rgba(0, 0, 0, 0.6), 0 4px 12px rgba(0, 0, 0, 0.4)',
              pointerEvents: 'none',
              zIndex: 30,
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}
          >
            {/* Job Title */}
            <div
              style={{
                fontSize: '0.86rem',
                fontWeight: 700,
                color: '#ffffff',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                lineHeight: 1.2,
              }}
              title={jobTitle}
            >
              {jobTitle}
            </div>

            {/* Metrics Row */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.72rem',
                color: 'rgba(255, 255, 255, 0.6)',
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid rgba(255, 255, 255, 0.06)',
                borderRadius: '6px',
                padding: '4px 8px',
              }}
            >
              <span>
                GCS: <strong style={{ color: '#ffffff', fontWeight: 600 }}>{r.gcs_pct.toFixed(1)}%</strong>
              </span>
              <span>
                AISA: <strong style={{ color: '#ffffff', fontWeight: 600 }}>{r.aisa_pct.toFixed(1)}%</strong>
              </span>
            </div>

            {/* Suitability Badge */}
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                alignSelf: 'flex-start',
                gap: '5px',
                padding: '3px 8px',
                borderRadius: '6px',
                fontSize: '0.68rem',
                fontWeight: 700,
                letterSpacing: '0.03em',
                color: r.suitability_color,
                background: `${r.suitability_color}18`,
                border: `1px solid ${r.suitability_color}40`,
                marginTop: '1px',
              }}
            >
              <span style={{ fontSize: '0.7rem' }}>{icon}</span>
              <span>{r.suitability}</span>
            </div>
          </div>
        );
      })()}
    </div>
  );
}





const CRIT_COLOR: Record<string, string> = {
  'not critical': 'rgba(255,255,255,0.30)',
  'SLIGHTLY CRITICAL': '#6aad8c',
  'MODERATELY CRITICAL': '#c4a83a',
  'RELEVANTLY CRITICAL': '#c47e45',
  'EXTREMELY CRITICAL': '#c04040',
};
const CRIT_RANK: Record<string, number> = {
  'not critical': 0,
  'SLIGHTLY CRITICAL': 1,
  'MODERATELY CRITICAL': 2,
  'RELEVANTLY CRITICAL': 3,
  'EXTREMELY CRITICAL': 4,
};
const ANCHOR_ICON = ['—', '↑', '↑↑', '↑↑↑'];

const CloseIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18"></line>
    <line x1="6" y1="6" x2="18" y2="18"></line>
  </svg>
);

const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"></polyline>
  </svg>
);



/* ═══════════════════════════════════════════════════════════════
   Sort types
═══════════════════════════════════════════════════════════════ */
export type SortCol = 'score' | 'anchor' | 'qualifier' | 'criticality_label';
export type SortDir = 'asc' | 'desc';
export type SortState = { col: SortCol; dir: SortDir }[];
type MainTab = 'map' | 'detail';

/* ═══════════════════════════════════════════════════════════════
   Main component
═══════════════════════════════════════════════════════════════ */
interface JobAnalysisViewProps {
  workerId: string;
  workerDisplayName: string;
}
export default function JobAnalysisView({ workerId, workerDisplayName }: JobAnalysisViewProps) {
  const [matchResults, setMatchResults] = useState<MatchResult[]>([]);
  const [loadingMatch, setLoadingMatch] = useState(true);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [mainTab, setMainTab] = useState<MainTab>('map');

  const [jobA, setJobA] = useState<string | null>(null);
  const [skillDataA, setSkillDataA] = useState<SkillDetailResponse | null>(null);
  const [loadingA, setLoadingA] = useState(false);
  const [menuOpenA, setMenuOpenA] = useState(false);
  const [sortsA, setSortsA] = useState<SortState>([]);
  const [skillSearchA, setSkillSearchA] = useState('');
  const [showSearchA, setShowSearchA] = useState(false);
  const [expandedSkillA, setExpandedSkillA] = useState<string | null>(null);

  const [splitMode, setSplitMode] = useState(false);
  const [jobB, setJobB] = useState<string | null>(null);
  const [skillDataB, setSkillDataB] = useState<SkillDetailResponse | null>(null);
  const [loadingB, setLoadingB] = useState(false);
  const [menuOpenB, setMenuOpenB] = useState(false);
  const [sortsB, setSortsB] = useState<SortState>([]);
  const [skillSearchB, setSkillSearchB] = useState('');
  const [showSearchB, setShowSearchB] = useState(false);
  const [expandedSkillB, setExpandedSkillB] = useState<string | null>(null);

  /* ── Edit Jobs modal ────────────────────────────────────────────────────── */
  const [editJobsOpen, setEditJobsOpen] = useState(false);
  const [allOntologyJobs, setAllOntologyJobs] = useState<JobEntry[]>([]);
  const [loadingAllJobs, setLoadingAllJobs] = useState(false);
  const [draftJobIds, setDraftJobIds] = useState<Set<string>>(new Set());
  const [jobSearch, setJobSearch] = useState('');
  const [savingJobs, setSavingJobs] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);


  /* ── Per-worker session cache ──────────────────────────────────────────
     Saves each worker's job-comparison state so switching back restores it.
     Only jobA/jobB/splitMode/sorts are saved; skill data is re-fetched.
  ─────────────────────────────────────────────────────────────────────── */
  type WorkerSession = {
    jobA: string | null; jobB: string | null; splitMode: boolean;
    sortsA: SortState; sortsB: SortState;
    skillSearchA: string; skillSearchB: string;
  };
  const sessionCache = useRef<Record<string, WorkerSession>>({});
  // Tracks the current mutable values so the cleanup closure is never stale
  const liveState = useRef<WorkerSession>({
    jobA: null, jobB: null, splitMode: false,
    sortsA: [], sortsB: [],
    skillSearchA: '', skillSearchB: '',
  });
  liveState.current = { jobA, jobB, splitMode, sortsA, sortsB, skillSearchA, skillSearchB };
  // Signals the fetch effect NOT to auto-select the first job (restored session exists)
  const skipAutoSelectRef = useRef(false);

  /* Save outgoing worker session → restore incoming worker session */
  useEffect(() => {
    return () => {
      // This runs when workerId is about to change (cleanup of the previous effect).
      // Save the current live state under the old workerId.
      // We read from sessionCache to know the last saved workerId key:
      // simply store keyed by the workerId value captured in this closure.
      sessionCache.current[workerId] = { ...liveState.current };
    };
  }, [workerId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const saved = sessionCache.current[workerId];
    if (saved) {
      // Restore previous session for this worker
      skipAutoSelectRef.current = true;
      setJobA(saved.jobA);
      setJobB(saved.jobB);
      setSplitMode(saved.splitMode);
      setSortsA(saved.sortsA);
      setSortsB(saved.sortsB);
      setSkillSearchA(saved.skillSearchA);
      setSkillSearchB(saved.skillSearchB);
    } else {
      // First visit — reset to empty; fetch effect will auto-pick first job
      skipAutoSelectRef.current = false;
      setJobA(null);
      setJobB(null);
      setSplitMode(false);
      setSortsA([]);
      setSortsB([]);
      setSkillSearchA('');
      setSkillSearchB('');
    }
    // Always clear fetched data — it will be re-fetched for the new worker
    setMatchResults([]);
    setSkillDataA(null);
    setSkillDataB(null);
    setMenuOpenA(false);
    setMenuOpenB(false);
    setShowSearchB(false);
  }, [workerId]); // eslint-disable-line react-hooks/exhaustive-deps

  /* fetch match results */
  useEffect(() => {
    setLoadingMatch(true); setMatchError(null);
    fetchMatchResults(workerId)
      .then(r => {
        setMatchResults(r);
        if (r.length && !skipAutoSelectRef.current) setJobA(r[0].job_id);
        skipAutoSelectRef.current = false;
      })
      .catch(e => setMatchError(e.message ?? 'Failed to load'))
      .finally(() => setLoadingMatch(false));
  }, [workerId]);



  useEffect(() => {
    if (!jobA) return;
    setLoadingA(true);
    fetchSkillDetail(workerId, jobA).then(setSkillDataA).catch(console.error).finally(() => setLoadingA(false));
  }, [workerId, jobA]);

  useEffect(() => {
    if (!jobB) return;
    setLoadingB(true);
    fetchSkillDetail(workerId, jobB).then(setSkillDataB).catch(console.error).finally(() => setLoadingB(false));
  }, [workerId, jobB]);

  const toggleSplit = () => {
    if (splitMode) {
      setSplitMode(false); setJobB(null); setSkillDataB(null); setMenuOpenB(false);
    } else {
      const idx = matchResults.findIndex(r => r.job_id === jobA);
      setJobB(matchResults[(idx + 1) % matchResults.length]?.job_id ?? null);
      setSplitMode(true);
    }
  };

  const doSort = (col: SortCol, sorts: SortState, setSorts: (s: SortState) => void) => {
    const idx = sorts.findIndex(s => s.col === col);
    if (idx >= 0) {
      const currentDir = sorts[idx].dir;
      const newSorts = [...sorts];
      if (currentDir === 'asc') {
        newSorts[idx].dir = 'desc';
      } else {
        newSorts.splice(idx, 1);
      }
      setSorts(newSorts);
    } else {
      setSorts([...sorts, { col, dir: 'asc' }]);
    }
  };

  const sortIcon = (col: SortCol, sorts: SortState) => {
    const idx = sorts.findIndex(s => s.col === col);
    if (idx === -1) return <span className="ja-sort-icon">⇅</span>;
    const s = sorts[idx];
    const n = sorts.length > 1 ? <sub style={{ fontSize: '0.7em', marginLeft: 1, verticalAlign: 'baseline' }}>{idx + 1}</sub> : null;
    return <span className="ja-sort-badge">{s.dir === 'asc' ? '↑' : '↓'}{n}</span>;
  };

  /* KPI stats */
  const stats = useMemo(() => ({
    total: matchResults.length,
    suitable: matchResults.filter(r => r.suitability === 'SUITABLE').length,
    precaution: matchResults.filter(r => r.suitability === 'SUITABLE WITH PRECAUTIONS').length,
    unsuitable: matchResults.filter(r => r.suitability === 'NOT SUITABLE').length,
    avgGCS: matchResults.length ? matchResults.reduce((s, r) => s + r.gcs_pct, 0) / matchResults.length : 0,
    avgAISA: matchResults.length ? matchResults.reduce((s, r) => s + r.aisa_pct, 0) / matchResults.length : 0,
  }), [matchResults]);

  /* ── Edit Jobs modal handlers ─────────────────────────────────────────── */
  const openEditJobs = useCallback(async () => {
    setEditJobsOpen(true);
    setSaveError(null);
    setJobSearch('');
    // Initialise draft from current match results
    setDraftJobIds(new Set(matchResults.map(r => r.job_id)));
    // Lazy-load full job catalogue only once
    if (allOntologyJobs.length === 0) {
      setLoadingAllJobs(true);
      try {
        const jobs = await fetchAllJobs();
        setAllOntologyJobs(jobs);
      } catch (e: any) {
        setSaveError(e?.message ?? 'Failed to load job catalogue.');
      } finally {
        setLoadingAllJobs(false);
      }
    }
  }, [matchResults, allOntologyJobs.length]);

  const saveJobAssignment = useCallback(async () => {
    setSavingJobs(true);
    setSaveError(null);
    try {
      await updateWorkerJobs(workerId, Array.from(draftJobIds));
      // Reload match results for the new assignment
      setLoadingMatch(true);
      setMatchError(null);
      const results = await fetchMatchResults(workerId);
      setMatchResults(results);
      if (results.length) setJobA(results[0].job_id);
      setJobB(null);
      setSplitMode(false);
      setSkillDataA(null);
      setSkillDataB(null);
      setEditJobsOpen(false);
    } catch (e: any) {
      setSaveError(e?.message ?? 'Failed to save job assignment.');
    } finally {
      setSavingJobs(false);
      setLoadingMatch(false);
    }
  }, [workerId, draftJobIds]);


  /* ── Job picker dropdown ── */
  const renderPicker = (
    panelId: 'A' | 'B',
    jobId: string | null, setJobId: (id: string) => void,
    open: boolean, setOpen: (v: boolean) => void,
  ) => {
    const r = matchResults.find(m => m.job_id === jobId);
    const otherJobId = panelId === 'A' ? jobB : jobA;
    return (
      <div className="ja-picker-wrap">
        <button className="ja-picker-btn" onClick={() => setOpen(!open)}>
          {r && <span className="ja-picker-dot" style={{ background: r.suitability_color }} />}
          {r ? r.job_id.replace(/_/g, ' ') : 'Select…'}
          <span className="ja-picker-chevron">{open ? '▲' : '▼'}</span>
        </button>
        {open && (
          <div className="ja-picker-menu">
            {matchResults
              .filter(m => !splitMode || m.job_id !== otherJobId)
              .map(m => (
                <button key={m.job_id} className={`ja-picker-item${m.job_id === jobId ? ' active' : ''}`}
                  onClick={() => { setJobId(m.job_id); setOpen(false); }}>
                  <span className="ja-picker-dot" style={{ background: m.suitability_color }} />
                  {m.job_id.replace(/_/g, ' ')}
                </button>
              ))}
          </div>
        )}
      </div>
    );
  };

  /* ── Skills table ── */
  const renderSkillsTable = (
    panelId: 'A' | 'B',
    jobId: string | null, setJobId: (id: string) => void,
    skillData: SkillDetailResponse | null, loading: boolean,
    open: boolean, setOpen: (v: boolean) => void,
    sorts: SortState, setSorts: (s: SortState) => void,
    search: string, setSearch: (v: string) => void,
    showSearch: boolean, setShowSearch: (v: boolean) => void,
    expandedSkill: string | null, setExpandedSkill: (id: string | null) => void,
  ) => {
    const result = matchResults.find(r => r.job_id === jobId) ?? null;
    if (!result) return null;

    // Filter
    const filteredSkills = (skillData?.skills ?? []).filter(s =>
      s.id.replace(/_/g, ' ').toLowerCase().includes(search.toLowerCase())
    );

    // Sort
    const sorted = [...filteredSkills].sort((a, b) => {
      for (const { col, dir } of sorts) {
        if (a[col] === b[col]) continue;
        const dirMult = dir === 'asc' ? 1 : -1;
        if (col === 'criticality_label') {
          const rankA = CRIT_RANK[a.criticality_label as string] ?? -1;
          const rankB = CRIT_RANK[b.criticality_label as string] ?? -1;
          if (rankA !== rankB) return dirMult * (rankA - rankB);
          continue;
        }
        return dirMult * ((a[col] as number) - (b[col] as number));
      }
      return 0;
    });
    return (
      <div className="ja-detail-pane">
        <div className="ja-detail-hdr" style={{
          flexDirection: splitMode ? 'column' : 'row',
          alignItems: splitMode ? 'stretch' : 'center',
          gap: splitMode ? '8px' : '12px',
          height: splitMode ? '84px' : 'auto',
          boxSizing: 'border-box'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', height: splitMode ? '28px' : 'auto', flexShrink: 0 }}>
            {splitMode && <span className="ja-split-lbl">{panelId}</span>}
            {renderPicker(panelId, jobId, setJobId, open, setOpen)}
            {splitMode && panelId === 'B' && (
              <button className="ja-btn-close-split" onClick={toggleSplit} title="Close compare" style={{ marginLeft: 'auto' }}>✕</button>
            )}
            {!splitMode && panelId === 'A' && (
              <button className="ja-btn-split" onClick={toggleSplit}>⊞ Compare</button>
            )}
          </div>

          <div style={{
            display: 'flex', alignItems: 'center', gap: '12px',
            marginLeft: splitMode ? '0' : 'auto',
            justifyContent: 'space-between'
          }}>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <span className="ja-metric">GCS <strong>{result.gcs_pct.toFixed(2)}%</strong></span>
              <span className="ja-metric">AISA <strong>{result.aisa_pct.toFixed(2)}%</strong></span>
              <span className="ja-metric">N skills <strong>{result.n_total}</strong></span>
            </div>
            <span className="ja-suit-badge"
              style={{ color: result.suitability_color, borderColor: result.suitability_color + '45', background: result.suitability_color + '12', whiteSpace: 'nowrap' }}>
              {result.suitability === 'SUITABLE' ? '✔' : result.suitability === 'SUITABLE WITH PRECAUTIONS' ? '⚠' : '✘'}{' '}
              {result.suitability}
            </span>
          </div>
        </div>
        <div className={`ja-skills-wrap${splitMode ? ' ja-skills-wrap--split' : ''}`} style={{ position: 'relative' }}>
          {loading && skillData && (
            <div className="ja-center" style={{ position: 'absolute', inset: 0, background: 'rgba(26,46,74,0.5)', zIndex: 10 }}>
              <div className="wp-spinner" />
            </div>
          )}
          {loading && !skillData ? (
            <div className="ja-center"><div className="wp-spinner" /><span className="ja-status-txt">Loading…</span></div>
          ) : skillData && skillData.skills.length > 0 ? (
            <table className={`ja-skills-tbl${splitMode ? ' ja-skills-tbl--split' : ''}`} style={{ opacity: loading ? 0.55 : 1, transition: 'opacity 0.2s' }}>
              <thead>
                <tr>
                  <th className="ja-th-searchable" onClick={() => !showSearch && setShowSearch(true)}>
                    {!showSearch && !search ? (
                      <div className="ja-th-search-lbl">
                        <span>Skill / Ability</span><span className="ja-search-icon">🔍</span>
                      </div>
                    ) : (
                      <div className="ja-th-search-wrap">
                        <input
                          autoFocus
                          className="ja-th-search-input"
                          value={search}
                          onChange={e => setSearch(e.target.value)}
                          onBlur={() => { if (!search) setShowSearch(false); }}
                          placeholder="Search skill..."
                        />
                        {search && (
                          <span className="ja-th-search-clear" onClick={(e) => { e.stopPropagation(); setSearch(''); setShowSearch(false); }}>✕</span>
                        )}
                      </div>
                    )}
                  </th>
                  <th className={`ja-th-sort${sorts.some(s => s.col === 'score') ? ' active' : ''}`}
                    onClick={() => doSort('score', sorts, setSorts)}>
                    Score {sortIcon('score', sorts)}</th>
                  {!splitMode && (
                    <th className={`ja-th-sort${sorts.some(s => s.col === 'anchor') ? ' active' : ''}`}
                      onClick={() => doSort('anchor', sorts, setSorts)}>
                      Importance {sortIcon('anchor', sorts)}</th>
                  )}
                  <th className={`ja-th-sort${sorts.some(s => s.col === 'qualifier') ? ' active' : ''}`}
                    onClick={() => doSort('qualifier', sorts, setSorts)}>
                    Qualifier {sortIcon('qualifier', sorts)}</th>
                  {!splitMode && <th>CS</th>}
                  {!splitMode && <th className="ja-th-bar">CS bar</th>}
                  <th className={`ja-th-sort${sorts.some(s => s.col === 'criticality_label') ? ' active' : ''}`}
                    onClick={() => doSort('criticality_label', sorts, setSorts)}>
                    Criticality {sortIcon('criticality_label', sorts)}</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((s, i) => {
                  const col = CRIT_COLOR[s.criticality_label] ?? 'rgba(255,255,255,0.4)';
                  const barW = Math.min((s.cs / 12) * 100, 100);
                  const rowKey = `${s.id}-${i}`;
                  const isExpanded = expandedSkill === rowKey;
                  const hasDesc = s.description && s.description.trim().length > 0;
                  return (
                    <>
                      <tr
                        key={rowKey}
                        className={`ja-skill-row${hasDesc ? ' ja-skill-row--clickable' : ''}${isExpanded ? ' ja-skill-row--expanded' : ''}`}
                        onClick={() => hasDesc && setExpandedSkill(isExpanded ? null : rowKey)}
                        title={hasDesc ? 'Click to see O*NET definition' : undefined}
                      >
                        <td className="ja-td-skill" style={{ color: col }}>
                          <div className="ja-skill-name-cell">
                            {hasDesc && (
                              <span className={`ja-row-expander-arrow${isExpanded ? ' is-expanded' : ''}`} aria-hidden="true">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                  <polyline points="6 9 12 15 18 9"></polyline>
                                </svg>
                              </span>
                            )}
                            <span className="ja-skill-name">{s.id.replace(/_/g, ' ')}</span>
                          </div>
                        </td>
                        <td className="ja-td-num">{s.score}</td>
                        {!splitMode && (
                          <td className="ja-td-num">
                            <span className={`ja-anchor ja-anchor-${s.anchor}`}>{ANCHOR_ICON[s.anchor] ?? '—'}</span>
                          </td>
                        )}
                        <td className="ja-td-num">{s.qualifier}</td>
                        {!splitMode && <td className="ja-td-num"><strong style={{ color: col }}>{s.cs}</strong></td>}
                        {!splitMode && (
                          <td className="ja-td-bar">
                            <div className="ja-cs-bar-track">
                              <div className="ja-cs-bar-fill" style={{ width: `${barW}%`, background: col }} />
                            </div>
                          </td>
                        )}
                        <td className="ja-td-crit" style={{ color: col }}>{s.criticality_label}</td>
                      </tr>
                      {isExpanded && hasDesc && (
                        <tr key={`${rowKey}-desc`} className="ja-desc-row">
                          <td colSpan={splitMode ? 4 : 7} className="ja-desc-cell">
                            <p className="ja-desc-text">{s.description}</p>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p className="ja-status-txt" style={{ padding: '20px 16px' }}>No skill data available.</p>
          )}
        </div>
      </div>
    );
  };

  /* ── Guards ── */
  if (loadingMatch && !matchResults.length) return (
    <div className="ja-root"><div className="ja-center"><div className="wp-spinner" /><span className="ja-status-txt">Loading job analysis…</span></div></div>
  );
  if (matchError) return (
    <div className="ja-root"><div className="ja-center"><span className="ja-err-icon">⚠</span><p className="ja-status-txt">{matchError}</p></div></div>
  );
  if (!matchResults.length) return (
    <div className="ja-root">
      <div className="ja-center">
        <p className="ja-status-txt">No job evaluation data for this worker.</p>
        <p className="ja-status-hint">Ensure the worker has <code>isSelected = true</code> and <code>isEvaluatedForJob</code> triples.</p>
      </div>
    </div>
  );

  /* ── Main render ── */
  return (
    <div className="ja-root">
      {editJobsOpen ? (
        <div className="hc-wizard-modal" style={{ animation: 'contentFadeIn 0.35s cubic-bezier(0.2, 0.8, 0.2, 1) forwards' }}>
          {/* Header */}
          <div className="hc-wizard-header">
            <div>
              <h2 className="hc-wizard-title">Edit Job Assignments</h2>
              <p className="hc-wizard-subtitle">
                {workerDisplayName} — select jobs to evaluate from the ontology
              </p>
            </div>
            <button className="hc-wizard-close-btn" onClick={() => setEditJobsOpen(false)} disabled={savingJobs} aria-label="Close dialog"><CloseIcon /></button>
          </div>

          {/* Content area */}
          <div className="hc-wizard-content">
            {/* Toolbar: Search input + Actions */}
            <div className="hc-wizard-toolbar">
              <div className="hc-search-wrapper" style={{ maxWidth: '360px' }}>
                <span className="hc-search-icon">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                </span>
                <input
                  type="text"
                  className="hc-search-input"
                  placeholder="Search jobs..."
                  value={jobSearch}
                  onChange={e => setJobSearch(e.target.value)}
                  autoFocus
                />
                {jobSearch && (
                  <button
                    className="hc-toast-close"
                    style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    onClick={() => setJobSearch('')}
                  >
                    ✕
                  </button>
                )}
              </div>

              <span className="ja-modal-counter" style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>
                <strong style={{ color: '#ffffff', fontWeight: 700 }}>{draftJobIds.size}</strong> / {allOntologyJobs.length} selected
              </span>

              {/* Quick actions (Select all / Clear all) */}
              <div style={{ display: 'flex', gap: '8px', marginLeft: 'auto' }}>
                <button className="ja-modal-action-btn" onClick={() => setDraftJobIds(new Set(allOntologyJobs.map(j => j.id)))}>Select all</button>
                <button className="ja-modal-action-btn" onClick={() => setDraftJobIds(new Set())}>Clear all</button>
              </div>
            </div>

            {/* Job list */}
            <div className="hc-wizard-table-container">
              {loadingAllJobs ? (
                <div className="ja-center" style={{ padding: '40px' }}>
                  <div className="wp-spinner" />
                  <span className="ja-status-txt">Loading job catalogue…</span>
                </div>
              ) : (
                <table className="hc-wizard-table">
                  <thead>
                    <tr>
                      <th style={{ width: 60 }}><CheckIcon /></th>
                      <th style={{ width: '45%' }}>Job Label</th>
                      <th>ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allOntologyJobs
                      .filter(j => j.label.toLowerCase().includes(jobSearch.toLowerCase()) || j.id.toLowerCase().includes(jobSearch.toLowerCase()))
                      .map(job => {
                        const checked = draftJobIds.has(job.id);
                        const toggle = () => setDraftJobIds(prev => {
                          const next = new Set(prev);
                          if (checked) next.delete(job.id); else next.add(job.id);
                          return next;
                        });
                        return (
                          <tr
                            key={job.id}
                            className={checked ? 'selected-row' : ''}
                            onClick={toggle}
                          >
                            <td>
                              <div className={`hc-checkbox ${checked ? 'checked' : ''}`}>
                                {checked && <CheckIcon />}
                              </div>
                            </td>
                            <td style={{ color: 'rgba(255, 255, 255, 0.9)' }}>
                              {job.label}
                            </td>
                            <td className="hc-table-code" style={{ opacity: checked ? 1 : 0.6 }}>
                              {job.id}
                            </td>
                          </tr>
                        );
                      })
                    }
                  </tbody>
                </table>
              )}
              {!loadingAllJobs && allOntologyJobs.length > 0 &&
                allOntologyJobs.filter(j => j.label.toLowerCase().includes(jobSearch.toLowerCase()) || j.id.toLowerCase().includes(jobSearch.toLowerCase())).length === 0 && (
                  <p className="ja-status-txt" style={{ padding: '24px 16px', textAlign: 'center' }}>No jobs match "{jobSearch}".</p>
                )}
            </div>

            {/* Error messaging */}
            {saveError && (
              <div className="hc-wizard-error" style={{ margin: '12px 0 0 0' }}>
                ⚠ {saveError}
              </div>
            )}
          </div>

          {/* Footer (direct child of hc-wizard-modal, same structure as HealthConditionWizard) */}
          <div className="hc-wizard-footer">
            <div className="hc-footer-left">
              {draftJobIds.size} items selected
            </div>
            <div className="hc-footer-right">
              <button
                className="hc-btn-primary"
                onClick={saveJobAssignment}
                disabled={savingJobs}
              >
                {savingJobs ? (
                  <>
                    <span className="wp-spinner" style={{ width: 14, height: 14, borderWidth: 2, marginRight: 6 }} />
                    Saving & Re-running Pellet…
                  </>
                ) : (
                  <>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 6 }}>
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    Save Assignment
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <>
          {/* KPI strip */}
          <div className="ja-kpi-row">
            <div className="ja-kpi">
              <span className="ja-kpi-val">{stats.total}</span>
              <span className="ja-kpi-lbl">Jobs evaluated</span>
            </div>
            <div className="ja-kpi">
              <span className="ja-kpi-val" style={{ color: '#5bbf82' }}>{stats.suitable}</span>
              <span className="ja-kpi-lbl">Suitable</span>
            </div>
            <div className="ja-kpi">
              <span className="ja-kpi-val" style={{ color: '#c4a83a' }}>{stats.precaution}</span>
              <span className="ja-kpi-lbl">With precautions</span>
            </div>
            <div className="ja-kpi">
              <span className="ja-kpi-val" style={{ color: '#c04040' }}>{stats.unsuitable}</span>
              <span className="ja-kpi-lbl">Not suitable</span>
            </div>
            <div className="ja-kpi">
              <span className="ja-kpi-val">{stats.avgGCS.toFixed(1)}%</span>
              <span className="ja-kpi-lbl">Avg GCS</span>
            </div>
            <div className="ja-kpi">
              <span className="ja-kpi-val">{stats.avgAISA.toFixed(1)}%</span>
              <span className="ja-kpi-lbl">Avg AISA</span>
            </div>
          </div>

          {/* Tab bar */}
          <div className="ja-tab-bar">
            <button className={`ja-tab${mainTab === 'map' ? ' active' : ''}`} onClick={() => setMainTab('map')}>Suitability Map</button>
            <button className={`ja-tab${mainTab === 'detail' ? ' active' : ''}`} onClick={() => setMainTab('detail')}>Skill Detail</button>
          </div>

          {/* ── MAP tab ── */}
          {mainTab === 'map' && (
            <div className="ja-tab-content">
              <div className="ja-map-body">
                <div className="ja-scatter-area">
                  <div className="ja-scatter-legend">
                    {[
                      {
                        label: 'Not suitable',
                        color: '#ef4444',
                        formula: 'GCS > −0.5·AISA + 21',
                        description: 'High criticality on essential job capabilities. The position exceeds the safety threshold and is not recommended without substantial adaptations.',
                      },
                      {
                        label: 'With precautions',
                        color: '#f59e0b',
                        formula: '−0.5·AISA + 15.5 ≤ GCS ≤ 21',
                        description: 'Moderate criticality score. The worker can perform the position with specific ergonomic precautions, assistive devices, or task accommodations.',
                      },
                      {
                        label: 'Suitable',
                        color: '#22c55e',
                        formula: 'GCS < −0.5·AISA + 15.5',
                        description: 'Low criticality score and minimal impairment. The worker is fully compatible with this job position under standard operational conditions.',
                      },
                    ].map(item => (
                      <span key={item.label} className="ja-legend-item">
                        <span className="ja-legend-dot" style={{ background: item.color }} />
                        {item.label}
                        <div className="ja-legend-tooltip">
                          <div className="ja-legend-tooltip-header">
                            <span className="ja-legend-tooltip-title">
                              <span className="ja-legend-dot" style={{ background: item.color }} />
                              {item.label}
                            </span>
                          </div>
                          <div className="ja-legend-tooltip-formula-box">
                            <div className="ja-legend-tooltip-formula-lbl">Threshold</div>
                            <div className="ja-legend-tooltip-formula-val">{item.formula}</div>
                          </div>
                          <div className="ja-legend-tooltip-desc">
                            {item.description}
                          </div>
                        </div>
                      </span>
                    ))}
                  </div>
                  <ScatterPlot
                    matchResults={matchResults}
                    jobA={jobA}
                    jobB={jobB}
                    onSelect={id => setJobA(id)}
                  />
                </div>
                <div className="ja-jobs-sidebar">
                  <div className="ja-jobs-sidebar-hdr">
                    <span className="ja-jobs-sidebar-title">Jobs</span>
                    <button
                      className="ja-btn-edit-jobs-compact"
                      id="btn-edit-jobs"
                      onClick={openEditJobs}
                      title="Edit assigned jobs for this worker"
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                      </svg>
                      Edit Jobs
                    </button>
                  </div>
                  <ul className="ja-jobs-list" role="listbox">
                    {[...matchResults].sort((a, b) => {
                      const rank: Record<string, number> = { 'NOT SUITABLE': 0, 'SUITABLE WITH PRECAUTIONS': 1, 'SUITABLE': 2 };
                      const rankA = rank[a.suitability] ?? 3;
                      const rankB = rank[b.suitability] ?? 3;
                      if (rankA !== rankB) return rankA - rankB;
                      return a.job_id.localeCompare(b.job_id);
                    }).map(r => (
                      <li key={r.job_id} role="option" aria-selected={r.job_id === jobA}
                        className={`ja-job-item${r.job_id === jobA ? ' selected' : ''}`}
                        onClick={() => setJobA(r.job_id)}>
                        <span className="ja-job-dot" style={{ background: r.suitability_color }} />
                        <span className="ja-job-label">{r.job_id.replace(/_/g, ' ')}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* ── DETAIL tab ── */}
          {mainTab === 'detail' && (
            <div className="ja-tab-content">
              <div className="ja-detail-body">
                <div className="ja-detail-split">
                  {jobA && renderSkillsTable(
                    'A', jobA, setJobA, skillDataA, loadingA, menuOpenA, setMenuOpenA,
                    sortsA, setSortsA, skillSearchA, setSkillSearchA, showSearchA, setShowSearchA,
                    expandedSkillA, setExpandedSkillA,
                  )}
                  {splitMode && jobB && renderSkillsTable(
                    'B', jobB, setJobB, skillDataB, loadingB, menuOpenB, setMenuOpenB,
                    sortsB, setSortsB, skillSearchB, setSkillSearchB, showSearchB, setShowSearchB,
                    expandedSkillB, setExpandedSkillB,
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}