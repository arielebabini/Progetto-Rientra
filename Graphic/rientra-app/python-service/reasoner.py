"""
reasoner.py
───────────
Pure logic layer for the Rientr@ semantic microservice.
Wraps owlready2 + Pellet reasoning; no print/Rich/matplotlib output.
All public functions are safe to call after `load_and_reason()` completes.
"""

from __future__ import annotations

import io
import os
import re
import contextlib
import threading
import warnings
import logging
import time
from collections import defaultdict
from typing import Optional

# ── silence owlready2 / Java logs ────────────────────────────────────────────
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

try:
    import owlready2
    owlready2.set_log_level(0)
    from owlready2 import (
        default_world,
        get_ontology,
        sync_reasoner_pellet,
        Thing,
    )
except ImportError as exc:
    raise ImportError(
        "owlready2 is not installed. Run: pip install owlready2\n"
        "Also requires Java 11+ in PATH for Pellet."
    ) from exc


# ═══════════════════════════════════════════════════════════════════════════════
#  IRI constants  (from the Rientr@ ontology namespace)
# ═══════════════════════════════════════════════════════════════════════════════

IRI_IS_VERY_IMP = "http://www.stiima.cnr.it/JobDescription#isVeryImportantFor"
IRI_IS_IMP      = "http://www.stiima.cnr.it/JobDescription#isImportantFor"
IRI_IS_SOMEWHAT = "http://www.stiima.cnr.it/JobDescription#isSomewhatImportantFor"
IRI_IS_LESS     = "http://www.stiima.cnr.it/JobDescription#isLessImportantFor"

IRI_HAS_CRIT    = "http://www.stiima.cnr.it/RientraOnt3#hasSpecificCriticality"
IRI_REQUIRES    = "http://www.stiima.cnr.it/JobList#requires"
IRI_CONCERNS    = "http://www.stiima.cnr.it/JobList#concerns"
IRI_HAS_SCORE   = "http://www.stiima.cnr.it/JobList#hasScore"
IRI_IS_EVAL_JOB = "http://www.stiima.cnr.it/RientraOnt3#isEvaluatedForJob"
IRI_IS_IN_HC    = "http://www.stiima.cnr.it/RientraHC#isInHealthCondition"
IRI_IS_SELECTED = "http://www.stiima.cnr.it/RientraOnt3Merged#isSelected"
IRI_IS_TRANSL   = "http://www.stiima.cnr.it/SkAb#isTranslatedWithICFCode"
IRI_BFQUAL      = "http://www.stiima.cnr.it/RientraHC#BFqual"
IRI_AP1QUAL     = "http://www.stiima.cnr.it/RientraHC#AP1qual"
IRI_FIRST_NAME  = "http://www.stiima.cnr.it/FOAF-excerpt#first_name"
IRI_SURNAME     = "http://www.stiima.cnr.it/FOAF-excerpt#surname"
IRI_IS_DESCRIBED_BY   = "http://www.stiima.cnr.it/RientraHC#isDescribedBy"
IRI_INVOLVES_ICF      = "http://www.stiima.cnr.it/RientraHC#involvesICFCode"
IRI_ICF_DESCRIPTION   = "http://www.stiima.cnr.it/ICF-exc-coreset#description"
IRI_ONET_DEFINITION   = "http://www.stiima.cnr.it/SkAb#O*Net_definition"

# Suitability thresholds (Fig. 4 of the paper)
JS_RED_INTERCEPT    = 21.0
JS_YELLOW_INTERCEPT = 15.5
JS_SLOPE            = -0.5

IMPORTANCE_IRIS: dict[str, str] = {
    "isVeryImportantFor"    : IRI_IS_VERY_IMP,
    "isImportantFor"        : IRI_IS_IMP,
    "isSomewhatImportantFor": IRI_IS_SOMEWHAT,
    "isLessImportantFor"    : IRI_IS_LESS,
}

