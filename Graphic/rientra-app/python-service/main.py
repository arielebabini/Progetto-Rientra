"""
main.py
───────
FastAPI application for the Rientr@ semantic microservice.

Architecture:
  • Ontology loaded + Pellet run ONCE in a background thread at startup
  • All endpoints return 503 while Pellet is still running
  • CORS enabled for React (localhost:5173) and Spring Boot (localhost:8080)
  • Auto-generated OpenAPI docs at http://localhost:8000/docs
  • POST /import/workers — import new Person individuals from a .sql dataset

Run with:
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import os
import threading
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from reasoner import (
    state,
    load_and_reason,
    load_snapshot_cache,
    get_workers,
    get_jobs,
    get_health_conditions,
    get_importance_summary,
    get_match_results,
    get_skill_detail,
    get_job_skill_profile,
    set_selected_worker,
    get_all_icf_codes,
    get_all_core_sets,
    update_health_conditions,
    update_worker_jobs,
    inject_imported_workers,
    delete_worker,
    clear_snapshot_cache,
)
from models import (
    StatusResponse,
    OntologyStats,
    WorkerSummary,
    WorkerDetail,
    JobSummary,
    JobSkillProfileEntry,
    HealthConditionsResponse,
    ImportanceEntry,
    MatchResult,
    MatchDetailRequest,
    SkillDetailResponse,
    SelectWorkerRequest,
    SelectWorkerResponse,
    IcfCodeEntry,
    HcChangeItem,
    UpdateHealthConditionsRequest,
    UpdateHealthConditionsResponse,
    UpdateWorkerJobsRequest,
    UpdateWorkerJobsResponse,
    DeleteWorkerResponse,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Lifespan — start Pellet in a background thread so the HTTP server is
#  immediately available and can respond to /status polling.
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    rdf_path = os.environ.get("ONTOLOGY_PATH", "")

    # ── Ensure the R2RML mapping file exists before the first import ──────────
    try:
        from import_workers.importer import ensure_mapping
        service_dir = Path(__file__).parent
        ontology_file = rdf_path or str(next(
            (service_dir / f for f in os.listdir(service_dir)
             if f.lower().endswith((".rdf", ".owl"))), Path()
        ))
        mapping_file = str(service_dir / "import_workers" / "rientra_mapping.ttl")
        if ontology_file and Path(ontology_file).exists():
            ensure_mapping(ontology_file, mapping_file)
    except Exception as _map_err:
        import logging as _log
        _log.getLogger(__name__).warning("[startup] Could not ensure mapping: %s", _map_err)

    load_snapshot_cache(rdf_path)
    thread = threading.Thread(
        target=load_and_reason,
        args=(rdf_path,),
        daemon=True,
        name="pellet-reasoner",
    )
    thread.start()
    yield
    # Nothing to clean up; owlready2 manages its own JVM subprocess.


# ═══════════════════════════════════════════════════════════════════════════════
#  App + CORS
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Rientr@ Semantic Microservice",
    description=(
        "REST API exposing the Rientr@ ontology reasoning results. "
        "Loads an RDF ontology, runs Pellet (DL reasoner) with SWRL rules, "
        "and serves SPARQL query outputs as structured JSON."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite / React dev server
        "http://localhost:3000",   # alternative React port
        "http://localhost:8080",   # Spring Boot backend
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ═══════════════════════════════════════════════════════════════════════════════
#  Guard — used by every endpoint that requires the reasoner to be ready
# ═══════════════════════════════════════════════════════════════════════════════

def _require_ready() -> None:
    """Raise 503 if Pellet hasn't finished yet, or 500 if it errored."""
    if state.status == "loading":
        raise HTTPException(
            status_code=503,
            detail={
                "status" : "loading",
                "message": "Ontology is still being loaded and reasoned. "
                           "Please retry in a few seconds.",
            },
        )
    if state.status == "error":
        raise HTTPException(
            status_code=500,
            detail={
                "status" : "error",
                "message": state.message,
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# ── GET /status ───────────────────────────────────────────────────────────────

@app.get(
    "/status",
    response_model=StatusResponse,
    summary="Service health and readiness",
    tags=["Service"],
)
def get_status() -> StatusResponse:
    """
    Returns the current service state:
    - **loading** — Pellet is still running (normal for the first 30–120 s)
    - **ready** — all endpoints are available
    - **error** — loading failed (check the `message` field for details)
    """
    stats = None
    if state.stats:
        stats = OntologyStats(**state.stats)
    return StatusResponse(
        status         = state.status,
        message        = state.message,
        ontology_path  = state.ontology_path,
        elapsed_pellet = state.elapsed_pellet,
        stats          = stats,
    )


# ── GET /workers ──────────────────────────────────────────────────────────────

@app.get(
    "/workers",
    response_model=list[WorkerSummary],
    summary="List all workers (Person individuals)",
    tags=["Workers"],
)
def list_workers() -> list[WorkerSummary]:
    """
    Returns all Person individuals found in the ontology that are
    associated with at least one job evaluation (`isEvaluatedForJob`).
    """
    _require_ready()
    try:
        workers = get_workers()
        return [WorkerSummary(**w) for w in workers]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── GET /workers/{worker_id} ──────────────────────────────────────────────────

@app.get(
    "/workers/{worker_id}",
    response_model=WorkerDetail,
    summary="Get a single worker by ID",
    tags=["Workers"],
)
def get_worker(worker_id: str) -> WorkerDetail:
    """
    Returns the details of the specified worker, including name,
    selection status, and the list of jobs they are evaluated for.
    """
    _require_ready()
    try:
        workers = get_workers()
        match   = next((w for w in workers if w["id"] == worker_id), None)
        if match is None:
            raise HTTPException(
                status_code=404,
                detail=f"Worker '{worker_id}' not found in ontology.",
            )
        return WorkerDetail(**match)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── DELETE /workers/{worker_id} ───────────────────────────────────────────────

@app.delete(
    "/workers/{worker_id}",
    response_model=DeleteWorkerResponse,
    summary="Permanently delete a worker and their data from the ontology",
    tags=["Workers"],
)
def delete_worker_endpoint(worker_id: str) -> DeleteWorkerResponse:
    """
    Permanently deletes a worker (Person) and all their associated health condition
    and descriptor data from the owlready2 in-memory ontology, and saves the ontology.
    """
    _require_ready()
    try:
        data = delete_worker(worker_id)
        return DeleteWorkerResponse(**data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



# ── GET /jobs ─────────────────────────────────────────────────────────────────

@app.get(
    "/jobs",
    response_model=list[JobSummary],
    summary="List all job positions",
    tags=["Jobs"],
)
def list_jobs() -> list[JobSummary]:
    """
    Returns all Job individuals that have at least one `requires` relation
    in the ontology (i.e., they require at least one Skill/Ability descriptor).
    """
    _require_ready()
    try:
        jobs = get_jobs()
        return [JobSummary(**j) for j in jobs]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── GET /health-conditions/{worker_id} ───────────────────────────────────────

@app.get(
    "/health-conditions/{worker_id}",
    response_model=HealthConditionsResponse,
    summary="Get ICF health conditions for a worker",
    tags=["Workers"],
)
def health_conditions(worker_id: str) -> HealthConditionsResponse:
    """
    Returns the ICF codes and qualifier values associated with the
    specified worker's health condition profile.
    This feeds the **Current Health Conditions** table in the React frontend.
    """
    _require_ready()
    try:
        data = get_health_conditions(worker_id)
        return HealthConditionsResponse(**data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── GET /jobs/{job_id}/importance ─────────────────────────────────────────────

@app.get(
    "/jobs/{job_id}/importance",
    response_model=list[ImportanceEntry],
    summary="Skill/ability importance summary for a job (Q4)",
    tags=["Jobs"],
)
def job_importance(job_id: str) -> list[ImportanceEntry]:
    """
    Q4 — Returns the Skill/Ability importance breakdown for a specific job,
    organised by importance level (`isVeryImportantFor`, `isImportantFor`, etc.)
    as inferred by Pellet via SWRL rules 9–12.
    """
    _require_ready()
    try:
        entries = get_importance_summary(job_id)
        if not entries:
            raise HTTPException(
                status_code=404,
                detail=f"No importance data found for job '{job_id}'.",
            )
        return [ImportanceEntry(**e) for e in entries]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── GET /match ────────────────────────────────────────────────────────────────

@app.get(
    "/match",
    response_model=list[MatchResult],
    summary="GCS%/AISA% for all selected workers × all jobs (Q1+Q2)",
    tags=["Matching"],
)
def match_all(
    worker_id: Optional[str] = Query(
        default=None,
        description="Filter results to a specific worker ID",
        examples=["Patient1"],
    ),
) -> list[MatchResult]:
    """
    Q1+Q2 — Computes the **General Criticality Score (GCS%)** and
    **Amount of Impaired Skill/Abilities (AISA%)** for every
    `(Person, Job)` pair where `isSelected = true`.

    Optionally filter to a single worker using the `worker_id` query parameter.

    The `suitability` field is derived from the classification boundaries
    of Fig. 4 of the Rientr@ paper:
    - `SUITABLE` — GCS < −0.5·AISA + 15.5
    - `SUITABLE WITH PRECAUTIONS` — GCS between the two thresholds
    - `NOT SUITABLE` — GCS > −0.5·AISA + 21
    """
    _require_ready()
    try:
        results = get_match_results(worker_id)
        return [MatchResult(**r) for r in results]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── GET /match/{worker_id} ────────────────────────────────────────────────────

@app.get(
    "/match/{worker_id}",
    response_model=list[MatchResult],
    summary="GCS%/AISA% for a specific worker across all jobs",
    tags=["Matching"],
)
def match_worker(worker_id: str) -> list[MatchResult]:
    """
    Same as `GET /match` but scoped to a single worker,
    returning one entry per job the worker is evaluated for.
    """
    _require_ready()
    try:
        results = get_match_results(worker_id)
        if not results:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No match results found for worker '{worker_id}'. "
                    "Ensure the worker has isSelected=true and isEvaluatedForJob set."
                ),
            )
        return [MatchResult(**r) for r in results]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── POST /match/detail ────────────────────────────────────────────────────────

@app.post(
    "/match/detail",
    response_model=SkillDetailResponse,
    summary="Full Skill/Ability breakdown for one (worker, job) pair (Q3)",
    tags=["Matching"],
)
def match_detail(body: MatchDetailRequest) -> SkillDetailResponse:
    """
    Q3 — Returns the per-Skill/Ability detail for a specific *(worker, job)* pair:
    - O\\*NET importance score
    - Importance anchor [0–3]
    - ICF qualifier value
    - Criticality Score (CS = qualifier × anchor)
    - Normalised CS (CS / 12)
    - Criticality label (not critical → EXTREMELY CRITICAL)

    **Request body**:
    ```json
    { "worker_id": "Patient1", "job_id": "Job_AssemblyWorker" }
    ```
    """
    _require_ready()
    try:
        data = get_skill_detail(body.worker_id, body.job_id)
        return SkillDetailResponse(**data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/jobs/{job_id}/profile",
    response_model=list[JobSkillProfileEntry],
    summary="All skills a job requires with their O*NET scores (job-only, no worker)",
    tags=["Jobs"],
)
def job_profile(job_id: str) -> list[JobSkillProfileEntry]:
    """
    Returns the complete list of Skill/Ability individuals required by the
    given job, each with its raw O*NET score (0–100).  No worker is
    involved — call this to understand what a job **tends toward** and to
    build radar / inclination charts independently of any health condition.
    """
    _require_ready()
    try:
        entries = get_job_skill_profile(job_id)
        if not entries:
            raise HTTPException(
                status_code=404,
                detail=f"No skill data found for job '{job_id}'.",
            )
        return [JobSkillProfileEntry(**e) for e in entries]
    except HTTPException:
        raise
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ═ POST /workers/select ────────────────────────────────────────────────────────────────────

@app.post(
    "/workers/select",
    response_model=SelectWorkerResponse,
    summary="Select a worker (flip isSelected in the ontology)",
    tags=["Workers"],
)
def select_worker(body: SelectWorkerRequest) -> SelectWorkerResponse:
    """
    Deselects the previously active worker and marks `worker_id` as selected
    by mutating the owlready2 in-memory ontology.
    Must be awaited by the frontend **before** calling `/match/{worker_id}`,
    otherwise the SPARQL filter `FILTER(?selected = true)` will still match
    the old worker.
    """
    _require_ready()
    try:
        data = set_selected_worker(body.worker_id)
        return SelectWorkerResponse(**data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─ GET /icf-codes ─────────────────────────────────────────────────────────────

@app.get(
    "/icf-codes",
    response_model=list[IcfCodeEntry],
    summary="All ICF code individuals from the ontology",
    tags=["Health Conditions"],
)
def list_icf_codes() -> list[IcfCodeEntry]:
    """
    Returns every ICF code that appears in any health-condition descriptor
    (`involvesICFCode` triples).  Used to populate the selection table in
    the Modify Health Condition wizard.
    """
    _require_ready()
    try:
        codes = get_all_icf_codes()
        return [IcfCodeEntry(**c) for c in codes]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─ GET /core-sets ─────────────────────────────────────────────────────────────────────

@app.get(
    "/core-sets",
    response_model=list[str],
    summary="All ICF core set labels from the ontology",
    tags=["Health Conditions"],
)
def list_core_sets() -> list[str]:
    """
    Returns the sorted list of all distinct ICF core set names that exist
    in the ontology (e.g. Stroke, Hearing Loss, Low Back Pain, ...).
    Used to populate Core Set filter dropdowns on the frontend.
    """
    _require_ready()
    try:
        return get_all_core_sets()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─ POST /health-conditions/{worker_id}/update ─────────────────────────────────

@app.post(
    "/health-conditions/{worker_id}/update",
    response_model=UpdateHealthConditionsResponse,
    summary="Apply ICF health-condition changes for a worker",
    tags=["Health Conditions"],
)
def update_worker_health_conditions(
    worker_id: str,
    body: UpdateHealthConditionsRequest,
) -> UpdateHealthConditionsResponse:
    """
    Applies a batch of `add`, `remove`, or `modify` actions to the worker’s
    health-condition profile (in-memory only; no RDF file is re-saved).

    **Request body**:
    ```json
    {
      "worker_id": "Patient1",
      "changes": [
        { "icf_code": "b1408", "action": "add",    "qualifier": 2 },
        { "icf_code": "d410",  "action": "modify", "qualifier": 3 },
        { "icf_code": "b280",  "action": "remove", "qualifier": null }
      ]
    }
    ```
    """
    _require_ready()
    try:
        changes_raw = [c.model_dump() for c in body.changes]
        data = update_health_conditions(worker_id, changes_raw)
        return UpdateHealthConditionsResponse(**data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─ POST /workers/{worker_id}/jobs/update ──────────────────────────────────────

@app.post(
    "/workers/{worker_id}/jobs/update",
    response_model=UpdateWorkerJobsResponse,
    summary="Replace the set of jobs a worker is evaluated for",
    tags=["Workers"],
)
def update_worker_jobs_endpoint(
    worker_id: str,
    body: UpdateWorkerJobsRequest,
) -> UpdateWorkerJobsResponse:
    """
    Atomically replaces all **isEvaluatedForJob** links for the given worker
    with the supplied `job_ids` list.

    After the mutation the ontology is saved to disk, Pellet is re-run, and
    the snapshot cache is refreshed — so subsequent `/match/{worker_id}` calls
    immediately reflect the new assignment.

    **Request body**:
    ```json
    { "job_ids": ["Job_AssemblyWorker", "Job_Carpenter"] }
    ```
    """
    _require_ready()
    try:
        data = update_worker_jobs(worker_id, body.job_ids)
        return UpdateWorkerJobsResponse(**data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /import/workers — import new persons from a .sql dataset
# ═══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/import/workers",
    summary="Import new Person individuals from a SQL dataset (RDB2RDF via R2RML)",
    tags=["Import"],
)
async def import_workers_endpoint(request: Request) -> JSONResponse:
    """
    Accepts the raw `.sql` file bytes as `application/octet-stream` body.
    Pass the original filename in the `X-Filename` header (optional).

    No `python-multipart` required — uses Starlette's native `request.body()`.

    Returns a JSON summary:
    ```json
    {
      "persons_added": 3,
      "persons_skipped": 0,
      "icf_valid": 42,
      "icf_skipped": 2,
      "jobs_valid": 7,
      "jobs_skipped": 1,
      "new_person_ids": ["LucaMartini", "ElenaConti", "GiuseppeFerrari"],
      "skipped_ids": [],
      "backup_path": "/abs/path/Rientra.rdf.bak",
      "error": null
    }
    ```
    """
    from import_workers.importer import import_sql_dataset, ensure_mapping

    # -- Read raw body (no python-multipart needed) --
    contents = await request.body()
    if not contents:
        raise HTTPException(status_code=422, detail="Request body is empty — send the SQL file as raw bytes.")

    filename = request.headers.get("x-filename", "dataset.sql")
    suffix   = Path(filename).suffix or ".sql"

    # -- Resolve ontology and mapping paths --
    service_dir   = Path(__file__).parent
    ontology_path = state.ontology_path or os.environ.get("ONTOLOGY_PATH", "")
    if not ontology_path:
        for fname in os.listdir(service_dir):
            if fname.lower().endswith((".rdf", ".owl")):
                ontology_path = str(service_dir / fname)
                break
    if not ontology_path or not Path(ontology_path).exists():
        raise HTTPException(
            status_code=503,
            detail="Ontology file not found. Cannot run import before the service is ready.",
        )

    mapping_path = str(service_dir / "import_workers" / "rientra_mapping.ttl")

    # -- Ensure R2RML mapping exists --
    try:
        ensure_mapping(ontology_path, mapping_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mapping generation failed: {exc}") from exc

    # -- Write bytes to a temp .sql file and run the pipeline --
    tmp_sql = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp_sql.write(contents)
        tmp_sql.close()

        result = import_sql_dataset(
            sql_path      = tmp_sql.name,
            ontology_path = ontology_path,
            mapping_path  = mapping_path,
        )
    finally:
        Path(tmp_sql.name).unlink(missing_ok=True)

    if result.validation_errors:
        return JSONResponse(
            status_code=422,
            content={
                "persons_added": 0,
                "persons_skipped": 0,
                "icf_valid": 0,
                "icf_skipped": 0,
                "jobs_valid": 0,
                "jobs_skipped": 0,
                "new_person_ids": [],
                "skipped_ids": [],
                "details": [],
                "backup_path": "",
                "validation_errors": result.validation_errors,
                "error": result.error,
                "detail": result.error,
            },
        )

    if result.error:
        raise HTTPException(status_code=500, detail=result.error)

    # Update the live in-memory ontology and snapshot cache by triggering a reload and re-running reasoning in the background
    if result.new_person_ids or result.updated_ids:
        try:
            clear_snapshot_cache(clean_disk=True)
            state.set_loading("Applying imported changes and recomputing inference...")
            thread = threading.Thread(
                target=load_and_reason,
                args=(ontology_path,),
                daemon=True,
                name="pellet-reasoner-reload",
            )
            thread.start()
        except Exception as _re_err:
            import logging as _log
            _log.getLogger(__name__).warning(
                "[import] Background reload failed to trigger: %s", _re_err
            )

    return JSONResponse({
        "persons_added"    : result.persons_added,
        "persons_updated"  : result.persons_updated,
        "persons_skipped"  : result.persons_skipped,
        "icf_valid"        : result.icf_valid,
        "icf_skipped"      : result.icf_skipped,
        "jobs_valid"       : result.jobs_valid,
        "jobs_skipped"     : result.jobs_skipped,
        "new_person_ids"   : result.new_person_ids,
        "updated_ids"      : result.updated_ids,
        "skipped_ids"      : result.skipped_ids,
        "details"          : result.details,
        "validation_errors": result.validation_errors,
        "backup_path"      : result.backup_path,
        "error"            : None,
    })


# ── POST /cache/clear ─────────────────────────────────────────────────────────
@app.post("/cache/clear", summary="Clear reasoning snapshot cache")
@app.delete("/cache", summary="Clear reasoning snapshot cache")
def clear_cache_endpoint():
    clear_snapshot_cache(clean_disk=True)
    return {"cleared": True, "message": "Reasoning snapshot cache cleared."}


# ═══════════════════════════════════════════════════════════════════════════════
#  Dev entrypoint
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,   # set True only during development
        log_level="info",
    )
