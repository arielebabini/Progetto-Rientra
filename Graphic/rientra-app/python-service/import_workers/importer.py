"""
importer.py
───────────
Rientr@ RDB2RDF Import Pipeline — library version.

Adapted from rientra_import.py (Union folder) so it can be called
programmatically from the FastAPI service instead of the CLI.

Public API
----------
ensure_mapping(ontology_path, mapping_path)
    Generate rientra_mapping.ttl if missing or outdated.

import_sql_dataset(sql_path, ontology_path, mapping_path) -> ImportResult
    Parse an SQL dataset, run R2RML materialisation, inject new
    Person + HealthCondition individuals into the RDF file.

The ontology file is modified **in place** (with a .bak backup).
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from xml.sax.saxutils import escape as xml_escape

logger = logging.getLogger(__name__)

# ── Optional heavy imports (morph_kgc / rdflib) ──────────────────────────────
# _SAFE_ANY is used as a stub type for names that may not be imported.
# Pyrefly treats Any as compatible with all operations (call, subscript,
# attribute access), so no further errors propagate from these stubs.
_SAFE_ANY: Any = None

try:
    import morph_kgc
    from rdflib import Graph, URIRef, Namespace
    from rdflib.namespace import RDF, OWL, RDFS, XSD
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False
    # These names are never used at runtime when _DEPS_OK is False — every
    # function that needs them guards with `if not _DEPS_OK: raise RuntimeError`.
    # Typed as Any so that Pyrefly accepts calling / attribute-access on them.
    morph_kgc: Any = _SAFE_ANY  # type: ignore[no-redef]
    Graph:     Any = _SAFE_ANY  # type: ignore[no-redef]
    URIRef:    Any = _SAFE_ANY  # type: ignore[no-redef]
    Namespace: Any = _SAFE_ANY  # type: ignore[no-redef]
    RDF:       Any = _SAFE_ANY  # type: ignore[no-redef]
    OWL:       Any = _SAFE_ANY  # type: ignore[no-redef]
    RDFS:      Any = _SAFE_ANY  # type: ignore[no-redef]
    XSD:       Any = _SAFE_ANY  # type: ignore[no-redef]
    logger.warning(
        "morph_kgc or rdflib not installed — import pipeline unavailable. "
        "Run: pip install morph-kgc rdflib"
    )

# ── Namespaces ────────────────────────────────────────────────────────────────
# Always assigned; fall back to _SAFE_ANY when deps are missing so that
# Pyrefly sees these names as unconditionally bound in all branches.
if _DEPS_OK:
    NS_FOAF    = Namespace("http://www.stiima.cnr.it/FOAF-excerpt#")
    NS_HC      = Namespace("http://www.stiima.cnr.it/RientraHC#")
    NS_ICF     = Namespace("http://www.stiima.cnr.it/ICF-exc-coreset#")
    NS_PERSON  = Namespace("http://www.stiima.cnr.it/Person-CommonBox#")
    NS_JOB     = Namespace("http://www.stiima.cnr.it/JobList#")
    NS_RIEONT3 = Namespace("http://www.stiima.cnr.it/RientraOnt3#")
else:
    NS_FOAF = NS_HC = NS_ICF = NS_PERSON = NS_JOB = NS_RIEONT3 = _SAFE_ANY


CLOSING_TAG   = "</rdf:RDF>"
QUALIFIER_MAP = {"b": "BFqual", "d": "AP1qual", "s": "BS1qual"}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ImportResult:
    """Summary returned to the FastAPI endpoint after a successful import."""
    persons_added:    int = 0
    persons_skipped:  int = 0
    icf_valid:        int = 0
    icf_skipped:      int = 0
    jobs_valid:       int = 0
    jobs_skipped:     int = 0
    backup_path:      str = ""
    new_person_ids:   list[str] = field(default_factory=list)
    skipped_ids:      list[str] = field(default_factory=list)
    error:            Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
#  MAPPING GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def ensure_mapping(ontology_path: str, mapping_path: str) -> None:
    """
    Generate rientra_mapping.ttl from the ontology if it does not exist yet.
    Safe to call on every startup: if the file already exists it is a no-op.
    Raises RuntimeError if deps are missing or ontology cannot be parsed.
    """
    if not _DEPS_OK:
        raise RuntimeError(
            "morph-kgc / rdflib are not installed. "
            "Run: pip install morph-kgc rdflib"
        )

    mapping = Path(mapping_path)
    if mapping.exists():
        logger.info("[importer] Mapping file already exists: %s", mapping)
        return

    logger.info("[importer] Generating mapping from ontology: %s", ontology_path)
    _generate_mapping(ontology_path, mapping_path)
    logger.info("[importer] Mapping written to: %s", mapping_path)


def _generate_mapping(ontology_path: str, mapping_out: str) -> None:
    """Internal: parse the ontology and write an R2RML .ttl mapping."""
    g = Graph()
    g.parse(ontology_path, format="xml")

    foaf_person   = NS_FOAF.Person
    plain_props:   dict = {}
    typed_props:   dict = {}
    boolean_props: dict = {}
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

    qualifier_props: dict = {}
    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        domain = next(g.objects(prop, RDFS.domain), None)
        if str(domain) != str(NS_HC.HC_Descriptor):
            continue
        prop_name = str(prop).split("#")[-1]
        range_ = next(g.objects(prop, RDFS.range), None)
        qualifier_props[prop_name] = str(range_).split("#")[-1] if range_ else "integer"

    lines = []
    lines.append(f"""\
