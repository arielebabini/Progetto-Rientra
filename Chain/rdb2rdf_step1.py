"""
rdb2rdf_step1.py
================
Step 1 del progetto Rientra@: RDB2RDF con string matching.

Fasi eseguite:
  1. Connessione a PostgreSQL e lettura delle tabelle
  2. Direct Mapping  — traduzione automatica DB → RDF (senza config)
  3. R2RML-style Mapping — traduzione controllata verso l'ontologia Rientra@
  4. String Matching — risoluzione del mismatch tra nomi job DB e O*NET
  5. Arricchimento del grafo con i risultati del matching
  6. Serializzazione dell'output in Turtle e RDF/XML

Requisiti:
    pip install psycopg2-binary rdflib

Uso:
    python rdb2rdf_step1.py
"""

import sys
import os
from datetime import datetime

import psycopg2
import psycopg2.extras
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, XSD, OWL
from rdflib.namespace import FOAF

# ─────────────────────────────────────────────────────────────
# CONFIGURAZIONE — modifica questi valori
# ─────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "rientra_db",
    "user":     "postgres",       # oppure il tuo username macOS
    "password": "postgres"        # la password scelta durante l'installazione
}

ONTOLOGY_FILE = "ontology/rientra_mini.ttl"   # percorso all'ontologia
OUTPUT_DIR    = "output"

# ─────────────────────────────────────────────────────────────
# NAMESPACE
# ─────────────────────────────────────────────────────────────

RIENTRA = Namespace("https://www.stiima.cnr.it/rientra#")
BASE_DM  = Namespace("http://example.org/rientra/")   # usato solo nel Direct Mapping


# ═════════════════════════════════════════════════════════════
# UTILITÀ DB
# ═════════════════════════════════════════════════════════════

def get_connection():
    """Apre e restituisce una connessione a PostgreSQL."""
    return psycopg2.connect(**DB_CONFIG)


def fetch_all(sql: str, params=None) -> list[dict]:
    """Esegue una query e restituisce una lista di dizionari."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def test_connection() -> bool:
    """Verifica che la connessione al DB funzioni."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()[0]
        print(f"  ✓ PostgreSQL OK: {version[:50]}...")
        return True
    except Exception as e:
        print(f"  ✗ Errore connessione: {e}")
        print("  → Verifica DB_CONFIG in cima allo script.")
        return False


# ═════════════════════════════════════════════════════════════
# FASE 1 — DIRECT MAPPING
# ═════════════════════════════════════════════════════════════

def direct_mapping() -> Graph:
    """
    Implementa il W3C Direct Mapping (https://www.w3.org/TR/rdb-direct-mapping/).

    Regole applicate:
    - Ogni tabella  →  una Classe RDF  (es. ex:wheelchair_user)
    - Ogni riga     →  un individuo    (IRI = base + tabella + PK)
    - Ogni colonna  →  una datatype property
    - Ogni FK       →  un riferimento (non risolto in join, solo il valore)

    Non richiede configurazione ma produce RDF che NON rispetta
    il vocabolario dell'ontologia Rientra@.
    """
    g = Graph()
    g.bind("ex", BASE_DM)

    # Tabelle da mappare con la loro chiave primaria
    tables = [
        ("wheelchair_user",    "id"),
        ("icf_code",           "code"),
        ("health_condition",   "id"),
        ("health_condition_code", "id"),
        ("job",                "id"),
        ("job_descriptor",     "id"),
    ]

    total = 0
    for table_name, pk_col in tables:
        rows = fetch_all(f"SELECT * FROM {table_name}")
        table_class = BASE_DM[table_name]

        for row in rows:
            pk_val  = str(row[pk_col])
            subject = BASE_DM[f"{table_name}/{pk_val}"]

            # rdf:type
            g.add((subject, RDF.type, table_class))

            # Una proprietà per ogni colonna non nulla
            for col, val in row.items():
                if val is None:
                    continue
                prop = BASE_DM[f"{table_name}#{col}"]
                g.add((subject, prop, Literal(str(val))))

        count = len(rows)
        total += count
        print(f"    {table_name:30s}  {count:3d} righe  →  {count * (1 + len(rows[0]) if rows else 0)} triple")

    print(f"    ─────────────────────────────────────────")
    print(f"    Totale triple (Direct Mapping): {len(g)}")
    return g


# ═════════════════════════════════════════════════════════════
# FASE 2 — R2RML-STYLE MAPPING
# ═════════════════════════════════════════════════════════════

