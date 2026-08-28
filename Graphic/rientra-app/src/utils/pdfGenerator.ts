/**
 * pdfGenerator.ts
 * ───────────────
 * Generates a clean, highly structured, print-optimized technical report
 * for the selected patient/worker and exports it to PDF via Electron's printToPDF
 * or web print fallback.
 *
 * Fully in English, free of emoticons, structured with clean medical/scientific layout.
 */

import type { Worker, HealthCondition, MatchResult } from '../api/semanticService';

function formatJobName(jobId: string): string {
  return jobId.replace(/^Job_/, '').replace(/_/g, ' ');
}

function getQualifierInfo(qualifier: number | null): { label: string; text: string; bg: string; color: string; border: string } {
  switch (qualifier) {
    case 0:
      return {
        label: '0',
        text: '0 — No impairment (0–4%)',
        bg: '#f0fdf4',
        color: '#166534',
        border: '#bbf7d0',
      };
    case 1:
      return {
        label: '1',
        text: '1 — Mild impairment (5–24%)',
        bg: '#f0f9ff',
        color: '#0369a1',
        border: '#bae6fd',
      };
    case 2:
      return {
        label: '2',
        text: '2 — Moderate impairment (25–49%)',
        bg: '#fffbeb',
        color: '#b45309',
        border: '#fde68a',
      };
    case 3:
      return {
        label: '3',
        text: '3 — Severe impairment (50–95%)',
        bg: '#fff7ed',
        color: '#c2410c',
        border: '#fed7aa',
      };
    case 4:
      return {
        label: '4',
        text: '4 — Complete impairment (96–100%)',
        bg: '#fef2f2',
        color: '#b91c1c',
        border: '#fecaca',
      };
    default:
      return {
        label: '—',
        text: 'Unspecified',
        bg: '#f8fafc',
        color: '#64748b',
        border: '#e2e8f0',
      };
  }
}

function getSuitabilityBadge(suitability: string): { label: string; bg: string; color: string; border: string } {
  const norm = suitability.toUpperCase();
  if (norm.includes('PRECAUTION')) {
    return {
      label: 'SUITABLE WITH PRECAUTIONS',
      bg: '#fffbeb',
      color: '#b45309',
      border: '#fde68a',
    };
  }
  if (norm.includes('NOT') || norm.includes('NON')) {
    return {
      label: 'NOT SUITABLE',
      bg: '#fef2f2',
      color: '#b91c1c',
      border: '#fecaca',
    };
  }
  return {
    label: 'SUITABLE',
    bg: '#f0fdf4',
    color: '#15803d',
    border: '#bbf7d0',
  };
}

