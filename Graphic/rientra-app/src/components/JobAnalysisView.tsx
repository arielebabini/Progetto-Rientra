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
const VB_W = 560;
const VB_H = 300;
const PAD  = { l: 54, r: 22, t: 18, b: 44 };
const PW   = VB_W - PAD.l - PAD.r;   // 484
const PH   = VB_H - PAD.t - PAD.b;   // 238

const X_MAX = 55;   // AISA %
const Y_MAX = 25;   // GCS  %

// Data → SVG pixel
function svgX(aisa: number) { return PAD.l + (aisa / X_MAX) * PW; }
function svgY(gcs:  number) { return PAD.t + PH - (gcs  / Y_MAX) * PH; }

// Threshold formulas (paper Fig. 4)
// Red line:    GCS = −0.5·AISA + 21   → exits bottom at AISA = 42
// Yellow line: GCS = −0.5·AISA + 15.5 → exits bottom at AISA = 31

// Zone polygon vertex lists in SVG space
function zonePoly(zone: 'green' | 'yellow' | 'red'): string {
  // All coordinates in DATA space [aisa, gcs], then mapped to SVG
  let pts: [number, number][];
  if (zone === 'green') {
    // Triangle below yellow line
    pts = [[0, 0], [31, 0], [0, 15.5]];
  } else if (zone === 'yellow') {
    // Quadrilateral between the two lines
    pts = [[0, 15.5], [31, 0], [42, 0], [0, 21]];
  } else {
    // Pentagon above red line (extends to top & right edges)
    pts = [[0, 21], [42, 0], [X_MAX, 0], [X_MAX, Y_MAX], [0, Y_MAX]];
  }
  return pts.map(([a, g]) => `${svgX(a)},${svgY(g)}`).join(' ');
}

const X_TICKS = [0, 10, 20, 30, 40, 50];
const Y_TICKS = [0, 5, 10, 15, 20, 25];

/* ─────────────────────────────────────────────
   Colour maps
───────────────────────────────────────────── */
const CRIT_COLOR: Record<string, string> = {
  'not critical':        'rgba(255,255,255,0.3)',
  'SLIGHTLY CRITICAL':   '#4ade80',
  'MODERATELY CRITICAL': '#fbbf24',
  'RELEVANTLY CRITICAL': '#fb923c',
  'EXTREMELY CRITICAL':  '#f87171',
};

const ANCHOR_ICON = ['—', '↑', '↑↑', '↑↑↑'];

/* ─────────────────────────────────────────────
   Component
───────────────────────────────────────────── */
interface JobAnalysisViewProps {
  workerId:          string;
  workerDisplayName: string;
}

interface TooltipState {
  svgX: number;
  svgY: number;
  result: MatchResult;
}

