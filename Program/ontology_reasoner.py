"""
Ontologia Rientr@ (STIIMA-CNR) — Reasoner completo
====================================================
Implementa fedelmente la pipeline descritta in:
  Spoladore et al. (2024), "Towards a knowledge-based decision support
  system to foster the return to work of wheelchair users",
  Computational and Structural Biotechnology Journal, 24, 374-392.

PIPELINE COMPLETA
-----------------
PASSO 1 - Importanza (4 regole SWRL, par.3.2 + Table 2)
  hasScore <= 24             -> isLessImportantFor      (anchor 0)
  25 <= hasScore <= 49       -> isSomewhatImportantFor  (anchor 1)
  50 <= hasScore <= 74       -> isImportantFor          (anchor 2)
  hasScore >= 75             -> isVeryImportantFor      (anchor 3)

PASSO 2 - Criticita per Skill/Ability (8 regole SWRL, par.5.3.5)
  CS(skab) = qualifier x anchor
  qualifier = BFqual (Body Functions) o AP1qual (Activities & Participation)
  Soglie (Fig.2): CS>=7 extremely | >=5 relevantly | >=3 moderately | >=1 slightly | 0 not critical

PASSO 3 - GCS% e AISA% (par.5.2)
  GCS%  = mean(CS_i / 12) x 100    su tutte le Skill/Ability del job
  AISA% = (n. Skill/Ability con CS>0 / totale) x 100

PASSO 4 - Job Suitability (par.5.2, Fig.4)
  Confine rosso/giallo:   GCS% = -0.5 x AISA% + 21
  Confine giallo/verde:   GCS% = -0.5 x AISA% + 15.5
  GCS% > -0.5*AISA%+21              -> NOT SUITABLE        (rosso)
  -0.5*AISA%+15.5 <= GCS% <= +21    -> WITH PRECAUTIONS    (giallo)
  GCS% < -0.5*AISA%+15.5            -> SUITABLE            (verde)

PASSO 5 - Grafico GCS% vs AISA% con le tre aree (Fig.4 e Fig.9)

REQUISITI:
  pip install owlready2 matplotlib

Uso:
  python3 ontology_reasoner.py                # cerca .rdf nella cartella dello script
  python3 ontology_reasoner.py file.rdf       # percorso esplicito
"""

import sys
import os
import io
import re
import contextlib
import warnings
import logging
from collections import defaultdict

# -----------------------------------------------------------------------
# Import dipendenze opzionali
# -----------------------------------------------------------------------
try:
    import matplotlib
    # NON usare "Agg": con Agg il grafico viene solo salvato su file
    # e non viene mai mostrato a schermo. Rimuovendo questa riga
    # matplotlib usa il backend di default del sistema (TkAgg / Qt5Agg / ecc.)
    # che apre la finestra interattiva. Il salvataggio PNG funziona ugualmente.
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    import owlready2
    owlready2.set_log_level(0)
    from owlready2 import *
    HAS_OWLREADY = True
except ImportError:
    HAS_OWLREADY = False

try:
    from lxml import etree as ET
except ImportError:
    import xml.etree.ElementTree as ET

# -----------------------------------------------------------------------
# Utilita di percorso — compatibili Windows e Unix
# -----------------------------------------------------------------------

def _normalise_path(path: str) -> str:
    """Percorso assoluto normalizzato (gestisce backslash Windows)."""
    return os.path.normpath(os.path.abspath(path))


def _path_to_file_uri(path: str) -> str:
    """
    Converte un percorso di sistema in URI file:// corretto per owlready2.
      Windows  C:\\Users\\foo\\bar.rdf  ->  file:///C:/Users/foo/bar.rdf
      Unix     /home/foo/bar.rdf       ->  file:///home/foo/bar.rdf
    """
    abs_path = _normalise_path(path).replace("\\", "/")
    if len(abs_path) >= 2 and abs_path[1] == ":":
        # Drive letter Windows: C:/... -> file:///C:/...
        return "file:///" + abs_path
    # Unix: /home/... -> file:///home/...
    return "file://" + abs_path


def carica_ontologia(percorso: str) -> "owlready2.Ontology":
    """
    Carica l'ontologia dal percorso fornito (Windows o Unix).
    Costruisce l'URI file:// corretto per owlready2 in modo dinamico,
    senza alcun path hardcoded.
    """
    iri = _path_to_file_uri(percorso)
    print(f"[INFO] URI ontologia : {iri}")
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        onto = get_ontology("C:/Users/utente/OneDrive/Desktop/UNI/Tesi/python/Rientra_RDF-XML.rdf").load()   # FIX: usa iri dinamico, non path hardcoded
    print(f"[INFO] IRI base      : {onto.base_iri}")
    return onto


