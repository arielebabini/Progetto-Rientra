"""
===========================================================================

PIPELINE CORRETTA DEL PAPER
----------------------------

  FASE 1  Caricamento ontologia via owlready2
          get_ontology(...).load()

  FASE 2  Reasoning con Pellet (DL reasoner reale)
          sync_reasoner_pellet(
              infer_property_values=True,
              infer_data_property_values=True
          )
          Pellet legge le 13 regole SWRL nell'ontologia e inferisce:
            R9-R12  → is*ImportantFor(skab, job)
            R1-R8   → hasSpecificCriticality(skab, cs_value)
            R13     → matchedJob(person, job)
          Le triple inferite sono scritte nel default_world di owlready2.

  FASE 3  Query SPARQL sul world arricchito da Pellet
          default_world.sparql("SELECT ...")
          Q1  GCS%  = AVG(cs/12)*100  per (Person, Job)
          Q2  AISA% = COUNT(cs>0)/COUNT(*)*100  per (Person, Job)
          Q3  Dettaglio Skill/Ability per (Person, Job)
          Q4  Riepilogo is*ImportantFor per Job

  FASE 4  Job Suitability (Fig. 4 del paper)
          GCS > -0.5*AISA + 21      → NOT SUITABLE
          GCS >= -0.5*AISA + 15.5   → WITH PRECAUTIONS
          GCS < -0.5*AISA + 15.5    → SUITABLE

  FASE 5  Grafico GCS% vs AISA% (Fig. 4 / Fig. 9 del paper)

REQUISITI:
  pip install owlready2 matplotlib rich
  Java 11+ nel PATH (owlready2 usa Pellet come subprocess Java)

Uso:
  python3 ontology_reasoner_pellet.py                # cerca .rdf nella cartella
  python3 ontology_reasoner_pellet.py file.rdf       # percorso esplicito
"""

import sys
import os
import re
import io
import contextlib
import warnings
import logging
from collections import defaultdict

# ── owlready2 (obbligatorio) ──────────────────────────────────────────────────
try:
    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    import owlready2
    owlready2.set_log_level(0)
    from owlready2 import *
except ImportError:
    print(
        "[ERRORE] owlready2 non installato.\n"
        "         Installare con: pip install owlready2\n"
        "         Richiede anche Java 11+ nel PATH per Pellet."
    )
    sys.exit(1)

# ── matplotlib (opzionale) ────────────────────────────────────────────────────
try:
    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.gridspec as gridspec
    from matplotlib.colors import to_rgba
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("[WARN] matplotlib non installato: grafici non disponibili.")
    print("       Installare con: pip install matplotlib")

# ── Rich (opzionale, per la dashboard terminale) ──────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.text import Text
    from rich.rule import Rule
    from rich.progress_bar import ProgressBar
    from rich import box
    HAS_RICH = True
    _console = Console()
except ImportError:
    HAS_RICH = False
    _console = None
    print("[WARN] rich non installato: dashboard terminale non disponibile.")
    print("       Installare con: pip install rich")

# ═══════════════════════════════════════════════════════════════════════════════
#  IRI costanti dell'ontologia Rientr@
#  (verificati analizzando il file RDF/XML dell'ontologia)
# ═══════════════════════════════════════════════════════════════════════════════

# Proprietà inferite da Pellet tramite le regole SWRL 9-12
IRI_IS_VERY_IMP = "http://www.stiima.cnr.it/JobDescription#isVeryImportantFor"
IRI_IS_IMP      = "http://www.stiima.cnr.it/JobDescription#isImportantFor"
IRI_IS_SOMEWHAT = "http://www.stiima.cnr.it/JobDescription#isSomewhatImportantFor"
IRI_IS_LESS     = "http://www.stiima.cnr.it/JobDescription#isLessImportantFor"

# Proprietà inferita da Pellet tramite le regole SWRL 1-8
IRI_HAS_CRIT    = "http://www.stiima.cnr.it/RientraOnt3#hasSpecificCriticality"

# Proprietà dell'ontologia usate nelle query SPARQL
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

# Soglie Job Suitability (Fig. 4 del paper)
JS_RED_INTERCEPT    = 21.0     # GCS = -0.5*AISA + 21
JS_YELLOW_INTERCEPT = 15.5     # GCS = -0.5*AISA + 15.5
JS_SLOPE            = -0.5

LABEL_ORDER = [
    "isVeryImportantFor",
    "isImportantFor",
    "isSomewhatImportantFor",
    "isLessImportantFor",
]


# ═══════════════════════════════════════════════════════════════════════════════
#  Utilità
# ═══════════════════════════════════════════════════════════════════════════════

def local_name(entity) -> str:
    if hasattr(entity, "name"):
        return entity.name
    s = str(entity)
    return s.split("#")[-1] if "#" in s else s.split("/")[-1]


def criticality_label(cs: int) -> str:
    """Soglie della matrice Fig. 2 del paper."""
    if   cs >= 7: return "EXTREMELY CRITICAL"
    elif cs >= 5: return "RELEVANTLY CRITICAL"
    elif cs >= 3: return "MODERATELY CRITICAL"
    elif cs >= 1: return "SLIGHTLY CRITICAL"
    else:         return "not critical"


def job_suitability(gcs: float, aisa: float) -> tuple:
    """Classifica il job (Fig. 4 del paper)."""
    thr_red    = JS_SLOPE * aisa + JS_RED_INTERCEPT
    thr_yellow = JS_SLOPE * aisa + JS_YELLOW_INTERCEPT
    if gcs > thr_red:
        return "NOT SUITABLE", "darkred"
    elif gcs >= thr_yellow:
        return "SUITABLE WITH PRECAUTIONS", "darkorange"
    else:
        return "SUITABLE", "darkgreen"


def sparql(query_str: str) -> list:
    """
    Esegue una query SPARQL sul default_world di owlready2
    (che dopo Pellet contiene anche le triple inferite).
    """
    return list(default_world.sparql(query_str))


# ═══════════════════════════════════════════════════════════════════════════════
#  FASE 1 — Caricamento ontologia via owlready2
# ═══════════════════════════════════════════════════════════════════════════════