def r2rml_mapping(ontology_graph: Graph) -> Graph:
    """
    Mapping controllato verso l'ontologia Rientra@.

    Ogni funzione interna replica una TriplesMap R2RML:
    - SubjectMap:  IRI costruito dalla PK, classe dall'ontologia
    - PredicateObjectMap: proprietà → colonne SQL
    - JoinCondition: FK → object property verso l'individuo referenziato

    Questo approccio in Python è equivalente a un file R2RML .ttl
    eseguito da morph-kgc, ma più leggibile per scopi didattici.
    """

    # Parte dal grafo dell'ontologia (classi e proprietà già definite)
    g = Graph()

    # Bind dei namespace
    g.bind("rientra", RIENTRA)
    g.bind("foaf",    FOAF)
    g.bind("xsd",     XSD)
    g.bind("owl",     OWL)
    g.bind("rdfs",    RDFS)

    # Aggiunge le triple dell'ontologia (T-Box) al grafo
    for triple in ontology_graph:
        g.add(triple)

    total_individuals = 0

    # ── wheelchair_user → rientra:Wheelchair_user ──────────────
    users = fetch_all("SELECT * FROM wheelchair_user")
    for row in users:
        subj = RIENTRA[f"WU_{row['id']}"]
        g.add((subj, RDF.type,        RIENTRA.Wheelchair_user))
        g.add((subj, FOAF.givenName, Literal(row["first_name"])))
        g.add((subj, FOAF.lastName,  Literal(row["last_name"])))
        if row.get("email"):
            g.add((subj, FOAF.mbox,   Literal(row["email"])))
        if row.get("birth_year"):
            g.add((subj, FOAF.birthday, Literal(row["birth_year"], datatype=XSD.integer)))
        if row.get("gender"):
            g.add((subj, FOAF.gender, Literal(row["gender"])))
    print(f"    wheelchair_user       →  {len(users)} individui rientra:Wheelchair_user")
    total_individuals += len(users)

    # ── icf_code → rientra:ICF_Code ───────────────────────────
    icf_codes = fetch_all("SELECT * FROM icf_code")
    for row in icf_codes:
        subj = RIENTRA[f"ICF_{row['code']}"]
        g.add((subj, RDF.type,              RIENTRA.ICF_Code))
        g.add((subj, RDFS.label,            Literal(row["name"],        lang="en")))
        g.add((subj, RIENTRA.hasICFCode,    Literal(row["code"])))
        g.add((subj, RIENTRA.hasComponent,  Literal(row["component"])))
        if row.get("description"):
            g.add((subj, RIENTRA.hasDescription, Literal(row["description"], datatype=XSD.string)))
    print(f"    icf_code              →  {len(icf_codes)} individui rientra:ICF_Code")
    total_individuals += len(icf_codes)

    # ── health_condition → rientra:HealthCondition ─────────────
    conditions = fetch_all("SELECT * FROM health_condition")
    for row in conditions:
        subj = RIENTRA[f"HC_{row['id']}"]
        g.add((subj, RDF.type,                  RIENTRA.HealthCondition))
        g.add((subj, RIENTRA.assessedOnDate,     Literal(str(row["assessed_on"]), datatype=XSD.date)))
        # object property → WU (FK: worker_id)
        g.add((subj, RIENTRA.isHealthConditionOf, RIENTRA[f"WU_{row['worker_id']}"]))
        if row.get("notes"):
            g.add((subj, RIENTRA.hasNotes, Literal(row["notes"], datatype=XSD.string)))
    print(f"    health_condition      →  {len(conditions)} individui rientra:HealthCondition")
    total_individuals += len(conditions)

    # ── health_condition_code → rientra:HCDescriptor ───────────
    hc_codes = fetch_all("SELECT * FROM health_condition_code")
    for row in hc_codes:
        subj = RIENTRA[f"HCDesc_{row['id']}"]
        g.add((subj, RDF.type, RIENTRA.HCDescriptor))

        # Qualificatore 1: per b = bodyFunctionQual, per d = activityPart1stQual
        icf_row = next((r for r in icf_codes if r["code"] == row["icf_code"]), None)
        if icf_row and icf_row["component"] == "b":
            if row.get("qualifier_1") is not None:
                g.add((subj, RIENTRA.bodyFunctionQual,
                       Literal(row["qualifier_1"], datatype=XSD.integer)))
        elif icf_row and icf_row["component"] == "d":
            if row.get("qualifier_1") is not None:
                g.add((subj, RIENTRA.activityPart1stQual,
                       Literal(row["qualifier_1"], datatype=XSD.integer)))

        if row.get("qualifier_2") is not None:
            g.add((subj, RIENTRA.qualifier2,
                   Literal(row["qualifier_2"], datatype=XSD.integer)))

        # FK → HealthCondition
        g.add((subj, RIENTRA.isDescribedBy,   RIENTRA[f"HC_{row['condition_id']}"]))
        # FK → ICF_Code
        g.add((subj, RIENTRA.involvesICFCode, RIENTRA[f"ICF_{row['icf_code']}"]))

    print(f"    health_condition_code →  {len(hc_codes)} individui rientra:HCDescriptor")
    total_individuals += len(hc_codes)

    # ── job → rientra:Job ──────────────────────────────────────
    jobs = fetch_all("SELECT * FROM job")
    for row in jobs:
        subj = RIENTRA[f"Job_{row['id']}"]
        g.add((subj, RDF.type,               RIENTRA.Job))
        g.add((subj, RIENTRA.hasJobNameInDB, Literal(row["name"], datatype=XSD.string)))
        if row.get("description"):
            g.add((subj, RIENTRA.hasDescription, Literal(row["description"], datatype=XSD.string)))
        if row.get("onet_code"):
            g.add((subj, RIENTRA.hasONETCode, Literal(row["onet_code"])))
    print(f"    job                   →  {len(jobs)} individui rientra:Job")
    total_individuals += len(jobs)

    # ── job_descriptor → rientra:Job_Descriptor ────────────────
    descriptors = fetch_all("SELECT * FROM job_descriptor")
    for row in descriptors:
        subj = RIENTRA[f"JDesc_{row['id']}"]
        g.add((subj, RDF.type,                  RIENTRA.Job_Descriptor))
        g.add((subj, RIENTRA.hasDescriptorName, Literal(row["descriptor_name"], datatype=XSD.string)))
        if row.get("category"):
            g.add((subj, RIENTRA.hasCategory, Literal(row["category"])))
        if row.get("importance_score") is not None:
            g.add((subj, RIENTRA.hasScore,
                   Literal(row["importance_score"], datatype=XSD.integer)))
        if row.get("importance_anchor") is not None:
            g.add((subj, RIENTRA.hasImportanceAnchor,
                   Literal(row["importance_anchor"], datatype=XSD.integer)))
        # FK → Job
        g.add((subj, RIENTRA.isDescriptorOf, RIENTRA[f"Job_{row['job_id']}"]))

    print(f"    job_descriptor        →  {len(descriptors)} individui rientra:Job_Descriptor")
    total_individuals += len(descriptors)

    print(f"    ─────────────────────────────────────────")
    print(f"    Totale individui: {total_individuals}  |  Triple nel grafo: {len(g)}")
    return g