###############################################################
#  rientra_mapping.ttl  —  Rientr@ R2RML Mapping
#  GENERATED AUTOMATICALLY by importer.py
#  Ontologia: {Path(ontology_path).name}
#  W3C R2RML: https://www.w3.org/TR/r2rml/
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
<#HealthConditionMap>
    rr:logicalTable [ rr:tableName "person" ] ;
    rr:subjectMap [
        rr:template "http://www.stiima.cnr.it/Person-CommonBox#HC{person_id}" ;
        rr:class hc:Health_Condition ;
        rr:class owl:NamedIndividual
    ] .

""")

    # MAP 3 — hc_descriptor → HC_Descriptor (one per ICF prefix)
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

    Path(mapping_out).parent.mkdir(parents=True, exist_ok=True)
    Path(mapping_out).write_text("\n".join(lines), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
#  IMPORT PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def _sanitize_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name)


def _load_sql(sql_path: str) -> sqlite3.Connection:
    sql = Path(sql_path).read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(sql)
    return conn


def _extract_known_icf(rdf_text: str) -> set[str]:
    prefix = "http://www.stiima.cnr.it/ICF-exc-coreset#"
    return set(re.findall(rf'{re.escape(prefix)}([A-Za-z0-9_\-]+)', rdf_text))


def _extract_known_jobs(ontology_path: str) -> set[str]:
    """
    Extract all valid job IDs from the ontology.

    Jobs in this ontology use a metaclass/punning pattern:
    they are declared as owl:Class AND have rdf:type JobList#Job.
    The old approach (looking for subClassOf Job individuals) returned
    an empty set, causing all job evaluation links to be skipped.

    Strategy (most-to-least reliable):
      1. Any resource typed as JobList#Job (covers both classes and individuals)
      2. Any subject of a JobList#requires triple (fallback)
    """
    g = Graph()
    g.parse(ontology_path, format="xml")
    known: set[str] = set()

    # Pattern 1: rdf:type JobList#Job  (covers the metaclass/punning pattern)
    for entity in g.subjects(RDF.type, NS_JOB.Job):
        job_id = str(entity).split("#")[-1]
        if job_id and job_id != "Job":
            known.add(job_id)

    # Pattern 2: subClassOf JobList#Job (standard OWL hierarchy, kept as fallback)
    for subclass in g.subjects(RDFS.subClassOf, NS_JOB.Job):
        for ind in g.subjects(RDF.type, subclass):
            job_id = str(ind).split("#")[-1]
            if job_id:
                known.add(job_id)

    # Pattern 3: any subject of a requires triple in the JobList namespace
    JOB_REQUIRES = NS_JOB.requires
    for job in g.subjects(JOB_REQUIRES, None):
        job_id = str(job).split("#")[-1]
        if job_id:
            known.add(job_id)

    return known


def _person_exists(rdf_text: str, person_id: str) -> bool:
    return f"http://www.stiima.cnr.it/Person-CommonBox#{person_id}" in rdf_text


def _create_views(
    conn: sqlite3.Connection,
    known_icf: set[str],
    known_jobs: set[str],
) -> tuple[int, int, int, int]:
    conn.execute("DROP TABLE IF EXISTS _known_icf")
    conn.execute("CREATE TABLE _known_icf (icf_code TEXT PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO _known_icf VALUES (?)", [(c,) for c in known_icf])

    conn.execute("DROP TABLE IF EXISTS _known_jobs")
    conn.execute("CREATE TABLE _known_jobs (job_id TEXT PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO _known_jobs VALUES (?)", [(j,) for j in known_jobs])

    for view, prefix in [("v_desc_b", "b"), ("v_desc_d", "d"), ("v_desc_s", "s")]:
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
        conn.execute("DROP VIEW IF EXISTS v_job_valid")
        conn.execute("CREATE VIEW v_job_valid AS SELECT NULL AS person_id, NULL AS job_id WHERE 0")
        total_jobs, valid_jobs = 0, 0

    total_icf = conn.execute("SELECT COUNT(*) FROM hc_descriptor").fetchone()[0]
    valid_icf  = conn.execute("SELECT COUNT(*) FROM v_hc_links").fetchone()[0]
    return valid_icf, total_icf - valid_icf, valid_jobs, total_jobs - valid_jobs


def _export_db_to_file(conn: sqlite3.Connection) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    disk = sqlite3.connect(tmp.name)
    for line in conn.iterdump():
        try:
            disk.execute(line)
        except sqlite3.Error:
            pass
    disk.commit()
    disk.close()
    return tmp.name


def _run_r2rml(mapping_path: str, db_file: str) -> "Graph":
    config = f"""
