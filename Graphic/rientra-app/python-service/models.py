"""
models.py
─────────
Pydantic v2 response schemas for the Rientr@ semantic microservice.
All endpoints return instances of these models → auto-documented in /docs.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Status ────────────────────────────────────────────────────────────────────

class OntologyStats(BaseModel):
    classes:     int
    individuals: int
    properties:  int

class StatusResponse(BaseModel):
    status:         str = Field(..., examples=["ready", "loading", "error"])
    message:        str
    ontology_path:  str = ""
    elapsed_pellet: Optional[float] = Field(None, description="Pellet runtime in seconds")
    stats:          Optional[OntologyStats] = None


# ── Workers ───────────────────────────────────────────────────────────────────

class WorkerSummary(BaseModel):
    id:          str
    first_name:  str
    surname:     str
    is_selected: bool
    evaluated_for_jobs: list[str]

class WorkerDetail(BaseModel):
    id:          str
    first_name:  str
    surname:     str
    is_selected: bool
    evaluated_for_jobs: list[str]


# ── Jobs ─────────────────────────────────────────────────────────────────────

class JobSummary(BaseModel):
    id:    str
    label: str


# ── Health Conditions ─────────────────────────────────────────────────────────

class HealthCondition(BaseModel):
    icf_code:      str
    icf_name:      str = ""
    bf_qualifier:  Optional[int] = None
    ap1_qualifier: Optional[int] = None

class HealthConditionsResponse(BaseModel):
    worker_id:  str
    conditions: list[HealthCondition]


# ── Job Importance Summary  (Q4) ──────────────────────────────────────────────

class SkillScore(BaseModel):
    id:    str
    score: int

class ImportanceEntry(BaseModel):
    job_id:           str
    importance_level: str = Field(
        ...,
        examples=["isVeryImportantFor", "isImportantFor",
                  "isSomewhatImportantFor", "isLessImportantFor"],
    )
    skills: list[SkillScore]


# ── Match Results  (Q1+Q2) ───────────────────────────────────────────────────

class MatchResult(BaseModel):
    worker_id:         str
    job_id:            str
    gcs_pct:           float = Field(..., description="General Criticality Score %")
    aisa_pct:          float = Field(..., description="Amount Impaired SkAb %")
    n_total:           int   = Field(..., description="Total number of SkAb evaluated")
    n_critical:        int   = Field(..., description="Number of SkAb with CS > 0")
    suitability:       str   = Field(..., examples=["SUITABLE", "SUITABLE WITH PRECAUTIONS", "NOT SUITABLE"])
    suitability_color: str   = Field(..., examples=["#22c55e", "#f59e0b", "#ef4444"])


# ── Skill Detail  (Q3) ───────────────────────────────────────────────────────

class SkillDetail(BaseModel):
    id:                str
    score:             int   = Field(..., description="O*NET importance score [0-100]")
    importance_label:  str   = Field(..., examples=["isVeryImportantFor"])
    anchor:            int   = Field(..., description="Importance anchor [0-3]")
    qualifier:         int   = Field(..., description="ICF qualifier value")
    cs:                int   = Field(..., description="Criticality Score = qualifier × anchor")
    cs_normalized:     float = Field(..., description="CS / 12 (normalized)")
    criticality_label: str   = Field(..., examples=["MODERATELY CRITICAL"])

class SkillDetailResponse(BaseModel):
    worker_id: str
    job_id:    str
    skills:    list[SkillDetail]


# ── Request body for POST /match/detail ──────────────────────────────────────

class MatchDetailRequest(BaseModel):
    worker_id: str = Field(..., examples=["Patient1"])
    job_id:    str = Field(..., examples=["Job_AssemblyWorker"])


# ── Request / response for POST /workers/select ──────────────────────────────

class SelectWorkerRequest(BaseModel):
    worker_id: str = Field(..., examples=["Patient1"])

class SelectWorkerResponse(BaseModel):
    previous: Optional[str] = Field(
        None,
        description="ID of the worker that was previously selected (null if none).",
    )
    selected: str = Field(..., description="ID of the newly selected worker.")


# ── ICF Codes catalogue  (for HC wizard Step 1) ──────────────────────────────

class IcfCodeEntry(BaseModel):
    icf_code: str
    icf_name: str = ""
    category: str = ""
    iri:      str = ""


# ── HC update request / response ─────────────────────────────────────────────

class HcChangeItem(BaseModel):
    icf_code:  str
    action:    str = Field(..., examples=["add", "remove", "modify"])
    qualifier: Optional[int] = Field(None, ge=0, le=4)

class UpdateHealthConditionsRequest(BaseModel):
    worker_id: str
    changes:   list[HcChangeItem]

class UpdateHealthConditionsResponse(BaseModel):
    worker_id: str
    added:     int
    removed:   int
    modified:  int