# -----------------------------------------------------------------------
# IRI / tag XML costanti (ricavati dall'analisi dell'ontologia)
# -----------------------------------------------------------------------
NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS_OWL = "http://www.w3.org/2002/07/owl#"

REQUIRES_TAG      = "{http://www.stiima.cnr.it/JobList#}requires"
CONCERNS_TAG      = "{http://www.stiima.cnr.it/JobList#}concerns"
HAS_SCORE_TAG     = "{http://www.stiima.cnr.it/JobList#}hasScore"
IS_TRANSLATED_TAG = "{http://www.stiima.cnr.it/SkAb#}isTranslatedWithICFCode"
IS_IN_HC_TAG      = "{http://www.stiima.cnr.it/RientraHC#}isInHealthCondition"
IS_DESC_TAG       = "{http://www.stiima.cnr.it/RientraHC#}isDescribedBy"
INV_ICF_TAG       = "{http://www.stiima.cnr.it/RientraHC#}involvesICFCode"
BFQUAL_TAG        = "{http://www.stiima.cnr.it/RientraHC#}BFqual"
AP1QUAL_TAG       = "{http://www.stiima.cnr.it/RientraHC#}AP1qual"
IS_SELECTED_TAG   = "{http://www.stiima.cnr.it/RientraOnt3Merged#}isSelected"
IS_EVAL_JOB_TAG   = "{http://www.stiima.cnr.it/RientraOnt3#}isEvaluatedForJob"

IMPORTANCE_IRIS = {
    "isLessImportantFor"    : "http://www.stiima.cnr.it/JobDescription#isLessImportantFor",
    "isSomewhatImportantFor": "http://www.stiima.cnr.it/JobDescription#isSomewhatImportantFor",
    "isImportantFor"        : "http://www.stiima.cnr.it/JobDescription#isImportantFor",
    "isVeryImportantFor"    : "http://www.stiima.cnr.it/JobDescription#isVeryImportantFor",
}

ANCHOR_MAP = {
    "isLessImportantFor"    : 0,
    "isSomewhatImportantFor": 1,
    "isImportantFor"        : 2,
    "isVeryImportantFor"    : 3,
}

LABEL_ORDER = [
    "isVeryImportantFor",
    "isImportantFor",
    "isSomewhatImportantFor",
    "isLessImportantFor",
]

# Parametri linee Job Suitability (Fig.4 del paper)
JS_RED_INTERCEPT    = 21.0     # y = -0.5x + 21
JS_YELLOW_INTERCEPT = 15.5     # y = -0.5x + 15.5
JS_SLOPE            = -0.5

# -----------------------------------------------------------------------
# Utilita
# -----------------------------------------------------------------------

def local_name(iri: str) -> str:
    return iri.split("#")[-1] if "#" in iri else iri.split("/")[-1]


def importance_label(score: int) -> str:
    """Regole SWRL 9-12: score O*NET -> etichetta importanza."""
    if   score <= 24: return "isLessImportantFor"
    elif score <= 49: return "isSomewhatImportantFor"
    elif score <= 74: return "isImportantFor"
    else:             return "isVeryImportantFor"


def criticality_label(cs: int) -> str:
    """Soglie matrice Fig.2 del paper."""
    if   cs >= 7: return "EXTREMELY CRITICAL"
    elif cs >= 5: return "RELEVANTLY CRITICAL"
    elif cs >= 3: return "MODERATELY CRITICAL"
    elif cs >= 1: return "SLIGHTLY CRITICAL"
    else:         return "not critical"


def job_suitability(gcs_pct: float, aisa_pct: float) -> tuple:
    """
    Classifica il job (Fig.4 del paper).
    Restituisce (etichetta, colore_matplotlib).
    """
    thr_red    = JS_SLOPE * aisa_pct + JS_RED_INTERCEPT
    thr_yellow = JS_SLOPE * aisa_pct + JS_YELLOW_INTERCEPT
    if gcs_pct > thr_red:
        return "NOT SUITABLE", "red"
    elif gcs_pct >= thr_yellow:
        return "SUITABLE WITH PRECAUTIONS", "orange"
    else:
        return "SUITABLE", "green"


# -----------------------------------------------------------------------
# Parser RDF/XML diretto (non richiede owlready2)
# -----------------------------------------------------------------------