[CONFIGURATION]
output_format=N-TRIPLES

[RientraDataSource]
mappings={mapping_path}
db_url=sqlite:///{db_file}
"""
    return morph_kgc.materialize(config)


def _triples_to_rdfxml_blocks(new_graph: "Graph", persons_to_add: set[str]) -> list[str]:
    IS_EVAL = NS_RIEONT3.isEvaluatedForJob
    blocks: list[str] = []

    for person_id in sorted(persons_to_add):
        p_iri  = URIRef(str(NS_PERSON) + person_id)
        hc_iri = URIRef(str(NS_PERSON) + "HC" + person_id)
        hc_frag = "HC" + person_id

        # HC_Descriptor blocks
        for _, _, desc_iri in new_graph.triples((hc_iri, NS_HC.isDescribedBy, None)):
            desc_id  = str(desc_iri).replace(str(NS_HC), "")
            icf_iri  = next(new_graph.objects(desc_iri, NS_HC.involvesICFCode), None)
            if icf_iri is None:
                continue
            icf_code  = str(icf_iri).replace(str(NS_ICF), "")
            prefix    = icf_code[0].lower() if icf_code else "b"
            qual_prop = QUALIFIER_MAP.get(prefix, "BFqual")
            qual_val  = next(new_graph.objects(desc_iri, getattr(NS_HC, qual_prop)), None)
            if qual_val is None:
                continue
            blocks.append(
                f'    <owl:NamedIndividual rdf:about="{NS_HC}{desc_id}">\n'
                f'        <rdf:type rdf:resource="{NS_HC}HC_Descriptor"/>\n'
                f'        <Rien3:involvesICFCode rdf:resource="{NS_ICF}{icf_code}"/>\n'
                f'        <Rien3:{qual_prop} rdf:datatype="{XSD}integer">'
                f'{qual_val}</Rien3:{qual_prop}>\n'
                f'    </owl:NamedIndividual>'
            )

        # Health_Condition block
        desc_lines = "\n".join(
            f'        <Rien3:isDescribedBy rdf:resource="{d}"/>'
            for _, _, d in new_graph.triples((hc_iri, NS_HC.isDescribedBy, None))
        )
        blocks.append(
            f'    <owl:NamedIndividual rdf:about="{NS_PERSON}{hc_frag}">\n'
            f'        <rdf:type rdf:resource="{NS_HC}Health_Condition"/>\n'
            f'{desc_lines}\n'
            f'    </owl:NamedIndividual>'
        )

        # Person block
        prop_lines: list[str] = []
        FOAF_PLAIN = {
            NS_FOAF.first_name: "FOAF:first_name",
            NS_FOAF.surname:    "FOAF:surname",
            NS_FOAF.TIN:        "FOAF:TIN",
            NS_FOAF.city:       "FOAF:city",
            NS_FOAF.country:    "FOAF:country",
        }
        FOAF_TYPED = {
            NS_FOAF.birthday: ("FOAF:birthday", f"{XSD}dateTime"),
            NS_FOAF.ZIPcode:  ("FOAF:ZIPcode",  f"{XSD}int"),
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

        for _, _, job_iri in new_graph.triples((p_iri, IS_EVAL, None)):
            prop_lines.append(
                f'        <Rien:isEvaluatedForJob rdf:resource="{job_iri}"/>'
            )
        prop_lines.append(
            f'        <Rien2:isSelected rdf:datatype="{XSD}boolean">false</Rien2:isSelected>'
        )

        blocks.append(
            f'    <!-- Person: {person_id} -->\n'
            f'    <owl:NamedIndividual rdf:about="{NS_PERSON}{person_id}">\n'
            f'        <rdf:type rdf:resource="{NS_FOAF}Person"/>\n'
            f'        <Rien3:isInHealthCondition rdf:resource="{NS_PERSON}{hc_frag}"/>\n'
            + "\n".join(prop_lines) + "\n"
            f'    </owl:NamedIndividual>'
        )

    return blocks


# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def import_sql_dataset(
    sql_path: str,
    ontology_path: str,
    mapping_path: str,
) -> ImportResult:
    """
    Full import pipeline:
      1. Load SQL dataset into in-memory SQLite
      2. Identify new/duplicate persons
      3. Create auxiliary VIEWs for R2RML
      4. Materialise triples with Morph-KGC
      5. Inject XML blocks into the RDF file (in place, with .bak backup)

    Returns an ImportResult summary. On any error, result.error is set.
    """
    if not _DEPS_OK:
        return ImportResult(
            error="morph-kgc / rdflib not installed. Run: pip install morph-kgc rdflib"
        )

    result = ImportResult()

    try:
        # 1. Load SQL
        conn = _load_sql(sql_path)
        all_persons = conn.execute("SELECT person_id FROM person").fetchall()

        # 2. Read ontology text + identify new persons
        rdf_text = Path(ontology_path).read_text(encoding="utf-8")
        known_icf  = _extract_known_icf(rdf_text)
        known_jobs = _extract_known_jobs(ontology_path)

        new_ids = [
            _sanitize_id(r["person_id"]) for r in all_persons
            if not _person_exists(rdf_text, _sanitize_id(r["person_id"]))
        ]
        skipped_ids = [
            _sanitize_id(r["person_id"]) for r in all_persons
            if _person_exists(rdf_text, _sanitize_id(r["person_id"]))
        ]
        result.new_person_ids  = new_ids
        result.skipped_ids     = skipped_ids
        result.persons_skipped = len(skipped_ids)

        if not new_ids:
            result.persons_added = 0
            conn.close()
            return result

        # 3. Create auxiliary views
        v_icf_ok, v_icf_skip, v_job_ok, v_job_skip = _create_views(
            conn, known_icf, known_jobs
        )
        result.icf_valid    = v_icf_ok
        result.icf_skipped  = v_icf_skip
        result.jobs_valid   = v_job_ok
        result.jobs_skipped = v_job_skip

        # 4. Materialise via R2RML
        db_file = _export_db_to_file(conn)
        try:
            new_graph = _run_r2rml(mapping_path, db_file)
        finally:
            Path(db_file).unlink(missing_ok=True)

        # 5. Convert triples → RDF/XML blocks
        blocks = _triples_to_rdfxml_blocks(new_graph, set(new_ids))

        # 6. Inject into the RDF file
        if CLOSING_TAG not in rdf_text:
            return ImportResult(error="</rdf:RDF> closing tag not found in ontology file.")

        backup = ontology_path + ".bak"
        shutil.copy2(ontology_path, backup)
        result.backup_path = backup

        injection = (
            "\n\n\n    <!-- ===== PERSONE IMPORTATE (RDB2RDF via R2RML) ===== -->\n\n"
            + "\n\n".join(blocks) + "\n\n"
        )
        updated = rdf_text.replace(CLOSING_TAG, injection + CLOSING_TAG, 1)
        Path(ontology_path).write_text(updated, encoding="utf-8")

        result.persons_added = len(new_ids)
        conn.close()

    except Exception as exc:
        logger.exception("[importer] Import failed")
        result.error = str(exc)

    return result
