import { useState, useEffect, useMemo } from 'react';
import './JobAnalysisView.css';
import {
  fetchMatchResults,
  fetchSkillDetail,
  type MatchResult,
  type SkillDetailResponse,
  type SkillDetail,
} from '../api/semanticService';

/* ═══════════════════════════════════════════════════════════════
   Scatter plot coordinate system
═══════════════════════════════════════════════════════════════ */
const VB_W = 600, VB_H = 280;
const PAD = { l: 62, r: 22, t: 22, b: 52 };
const PW = VB_W - PAD.l - PAD.r;
const PH = VB_H - PAD.t - PAD.b;
const X_MAX = 55, Y_MAX = 25;

const toX = (a: number) => PAD.l + (a / X_MAX) * PW;
const toY = (g: number) => PAD.t + PH - (g / Y_MAX) * PH;

const zonePts = (z: 'green' | 'yellow' | 'red') => {
  const pts: [number, number][] =
    z === 'green' ? [[0, 0], [31, 0], [0, 15.5]] :
      z === 'yellow' ? [[0, 15.5], [31, 0], [42, 0], [0, 21]] :
        [[0, 21], [42, 0], [X_MAX, 0], [X_MAX, Y_MAX], [0, Y_MAX]];
  return pts.map(([a, g]) => `${toX(a)},${toY(g)}`).join(' ');
};

const X_TICKS = [0, 10, 20, 30, 40, 50];
const Y_TICKS = [0, 5, 10, 15, 20, 25];

/* Suitability zone colours — muted fills only, no neon */
const ZONE_FILL = { green: 'rgba(34,197,94,0.10)', yellow: 'rgba(245,158,11,0.10)', red: 'rgba(239,68,68,0.10)' };
const ZONE_LINE = { red: 'rgba(239,68,68,0.65)', yellow: 'rgba(245,158,11,0.65)' };

/* ═══════════════════════════════════════════════════════════════
   Criticality colour map — desaturated to match app palette
═══════════════════════════════════════════════════════════════ */
const CRIT_COLOR: Record<string, string> = {
  'not critical': 'rgba(255,255,255,0.30)',
  'SLIGHTLY CRITICAL': '#6aad8c',
  'MODERATELY CRITICAL': '#c4a83a',
  'RELEVANTLY CRITICAL': '#c47e45',
  'EXTREMELY CRITICAL': '#c04040',
};
const ANCHOR_ICON = ['—', '↑', '↑↑', '↑↑↑'];

/* ═══════════════════════════════════════════════════════════════
   Skill-area classification for radar
═══════════════════════════════════════════════════════════════ */
const SKILL_AREAS = [
  { label: 'Physical', keys: ['Strength', 'Stamina', 'Steadiness', 'Flexibility', 'Gross', 'Reaction', 'Manual', 'Arm', 'Finger', 'Wrist', 'Hand', 'Trunk', 'Static', 'Dynamic', 'Explosive', 'Movement'] },
  { label: 'Sensory', keys: ['Vision', 'Hearing', 'Touch', 'Night', 'Depth', 'Color', 'Sound', 'Speech', 'Vocal'] },
  { label: 'Cognitive', keys: ['Reasoning', 'Learning', 'Memory', 'Attention', 'Problem', 'Math', 'Writing', 'Reading', 'Comprehension', 'Inductive', 'Deductive', 'Fluency', 'Information', 'Number', 'Oral'] },
  { label: 'Social', keys: ['Listening', 'Service', 'Persuasion', 'Negotiation', 'Instructing', 'Social', 'Communication', 'Empathy'] },
  { label: 'Technical', keys: ['Technology', 'Equipment', 'Operation', 'Programming', 'Quality', 'Science', 'Engineering', 'Install', 'Repair', 'Trouble', 'Monitoring', 'Computer', 'Systems'] },
  { label: 'Creative', keys: ['Originality', 'Artistic', 'Creative', 'Design', 'Imagination'] },
];
const RADAR_AXES = [...SKILL_AREAS.map(a => a.label), 'Other'];
const RADAR_COLORS = ['#4DD9C0', '#f59e0b', '#818cf8'];