def parse_ontology(path: str) -> dict:
    """
    Legge il file RDF/XML e restituisce
      { iri: { tag_property: [value, ...] } }
    per tutti gli owl:NamedIndividual.
    ERRORE se il file non e leggibile o non contiene individui.
    """
    print(f"[INFO] Parsing RDF/XML: {path}")
    try:
        tree = ET.parse(path)
    except Exception as e:
        raise RuntimeError(f"[ERRORE] Impossibile leggere il file: {e}")

    root = tree.getroot()
    RDF_ABOUT = f"{{{NS_RDF}}}about"
    RDF_RES   = f"{{{NS_RDF}}}resource"
    OWL_IND   = f"{{{NS_OWL}}}NamedIndividual"

    individuals = {}
    for el in root.findall(OWL_IND):
        iri = el.get(RDF_ABOUT)
        if not iri:
            continue
        props = {}
        for child in el:
            val = child.get(RDF_RES) or (child.text.strip() if child.text else None)
            if val:
                props.setdefault(child.tag, []).append(val)
        individuals[iri] = props

    if not individuals:
        raise RuntimeError(
            "[ERRORE] Nessun owl:NamedIndividual trovato. "
            "Verificare che il file sia un OWL/RDF valido."
        )

    print(f"[INFO] {len(individuals)} individui caricati.")
    return individuals


# -----------------------------------------------------------------------
# Parser da oggetto owlready2 in memoria (usato dopo Pellet)
# Non usa rdflib — legge il quadstore interno di owlready2 direttamente.
# -----------------------------------------------------------------------

_TAG_TO_PROP_IRI = {
    REQUIRES_TAG      : "http://www.stiima.cnr.it/JobList#requires",
    CONCERNS_TAG      : "http://www.stiima.cnr.it/JobList#concerns",
    HAS_SCORE_TAG     : "http://www.stiima.cnr.it/JobList#hasScore",
    IS_TRANSLATED_TAG : "http://www.stiima.cnr.it/SkAb#isTranslatedWithICFCode",
    IS_IN_HC_TAG      : "http://www.stiima.cnr.it/RientraHC#isInHealthCondition",
    IS_DESC_TAG       : "http://www.stiima.cnr.it/RientraHC#isDescribedBy",
    INV_ICF_TAG       : "http://www.stiima.cnr.it/RientraHC#involvesICFCode",
    BFQUAL_TAG        : "http://www.stiima.cnr.it/RientraHC#BFqual",
    AP1QUAL_TAG       : "http://www.stiima.cnr.it/RientraHC#AP1qual",
    IS_SELECTED_TAG   : "http://www.stiima.cnr.it/RientraOnt3Merged#isSelected",
    IS_EVAL_JOB_TAG   : "http://www.stiima.cnr.it/RientraOnt3#isEvaluatedForJob",
}


def parse_ontology_from_owlready(onto) -> dict:
    """
    Costruisce il dizionario { iri: {tag: [val,...]} } leggendo direttamente
    dal quadstore interno di owlready2 (world.graph) dopo sync_reasoner_pellet.
    Non richiede rdflib — usa solo owlready2 nativo.
    Cattura sia le triple esplicite che quelle inferite dal Pellet.
    """
    world = onto.world
    individuals = {}

    for tag, prop_iri in _TAG_TO_PROP_IRI.items():
        # storid = identificatore numerico interno di owlready2 per l'IRI
        prop_storid = world._abbreviate(prop_iri, create_if_missing=False)
        if prop_storid is None:
            continue  # proprietà non presente nell'ontologia

        # Itera su tutte le triple (sogg, prop, obj) nel quadstore
        for subj_storid, obj_storid in world.graph.SPO_search(
                None, prop_storid, None):
            subj_iri = world._unabbreviate(subj_storid)
            if subj_iri is None:
                continue

            # obj può essere un IRI (intero storid) o una literal (stringa)
            if isinstance(obj_storid, int):
                val_str = world._unabbreviate(obj_storid)
            else:
                # literal: owlready2 le rappresenta come stringe o tuple (val, lang/type)
                val_str = str(obj_storid[0] if isinstance(obj_storid, tuple) else obj_storid)

            if not val_str:
                continue

            if subj_iri not in individuals:
                individuals[subj_iri] = {}
            lst = individuals[subj_iri].setdefault(tag, [])
            if val_str not in lst:
                lst.append(val_str)

    if not individuals:
        raise RuntimeError(
            "[ERRORE] Nessun individuo estratto dall'ontologia inferred. "
            "Verificare che il file sia un OWL/RDF valido."
        )

    print(f"[INFO] {len(individuals)} individui estratti dall'ontologia inferred.")
    return individuals


