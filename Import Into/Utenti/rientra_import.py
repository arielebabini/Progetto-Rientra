"""
rientra_import.py  —  Rientr@ Import Tool  (Strada B: RDB2RDF)
==============================================================
Pipeline conforme W3C RDB2RDF.

Tabelle SQL sorgente:
  person          → FOAF:Person + Health_Condition
  hc_descriptor   → HC:HC_Descriptor  (codici ICF b/d/s)
  job_evaluation  → isEvaluatedForJob  (job già presenti nell'ontologia)

Uso:
  # Genera il mapping R2RML dall'ontologia
  python rientra_import.py --generate-mapping --ontology Rientra.rdf

  # Import pazienti + job
  python rientra_import.py --ontology Rientra.rdf --dataset dataset_import.sql
  python rientra_import.py --ontology Rientra.rdf --dataset dataset_import.sql --output Rientra_v2.rdf
"""

import argparse
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import morph_kgc
from rdflib import Graph, URIRef, Namespace, Literal
from rdflib.namespace import RDF, OWL, RDFS, XSD

# ── Namespace ─────────────────────────────────────────────────────────────────
NS_FOAF   = Namespace("http://www.stiima.cnr.it/FOAF-excerpt#")
NS_HC     = Namespace("http://www.stiima.cnr.it/RientraHC#")
NS_ICF    = Namespace("http://www.stiima.cnr.it/ICF-exc-coreset#")
NS_PERSON = Namespace("http://www.stiima.cnr.it/Person-CommonBox#")
NS_RIE    = Namespace("http://www.stiima.cnr.it/RientraOnt3Merged#")
NS_JOB    = Namespace("http://www.stiima.cnr.it/JobList#")
NS_RIEONT3 = Namespace("http://www.stiima.cnr.it/RientraOnt3#")

CLOSING_TAG   = "</rdf:RDF>"
QUALIFIER_MAP = {"b": "BFqual", "d": "AP1qual", "s": "BS1qual"}
DEFAULT_MAPPING = Path(__file__).parent / "rientra_mapping.ttl"


# ══════════════════════════════════════════════════════════════════════════════
#  GENERATORE MAPPING R2RML
# ══════════════════════════════════════════════════════════════════════════════

