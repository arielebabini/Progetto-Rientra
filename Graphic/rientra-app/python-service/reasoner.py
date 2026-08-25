"""
reasoner.py
───────────
Pure logic layer for the Rientr@ semantic microservice.
Wraps owlready2 + Pellet reasoning; no print/Rich/matplotlib output.
All public functions are safe to call after `load_and_reason()` completes.
"""

from __future__ import annotations

import io
import json
import os
import re
import hashlib
import contextlib
import threading
import warnings
import logging
import time
from collections import defaultdict
from typing import Optional, Any, cast

# ── silence owlready2 / Java logs ────────────────────────────────────────────
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

try:
    import owlready2
    owlready2.set_log_level(0)

    # ── Configure custom Java path if passed from Electron or bundled locally ──
    import os
    from pathlib import Path
    if "JAVA_EXE" in os.environ:
        owlready2.JAVA_EXE = os.environ["JAVA_EXE"]
    else:
        # Fallback detection for bundled JRE relative to this script
        _current_dir = Path(__file__).parent.resolve()
        for _candidate in [
            _current_dir / "jre" / "Contents" / "Home" / "bin" / "java",
            _current_dir / "jre-mac" / "Contents" / "Home" / "bin" / "java",
            _current_dir / "jre" / "bin" / "java.exe",
            _current_dir / "jre-win" / "bin" / "java.exe",
        ]:
            if _candidate.exists():
                owlready2.JAVA_EXE = str(_candidate)
                break

    from owlready2 import (
        default_world,
        get_ontology,
        sync_reasoner_pellet,
        Thing,
        owl_world,
    )
except ImportError as exc:
    raise ImportError(
        "owlready2 is not installed. Run: pip install owlready2\n"
        "Also requires Java 17+ in PATH for Pellet."
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
IRI_ONET_DEFINITION   = "http://www.stiima.cnr.it/SkAb#ONet_definition"

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

    def set_ready_from_cache(self, path: str, stats: dict) -> None:
        with self._lock:
            self.status = "ready"
            self.ontology_path = path
            self.elapsed_pellet = None
            self.stats = stats
            self.message = "Inference snapshot loaded from local cache."

    def set_loading(self, message: str) -> None:
        with self._lock:
            self.status = "loading"
            self.message = message

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
_snapshot_cache: dict[str, Any] | None = None
# Convenience alias — owlready2 property objects are fully dynamic; annotating
# search_one() return values as OWLProp suppresses false-positive subscript errors.
OWLProp = Any
_live_reasoner_ready = False
_pending_selected_worker_id: Optional[str] = None
_loaded_ontology = None


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
    if _use_snapshot_cache():
        return list(cast(dict, _snapshot_cache)["core_sets"])

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


def _resolve_rdf_path(rdf_path: str = "") -> str:
    """Resolve the ontology path from arg, env var, or autodetection."""
    return rdf_path or os.environ.get("ONTOLOGY_PATH", "") or _find_rdf_file()


def _ontology_fingerprint(path: str) -> str:
    """
    Build a cheap fingerprint for the ontology source so cached snapshots are
    invalidated when the RDF file changes.
    """
    abs_path = os.path.abspath(path)
    stat = os.stat(abs_path)
    payload = f"{abs_path}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _snapshot_cache_path(path: str) -> str:
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reasoning_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"inference_{_ontology_fingerprint(path)}.json")


def _use_snapshot_cache() -> bool:
    return _snapshot_cache is not None and not _live_reasoner_ready


def is_live_reasoner_ready() -> bool:
    return _live_reasoner_ready