export default function JobAnalysisView({ workerId, workerDisplayName }: JobAnalysisViewProps) {
  const [matchResults,   setMatchResults]   = useState<MatchResult[]>([]);
  const [loadingMatch,   setLoadingMatch]   = useState(true);
  const [matchError,     setMatchError]     = useState<string | null>(null);

  const [selectedJobId,  setSelectedJobId]  = useState<string | null>(null);
  const [skillData,      setSkillData]      = useState<SkillDetailResponse | null>(null);
  const [loadingSkills,  setLoadingSkills]  = useState(false);

  const [tooltip,        setTooltip]        = useState<TooltipState | null>(null);

  // ── Fetch match results ───────────────────────────────────────────
  useEffect(() => {
    setLoadingMatch(true);
    setMatchError(null);
    setMatchResults([]);
    setSelectedJobId(null);
    setSkillData(null);

    fetchMatchResults(workerId)
      .then(results => {
        setMatchResults(results);
        if (results.length > 0) setSelectedJobId(results[0].job_id);
      })
      .catch(e => setMatchError(e.message ?? 'Failed to load match results'))
      .finally(() => setLoadingMatch(false));
  }, [workerId]);

  // ── Fetch skill detail when job selected ─────────────────────────
  useEffect(() => {
    if (!selectedJobId) return;
    setSkillData(null);
    setLoadingSkills(true);
    fetchSkillDetail(workerId, selectedJobId)
      .then(setSkillData)
      .catch(e => console.error('fetchSkillDetail:', e))
      .finally(() => setLoadingSkills(false));
  }, [workerId, selectedJobId]);

  const selectedResult = matchResults.find(r => r.job_id === selectedJobId) ?? null;

  // ── Loading / error / empty guards ───────────────────────────────
  if (loadingMatch) {
    return (
      <div className="ja-center">
        <div className="wp-spinner" />
        <span className="ja-status-text">Loading job analysis…</span>
      </div>
    );
  }
  if (matchError) {
    return (
      <div className="ja-center">
        <span className="ja-error-icon">⚠</span>
        <p className="ja-status-text">{matchError}</p>
      </div>
    );
  }
  if (matchResults.length === 0) {
    return (
      <div className="ja-center">
        <p className="ja-status-text">No job evaluation data found for this worker.</p>
        <p className="ja-status-hint">
          Make sure this worker has <code>isSelected = true</code> and
          <code> isEvaluatedForJob</code> triples in the ontology.
        </p>
      </div>
    );
  }

  return (
    <div className="ja-root">

      {/* ═══════════════════════════════ Top row ═══════════════════════════════ */}
      <div className="ja-top-row">

        {/* ── Scatter plot card ─────────────────────────────────────────────── */}
        <div className="ja-card ja-scatter-card">
          <div className="ja-card-header">
            <div>
              <div className="ja-card-title">Scatter Plot</div>
              <div className="ja-card-sub">All available jobs for {workerDisplayName}</div>
            </div>
            <div className="ja-legend">
              <span className="ja-legend-dot" style={{ background: '#22c55e' }} />Suitable
              <span className="ja-legend-dot" style={{ background: '#f59e0b', marginLeft: 12 }} />With precautions
              <span className="ja-legend-dot" style={{ background: '#ef4444', marginLeft: 12 }} />Not suitable
            </div>
          </div>

          <svg
            viewBox={`0 0 ${VB_W} ${VB_H}`}
            className="ja-scatter-svg"
            aria-label="Job suitability scatter plot"
          >
            <defs>
              <clipPath id="ja-clip">
                <rect x={PAD.l} y={PAD.t} width={PW} height={PH} />
              </clipPath>
              {/* Dot glow filter */}
              <filter id="ja-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="4" result="blur" />
                <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
              </filter>
              {/* Zone Gradients */}
              <linearGradient id="grad-green" x1="0" y1="1" x2="1" y2="0">
                <stop offset="0%" stopColor="#22c55e" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#22c55e" stopOpacity="0.03" />
              </linearGradient>
              <linearGradient id="grad-yellow" x1="0" y1="1" x2="1" y2="0">
                <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.18" />
                <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.03" />
              </linearGradient>
              <linearGradient id="grad-red" x1="0" y1="1" x2="1" y2="0">
                <stop offset="0%" stopColor="#ef4444" stopOpacity="0.15" />
                <stop offset="100%" stopColor="#ef4444" stopOpacity="0.05" />
              </linearGradient>
            </defs>

            {/* Subtle background grid pattern */}
            <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="rgba(0,0,0,0.15)" />

            {/* Zone fills */}
            <g clipPath="url(#ja-clip)">
              <polygon points={zonePoly('green')}  fill="url(#grad-green)" />
              <polygon points={zonePoly('yellow')} fill="url(#grad-yellow)" />
              <polygon points={zonePoly('red')}    fill="url(#grad-red)" />
            </g>

            {/* Grid */}
            {X_TICKS.map(t => (
              <line key={`xg${t}`}
                x1={svgX(t)} y1={PAD.t} x2={svgX(t)} y2={PAD.t + PH}
                stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
            ))}
            {Y_TICKS.map(t => (
              <line key={`yg${t}`}
                x1={PAD.l} y1={svgY(t)} x2={PAD.l + PW} y2={svgY(t)}
                stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
            ))}

            {/* Glowing Threshold lines */}
            <g clipPath="url(#ja-clip)">
              {/* Red line glow */}
              <line x1={svgX(0)} y1={svgY(21)} x2={svgX(42)} y2={svgY(0)}
                stroke="#ef4444" strokeWidth="6" opacity="0.2" filter="url(#ja-glow)" />
              <line x1={svgX(0)} y1={svgY(21)} x2={svgX(42)} y2={svgY(0)}
                stroke="#ef4444" strokeWidth="2" strokeDasharray="8,6" opacity="0.8" />
              
              {/* Yellow line glow */}
              <line x1={svgX(0)} y1={svgY(15.5)} x2={svgX(31)} y2={svgY(0)}
                stroke="#f59e0b" strokeWidth="6" opacity="0.2" filter="url(#ja-glow)" />
              <line x1={svgX(0)} y1={svgY(15.5)} x2={svgX(31)} y2={svgY(0)}
                stroke="#f59e0b" strokeWidth="2" strokeDasharray="8,6" opacity="0.8" />
            </g>

            {/* Zone labels */}
            <text x={svgX(1.5)} y={svgY(23)} fontSize="11" fontWeight="800" fill="rgba(239,68,68,0.7)" fontStyle="italic" letterSpacing="1">NOT SUITABLE</text>
            <text x={svgX(1.5)} y={svgY(13)} fontSize="11" fontWeight="800" fill="rgba(245,158,11,0.7)" fontStyle="italic" letterSpacing="1">WITH PRECAUTIONS</text>
            <text x={svgX(1.5)} y={svgY(3.5)} fontSize="11" fontWeight="800" fill="rgba(34,197,94,0.7)"  fontStyle="italic" letterSpacing="1">SUITABLE</text>

            {/* Plot border styled beautifully */}
            <rect x={PAD.l} y={PAD.t} width={PW} height={PH}
              fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="1" rx="4" />

            {/* X axis */}
            {X_TICKS.map(t => (
              <g key={`xt${t}`}>
                <line x1={svgX(t)} y1={PAD.t+PH} x2={svgX(t)} y2={PAD.t+PH+5}
                  stroke="rgba(255,255,255,0.3)" strokeWidth="1.5" />
                <text x={svgX(t)} y={PAD.t+PH+16} textAnchor="middle" fontSize="10" fontWeight="600" fill="rgba(255,255,255,0.6)">{t}</text>
              </g>
            ))}
            {/* Y axis */}
            {Y_TICKS.map(t => (
              <g key={`yt${t}`}>
                <line x1={PAD.l-5} y1={svgY(t)} x2={PAD.l} y2={svgY(t)}
                  stroke="rgba(255,255,255,0.3)" strokeWidth="1.5" />
                <text x={PAD.l-8} y={svgY(t)+3.5} textAnchor="end" fontSize="10" fontWeight="600" fill="rgba(255,255,255,0.6)">{t}</text>
              </g>
            ))}

            {/* Axis labels */}
            <text x={PAD.l + PW/2} y={VB_H - 4}
              textAnchor="middle" fontSize="10.5" fontWeight="600" fill="rgba(255,255,255,0.85)" letterSpacing="0.5">
              AMOUNT OF IMPAIRED SKILLS AND ABILITIES · AISA (%)
            </text>
            <text x={18} y={PAD.t + PH/2}
              textAnchor="middle" fontSize="10.5" fontWeight="600" fill="rgba(255,255,255,0.85)" letterSpacing="0.5"
              transform={`rotate(-90, 18, ${PAD.t + PH/2})`}>
              GENERAL CRITICALITY SCORE · GCS (%)
            </text>

            {/* Data points */}
            {matchResults.map(r => {
              const cx       = svgX(r.aisa_pct);
              const cy       = svgY(r.gcs_pct);
              const isActive = r.job_id === selectedJobId;
              const color    = r.suitability_color;
              return (
                <g key={r.job_id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => setSelectedJobId(r.job_id)}
                  onMouseEnter={() => setTooltip({ svgX: cx, svgY: cy, result: r })}
                  onMouseLeave={() => setTooltip(null)}
                >
                  {/* Outer ring when selected */}
                  {isActive && (
                    <circle cx={cx} cy={cy} r="13"
                      fill="none" stroke={color} strokeWidth="1.5" opacity="0.45" />
                  )}
                  {/* Glow only on selected */}
                  <circle cx={cx} cy={cy} r={isActive ? 7 : 5}
                    fill={color}
                    stroke={isActive ? '#fff' : color}
                    strokeWidth={isActive ? 1.8 : 0.5}
                    opacity={isActive ? 1 : 0.78}
                    filter={isActive ? 'url(#ja-glow)' : undefined}
                    className="ja-dot"
                  />
                </g>
              );
            })}

            {/* Tooltip */}
            {tooltip && (() => {
              const label = tooltip.result.job_id.replace(/_/g, ' ');
              const truncated = label.length > 24 ? label.slice(0, 24) + '…' : label;
              const tw  = Math.min(truncated.length * 6.3 + 16, 190);
              const tx  = Math.min(tooltip.svgX + 10, VB_W - tw - 6);
              const ty  = Math.max(tooltip.svgY - 38, PAD.t);
              return (
                <g style={{ pointerEvents: 'none' }}>
                  <rect x={tx} y={ty} width={tw} height={24} rx="5"
                    fill="rgba(10,20,45,0.93)" stroke="rgba(255,255,255,0.18)" strokeWidth="1" />
                  <text x={tx + 8} y={ty + 15.5} fontSize="10.5" fill="rgba(255,255,255,0.92)">
                    {truncated}
                  </text>
                </g>
              );
            })()}
          </svg>
        </div>

        {/* ── Jobs list ─────────────────────────────────────────────────────── */}
        <div className="ja-card ja-jobs-card">
          <div className="ja-jobs-header">Jobs</div>
          <ul className="ja-jobs-list" role="listbox" aria-label="Job list">
            {matchResults.map(r => (
              <li key={r.job_id}
                role="option"
                aria-selected={r.job_id === selectedJobId}
                className={`ja-job-item ${r.job_id === selectedJobId ? 'selected' : ''}`}
                onClick={() => setSelectedJobId(r.job_id)}
              >
                <span className="ja-job-dot" style={{ background: r.suitability_color, boxShadow: `0 0 6px ${r.suitability_color}` }} />
                <span className="ja-job-label">{r.job_id.replace(/_/g, ' ')}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ═══════════════════════════════ Detail row ════════════════════════════ */}
      {selectedResult && (
        <div className="ja-card ja-detail-card">
          {/* Detail header */}
          <div className="ja-detail-header">
            <span className="ja-detail-job-name">
              Job: {selectedResult.job_id.replace(/_/g, ' ')}
            </span>
            <span className="ja-detail-metric">
              GCS: <strong>{selectedResult.gcs_pct.toFixed(2)}%</strong>
            </span>
            <span className="ja-detail-metric">
              AISA: <strong>{selectedResult.aisa_pct.toFixed(2)}%</strong>
            </span>
            <span className="ja-detail-metric">
              N skills: <strong>{selectedResult.n_total}</strong>
            </span>
            <span className="ja-suit-badge"
              style={{
                color:       selectedResult.suitability_color,
                borderColor: selectedResult.suitability_color + '55',
                background:  selectedResult.suitability_color + '18',
              }}>
              {selectedResult.suitability === 'SUITABLE'                  ? '✔' :
               selectedResult.suitability === 'SUITABLE WITH PRECAUTIONS' ? '⚠' : '✘'}{' '}
              {selectedResult.suitability}
            </span>
          </div>

          {/* Skills table */}
          <div className="ja-skills-wrapper">
            {loadingSkills ? (
              <div className="ja-center" style={{ minHeight: 80 }}>
                <div className="wp-spinner" />
                <span className="ja-status-text">Loading skills…</span>
              </div>
            ) : skillData && skillData.skills.length > 0 ? (
              <table className="ja-skills-table">
                <thead>
                  <tr>
                    <th>Skill / Ability</th>
                    <th>Score</th>
                    <th>Importance</th>
                    <th>Qualifier</th>
                    <th>CS</th>
                    <th className="ja-th-bar">CS bar</th>
                    <th>Criticality</th>
                  </tr>
                </thead>
                <tbody>
                  {skillData.skills.map((s, i) => {
                    const color  = CRIT_COLOR[s.criticality_label] ?? 'rgba(255,255,255,0.4)';
                    const barPct = Math.min((s.cs / 12) * 100, 100);
                    return (
                      <tr key={`${s.id}-${i}`}>
                        <td className="ja-td-skill" style={{ color }}>{s.id.replace(/_/g, ' ')}</td>
                        <td className="ja-td-num">{s.score}</td>
                        <td className="ja-td-num">
                          <span className={`ja-anchor ja-anchor-${s.anchor}`}>
                            {ANCHOR_ICON[s.anchor] ?? '—'}
                          </span>
                        </td>
                        <td className="ja-td-num">{s.qualifier}</td>
                        <td className="ja-td-num"><strong style={{ color }}>{s.cs}</strong></td>
                        <td className="ja-td-bar">
                          <div className="ja-bar-track" style={{ background: 'rgba(0,0,0,0.2)', boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.3)' }}>
                            <div className="ja-bar-fill"
                              style={{ width: `${barPct}%`, background: color, boxShadow: `0 0 10px ${color}` }} />
                          </div>
                        </td>
                        <td className="ja-td-crit" style={{ color, fontWeight: 600, textShadow: `0 0 8px ${color}55` }}>{s.criticality_label}</td>
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
      )}
    </div>
  );
}
