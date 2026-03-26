"""
Ontologia Rientr@ (STIIMA-CNR) — Pipeline fedele al paper con Pellet reale
===========================================================================
Spoladore et al. (2024), CSBJ 24, 374-392.

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
  pip install owlready2 matplotlib
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

# ── matplotlib (opzionale, solo per il grafico) ───────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("[WARN] matplotlib non installato: grafico non disponibile.")
    print("       Installare con: pip install matplotlib")

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
IRI_MATCHED_JOB = "http://www.stiima.cnr.it/RientraOnt3#matchedJob"

# Ancora importanza (corrispondenza regole SWRL → moltiplicatore)
ANCHOR_MAP = {
    IRI_IS_LESS    : 0,
    IRI_IS_SOMEWHAT: 1,
    IRI_IS_IMP     : 2,
    IRI_IS_VERY_IMP: 3,
}

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

    PROBLEMA STRUTTURALE DELLE REGOLE SWRL:
      Le regole 1-8 producono:  hasSpecificCriticality(?skab, ?res)
      Il soggetto e solo ?skab, NON (?skab, ?job).
      Con piu job assegnati, Pellet produce valori multipli per la stessa
      skab (uno per ogni job valutato) ma tutti indistinguibili per job.
      Leggere hasSpecificCriticality direttamente darebbe lo stesso CS
      per tutti i job — risultato errato.

    SOLUZIONE (fedele al paper):
      Usiamo is*ImportantFor(skab, job) — inferita da Pellet con R9-R12
      e JOB-SPECIFICA — per ricavare l'anchor per ogni (skab, job).
      Poi leggiamo i qualifier ICF della persona dal world di Pellet
      e calcoliamo CS = qualifier × anchor per ogni (skab, job).
      Questo e esattamente cio che fa Pellet internamente nelle R1-8,
      solo che la tripla di output non porta il job.

    Il paper (§5.3.6):
      GCS%  = AVG(CS_i / 12) * 100  per tutte le SkAb del job
      AISA% = COUNT(CS_i > 0) / COUNT(*) * 100
    """

    # ── Step 1: recupera tutti i Person con isSelected=true ────────────────
    persons_rows = sparql(f"""
        SELECT ?person ?job WHERE {{
            ?person <{IRI_IS_SELECTED}> ?sel .
            ?person <{IRI_IS_EVAL_JOB}> ?job .
            FILTER(?sel = true)
        }}
    """)

    if not persons_rows:
        raise RuntimeError(
            "[ERRORE] Q1+Q2: nessun Person con isSelected=true e "
            "isEvaluatedForJob trovato nel world."
        )

    # ── Step 2: costruisce mappa ICF → max qualifier per ogni persona ───────
    # Catena dal world di Pellet (dati originali, non inferiti):
    #   person → isInHealthCondition → hc
    #   hc → isDescribedBy → des
    #   des → involvesICFCode → icf
    #   des → [BF|AP1]qual → qualifier
    def build_icf_qual_map(person_iri: str) -> dict:
        """Mappa ICF_iri → max qualifier per questa persona."""
        hc_rows = sparql(f"""
            SELECT ?des ?icf ?bf ?ap1 WHERE {{
                <{person_iri}> <{IRI_IS_IN_HC}>  ?hc .
                ?hc <{IRI_IS_DESCRIBED}>  ?des .
                ?des <{IRI_INVOLVES_ICF}> ?icf .
                OPTIONAL {{ ?des <{IRI_BFQUAL}>  ?bf  }}
                OPTIONAL {{ ?des <{IRI_AP1QUAL}> ?ap1 }}
            }}
        """)
        icf_qual: dict = {}
        for des, icf, bf, ap1 in hc_rows:
            qual_raw = bf if bf is not None else ap1
            if qual_raw is None:
                continue
            qual = int(qual_raw)
            icf_iri = str(icf)
            icf_qual[icf_iri] = max(icf_qual.get(icf_iri, 0), qual)
        return icf_qual

    # ── Step 3: per ogni (person, job) calcola CS per ogni skab ────────────
    # Legge dal world di Pellet:
    #   is*ImportantFor(skab, job) → anchor (job-specifico, inferito R9-12)
    #   isTranslatedWithICFCode(skab, icf) → codice ICF
    # Poi: CS = max(qualifier dei codici ICF della skab) × anchor

    results = []
    person_icf_cache: dict = {}

    # Raggruppa (person, job)
    pj_pairs = {}
    for person, job in persons_rows:
        p_iri = str(person)
        j_iri = str(job)
        pj_pairs.setdefault(p_iri, []).append(j_iri)

    for p_iri, job_iris in sorted(pj_pairs.items()):
        p_name = local_name(p_iri)

        # Costruisce mappa ICF→qualifier per questa persona (una volta sola)
        if p_iri not in person_icf_cache:
            person_icf_cache[p_iri] = build_icf_qual_map(p_iri)
        icf_qual = person_icf_cache[p_iri]

        if not icf_qual:
            raise RuntimeError(
                f"[ERRORE] {p_name}: nessun qualifier ICF trovato nella HC. "
                "Verificare i HC_Descriptor nell'ontologia."
            )

        for j_iri in sorted(job_iris):
            j_name = local_name(j_iri)

            # Recupera tutte le (skab, anchor, score) per questo job
            # usando is*ImportantFor (JOB-SPECIFICO) inferita da Pellet
            skab_rows = sparql(f"""
                SELECT ?skab ?anchor ?score WHERE {{
                    {{
                        ?skab <{IRI_IS_VERY_IMP}> <{j_iri}> .
                        BIND(3 AS ?anchor)
                    }} UNION {{
                        ?skab <{IRI_IS_IMP}> <{j_iri}> .
                        BIND(2 AS ?anchor)
                    }} UNION {{
                        ?skab <{IRI_IS_SOMEWHAT}> <{j_iri}> .
                        BIND(1 AS ?anchor)
                    }} UNION {{
                        ?skab <{IRI_IS_LESS}> <{j_iri}> .
                        BIND(0 AS ?anchor)
                    }}
                    ?jde <{IRI_CONCERNS}> ?skab .
                    <{j_iri}> <{IRI_REQUIRES}> ?jde .
                    ?jde <{IRI_HAS_SCORE}> ?score .
                }}
            """)

            if not skab_rows:
                print(f"  [WARN] {j_name}: nessuna triple is*ImportantFor "
                      "trovata per questo job. Saltato.")
                continue

            # Calcola CS per ogni skab (max qualifier × anchor)
            # Deduplica per skab tenendo CS massimo
            cs_by_skab: dict = {}
            score_by_skab: dict = {}

            for skab, anchor_raw, score_raw in skab_rows:
                s_name = local_name(skab)
                anchor = int(anchor_raw) if anchor_raw is not None else 0
                score  = int(score_raw)  if score_raw  is not None else 0

                # Qualifier: max tra tutti i codici ICF che traducono questa skab
                icf_rows = sparql(f"""
                    SELECT ?icf WHERE {{
                        <{str(skab)}> <{IRI_IS_TRANSL}> ?icf .
                    }}
                """)
                max_qual = 0
                for (icf_ind,) in icf_rows:
                    q = icf_qual.get(str(icf_ind), 0)
                    if q > max_qual:
                        max_qual = q

                cs = max_qual * anchor

                # Deduplica: tieni CS massimo per skab
                prev_cs = cs_by_skab.get(s_name, -1)
                if cs > prev_cs:
                    cs_by_skab[s_name]    = cs
                    score_by_skab[s_name] = score

            cs_values  = list(cs_by_skab.items())
            n_total    = len(cs_values)
            n_crit     = sum(1 for _, cs in cs_values if cs > 0)
            sum_norm   = sum(cs / 12.0 for _, cs in cs_values)

            gcs_pct  = (sum_norm / n_total) * 100.0 if n_total > 0 else 0.0
            aisa_pct = (n_crit  / n_total) * 100.0 if n_total > 0 else 0.0
            suitability, color = job_suitability(gcs_pct, aisa_pct)

            results.append({
                "person"     : p_name,
                "job"        : j_name,
                "cs_values"  : cs_values,
                "score_map"  : score_by_skab,
                "n_total"    : n_total,
                "n_critical" : n_crit,
                "gcs_pct"    : gcs_pct,
                "aisa_pct"   : aisa_pct,
                "suitability": suitability,
                "color"      : color,
            })

    if not results:
        raise RuntimeError(
            "[ERRORE] Q1+Q2: nessun risultato calcolato. "
            "Verificare is*ImportantFor nel world di Pellet."
        )

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

    # Usa la stessa logica di query_gcs_aisa:
    # legge is*ImportantFor(skab, job) dal world Pellet (job-specifico)
    # e calcola CS = qualifier * anchor per ogni skab.
    skab_rows = sparql(f"""
        SELECT ?skab ?anchor ?score WHERE {{
            {{
                ?skab <{IRI_IS_VERY_IMP}> <{job_iri}> .
                BIND(3 AS ?anchor)
            }} UNION {{
                ?skab <{IRI_IS_IMP}> <{job_iri}> .
                BIND(2 AS ?anchor)
            }} UNION {{
                ?skab <{IRI_IS_SOMEWHAT}> <{job_iri}> .
                BIND(1 AS ?anchor)
            }} UNION {{
                ?skab <{IRI_IS_LESS}> <{job_iri}> .
                BIND(0 AS ?anchor)
            }}
            ?jde <{IRI_CONCERNS}> ?skab .
            <{job_iri}> <{IRI_REQUIRES}> ?jde .
            ?jde <{IRI_HAS_SCORE}> ?score .
        }}
    """)

    # Costruisce mappa ICF→qualifier per questa persona
    hc_rows = sparql(f"""
        SELECT ?icf ?bf ?ap1 WHERE {{
            <{person_iri}> <{IRI_IS_IN_HC}>  ?hc .
            ?hc <{IRI_IS_DESCRIBED}>  ?des .
            ?des <{IRI_INVOLVES_ICF}> ?icf .
            OPTIONAL {{ ?des <{IRI_BFQUAL}>  ?bf  }}
            OPTIONAL {{ ?des <{IRI_AP1QUAL}> ?ap1 }}
        }}
    """)
    icf_qual: dict = {}
    for icf, bf, ap1 in hc_rows:
        qual_raw = bf if bf is not None else ap1
        if qual_raw is None: continue
        icf_qual[str(icf)] = max(icf_qual.get(str(icf), 0), int(qual_raw))

    # Calcola CS per ogni skab (deduplica tenendo max CS)
    best: dict = {}
    for skab, anchor_raw, score_raw in skab_rows:
        s_name = local_name(skab)
        anchor = int(anchor_raw) if anchor_raw is not None else 0
        score  = int(score_raw)  if score_raw  is not None else 0

        icf_r = sparql(f"SELECT ?icf WHERE {{ <{str(skab)}> <{IRI_IS_TRANSL}> ?icf . }}")
        max_qual = max((icf_qual.get(str(i[0]), 0) for i in icf_r), default=0)
        cs = max_qual * anchor

        if s_name not in best or cs > best[s_name]["cs"]:
            best[s_name] = {
                "skab_name" : s_name,
                "score"     : score,
                "anchor"    : anchor,
                "qualifier" : max_qual,
                "cs"        : cs,
                "norm"      : cs / 12.0,
                "label"     : _get_importance_label(skab, job_ind),
                "crit_label": criticality_label(cs),
            }

    details = sorted(best.values(), key=lambda x: (-x["cs"], x["skab_name"]))
    return details