def load_ontology(path: str) -> "Ontology":
    """
    Carica l'ontologia nel default_world di owlready2.
    ERRORE se il file non è leggibile o l'IRI non è valido.
    """
    abs_path = os.path.abspath(path)
    iri = f"file://{abs_path}"
    print(f"[FASE 1] Caricamento ontologia: {iri}")

    # Sopprime i warning di owlready2 (cicli di ereditarietà ICF)
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        try:
            onto = get_ontology(iri).load()
        except Exception as e:
            raise RuntimeError(
                f"[ERRORE] Impossibile caricare l'ontologia: {e}\n"
                f"         Percorso: {abs_path}"
            )

    n_cls = len(list(default_world.classes()))
    n_ind = len(list(default_world.individuals()))
    n_prp = len(list(default_world.properties()))
    print(f"[FASE 1] {n_cls} classi | {n_ind} individui | {n_prp} proprietà")
    return onto


# ═══════════════════════════════════════════════════════════════════════════════
#  FASE 2 — Reasoning con Pellet
# ═══════════════════════════════════════════════════════════════════════════════

def run_pellet(onto: "Ontology") -> None:
    """
    Esegue Pellet tramite owlready2.

    Pellet legge le 13 regole SWRL nell'ontologia e inferisce nel world:
      R9-R12  is*ImportantFor(skab, job)           ← 4 regole importanza
      R1-R8   hasSpecificCriticality(skab, value)  ← 8 regole criticità
      R13     matchedJob(person, job)              ← 1 regola matching

    Le triple inferite sono scritte nel default_world e accessibili
    via SPARQL nella Fase 3.

    Gestisce i cicli di ereditarietà ICF (warning noto dell'ontologia)
    senza interrompere il reasoning.
    """
    print("[FASE 2] Avvio Pellet (infer_property_values=True, "
          "infer_data_property_values=True)...")
    print("         [Questa operazione può richiedere 30-120 secondi]")

    # Patch per i cicli di ereditarietà nell'ICF (bug noto dell'ontologia)
    ThingMeta = type(Thing)
    orig_setattr = ThingMeta.__setattr__
    n_cycle_errors = [0]

    def patched_setattr(self, name, value):
        if name == "__bases__":
            try:
                orig_setattr(self, name, value)
            except TypeError as exc:
                if "inheritance cycle" in str(exc):
                    n_cycle_errors[0] += 1
                else:
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

        # Estrae il tempo di esecuzione dal log di Pellet
        pellet_log = stderr_buf.getvalue()
        time_match = re.search(r"Pellet took ([\d.]+)", pellet_log)
        elapsed = float(time_match.group(1)) if time_match else None

        if elapsed:
            print(f"[FASE 2] Pellet completato in {elapsed:.1f}s")
        else:
            print("[FASE 2] Pellet completato.")

        if n_cycle_errors[0]:
            print(f"         ({n_cycle_errors[0]} cicli di ereditarietà ICF "
                  "gestiti silenziosamente — comportamento atteso)")

    except Exception as exc:
        msg = str(exc)
        if "UnsupportedClassVersionError" in msg:
            raise RuntimeError(
                "[ERRORE] Versione Java insufficiente per Pellet.\n"
                "         Pellet richiede Java 11+.\n"
                "         Verificare con: java -version"
            )
        raise RuntimeError(f"[ERRORE] Pellet ha restituito un errore: {exc}")

    finally:
        ThingMeta.__setattr__ = orig_setattr

    # Verifica che Pellet abbia effettivamente inferito qualcosa
    _verify_pellet_output()


def _verify_pellet_output() -> None:
    """
    Verifica che Pellet abbia prodotto le triple attese nel world.
    ERRORE se nessuna tripla inferita trovata.
    """
    # Controlla le triple is*ImportantFor (R9-R12)
    n_importance = len(sparql(f"""
        SELECT ?s ?o WHERE {{
            {{ ?s <{IRI_IS_IMP}> ?o }}
            UNION
            {{ ?s <{IRI_IS_VERY_IMP}> ?o }}
            UNION
            {{ ?s <{IRI_IS_SOMEWHAT}> ?o }}
            UNION
            {{ ?s <{IRI_IS_LESS}> ?o }}
        }}
    """))

    if n_importance == 0:
        raise RuntimeError(
            "[ERRORE] Pellet non ha inferito nessuna tripla is*ImportantFor.\n"
            "         Verificare che le regole SWRL 9-12 siano presenti nell'ontologia."
        )
    print(f"[FASE 2] Verificato: {n_importance} triple is*ImportantFor inferite da Pellet.")

    # Controlla le triple hasSpecificCriticality (R1-R8)
    n_crit = len(sparql(f"""
        SELECT ?s ?v WHERE {{
            ?s <{IRI_HAS_CRIT}> ?v .
        }}
    """))

    if n_crit == 0:
        # Pellet ha inferito l'importanza ma non la criticità:
        # significa che nessun Person con isSelected=true e isEvaluatedForJob
        # è presente nell'ontologia.
        print(
            "[WARN] Pellet non ha inferito nessuna tripla hasSpecificCriticality.\n"
            "       Le regole SWRL 1-8 richiedono un Person con:\n"
            "         isSelected = true\n"
            "         isEvaluatedForJob = <un Job>\n"
            "       Verificare gli individui Person nell'ontologia."
        )
    else:
        print(f"[FASE 2] Verificato: {n_crit} triple hasSpecificCriticality "
              "inferite da Pellet.")


# ═══════════════════════════════════════════════════════════════════════════════
#  FASE 3 — Query SPARQL sul world arricchito da Pellet
# ═══════════════════════════════════════════════════════════════════════════════

# --- Q4: riepilogo importanza ------------------------------------------------

def query_importance_summary() -> dict:
    """
    Q4 — Legge le triple is*ImportantFor inferite da Pellet.

    SELECT ?skab ?job ?score WHERE {
        { ?skab <isImportantFor> ?job } UNION ... (per tutti e 4 i livelli)
        ?jde <concerns> ?skab .
        ?job <requires> ?jde .
        ?jde <hasScore> ?score .
    }

    Restituisce { job_name → { label → [(skab_name, score)] } }
    """
    result: dict = defaultdict(lambda: defaultdict(list))

    importance_iris = {
        "isVeryImportantFor"    : IRI_IS_VERY_IMP,
        "isImportantFor"        : IRI_IS_IMP,
        "isSomewhatImportantFor": IRI_IS_SOMEWHAT,
        "isLessImportantFor"    : IRI_IS_LESS,
    }

    for label, iri in importance_iris.items():
        rows = sparql(f"""
            SELECT ?skab ?job ?score WHERE {{
                ?skab <{iri}> ?job .
                ?jde  <{IRI_CONCERNS}> ?skab .
                ?job  <{IRI_REQUIRES}> ?jde .
                ?jde  <{IRI_HAS_SCORE}> ?score .
            }}
        """)
        for skab, job, score in rows:
            result[local_name(job)][label].append(
                (local_name(skab), int(score))
            )

    if not result:
        raise RuntimeError(
            "[ERRORE] Q4: nessuna tripla is*ImportantFor trovata nel world.\n"
            "         Verificare che Pellet abbia eseguito correttamente le regole 9-12."
        )

    return result