# ═════════════════════════════════════════════════════════════
# FASE 3 — STRING MATCHING (Soluzione 1)
# ═════════════════════════════════════════════════════════════

# Vocabolario O*NET: nome canonico → label alternative
# In un sistema reale questo viene estratto dall'ontologia via SPARQL
ONET_LABELS: dict[str, list[str]] = {
    "Archivists": [
        "Accessioning Archivist", "Archivist", "Digital Archivist",
        "Film Archivist", "Museum Archivist", "Records Manager",
        "Reference Archivist", "Registrar", "State Archivist", "University Archivist"
    ],
    "File Clerks": [
        "Administrative Clerk", "Claim Clerk", "Document Clerk",
        "File Clerk", "Record Clerk", "Filing Clerk", "Office Document Manager"
    ],
    "Receptionists and Information Clerks": [
        "Front Desk Agent", "Front Desk Coordinator", "Receptionist",
        "Information Clerk", "Office Receptionist", "Customer Service Operator"
    ],
    "Word Processors and Typists": [
        "Data Entry Specialist", "Document Processor", "Typist",
        "Word Processor", "Text Processing Operator", "Data Entry Operator"
    ],
    "Landscaping and Groundskeeping Workers": [
        "Groundskeeper", "Landscape Technician", "Lawn Care Specialist",
        "Garden Maintenance Worker", "Outdoor Maintenance Worker"
    ],
}

# Ground truth: codice O*NET → nome canonico (per valutazione accuratezza)
ONET_CODE_TO_NAME: dict[str, str] = {
    "25-4011.00": "Archivists",
    "43-4071.00": "File Clerks",
    "43-4171.00": "Receptionists and Information Clerks",
    "43-9022.00": "Word Processors and Typists",
    "37-3011.00": "Landscaping and Groundskeeping Workers",
}


def normalize(s: str) -> str:
    """Minuscolo e strip."""
    return s.lower().strip()