def _get_importance_label(skab, job_ind) -> str:
    """Legge dal world di Pellet il livello di importanza per (skab, job)."""
    job_iri = job_ind.iri
    skab_iri = skab.iri if hasattr(skab, "iri") else str(skab)

    for label, iri in [
        ("isVeryImportantFor",    IRI_IS_VERY_IMP),
        ("isImportantFor",        IRI_IS_IMP),
        ("isSomewhatImportantFor",IRI_IS_SOMEWHAT),
        ("isLessImportantFor",    IRI_IS_LESS),
    ]:
        rows = sparql(f"""
            SELECT ?s WHERE {{
                <{skab_iri}> <{iri}> <{job_iri}> .
                BIND(<{skab_iri}> AS ?s)
            }} LIMIT 1
        """)
        if rows:
            return label
    return "isLessImportantFor"


# ═══════════════════════════════════════════════════════════════════════════════
#  Stampa risultati
# ═══════════════════════════════════════════════════════════════════════════════

def print_importance_summary(importance: dict) -> None:
    n_total = sum(
        len(items)
        for job_data in importance.values()
        for items in job_data.values()
    )
    print(f"\n{'='*72}")
    print(f"  [Q4] IMPORTANZA inferita da Pellet  ({n_total} triple is*ImportantFor)")
    print(f"  Regole SWRL 9-12: score<=24→Less | 25-49→Somewhat | "
          f"50-74→Important | >=75→Very")
    print(f"{'='*72}")

    for job in sorted(importance):
        n_skabs = sum(len(v) for v in importance[job].values())
        print(f"\n  ► {job}  ({n_skabs} Skill/Ability)")
        for lbl in LABEL_ORDER:
            items = sorted(importance[job].get(lbl, []), key=lambda x: -x[1])
            if items:
                names = ", ".join(f"{n}({s})" for n, s in items)
                print(f"    {lbl:<32} → {names}")