# --- Q1+Q2: GCS% e AISA% per (Person, Job) ----------------------------------

def query_gcs_aisa() -> list[dict]:
    """
    Q1 + Q2 — Calcola GCS% e AISA% per ogni (Person, Job).

    NOTA: hasSpecificCriticality non è usato come sorgente primaria perché
    Pellet scrive nel world una sola tripla per skab, senza riferimento al job
    specifico, producendo valori CS identici tra job diversi. Il CS viene
    invece ricalcolato in Python da hasScore (job-specific) e dal qualifier
    ICF della persona (BFqual / AP1qual), come descritto in §5.1 del paper.
    Il fallback su hasSpecificCriticality rimane attivo se la struttura HC
    non è presente nell'ontologia.

    Passo 1: recupera (person, job, skab, score, qualifier) via SPARQL.
    Passo 2: aggrega per (person, job, skab), max qualifier (§5.1).
    Passo 3: calcola CS = qualifier × anchor, poi GCS% e AISA%.
    """

    # ── Passo 1: recupera (person, job, skab, score, qualifier) ──────────────
    #
    # Per ogni skab richiesto da un job valutato dalla persona, leggiamo:
    #   - hasScore del descriptor (specifico per quel job)
    #   - BFqual  (qualificatore Body Function, per codici "b...")
    #   - AP1qual (qualificatore Activities & Participation, per codici "d...")
    # Il qualifier è il massimo tra i due (solitamente solo uno è presente).

    rows = sparql(f"""
        SELECT ?person ?job ?skab ?score ?bfq ?ap1q WHERE {{
            ?person <{IRI_IS_EVAL_JOB}> ?job .
            ?person <{IRI_IS_SELECTED}> ?selected .
            FILTER(?selected = true)

            ?job    <{IRI_REQUIRES}>    ?jde .
            ?jde    <{IRI_CONCERNS}>    ?skab .
            ?jde    <{IRI_HAS_SCORE}>   ?score .

            ?skab   <{IRI_IS_TRANSL}>   ?icf .
            ?person <{IRI_IS_IN_HC}>    ?hc .
            ?hc     <http://www.stiima.cnr.it/RientraHC#isDescribedBy> ?des .
            ?des    <http://www.stiima.cnr.it/RientraHC#involvesICFCode> ?icf .

            OPTIONAL {{ ?des <{IRI_BFQUAL}>  ?bfq  }}
            OPTIONAL {{ ?des <{IRI_AP1QUAL}> ?ap1q }}
        }}
    """)

    if not rows:
        # Fallback: prova con hasSpecificCriticality (metodo precedente)
        # così il codice rimane funzionante anche se la struttura HC cambia.
        rows_crit = sparql(f"""
            SELECT ?skab ?cs ?job ?person WHERE {{
                ?skab   <{IRI_HAS_CRIT}>    ?cs .
                ?jde    <{IRI_CONCERNS}>    ?skab .
                ?job    <{IRI_REQUIRES}>    ?jde .
                ?person <{IRI_IS_EVAL_JOB}> ?job .
                ?person <{IRI_IS_SELECTED}> ?selected .
                FILTER(?selected = true)
            }}
        """)
        if not rows_crit:
            raise RuntimeError(
                "[ERRORE] Q1+Q2: nessun dato trovato né con la query riscritta\n"
                "         né con hasSpecificCriticality. Verificare che esista\n"
                "         un Person con isSelected=true e isEvaluatedForJob."
            )
        print("[WARN] Q1+Q2: usato fallback hasSpecificCriticality "
              "(CS potrebbe essere identico tra job).")
        return _gcs_aisa_from_crit_triples(rows_crit)

    # ── Passo 2: aggrega per (person, job, skab), max qualifier ──────────────
    #
    # Struttura: agg[(p_name, j_name)][s_name] = {"score": s, "qual": max_q}

    agg: dict = {}

    for person, job, skab, score_raw, bfq_raw, ap1q_raw in rows:
        p_name = local_name(person)
        j_name = local_name(job)
        s_name = local_name(skab)
        score  = int(score_raw) if score_raw is not None else 0

        # Prendi il qualificatore disponibile (max tra BFqual e AP1qual)
        bfq  = int(bfq_raw)  if bfq_raw  is not None else 0
        ap1q = int(ap1q_raw) if ap1q_raw is not None else 0
        qual = max(bfq, ap1q)

        agg_key = (p_name, j_name)
        if agg_key not in agg:
            agg[agg_key] = {"person": p_name, "job": j_name, "skabs": {}}

        prev = agg[agg_key]["skabs"].get(s_name)
        if prev is None or qual > prev["qual"]:
            agg[agg_key]["skabs"][s_name] = {"score": score, "qual": qual}

    if not agg:
        raise RuntimeError(
            "[ERRORE] Q1+Q2: dati aggregati vuoti dopo la query riscritta.\n"
            "         Verificare la struttura HC nell'ontologia."
        )

    # ── Passo 3: calcola CS, GCS%, AISA% ─────────────────────────────────────

    results = []
    for (person, job), data in sorted(agg.items()):
        cs_values = []
        for s_name, entry in data["skabs"].items():
            anchor = _score_to_anchor(entry["score"])
            cs     = entry["qual"] * anchor
            cs_values.append((s_name, cs))

        n_total  = len(cs_values)
        n_crit   = sum(1 for _, cs in cs_values if cs > 0)
        sum_norm = sum(cs / 12.0 for _, cs in cs_values)

        gcs_pct  = (sum_norm / n_total) * 100.0 if n_total > 0 else 0.0
        aisa_pct = (n_crit  / n_total) * 100.0 if n_total > 0 else 0.0

        suitability, color = job_suitability(gcs_pct, aisa_pct)

        results.append({
            "person"     : person,
            "job"        : job,
            "cs_values"  : cs_values,
            "n_total"    : n_total,
            "n_critical" : n_crit,
            "gcs_pct"    : gcs_pct,
            "aisa_pct"   : aisa_pct,
            "suitability": suitability,
            "color"      : color,
        })

    return results