# -----------------------------------------------------------------------
# PASSO 1 - Mappa importanza: (skab_iri, job_iri) -> (label, score, anchor)
# -----------------------------------------------------------------------

def build_importance_map(inds: dict) -> dict:
    """
    Implementa le 4 regole SWRL di importanza (regole 9-12):
      Per ogni Job_Descriptor con hasScore:
        - calcola l'etichetta di importanza
        - mappa (skab_iri, job_iri) -> (label, score, anchor)

    ERRORE se nessun Job_Descriptor ha hasScore o nessuna coppia e costruibile.
    """
    # Indice inverso: jde_iri -> [job_iri, ...]
    jde_to_jobs = defaultdict(list)
    for iri, props in inds.items():
        for jde_iri in props.get(REQUIRES_TAG, []):
            jde_to_jobs[jde_iri].append(iri)

    importance = {}   # (skab_iri, job_iri) -> (label, score, anchor)
    n_jde = 0

    for iri, props in inds.items():
        scores = props.get(HAS_SCORE_TAG)
        if not scores:
            continue
        n_jde += 1
        score  = int(scores[0])
        label  = importance_label(score)
        anchor = ANCHOR_MAP[label]

        for skab_iri in props.get(CONCERNS_TAG, []):
            for job_iri in jde_to_jobs.get(iri, []):
                key = (skab_iri, job_iri)
                if key not in importance or score > importance[key][1]:
                    importance[key] = (label, score, anchor)

    if n_jde == 0:
        raise RuntimeError(
            "[ERRORE] Nessun Job_Descriptor con hasScore trovato. "
            "Verificare l'ontologia."
        )
    if not importance:
        raise RuntimeError(
            "[ERRORE] Nessuna coppia (Skill/Ability, Job) costruita. "
            "Verificare le proprieta concerns e requires nell'ontologia."
        )

    print(f"[INFO] Importanza: {n_jde} Job_Descriptor, "
          f"{len(importance)} coppie (SkAb, Job) calcolate.")
    return importance


# -----------------------------------------------------------------------
# PASSO 2 - Mappa ICF -> qualifier per una persona
# -----------------------------------------------------------------------

def build_icf_qualifier_map(person_iri: str, inds: dict) -> dict:
    """
    Costruisce ICF_code_iri -> max_qualifier per una persona.
    Considera sia BFqual (Body Functions) che AP1qual (Activities & Participation).
    ERRORE se la catena isInHealthCondition e assente o non produce qualifier.
    """
    person_props = inds.get(person_iri, {})
    hc_iris = person_props.get(IS_IN_HC_TAG, [])
    if not hc_iris:
        raise RuntimeError(
            f"[ERRORE] {local_name(person_iri)}: isInHealthCondition mancante. "
            "Impossibile calcolare le criticita."
        )

    icf_to_qual = {}
    for hc_iri in hc_iris:
        hc_props = inds.get(hc_iri, {})
        for des_iri in hc_props.get(IS_DESC_TAG, []):
            des = inds.get(des_iri, {})
            icf_codes = des.get(INV_ICF_TAG, [])
            if not icf_codes:
                continue
            # BFqual per Body Functions, AP1qual per Activities & Participation
            bf  = des.get(BFQUAL_TAG,  [None])[0]
            ap1 = des.get(AP1QUAL_TAG, [None])[0]
            qual_raw = bf if bf is not None else ap1
            if qual_raw is None:
                continue
            qual = int(qual_raw)
            for icf_iri in icf_codes:
                icf_to_qual[icf_iri] = max(icf_to_qual.get(icf_iri, 0), qual)

    if not icf_to_qual:
        raise RuntimeError(
            f"[ERRORE] {local_name(person_iri)}: nessun codice ICF con qualifier "
            "trovato nella Health Condition. Verificare i HC_Descriptor."
        )

    n_nonzero = sum(1 for q in icf_to_qual.values() if q > 0)
    print(f"  [INFO] {local_name(person_iri)}: {len(icf_to_qual)} codici ICF, "
          f"{n_nonzero} con qualifier>0.")
    return icf_to_qual


# -----------------------------------------------------------------------
# PASSI 2-3-4 - CS, GCS%, AISA%, Suitability per un (Person, Job)
# -----------------------------------------------------------------------