SUITABILITY_COLORS: dict[str, str] = {
    "SUITABLE"                  : "#22c55e",
    "SUITABLE WITH PRECAUTIONS" : "#f59e0b",
    "NOT SUITABLE"              : "#ef4444",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Global service state  (managed by load_and_reason, read by endpoints)
# ═══════════════════════════════════════════════════════════════════════════════

class ReasonerState:
    """Thread-safe singleton holding the service readiness state."""

    def __init__(self) -> None:
        self._lock          = threading.Lock()
        self.status         = "loading"   # "loading" | "ready" | "error"
        self.message        = "Ontology not yet loaded."
        self.ontology_path  = ""
        self.elapsed_pellet: Optional[float] = None
        self.stats: dict    = {}

    def set_ready(self, path: str, elapsed: Optional[float], stats: dict) -> None:
        with self._lock:
            self.status        = "ready"
            self.ontology_path = path
            self.elapsed_pellet = elapsed
            self.stats         = stats
            msg = f"Pellet completed"
            if elapsed:
                msg += f" in {elapsed:.1f}s"
            self.message = msg

    def set_error(self, error: str) -> None:
        with self._lock:
            self.status  = "error"
            self.message = error

    def is_ready(self) -> bool:
        return self.status == "ready"


# Module-level singleton — imported by main.py
state = ReasonerState()

# Lock that serialises any in-memory isSelected mutations
_selection_lock = threading.Lock()

# Cache: local ICF code name -> sorted list of core set labels
_icf_core_set_map: dict[str, list[str]] = {}


# ═══════════════════════════════════════════════════════════════════════════════
#  Core-set membership map  (built once after load_and_reason)
# ═══════════════════════════════════════════════════════════════════════════════

IRI_ICF_CORE_SET = "http://www.stiima.cnr.it/ICF-exc-coreset#ICF_Core_set"

def _build_icf_core_set_map() -> None:
    """
    Build _icf_core_set_map by querying which core set classes each ICF code
    class belongs to (transitively via rdfs:subClassOf+).
    Must be called AFTER the ontology is loaded.
    """
    global _icf_core_set_map
    # Find all direct subclasses of ICF_Core_set — these ARE the core sets
    rows = _sparql(f"""
        SELECT DISTINCT ?icf ?coreset WHERE {{
            ?icf <http://www.w3.org/2000/01/rdf-schema#subClassOf>+ ?coreset .
            ?coreset <http://www.w3.org/2000/01/rdf-schema#subClassOf> <{IRI_ICF_CORE_SET}> .
        }}
    """)
    result: dict[str, list[str]] = {}
    for icf_cls, cs_cls in rows:
        icf_name = local_name(icf_cls) if hasattr(icf_cls, 'name') else str(icf_cls).split('#')[-1]
        cs_name  = local_name(cs_cls).replace('_', ' ')
        if icf_name not in result:
            result[icf_name] = []
        if cs_name not in result[icf_name]:
            result[icf_name].append(cs_name)
    # Sort each list for deterministic output
    for k in result:
        result[k] = sorted(result[k])
    _icf_core_set_map = result


def get_all_core_sets() -> list[str]:
    """
    Return a sorted list of all distinct core set names present in the ontology.
    Built from _icf_core_set_map, so must be called after _build_icf_core_set_map.
    """
    labels: set[str] = set()
    for cs_list in _icf_core_set_map.values():
        labels.update(cs_list)
    return sorted(labels)


# ═══════════════════════════════════════════════════════════════════════════════
#  Utility functions
# ═══════════════════════════════════════════════════════════════════════════════

def local_name(entity) -> str:
    """Return the local fragment of an IRI (after # or last /)."""
    if hasattr(entity, "name"):
        return entity.name
    s = str(entity)
    return s.split("#")[-1] if "#" in s else s.split("/")[-1]


def criticality_label(cs: int) -> str:
    """Map CS value to human-readable label (Fig. 2 of the paper)."""
    if   cs >= 7: return "EXTREMELY CRITICAL"
    elif cs >= 5: return "RELEVANTLY CRITICAL"
    elif cs >= 3: return "MODERATELY CRITICAL"
    elif cs >= 1: return "SLIGHTLY CRITICAL"
    else:         return "not critical"


def job_suitability(gcs: float, aisa: float) -> tuple[str, str]:
    """Return (suitability_label, hex_color) per Fig. 4 of the paper."""
    thr_red    = JS_SLOPE * aisa + JS_RED_INTERCEPT
    thr_yellow = JS_SLOPE * aisa + JS_YELLOW_INTERCEPT
    if gcs > thr_red:
        label = "NOT SUITABLE"
    elif gcs >= thr_yellow:
        label = "SUITABLE WITH PRECAUTIONS"
    else:
        label = "SUITABLE"
    return label, SUITABILITY_COLORS[label]


def _score_to_anchor(score: int) -> int:
    """Convert O*NET score to importance anchor (Table 2 of the paper)."""
    if score >= 75: return 3
    if score >= 50: return 2
    if score >= 26: return 1
    return 0


def _sparql(query: str) -> list:
    """Execute a SPARQL query on the owlready2 default_world."""
    return list(default_world.sparql(query))


def _find_rdf_file() -> str:
    """Auto-detect the first .rdf/.owl/.ttl/.n3 file in service dir or parent."""
    service_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs = [service_dir, os.path.dirname(service_dir)]
    extensions  = (".rdf", ".owl", ".ttl", ".n3")
    for folder in search_dirs:
        try:
            candidates = sorted(
                f for f in os.listdir(folder)
                if f.lower().endswith(extensions)
            )
            if candidates:
                return os.path.join(folder, candidates[0])
        except PermissionError:
            continue
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 1 — Load ontology
# ═══════════════════════════════════════════════════════════════════════════════

def _load_ontology(path: str):
    """Load the ontology file into the owlready2 default_world."""
    abs_path = os.path.abspath(path)
    iri = f"file://{abs_path}"
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        try:
            onto = get_ontology(iri).load()
        except Exception as exc:
            raise RuntimeError(f"Cannot load ontology: {exc}") from exc
    return onto


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 2 — Run Pellet reasoner
# ═══════════════════════════════════════════════════════════════════════════════

def _run_pellet(onto) -> Optional[float]:
    """
    Run Pellet via owlready2; handle ICF inheritance cycles gracefully.
    Returns elapsed seconds if Pellet reported them, else None.
    """
    ThingMeta = type(Thing)
    orig_setattr = ThingMeta.__setattr__

    def patched_setattr(self, name, value):
        if name == "__bases__":
            try:
                orig_setattr(self, name, value)
            except TypeError as exc:
                if "inheritance cycle" not in str(exc):
                    raise
        else:
            orig_setattr(self, name, value)

    try:
        ThingMeta.__setattr__ = patched_setattr
        stderr_buf = io.StringIO()
        with contextlib.redirect_stderr(stderr_buf):
            with onto:
                sync_reasoner_pellet(
                    infer_property_values=True,
                    infer_data_property_values=True,
                )
        pellet_log = stderr_buf.getvalue()
        time_match = re.search(r"Pellet took ([\d.]+)", pellet_log)
        return float(time_match.group(1)) if time_match else None
    except Exception as exc:
        msg = str(exc)
        if "UnsupportedClassVersionError" in msg:
            raise RuntimeError(
                "Java version too old for Pellet. Requires Java 11+. "
                "Check with: java -version"
            ) from exc
        raise RuntimeError(f"Pellet error: {exc}") from exc
    finally:
        ThingMeta.__setattr__ = orig_setattr


# ═══════════════════════════════════════════════════════════════════════════════
#  Public entrypoint — called from the FastAPI lifespan in a background thread
# ═══════════════════════════════════════════════════════════════════════════════

def load_and_reason(rdf_path: str = "") -> None:
    """
    Load ontology + run Pellet in one call.
    Updates the global `state` object when done (or on error).
    Designed to run in a background thread so the HTTP server starts immediately.
    """
    path = rdf_path or os.environ.get("ONTOLOGY_PATH", "") or _find_rdf_file()
    if not path:
        state.set_error(
            "No .rdf/.owl/.ttl/.n3 file found. "
            "Set the ONTOLOGY_PATH environment variable or place the file "
            "in the python-service/ directory (or its parent)."
        )
        return

    try:
        onto = _load_ontology(path)
    except RuntimeError as exc:
        state.set_error(str(exc))
        return

    try:
        elapsed = _run_pellet(onto)
    except RuntimeError as exc:
        state.set_error(str(exc))
        return

    stats = {
        "classes"     : len(list(default_world.classes())),
        "individuals" : len(list(default_world.individuals())),
        "properties"  : len(list(default_world.properties())),
    }
    state.set_ready(path, elapsed, stats)
    # Build ICF → Core Set lookup map once, after reasoning is complete
    _build_icf_core_set_map()


# ═══════════════════════════════════════════════════════════════════════════════
#  Query — Workers  (Person individuals)
# ═══════════════════════════════════════════════════════════════════════════════

def get_workers() -> list[dict]:
    """
    Return a list of all Person individuals that have isEvaluatedForJob.
    Falls back to querying by isSelected if the first query is empty.
    """
    fn_prop  = default_world.search_one(iri=IRI_FIRST_NAME)
    sur_prop = default_world.search_one(iri=IRI_SURNAME)
    sel_prop = default_world.search_one(iri=IRI_IS_SELECTED)
    eval_prop = default_world.search_one(iri=IRI_IS_EVAL_JOB)

    # Collect all persons via isEvaluatedForJob
    rows = _sparql(f"""
        SELECT DISTINCT ?person WHERE {{
            ?person <{IRI_IS_EVAL_JOB}> ?job .
        }}
    """)

    result = []
    seen   = set()
    for (person,) in rows:
        pid = local_name(person)
        if pid in seen:
            continue
        seen.add(pid)

        fn  = fn_prop[person][0]  if (fn_prop  and fn_prop[person])  else ""
        sur = sur_prop[person][0] if (sur_prop and sur_prop[person]) else ""
        is_sel = bool(sel_prop[person][0]) if (sel_prop and sel_prop[person]) else False

        # Jobs this person is evaluated for
        jobs = []
        if eval_prop and eval_prop[person]:
            jobs = [local_name(j) for j in eval_prop[person]]

        result.append({
            "id"                 : pid,
            "first_name"         : str(fn)  if fn  else "",
            "surname"            : str(sur) if sur else "",
            "is_selected"        : is_sel,
            "evaluated_for_jobs" : jobs,
        })

    result.sort(key=lambda w: w["id"])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Query — Jobs
# ═══════════════════════════════════════════════════════════════════════════════

def get_jobs() -> list[dict]:
    """Return all Job individuals (those that have at least one 'requires' triple)."""
    rows = _sparql(f"""
        SELECT DISTINCT ?job WHERE {{
            ?job <{IRI_REQUIRES}> ?jde .
        }}
    """)
    result = []
    seen   = set()
    for (job,) in rows:
        jid = local_name(job)
        if jid in seen:
            continue
        seen.add(jid)
        result.append({
            "id"   : jid,
            "label": jid.replace("_", " "),
        })
    result.sort(key=lambda j: j["id"])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Query — Health conditions for one worker  (feeds the ICF table in React)
# ═══════════════════════════════════════════════════════════════════════════════

def get_health_conditions(worker_id: str) -> dict:
    """
    Return the ICF health conditions for a given worker.
    Queries: person → isInHealthCondition → HC → isDescribedBy → descriptor
             descriptor → involvesICFCode, BFqual, AP1qual
    """
    person_ind = default_world.search_one(iri=f"*#{worker_id}")
    if person_ind is None:
        raise KeyError(f"Worker '{worker_id}' not found in ontology.")

    rows = _sparql(f"""
        SELECT ?icf ?desc ?bfq ?ap1q WHERE {{
            <{person_ind.iri}> <{IRI_IS_IN_HC}> ?hc .
            ?hc  <{IRI_IS_DESCRIBED_BY}>  ?des .
            ?des <{IRI_INVOLVES_ICF}>      ?icf .
            OPTIONAL {{ ?icf <{IRI_ICF_DESCRIPTION}> ?desc }}
            OPTIONAL {{ ?des <{IRI_BFQUAL}>  ?bfq  }}
            OPTIONAL {{ ?des <{IRI_AP1QUAL}> ?ap1q }}
        }}
    """)

    conditions = []
    seen_icf   = set()
    import re as _re
    for icf, desc_raw, bfq_raw, ap1q_raw in rows:
        full_id  = local_name(icf)
        if full_id in seen_icf:
            continue
        seen_icf.add(full_id)

        # Split compound identifiers like "b1408-AuditoryAttention"
        # into pure code ("b1408") and embedded name ("AuditoryAttention").
        if '-' in full_id:
            icf_code, embedded_name = full_id.split('-', 1)
            # Add spaces before capital letters: "AuditoryAttention" → "Auditory Attention"
            embedded_name = _re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', embedded_name)
        else:
            icf_code      = full_id
            embedded_name = ""

        # Prefer explicit ontology rdfs:label; fall back to the embedded name part
        labels   = getattr(icf, "label", [])
        icf_name = str(labels[0]) if labels else embedded_name

        core_sets = _icf_core_set_map.get(icf_code, [])

        conditions.append({
            "icf_code"     : icf_code,
            "icf_name"     : icf_name,
            "description"  : str(desc_raw).strip() if desc_raw is not None else "",
            "core_sets"    : core_sets,
            "bf_qualifier" : int(bfq_raw)  if bfq_raw  is not None else None,
            "ap1_qualifier": int(ap1q_raw) if ap1q_raw is not None else None,
        })

    conditions.sort(key=lambda c: c["icf_code"])
    return {
        "worker_id" : worker_id,
        "conditions": conditions,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Query — Job importance summary  (Q4)
# ═══════════════════════════════════════════════════════════════════════════════

def get_importance_summary(job_id: Optional[str] = None) -> list[dict]:
    """
    Q4 — is*ImportantFor triples for jobs (SWRL rules 9–12).
    If job_id is given, returns only that job's summary.
    Returns a list of { job_id, importance_level, skills: [{id, score}] }.
    """
    raw: dict = defaultdict(lambda: defaultdict(list))

    for label, iri in IMPORTANCE_IRIS.items():
        rows = _sparql(f"""
            SELECT ?skab ?job ?score WHERE {{
                ?skab <{iri}> ?job .
                ?jde  <{IRI_CONCERNS}> ?skab .
                ?job  <{IRI_REQUIRES}> ?jde .
                ?jde  <{IRI_HAS_SCORE}> ?score .
            }}
        """)
        for skab, job, score in rows:
            j_id = local_name(job)
            if job_id and j_id != job_id:
                continue
            raw[j_id][label].append({
                "id"   : local_name(skab),
                "score": int(score),
            })

    result = []
    for j_id in sorted(raw):
        for imp_label in IMPORTANCE_IRIS:
            skills = sorted(raw[j_id].get(imp_label, []), key=lambda s: -s["score"])
            if skills:
                result.append({
                    "job_id"         : j_id,
                    "importance_level": imp_label,
                    "skills"         : skills,
                })
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Query — Job skill/ability demand profile  (used by radar chart)
# ═══════════════════════════════════════════════════════════════════════════════

def get_job_skill_profile(job_id: str) -> list[dict]:
    """
    Returns every Skill/Ability required by the given job with its raw O*NET
    score (0–100).  This is purely job-side data — no worker is involved —
    so comparing two jobs actually reflects their different skill demands.

    Used by the frontend radar chart to show what a job 'tends toward'
    (e.g. Carpenter → high Physical scores).
    """
    job_ind = default_world.search_one(iri=f"*#{job_id}")
    if job_ind is None:
        raise KeyError(f"Job '{job_id}' not found in ontology.")

    rows = _sparql(f"""
        SELECT DISTINCT ?skab ?score WHERE {{
            <{job_ind.iri}> <{IRI_REQUIRES}> ?jde .
            ?jde  <{IRI_CONCERNS}>  ?skab .
            ?jde  <{IRI_HAS_SCORE}> ?score .
        }}
    """)

    seen: dict = {}
    for skab, score_raw in rows:
        key   = str(skab)
        score = int(score_raw) if score_raw is not None else 0
        # keep highest score if duplicated
        if key not in seen or score > seen[key]["score"]:
            seen[key] = {"id": local_name(skab), "score": score}

    result = sorted(seen.values(), key=lambda s: (-s["score"], s["id"]))
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Query — GCS% and AISA% for all selected workers × jobs  (Q1+Q2)
# ═══════════════════════════════════════════════════════════════════════════════

def get_match_results(worker_id: Optional[str] = None) -> list[dict]:
    """
    Q1+Q2 — GCS% and AISA% for every (Person, Job) pair where isSelected=true.
    If worker_id is given, filters to that person only.
    Mirrors query_gcs_aisa() from ontology_reasoner.py.
    """
    rows = _sparql(f"""
        SELECT ?person ?job ?skab ?score ?bfq ?ap1q WHERE {{
            ?person <{IRI_IS_EVAL_JOB}> ?job .
            ?person <{IRI_IS_SELECTED}> ?selected .
            FILTER(?selected = true)
            ?job    <{IRI_REQUIRES}>    ?jde .
            ?jde    <{IRI_CONCERNS}>    ?skab .
            ?jde    <{IRI_HAS_SCORE}>   ?score .
            ?skab   <{IRI_IS_TRANSL}>   ?icf .
            ?person <{IRI_IS_IN_HC}>    ?hc .
            ?hc  <http://www.stiima.cnr.it/RientraHC#isDescribedBy> ?des .
            ?des <http://www.stiima.cnr.it/RientraHC#involvesICFCode> ?icf .
            OPTIONAL {{ ?des <{IRI_BFQUAL}>  ?bfq  }}
            OPTIONAL {{ ?des <{IRI_AP1QUAL}> ?ap1q }}
        }}
    """)

    # Fallback to hasSpecificCriticality if the primary query returns nothing
    if not rows:
        return _match_results_fallback(worker_id)

    agg: dict = {}
    for person, job, skab, score_raw, bfq_raw, ap1q_raw in rows:
        p_id   = local_name(person)
        j_id   = local_name(job)
        s_id   = local_name(skab)
        if worker_id and p_id != worker_id:
            continue
        score = int(score_raw) if score_raw is not None else 0
        bfq   = int(bfq_raw)  if bfq_raw  is not None else 0
        ap1q  = int(ap1q_raw) if ap1q_raw is not None else 0
        qual  = max(bfq, ap1q)
        key   = (p_id, j_id)
        if key not in agg:
            agg[key] = {"worker_id": p_id, "job_id": j_id, "skabs": {}}
        prev = agg[key]["skabs"].get(s_id)
        if prev is None or qual > prev["qual"]:
            agg[key]["skabs"][s_id] = {"score": score, "qual": qual}

    return _compute_metrics(agg)


def _match_results_fallback(worker_id: Optional[str]) -> list[dict]:
    rows_crit = _sparql(f"""
        SELECT ?skab ?cs ?job ?person WHERE {{
            ?skab   <{IRI_HAS_CRIT}>    ?cs .
            ?jde    <{IRI_CONCERNS}>    ?skab .
            ?job    <{IRI_REQUIRES}>    ?jde .
            ?person <{IRI_IS_EVAL_JOB}> ?job .
            ?person <{IRI_IS_SELECTED}> ?selected .
            FILTER(?selected = true)
        }}
    """)
    aggregated: dict = {}
    for skab, cs_raw, job, person in rows_crit:
        p_id = local_name(person)
        j_id = local_name(job)
        s_id = local_name(skab)
        if worker_id and p_id != worker_id:
            continue
        cs  = int(cs_raw) if cs_raw is not None else 0
        key = (p_id, j_id)
        if key not in aggregated:
            aggregated[key] = {"worker_id": p_id, "job_id": j_id, "cs_by_skab": {}}
        if cs > aggregated[key]["cs_by_skab"].get(s_id, -1):
            aggregated[key]["cs_by_skab"][s_id] = cs

    results = []
    for (p_id, j_id), data in sorted(aggregated.items()):
        cs_values = list(data["cs_by_skab"].values())
        n_total   = len(cs_values)
        n_crit    = sum(1 for cs in cs_values if cs > 0)
        sum_norm  = sum(cs / 12.0 for cs in cs_values)
        gcs_pct   = (sum_norm / n_total) * 100.0 if n_total > 0 else 0.0
        aisa_pct  = (n_crit  / n_total) * 100.0 if n_total > 0 else 0.0
        suit, color = job_suitability(gcs_pct, aisa_pct)
        results.append({
            "worker_id"        : p_id,
            "job_id"           : j_id,
            "gcs_pct"          : round(gcs_pct, 4),
            "aisa_pct"         : round(aisa_pct, 4),
            "n_total"          : n_total,
            "n_critical"       : n_crit,
            "suitability"      : suit,
            "suitability_color": color,
        })
    return results


def _compute_metrics(agg: dict) -> list[dict]:
    results = []
    for (p_id, j_id), data in sorted(agg.items()):
        cs_values = []
        for s_id, entry in data["skabs"].items():
            anchor = _score_to_anchor(entry["score"])
            cs     = entry["qual"] * anchor
            cs_values.append(cs)
        n_total  = len(cs_values)
        n_crit   = sum(1 for cs in cs_values if cs > 0)
        sum_norm = sum(cs / 12.0 for cs in cs_values)
        gcs_pct  = (sum_norm / n_total) * 100.0 if n_total > 0 else 0.0
        aisa_pct = (n_crit  / n_total) * 100.0 if n_total > 0 else 0.0
        suit, color = job_suitability(gcs_pct, aisa_pct)
        results.append({
            "worker_id"        : p_id,
            "job_id"           : j_id,
            "gcs_pct"          : round(gcs_pct, 4),
            "aisa_pct"         : round(aisa_pct, 4),
            "n_total"          : n_total,
            "n_critical"       : n_crit,
            "suitability"      : suit,
            "suitability_color": color,
        })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  Query — Skill/Ability detail for one (worker, job) pair  (Q3)
# ═══════════════════════════════════════════════════════════════════════════════

def get_skill_detail(worker_id: str, job_id: str) -> dict:
    """
    Q3 — Full Skill/Ability breakdown for one (worker, job) pair.
    Returns computed CS, anchor, qualifier, and criticality label per SkAb.
    """
    person_ind = default_world.search_one(iri=f"*#{worker_id}")
    job_ind    = default_world.search_one(iri=f"*#{job_id}")

    if person_ind is None:
        raise KeyError(f"Worker '{worker_id}' not found.")
    if job_ind is None:
        raise KeyError(f"Job '{job_id}' not found.")

    rows = _sparql(f"""
        SELECT ?skab ?cs ?score ?def WHERE {{
            ?skab   <{IRI_HAS_CRIT}>    ?cs .
            ?jde    <{IRI_CONCERNS}>    ?skab .
            <{job_ind.iri}> <{IRI_REQUIRES}> ?jde .
            ?jde    <{IRI_HAS_SCORE}>   ?score .
            <{person_ind.iri}> <{IRI_IS_EVAL_JOB}> <{job_ind.iri}> .
            OPTIONAL {{
                ?skab <{IRI_ONET_DEFINITION}> ?def .
            }}
        }}
    """)

    best: dict = {}
    for skab, cs_raw, score_raw, def_raw in rows:
        cs    = int(cs_raw)    if cs_raw    is not None else 0
        score = int(score_raw) if score_raw is not None else 0
        key   = str(skab)
        defn  = str(def_raw).strip() if def_raw is not None else ""
        if key not in best or cs > best[key]["cs"]:
            best[key] = {"cs": cs, "score": score, "obj": skab, "desc": defn}
        elif not best[key]["desc"] and defn:
            best[key]["desc"] = defn

    anchor_to_label: dict[int, str] = {
        3: "isVeryImportantFor",
        2: "isImportantFor",
        1: "isSomewhatImportantFor",
        0: "isLessImportantFor",
    }

    skills = []
    for entry in best.values():
        cs     = entry["cs"]
        score  = entry["score"]
        anchor = _score_to_anchor(score)
        qual   = cs // anchor if anchor > 0 else 0
        skills.append({
            "id"               : local_name(entry["obj"]),
            "score"            : score,
            "importance_label" : anchor_to_label.get(anchor, "isLessImportantFor"),
            "anchor"           : anchor,
            "qualifier"        : qual,
            "cs"               : cs,
            "cs_normalized"    : round(cs / 12.0, 6),
            "criticality_label": criticality_label(cs),
            "description"      : entry.get("desc", ""),
        })

    skills.sort(key=lambda s: (-s["cs"], s["id"]))
    return {
        "worker_id": worker_id,
        "job_id"   : job_id,
        "skills"   : skills,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Mutation — Flip isSelected for a given worker  (called by POST /workers/select)
# ═══════════════════════════════════════════════════════════════════════════════

def set_selected_worker(worker_id: str) -> dict:
    """
    Atomically deselect the currently selected worker and select the given one.
    Uses a threading.Lock so concurrent requests cannot corrupt the state.
    Returns {"previous": old_id_or_None, "selected": worker_id}.
    """
    sel_prop = default_world.search_one(iri=IRI_IS_SELECTED)
    if sel_prop is None:
        raise KeyError("isSelected property not found in ontology.")

    target = default_world.search_one(iri=f"*#{worker_id}")
    if target is None:
        raise KeyError(f"Worker '{worker_id}' not found in ontology.")

    with _selection_lock:
        old_id: Optional[str] = None
        for ind in default_world.individuals():
            vals = sel_prop[ind]
            if vals and bool(vals[0]):
                old_id = local_name(ind)
                sel_prop[ind] = [False]
        sel_prop[target] = [True]

    return {"previous": old_id, "selected": worker_id}


# ═══════════════════════════════════════════════════════════════════════════════
#  Query — All ICF codes in the ontology  (feeds the HC wizard Step 1)
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_icf_codes() -> list[dict]:
    """
    Return every ICF code individual that appears in any health-condition
    descriptor (involvesICFCode triples).  Used to populate the selection
    table in the Modify-Health-Condition wizard.
    """
    import re as _re

    rows = _sparql(f"""
        SELECT DISTINCT ?icf ?desc WHERE {{
            ?des <{IRI_INVOLVES_ICF}> ?icf .
            OPTIONAL {{ ?icf <{IRI_ICF_DESCRIPTION}> ?desc }}
        }}
    """)

    by_code: dict[str, dict] = {}
    for icf, desc_raw in rows:
        full_id = local_name(icf)

        # Split "b1408-AuditoryAttention" → code + name
        if '-' in full_id:
            icf_code, embedded = full_id.split('-', 1)
            embedded_name = _re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', embedded)
        else:
            icf_code      = full_id
            embedded_name = ""

        labels   = getattr(icf, "label", [])
        icf_name = str(labels[0]) if labels else embedded_name

        # ICF category: b* → Body Functions, d* → Activities & Participation
        prefix = icf_code[0].lower() if icf_code else ""
        if prefix == 'b':
            category = "Body Functions"
        elif prefix == 'd':
            category = "Activities and Participation"
        elif prefix == 's':
            category = "Body Structures"
        elif prefix == 'e':
            category = "Environmental Factors"
        else:
            category = "Other"

        core_sets = sorted(set(_icf_core_set_map.get(icf_code, [])))
        existing = by_code.get(icf_code)

        if existing is None:
            by_code[icf_code] = {
                "icf_code" : icf_code,
                "icf_name" : icf_name,
                "description": str(desc_raw).strip() if desc_raw is not None else "",
                "category" : category,
                "core_sets": core_sets,
                "iri"      : str(icf.iri),
            }
            continue

        # The wizard operates on the pure ICF code, so multiple ontology
        # individuals that collapse to the same code must be merged into one row.
        if not existing["icf_name"] and icf_name:
            existing["icf_name"] = icf_name
        if not existing["description"] and desc_raw is not None:
            existing["description"] = str(desc_raw).strip()
        if existing["category"] == "Other" and category != "Other":
            existing["category"] = category
        existing["core_sets"] = sorted(set(existing["core_sets"]) | set(core_sets))

    result = list(by_code.values())
    result.sort(key=lambda x: x["icf_code"])
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Mutation — Update health conditions for a worker
# ═══════════════════════════════════════════════════════════════════════════════

# Lock for HC mutations
_hc_lock = threading.Lock()

# Cache: pure ICF code (e.g. "b1408") -> owlready2 individual object
_icf_ind_cache: dict[str, object] = {}


def _build_icf_ind_cache() -> None:
    """
    Populate _icf_ind_cache by scanning all involvesICFCode triples.
    Maps the pure code prefix (e.g. "b1408") to the owlready2 individual.
    """
    global _icf_ind_cache
    cache: dict[str, object] = {}
    rows = _sparql(
        "SELECT DISTINCT ?icf WHERE { ?des <" + IRI_INVOLVES_ICF + "> ?icf . }"
    )
    for (icf_ind,) in rows:
        raw  = local_name(icf_ind)
        code = raw.split("-")[0]
        if code not in cache:
            cache[code] = icf_ind
    _icf_ind_cache = cache


def _resolve_icf_individual(icf_code: str) -> object | None:
    """
    Find the owlready2 individual for a given pure ICF code.
    Uses the pre-built cache; falls back to live ontology search.
    """
    if icf_code in _icf_ind_cache:
        return _icf_ind_cache[icf_code]
    # Wildcard prefix (handles "b1408-AuditoryAttention")
    ind = default_world.search_one(iri="*#" + icf_code + "-*")
    if ind is not None:
        _icf_ind_cache[icf_code] = ind
        return ind
    # Exact match
    ind = default_world.search_one(iri="*#" + icf_code)
    if ind is not None:
        _icf_ind_cache[icf_code] = ind
        return ind
    # Linear scan (last resort)
    for candidate in default_world.individuals():
        cname = local_name(candidate)
        if cname == icf_code or cname.startswith(icf_code + "-"):
            _icf_ind_cache[icf_code] = candidate
            return candidate
    return None


def _is_ap1_code(icf_code: str) -> bool:
    """
    Return True for Activities & Participation codes (d-prefix),
    which use AP1qual instead of BFqual.
    """
    return icf_code.lower().startswith("d")


def update_health_conditions(worker_id: str, changes: list[dict]) -> dict:
    """
    Apply a batch of health-condition changes for the given worker and update
    the in-memory owlready2 ontology graph.

    Each change dict must contain:
        {
            "icf_code" : str,             # e.g. "b1408"
            "action"   : "add" | "remove" | "modify",
            "qualifier": int | None       # 0-4; required for add/modify
        }

    Ontological implications handled:
    ─────────────────────────────────
    ADD
      * Resolves the ICF individual from the ontology (cache then live search).
      * Creates a new Descriptor individual of the appropriate class.
      * Sets involvesICFCode -> ICF individual.
      * Sets BFqual for b-codes, AP1qual for d-codes (clears the other).
      * Links the descriptor to the worker's HealthCondition via isDescribedBy.
      * If the worker has no HC yet, a new HealthCondition individual is created
        and linked via isInHealthCondition.
      * If the ICF code already has a descriptor (duplicate add), treated as
        a modify of the existing qualifier.

    REMOVE
      * Locates the Descriptor whose involvesICFCode matches the given code.
      * Removes it from HC.isDescribedBy.
      * Calls owlready2.destroy_entity() to remove all triples for the descriptor.
      * If the HealthCondition ends up with no descriptors, it is also destroyed
        and unlinked from the person (clean HC lifecycle).

    MODIFY
      * Locates the Descriptor for the given ICF code.
      * Updates BFqual (b-codes) or AP1qual (d-codes) to the new qualifier value.
      * Clears the other qualifier property to avoid stale data.

    Note: Pellet is NOT re-run after mutations. GCS/AISA calculation reads
    BFqual/AP1qual directly, so match results update correctly without re-reasoning.
    """
    person_ind = default_world.search_one(iri="*#" + worker_id)
    if person_ind is None:
        raise KeyError("Worker '" + worker_id + "' not found in ontology.")

    is_in_hc_prop   = default_world.search_one(iri=IRI_IS_IN_HC)
    is_described_by = default_world.search_one(iri=IRI_IS_DESCRIBED_BY)
    involves_icf    = default_world.search_one(iri=IRI_INVOLVES_ICF)
    bfqual_prop     = default_world.search_one(iri=IRI_BFQUAL)
    ap1qual_prop    = default_world.search_one(iri=IRI_AP1QUAL)

    missing = [
        n for n, p in [
            ("isInHealthCondition", is_in_hc_prop),
            ("isDescribedBy",       is_described_by),
            ("involvesICFCode",     involves_icf),
            ("BFqual",              bfqual_prop),
            ("AP1qual",             ap1qual_prop),
        ] if p is None
    ]
    if missing:
        raise RuntimeError("Cannot find ontology properties: " + str(missing))

    added = removed = modified = 0
    errors: list[str] = []

    with _hc_lock:

        # Populate ICF cache if needed
        if not _icf_ind_cache:
            _build_icf_ind_cache()

        # Build descriptor map: icf_code -> {"hc": hc_ind, "des": des_ind}
        desc_map: dict[str, dict] = {}
        hc_inds: list = list(is_in_hc_prop[person_ind] or [])
        for hc_ind in hc_inds:
            for des_ind in list(is_described_by[hc_ind] or []):
                for icf_ind in list(involves_icf[des_ind] or []):
                    code = local_name(icf_ind).split("-")[0]
                    if code not in desc_map:
                        desc_map[code] = {"hc": hc_ind, "des": des_ind}

        # Helper: get or create HealthCondition
        def _get_or_create_hc() -> object:
            nonlocal hc_inds
            if hc_inds:
                return hc_inds[0]
            hc_class = None
            for c in default_world.classes():
                cn = local_name(c)
                if cn in ("HealthCondition", "HC") or "HealthCondition" in cn:
                    hc_class = c
                    break
            if hc_class is None:
                raise RuntimeError("Cannot find HealthCondition class.")
            new_hc = hc_class()
            cur = list(is_in_hc_prop[person_ind] or [])
            cur.append(new_hc)
            is_in_hc_prop[person_ind] = cur
            hc_inds = list(is_in_hc_prop[person_ind] or [])
            return new_hc

        # Find Descriptor class
        des_class = None
        for c in default_world.classes():
            cn = local_name(c)
            if "Descriptor" in cn or "descriptor" in cn.lower():
                des_class = c
                break

        # Apply each change
        for change in changes:
            icf_code   = change["icf_code"]
            action     = change["action"]
            qualifier  = change.get("qualifier")
            use_ap1    = _is_ap1_code(icf_code)
            q_prop     = ap1qual_prop if use_ap1 else bfqual_prop
            other_prop = bfqual_prop  if use_ap1 else ap1qual_prop

            # REMOVE
            if action == "remove":
                entry = desc_map.get(icf_code)
                if entry is None:
                    errors.append("remove: '" + icf_code + "' not found in worker's HC.")
                    continue
                hc_ind  = entry["hc"]
                des_ind = entry["des"]
                cur = list(is_described_by[hc_ind] or [])
                if des_ind in cur:
                    cur.remove(des_ind)
                    is_described_by[hc_ind] = cur
                try:
                    owlready2.destroy_entity(des_ind)
                except Exception:
                    pass
                # Destroy empty HC
                if not list(is_described_by[hc_ind] or []):
                    cur_hcs = list(is_in_hc_prop[person_ind] or [])
                    if hc_ind in cur_hcs:
                        cur_hcs.remove(hc_ind)
                        is_in_hc_prop[person_ind] = cur_hcs
                    try:
                        owlready2.destroy_entity(hc_ind)
                    except Exception:
                        pass
                    if hc_ind in hc_inds:
                        hc_inds.remove(hc_ind)
                desc_map.pop(icf_code, None)
                removed += 1

            # MODIFY
            elif action == "modify":
                if qualifier is None:
                    errors.append("modify: qualifier required for '" + icf_code + "'.")
                    continue
                entry = desc_map.get(icf_code)
                if entry is None:
                    errors.append("modify: '" + icf_code + "' not found in worker's HC.")
                    continue
                des_ind = entry["des"]
                q_prop[des_ind]     = [int(qualifier)]
                other_prop[des_ind] = []
                modified += 1

            # ADD
            elif action == "add":
                if qualifier is None:
                    errors.append("add: qualifier required for '" + icf_code + "'.")
                    continue
                if icf_code in desc_map:
                    # Already present -> treat as modify
                    des_ind = desc_map[icf_code]["des"]
                    q_prop[des_ind]     = [int(qualifier)]
                    other_prop[des_ind] = []
                    modified += 1
                    continue
                icf_ind = _resolve_icf_individual(icf_code)
                if icf_ind is None:
                    errors.append("add: ICF individual '" + icf_code + "' not found in ontology.")
                    continue
                hc_ind  = _get_or_create_hc()
                des_ind = des_class() if des_class is not None else Thing()
                involves_icf[des_ind] = [icf_ind]
                q_prop[des_ind]       = [int(qualifier)]
                other_prop[des_ind]   = []
                cur = list(is_described_by[hc_ind] or [])
                cur.append(des_ind)
                is_described_by[hc_ind] = cur
                desc_map[icf_code] = {"hc": hc_ind, "des": des_ind}
                added += 1

            else:
                errors.append("Unknown action '" + action + "' for code '" + icf_code + "'.")

    result: dict = {
        "worker_id": worker_id,
        "added"    : added,
        "removed"  : removed,
        "modified" : modified,
    }
    if errors:
        result["errors"] = errors
    return result