def load_snapshot_cache(rdf_path: str = "", update_state: bool = True) -> bool:
    """
    Load a previously saved reasoning snapshot, if present and still valid.
    Returns True when the snapshot was loaded and the service can serve cached
    read-only data immediately.
    """
    global _snapshot_cache

    path = _resolve_rdf_path(rdf_path)
    if not path:
        return False

    try:
        cache_path = _snapshot_cache_path(path)
    except OSError:
        return False

    if not os.path.exists(cache_path):
        return False

    try:
        with open(cache_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False

    required_keys = {
        "source_hash",
        "source_path",
        "stats",
        "workers",
        "jobs",
        "core_sets",
        "icf_codes",
        "health_conditions",
        "importance_by_job",
        "job_profiles",
        "match_results_by_worker",
        "skill_details_by_worker_job",
    }
    if not required_keys.issubset(payload):
        return False

    _snapshot_cache = payload
    if update_state:
        state.set_ready_from_cache(path, payload.get("stats", {}))
    return True


def _save_snapshot_cache(source_path: str, elapsed: Optional[float], stats: dict) -> None:
    """
    Persist the inferred read models so the next startup can serve them
    instantly while the live reasoner warms in background.
    """
    cache_path = _snapshot_cache_path(source_path)
    workers = get_workers()
    jobs = get_jobs()

    selected_before = next((w["id"] for w in workers if w.get("is_selected")), None)
    match_results_by_worker: dict[str, list[dict]] = {}
    skill_details_by_worker_job: dict[str, dict[str, dict]] = {}
    health_conditions: dict[str, dict] = {}

    for worker in workers:
        worker_id = worker["id"]
        health_conditions[worker_id] = get_health_conditions(worker_id)
        prev = set_selected_worker(worker_id)
        try:
            match_results_by_worker[worker_id] = get_match_results(worker_id)
            worker_jobs = {}
            for job_id in worker.get("evaluated_for_jobs", []):
                worker_jobs[job_id] = get_skill_detail(worker_id, job_id)
            skill_details_by_worker_job[worker_id] = worker_jobs
        finally:
            if prev["previous"] and prev["previous"] != worker_id:
                set_selected_worker(prev["previous"])

    if selected_before:
        set_selected_worker(selected_before)
    else:
        sel_prop = default_world.search_one(iri=IRI_IS_SELECTED)
        if sel_prop is not None:
            for ind in default_world.individuals():
                if sel_prop[ind]:
                    sel_prop[ind] = [False]

    importance_by_job: dict[str, list[dict]] = {}
    job_profiles: dict[str, list[dict]] = {}
    for job in jobs:
        job_id = job["id"]
        importance_by_job[job_id] = get_importance_summary(job_id)
        job_profiles[job_id] = get_job_skill_profile(job_id)

    payload = {
        "source_hash": _ontology_fingerprint(source_path),
        "source_path": os.path.abspath(source_path),
        "elapsed_pellet_s": elapsed,
        "stats": stats,
        "workers": workers,
        "jobs": jobs,
        "core_sets": get_all_core_sets(),
        "icf_codes": get_all_icf_codes(),
        "health_conditions": health_conditions,
        "importance_by_job": importance_by_job,
        "job_profiles": job_profiles,
        "match_results_by_worker": match_results_by_worker,
        "skill_details_by_worker_job": skill_details_by_worker_job,
    }

    tmp_path = f"{cache_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True)
    os.replace(tmp_path, cache_path)


def _save_live_ontology(path: str) -> None:
    """Persist the current in-memory ontology graph back to the RDF file."""
    if _loaded_ontology is None:
        raise RuntimeError("Ontology is not loaded in memory.")
    _loaded_ontology.save(file=os.path.abspath(path), format="rdfxml")


def inject_imported_workers(
    new_person_ids: list[str],
    ontology_path: str,
) -> dict:
    """
    Update the live ontology and snapshot cache after a successful SQL import.

    The import pipeline writes new Person individuals (with isEvaluatedForJob
    triples) to the RDF file on disk, but the in-memory owlready2 graph and
    snapshot cache are NOT automatically updated.  Calling this function:

      1. Re-reads the isEvaluatedForJob triples for each new person from the
         updated RDF file (using rdflib, not owlready2) and injects them into
         the live owlready2 ontology.
      2. Updates the snapshot cache in-memory so subsequent calls to
         get_match_results / get_workers / get_health_conditions return fresh
         data without requiring a full Pellet re-run.
      3. Persists the updated snapshot to disk.

    Returns a dict with counts of workers whose data was successfully updated.
    """
    global _snapshot_cache

    if not _live_reasoner_ready:
        # Reasoner not ready yet — skip; next startup will rebuild the cache
        return {"updated": 0, "note": "reasoner_not_ready"}

    try:
        from rdflib import Graph, URIRef
        from rdflib.namespace import RDF
    except ImportError:
        return {"updated": 0, "note": "rdflib_not_installed"}

    IRI_EVAL_PROP = URIRef(IRI_IS_EVAL_JOB)
    IRI_IS_IN_HC_URI = URIRef(IRI_IS_IN_HC)
    IRI_IS_SEL_URI = URIRef(IRI_IS_SELECTED)

    # Parse the updated RDF file with rdflib to extract new triples
    g = Graph()
    g.parse(ontology_path, format="xml")

    eval_prop  = default_world.search_one(iri=IRI_IS_EVAL_JOB)
    sel_prop   = default_world.search_one(iri=IRI_IS_SELECTED)
    fn_prop    = default_world.search_one(iri=IRI_FIRST_NAME)
    sur_prop   = default_world.search_one(iri=IRI_SURNAME)

    updated_count = 0

    for person_id in new_person_ids:
        person_iri = URIRef(f"http://www.stiima.cnr.it/Person-CommonBox#{person_id}")
        person_ind = default_world.search_one(iri=str(person_iri))
        if person_ind is None:
            # Person not found in live ontology — skip (Pellet re-run will fix)
            continue

        # Inject isEvaluatedForJob links from the updated RDF file
        if eval_prop is not None:
            new_jobs = [
                default_world.search_one(iri=str(job_iri))
                for job_iri in g.objects(person_iri, IRI_EVAL_PROP)
            ]
            new_jobs = [j for j in new_jobs if j is not None]
            if new_jobs:
                existing = list(eval_prop[person_ind]) if eval_prop[person_ind] else []
                existing_iris = {j.iri for j in existing}
                for job in new_jobs:
                    if job.iri not in existing_iris:
                        existing.append(job)
                eval_prop[person_ind] = existing

        # Ensure isSelected = false for new workers
        if sel_prop is not None and not sel_prop[person_ind]:
            sel_prop[person_ind] = [False]

        updated_count += 1

    # Refresh snapshot cache to include new workers
    if _snapshot_cache is not None:
        try:
            _save_snapshot_cache(ontology_path, None, _snapshot_cache.get("stats", {}))
            load_snapshot_cache(ontology_path, update_state=False)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "[inject_imported_workers] Cache refresh failed: %s", exc
            )

    return {"updated": updated_count}