def compute_job_metrics(job_iri: str, inds: dict, importance_map: dict,
                        icf_to_qual: dict) -> dict:
    """
    Implementa i passi 2-3-4 del paper per una coppia (Person, Job):

    Passo 2 (regole SWRL 1-8):
      CS_i = qualifier_i x anchor_i
      per ogni Skill/Ability del job il cui codice ICF e presente
      nella Health Condition della persona.

    Passo 3:
      GCS%  = mean(CS_i / 12) x 100
      AISA% = (n CS_i>0 / n totale) x 100

    Passo 4:
      Job Suitability tramite le linee di separazione del paper (Fig.4)

    ERRORE se il job non ha Job_Descriptor o nessuna Skill/Ability ha score.
    """
    job_props = inds.get(job_iri, {})
    jdes = job_props.get(REQUIRES_TAG, [])
    if not jdes:
        raise RuntimeError(
            f"[ERRORE] Job '{local_name(job_iri)}': nessun Job_Descriptor (requires). "
            "Verificare l'ontologia."
        )

    skill_rows = []

    for jde_iri in jdes:
        jde = inds.get(jde_iri, {})
        score_raw = jde.get(HAS_SCORE_TAG, [None])[0]
        if score_raw is None:
            continue
        score = int(score_raw)

        for skab_iri in jde.get(CONCERNS_TAG, []):
            # Recupera label/anchor dalla mappa pre-calcolata
            imp = importance_map.get((skab_iri, job_iri))
            if imp is not None:
                label, score, anchor = imp
            else:
                label  = importance_label(score)
                anchor = ANCHOR_MAP[label]

            # Cerca il qualifier massimo tra i codici ICF della Skill/Ability
            skab_props  = inds.get(skab_iri, {})
            icf_iris    = skab_props.get(IS_TRANSLATED_TAG, [])

            max_qual    = 0
            matched_icf = None
            for icf_iri in icf_iris:
                q = icf_to_qual.get(icf_iri, 0)
                if q > max_qual:
                    max_qual    = q
                    matched_icf = icf_iri

            cs   = max_qual * anchor      # hasSpecificCriticality
            norm = cs / 12.0              # normalizzato su max possibile (4x3=12)

            skill_rows.append({
                "skab_name"  : local_name(skab_iri),
                "score"      : score,
                "label"      : label,
                "anchor"     : anchor,
                "qualifier"  : max_qual,
                "matched_icf": local_name(matched_icf) if matched_icf else None,
                "cs"         : cs,
                "norm"       : norm,
            })

    if not skill_rows:
        raise RuntimeError(
            f"[ERRORE] Job '{local_name(job_iri)}': nessuna Skill/Ability con score. "
            "Verificare l'ontologia."
        )

    n_total    = len(skill_rows)
    n_critical = sum(1 for s in skill_rows if s["cs"] > 0)
    sum_norm   = sum(s["norm"] for s in skill_rows)
    gcs_pct    = (sum_norm / n_total) * 100.0
    aisa_pct   = (n_critical / n_total) * 100.0
    suitability, color = job_suitability(gcs_pct, aisa_pct)

    return {
        "job_name"   : local_name(job_iri),
        "skills"     : skill_rows,
        "n_total"    : n_total,
        "n_critical" : n_critical,
        "gcs_pct"    : gcs_pct,
        "aisa_pct"   : aisa_pct,
        "suitability": suitability,
        "color"      : color,
    }


def analyze_person(person_iri: str, inds: dict, importance_map: dict) -> dict:
    """
    Esegue la pipeline completa per una persona:
    costruisce la mappa ICF->qualifier e calcola le metriche per TUTTI
    i job presenti nell'ontologia (ricavati dalla importance_map),
    indipendentemente da isEvaluatedForJob.
    """
    p_name = local_name(person_iri)

    # Tutti i job presenti nell'ontologia, ricavati dalla importance_map
    job_iris = sorted({job_iri for (_, job_iri) in importance_map.keys()})

    if not job_iris:
        raise RuntimeError(
            f"[ERRORE] {p_name}: nessun job trovato nell'ontologia (importance_map vuota)."
        )

    icf_to_qual = build_icf_qualifier_map(person_iri, inds)
    print(f"  [INFO] {p_name}: {len(job_iris)} job da valutare (tutti i job dell'ontologia).")

    job_results = []
    for job_iri in job_iris:
        try:
            m = compute_job_metrics(job_iri, inds, importance_map, icf_to_qual)
            job_results.append(m)
        except RuntimeError as e:
            print(f"  [WARN] {e}")

    if not job_results:
        raise RuntimeError(
            f"[ERRORE] {p_name}: nessun risultato calcolato per i job assegnati."
        )

    return {
        "person_name": p_name,
        "person_iri" : person_iri,
        "icf_map"    : icf_to_qual,
        "jobs"       : job_results,
    }


