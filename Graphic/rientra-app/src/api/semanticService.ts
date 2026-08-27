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
  icf_name: string;
  description: string;
  core_sets: string[];
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
  description: string;
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

// ── Job skill-demand profile (radar chart, no worker needed) ──────────────────

export interface JobSkillEntry {
  id: string;
  score: number; // raw O*NET score 0–100, purely job-side
}

/**
 * All skills a job requires with their O*NET scores.
 * Worker-independent: use for the radar "inclination" chart to show
 * what a job is oriented toward (e.g. Carpenter → high Physical scores).
 */
export function fetchJobProfile(jobId: string): Promise<JobSkillEntry[]> {
  return apiFetch<JobSkillEntry[]>(`/jobs/${encodeURIComponent(jobId)}/profile`);
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

// ── Worker deletion ───────────────────────────────────────────────────────────

export interface DeleteWorkerResponse {
  worker_id: string;
  deleted: boolean;
}

/**
 * Permanently delete a worker and their data from the ontology.
 */
export function deleteWorker(workerId: string): Promise<DeleteWorkerResponse> {
  return apiFetch<DeleteWorkerResponse>(`/workers/${encodeURIComponent(workerId)}`, {
    method: 'DELETE',
  });
}


// ── ICF catalogue (HC wizard) ─────────────────────────────────────────────────

export interface IcfCodeEntry {
  icf_code: string;
  icf_name: string;
  description: string;
  category: string;
  core_sets: string[];
  iri: string;
}

/** All ICF codes in the ontology — used in the Modify Health Conditions wizard. */
export function fetchAllIcfCodes(): Promise<IcfCodeEntry[]> {
  return apiFetch<IcfCodeEntry[]>('/icf-codes');
}

/** All distinct ICF core set labels in the ontology (e.g. "Stroke", "Low Back Pain"). */
export function fetchCoreSets(): Promise<string[]> {
  return apiFetch<string[]>('/core-sets');
}

// ── HC mutation ───────────────────────────────────────────────────────────────

export interface HcChangeItem {
  icf_code: string;
  action: 'add' | 'remove' | 'modify';
  qualifier: number | null;
}

export interface UpdateHcResponse {
  worker_id: string;
  added: number;
  removed: number;
  modified: number;
}

/** Apply a batch of add/remove/modify changes to a worker's health conditions. */
export function updateHealthConditions(
  workerId: string,
  changes: HcChangeItem[],
): Promise<UpdateHcResponse> {
  return apiFetch<UpdateHcResponse>(`/health-conditions/${encodeURIComponent(workerId)}/update`, {
    method: 'POST',
    body: JSON.stringify({ worker_id: workerId, changes }),
  });
}

export interface ValidationErrorItem {
  category: 'schema' | 'person' | 'health_condition' | 'job' | 'ontology_conflict' | string;
  message: string;
  person_id?: string;
  field?: string;
  value?: string;
  fix_hint?: string;
}

export interface ImportedPersonDetail {
  person_id: string;
  fullname: string;
  is_updated?: boolean;
  icfs: string[];
  jobs: string[];
}

export interface ImportWorkersResult {
  persons_added: number;
  persons_updated?: number;
  persons_skipped: number;
  icf_valid: number;
  icf_skipped: number;
  jobs_valid: number;
  jobs_skipped: number;
  new_person_ids: string[];
  updated_ids?: string[];
  skipped_ids: string[];
  details?: ImportedPersonDetail[];
  validation_errors?: ValidationErrorItem[];
  backup_path: string;
  error: string | null;
}

/**
 * Upload a .sql dataset file to the Python service and run the RDB2RDF pipeline.
 * Sends the raw bytes as application/octet-stream — no python-multipart needed.
 */
export async function importWorkers(
  fileBytes: number[],
  fileName: string,
): Promise<ImportWorkersResult> {
  const body = new Uint8Array(fileBytes);

  const res = await fetch(`${BASE_URL}/import/workers`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/octet-stream',
      'X-Filename': fileName,
    },
    body,
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: res.statusText }));
    // If backend returned a structured 422 validation report, return it directly
    if (data?.validation_errors && Array.isArray(data.validation_errors)) {
      return data as ImportWorkersResult;
    }
    throw Object.assign(
      new Error(data?.detail?.message ?? data?.detail ?? data?.error ?? res.statusText),
      { status: res.status, body: data },
    );
  }
  return res.json() as Promise<ImportWorkersResult>;
}

// ── Job catalogue (for job-assignment editor) ──────────────────────────────────

export interface JobEntry {
  id: string;
  label: string;
}

/** All Job individuals that have at least one 'requires' triple in the ontology. */
export function fetchAllJobs(): Promise<JobEntry[]> {
  return apiFetch<JobEntry[]>('/jobs');
}

// ── Worker job-assignment mutation ────────────────────────────────────────────

export interface UpdateWorkerJobsResponse {
  worker_id:  string;
  previous:   string[];
  assigned:   string[];
  unresolved: string[];
}

/**
 * Replace the complete set of isEvaluatedForJob links for a worker.
 * Triggers a full Pellet re-run on the backend so match results are refreshed.
 */
export function updateWorkerJobs(
  workerId: string,
  jobIds: string[],
): Promise<UpdateWorkerJobsResponse> {
  return apiFetch<UpdateWorkerJobsResponse>(
    `/workers/${encodeURIComponent(workerId)}/jobs/update`,
    {
      method: 'POST',
      body: JSON.stringify({ job_ids: jobIds }),
    },
  );
}