def generate_mapping(ontology_path: str, mapping_out: str) -> None:
    """
    Analizza l'ontologia OWL e genera automaticamente il file R2RML (.ttl).
    Rieseguire solo se la struttura dell'ontologia cambia.
    """
    print(f"\n{'='*60}")
    print(f"  Rientr@ — Generatore Mapping R2RML")
    print(f"  Ontologia : {ontology_path}")
    print(f"  Output    : {mapping_out}")
    print(f"{'='*60}\n")

    print("[1/3] Parsing ontologia...")
    g = Graph()
    g.parse(ontology_path, format="xml")
    print(f"      {len(g)} triple caricate.\n")

    print("[2/3] Analisi proprietà...")

    foaf_person   = NS_FOAF.Person
    plain_props   = {}
    typed_props   = {}
    boolean_props = {}
    XSD_PLAIN = {str(XSD.string), str(XSD.anyURI)}

    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        domain = next(g.objects(prop, RDFS.domain), None)
        range_ = next(g.objects(prop, RDFS.range), None)
        if str(domain) != str(foaf_person):
            continue
        prop_name = str(prop).split("#")[-1]
        range_str = str(range_) if range_ else str(XSD.string)
        if range_str == str(XSD.boolean):
            boolean_props[prop_name] = prop
        elif range_str in XSD_PLAIN or range_ is None:
            plain_props[prop_name] = prop
        else:
            typed_props[prop_name] = (str(range_).split("#")[-1], prop)

    # qualifier properties da HC_Descriptor
    qualifier_props = {}
    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        domain = next(g.objects(prop, RDFS.domain), None)
        if str(domain) != str(NS_HC.HC_Descriptor):
            continue
        prop_name = str(prop).split("#")[-1]
        range_ = next(g.objects(prop, RDFS.range), None)
        qualifier_props[prop_name] = str(range_).split("#")[-1] if range_ else "integer"

    # job validi nell'ontologia (individui sottoclasse di Job)
    known_jobs = set()
    for subclass in g.subjects(RDFS.subClassOf, NS_JOB.Job):
        for ind in g.subjects(RDF.type, subclass):
            known_jobs.add(str(ind).split("#")[1])

    print(f"      Plain props     : {sorted(plain_props)}")
    print(f"      Typed props     : {sorted(typed_props)}")
    print(f"      Boolean props   : {sorted(boolean_props)}")
    print(f"      Qualifier props : {sorted(qualifier_props)}")
    print(f"      Job noti        : {len(known_jobs)}\n")

    print("[3/3] Generazione Turtle...")
    lines = []
    lines.append(f"""\
###############################################################
#  rientra_mapping.ttl  —  Rientr@ R2RML Mapping
#  GENERATO AUTOMATICAMENTE da rientra_import.py
#  Ontologia: {Path(ontology_path).name}
#  Standard W3C R2RML: https://www.w3.org/TR/r2rml/
#
#  Rigenera con:
#    python rientra_import.py --generate-mapping --ontology {Path(ontology_path).name}
###############################################################

@prefix rr:    <http://www.w3.org/ns/r2rml#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix foaf:  <http://www.stiima.cnr.it/FOAF-excerpt#> .
@prefix hc:    <http://www.stiima.cnr.it/RientraHC#> .
@prefix icf:   <http://www.stiima.cnr.it/ICF-exc-coreset#> .
@prefix pcb:   <http://www.stiima.cnr.it/Person-CommonBox#> .
@prefix rie:   <http://www.stiima.cnr.it/RientraOnt3Merged#> .
@prefix job:   <http://www.stiima.cnr.it/JobList#> .
@prefix rieont3: <http://www.stiima.cnr.it/RientraOnt3#> .
""")

    # MAP 1 — person → FOAF:Person
    lines.append("""\
# ─────────────────────────────────────────────────────────────
#  MAP 1 — person → FOAF:Person
# ─────────────────────────────────────────────────────────────
<#PersonMap>
    rr:logicalTable [ rr:tableName "person" ] ;
    rr:subjectMap [
        rr:template "http://www.stiima.cnr.it/Person-CommonBox#{person_id}" ;
        rr:class foaf:Person ;
        rr:class owl:NamedIndividual
    ] ;
""")
    for prop_name, prop_iri in sorted(plain_props.items()):
        col = "zip_code" if prop_name == "ZIPcode" else prop_name
        lines.append(f"""\
    rr:predicateObjectMap [
        rr:predicate <{prop_iri}> ;
        rr:objectMap [ rr:column "{col}" ]
    ] ;
""")
    for prop_name, (xsd_type, prop_iri) in sorted(typed_props.items()):
        col = "zip_code" if prop_name == "ZIPcode" else prop_name
        lines.append(f"""\
    rr:predicateObjectMap [
        rr:predicate <{prop_iri}> ;
        rr:objectMap [ rr:column "{col}" ; rr:datatype xsd:{xsd_type} ]
    ] ;
""")
    for prop_name, prop_iri in sorted(boolean_props.items()):
        lines.append(f"""\
    rr:predicateObjectMap [
        rr:predicate <{prop_iri}> ;
        rr:objectMap [ rr:constant "false"^^xsd:boolean ]
    ] ;
""")
    lines.append("""\
    rr:predicateObjectMap [
        rr:predicate hc:isInHealthCondition ;
        rr:objectMap [
            rr:template "http://www.stiima.cnr.it/Person-CommonBox#HC{person_id}" ;
            rr:termType rr:IRI
        ]
    ] .

""")

    # MAP 2 — person → Health_Condition
    lines.append("""\
# ─────────────────────────────────────────────────────────────
#  MAP 2 — person → HC:Health_Condition
# ─────────────────────────────────────────────────────────────
<#HealthConditionMap>
    rr:logicalTable [ rr:tableName "person" ] ;
    rr:subjectMap [
        rr:template "http://www.stiima.cnr.it/Person-CommonBox#HC{person_id}" ;
        rr:class hc:Health_Condition ;
        rr:class owl:NamedIndividual
    ] .

""")

    # MAP 3 — hc_descriptor → HC_Descriptor (una per prefisso)
    lines.append("""\
# ─────────────────────────────────────────────────────────────
#  MAP 3 — hc_descriptor → HC:HC_Descriptor (per prefisso ICF)
# ─────────────────────────────────────────────────────────────
""")
    for prefix, qual_prop in sorted(QUALIFIER_MAP.items()):
        xsd_type = qualifier_props.get(qual_prop, "integer")
        lines.append(f"""\
<#DescriptorMap{prefix.upper()}>
    rr:logicalTable [ rr:tableName "v_desc_{prefix}" ] ;
    rr:subjectMap [
        rr:template "http://www.stiima.cnr.it/RientraHC#des_{{person_id}}_{{icf_code}}" ;
        rr:class hc:HC_Descriptor ;
        rr:class owl:NamedIndividual
    ] ;
    rr:predicateObjectMap [
        rr:predicate hc:involvesICFCode ;
        rr:objectMap [
            rr:template "http://www.stiima.cnr.it/ICF-exc-coreset#{{icf_code}}" ;
            rr:termType rr:IRI
        ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate hc:{qual_prop} ;
        rr:objectMap [ rr:column "qualifier" ; rr:datatype xsd:{xsd_type} ]
    ] .

""")

    # MAP 4 — isDescribedBy
    lines.append("""\
# ─────────────────────────────────────────────────────────────
#  MAP 4 — v_hc_links → isDescribedBy
# ─────────────────────────────────────────────────────────────
<#DescriptorLinkMap>
    rr:logicalTable [ rr:tableName "v_hc_links" ] ;
    rr:subjectMap [
        rr:template "http://www.stiima.cnr.it/Person-CommonBox#HC{person_id}" ;
        rr:termType rr:IRI
    ] ;
    rr:predicateObjectMap [
        rr:predicate hc:isDescribedBy ;
        rr:objectMap [
            rr:template "http://www.stiima.cnr.it/RientraHC#des_{person_id}_{icf_code}" ;
            rr:termType rr:IRI
        ]
    ] .

""")

    # MAP 5 — job_evaluation → isEvaluatedForJob
    lines.append("""\
# ─────────────────────────────────────────────────────────────
#  MAP 5 — job_evaluation → isEvaluatedForJob
#  Collega Person ai Job già presenti nell'ontologia.
#  Solo job presenti nella VIEW v_job_valid (filtra job sconosciuti).
# ─────────────────────────────────────────────────────────────
<#JobEvaluationMap>
    rr:logicalTable [ rr:tableName "v_job_valid" ] ;
    rr:subjectMap [
        rr:template "http://www.stiima.cnr.it/Person-CommonBox#{person_id}" ;
        rr:termType rr:IRI
    ] ;
    rr:predicateObjectMap [
        rr:predicate <http://www.stiima.cnr.it/RientraOnt3#isEvaluatedForJob> ;
        rr:objectMap [
            rr:template "http://www.stiima.cnr.it/JobList#{job_id}" ;
            rr:termType rr:IRI
        ]
    ] .
""")

    Path(mapping_out).write_text("\n".join(lines), encoding="utf-8")
    print(f"      Salvato: {mapping_out}")
    print(f"\n{'='*60}")
    print(f"  Mapping generato: 5 TriplesMap")
    print(f"  Job noti nell'ontologia: {len(known_jobs)}")
    print(f"{'='*60}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  PIPELINE DI IMPORT
# ══════════════════════════════════════════════════════════════════════════════

def sanitize_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name)