# -----------------------------------------------------------------------
# Stampa risultati
# -----------------------------------------------------------------------

def print_importance_summary(importance_map: dict):
    # Raggruppa per job
    job_to_skabs = defaultdict(list)
    for (skab_iri, job_iri), (label, score, anchor) in importance_map.items():
        job_to_skabs[local_name(job_iri)].append((local_name(skab_iri), label, score))

    print(f"\n{'='*72}")
    print(f"  IMPORTANZA Skill/Ability per Job  ({len(importance_map)} coppie totali)")
    print(f"  Regole 9-12: score<=24->Less | 25-49->Somewhat | 50-74->Important | >=75->Very")
    print(f"{'='*72}")
    for job_name in sorted(job_to_skabs):
        entries = job_to_skabs[job_name]
        by_label = defaultdict(list)
        for skab_name, label, score in entries:
            by_label[label].append((skab_name, score))
        print(f"\n  > {job_name}  ({len(entries)} Skill/Ability)")
        for lbl in LABEL_ORDER:
            items = sorted(by_label.get(lbl, []), key=lambda x: -x[1])
            if items:
                names = ", ".join(f"{n}({s})" for n, s in items)
                print(f"    {lbl:<32} -> {names}")


def print_job_metrics(person_result: dict):
    p_name = person_result["person_name"]

    print(f"\n{'='*72}")
    print(f"  RISULTATI — Persona: {p_name}")
    print(f"  GCS%  = mean(CS_i/12)*100   dove CS_i = qualifier * anchor (0/1/2/3)")
    print(f"  AISA% = (n SkAb con CS>0 / n totale) * 100")
    print(f"{'='*72}")

    # Tabella riepilogativa
    print(f"\n  {'Job':<42} {'GCS%':>7} {'AISA%':>7}  Suitability")
    print(f"  {'-'*42} {'-'*7} {'-'*7}  {'-'*26}")
    for m in person_result["jobs"]:
        emoji_map = {
            "SUITABLE"                  : "[OK]",
            "SUITABLE WITH PRECAUTIONS" : "[!] ",
            "NOT SUITABLE"              : "[X] ",
        }
        e = emoji_map.get(m["suitability"], "    ")
        print(f"  {m['job_name']:<42} {m['gcs_pct']:>6.2f}% {m['aisa_pct']:>6.2f}%"
              f"  {e} {m['suitability']}")

    # Dettaglio per ogni job
    for m in person_result["jobs"]:
        print(f"\n  {'─'*68}")
        print(f"  JOB: {m['job_name']}")
        print(f"  GCS%={m['gcs_pct']:.4f}%  AISA%={m['aisa_pct']:.4f}%  "
              f"-> {m['suitability']}")
        print(f"  SkAb totali: {m['n_total']}  |  con CS>0: {m['n_critical']}")

        sorted_skills = sorted(m["skills"], key=lambda x: (-x["cs"], x["skab_name"]))
        print(f"\n  {'Skill/Ability':<35} {'Sc':>4} {'An':>2} {'Qu':>2} "
              f"{'CS':>2} {'Norm':>7}  Criticita              ICF collegato")
        print(f"  {'-'*35} {'-'*4} {'-'*2} {'-'*2} "
              f"{'-'*2} {'-'*7}  {'-'*22}  {'-'*20}")
        for s in sorted_skills:
            icf_str = s["matched_icf"] or "-"
            print(f"  {s['skab_name']:<35} {s['score']:>4} {s['anchor']:>2} "
                  f"{s['qualifier']:>2} {s['cs']:>2} {s['norm']:>7.4f}  "
                  f"{criticality_label(s['cs']):<22}  {icf_str}")


# -----------------------------------------------------------------------
# PASSO 5 - Grafico GCS% vs AISA% (Fig.4 del paper)
# -----------------------------------------------------------------------