def _score_to_anchor(score: int) -> int:
    """
    Converte il punteggio O*NET nell'ancora di importanza (Tabella 2 del paper).
      score <= 25  → ancora 0  (Not important)
      26-49        → ancora 1  (Somewhat important)
      50-74        → ancora 2  (Important)
      >= 75        → ancora 3  (Very important)
    """
    if score >= 75:
        return 3
    elif score >= 50:
        return 2
    elif score >= 26:
        return 1
    else:
        return 0


def _gcs_aisa_from_crit_triples(rows_crit) -> list[dict]:
    """
    Fallback: calcola GCS%/AISA% da triple hasSpecificCriticality.
    Usato solo se la query principale (basata su hasScore + qualifier ICF)
    non trova dati. Il CS ottenuto da hasSpecificCriticality non è
    job-specific: Pellet scrive una sola tripla per skab, quindi GCS% e
    AISA% possono risultare identici tra job diversi.
    """
    aggregated: dict = {}
    for skab, cs_raw, job, person in rows_crit:
        cs     = int(cs_raw) if cs_raw is not None else 0
        p_name = local_name(person)
        j_name = local_name(job)
        s_name = local_name(skab)
        key    = (p_name, j_name)
        if key not in aggregated:
            aggregated[key] = {"person": p_name, "job": j_name, "cs_by_skab": {}}
        prev = aggregated[key]["cs_by_skab"].get(s_name, -1)
        if cs > prev:
            aggregated[key]["cs_by_skab"][s_name] = cs

    results = []
    for (person, job), data in sorted(aggregated.items()):
        cs_values = list(data["cs_by_skab"].items())
        n_total   = len(cs_values)
        n_crit    = sum(1 for _, cs in cs_values if cs > 0)
        sum_norm  = sum(cs / 12.0 for _, cs in cs_values)
        gcs_pct   = (sum_norm / n_total) * 100.0 if n_total > 0 else 0.0
        aisa_pct  = (n_crit  / n_total) * 100.0 if n_total > 0 else 0.0
        suitability, color = job_suitability(gcs_pct, aisa_pct)
        results.append({
            "person": person, "job": job, "cs_values": cs_values,
            "n_total": n_total, "n_critical": n_crit,
            "gcs_pct": gcs_pct, "aisa_pct": aisa_pct,
            "suitability": suitability, "color": color,
        })
    return results


# --- Q3: dettaglio Skill/Ability per (Person, Job) --------------------------

def query_skill_detail(person_name: str, job_name: str) -> list[dict]:
    """
    Q3 — Dettaglio completo Skill/Ability per una coppia (Person, Job).

    Legge dal world di Pellet:
      - hasSpecificCriticality (inferita da R1-R8)
      - is*ImportantFor (inferita da R9-R12)
      - hasScore, BFqual/AP1qual (dall'ontologia originale)

    SELECT ?skab ?cs ?score ?label WHERE {
        ?skab   <hasSpecificCriticality> ?cs .
        ?jde    <concerns>    ?skab .
        ?job    <requires>    ?jde .
        ?jde    <hasScore>    ?score .
        ?person <isEvaluatedForJob> ?job .
        FILTER(localname(?person) = person_name)
        FILTER(localname(?job)    = job_name)
        OPTIONAL {
            { ?skab <isVeryImportantFor> ?job . BIND("VeryImportant" AS ?label) }
            UNION ...
        }
    }
    """
    # SPARQL di owlready2 non supporta FILTER su local names —
    # recuperiamo per IRI cercando l'individuo per nome
    person_ind = default_world.search_one(iri=f"*#{person_name}")
    job_ind    = default_world.search_one(iri=f"*#{job_name}")

    if person_ind is None:
        raise RuntimeError(
            f"[ERRORE] Q3: individuo Person '{person_name}' non trovato nel world."
        )
    if job_ind is None:
        raise RuntimeError(
            f"[ERRORE] Q3: individuo Job '{job_name}' non trovato nel world."
        )

    person_iri = person_ind.iri
    job_iri    = job_ind.iri

    # Recupera tutte le righe dal world di Pellet, poi deduplica per skab
    # tenendo solo il CS massimo (stessa logica di query_gcs_aisa).
    rows = sparql(f"""
        SELECT ?skab ?cs ?score WHERE {{
            ?skab   <{IRI_HAS_CRIT}>    ?cs .
            ?jde    <{IRI_CONCERNS}>    ?skab .
            <{job_iri}> <{IRI_REQUIRES}> ?jde .
            ?jde    <{IRI_HAS_SCORE}>   ?score .
            <{person_iri}> <{IRI_IS_EVAL_JOB}> <{job_iri}> .
        }}
    """)

    # Deduplica: per ogni skab tieni CS massimo e score massimo
    best: dict = {}   # skab_iri -> {"cs": max_cs, "score": score, "obj": skab}
    for skab, cs_raw, score_raw in rows:
        cs    = int(cs_raw)    if cs_raw    is not None else 0
        score = int(score_raw) if score_raw is not None else 0
        key   = str(skab)
        if key not in best or cs > best[key]["cs"]:
            best[key] = {"cs": cs, "score": score, "obj": skab}

    details = []
    for key, entry in best.items():
        skab  = entry["obj"]
        cs    = entry["cs"]
        score = entry["score"]

        # Anchor calcolato dallo score O*NET (Tabella 2 del paper).
        # È job-specific perché hasScore dipende dal descriptor del job.
        anchor = _score_to_anchor(score)

        # Qualifier ricavato per inversione CS = qualifier × anchor.
        qualifier = cs // anchor if anchor > 0 else 0

        anchor_to_label = {
            3: "isVeryImportantFor",
            2: "isImportantFor",
            1: "isSomewhatImportantFor",
            0: "isLessImportantFor",
        }
        label = anchor_to_label.get(anchor, "isLessImportantFor")

        details.append({
            "skab_name" : local_name(skab),
            "score"     : score,
            "label"     : label,
            "anchor"    : anchor,
            "qualifier" : qualifier,
            "cs"        : cs,
            "norm"      : cs / 12.0,
            "crit_label": criticality_label(cs),
        })

    # Ordina per CS decrescente, poi per nome
    details.sort(key=lambda x: (-x["cs"], x["skab_name"]))
    return details