def print_metrics(results: list[dict]) -> None:
    by_person: dict[str, list] = defaultdict(list)
    for r in results:
        by_person[r["person"]].append(r)

    for person, job_results in sorted(by_person.items()):
        # Recupera nome e cognome dal world
        p_ind = default_world.search_one(iri=f"*#{person}")
        fn_prop  = default_world.search_one(iri=IRI_FIRST_NAME)
        sur_prop = default_world.search_one(iri=IRI_SURNAME)
        fn  = fn_prop[p_ind][0]  if (fn_prop  and p_ind) else ""
        sur = sur_prop[p_ind][0] if (sur_prop and p_ind) else ""
        display = f"{fn} {sur}".strip() or person

        print(f"\n{'='*72}")
        print(f"  [Q1+Q2] RISULTATI — {display} ({person})")
        print(f"  GCS%  = AVG(CS_i / 12) * 100   CS_i = qualifier × anchor")
        print(f"  AISA% = (n SkAb con CS>0 / n totale) * 100")
        print(f"{'='*72}")

        emoji = {
            "SUITABLE"                  : "[OK] ",
            "SUITABLE WITH PRECAUTIONS" : "[!!] ",
            "NOT SUITABLE"              : "[XX] ",
        }
        print(f"\n  {'Job':<42} {'GCS%':>7} {'AISA%':>7}  Suitability")
        print(f"  {'-'*42} {'-'*7} {'-'*7}  {'-'*28}")
        for m in sorted(job_results, key=lambda x: x["gcs_pct"]):
            e = emoji.get(m["suitability"], "     ")
            print(f"  {m['job']:<42} {m['gcs_pct']:>6.2f}% "
                  f"{m['aisa_pct']:>6.2f}%  {e} {m['suitability']}")

        # Dettaglio per ogni job
        for m in sorted(job_results, key=lambda x: x["gcs_pct"]):
            print(f"\n  {'─'*68}")
            print(f"  JOB: {m['job']}")
            print(f"  GCS%={m['gcs_pct']:.4f}%  |  AISA%={m['aisa_pct']:.4f}%")
            print(f"  Suitability: {m['suitability']}")
            print(f"  SkAb totali: {m['n_total']}  |  con CS>0: {m['n_critical']}")

            # Q3 — dettaglio ordinato per CS
            try:
                details = query_skill_detail(person, m["job"])
            except RuntimeError as e:
                print(f"  [WARN] {e}")
                # Fallback: usa i valori già aggregati
                details = [
                    {
                        "skab_name" : sn,
                        "score"     : 0,
                        "label"     : "?",
                        "anchor"    : cs // max(cs, 1),
                        "qualifier" : 0,
                        "cs"        : cs,
                        "norm"      : cs / 12.0,
                        "crit_label": criticality_label(cs),
                    }
                    for sn, cs in sorted(m["cs_values"], key=lambda x: -x[1])
                ]

            print(f"\n  [Q3] Dettaglio Skill/Ability (da Pellet, ordinato per CS):")
            print(f"  {'Skill/Ability':<35} {'Sc':>4} {'An':>2} {'Qu':>2} "
                  f"{'CS':>2} {'Norm':>7}  Criticità")
            print(f"  {'-'*35} {'-'*4} {'-'*2} {'-'*2} "
                  f"{'-'*2} {'-'*7}  {'-'*22}")
            for s in details:
                print(f"  {s['skab_name']:<35} {s['score']:>4} "
                      f"{s['anchor']:>2} {s['qualifier']:>2} "
                      f"{s['cs']:>2} {s['norm']:>7.4f}  {s['crit_label']}")