def _refresh_reasoning_artifacts() -> None:
    """
    Re-run Pellet on the updated ontology, then regenerate the local JSON
    snapshot used for fast startup.
    """
    global _snapshot_cache, _live_reasoner_ready

    ontology_path = state.ontology_path
    if not ontology_path:
        raise RuntimeError("Ontology path is unknown; cannot refresh reasoning artifacts.")
    if _loaded_ontology is None:
        raise RuntimeError("Ontology is not loaded in memory.")

    state.set_loading("Applying health-condition changes and recomputing inference...")
    _live_reasoner_ready = False
    _snapshot_cache = None

    try:
        _save_live_ontology(ontology_path)
        elapsed = _run_pellet(_loaded_ontology)
        _build_icf_core_set_map()
        _build_icf_ind_cache()

        stats = {
            "classes": len(list(default_world.classes())),
            "individuals": len(list(default_world.individuals())),
            "properties": len(list(default_world.properties())),
        }

        _live_reasoner_ready = True
        state.set_ready(ontology_path, elapsed, stats)
        _save_snapshot_cache(ontology_path, elapsed, stats)
        load_snapshot_cache(ontology_path, update_state=False)
    except Exception as exc:
        state.set_error(str(exc))
        raise


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 1 — Load ontology
# ═══════════════════════════════════════════════════════════════════════════════