# ═══════════════════════════════════════════════════════════════════════════════
#  Stampa risultati
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
#  DASHBOARD TERMINALE (Rich)
# ═══════════════════════════════════════════════════════════════════════════════

# Costanti colore Rich
_SUIT_STYLE = {
    "SUITABLE"                  : "bold green",
    "SUITABLE WITH PRECAUTIONS" : "bold yellow",
    "NOT SUITABLE"              : "bold red",
}
_SUIT_ICON = {
    "SUITABLE"                  : "✔",
    "SUITABLE WITH PRECAUTIONS" : "⚠",
    "NOT SUITABLE"              : "✘",
}
_CRIT_STYLE = {
    "not critical"        : "dim",
    "SLIGHTLY CRITICAL"   : "green",
    "MODERATELY CRITICAL" : "yellow",
    "RELEVANTLY CRITICAL" : "dark_orange",
    "EXTREMELY CRITICAL"  : "bold red",
}
_ANCHOR_LABEL = {0: "Not important", 1: "Somewhat important",
                 2: "Important",     3: "Very important"}


def _rich_bar(value: float, total: float = 100.0,
              width: int = 20, color: str = "cyan") -> Text:
    """Restituisce una barra testuale Rich proporzionale a value/total."""
    filled = int(round(value / total * width))
    filled = max(0, min(filled, width))
    bar = "█" * filled + "░" * (width - filled)
    pct = f" {value:5.2f}%"
    t = Text()
    t.append(bar, style=color)
    t.append(pct, style="bold " + color)
    return t


def print_importance_summary(importance: dict) -> None:
    """Dashboard Rich — Q4: importanza Skill/Ability per job."""
    if not HAS_RICH:
        # fallback plain
        for job in sorted(importance):
            n = sum(len(v) for v in importance[job].values())
            print(f"\n  ▸ {job}  ({n} SkAb)")
            for lbl in LABEL_ORDER:
                items = sorted(importance[job].get(lbl, []), key=lambda x: -x[1])
                if items:
                    names = ", ".join(f"{n}({s})" for n, s in items)
                    print(f"    {lbl:<32} → {names}")
        return

    _console.print()
    _console.rule("[bold cyan]Q4 · IMPORTANZA SKILL/ABILITY PER JOB[/bold cyan]  "
                  "(regole SWRL 9-12)")

    ANCHOR_COLORS = {
        "isVeryImportantFor"    : ("3", "bold red",    "Very important    [≥75]"),
        "isImportantFor"        : ("2", "dark_orange", "Important         [50-74]"),
        "isSomewhatImportantFor": ("1", "yellow",      "Somewhat important[26-49]"),
        "isLessImportantFor"    : ("0", "dim",         "Not important     [≤25]"),
    }

    for job in sorted(importance):
        n_skabs = sum(len(v) for v in importance[job].values())
        t = Table(title=f"[bold]{job}[/bold]  —  {n_skabs} SkAb",
                  box=box.SIMPLE_HEAVY, show_header=True,
                  header_style="bold cyan", expand=False)
        t.add_column("Ancora", style="bold", width=3, justify="center")
        t.add_column("Livello",   width=24)
        t.add_column("Score O*NET", justify="right", width=11)
        t.add_column("Skill / Ability")

        for lbl in LABEL_ORDER:
            items = sorted(importance[job].get(lbl, []), key=lambda x: -x[1])
            sym, color, desc = ANCHOR_COLORS[lbl]
            for name, score in items:
                t.add_row(sym, f"[{color}]{desc}[/{color}]",
                          f"[{color}]{score}[/{color}]",
                          f"[{color}]{name}[/{color}]")

        _console.print(t)