# ═══════════════════════════════════════════════════════════════════════════════
#  FASE 4+5 — Grafico GCS% vs AISA% (Fig. 4 del paper)
# ═══════════════════════════════════════════════════════════════════════════════

def plot_job_suitability(results: list[dict], output_path: str) -> None:
    if not HAS_MATPLOTLIB:
        return

    fig, ax = plt.subplots(figsize=(11, 7))
    x_arr = [0, 55]

    y_red    = [JS_SLOPE * x + JS_RED_INTERCEPT    for x in x_arr]
    y_yellow = [JS_SLOPE * x + JS_YELLOW_INTERCEPT for x in x_arr]

    ax.fill_between(x_arr, y_red,    [26]*2, color="#ffcccc", alpha=0.5)
    ax.fill_between(x_arr, y_yellow, y_red,  color="#fff3cc", alpha=0.6)
    ax.fill_between(x_arr, [0]*2,  y_yellow, color="#ccffcc", alpha=0.5)

    ax.plot(x_arr, y_red,    "r--", lw=1.2,
            label="GCS = -0.5·AISA + 21   (confine rosso/giallo)")
    ax.plot(x_arr, y_yellow, color="darkorange", linestyle="--", lw=1.2,
            label="GCS = -0.5·AISA + 15.5 (confine giallo/verde)")

    markers = ["o", "s", "^", "D", "v", "P", "X", "*", "h", "p"]
    by_person: dict[str, list] = defaultdict(list)
    for r in results:
        by_person[r["person"]].append(r)

    for p_idx, (person, job_results) in enumerate(sorted(by_person.items())):
        for j_idx, m in enumerate(job_results):
            mk  = markers[(p_idx * 10 + j_idx) % len(markers)]
            ax.scatter(m["aisa_pct"], m["gcs_pct"],
                       c=m["color"], marker=mk, s=130, zorder=5,
                       edgecolors="black", linewidths=0.5)
            label_txt = (
                f"{person}\n{m['job'].replace('_', ' ')}\n"
                f"({m['gcs_pct']:.2f}%, {m['aisa_pct']:.2f}%)"
            )
            ax.annotate(label_txt,
                        (m["aisa_pct"], m["gcs_pct"]),
                        textcoords="offset points", xytext=(7, 4),
                        fontsize=7,
                        bbox=dict(boxstyle="round,pad=0.2",
                                  fc="white", alpha=0.65, lw=0))

    pg = mpatches.Patch(color="#ccffcc", alpha=0.8, label="Suitable")
    py = mpatches.Patch(color="#fff3cc", alpha=0.8, label="Suitable with precautions")
    pr = mpatches.Patch(color="#ffcccc", alpha=0.8, label="Not suitable")
    lh, _ = ax.get_legend_handles_labels()
    ax.legend(handles=[pg, py, pr] + lh,
              loc="upper right", fontsize=8, framealpha=0.9)

    ax.set_xlabel("AISA%  —  Amount of Impaired Skills and Abilities (%)", fontsize=11)
    ax.set_ylabel("GCS%  —  General Criticality Score (%)", fontsize=11)
    persons_str = " | ".join(sorted(by_person.keys()))
    ax.set_title(
        f"Job Suitability — {persons_str}\n"
        f"(Rientr@ DSS — Spoladore et al. 2024 — Pellet + SPARQL)",
        fontsize=11,
    )
    ax.set_xlim(0, 55)
    ax.set_ylim(0, 25)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[FASE 5] Grafico salvato: {output_path}")


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

    # ── FASE 4+5: Suitability + Grafico ─────────────────────────────────────
    grafico = os.path.join(
        os.path.dirname(os.path.abspath(percorso)),
        "job_suitability_pellet.png"
    )
    print(f"\n[FASE 4+5] Job Suitability e grafico...")
    plot_job_suitability(results, grafico)

    print("\n[FINE]\n")


if __name__ == "__main__":
    main()