def plot_job_suitability(person_results: list, output_path: str):
    """
    Produce il grafico GCS% vs AISA% con le tre aree (Fig.4 del paper).
    Ogni job e un punto colorato in base alla suitability.
    Salva su file PNG.
    """
    if not HAS_MATPLOTLIB:
        print("[WARN] matplotlib non disponibile. Installare con: pip install matplotlib")
        return

    fig, ax = plt.subplots(figsize=(11, 7))

    # --- Sfondo con le tre aree -------------------------------------------
    x_arr = [0, 55]
    y_red    = [JS_SLOPE * x + JS_RED_INTERCEPT    for x in x_arr]
    y_yellow = [JS_SLOPE * x + JS_YELLOW_INTERCEPT for x in x_arr]

    ax.fill_between(x_arr, y_red,    [26, 26],   color="#ffcccc", alpha=0.55,
                    label="_red_area")
    ax.fill_between(x_arr, y_yellow, y_red,       color="#fff3cc", alpha=0.60,
                    label="_yellow_area")
    ax.fill_between(x_arr, [0, 0],   y_yellow,    color="#ccffcc", alpha=0.55,
                    label="_green_area")

    ax.plot(x_arr, y_red,    color="red",    linestyle="--", linewidth=1.2,
            label="GCS = -0.5*AISA + 21  (confine rosso/giallo)")
    ax.plot(x_arr, y_yellow, color="darkorange", linestyle="--", linewidth=1.2,
            label="GCS = -0.5*AISA + 15.5 (confine giallo/verde)")

    # --- Punti dei job -------------------------------------------------------
    color_map = {
        "SUITABLE"                  : "darkgreen",
        "SUITABLE WITH PRECAUTIONS" : "darkorange",
        "NOT SUITABLE"              : "darkred",
    }
    markers = ["o", "s", "^", "D", "v", "P", "X", "*", "h", "p"]

    for p_idx, pr in enumerate(person_results):
        for j_idx, m in enumerate(pr["jobs"]):
            mk  = markers[(p_idx * 10 + j_idx) % len(markers)]
            col = color_map.get(m["suitability"], "gray")
            ax.scatter(
                m["aisa_pct"], m["gcs_pct"],
                c=col, marker=mk, s=130, zorder=5,
                edgecolors="black", linewidths=0.6,
            )
            job_label = m["job_name"].replace("_", " ")
            # Offset testo per evitare sovrapposizioni
            ax.annotate(
                f"{job_label}\n({m['gcs_pct']:.2f}%, {m['aisa_pct']:.2f}%)",
                (m["aisa_pct"], m["gcs_pct"]),
                textcoords="offset points", xytext=(7, 5),
                fontsize=7.5, color="black",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.6, lw=0),
            )

    # --- Legenda area ---------------------------------------------------------
    patch_g = mpatches.Patch(color="#ccffcc", alpha=0.8,
                             label="Suitable")
    patch_y = mpatches.Patch(color="#fff3cc", alpha=0.8,
                             label="Suitable with precautions")
    patch_r = mpatches.Patch(color="#ffcccc", alpha=0.8,
                             label="Not suitable")
    line_handles, line_labels = ax.get_legend_handles_labels()
    ax.legend(
        handles=[patch_g, patch_y, patch_r] + line_handles,
        loc="upper right", fontsize=8, framealpha=0.9,
    )

    # --- Assi e titolo -------------------------------------------------------
    ax.set_xlabel("AISA%  —  Amount of Impaired Skills and Abilities (%)", fontsize=11)
    ax.set_ylabel("GCS%  —  General Criticality Score (%)", fontsize=11)
    persons_str = " | ".join(r["person_name"] for r in person_results)
    ax.set_title(
        f"Job Suitability — {persons_str}\n"
        f"(Rientr@ DSS — Spoladore et al. 2024)",
        fontsize=12,
    )
    ax.set_xlim(0, 55)
    ax.set_ylim(0, 25)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"[OK]  Grafico salvato: {output_path}")
    plt.show()   # FIX: mostra la finestra interattiva (richiede backend GUI)
    plt.close()


# -----------------------------------------------------------------------
# Reasoning Pellet (opzionale, richiede owlready2 + Java)
# -----------------------------------------------------------------------

def run_pellet_reasoning(onto) -> bool:
    if not HAS_OWLREADY:
        print("[INFO] owlready2 non disponibile, Pellet saltato.")
        return False

    reparent_errors = []
    print("\n[INFO] Avvio Pellet...")
    ThingMetaClass = type(Thing)
    orig_sa = ThingMetaClass.__setattr__

    def patched_sa(self, name, value):
        if name == "__bases__":
            try: orig_sa(self, name, value)
            except TypeError as e:
                if "inheritance cycle" in str(e): reparent_errors.append(1)
                else: raise
        else:
            orig_sa(self, name, value)

    try:
        ThingMetaClass.__setattr__ = patched_sa
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            with onto:
                sync_reasoner_pellet(
                    infer_property_values=True,
                    infer_data_property_values=True,
                )
        for line in buf.getvalue().split("\n"):
            if "Pellet took" in line:
                match = re.search(r"Pellet took ([\d.]+)", line)
                if match:
                    print(f"[OK]  Pellet completato in {float(match.group(1)):.1f}s")
                break
        if reparent_errors:
            print(f"      ({len(reparent_errors)} cicli ICF ignorati)")
        return True
    except Exception as e:
        print(f"[ERRORE] Pellet: {e}")
        return False
    finally:
        ThingMetaClass.__setattr__ = orig_sa


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------