def _load_ontology(path: str, reload: bool = False):
    """Load the ontology file into the owlready2 default_world."""
    abs_path = os.path.abspath(path)
    iri = f"file://{abs_path}"

    if reload:
        try:
            default_world.close()
        except Exception:
            pass
        default_world.ontologies.clear()
        default_world._props.clear()
        default_world._reasoning_props.clear()
        default_world._entities.clear()
        default_world._namespaces.clear()
        default_world._fusion_class_cache.clear()
        default_world._rdflib_store = None
        default_world.graph = None

        if owl_world is not None:
            default_world._entities.update(owl_world._entities)
            default_world._props.update(owl_world._props)

        try:
            default_world.set_backend(backend="sqlite", filename=":memory:")
            default_world.get_ontology("http://anonymous/")
        except Exception as exc:
            raise RuntimeError(f"Cannot reset owlready2 backend: {exc}") from exc

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        try:
            onto = get_ontology(iri).load(reload=reload)
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
        ThingMeta.__setattr__ = patched_setattr  # type: ignore[assignment]  # intentional monkey-patch, reverted in finally
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
                f"Java version too old for Pellet. Requires Java 17+. Actual error: {msg}"
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
    global _live_reasoner_ready, _pending_selected_worker_id, _loaded_ontology, _icf_ind_cache

    path = _resolve_rdf_path(rdf_path)
    if not path:
        state.set_error(
            "No .rdf/.owl/.ttl/.n3 file found. "
            "Set the ONTOLOGY_PATH environment variable or place the file "
            "in the python-service/ directory (or its parent)."
        )
        return

    # Preserve currently selected worker before reloading to restore it later
    current_selected = None
    if _live_reasoner_ready:
        try:
            sel_prop = default_world.search_one(iri=IRI_IS_SELECTED)
            if sel_prop is not None:
                for ind in default_world.individuals():
                    vals = sel_prop[ind]
                    if vals and bool(vals[0]):
                        current_selected = local_name(ind)
                        break
        except Exception:
            pass
    if not current_selected and _pending_selected_worker_id:
        current_selected = _pending_selected_worker_id
    if not current_selected and _snapshot_cache:
        workers = _snapshot_cache.get("workers", [])
        current_selected = next((w["id"] for w in workers if w.get("is_selected")), None)

    # Clean up previous state to allow reload
    _live_reasoner_ready = False
    _icf_ind_cache.clear()

    try:
        onto = _load_ontology(path, reload=True)
        _loaded_ontology = onto
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
    _live_reasoner_ready = True
    
    # Restore the selected worker (either what was selected before, or what is pending)
    target_selected = current_selected or _pending_selected_worker_id
    if target_selected:
        try:
            set_selected_worker(target_selected)
        except Exception:
            pass
    _pending_selected_worker_id = None

    state.set_ready(path, elapsed, stats)
    # Build ICF → Core Set lookup map once, after reasoning is complete
    _build_icf_core_set_map()
    try:
        _save_snapshot_cache(path, elapsed, stats)
        load_snapshot_cache(path, update_state=False)
    except Exception:
        # Cache persistence is best-effort; the live API must remain available.
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  Query — Workers  (Person individuals)
# ═══════════════════════════════════════════════════════════════════════════════

