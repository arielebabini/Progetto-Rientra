import { useState, useEffect } from 'react';

import './JobAnalysisView.css';
import {
  fetchMatchResults,
  fetchSkillDetail,
  type MatchResult,
  type SkillDetailResponse,
} from '../api/semanticService';

/* ─────────────────────────────────────────────
   SVG scatter plot — coordinate system
───────────────────────────────────────────── */
const VB_W = 600;
const VB_H = 265;
const PAD = { l: 62, r: 28, t: 24, b: 52 };
const PW = VB_W - PAD.l - PAD.r;
const PH = VB_H - PAD.t - PAD.b;

const X_MAX = 55;
const Y_MAX = 25;

function svgX(aisa: number) { return PAD.l + (aisa / X_MAX) * PW; }
function svgY(gcs: number) { return PAD.t + PH - (gcs / Y_MAX) * PH; }

function zonePoly(zone: 'green' | 'yellow' | 'red'): string {
  let pts: [number, number][];
  if (zone === 'green') pts = [[0, 0], [31, 0], [0, 15.5]];
  else if (zone === 'yellow') pts = [[0, 15.5], [31, 0], [42, 0], [0, 21]];
  else pts = [[0, 21], [42, 0], [X_MAX, 0], [X_MAX, Y_MAX], [0, Y_MAX]];
  return pts.map(([a, g]) => `${svgX(a)},${svgY(g)}`).join(' ');
}

const X_TICKS = [0, 10, 20, 30, 40, 50];
const Y_TICKS = [0, 5, 10, 15, 20, 25];

/* ─────────────────────────────────────────────
   Colour maps
───────────────────────────────────────────── */
const CRIT_COLOR: Record<string, string> = {
  'not critical': 'rgba(255,255,255,0.3)',
  'SLIGHTLY CRITICAL': '#7dc8a3',
  'MODERATELY CRITICAL': '#dbc468',
  'RELEVANTLY CRITICAL': '#db9f6c',
  'EXTREMELY CRITICAL': '#d24444ff',
};

const ANCHOR_ICON = ['—', '↑', '↑↑', '↑↑↑'];

/* ─────────────────────────────────────────────
   Sort types (shared between panels)
───────────────────────────────────────────── */
type SortCol = 'score' | 'anchor' | 'qualifier' | null;
type SortDir = 'asc' | 'desc' | null;

/* ─────────────────────────────────────────────
   Component
───────────────────────────────────────────── */
interface JobAnalysisViewProps {
  workerId: string;
  workerDisplayName: string;
}

interface TooltipState {
  dataX: number;
  dataY: number;
  result: MatchResult;
}