def load_dataset(sql_path: str) -> sqlite3.Connection:
    sql = Path(sql_path).read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(sql)
    except sqlite3.Error as e:
        print(f"ERRORE SQL: {e}"); sys.exit(1)
    return conn


def extract_known_icf(rdf_text: str) -> set[str]:
    prefix = "http://www.stiima.cnr.it/ICF-exc-coreset#"
    return set(re.findall(rf'{re.escape(prefix)}([A-Za-z0-9_\-]+)', rdf_text))


def extract_known_jobs(ontology_path: str) -> set[str]:
    """
    Estrae i job_id degli individui Job presenti nell'ontologia
    (sottoclassi di JobList:Job) tramite rdflib — preciso, non regex.
    """
    g = Graph()
    g.parse(ontology_path, format="xml")
    known = set()
    for subclass in g.subjects(RDFS.subClassOf, NS_JOB.Job):
        for ind in g.subjects(RDF.type, subclass):
            known.add(str(ind).split("#")[-1])
    return known


def person_exists(rdf_text: str, person_id: str) -> bool:
    return f"http://www.stiima.cnr.it/Person-CommonBox#{person_id}" in rdf_text


def create_views(conn: sqlite3.Connection, known_icf: set[str],
                 known_jobs: set[str]) -> tuple[int, int, int, int]:
    """Crea le VIEW ausiliarie per il mapping R2RML."""
    # Tabella codici ICF noti
    conn.execute("DROP TABLE IF EXISTS _known_icf")
    conn.execute("CREATE TABLE _known_icf (icf_code TEXT PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO _known_icf VALUES (?)",
                     [(c,) for c in known_icf])

    # Tabella job noti
    conn.execute("DROP TABLE IF EXISTS _known_jobs")
    conn.execute("CREATE TABLE _known_jobs (job_id TEXT PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO _known_jobs VALUES (?)",
                     [(j,) for j in known_jobs])

    # VIEW descrittori per prefisso ICF
    for view, prefix in [("v_desc_b","b"), ("v_desc_d","d"), ("v_desc_s","s")]:
        conn.execute(f"DROP VIEW IF EXISTS {view}")
        conn.execute(f"""
            CREATE VIEW {view} AS
            SELECT h.person_id, h.icf_code, h.qualifier
            FROM hc_descriptor h
            JOIN _known_icf k ON k.icf_code = h.icf_code
            WHERE lower(substr(h.icf_code,1,1)) = '{prefix}'
        """)
    conn.execute("DROP VIEW IF EXISTS v_hc_links")
    conn.execute("""
        CREATE VIEW v_hc_links AS
        SELECT person_id, icf_code FROM v_desc_b
        UNION ALL SELECT person_id, icf_code FROM v_desc_d
        UNION ALL SELECT person_id, icf_code FROM v_desc_s
    """)

    # VIEW job validi (filtra job non presenti nell'ontologia)
    # La tabella job_evaluation è opzionale: se non esiste, la view è vuota
    try:
        conn.execute("DROP VIEW IF EXISTS v_job_valid")
        conn.execute("""
            CREATE VIEW v_job_valid AS
            SELECT j.person_id, j.job_id
            FROM job_evaluation j
            JOIN _known_jobs k ON k.job_id = j.job_id
        """)
        total_jobs = conn.execute("SELECT COUNT(*) FROM job_evaluation").fetchone()[0]
        valid_jobs = conn.execute("SELECT COUNT(*) FROM v_job_valid").fetchone()[0]
    except sqlite3.Error:
        # Tabella job_evaluation non presente nel dataset
        conn.execute("DROP VIEW IF EXISTS v_job_valid")
        conn.execute("CREATE VIEW v_job_valid AS SELECT NULL AS person_id, NULL AS job_id WHERE 0")
        total_jobs, valid_jobs = 0, 0

    total_icf = conn.execute("SELECT COUNT(*) FROM hc_descriptor").fetchone()[0]
    valid_icf = conn.execute("SELECT COUNT(*) FROM v_hc_links").fetchone()[0]
    return valid_icf, total_icf - valid_icf, valid_jobs, total_jobs - valid_jobs