def get_workers() -> list[dict]:
    """
    Return a list of all Person individuals that have isEvaluatedForJob.
    Falls back to querying by isSelected if the first query is empty.
    """
    if _use_snapshot_cache():
        return list(cast(dict, _snapshot_cache)["workers"])

    fn_prop:   OWLProp = default_world.search_one(iri=IRI_FIRST_NAME)
    sur_prop:  OWLProp = default_world.search_one(iri=IRI_SURNAME)
    sel_prop:  OWLProp = default_world.search_one(iri=IRI_IS_SELECTED)
    eval_prop: OWLProp = default_world.search_one(iri=IRI_IS_EVAL_JOB)

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
    if _use_snapshot_cache():
        return list(cast(dict, _snapshot_cache)["jobs"])

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
    if _use_snapshot_cache():
        cached = cast(dict, _snapshot_cache)["health_conditions"].get(worker_id)
        if cached is None:
            raise KeyError(f"Worker '{worker_id}' not found in cache.")
        return cached

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
    if _use_snapshot_cache():
        sc = cast(dict, _snapshot_cache)
        if job_id:
            return list(sc["importance_by_job"].get(job_id, []))
        result: list[dict] = []
        for entries in sc["importance_by_job"].values():
            result.extend(entries)
        return result

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
    if _use_snapshot_cache():
        entries = cast(dict, _snapshot_cache)["job_profiles"].get(job_id)
        if entries is None:
            raise KeyError(f"Job '{job_id}' not found in cache.")
        return list(entries)

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
    if _use_snapshot_cache():
        sc = cast(dict, _snapshot_cache)
        if worker_id:
            return list(sc["match_results_by_worker"].get(worker_id, []))
        result: list[dict] = []
        selected_ids = {
            worker["id"]
            for worker in sc["workers"]
            if worker.get("is_selected")
        }
        for wid, entries in sc["match_results_by_worker"].items():
            if selected_ids and wid not in selected_ids:
                continue
            result.extend(entries)
        return result

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
    if _use_snapshot_cache():
        worker_cache = cast(dict, _snapshot_cache)["skill_details_by_worker_job"].get(worker_id, {})
        cached = worker_cache.get(job_id)
        if cached is None:
            raise KeyError(f"No cached detail found for worker '{worker_id}' and job '{job_id}'.")
        return cached

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
    if _use_snapshot_cache():
        global _pending_selected_worker_id
        workers = cast(dict, _snapshot_cache)["workers"]
        target = next((w for w in workers if w["id"] == worker_id), None)
        if target is None:
            raise KeyError(f"Worker '{worker_id}' not found in cache.")

        old_id: Optional[str] = None
        for worker in workers:
            if worker.get("is_selected"):
                old_id = worker["id"]
            worker["is_selected"] = (worker["id"] == worker_id)
        _pending_selected_worker_id = worker_id
        return {"previous": old_id, "selected": worker_id}

    sel_prop: OWLProp = default_world.search_one(iri=IRI_IS_SELECTED)
    if sel_prop is None:
        raise KeyError("isSelected property not found in ontology.")

    target: OWLProp = default_world.search_one(iri=f"*#{worker_id}")
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
    if _use_snapshot_cache():
        return list(cast(dict, _snapshot_cache)["icf_codes"])

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

    After the mutation batch is applied:
      * the ontology is saved back to the RDF file on disk
      * Pellet is re-run on the updated ontology
      * the local JSON snapshot is overwritten with the new inferred data
    """
    if not _live_reasoner_ready:
        raise RuntimeError(
            "The live ontology is still warming up in background. "
            "Health-condition updates will be available as soon as the reasoner finishes."
        )

    person_ind = default_world.search_one(iri="*#" + worker_id)
    if person_ind is None:
        raise KeyError("Worker '" + worker_id + "' not found in ontology.")

    is_in_hc_prop:   OWLProp = default_world.search_one(iri=IRI_IS_IN_HC)
    is_described_by: OWLProp = default_world.search_one(iri=IRI_IS_DESCRIBED_BY)
    involves_icf:    OWLProp = default_world.search_one(iri=IRI_INVOLVES_ICF)
    bfqual_prop:     OWLProp = default_world.search_one(iri=IRI_BFQUAL)
    ap1qual_prop:    OWLProp = default_world.search_one(iri=IRI_AP1QUAL)

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

    def _safe_set_prop(prop, ind, value: int | None) -> None:
        """
        Safely assign a single value to a data property.

        owlready2 merges rather than replaces at the RDF-triple level when you
        do `prop[ind] = [new_value]` on an individual that already has a value
        for that property.  For **functional** properties (BFqual, AP1qual)
        this creates two triples → Pellet raises InconsistentOntologyException.

        The fix: always clear the property to [] first, then set the new value.
        """
        prop[ind] = []           # flush all existing triples for this (ind, prop) pair
        if value is not None:
            prop[ind] = [value]  # now assign the single new value

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
                _safe_set_prop(q_prop,     des_ind, int(qualifier))
                _safe_set_prop(other_prop, des_ind, None)
                modified += 1

            # ADD
            elif action == "add":
                if qualifier is None:
                    errors.append("add: qualifier required for '" + icf_code + "'.")
                    continue
                if icf_code in desc_map:
                    # Already present -> treat as modify
                    des_ind = desc_map[icf_code]["des"]
                    _safe_set_prop(q_prop,     des_ind, int(qualifier))
                    _safe_set_prop(other_prop, des_ind, None)
                    modified += 1
                    continue
                icf_ind = _resolve_icf_individual(icf_code)
                if icf_ind is None:
                    errors.append("add: ICF individual '" + icf_code + "' not found in ontology.")
                    continue
                hc_ind  = _get_or_create_hc()
                des_ind = des_class() if des_class is not None else Thing()
                involves_icf[des_ind] = [icf_ind]
                _safe_set_prop(q_prop,     des_ind, int(qualifier))
                _safe_set_prop(other_prop, des_ind, None)
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
    _refresh_reasoning_artifacts()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Mutation — Update isEvaluatedForJob links for a worker
# ═══════════════════════════════════════════════════════════════════════════════

# Lock for job-assignment mutations
_job_lock = threading.Lock()


def update_worker_jobs(worker_id: str, job_ids: list[str]) -> dict:
    """
    Atomically replace the set of isEvaluatedForJob triples for the given
    worker with the supplied list of job IDs.

    Steps
    ─────
    1. Look up the Person individual in the live owlready2 ontology.
    2. Resolve each requested job ID to an owlready2 individual.
    3. Replace eval_prop[person] with the resolved set.
    4. Save the ontology to disk, re-run Pellet, and refresh the snapshot cache.

    Returns
    ───────
    {
        "worker_id"  : str,
        "previous"   : [job_id, ...],   # the job IDs that were assigned before
        "assigned"   : [job_id, ...],   # the job IDs now assigned
        "unresolved" : [job_id, ...],   # requested IDs not found in ontology
    }
    """
    if not _live_reasoner_ready:
        raise RuntimeError(
            "The live ontology is still warming up in background. "
            "Job-assignment updates will be available as soon as the reasoner finishes."
        )

    person_ind = default_world.search_one(iri="*#" + worker_id)
    if person_ind is None:
        raise KeyError("Worker '" + worker_id + "' not found in ontology.")

    eval_prop: OWLProp = default_world.search_one(iri=IRI_IS_EVAL_JOB)
    if eval_prop is None:
        raise RuntimeError("isEvaluatedForJob property not found in ontology.")

    with _job_lock:
        # Capture current assignments
        previous = [local_name(j) for j in (eval_prop[person_ind] or [])]

        # Resolve requested job individuals
        resolved: list = []
        unresolved: list[str] = []
        for jid in job_ids:
            ind = default_world.search_one(iri="*#" + jid)
            if ind is not None:
                resolved.append(ind)
            else:
                unresolved.append(jid)

        # Apply the new assignment
        eval_prop[person_ind] = resolved

    assigned = [local_name(j) for j in resolved]

    _refresh_reasoning_artifacts()

    return {
        "worker_id" : worker_id,
        "previous"  : previous,
        "assigned"  : assigned,
        "unresolved": unresolved,
    }


def delete_worker(worker_id: str) -> dict:
    """
    Permanently delete a worker (Person individual) and all their associated
    data (HealthCondition, Descriptors) from the ontology.
    """
    if not _live_reasoner_ready:
        raise RuntimeError(
            "The live ontology is still warming up in background. "
            "Worker deletion will be available as soon as the reasoner finishes."
        )

    person_ind = default_world.search_one(iri="*#" + worker_id)
    if person_ind is None:
        raise KeyError(f"Worker '{worker_id}' not found in ontology.")

    is_in_hc_prop = default_world.search_one(iri=IRI_IS_IN_HC)
    is_described_by = default_world.search_one(iri=IRI_IS_DESCRIBED_BY)

    with _hc_lock, _job_lock:
        # Find and destroy associated HealthCondition and Descriptors
        if is_in_hc_prop is not None:
            hc_inds = list(is_in_hc_prop[person_ind] or [])
            for hc_ind in hc_inds:
                if is_described_by is not None:
                    des_inds = list(is_described_by[hc_ind] or [])
                    for des_ind in des_inds:
                        try:
                            owlready2.destroy_entity(des_ind)
                        except Exception:
                            pass
                try:
                    owlready2.destroy_entity(hc_ind)
                except Exception:
                    pass

        # Destroy the person individual itself
        try:
            owlready2.destroy_entity(person_ind)
        except Exception as exc:
            raise RuntimeError(f"Failed to destroy Person individual: {exc}") from exc

    _refresh_reasoning_artifacts()

    return {"worker_id": worker_id, "deleted": True}