def print_metrics(results: list[dict]) -> None:
    """Dashboard Rich — Q1+Q2+Q3: GCS%, AISA%, suitability, dettaglio SkAb."""
    if not HAS_RICH:
        # ── fallback plain (versione compatta) ───────────────────────────────
        by_person: dict[str, list] = defaultdict(list)
        for r in results:
            by_person[r["person"]].append(r)
        for person, job_results in sorted(by_person.items()):
            print(f"\n{'='*70}")
            print(f"  PAZIENTE: {person}")
            print(f"{'='*70}")
            print(f"  {'Job':<34} {'GCS%':>7} {'AISA%':>7}  Esito")
            print(f"  {'-'*34} {'-'*7} {'-'*7}  {'-'*30}")
            for m in sorted(job_results, key=lambda x: x["gcs_pct"]):
                icon = _SUIT_ICON.get(m["suitability"], "?")
                print(f"  {m['job']:<34} {m['gcs_pct']:>6.2f}% "
                      f"{m['aisa_pct']:>6.2f}%  {icon} {m['suitability']}")
        return

    by_person: dict[str, list] = defaultdict(list)
    for r in results:
        by_person[r["person"]].append(r)

    fn_prop  = default_world.search_one(iri=IRI_FIRST_NAME)
    sur_prop = default_world.search_one(iri=IRI_SURNAME)

    for person, job_results in sorted(by_person.items()):

        # ── nome display ─────────────────────────────────────────────────────
        p_ind = default_world.search_one(iri=f"*#{person}")
        fn  = fn_prop[p_ind][0]  if (fn_prop  and p_ind) else ""
        sur = sur_prop[p_ind][0] if (sur_prop and p_ind) else ""
        display = f"{fn} {sur}".strip() or person

        _console.print()
        _console.rule(f"[bold white]PAZIENTE: {display}[/bold white]  "
                      f"[dim](ID: {person})[/dim]", style="cyan")

        # ── KPI strip ────────────────────────────────────────────────────────
        n_ok   = sum(1 for m in job_results if m["suitability"] == "SUITABLE")
        n_warn = sum(1 for m in job_results if m["suitability"] == "SUITABLE WITH PRECAUTIONS")
        n_bad  = sum(1 for m in job_results if m["suitability"] == "NOT SUITABLE")
        avg_gcs  = sum(m["gcs_pct"]  for m in job_results) / len(job_results)
        avg_aisa = sum(m["aisa_pct"] for m in job_results) / len(job_results)

        kpis = [
            Panel(f"[bold green]{n_ok}[/bold green]",
                  title="✔ SUITABLE",       border_style="green",  width=18),
            Panel(f"[bold yellow]{n_warn}[/bold yellow]",
                  title="⚠ PRECAUTIONS",    border_style="yellow", width=18),
            Panel(f"[bold red]{n_bad}[/bold red]",
                  title="✘ NOT SUITABLE",   border_style="red",    width=18),
            Panel(f"[bold cyan]{avg_gcs:.2f}%[/bold cyan]",
                  title="GCS% medio",       border_style="cyan",   width=18),
            Panel(f"[bold cyan]{avg_aisa:.2f}%[/bold cyan]",
                  title="AISA% medio",      border_style="cyan",   width=18),
        ]
        _console.print(Columns(kpis))

        # ── tabella riepilogativa ─────────────────────────────────────────────
        _console.print()
        _console.print("[bold]RIEPILOGO  —  formule :[/bold]")
        _console.print("  [dim]CS = qualifier × anchor   │   "
                        "GCS% = [Σ(CS/12) / N] × 100   │   "
                        "AISA% = N(CS>0) / N × 100[/dim]")
        _console.print()

        recap = Table(box=box.ROUNDED, header_style="bold cyan",
                      show_lines=False, expand=False)
        recap.add_column("Job",           min_width=28)
        recap.add_column("N tot",         justify="right", width=6)
        recap.add_column("N(CS>0)",       justify="right", width=8)
        recap.add_column("GCS%",          justify="right", width=8)
        recap.add_column("barra GCS%",    width=24, no_wrap=True)
        recap.add_column("AISA%",         justify="right", width=8)
        recap.add_column("barra AISA%",   width=24, no_wrap=True)
        recap.add_column("Esito",         width=30)

        for m in sorted(job_results, key=lambda x: x["gcs_pct"]):
            s   = m["suitability"]
            sty = _SUIT_STYLE.get(s, "white")
            ico = _SUIT_ICON.get(s, "?")

            gcs_color  = {"SUITABLE":"green","SUITABLE WITH PRECAUTIONS":"yellow",
                          "NOT SUITABLE":"red"}.get(s,"cyan")
            aisa_color = gcs_color

            recap.add_row(
                m["job"].replace("_", " "),
                str(m["n_total"]),
                str(m["n_critical"]),
                f"[{gcs_color}]{m['gcs_pct']:.2f}%[/{gcs_color}]",
                _rich_bar(m["gcs_pct"], 25.0, 20, gcs_color),
                f"[{aisa_color}]{m['aisa_pct']:.2f}%[/{aisa_color}]",
                _rich_bar(m["aisa_pct"], 55.0, 20, aisa_color),
                Text(f"{ico} {s}", style=sty),
            )
        _console.print(recap)

        # ── dettaglio per ogni job ────────────────────────────────────────────
        for m in sorted(job_results, key=lambda x: x["gcs_pct"]):
            s   = m["suitability"]
            sty = _SUIT_STYLE.get(s, "white")
            ico = _SUIT_ICON.get(s, "?")

            # soglie
            thr_red    = -0.5 * m["aisa_pct"] + 21.0
            thr_yellow = -0.5 * m["aisa_pct"] + 15.5
            sum_norm   = m["gcs_pct"] / 100.0 * m["n_total"]

            if m["gcs_pct"] > thr_red:
                cmp_txt = (f"[red]{m['gcs_pct']:.4f} > {thr_red:.4f}"
                           f"  →  NOT SUITABLE ✘[/red]")
            elif m["gcs_pct"] >= thr_yellow:
                cmp_txt = (f"[yellow]{thr_yellow:.4f} ≤ {m['gcs_pct']:.4f}"
                           f" ≤ {thr_red:.4f}  →  WITH PRECAUTIONS ⚠[/yellow]")
            else:
                cmp_txt = (f"[green]{m['gcs_pct']:.4f} < {thr_yellow:.4f}"
                           f"  →  SUITABLE ✔[/green]")

            # pannello calcolo
            calc_txt = (
                f"[cyan]GCS%[/cyan]\n"
                f"  Σ(CS_i/12)         = {sum_norm:.6f}\n"
                f"  ÷ N_tot ({m['n_total']:>2})        = "
                f"{sum_norm/m['n_total']:.6f}\n"
                f"  × 100              = [bold cyan]{m['gcs_pct']:.4f}%[/bold cyan]\n\n"
                f"[cyan]AISA%[/cyan]\n"
                f"  N(CS>0)            = {m['n_critical']}\n"
                f"  N_tot              = {m['n_total']}\n"
                f"  {m['n_critical']}/{m['n_total']} × 100"
                f"             = [bold cyan]{m['aisa_pct']:.4f}%[/bold cyan]\n\n"
                f"[cyan]Soglie Fig. 4[/cyan]\n"
                f"  NOT SUIT.: GCS > -0.5·{m['aisa_pct']:.2f}+21 = {thr_red:.4f}\n"
                f"  PRECAUT. : GCS ≥ -0.5·{m['aisa_pct']:.2f}+15.5 = {thr_yellow:.4f}\n"
                f"  GCS       = {m['gcs_pct']:.4f}\n"
                f"  {cmp_txt}"
            )

            _console.print()
            _console.print(Rule(f"[{sty}]{ico} {m['job'].replace('_',' ')}[/{sty}]",
                                style=sty.split()[-1]))
            _console.print(Panel(calc_txt, title="Calcolo passo-passo",
                                 border_style="dim cyan", padding=(0, 2)))

            # tabella SkAb
            try:
                details = query_skill_detail(person, m["job"])
            except RuntimeError:
                details = [
                    {"skab_name": sn, "score": 0, "anchor": 0,
                     "qualifier": 0, "cs": cs, "norm": cs/12.0,
                     "crit_label": criticality_label(cs)}
                    for sn, cs in sorted(m["cs_values"], key=lambda x: -x[1])
                ]

            skab_tbl = Table(box=box.SIMPLE, header_style="bold dim",
                             show_lines=False, expand=False)
            skab_tbl.add_column("Skill / Ability",  min_width=30)
            skab_tbl.add_column("Score\nO*NET",      justify="right", width=6)
            skab_tbl.add_column("Ancora\n[0-3]",     justify="center", width=7)
            skab_tbl.add_column("Qual.\nICF",        justify="center", width=6)
            skab_tbl.add_column("CS\n=Q×A",          justify="center", width=5)
            skab_tbl.add_column("CS/12",             justify="right",  width=7)
            skab_tbl.add_column("barra CS",          width=14, no_wrap=True)
            skab_tbl.add_column("Criticità",         width=22)

            for s in details:
                cl  = s["crit_label"]
                cst = _CRIT_STYLE.get(cl, "white")
                anc_lbl = _ANCHOR_LABEL.get(s.get("anchor", 0), "?")
                skab_tbl.add_row(
                    f"[{cst}]{s['skab_name']}[/{cst}]",
                    str(s.get("score", 0)),
                    f"{s.get('anchor',0)} [dim]({anc_lbl[:3]}…)[/dim]"
                        if len(anc_lbl) > 4 else f"{s.get('anchor',0)}",
                    str(s.get("qualifier", 0)),
                    f"[bold {cst}]{s['cs']}[/bold {cst}]",
                    f"{s['norm']:.4f}",
                    _rich_bar(s["cs"], 12.0, 12, cst if cst != "dim" else "white"),
                    f"[{cst}]{cl}[/{cst}]",
                )
            _console.print(skab_tbl)

        _console.print()