def main():
    # Trova il file ontologia
    if len(sys.argv) > 1:
        percorso = sys.argv[1]
    else:
        cartella = os.path.dirname(os.path.abspath(__file__))
        candidati = sorted(
            f for f in os.listdir(cartella)
            if f.lower().endswith((".rdf", ".owl", ".ttl", ".n3"))
        )
        if not candidati:
            print("[ERRORE] Nessun file .rdf/.owl trovato nella cartella.")
            sys.exit(1)
        percorso = os.path.join(cartella, candidati[0])
        print(f"[INFO] File: {candidati[0]}")

    # === Parsing iniziale dal file originale ================================
    # Necessario per il Passo 1 (importance_map), prerequisito delle regole
    # SWRL che Pellet usa per inferire isSelected=true.
    try:
        inds = parse_ontology(percorso)
    except RuntimeError as e:
        print(e); sys.exit(1)

    # === PASSO 1 — Importanza ==============================================
    # Calcolato PRIMA del Pellet: le regole SWRL di isSelected dipendono
    # dall'importance map già presente nell'ontologia.
    print("\n[INFO] PASSO 1 — Calcolo importanza (regole SWRL 9-12)...")
    try:
        importance_map = build_importance_map(inds)
    except RuntimeError as e:
        print(e); sys.exit(1)

    print_importance_summary(importance_map)

    # === Pellet: eseguito DOPO il Passo 1 ==================================
    # Ora Pellet può inferire isSelected=true sulle persone.
    # I dati vengono letti direttamente dal quadstore owlready2 in memoria
    # (no file temp, no rdflib).
    if HAS_OWLREADY:
        print("\n[INFO] PASSO 1b — Pellet reasoning (inferisce isSelected e proprietà SWRL)...")
        try:
            onto = carica_ontologia(percorso)
            pellet_ok = run_pellet_reasoning(onto)
            if pellet_ok:
                print("[INFO] Ontologia inferred pronta in memoria.")
                inds = parse_ontology_from_owlready(onto)
                try:
                    importance_map = build_importance_map(inds)
                except RuntimeError:
                    pass  # mantieni quella già calcolata
            else:
                print("[WARN] Pellet non completato: continuo con ontologia originale.")
        except Exception as e:
            print(f"[WARN] Pellet non eseguito: {e}")
            print("[WARN] Continuo con l'ontologia originale (senza inferenze).")
    else:
        print("\n[INFO] owlready2 non installato, Pellet saltato.")
        print("       Per abilitare: pip install owlready2")

    # === PASSI 2-3-4 — Criticita, GCS%, AISA%, Suitability ================
    print(f"\n[INFO] PASSI 2-3-4 — Criticita per Skill/Ability, GCS%, AISA%, "
          "Job Suitability...")

    # Cerca persone con isSelected=true (inferito da Pellet)
    persons_selected = [
        iri for iri, props in inds.items()
        if "true" in props.get(IS_SELECTED_TAG, [])
    ]

    if not persons_selected:
        print(
            "[ERRORE] Nessun individuo con isSelected=true trovato.\n"
            "         Le regole di criticita richiedono almeno un Person con\n"
            "         isSelected=true e isEvaluatedForJob valorizzato.\n"
            "         Verificare l'ontologia."
        )
        sys.exit(1)

    print(f"[INFO] {len(persons_selected)} persona/e con isSelected=true.")

    all_results = []
    for p_iri in persons_selected:
        print(f"\n[INFO] Elaborazione: {local_name(p_iri)}")
        try:
            result = analyze_person(p_iri, inds, importance_map)
            all_results.append(result)
            print_job_metrics(result)
        except RuntimeError as e:
            print(e)

    if not all_results:
        print("[ERRORE] Nessun risultato calcolato per nessuna persona.")
        sys.exit(1)

    # === PASSO 5 — Grafico =================================================
    print(f"\n[INFO] PASSO 5 — Generazione grafico GCS% vs AISA%...")
    grafico_path = os.path.join(
        os.path.dirname(os.path.abspath(percorso)),
        "job_suitability.png"
    )
    plot_job_suitability(all_results, output_path=grafico_path)

    print("\n[FINE]\n")


if __name__ == "__main__":
    main()