def export_db_to_file(conn: sqlite3.Connection) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    disk = sqlite3.connect(tmp.name)
    for line in conn.iterdump():
        try: disk.execute(line)
        except sqlite3.Error: pass
    disk.commit(); disk.close()
    return tmp.name


def run_r2rml(mapping_path: str, db_file: str) -> Graph:
    config = f"""
[CONFIGURATION]
output_format=N-TRIPLES

[RientraDataSource]
mappings={mapping_path}
db_url=sqlite:///{db_file}
"""
    return morph_kgc.materialize(config)


def triples_to_rdfxml_blocks(new_graph: Graph, persons_to_add: set[str]) -> list[str]:
    """
    Converte le triple materializzate in blocchi RDF/XML.
    Iniettati testualmente senza re-serializzare l'ontologia.
    """
    IS_EVAL = NS_RIEONT3.isEvaluatedForJob
    blocks = []

    for person_id in sorted(persons_to_add):
        p_iri   = URIRef(str(NS_PERSON) + person_id)
        hc_iri  = URIRef(str(NS_PERSON) + "HC" + person_id)
        hc_frag = "HC" + person_id

        # ── HC_Descriptor blocks ─────────────────────────────────────────────
        for _, _, desc_iri in new_graph.triples((hc_iri, NS_HC.isDescribedBy, None)):
            desc_id   = str(desc_iri).replace(str(NS_HC), "")
            icf_iri   = next(new_graph.objects(desc_iri, NS_HC.involvesICFCode), None)
            if icf_iri is None: continue
            icf_code  = str(icf_iri).replace(str(NS_ICF), "")
            prefix    = icf_code[0].lower() if icf_code else "b"
            qual_prop = QUALIFIER_MAP.get(prefix, "BFqual")
            qual_val  = next(new_graph.objects(desc_iri, getattr(NS_HC, qual_prop)), None)
            if qual_val is None: continue
            blocks.append(
                f'    <owl:NamedIndividual rdf:about="{NS_HC}{desc_id}">\n'
                f'        <rdf:type rdf:resource="{NS_HC}HC_Descriptor"/>\n'
                f'        <RientraHC:involvesICFCode rdf:resource="{NS_ICF}{icf_code}"/>\n'
                f'        <RientraHC:{qual_prop} rdf:datatype="{XSD}integer">'
                f'{qual_val}</RientraHC:{qual_prop}>\n'
                f'    </owl:NamedIndividual>'
            )

        # ── Health_Condition block ───────────────────────────────────────────
        desc_lines = "\n".join(
            f'        <RientraHC:isDescribedBy rdf:resource="{d}"/>'
            for _, _, d in new_graph.triples((hc_iri, NS_HC.isDescribedBy, None))
        )
        blocks.append(
            f'    <owl:NamedIndividual rdf:about="{NS_PERSON}{hc_frag}">\n'
            f'        <rdf:type rdf:resource="{NS_HC}Health_Condition"/>\n'
            f'{desc_lines}\n'
            f'    </owl:NamedIndividual>'
        )

        # ── Person block ─────────────────────────────────────────────────────
        prop_lines = []
        FOAF_PLAIN = {
            NS_FOAF.first_name: "FOAF-excerpt:first_name",
            NS_FOAF.surname:    "FOAF-excerpt:surname",
            NS_FOAF.TIN:        "FOAF-excerpt:TIN",
            NS_FOAF.city:       "FOAF-excerpt:city",
            NS_FOAF.country:    "FOAF-excerpt:country",
        }
        FOAF_TYPED = {
            NS_FOAF.birthday: ("FOAF-excerpt:birthday", f"{XSD}dateTime"),
            NS_FOAF.ZIPcode:  ("FOAF-excerpt:ZIPcode",  f"{XSD}int"),
        }
        for pred, tag in FOAF_PLAIN.items():
            val = next(new_graph.objects(p_iri, pred), None)
            if val:
                prop_lines.append(f'        <{tag}>{xml_escape(str(val))}</{tag}>')
        for pred, (tag, dtype) in FOAF_TYPED.items():
            val = next(new_graph.objects(p_iri, pred), None)
            if val:
                prop_lines.append(
                    f'        <{tag} rdf:datatype="{dtype}">{xml_escape(str(val))}</{tag}>')

        # isEvaluatedForJob — uno per ogni job assegnato
        for _, _, job_iri in new_graph.triples((p_iri, IS_EVAL, None)):
            prop_lines.append(
                f'        <RientraOnt3:isEvaluatedForJob rdf:resource="{job_iri}"/>'
            )

        # isSelected — scritto come nell'ontologia originale
        prop_lines.append(
            f'        <isSelected rdf:datatype="{XSD}boolean">false</isSelected>'
        )

        blocks.append(
            f'    <!-- Person: {person_id} -->\n'
            f'    <owl:NamedIndividual rdf:about="{NS_PERSON}{person_id}">\n'
            f'        <rdf:type rdf:resource="{NS_FOAF}Person"/>\n'
            f'        <RientraHC:isInHealthCondition rdf:resource="{NS_PERSON}{hc_frag}"/>\n'
            + "\n".join(prop_lines) + "\n"
            f'    </owl:NamedIndividual>'
        )

    return blocks


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Rientr@ Import Tool (RDB2RDF via R2RML)")
    parser.add_argument("--ontology",         required=True)
    parser.add_argument("--generate-mapping", action="store_true",
                        help="Genera rientra_mapping.ttl dall'ontologia ed esce")
    parser.add_argument("--dataset",          default=None)
    parser.add_argument("--output",           default=None)
    parser.add_argument("--mapping",          default=str(DEFAULT_MAPPING))
    args = parser.parse_args()

    # ── Modalità: genera mapping ──────────────────────────────────────────────
    if args.generate_mapping:
        generate_mapping(args.ontology, args.mapping)
        return

    # ── Modalità: import ──────────────────────────────────────────────────────
    if not args.dataset:
        parser.error("--dataset è richiesto per l'import")
    if not Path(args.mapping).exists():
        print(f"\nERRORE: Mapping R2RML non trovato: {args.mapping}")
        print(f"Generalo con:")
        print(f"  python rientra_import.py --generate-mapping --ontology {args.ontology}\n")
        sys.exit(1)

    out_path = args.output or args.ontology

    print(f"\n{'='*60}")
    print(f"  Rientr@ Import Tool  —  RDB2RDF (R2RML via Morph-KGC)")
    print(f"  Ontologia : {args.ontology}")
    print(f"  Dataset   : {args.dataset}")
    print(f"  Mapping   : {args.mapping}")
    print(f"  Output    : {out_path}")
    print(f"{'='*60}\n")

    print("[1/6] Caricamento dataset SQL in SQLite...")
    conn = load_dataset(args.dataset)
    n_persons = conn.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    print(f"      {n_persons} persona/e trovata/e.\n")

    print("[2/6] Lettura ontologia (testo grezzo)...")
    rdf_text = Path(args.ontology).read_text(encoding="utf-8")
    print(f"      {len(rdf_text.splitlines())} righe.\n")

    known_icf   = extract_known_icf(rdf_text)
    known_jobs  = extract_known_jobs(args.ontology)
    all_persons = conn.execute("SELECT person_id FROM person").fetchall()
    new_person_ids = [
        sanitize_id(r["person_id"]) for r in all_persons
        if not person_exists(rdf_text, sanitize_id(r["person_id"]))
    ]
    skipped = [
        sanitize_id(r["person_id"]) for r in all_persons
        if person_exists(rdf_text, sanitize_id(r["person_id"]))
    ]
    print(f"      Codici ICF noti : {len(known_icf)}")
    print(f"      Job noti        : {len(known_jobs)}")
    print(f"      Nuove persone   : {len(new_person_ids)}")
    if skipped:
        print(f"      [SKIP] già presenti: {skipped}")
    print()

    print("[3/6] Creazione VIEW ausiliarie per R2RML...")
    n_icf_ok, n_icf_skip, n_job_ok, n_job_skip = create_views(conn, known_icf, known_jobs)
    print(f"      Descrittori ICF validi : {n_icf_ok}  |  Ignorati: {n_icf_skip}")
    print(f"      Job validi             : {n_job_ok}  |  Ignorati: {n_job_skip}\n")

    print("[4/6] Materializzazione R2RML con Morph-KGC...")
    db_file = export_db_to_file(conn)
    try:
        new_graph = run_r2rml(args.mapping, db_file)
    finally:
        Path(db_file).unlink(missing_ok=True)
    print(f"      Triple materializzate: {len(new_graph)}\n")

    print("[5/6] Conversione triple → blocchi RDF/XML...")
    blocks = triples_to_rdfxml_blocks(new_graph, set(new_person_ids))
    IS_EVAL = NS_RIEONT3.isEvaluatedForJob
    for pid in sorted(new_person_ids):
        p_iri  = URIRef(str(NS_PERSON) + pid)
        hc_iri = URIRef(str(NS_PERSON) + "HC" + pid)
        n_desc = len(list(new_graph.triples((hc_iri, NS_HC.isDescribedBy, None))))
        n_jobs = len(list(new_graph.triples((p_iri, IS_EVAL, None))))
        print(f"  [OK]   {pid} → {n_desc} descrittori ICF, {n_jobs} job")
    print(f"\n      Blocchi XML da iniettare: {len(blocks)}\n")

    print("[6/6] Iniezione nel file RDF originale...")
    backup = out_path + ".bak"
    shutil.copy2(args.ontology, backup)
    print(f"      Backup: {backup}")

    if blocks:
        if CLOSING_TAG not in rdf_text:
            print("ERRORE: </rdf:RDF> non trovato."); sys.exit(1)
        injection = (
            "\n\n\n    <!-- ===== PAZIENTI IMPORTATI (RDB2RDF via R2RML) ===== -->\n\n"
            + "\n\n".join(blocks) + "\n\n"
        )
        updated = rdf_text.replace(CLOSING_TAG, injection + CLOSING_TAG, 1)
        Path(out_path).write_text(updated, encoding="utf-8")
    else:
        print("      Nessuna nuova persona da inserire.")
        if out_path != args.ontology:
            shutil.copy2(args.ontology, out_path)

    print(f"\n{'='*60}")
    print(f"  Salvato: {out_path}")
    print(f"{'='*60}")
    print(f"""
  RIEPILOGO
  ─────────────────────────────────
  Persone inserite       : {len(new_person_ids)}
  Persone già presenti   : {len(skipped)}
  Descrittori ICF validi : {n_icf_ok}
  Codici ICF ignorati    : {n_icf_skip}
  Job associati          : {n_job_ok}
  Job ignorati           : {n_job_skip}
  Backup                 : {backup}
  ─────────────────────────────────
""")
    conn.close()


if __name__ == "__main__":
    main()
