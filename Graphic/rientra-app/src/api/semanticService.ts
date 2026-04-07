/**
 * semanticService.ts
 * ──────────────────
 * Typed fetch client for the Rientr@ Python semantic microservice.
 * All calls target http://127.0.0.1:8000 (the FastAPI/uvicorn process
 * spawned by Electron at startup).
 */

const BASE_URL = 'http://127.0.0.1:8000';

// ── Types (mirroring Python Pydantic models) ─────────────────────────────────

export interface ServiceStatus {
  status: 'loading' | 'ready' | 'error';
  message: string;
  ontology_path: string;
  elapsed_pellet: number | null;
  stats: { classes: number; individuals: number; properties: number } | null;
}

export interface Worker {
  id: string;
  first_name: string;
  surname: string;
  is_selected: boolean;
  evaluated_for_jobs: string[];
}

export interface HealthCondition {
  icf_code: string;
  bf_qualifier: number | null;
  ap1_qualifier: number | null;
}

export interface HealthConditionsResponse {
  worker_id: string;
  conditions: HealthCondition[];
}

export interface MatchResult {
  worker_id: string;
  job_id: string;
  gcs_pct: number;
  aisa_pct: number;
  n_total: number;
  n_critical: number;
  suitability: 'SUITABLE' | 'SUITABLE WITH PRECAUTIONS' | 'NOT SUITABLE';
  suitability_color: string;
}

// ── Generic fetch helper ──────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw Object.assign(new Error(body?.detail?.message ?? body?.detail ?? res.statusText), {
      status: res.status,
      body,
    });
  }
  return res.json() as Promise<T>;
}

// ── Exported API calls ────────────────────────────────────────────────────────

/** Poll this until status === 'ready' before calling other endpoints. */
export function fetchStatus(): Promise<ServiceStatus> {
  return apiFetch<ServiceStatus>('/status');
}

/** List all Person individuals from the ontology. */
export function fetchWorkers(): Promise<Worker[]> {
  return apiFetch<Worker[]>('/workers');
}

/** ICF health conditions for a specific worker. */
export function fetchHealthConditions(workerId: string): Promise<HealthConditionsResponse> {
  return apiFetch<HealthConditionsResponse>(`/health-conditions/${encodeURIComponent(workerId)}`);
}

/** GCS%/AISA% match results for a specific worker. */
export function fetchMatchResults(workerId: string): Promise<MatchResult[]> {
  return apiFetch<MatchResult[]>(`/match/${encodeURIComponent(workerId)}`);
}

// ── Skill / Ability detail (Q3) ───────────────────────────────────────────────

export interface SkillDetail {
  id: string;
  score: number;
  importance_label: string;
  anchor: number;
  qualifier: number;
  cs: number;
  cs_normalized: number;
  criticality_label: string;
}

export interface SkillDetailResponse {
  worker_id: string;
  job_id: string;
  skills: SkillDetail[];
}

/** Full Skill/Ability breakdown for one (worker, job) pair — Q3. */
export function fetchSkillDetail(
  workerId: string,
  jobId: string,
): Promise<SkillDetailResponse> {
  return apiFetch<SkillDetailResponse>('/match/detail', {
    method: 'POST',
    body: JSON.stringify({ worker_id: workerId, job_id: jobId }),
  });
}

// ── Worker selection ──────────────────────────────────────────────────────────

export interface SelectWorkerResponse {
  previous: string | null;
  selected: string;
}

/**
 * Flip isSelected in the ontology: deselect the previous worker,
 * select workerId. Must be awaited BEFORE fetching match results so
 * the SPARQL FILTER(?selected = true) sees the correct worker.
 */
export function selectWorker(workerId: string): Promise<SelectWorkerResponse> {
  return apiFetch<SelectWorkerResponse>('/workers/select', {
    method: 'POST',
    body: JSON.stringify({ worker_id: workerId }),
  });
}