def jaccard_similarity(s1: str, s2: str) -> float:
    """
    Jaccard sugli insiemi di parole: |A ∩ B| / |A ∪ B|
    Valore in [0, 1]. Bassa sensibilità alla lunghezza delle stringhe.
    """
    a = set(normalize(s1).split())
    b = set(normalize(s2).split())
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def overlap_coefficient(s1: str, s2: str) -> float:
    """
    Overlap: |A ∩ B| / min(|A|, |B|)
    Utile quando un nome breve è sottoinsieme di uno più lungo.
    """
    a = set(normalize(s1).split())
    b = set(normalize(s2).split())
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def levenshtein_similarity(s1: str, s2: str) -> float:
    """
    Distanza di edit normalizzata: 1 - dist / max_len
    Sensibile all'ordine dei caratteri, utile per abbreviazioni.
    """
    s1, s2 = normalize(s1), normalize(s2)
    m, n = len(s1), len(s2)
    if m == 0 and n == 0:
        return 1.0
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            dp[j] = min(prev[j] + 1, dp[j-1] + 1, prev[j-1] + cost)
    return 1.0 - dp[n] / max(m, n)


def combined_score(s1: str, s2: str) -> float:
    """
    Score combinato: media pesata di Jaccard e Overlap.
    Jaccard è più affidabile in generale (peso 0.6),
    Overlap gestisce meglio le coppie asimmetriche (peso 0.4).
    """
    return 0.6 * jaccard_similarity(s1, s2) + 0.4 * overlap_coefficient(s1, s2)


def find_best_match(db_name: str, threshold: float = 0.15) -> dict | None:
    """
    Trova il miglior candidato O*NET per un nome proveniente dal DB.

    Strategia:
    1. Confronta db_name con ogni nome O*NET e le sue label alternative
    2. Per ogni professione prende il punteggio massimo tra tutte le label
    3. Restituisce il candidato con score massimo (se >= threshold)

    Returns:
        dict con chiavi: onet_name, best_label, score
        oppure None se nessun candidato supera la soglia
    """
    best_onet   = None
    best_label  = None
    best_score  = 0.0

    for onet_name, alt_labels in ONET_LABELS.items():
        for label in [onet_name] + alt_labels:
            score = combined_score(db_name, label)
            if score > best_score:
                best_score  = score
                best_onet   = onet_name
                best_label  = label

    if best_score >= threshold:
        return {"onet_name": best_onet, "best_label": best_label, "score": best_score}
    return None


def run_string_matching() -> list[dict]:
    """
    Esegue il matching per tutti i lavori nel DB.
    Restituisce la lista dei risultati con valutazione accuratezza.
    """
    jobs = fetch_all("SELECT id, name, onet_code FROM job ORDER BY id")
    results = []

    for row in jobs:
        match = find_best_match(row["name"])
        expected = ONET_CODE_TO_NAME.get(row["onet_code"], "?")
        found    = match["onet_name"] if match else None
        correct  = (found == expected)

        results.append({
            "job_id":    row["id"],
            "db_name":   row["name"],
            "onet_code": row["onet_code"],
            "expected":  expected,
            "found":     found,
            "via_label": match["best_label"] if match else None,
            "score":     match["score"] if match else 0.0,
            "correct":   correct,
        })

        mark = "✓" if correct else "✗"
        print(f"    {mark} [{row['id']}] {row['name'][:38]:38s}")
        print(f"         Atteso:  {expected}")
        print(f"         Trovato: {found or '[nessun match]'}  (score={results[-1]['score']:.3f})")
        if match:
            print(f"         Via:     {match['best_label']}")
        print()

    n_correct = sum(1 for r in results if r["correct"])
    print(f"    Accuratezza: {n_correct}/{len(results)} = {n_correct/len(results)*100:.0f}%")
    return results


def enrich_graph_with_matching(g: Graph, matching_results: list[dict]) -> Graph:
    """
    Aggiunge al grafo RDF le triple che collegano ogni Job del DB
    al corrispondente Job O*NET nell'ontologia, con lo score di matching.
    """
    added = 0
    for r in matching_results:
        if not r["found"]:
            continue
        db_job_uri = RIENTRA[f"Job_{r['job_id']}"]
        # IRI del job O*NET (nell'ontologia reale questo punterebbe all'individuo esistente)
        onet_safe  = r["found"].replace(" ", "_").replace(",", "")
        onet_uri   = RIENTRA[f"ONETJob_{onet_safe}"]

        g.add((db_job_uri, RIENTRA.matchedToONETJob, onet_uri))
        g.add((db_job_uri, RIENTRA.matchingScore,
                Literal(round(r["score"], 4), datatype=XSD.decimal)))
        g.add((db_job_uri, RIENTRA.matchedViaLabel,
                Literal(r["via_label"], datatype=XSD.string)))
        added += 3

    print(f"    {added} triple aggiunte al grafo (matching)")
    return g