# ═══════════════════════════════════════════════════════════════════════════════
#  FASE 4+5 — Dashboard matplotlib multi-pannello
# ═══════════════════════════════════════════════════════════════════════════════

# Palette colori matplotlib coerente con la logica del paper
_MPL_COLORS = {
    "SUITABLE"                  : "#22c55e",
    "SUITABLE WITH PRECAUTIONS" : "#f59e0b",
    "NOT SUITABLE"              : "#ef4444",
}


def plot_job_suitability(results: list[dict], output_path: str) -> None:
    """
    Dashboard matplotlib su 3 pannelli per ogni paziente:
      ① scatter GCS% vs AISA% con zone colorate (replica Fig. 4 del paper)
      ② barre orizzontali GCS% per job
      ③ barre orizzontali AISA% per job
    Salva il PNG e mostra la finestra interattiva (se il backend lo consente).
    """
    if not HAS_MATPLOTLIB:
        return

    by_person: dict[str, list] = defaultdict(list)
    for r in results:
        by_person[r["person"]].append(r)

    n_persons = len(by_person)
    # 3 colonne: scatter | GCS bars | AISA bars
    fig = plt.figure(figsize=(18, 5 * n_persons), facecolor="#0f1117")
    fig.suptitle("Rientr@ DSS — Job Suitability Dashboard\n",
                 color="white", fontsize=13, fontweight="bold", y=1.01)

    outer = gridspec.GridSpec(n_persons, 1, figure=fig,
                              hspace=0.55, left=0.06, right=0.97,
                              top=0.95, bottom=0.05)

    ZONE_ALPHA = 0.18
    BG         = "#0f1117"
    PANEL_BG   = "#181c27"
    GRID_COLOR = "#2a2f45"
    TEXT_COLOR = "#e8eaf0"
    MUTED      = "#6b7280"

    for p_idx, (person, job_results) in enumerate(sorted(by_person.items())):
        inner = gridspec.GridSpecFromSubplotSpec(
            1, 3, subplot_spec=outer[p_idx],
            wspace=0.38,
            width_ratios=[1.6, 1.2, 1.2],
        )

        jobs_sorted = sorted(job_results, key=lambda x: x["gcs_pct"])
        job_names   = [m["job"].replace("_", " ") for m in jobs_sorted]
        gcs_vals    = [m["gcs_pct"]  for m in jobs_sorted]
        aisa_vals   = [m["aisa_pct"] for m in jobs_sorted]
        colors      = [_MPL_COLORS.get(m["suitability"], "#64748b")
                       for m in jobs_sorted]

        # ── ① SCATTER ────────────────────────────────────────────────────────
        ax_sc = fig.add_subplot(inner[0])
        ax_sc.set_facecolor(PANEL_BG)

        x_line = [0, 55]
        y_red    = [-0.5 * x + 21   for x in x_line]
        y_yellow = [-0.5 * x + 15.5 for x in x_line]

        ax_sc.fill_between(x_line, y_red,    [26, 26],
                           color="#ef4444", alpha=ZONE_ALPHA, label="_")
        ax_sc.fill_between(x_line, y_yellow, y_red,
                           color="#f59e0b", alpha=ZONE_ALPHA, label="_")
        ax_sc.fill_between(x_line, [0, 0],   y_yellow,
                           color="#22c55e", alpha=ZONE_ALPHA, label="_")

        ax_sc.plot(x_line, y_red,    "--", color="#ef4444",
                   lw=1.2, label="NOT SUITABLE border")
        ax_sc.plot(x_line, y_yellow, "--", color="#f59e0b",
                   lw=1.2, label="PRECAUTIONS border")

        # zone labels
        ax_sc.text(1, 22.5, "NOT SUITABLE", color="#ef4444",
                   fontsize=7, alpha=0.8, va="top")
        ax_sc.text(1, 14.5, "WITH PRECAUTIONS", color="#f59e0b",
                   fontsize=7, alpha=0.8, va="top")
        ax_sc.text(1, 1.0,  "SUITABLE", color="#22c55e",
                   fontsize=7, alpha=0.8, va="bottom")

        markers = ["o", "s", "^", "D", "v", "P", "X", "*"]
        for j_idx, m in enumerate(jobs_sorted):
            c  = _MPL_COLORS.get(m["suitability"], "#64748b")
            mk = markers[j_idx % len(markers)]
            ax_sc.scatter(m["aisa_pct"], m["gcs_pct"],
                          color=c, marker=mk, s=100, zorder=5,
                          edgecolors="white", linewidths=0.5)
            ax_sc.annotate(
                m["job"].replace("_", " "),
                (m["aisa_pct"], m["gcs_pct"]),
                textcoords="offset points", xytext=(6, 3),
                fontsize=6.5, color=TEXT_COLOR,
                bbox=dict(boxstyle="round,pad=0.15", fc="#1e2336",
                          ec="none", alpha=0.8),
            )

        ax_sc.set_xlim(0, 55);  ax_sc.set_ylim(0, 25)
        ax_sc.set_xlabel("AISA%", color=MUTED, fontsize=9)
        ax_sc.set_ylabel("GCS%",  color=MUTED, fontsize=9)
        ax_sc.set_title(f"GCS% vs AISA%  —  {person}",
                        color=TEXT_COLOR, fontsize=9, pad=6)
        ax_sc.tick_params(colors=MUTED, labelsize=7)
        for sp in ax_sc.spines.values():
            sp.set_edgecolor(GRID_COLOR)
        ax_sc.grid(True, color=GRID_COLOR, linewidth=0.5)

        # ── ② BARRE GCS% ─────────────────────────────────────────────────────
        ax_gcs = fig.add_subplot(inner[1])
        ax_gcs.set_facecolor(PANEL_BG)

        y_pos = range(len(jobs_sorted))
        bars  = ax_gcs.barh(list(y_pos), gcs_vals, color=colors,
                            height=0.55, edgecolor="none")
        # linee soglia GCS (proiettate per ogni job con il suo AISA)
        for j_idx, m in enumerate(jobs_sorted):
            thr_r = -0.5 * m["aisa_pct"] + 21.0
            thr_y = -0.5 * m["aisa_pct"] + 15.5
            ax_gcs.plot([thr_r, thr_r], [j_idx - 0.35, j_idx + 0.35],
                        color="#ef4444", lw=1.2, alpha=0.7)
            ax_gcs.plot([thr_y, thr_y], [j_idx - 0.35, j_idx + 0.35],
                        color="#f59e0b", lw=1.2, alpha=0.7)
        # valori
        for bar, val in zip(bars, gcs_vals):
            ax_gcs.text(val + 0.15, bar.get_y() + bar.get_height() / 2,
                        f"{val:.2f}%", va="center", ha="left",
                        fontsize=7, color=TEXT_COLOR)

        ax_gcs.set_yticks(list(y_pos))
        ax_gcs.set_yticklabels(job_names, fontsize=7, color=TEXT_COLOR)
        ax_gcs.set_xlabel("GCS%", color=MUTED, fontsize=9)
        ax_gcs.set_xlim(0, max(gcs_vals) * 1.35 + 1)
        ax_gcs.set_title("General Criticality Score%\n"
                         "[dim lines = soglie per quel job]",
                         color=TEXT_COLOR, fontsize=9, pad=6)
        ax_gcs.tick_params(colors=MUTED, labelsize=7)
        for sp in ax_gcs.spines.values():
            sp.set_edgecolor(GRID_COLOR)
        ax_gcs.grid(True, axis="x", color=GRID_COLOR, linewidth=0.5)

        # ── ③ BARRE AISA% ────────────────────────────────────────────────────
        ax_aisa = fig.add_subplot(inner[2])
        ax_aisa.set_facecolor(PANEL_BG)

        bars2 = ax_aisa.barh(list(y_pos), aisa_vals,
                             color=[to_rgba(c, 0.75) for c in colors],
                             height=0.55, edgecolor="none")
        for bar, val in zip(bars2, aisa_vals):
            ax_aisa.text(val + 0.3, bar.get_y() + bar.get_height() / 2,
                         f"{val:.2f}%", va="center", ha="left",
                         fontsize=7, color=TEXT_COLOR)

        ax_aisa.set_yticks(list(y_pos))
        ax_aisa.set_yticklabels(job_names, fontsize=7, color=TEXT_COLOR)
        ax_aisa.set_xlabel("AISA%", color=MUTED, fontsize=9)
        ax_aisa.set_xlim(0, max(aisa_vals) * 1.35 + 1)
        ax_aisa.set_title("Amount Impaired SkAb%",
                          color=TEXT_COLOR, fontsize=9, pad=6)
        ax_aisa.tick_params(colors=MUTED, labelsize=7)
        for sp in ax_aisa.spines.values():
            sp.set_edgecolor(GRID_COLOR)
        ax_aisa.grid(True, axis="x", color=GRID_COLOR, linewidth=0.5)

        # legenda colori comune al pannello
        handles = [
            mpatches.Patch(color="#22c55e", label="Suitable"),
            mpatches.Patch(color="#f59e0b", label="With precautions"),
            mpatches.Patch(color="#ef4444", label="Not suitable"),
        ]
        ax_sc.legend(handles=handles, loc="upper right",
                     fontsize=7, framealpha=0.6,
                     labelcolor=TEXT_COLOR,
                     facecolor=PANEL_BG, edgecolor=GRID_COLOR)

    fig.patch.set_facecolor(BG)
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    print(f"[FASE 5] Dashboard matplotlib salvata: {output_path}")

    # Mostra finestra interattiva se il backend supporta GUI
    try:
        plt.show()
    except Exception:
        pass  # ambienti headless: il PNG è già stato salvato


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════

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
            print("[ERRORE] Nessun file .rdf/.owl trovato nella cartella dello script.")
            sys.exit(1)
        percorso = os.path.join(cartella, candidati[0])
        print(f"[INFO] File: {candidati[0]}")

    # ── FASE 1: Caricamento ──────────────────────────────────────────────────
    try:
        onto = load_ontology(percorso)
    except RuntimeError as e:
        print(e)
        sys.exit(1)

    # ── FASE 2: Pellet ───────────────────────────────────────────────────────
    try:
        run_pellet(onto)
    except RuntimeError as e:
        print(e)
        sys.exit(1)

    # ── FASE 3: Query SPARQL sul world arricchito da Pellet ──────────────────
    print("\n[FASE 3] Query SPARQL sul world arricchito da Pellet...")

    # Q4 — importanza
    try:
        importance = query_importance_summary()
    except RuntimeError as e:
        print(e)
        sys.exit(1)
    print_importance_summary(importance)

    # Q1+Q2 — GCS% e AISA%
    try:
        results = query_gcs_aisa()
    except RuntimeError as e:
        print(e)
        sys.exit(1)

    # Q3 — dettaglio incluso in print_metrics
    print_metrics(results)

    # ── FASE 4+5: Dashboard matplotlib ──────────────────────────────────────
    grafico = os.path.join(
        os.path.dirname(os.path.abspath(percorso)),
        "rientra_dashboard.png"
    )
    print(f"\n[FASE 4+5] Generazione dashboard matplotlib...")
    plot_job_suitability(results, grafico)

    print("\n[FINE]\n")


if __name__ == "__main__":
    main()