export function buildWorkerPdfHtml(
  worker: Worker,
  conditions: HealthCondition[],
  matchResults: MatchResult[],
  isArchived: boolean = false
): string {
  const workerFullName = [worker.first_name, worker.surname].filter(Boolean).join(' ') || worker.id;
  const now = new Date();
  const dateFormatted = now.toLocaleDateString('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
  });
  const timeFormatted = now.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  // Calculate job capability counts
  let suitableCount = 0;
  let precautionsCount = 0;
  let notSuitableCount = 0;

  matchResults.forEach((r) => {
    const s = r.suitability.toUpperCase();
    if (s.includes('PRECAUTION')) precautionsCount++;
    else if (s.includes('NOT') || s.includes('NON')) notSuitableCount++;
    else suitableCount++;
  });

  const totalJobs = matchResults.length;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Worker Technical Report — ${escapeHtml(workerFullName)} (${escapeHtml(worker.id)})</title>
  <style>
    @page {
      size: A4 portrait;
      margin: 14mm 14mm 14mm 14mm;
    }
    *, *::before, *::after {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-size: 9.5pt;
      line-height: 1.45;
      color: #0f172a;
      background: #ffffff;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .pdf-container {
      max-width: 100%;
      margin: 0 auto;
    }
    
    /* ── Header ── */
    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 2px solid #0284c7;
      padding-bottom: 12px;
      margin-bottom: 16px;
    }
    .brand-group {
      display: flex;
      flex-direction: column;
    }
    .brand-title {
      font-size: 17pt;
      font-weight: 800;
      color: #0f172a;
      letter-spacing: -0.4px;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .brand-title span.accent {
      color: #0284c7;
    }
    .brand-subtitle {
      font-size: 8pt;
      font-weight: 700;
      color: #0369a1;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      margin-top: 2px;
    }
    .brand-desc {
      font-size: 8pt;
      color: #64748b;
      margin-top: 1px;
    }
    .header-meta {
      text-align: right;
      font-size: 8pt;
      color: #64748b;
    }
    .header-meta strong {
      color: #0f172a;
    }
    .doc-badge {
      display: inline-block;
      background: #f0f9ff;
      color: #0369a1;
      font-weight: 700;
      font-size: 7.5pt;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 3px 8px;
      border-radius: 4px;
      margin-bottom: 4px;
      border: 1px solid #bae6fd;
    }

    /* ── Section Title ── */
    .section-title {
      font-size: 10.5pt;
      font-weight: 700;
      color: #0f172a;
      border-left: 3px solid #0284c7;
      padding-left: 8px;
      margin-top: 16px;
      margin-bottom: 9px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      page-break-after: avoid;
    }
    .section-title small {
      font-size: 8pt;
      font-weight: 500;
      color: #64748b;
    }

    /* ── Patient / Worker Info Card ── */
    .patient-card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 10px 14px;
      display: grid;
      grid-template-columns: 1.2fr 1.8fr 1fr 1fr;
      gap: 12px;
      margin-bottom: 14px;
      page-break-inside: avoid;
    }
    .info-item {
      display: flex;
      flex-direction: column;
    }
    .info-label {
      font-size: 7pt;
      font-weight: 700;
      text-transform: uppercase;
      color: #64748b;
      letter-spacing: 0.4px;
      margin-bottom: 2px;
    }
    .info-value {
      font-size: 10pt;
      font-weight: 700;
      color: #0f172a;
    }
    .status-pill {
      display: inline-block;
      width: fit-content;
      font-size: 7.5pt;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.3px;
      padding: 2px 8px;
      border-radius: 4px;
      background: ${isArchived ? '#f1f5f9' : '#f0fdf4'};
      color: ${isArchived ? '#475569' : '#166534'};
      border: 1px solid ${isArchived ? '#cbd5e1' : '#bbf7d0'};
    }

    /* ── Summary KPI Grid ── */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-bottom: 14px;
      page-break-inside: avoid;
    }
    .kpi-card {
      border-radius: 6px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      border: 1px solid transparent;
    }
    .kpi-green {
      background: #f0fdf4;
      border-color: #bbf7d0;
    }
    .kpi-amber {
      background: #fffbeb;
      border-color: #fde68a;
    }
    .kpi-red {
      background: #fef2f2;
      border-color: #fecaca;
    }
    .kpi-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .kpi-title {
      font-size: 7.5pt;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .kpi-green .kpi-title { color: #166534; }
    .kpi-amber .kpi-title { color: #92400e; }
    .kpi-red .kpi-title { color: #991b1b; }
    
    .kpi-count {
      font-size: 16pt;
      font-weight: 800;
      margin-top: 2px;
      margin-bottom: 2px;
      line-height: 1.1;
    }
    .kpi-green .kpi-count { color: #15803d; }
    .kpi-amber .kpi-count { color: #b45309; }
    .kpi-red .kpi-count { color: #b91c1c; }

    .kpi-desc {
      font-size: 7.5pt;
      color: #64748b;
      line-height: 1.3;
    }

    /* ── Tables ── */
    table.data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 8.5pt;
      margin-bottom: 14px;
    }
    table.data-table thead {
      display: table-header-group;
    }
    table.data-table tr {
      page-break-inside: avoid;
    }
    table.data-table th {
      background: #f1f5f9;
      color: #334155;
      font-weight: 700;
      text-transform: uppercase;
      font-size: 7pt;
      letter-spacing: 0.5px;
      padding: 7px 8px;
      border: 1px solid #cbd5e1;
      text-align: left;
    }
    table.data-table td {
      padding: 6px 8px;
      border: 1px solid #e2e8f0;
      color: #0f172a;
      vertical-align: middle;
    }
    table.data-table tbody tr:nth-child(even) {
      background-color: #f8fafc;
    }

    .badge {
      display: inline-block;
      font-size: 7pt;
      font-weight: 700;
      letter-spacing: 0.3px;
      padding: 2px 7px;
      border-radius: 4px;
      white-space: nowrap;
      text-align: center;
    }
    .code-badge {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 8pt;
      font-weight: 700;
      color: #0284c7;
      background: #f0f9ff;
      border: 1px solid #bae6fd;
      padding: 1px 5px;
      border-radius: 3px;
    }
    .metric-val {
      font-weight: 600;
      font-size: 8.5pt;
    }

    /* ── Footer ── */
    .footer {
      margin-top: 24px;
      padding-top: 8px;
      border-top: 1px solid #e2e8f0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 7.5pt;
      color: #94a3b8;
      page-break-inside: avoid;
    }
    .footer strong {
      color: #64748b;
    }
  </style>
</head>
<body>
  <div class="pdf-container">
    
    <!-- ── HEADER ── -->
    <header class="header">
      <div class="brand-group">
        <div class="brand-title">
          RIENTR<span class="accent">@</span> returns
        </div>
        <div class="brand-subtitle">Decision Support System — Vocational Reintegration</div>
        <div class="brand-desc">STIIMA-CNR / INAIL Project — Clinical &amp; Vocational Technical Assessment</div>
      </div>
      <div class="header-meta">
        <div class="doc-badge">TECHNICAL REPORT</div>
        <div>Date: <strong>${dateFormatted}</strong> at <strong>${timeFormatted}</strong></div>
        <div>Report ID: <strong>RPT-${escapeHtml(worker.id)}-${now.getFullYear()}</strong></div>
      </div>
    </header>

    <!-- ── PATIENT / WORKER DEMOGRAPHICS ── -->
    <div class="patient-card">
      <div class="info-item">
        <span class="info-label">Worker ID</span>
        <span class="info-value">${escapeHtml(worker.id)}</span>
      </div>
      <div class="info-item">
        <span class="info-label">Full Name</span>
        <span class="info-value">${escapeHtml(workerFullName)}</span>
      </div>
      <div class="info-item">
        <span class="info-label">Evaluated Jobs</span>
        <span class="info-value">${totalJobs}</span>
      </div>
      <div class="info-item">
        <span class="info-label">Status</span>
        <div><span class="status-pill">${isArchived ? 'Archived' : 'Active'}</span></div>
      </div>
    </div>

    <!-- ── JOB CAPABILITY SUMMARY ── -->
    <div class="section-title">
      <span>Job Capability Summary</span>
      <small>${totalJobs} total evaluated job roles</small>
    </div>

    <div class="kpi-grid">
      <div class="kpi-card kpi-green">
        <div class="kpi-header">
          <span class="kpi-title">Suitable</span>
        </div>
        <div class="kpi-count">${suitableCount}</div>
        <div class="kpi-desc">Job roles compatible with worker abilities without critical constraints.</div>
      </div>

      <div class="kpi-card kpi-amber">
        <div class="kpi-header">
          <span class="kpi-title">With Precautions</span>
        </div>
        <div class="kpi-count">${precautionsCount}</div>
        <div class="kpi-desc">Job roles compatible subject to ergonomic adaptations or precautions.</div>
      </div>

      <div class="kpi-card kpi-red">
        <div class="kpi-header">
          <span class="kpi-title">Not Suitable</span>
        </div>
        <div class="kpi-count">${notSuitableCount}</div>
        <div class="kpi-desc">Job roles incompatible due to significantly impaired skills or abilities.</div>
      </div>
    </div>

    <!-- ── JOB SUITABILITY TABLE ── -->
    <div class="section-title">
      <span>Job Suitability Assessment Details</span>
      <small>Semantic reasoning matching algorithm (Q1–Q2)</small>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th style="width: 34%;">Job Role / Title</th>
          <th style="width: 26%; text-align: center;">Suitability Status</th>
          <th style="width: 13%; text-align: right;">GCS %</th>
          <th style="width: 13%; text-align: right;">AISA %</th>
          <th style="width: 14%; text-align: right;">Critical Skills</th>
        </tr>
      </thead>
      <tbody>
        ${
          matchResults.length === 0
            ? `<tr><td colspan="5" style="text-align: center; color: #64748b; padding: 12px;">No evaluated job roles for this worker.</td></tr>`
            : matchResults
                .slice()
                .sort((a, b) => {
                  const rank = (s: string) => {
                    const u = s.toUpperCase();
                    if (u.includes('NOT') || u.includes('NON')) return 1;
                    if (u.includes('PRECAUTION')) return 2;
                    return 3;
                  };
                  const rA = rank(a.suitability), rB = rank(b.suitability);
                  if (rA !== rB) return rA - rB;
                  return a.job_id.localeCompare(b.job_id);
                })
                .map((r) => {
                  const badge = getSuitabilityBadge(r.suitability);
                  return `
            <tr>
              <td><strong>${escapeHtml(formatJobName(r.job_id))}</strong></td>
              <td style="text-align: center;">
                <span class="badge" style="background: ${badge.bg}; color: ${badge.color}; border: 1px solid ${badge.border};">
                  ${badge.label}
                </span>
              </td>
              <td style="text-align: right;" class="metric-val">${r.gcs_pct.toFixed(1)}%</td>
              <td style="text-align: right;" class="metric-val">${r.aisa_pct.toFixed(1)}%</td>
              <td style="text-align: right; color: ${r.n_critical > 0 ? '#b91c1c' : '#166534'}; font-weight: 700;">
                ${r.n_critical} <span style="font-weight: 400; color: #64748b;">/ ${r.n_total}</span>
              </td>
            </tr>`;
                })
                .join('')
        }
      </tbody>
    </table>

    <!-- ── HEALTH CONDITIONS (ICF) ── -->
    <div class="section-title">
      <span>Functional Profile &amp; Health Conditions (ICF)</span>
      <small>${conditions.length} registered ICF codes</small>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th style="width: 14%;">ICF Code</th>
          <th style="width: 32%;">Function / Code Name</th>
          <th style="width: 24%;">Core Set</th>
          <th style="width: 30%;">Impairment Severity (Qualifier)</th>
        </tr>
      </thead>
      <tbody>
        ${
          conditions.length === 0
            ? `<tr><td colspan="4" style="text-align: center; color: #64748b; padding: 12px;">No registered health conditions for this worker.</td></tr>`
            : conditions
                .slice()
                .sort((a, b) => a.icf_code.localeCompare(b.icf_code))
                .map((c) => {
                  const q = c.bf_qualifier ?? c.ap1_qualifier;
                  const qInfo = getQualifierInfo(q);
                  const coreSetsLabel = c.core_sets && c.core_sets.length > 0 ? c.core_sets.join(', ') : '—';

                  return `
            <tr>
              <td><span class="code-badge">${escapeHtml(c.icf_code)}</span></td>
              <td>
                <strong>${escapeHtml(c.icf_name || c.icf_code)}</strong>
                ${c.description ? `<div style="font-size: 7.5pt; color: #64748b; margin-top: 2px;">${escapeHtml(c.description)}</div>` : ''}
              </td>
              <td style="font-size: 8pt; color: #475569;">${escapeHtml(coreSetsLabel)}</td>
              <td>
                <span class="badge" style="background: ${qInfo.bg}; color: ${qInfo.color}; border: 1px solid ${qInfo.border};">
                  ${escapeHtml(qInfo.text)}
                </span>
              </td>
            </tr>`;
                })
                .join('')
        }
      </tbody>
    </table>

    <!-- ── FOOTER ── -->
    <footer class="footer">
      <div>RIENTR@ DSS — Vocational Return Decision Support System (STIIMA-CNR / INAIL)</div>
      <div>Confidential document for evaluation purposes only — Generated on ${dateFormatted}</div>
    </footer>

  </div>
</body>
</html>`;
}

function escapeHtml(text: string | null | undefined): string {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export interface ExportPdfResult {
  ok: boolean;
  canceled?: boolean;
  filePath?: string;
  error?: string;
}

/**
 * Triggers PDF export for a worker.
 * Uses Electron printToPDF if running in Electron, or opens a printable window in browser.
 */
export async function exportWorkerPdf(
  worker: Worker,
  conditions: HealthCondition[],
  matchResults: MatchResult[],
  isArchived: boolean = false
): Promise<ExportPdfResult> {
  const htmlContent = buildWorkerPdfHtml(worker, conditions, matchResults, isArchived);
  const workerCleanName = [worker.first_name, worker.surname].filter(Boolean).join('_') || worker.id;
  const now = new Date();
  const dateStr = now.toISOString().slice(0, 10);
  const defaultFileName = `Worker_Report_${workerCleanName}_${dateStr}.pdf`;

  const electronAPI = (window as any).electronAPI;

  if (electronAPI?.exportPdf) {
    return await electronAPI.exportPdf({
      defaultFileName,
      htmlContent,
    });
  }

  // Fallback for standard web browser environment
  try {
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      return { ok: false, error: 'Unable to open print preview window. Please check popup blockers.' };
    }
    printWindow.document.write(htmlContent);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => {
      printWindow.print();
    }, 400);
    return { ok: true };
  } catch (err: any) {
    return { ok: false, error: err.message || 'Error generating PDF preview' };
  }
}