# ═════════════════════════════════════════════════════════════
# FASE 4 — SERIALIZZAZIONE OUTPUT
# ═════════════════════════════════════════════════════════════

def save_graph(g: Graph, name: str):
    """Salva il grafo in Turtle e RDF/XML."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    ttl_path = os.path.join(OUTPUT_DIR, f"{name}.ttl")
    rdf_path = os.path.join(OUTPUT_DIR, f"{name}.rdf")

    g.serialize(ttl_path, format="turtle")
    g.serialize(rdf_path, format="xml")

    # Conta solo le triple A-Box (individui), escludendo T-Box
    abox_count = sum(1 for s, p, o in g if not isinstance(s, URIRef)
                     or str(s).startswith("https://www.stiima.cnr.it/rientra#")
                     and p != RDF.type or p == RDF.type
                     and o not in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty))

    print(f"    Turtle  →  {ttl_path}  ({os.path.getsize(ttl_path):,} bytes)")
    print(f"    RDF/XML →  {rdf_path}  ({os.path.getsize(rdf_path):,} bytes)")
    print(f"    Totale triple nel grafo: {len(g)}")


# ═════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Rientra@ — Step 1: RDB2RDF + String Matching")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── Test connessione ──────────────────────────────────────
    print("\n[0] Test connessione PostgreSQL")
    if not test_connection():
        sys.exit(1)

    # ── Carica l'ontologia (T-Box) ────────────────────────────
    print(f"\n[0] Caricamento ontologia: {ONTOLOGY_FILE}")
    onto_graph = Graph()
    onto_graph.parse(ONTOLOGY_FILE, format="turtle")
    print(f"  ✓ {len(onto_graph)} triple caricate dall'ontologia")

    # ── Fase 1: Direct Mapping ────────────────────────────────
    print("\n[1] DIRECT MAPPING")
    print("    (traduzione automatica senza configurazione)\n")
    g_direct = direct_mapping()
    save_graph(g_direct, "direct_mapping")

    # ── Fase 2: R2RML-style Mapping ───────────────────────────
    print("\n[2] R2RML-STYLE MAPPING")
    print("    (mapping controllato verso l'ontologia Rientra@)\n")
    g_r2rml = r2rml_mapping(onto_graph)
    save_graph(g_r2rml, "r2rml_mapping")

    # ── Fase 3: String Matching ───────────────────────────────
    print("\n[3] STRING MATCHING — Soluzione 1")
    print("    (matching nomi job DB → label O*NET)\n")
    matching_results = run_string_matching()

    # ── Arricchimento grafo ───────────────────────────────────
    print("\n[4] ARRICCHIMENTO GRAFO")
    g_final = enrich_graph_with_matching(g_r2rml, matching_results)
    save_graph(g_final, "rientra_final")

    # ── Confronto finale ──────────────────────────────────────
    print("\n[5] CONFRONTO: Direct Mapping vs R2RML")
    print()
    print("    Direct Mapping — classi generate:")
    dm_classes = set(g_direct.objects(predicate=RDF.type))
    for c in sorted(dm_classes, key=str):
        n = len(list(g_direct.subjects(RDF.type, c)))
        print(f"      {str(c).split('/')[-1]:30s}  ({n} individui)")

    print()
    print("    R2RML Mapping — classi generate:")
    r2rml_classes = {
        o for s, p, o in g_r2rml
        if p == RDF.type and str(o).startswith("https://www.stiima.cnr.it/rientra#")
        and str(o).split("#")[1][0].isupper()
    }
    for c in sorted(r2rml_classes, key=str):
        n = len(list(g_r2rml.subjects(RDF.type, c)))
        print(f"      {str(c).split('#')[-1]:30s}  ({n} individui)")

    print()
    print("=" * 60)
    print("  Step 1 completato.")
    print(f"  Output salvato in: {os.path.abspath(OUTPUT_DIR)}/")
    print("  File prodotti:")
    print("    - direct_mapping.ttl / .rdf   (Direct Mapping grezzo)")
    print("    - r2rml_mapping.ttl / .rdf    (R2RML verso Rientra@)")
    print("    - rientra_final.ttl / .rdf    (R2RML + String Matching)")
    print()
    print("  Prossimo step: Soluzione 2 — NLP con sentence-transformers")
    print("=" * 60)


if __name__ == "__main__":
    main()