function classifySkill(id: string): string {
  const name = id.toLowerCase();
  for (const area of SKILL_AREAS) {
    if (area.keys.some(k => name.includes(k.toLowerCase()))) return area.label;
  }
  return 'Other';
}

/* ═══════════════════════════════════════════════════════════════
   Radar SVG — clean, no glow
═══════════════════════════════════════════════════════════════ */
interface RadarDataset { label: string; color: string; values: number[]; }

function RadarChart({ datasets }: { datasets: RadarDataset[] }) {
  const n = RADAR_AXES.length;
  const size = 260, cx = size / 2, cy = (size / 2) + 8, R = size * 0.36;
  const levels = 4;
  const ang = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const pt = (i: number, r: number) => ({ x: cx + r * Math.cos(ang(i)), y: cy + r * Math.sin(ang(i)) });

  return (
    <svg viewBox={`-15 -15 ${size + 30} ${size + 30}`} style={{ width: '100%', maxWidth: 480, maxHeight: '100%', display: 'block', margin: '0 auto', overflow: 'visible' }}>
      {/* level rings */}
      {Array.from({ length: levels }, (_, k) => {
        const r = R * ((k + 1) / levels);
        const d = Array.from({ length: n }, (__, i) => {
          const p = pt(i, r);
          return `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`;
        }).join(' ') + ' Z';
        return <path key={k} d={d} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="0.7" />;
      })}
      {/* spokes */}
      {Array.from({ length: n }, (_, i) => {
        const end = pt(i, R);
        return <line key={i} x1={cx} y1={cy} x2={end.x} y2={end.y} stroke="rgba(255,255,255,0.08)" strokeWidth="0.7" />;
      })}
      {/* datasets */}
      {datasets.map((ds, di) => {
        const pts = ds.values.map((v, i) => pt(i, R * v));
        const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + ' Z';
        return (
          <g key={di}>
            <path d={d} fill={ds.color} fillOpacity="0.14" stroke={ds.color} strokeWidth="1.5" />
            {pts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r="3" fill={ds.color} opacity="0.85" />)}
          </g>
        );
      })}
      {/* labels */}
      {Array.from({ length: n }, (_, i) => {
        const p = pt(i, R + 20);
        return (
          <text key={i} x={p.x} y={p.y} textAnchor="middle" dominantBaseline="middle"
            fontSize="9" fill="rgba(255,255,255,0.50)" fontWeight="600">
            {RADAR_AXES[i]}
          </text>
        );
      })}
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Sort types
═══════════════════════════════════════════════════════════════ */
type SortCol = 'score' | 'anchor' | 'qualifier' | null;
type SortDir = 'asc' | 'desc' | null;
type MainTab = 'map' | 'radar' | 'detail';

/* ═══════════════════════════════════════════════════════════════
   Main component
═══════════════════════════════════════════════════════════════ */
interface JobAnalysisViewProps {
  workerId: string;
  workerDisplayName: string;
}
interface TooltipState { dataX: number; dataY: number; result: MatchResult; }

export default function JobAnalysisView({ workerId, workerDisplayName }: JobAnalysisViewProps) {
  const [matchResults, setMatchResults] = useState<MatchResult[]>([]);
  const [loadingMatch, setLoadingMatch] = useState(true);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [mainTab, setMainTab] = useState<MainTab>('map');

  const [jobA, setJobA] = useState<string | null>(null);
  const [skillDataA, setSkillDataA] = useState<SkillDetailResponse | null>(null);
  const [loadingA, setLoadingA] = useState(false);
  const [menuOpenA, setMenuOpenA] = useState(false);
  const [sortColA, setSortColA] = useState<SortCol>(null);
  const [sortDirA, setSortDirA] = useState<SortDir>(null);

  const [splitMode, setSplitMode] = useState(false);
  const [jobB, setJobB] = useState<string | null>(null);
  const [skillDataB, setSkillDataB] = useState<SkillDetailResponse | null>(null);
  const [loadingB, setLoadingB] = useState(false);
  const [menuOpenB, setMenuOpenB] = useState(false);
  const [sortColB, setSortColB] = useState<SortCol>(null);
  const [sortDirB, setSortDirB] = useState<SortDir>(null);

  /* fetch */
  useEffect(() => {
    setLoadingMatch(true); setMatchError(null);
    fetchMatchResults(workerId)
      .then(r => { setMatchResults(r); if (r.length) setJobA(r[0].job_id); })
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

  const doSort = (col: SortCol, cc: SortCol, sc: (c: SortCol) => void, cd: SortDir, sd: (d: SortDir) => void) => {
    if (cc !== col) { sc(col); sd('asc'); return; }
    if (cd === 'asc') { sd('desc'); return; }
    sc(null); sd(null);
  };
  const sortIcon = (col: SortCol, cc: SortCol, cd: SortDir) =>
    cc !== col ? <span className="ja-sort-icon">⇅</span>
      : <span className="ja-sort-badge">{cd === 'asc' ? '↑' : '↓'}</span>;

  /* KPI stats */
  const stats = useMemo(() => ({
    total: matchResults.length,
    suitable: matchResults.filter(r => r.suitability === 'SUITABLE').length,
    precaution: matchResults.filter(r => r.suitability === 'SUITABLE WITH PRECAUTIONS').length,
    unsuitable: matchResults.filter(r => r.suitability === 'NOT SUITABLE').length,
    avgGCS: matchResults.length ? matchResults.reduce((s, r) => s + r.gcs_pct, 0) / matchResults.length : 0,
    avgAISA: matchResults.length ? matchResults.reduce((s, r) => s + r.aisa_pct, 0) / matchResults.length : 0,
  }), [matchResults]);

  /* radar */
  const radarDatasets = useMemo<RadarDataset[]>(() => {
    return (splitMode ? [{ sd: skillDataA, id: jobA }, { sd: skillDataB, id: jobB }] : [{ sd: skillDataA, id: jobA }])
      .flatMap(({ sd, id }, di) => {
        if (!sd || !id) return [];
        const buckets: Record<string, number[]> = {};
        RADAR_AXES.forEach(a => { buckets[a] = []; });
        sd.skills.forEach((s: SkillDetail) => {
          const area = classifySkill(s.id);
          const key = RADAR_AXES.includes(area) ? area : 'Other';
          buckets[key].push(s.cs_normalized);
        });
        const values = RADAR_AXES.map(a => {
          const arr = buckets[a];
          return arr.length ? Math.min(arr.reduce((x, y) => x + y, 0) / arr.length, 1) : 0;
        });
        return [{ label: id.replace(/_/g, ' '), color: RADAR_COLORS[di], values }];
      });
  }, [skillDataA, skillDataB, splitMode, jobA, jobB]);

  /* ── Scatter plot ── */
  const renderScatter = () => (
    <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="ja-scatter-svg"
      aria-label="Job suitability scatter plot" preserveAspectRatio="xMidYMid meet">
      <defs>
        <clipPath id="ja-clip">
          <rect x={PAD.l} y={PAD.t} width={PW} height={PH} />
        </clipPath>
      </defs>

      {/* plot background */}
      <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="rgba(0,0,0,0.25)" rx="3" />

      {/* zone fills */}
      <g clipPath="url(#ja-clip)">
        <polygon points={zonePts('green')} fill={ZONE_FILL.green} />
        <polygon points={zonePts('yellow')} fill={ZONE_FILL.yellow} />
        <polygon points={zonePts('red')} fill={ZONE_FILL.red} />
      </g>

      {/* subtle grid */}
      {X_TICKS.map(t => <line key={`xg${t}`} x1={toX(t)} y1={PAD.t} x2={toX(t)} y2={PAD.t + PH} stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" strokeDasharray="3,4" />)}
      {Y_TICKS.map(t => <line key={`yg${t}`} x1={PAD.l} y1={toY(t)} x2={PAD.l + PW} y2={toY(t)} stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" strokeDasharray="3,4" />)}

      {/* boundary lines */}
      <g clipPath="url(#ja-clip)">
        <line x1={toX(0)} y1={toY(21)} x2={toX(42)} y2={toY(0)} stroke={ZONE_LINE.red} strokeWidth="1.3" />
        <line x1={toX(0)} y1={toY(15.5)} x2={toX(31)} y2={toY(0)} stroke={ZONE_LINE.yellow} strokeWidth="1.3" />
      </g>

      {/* zone labels */}
      <text x={toX(2)} y={toY(23.2)} fontSize="7.5" fontWeight="700" fill="rgba(239,68,68,0.55)" letterSpacing="0.9">NOT SUITABLE</text>
      <text x={toX(2)} y={toY(12.8)} fontSize="7.5" fontWeight="700" fill="rgba(245,158,11,0.55)" letterSpacing="0.9">WITH PRECAUTIONS</text>
      <text x={toX(2)} y={toY(2.8)} fontSize="7.5" fontWeight="700" fill="rgba(34,197,94,0.55)" letterSpacing="0.9">SUITABLE</text>

      {/* border */}
      <rect x={PAD.l} y={PAD.t} width={PW} height={PH} fill="none" stroke="rgba(255,255,255,0.10)" strokeWidth="0.8" rx="3" />

      {/* axes */}
      {X_TICKS.map(t => (
        <g key={`xt${t}`}>
          <line x1={toX(t)} y1={PAD.t + PH} x2={toX(t)} y2={PAD.t + PH + 4} stroke="rgba(255,255,255,0.22)" strokeWidth="0.8" />
          <text x={toX(t)} y={PAD.t + PH + 14} textAnchor="middle" fontSize="8" fill="rgba(255,255,255,0.45)">{t}</text>
        </g>
      ))}
      {Y_TICKS.map(t => (
        <g key={`yt${t}`}>
          <line x1={PAD.l - 4} y1={toY(t)} x2={PAD.l} y2={toY(t)} stroke="rgba(255,255,255,0.22)" strokeWidth="0.8" />
          <text x={PAD.l - 6} y={toY(t) + 3} textAnchor="end" fontSize="8" fill="rgba(255,255,255,0.45)" >{t}</text>
        </g>
      ))}
      <text x={PAD.l + PW / 2} y={VB_H - 5} textAnchor="middle" fontSize="8.5" fontWeight="500" fill="rgba(255,255,255,0.38)" letterSpacing="0.4">
        AMOUNT OF IMPAIRED SKILLS &amp; ABILITIES — AISA (%)
      </text>
      <text x={13} y={PAD.t + PH / 2} textAnchor="middle" fontSize="8.5" fontWeight="500" fill="rgba(255,255,255,0.38)" letterSpacing="0.4"
        transform={`rotate(-90,13,${PAD.t + PH / 2})`}>
        GENERAL CRITICALITY SCORE — GCS (%)
      </text>

      {/* data points */}
      {matchResults.map(r => {
        const cx = toX(r.aisa_pct), cy = toY(r.gcs_pct);
        const isA = r.job_id === jobA, isB = r.job_id === jobB;
        const active = isA || isB;
        const col = r.suitability_color;
        return (
          <g key={r.job_id} style={{ cursor: 'pointer' }}
            onClick={() => setJobA(r.job_id)}
            onMouseEnter={() => setTooltip({ dataX: r.aisa_pct, dataY: r.gcs_pct, result: r })}
            onMouseLeave={() => setTooltip(null)}>
            {active && <circle cx={cx} cy={cy} r="13" fill="none" stroke={col} strokeWidth="1" opacity="0.28" className="ja-ring-pulse" />}
            {active && <circle cx={cx} cy={cy} r="8.5" fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth="1.2" />}
            <circle cx={cx} cy={cy} r={active ? 5 : 4} fill={col} opacity={active ? 0.95 : 0.75} className="ja-dot" />
          </g>
        );
      })}

      {/* tooltip */}
      {tooltip && (() => {
        const r = tooltip.result;
        const lbl = r.job_id.replace(/_/g, ' ');
        const trunc = lbl.length > 22 ? lbl.slice(0, 22) + '…' : lbl;
        const bw = 170, bh = 66;
        const px = toX(tooltip.dataX), py = toY(tooltip.dataY);
        const tx = px + 14 + bw > VB_W - PAD.r ? px - bw - 14 : px + 14;
        const ty = Math.max(PAD.t + 2, Math.min(py - bh / 2, PAD.t + PH - bh - 2));
        const icon = r.suitability === 'SUITABLE' ? '✔' : r.suitability === 'SUITABLE WITH PRECAUTIONS' ? '⚠' : '✘';
        return (
          <g style={{ pointerEvents: 'none' }}>
            <line x1={px} y1={PAD.t} x2={px} y2={PAD.t + PH} stroke="rgba(255,255,255,0.10)" strokeWidth="0.8" strokeDasharray="4,3" clipPath="url(#ja-clip)" />
            <line x1={PAD.l} y1={py} x2={PAD.l + PW} y2={py} stroke="rgba(255,255,255,0.10)" strokeWidth="0.8" strokeDasharray="4,3" clipPath="url(#ja-clip)" />
            <rect x={tx} y={ty} width={bw} height={bh} rx="8"
              fill="rgba(18,34,60,0.96)" stroke="rgba(255,255,255,0.13)" strokeWidth="0.8" />
            <rect x={tx} y={ty} width="3.5" height={bh} rx="3.5" fill={r.suitability_color} opacity="0.90" />
            <text x={tx + 12} y={ty + 17} fontSize="10.5" fontWeight="700" fill="rgba(255,255,255,0.92)">{trunc}</text>
            <text x={tx + 12} y={ty + 32} fontSize="9" fill="rgba(255,255,255,0.42)">
              GCS <tspan fontWeight="600" fill="rgba(255,255,255,0.80)">{r.gcs_pct.toFixed(1)}%</tspan>
              {'   '}AISA <tspan fontWeight="600" fill="rgba(255,255,255,0.80)">{r.aisa_pct.toFixed(1)}%</tspan>
            </text>
            <text x={tx + 12} y={ty + 50} fontSize="8.5" fontWeight="700" fill={r.suitability_color} letterSpacing="0.4">
              {icon}{' '}{r.suitability}
            </text>
          </g>
        );
      })()}
    </svg>
  );

  /* ── Job picker dropdown ── */
  const renderPicker = (
    jobId: string | null, setJobId: (id: string) => void,
    open: boolean, setOpen: (v: boolean) => void,
  ) => {
    const r = matchResults.find(m => m.job_id === jobId);
    return (
      <div className="ja-picker-wrap">
        <button className="ja-picker-btn" onClick={() => setOpen(!open)}>
          {r && <span className="ja-picker-dot" style={{ background: r.suitability_color }} />}
          {r ? r.job_id.replace(/_/g, ' ') : 'Select…'}
          <span className="ja-picker-chevron">{open ? '▲' : '▼'}</span>
        </button>
        {open && (
          <div className="ja-picker-menu">
            {matchResults.map(m => (
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
    sortCol: SortCol, setSortCol: (c: SortCol) => void,
    sortDir: SortDir, setSortDir: (d: SortDir) => void,
  ) => {
    const result = matchResults.find(r => r.job_id === jobId) ?? null;
    if (!result) return null;
    const sorted = [...(skillData?.skills ?? [])].sort((a, b) => {
      if (!sortCol || !sortDir) return 0;
      return (sortDir === 'asc' ? 1 : -1) * ((a[sortCol] as number) - (b[sortCol] as number));
    });
    return (
      <div className="ja-detail-pane">
        <div className="ja-detail-hdr">
          {splitMode && <span className="ja-split-lbl">{panelId}</span>}
          {renderPicker(jobId, setJobId, open, setOpen)}
          <span className="ja-metric">GCS <strong>{result.gcs_pct.toFixed(2)}%</strong></span>
          <span className="ja-metric">AISA <strong>{result.aisa_pct.toFixed(2)}%</strong></span>
          <span className="ja-metric">N skills <strong>{result.n_total}</strong></span>
          {splitMode ? (
            <div style={{ flexBasis: '100%', display: 'flex', alignItems: 'center', gap: '12px', minHeight: '32px' }}>
              <span className="ja-suit-badge"
                style={{ color: result.suitability_color, borderColor: result.suitability_color + '45', background: result.suitability_color + '12' }}>
                {result.suitability === 'SUITABLE' ? '✔' : result.suitability === 'SUITABLE WITH PRECAUTIONS' ? '⚠' : '✘'}{' '}
                {result.suitability}
              </span>
              {panelId === 'B' && (
                <button className="ja-btn-close-split" onClick={toggleSplit} title="Close compare">✕</button>
              )}
            </div>
          ) : (
            <>
              <span className="ja-suit-badge"
                style={{ color: result.suitability_color, borderColor: result.suitability_color + '45', background: result.suitability_color + '12' }}>
                {result.suitability === 'SUITABLE' ? '✔' : result.suitability === 'SUITABLE WITH PRECAUTIONS' ? '⚠' : '✘'}{' '}
                {result.suitability}
              </span>
              {panelId === 'A' && (
                <button className="ja-btn-split" onClick={toggleSplit}>⊞ Compare</button>
              )}
            </>
          )}
        </div>
        <div className="ja-skills-wrap" style={{ position: 'relative' }}>
          {loading && skillData && (
            <div className="ja-center" style={{ position: 'absolute', inset: 0, background: 'rgba(26,46,74,0.5)', zIndex: 10 }}>
              <div className="wp-spinner" />
            </div>
          )}
          {loading && !skillData ? (
            <div className="ja-center"><div className="wp-spinner" /><span className="ja-status-txt">Loading…</span></div>
          ) : skillData && skillData.skills.length > 0 ? (
            <table className="ja-skills-tbl" style={{ opacity: loading ? 0.55 : 1, transition: 'opacity 0.2s' }}>
              <thead>
                <tr>
                  <th>Skill / Ability</th>
                  <th className={`ja-th-sort${sortCol === 'score' ? ' active' : ''}`}
                    onClick={() => doSort('score', sortCol, setSortCol, sortDir, setSortDir)}>
                    Score {sortIcon('score', sortCol, sortDir)}</th>
                  {!splitMode && (
                    <th className={`ja-th-sort${sortCol === 'anchor' ? ' active' : ''}`}
                      onClick={() => doSort('anchor', sortCol, setSortCol, sortDir, setSortDir)}>
                      Importance {sortIcon('anchor', sortCol, sortDir)}</th>
                  )}
                  <th className={`ja-th-sort${sortCol === 'qualifier' ? ' active' : ''}`}
                    onClick={() => doSort('qualifier', sortCol, setSortCol, sortDir, setSortDir)}>
                    Qualifier {sortIcon('qualifier', sortCol, sortDir)}</th>
                  {!splitMode && <th>CS</th>}
                  {!splitMode && <th className="ja-th-bar">CS bar</th>}
                  <th>Criticality</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((s, i) => {
                  const col = CRIT_COLOR[s.criticality_label] ?? 'rgba(255,255,255,0.4)';
                  const barW = Math.min((s.cs / 12) * 100, 100);
                  return (
                    <tr key={`${s.id}-${i}`}>
                      <td className="ja-td-skill" style={{ color: col }}>{s.id.replace(/_/g, ' ')}</td>
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
        <button className={`ja-tab${mainTab === 'radar' ? ' active' : ''}`} onClick={() => setMainTab('radar')}>Skill Profile</button>
        <button className={`ja-tab${mainTab === 'detail' ? ' active' : ''}`} onClick={() => setMainTab('detail')}>Skill Detail</button>
        <div className="ja-tab-spacer" />
        <span className="ja-worker-chip">{workerDisplayName}</span>
      </div>

      {/* ── MAP tab ── */}
      {mainTab === 'map' && (
        <div className="ja-tab-content">
          <div className="ja-map-body">
            <div className="ja-scatter-area">
              <div className="ja-scatter-legend">
                {[['#22c55e', 'Suitable'], ['#f59e0b', 'With precautions'], ['#ef4444', 'Not suitable']].map(([c, l]) => (
                  <span key={l} className="ja-legend-item">
                    <span className="ja-legend-dot" style={{ background: c }} />{l}
                  </span>
                ))}
              </div>
              {renderScatter()}
            </div>
            <div className="ja-jobs-sidebar">
              <div className="ja-jobs-sidebar-hdr">Jobs</div>
              <ul className="ja-jobs-list" role="listbox">
                {matchResults.map(r => (
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

      {/* ── RADAR tab ── */}
      {mainTab === 'radar' && (
        <div className="ja-tab-content">
          <div className="ja-radar-body">
            <div className="ja-radar-chart-col">
              {/* controls */}
              <div className="ja-radar-controls">
                {renderPicker(jobA, setJobA, menuOpenA, setMenuOpenA)}
                {!splitMode && <button className="ja-btn-split" onClick={toggleSplit}>⊞ Compare</button>}
                {splitMode && renderPicker(jobB ?? null, (id) => setJobB(id), menuOpenB, setMenuOpenB)}
                {splitMode && <button className="ja-btn-close-split" onClick={toggleSplit}>✕</button>}
              </div>
              {/* legend */}
              <div className="ja-radar-legend">
                {radarDatasets.map(ds => (
                  <span key={ds.label} className="ja-legend-item">
                    <span className="ja-legend-dot" style={{ background: ds.color }} />{ds.label}
                  </span>
                ))}
              </div>
              {/* chart */}
              <div className="ja-radar-svg-wrap">
                {loadingA
                  ? <div className="ja-center"><div className="wp-spinner" /><span className="ja-status-txt">Loading…</span></div>
                  : <RadarChart datasets={radarDatasets} />
                }
              </div>
            </div>

            {/* breakdown sidebar */}
            <div className="ja-radar-sidebar">
              <div className="ja-radar-sidebar-title">Skill Area Breakdown</div>
              {radarDatasets.map(ds => (
                <div key={ds.label}>
                  <div className="ja-breakdown-ds-name" style={{ color: ds.color }}>{ds.label}</div>
                  {RADAR_AXES.map((axis, i) => {
                    const pct = Math.round(ds.values[i] * 100);
                    return (
                      <div key={axis} className="ja-bar-row">
                        <span className="ja-bar-row-lbl">{axis}</span>
                        <div className="ja-bar-track">
                          <div className="ja-bar-fill" style={{ width: `${pct}%`, background: ds.color }} />
                        </div>
                        <span className="ja-bar-pct">{pct}%</span>
                      </div>
                    );
                  })}
                </div>
              ))}
              {!skillDataA && !loadingA && (
                <p className="ja-status-txt" style={{ fontSize: '0.75rem' }}>Select a job to view the skill profile.</p>
              )}
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
                sortColA, setSortColA, sortDirA, setSortDirA,
              )}
              {splitMode && jobB && renderSkillsTable(
                'B', jobB, setJobB, skillDataB, loadingB, menuOpenB, setMenuOpenB,
                sortColB, setSortColB, sortDirB, setSortDirB,
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