export default function JobAnalysisView({ workerId, workerDisplayName }: JobAnalysisViewProps) {
  const [matchResults, setMatchResults] = useState<MatchResult[]>([]);
  const [loadingMatch, setLoadingMatch] = useState(true);
  const [matchError, setMatchError]     = useState<string | null>(null);
  const [tooltip, setTooltip]           = useState<TooltipState | null>(null);

  /* ── Panel A (primary) ── */
  const [jobA, setJobA]           = useState<string | null>(null);
  const [skillDataA, setSkillDataA] = useState<SkillDetailResponse | null>(null);
  const [loadingA, setLoadingA]   = useState(false);
  const [menuOpenA, setMenuOpenA] = useState(false);
  const [sortColA, setSortColA]   = useState<SortCol>(null);
  const [sortDirA, setSortDirA]   = useState<SortDir>(null);

  /* ── Panel B (split) ── */
  const [splitMode, setSplitMode] = useState(false);
  const [jobB, setJobB]           = useState<string | null>(null);
  const [skillDataB, setSkillDataB] = useState<SkillDetailResponse | null>(null);
  const [loadingB, setLoadingB]   = useState(false);
  const [menuOpenB, setMenuOpenB] = useState(false);
  const [sortColB, setSortColB]   = useState<SortCol>(null);
  const [sortDirB, setSortDirB]   = useState<SortDir>(null);

  /* ── Fetch match results ── */
  useEffect(() => {
    setLoadingMatch(true);
    setMatchError(null);

    fetchMatchResults(workerId)
      .then(results => {
        setMatchResults(results);
        if (results.length > 0) setJobA(results[0].job_id);
      })
      .catch(e => setMatchError(e.message ?? 'Failed to load match results'))
      .finally(() => setLoadingMatch(false));
  }, [workerId]);

  /* ── Fetch skills for Panel A ── */
  useEffect(() => {
    if (!jobA) return;
    setLoadingA(true);
    fetchSkillDetail(workerId, jobA)
      .then(setSkillDataA)
      .catch(e => console.error('fetchSkillDetail A:', e))
      .finally(() => setLoadingA(false));
  }, [workerId, jobA]);

  /* ── Fetch skills for Panel B ── */
  useEffect(() => {
    if (!jobB) return;
    setLoadingB(true);
    fetchSkillDetail(workerId, jobB)
      .then(setSkillDataB)
      .catch(e => console.error('fetchSkillDetail B:', e))
      .finally(() => setLoadingB(false));
  }, [workerId, jobB]);

  /* ── Toggle split mode ── */
  const toggleSplit = () => {
    if (splitMode) {
      setSplitMode(false);
      setJobB(null);
      setSkillDataB(null);
      setMenuOpenB(false);
    } else {
      // Default second job to the next one after A (or first)
      const idx = matchResults.findIndex(r => r.job_id === jobA);
      const nextIdx = (idx + 1) % matchResults.length;
      setJobB(matchResults[nextIdx]?.job_id ?? matchResults[0]?.job_id ?? null);
      setSplitMode(true);
    }
  };

  /* ── Sort helpers ── */
  const makeSortHandler = (
    col: SortCol,
    curCol: SortCol, setCol: (c: SortCol) => void,
    curDir: SortDir, setDir: (d: SortDir) => void
  ) => {
    if (curCol !== col) { setCol(col); setDir('asc'); return; }
    if (curDir === 'asc') { setDir('desc'); return; }
    setCol(null); setDir(null);
  };

  const makeSortIcon = (col: SortCol, curCol: SortCol, curDir: SortDir) => {
    if (curCol !== col) return <span className="ja-sort-icon">⇅</span>;
    return <span className="ja-sort-badge">{curDir === 'asc' ? '↑' : '↓'}</span>;
  };

  /* ── Tooltip render ── */
  const renderTooltip = () => {
    if (!tooltip) return null;
    const r = tooltip.result;
    const label = r.job_id.replace(/_/g, ' ');
    const truncated = label.length > 22 ? label.slice(0, 22) + '…' : label;
    const bw = 164, bh = 64;
    const px = svgX(tooltip.dataX), py = svgY(tooltip.dataY);
    const tx = px + 14 + bw > VB_W - PAD.r ? px - bw - 14 : px + 14;
    const ty = Math.max(PAD.t + 4, Math.min(py - bh / 2, PAD.t + PH - bh - 4));
    return (
      <g style={{ pointerEvents: 'none' }}>
        <line x1={px} y1={PAD.t} x2={px} y2={PAD.t + PH}
          stroke="rgba(255,255,255,0.15)" strokeWidth="1" strokeDasharray="4,3" clipPath="url(#ja-clip)" />
        <line x1={PAD.l} y1={py} x2={PAD.l + PW} y2={py}
          stroke="rgba(255,255,255,0.15)" strokeWidth="1" strokeDasharray="4,3" clipPath="url(#ja-clip)" />
        <rect x={tx+2} y={ty+2} width={bw} height={bh} rx="8" fill="rgba(0,0,0,0.4)" />
        <rect x={tx} y={ty} width={bw} height={bh} rx="8"
          fill="rgba(8,18,38,0.96)" stroke={r.suitability_color} strokeWidth="1.2" strokeOpacity="0.7" />
        <rect x={tx} y={ty} width="4" height={bh} rx="4" fill={r.suitability_color} opacity="0.9" />
        <text x={tx+13} y={ty+17} fontSize="10.5" fontWeight="700" fill="rgba(255,255,255,0.93)">{truncated}</text>
        <text x={tx+13} y={ty+33} fontSize="9.5" fill="rgba(255,255,255,0.5)">
          {'GCS: '}<tspan fontWeight="600" fill="rgba(255,255,255,0.85)">{r.gcs_pct.toFixed(1)}%</tspan>
          {'   AISA: '}<tspan fontWeight="600" fill="rgba(255,255,255,0.85)">{r.aisa_pct.toFixed(1)}%</tspan>
        </text>
        <text x={tx+13} y={ty+51} fontSize="9" fontWeight="700" fill={r.suitability_color} letterSpacing="0.4">
          {r.suitability === 'SUITABLE' ? '✔' : r.suitability === 'SUITABLE WITH PRECAUTIONS' ? '⚠' : '✘'}
          {' '}{r.suitability}
        </text>
      </g>
    );
  };

  /* ── Skills table panel renderer ── */
  const renderDetailPanel = (
    panelId: 'A' | 'B',
    jobId: string | null,
    setJobId: (id: string) => void,
    skillData: SkillDetailResponse | null,
    loadingSkills: boolean,
    menuOpen: boolean,
    setMenuOpen: (v: boolean) => void,
    sortCol: SortCol, setSortCol: (c: SortCol) => void,
    sortDir: SortDir, setSortDir: (d: SortDir) => void,
  ) => {
    const result = matchResults.find(r => r.job_id === jobId) ?? null;
    if (!result) return null;

    const sortedSkills = [...(skillData?.skills ?? [])].sort((a, b) => {
      if (!sortCol || !sortDir) return 0;
      const dir = sortDir === 'asc' ? 1 : -1;
      return dir * ((a[sortCol] as number) - (b[sortCol] as number));
    });

    return (
      <div className={`ja-detail-panel${splitMode ? ' ja-detail-panel--split' : ''}`}>
        {/* Panel header */}
        <div className="ja-detail-header">
          {splitMode && <span className="ja-split-label">{panelId}</span>}

          {/* Job picker */}
          <div className="ja-job-picker-wrapper">
            <button
              className="ja-detail-job-name ja-detail-job-btn"
              onClick={() => setMenuOpen(!menuOpen)}
              title="Change job"
            >
              <span className="ja-job-picker-dot" style={{ background: result.suitability_color }} />
              {result.job_id.replace(/_/g, ' ')}
              <span className="ja-job-picker-chevron">{menuOpen ? '▲' : '▼'}</span>
            </button>
            {menuOpen && (
              <div className="ja-job-picker-menu">
                {matchResults.map(r => (
                  <button
                    key={r.job_id}
                    className={`ja-job-picker-item${r.job_id === jobId ? ' active' : ''}`}
                    onClick={() => { setJobId(r.job_id); setMenuOpen(false); }}
                  >
                    <span className="ja-job-picker-dot" style={{ background: r.suitability_color }} />
                    {r.job_id.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Metrics */}
          <span className="ja-detail-metric">GCS: <strong>{result.gcs_pct.toFixed(2)}%</strong></span>
          <span className="ja-detail-metric">AISA: <strong>{result.aisa_pct.toFixed(2)}%</strong></span>
          <span className="ja-detail-metric">N skills: <strong>{result.n_total}</strong></span>

          {/* Suitability badge */}
          <span className="ja-suit-badge"
            style={{
              color: result.suitability_color,
              borderColor: result.suitability_color + '55',
              background: result.suitability_color + '18',
            }}>
            {result.suitability === 'SUITABLE' ? '✔' :
              result.suitability === 'SUITABLE WITH PRECAUTIONS' ? '⚠' : '✘'}{' '}
            {result.suitability}
          </span>

          {/* Split button — only on panel A when not split */}
          {panelId === 'A' && !splitMode && (
            <button
              className="ja-split-btn"
              onClick={toggleSplit}
              title="Compare with another job"
            >
              ⊞ Split view
            </button>
          )}

          {/* Close split button — only on panel B */}
          {panelId === 'B' && (
            <button
              className="ja-split-close-icon"
              onClick={toggleSplit}
              title="Close split view"
            >
              ✕
            </button>
          )}
        </div>

        {/* Skills table */}
        <div className="ja-skills-wrapper" style={{ position: 'relative' }}>
          {loadingSkills && skillData && (
            <div className="ja-center" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(26, 42, 74, 0.4)', zIndex: 10, minHeight: 80 }}>
              <div className="wp-spinner" />
            </div>
          )}
          {loadingSkills && !skillData ? (
            <div className="ja-center" style={{ minHeight: 80 }}>
              <div className="wp-spinner" />
              <span className="ja-status-text">Loading skills…</span>
            </div>
          ) : skillData && skillData.skills.length > 0 ? (
            <table className="ja-skills-table" style={{ opacity: loadingSkills ? 0.6 : 1, transition: 'opacity 0.2s' }}>
              <thead>
                <tr>
                  <th>Skill / Ability</th>
                  <th
                    className={`ja-th-sort${sortCol === 'score' ? ' active' : ''}`}
                    onClick={() => makeSortHandler('score', sortCol, setSortCol, sortDir, setSortDir)}
                    title="Sort by Score"
                  >Score {makeSortIcon('score', sortCol, sortDir)}</th>
                  {!splitMode && (
                    <th
                      className={`ja-th-sort${sortCol === 'anchor' ? ' active' : ''}`}
                      onClick={() => makeSortHandler('anchor', sortCol, setSortCol, sortDir, setSortDir)}
                      title="Sort by Importance"
                    >Importance {makeSortIcon('anchor', sortCol, sortDir)}</th>
                  )}
                  <th
                    className={`ja-th-sort${sortCol === 'qualifier' ? ' active' : ''}`}
                    onClick={() => makeSortHandler('qualifier', sortCol, setSortCol, sortDir, setSortDir)}
                    title="Sort by Qualifier"
                  >Qualifier {makeSortIcon('qualifier', sortCol, sortDir)}</th>
                  {!splitMode && <th>CS</th>}
                  {!splitMode && <th className="ja-th-bar">CS bar</th>}
                  <th>Criticality</th>
                </tr>
              </thead>
              <tbody>
                {sortedSkills.map((s, i) => {
                  const color = CRIT_COLOR[s.criticality_label] ?? 'rgba(255,255,255,0.4)';
                  const barPct = Math.min((s.cs / 12) * 100, 100);
                  return (
                    <tr key={`${s.id}-${i}`}>
                      <td className="ja-td-skill" style={{ color }}>{s.id.replace(/_/g, ' ')}</td>
                      <td className="ja-td-num">{s.score}</td>
                      {!splitMode && (
                        <td className="ja-td-num">
                          <span className={`ja-anchor ja-anchor-${s.anchor}`}>
                            {ANCHOR_ICON[s.anchor] ?? '—'}
                          </span>
                        </td>
                      )}
                      <td className="ja-td-num">{s.qualifier}</td>
                      {!splitMode && <td className="ja-td-num"><strong style={{ color }}>{s.cs}</strong></td>}
                      {!splitMode && (
                        <td className="ja-td-bar">
                          <div className="ja-bar-track" style={{ background: 'rgba(0,0,0,0.2)', boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.3)' }}>
                            <div className="ja-bar-fill" style={{ width: `${barPct}%`, background: color }} />
                          </div>
                        </td>
                      )}
                      <td className="ja-td-crit" style={{ color, fontWeight: 600 }}>{s.criticality_label}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p className="ja-status-text" style={{ padding: '20px 16px' }}>
              No skill detail data available for this job.
            </p>
          )}
        </div>
      </div>
    );
  };

  /* ── Guards ── */
  if (loadingMatch && matchResults.length === 0) return (
    <div className="ja-center">
      <div className="wp-spinner" />
      <span className="ja-status-text">Loading job analysis…</span>
    </div>
  );
  if (matchError) return (
    <div className="ja-center">
      <span className="ja-error-icon">⚠</span>
      <p className="ja-status-text">{matchError}</p>
    </div>
  );
  if (matchResults.length === 0) return (
    <div className="ja-center">
      <p className="ja-status-text">No job evaluation data found for this worker.</p>
      <p className="ja-status-hint">
        Make sure this worker has <code>isSelected = true</code> and
        <code> isEvaluatedForJob</code> triples in the ontology.
      </p>
    </div>
  );

  return (
    <div className="ja-root">

      {/* ═══ Top row ════════════════════════════════════════════════════════════ */}
      <div className="ja-top-row">

        {/* ── Scatter plot ── */}
        <div className="ja-card ja-scatter-card">
          <div className="ja-card-header">
            <div>
              <div className="ja-card-title">Job Suitability Map</div>
              <div className="ja-card-sub">All available jobs for {workerDisplayName} · click a point to inspect</div>
            </div>
            <div className="ja-legend">
              <span className="ja-legend-item"><span className="ja-legend-dot" style={{ background: '#22c55e' }} />Suitable</span>
              <span className="ja-legend-item"><span className="ja-legend-dot" style={{ background: '#f59e0b' }} />With precautions</span>
              <span className="ja-legend-item"><span className="ja-legend-dot" style={{ background: '#ef4444' }} />Not suitable</span>
            </div>
          </div>

          <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="ja-scatter-svg" aria-label="Job suitability scatter plot">
            <defs>
              <clipPath id="ja-clip">
                <rect x={PAD.l} y={PAD.t} width={PW} height={PH} />
              </clipPath>
            </defs>
            <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="rgba(8,18,36,0.97)" />
            <g clipPath="url(#ja-clip)">
              <polygon points={zonePoly('green')}  fill="rgba(34,197,94,0.08)"  />
              <polygon points={zonePoly('yellow')} fill="rgba(245,158,11,0.10)" />
              <polygon points={zonePoly('red')}    fill="rgba(239,68,68,0.10)"  />
            </g>
            {X_TICKS.map(t => (
              <line key={`xg${t}`} x1={svgX(t)} y1={PAD.t} x2={svgX(t)} y2={PAD.t+PH}
                stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" strokeDasharray="2,3" />
            ))}
            {Y_TICKS.map(t => (
              <line key={`yg${t}`} x1={PAD.l} y1={svgY(t)} x2={PAD.l+PW} y2={svgY(t)}
                stroke="rgba(255,255,255,0.06)" strokeWidth="0.5" strokeDasharray="2,3" />
            ))}
            <g clipPath="url(#ja-clip)">
              <line x1={svgX(0)} y1={svgY(21)}   x2={svgX(42)} y2={svgY(0)}
                stroke="rgba(239,68,68,0.75)"  strokeWidth="1.2" />
              <line x1={svgX(0)} y1={svgY(15.5)} x2={svgX(31)} y2={svgY(0)}
                stroke="rgba(245,158,11,0.75)" strokeWidth="1.2" />
            </g>
            <text x={svgX(2)} y={svgY(23.2)} fontSize="8" fontWeight="600" fill="rgba(239,68,68,0.55)"  letterSpacing="0.8">NOT SUITABLE</text>
            <text x={svgX(2)} y={svgY(12.8)} fontSize="8" fontWeight="600" fill="rgba(245,158,11,0.55)" letterSpacing="0.8">WITH PRECAUTIONS</text>
            <text x={svgX(2)} y={svgY(2.8)}  fontSize="8" fontWeight="600" fill="rgba(34,197,94,0.55)"  letterSpacing="0.8">SUITABLE</text>
            <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="1" rx="4" />
            {X_TICKS.map(t => (
              <g key={`xt${t}`}>
                <line x1={svgX(t)} y1={PAD.t+PH} x2={svgX(t)} y2={PAD.t+PH+4} stroke="rgba(255,255,255,0.3)" strokeWidth="1" />
                <text x={svgX(t)} y={PAD.t+PH+13} textAnchor="middle" fontSize="8" fill="rgba(255,255,255,0.55)">{t}</text>
              </g>
            ))}
            {Y_TICKS.map(t => (
              <g key={`yt${t}`}>
                <line x1={PAD.l-4} y1={svgY(t)} x2={PAD.l} y2={svgY(t)} stroke="rgba(255,255,255,0.3)" strokeWidth="1" />
                <text x={PAD.l-7} y={svgY(t)+3} textAnchor="end" fontSize="8" fill="rgba(255,255,255,0.55)">{t}</text>
              </g>
            ))}
            <text x={PAD.l+PW/2} y={VB_H-6} textAnchor="middle" fontSize="8.5" fontWeight="500" fill="rgba(255,255,255,0.55)" letterSpacing="0.4">
              AMOUNT OF IMPAIRED SKILLS &amp; ABILITIES — AISA (%)
            </text>
            <text x={14} y={PAD.t+PH/2} textAnchor="middle" fontSize="8.5" fontWeight="500"
              fill="rgba(255,255,255,0.55)" letterSpacing="0.4" transform={`rotate(-90, 14, ${PAD.t+PH/2})`}>
              GENERAL CRITICALITY SCORE — GCS (%)
            </text>
            {matchResults.map(r => {
              const cx = svgX(r.aisa_pct), cy = svgY(r.gcs_pct);
              const isA = r.job_id === jobA, isB = r.job_id === jobB;
              const isActive = isA || isB;
              const col = r.suitability_color;
              return (
                <g key={r.job_id} style={{ cursor: 'pointer' }}
                  onClick={() => setJobA(r.job_id)}
                  onMouseEnter={() => setTooltip({ dataX: r.aisa_pct, dataY: r.gcs_pct, result: r })}
                  onMouseLeave={() => setTooltip(null)}
                >
                  {isActive && <circle cx={cx} cy={cy} r="9" fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth="1.5" />}
                  {isB && <circle cx={cx} cy={cy} r="12" fill="none" stroke={col} strokeWidth="1" opacity="0.5" strokeDasharray="3,2" />}
                  <circle cx={cx} cy={cy} r={isActive ? 5.5 : 4.5} fill={col} opacity={isActive ? 1 : 0.85} className="ja-dot" />
                </g>
              );
            })}
            {renderTooltip()}
          </svg>
        </div>

        {/* ── Jobs list ── */}
        <div className="ja-card ja-jobs-card">
          <div className="ja-jobs-header">Jobs</div>
          <ul className="ja-jobs-list" role="listbox" aria-label="Job list">
            {matchResults.map(r => (
              <li key={r.job_id}
                role="option"
                aria-selected={r.job_id === jobA}
                className={`ja-job-item ${r.job_id === jobA ? 'selected' : ''}`}
                onClick={() => setJobA(r.job_id)}
              >
                <span className="ja-job-dot" style={{ background: r.suitability_color, boxShadow: `0 0 6px ${r.suitability_color}` }} />
                <span className="ja-job-label">{r.job_id.replace(/_/g, ' ')}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ═══ Detail row ══════════════════════════════════════════════════════════ */}
      {jobA && (
        <div className={`ja-detail-row${splitMode ? ' ja-detail-row--split' : ''}`}>
          {/* Panel A */}
          <div className="ja-card ja-detail-card">
            {renderDetailPanel(
              'A', jobA, setJobA, skillDataA, loadingA, menuOpenA, setMenuOpenA,
              sortColA, setSortColA, sortDirA, setSortDirA,
            )}
          </div>

          {/* Panel B — only in split mode */}
          {splitMode && jobB && (
            <div className="ja-card ja-detail-card">
              {renderDetailPanel(
                'B', jobB, setJobB, skillDataB, loadingB, menuOpenB, setMenuOpenB,
                sortColB, setSortColB, sortDirB, setSortDirB,
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
