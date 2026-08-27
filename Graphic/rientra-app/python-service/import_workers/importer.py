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


# ── Result and Validation dataclasses ────────────────────────────────────────

@dataclass
class ValidationErrorItem:
    """Represents a specific validation issue found in the imported SQL dataset."""
    category: str        # 'schema' | 'person' | 'health_condition' | 'job' | 'ontology_conflict'
    message: str         # Clear explanation of what is wrong
    person_id: Optional[str] = None
    field: Optional[str] = None
    value: Optional[str] = None
    fix_hint: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "message": self.message,
            "person_id": self.person_id,
            "field": self.field,
            "value": self.value,
            "fix_hint": self.fix_hint,
        }


@dataclass
class ImportResult:
    """Summary returned to the FastAPI endpoint after an import attempt."""
    persons_added:     int = 0
    persons_updated:   int = 0
    persons_skipped:   int = 0
    icf_valid:         int = 0
    icf_skipped:       int = 0
    jobs_valid:        int = 0
    jobs_skipped:      int = 0
    backup_path:       str = ""
    new_person_ids:    list[str] = field(default_factory=list)
    updated_ids:       list[str] = field(default_factory=list)
    skipped_ids:       list[str] = field(default_factory=list)
    details:           list[dict] = field(default_factory=list)
    validation_errors: list[dict] = field(default_factory=list)
    error:             Optional[str] = None


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

    # Ensure optional FOAF columns exist on person table with exact casing to avoid pandas/morph-kgc missing column dropna errors
    existing_person_cols_exact = {row[1] for row in conn.execute("PRAGMA table_info(person)").fetchall()}
    for opt_col, opt_type in [("TIN", "TEXT"), ("city", "TEXT"), ("country", "TEXT"), ("zip_code", "INT"), ("birthday", "TEXT")]:
        if opt_col not in existing_person_cols_exact:
            try:
                conn.execute(f'ALTER TABLE person ADD COLUMN "{opt_col}" {opt_type}')
            except Exception:
                pass

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
#  VALIDATION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def validate_sql_dataset(
    conn: sqlite3.Connection,
    rdf_text: str,
    known_icf: set[str],
    known_jobs: set[str],
) -> list[ValidationErrorItem]:
    """
    Rigorously validate an in-memory SQL dataset against ontology and domain rules:
      1. Schema & table presence (person, hc_descriptor, and optional job_evaluation).
      2. Required columns in each table.
      3. Person record validity, formatting, uniqueness, and ontology conflict detection.
      4. Health condition descriptors referential integrity, validity, qualifier range [0-4], and uniqueness.
      5. Job evaluation referential integrity, job existence in ontology, and uniqueness.
    """
    errors: list[ValidationErrorItem] = []
    cursor = conn.cursor()

    # 1. Check Tables Existence
    tables = {row[0].lower() for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    if "person" not in tables:
        errors.append(ValidationErrorItem(
            category="schema",
            field="table:person",
            message="Required table 'person' is missing in the SQL file.",
            fix_hint="Define the 'person' table with columns: person_id, first_name, surname."
        ))

    if "hc_descriptor" not in tables:
        errors.append(ValidationErrorItem(
            category="schema",
            field="table:hc_descriptor",
            message="Required table 'hc_descriptor' is missing in the SQL file.",
            fix_hint="Define the 'hc_descriptor' table with columns: person_id, icf_code, qualifier."
        ))

    if errors:
        return errors

    # 2. Check Column definitions for required tables
    person_cols = {row[1].lower() for row in cursor.execute("PRAGMA table_info(person)").fetchall()}
    for req in ["person_id", "first_name", "surname"]:
        if req not in person_cols:
            errors.append(ValidationErrorItem(
                category="schema",
                field=f"person.{req}",
                message=f"The 'person' table is missing required column '{req}'.",
                fix_hint=f"Add column '{req}' to the 'person' table definition."
            ))

    hc_cols = {row[1].lower() for row in cursor.execute("PRAGMA table_info(hc_descriptor)").fetchall()}
    for req in ["person_id", "icf_code", "qualifier"]:
        if req not in hc_cols:
            errors.append(ValidationErrorItem(
                category="schema",
                field=f"hc_descriptor.{req}",
                message=f"The 'hc_descriptor' table is missing required column '{req}'.",
                fix_hint=f"Add column '{req}' to the 'hc_descriptor' table definition."
            ))

    if "job_evaluation" in tables:
        job_cols = {row[1].lower() for row in cursor.execute("PRAGMA table_info(job_evaluation)").fetchall()}
        for req in ["person_id", "job_id"]:
            if req not in job_cols:
                errors.append(ValidationErrorItem(
                    category="schema",
                    field=f"job_evaluation.{req}",
                    message=f"The 'job_evaluation' table is missing required column '{req}'.",
                    fix_hint=f"Add column '{req}' to the 'job_evaluation' table."
                ))

    if errors:
        return errors

    # 3. Check Records in `person`
    persons = cursor.execute("SELECT * FROM person").fetchall()
    if not persons:
        errors.append(ValidationErrorItem(
            category="person",
            message="The 'person' table is empty. No workers to import.",
            fix_hint="Insert at least one record into the 'person' table."
        ))
        return errors

    seen_pids = set()
    valid_pids = set()

    for row in persons:
        pid = row["person_id"]
        fname = row["first_name"]
        sname = row["surname"]

        # Null / empty PID
        if pid is None or not str(pid).strip():
            errors.append(ValidationErrorItem(
                category="person",
                field="person_id",
                message="Found person record with empty or null 'person_id'.",
                fix_hint="Each person must have a non-empty unique identifier."
            ))
            continue

        raw_pid = str(pid).strip()
        sanitized_pid = _sanitize_id(raw_pid)

        # Invalid characters in PID (e.g. spaces, symbols)
        if not re.match(r"^[A-Za-z0-9_\-]+$", raw_pid):
            errors.append(ValidationErrorItem(
                category="person",
                person_id=raw_pid,
                field="person_id",
                value=raw_pid,
                message=f"Identifier '{raw_pid}' contains disallowed special characters or spaces.",
                fix_hint="Use only alphanumeric characters, dashes, and underscores for person_id."
            ))

        # Duplicate PID in the SQL file
        if sanitized_pid in seen_pids:
            errors.append(ValidationErrorItem(
                category="person",
                person_id=raw_pid,
                field="person_id",
                value=raw_pid,
                message=f"Duplicate worker ID '{raw_pid}' in the SQL file.",
                fix_hint=f"Remove or rename the duplicate record for '{raw_pid}'."
            ))
        else:
            seen_pids.add(sanitized_pid)
            valid_pids.add(sanitized_pid)

        # First name / surname empty
        if fname is None or not str(fname).strip():
            errors.append(ValidationErrorItem(
                category="person",
                person_id=raw_pid,
                field="first_name",
                message=f"Missing or empty first name ('first_name') for worker '{raw_pid}'.",
                fix_hint="Specify a first name for each worker."
            ))
        if sname is None or not str(sname).strip():
            errors.append(ValidationErrorItem(
                category="person",
                person_id=raw_pid,
                field="surname",
                message=f"Missing or empty surname ('surname') for worker '{raw_pid}'.",
                fix_hint="Specify a surname for each worker."
            ))

        # Check optional fields if present in schema
        if "birthday" in person_cols and row["birthday"] is not None:
            bday = str(row["birthday"]).strip()
            if bday and not re.match(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?", bday):
                errors.append(ValidationErrorItem(
                    category="person",
                    person_id=raw_pid,
                    field="birthday",
                    value=bday,
                    message=f"Invalid birthday format '{bday}' for worker '{raw_pid}'.",
                    fix_hint="Use standard YYYY-MM-DD or ISO dateTime format (e.g. 1985-04-12)."
                ))

    # 4. Check Records in `hc_descriptor`
    hc_rows = cursor.execute("SELECT * FROM hc_descriptor").fetchall()
    persons_with_hc = set()
    seen_person_icf = set()

    for row in hc_rows:
        h_pid = row["person_id"]
        icf = row["icf_code"]
        qual = row["qualifier"]

        h_pid_sanitized = _sanitize_id(str(h_pid).strip()) if h_pid is not None else ""

        # Referential integrity: person must exist in person table
        if not h_pid_sanitized or h_pid_sanitized not in valid_pids:
            errors.append(ValidationErrorItem(
                category="health_condition",
                person_id=str(h_pid) if h_pid else "NULL",
                field="person_id",
                value=str(h_pid),
                message=f"ICF descriptor references non-existent person_id in 'person' table: '{h_pid}'.",
                fix_hint=f"Ensure '{h_pid}' exists in the 'person' table."
            ))
            continue

        persons_with_hc.add(h_pid_sanitized)

        # ICF code checks
        if not icf or not str(icf).strip():
            errors.append(ValidationErrorItem(
                category="health_condition",
                person_id=h_pid_sanitized,
                field="icf_code",
                message=f"Empty or null ICF code for worker '{h_pid_sanitized}'.",
                fix_hint="Specify a valid ICF code for each row in 'hc_descriptor'."
            ))
        else:
            icf_str = str(icf).strip()
            prefix = icf_str[0].lower() if icf_str else ""
            if prefix not in QUALIFIER_MAP:
                errors.append(ValidationErrorItem(
                    category="health_condition",
                    person_id=h_pid_sanitized,
                    field="icf_code",
                    value=icf_str,
                    message=f"Invalid ICF prefix for '{icf_str}' (worker '{h_pid_sanitized}'). ICF codes must start with 'b' (Body Functions), 'd' (Activities & Participation) or 's' (Body Structures).",
                    fix_hint="Correct the ICF code to start with 'b', 'd', or 's'."
                ))
            elif icf_str not in known_icf:
                errors.append(ValidationErrorItem(
                    category="health_condition",
                    person_id=h_pid_sanitized,
                    field="icf_code",
                    value=icf_str,
                    message=f"ICF code '{icf_str}' (worker '{h_pid_sanitized}') does not exist in the loaded Rientr@ ontology.",
                    fix_hint="Use only ICF codes that belong to the loaded Rientr@ ontology Core Sets."
                ))

            # Duplicate ICF for same person
            key = (h_pid_sanitized, icf_str)
            if key in seen_person_icf:
                errors.append(ValidationErrorItem(
                    category="health_condition",
                    person_id=h_pid_sanitized,
                    field="icf_code",
                    value=icf_str,
                    message=f"Duplicate ICF code '{icf_str}' for worker '{h_pid_sanitized}'.",
                    fix_hint=f"Remove the duplicate '{icf_str}' row for '{h_pid_sanitized}' in 'hc_descriptor'."
                ))
            else:
                seen_person_icf.add(key)

        # Qualifier checks
        if qual is None:
            errors.append(ValidationErrorItem(
                category="health_condition",
                person_id=h_pid_sanitized,
                field="qualifier",
                message=f"Null qualifier for code '{icf}' (worker '{h_pid_sanitized}').",
                fix_hint="The qualifier must be an integer between 0 and 4."
            ))
        else:
            try:
                qual_int = int(qual)
                if qual_int < 0 or qual_int > 4:
                    errors.append(ValidationErrorItem(
                        category="health_condition",
                        person_id=h_pid_sanitized,
                        field="qualifier",
                        value=str(qual),
                        message=f"Qualifier out of range ({qual}) for code '{icf}' (worker '{h_pid_sanitized}'). Allowed values: 0 (no impairment), 1 (mild), 2 (moderate), 3 (severe), 4 (complete).",
                        fix_hint="Set qualifier to an integer value from 0 to 4."
                    ))
            except (ValueError, TypeError):
                errors.append(ValidationErrorItem(
                    category="health_condition",
                    person_id=h_pid_sanitized,
                    field="qualifier",
                    value=str(qual),
                    message=f"Non-numeric qualifier value '{qual}' for code '{icf}' (worker '{h_pid_sanitized}').",
                    fix_hint="The qualifier must be an integer between 0 and 4."
                ))

    # Check that each valid person has at least one HC descriptor
    for pid in valid_pids:
        if pid not in persons_with_hc:
            errors.append(ValidationErrorItem(
                category="health_condition",
                person_id=pid,
                field="hc_descriptor",
                message=f"Worker '{pid}' does not have any associated health conditions (ICF descriptors).",
                fix_hint=f"Add at least one row in 'hc_descriptor' for worker '{pid}'."
            ))

    # 5. Check Records in `job_evaluation` if present
    if "job_evaluation" in tables:
        job_rows = cursor.execute("SELECT * FROM job_evaluation").fetchall()
        seen_person_jobs = set()

        for row in job_rows:
            j_pid = row["person_id"]
            job_id = row["job_id"]

            j_pid_sanitized = _sanitize_id(str(j_pid).strip()) if j_pid is not None else ""

            if not j_pid_sanitized or j_pid_sanitized not in valid_pids:
                errors.append(ValidationErrorItem(
                    category="job",
                    person_id=str(j_pid) if j_pid else "NULL",
                    field="person_id",
                    value=str(j_pid),
                    message=f"Job evaluation references non-existent person_id in 'person' table: '{j_pid}'.",
                    fix_hint=f"Ensure '{j_pid}' is present in the 'person' table."
                ))
                continue

            if not job_id or not str(job_id).strip():
                errors.append(ValidationErrorItem(
                    category="job",
                    person_id=j_pid_sanitized,
                    field="job_id",
                    message=f"Empty or null job_id for worker '{j_pid_sanitized}'.",
                    fix_hint="Specify a valid job_id for each job evaluation."
                ))
            else:
                job_str = str(job_id).strip()
                if job_str not in known_jobs:
                    available_sample = ", ".join(sorted(list(known_jobs))[:4])
                    errors.append(ValidationErrorItem(
                        category="job",
                        person_id=j_pid_sanitized,
                        field="job_id",
                        value=job_str,
                        message=f"Job role '{job_str}' assigned to '{j_pid_sanitized}' does not exist in the loaded Rientr@ ontology.",
                        fix_hint=f"Use job identifiers present in the ontology (e.g. {available_sample}...). Ensure casing matches the ontology ID."
                    ))

                # Duplicate job evaluation for same person
                job_key = (j_pid_sanitized, job_str)
                if job_key in seen_person_jobs:
                    errors.append(ValidationErrorItem(
                        category="job",
                        person_id=j_pid_sanitized,
                        field="job_id",
                        value=job_str,
                        message=f"Duplicate job evaluation '{job_str}' for worker '{j_pid_sanitized}'.",
                        fix_hint=f"Remove the duplicate assignment for '{job_str}' on '{j_pid_sanitized}' in 'job_evaluation'."
                    ))
                else:
                    seen_person_jobs.add(job_key)

    return errors


def _remove_person_from_rdf(text: str, pid: str) -> str:
    """Remove existing Person, HealthCondition, and Descriptors RDF blocks for pid."""
    text = re.sub(
        rf'\s*<owl:NamedIndividual\s+rdf:about="http://www\.stiima\.cnr\.it/RientraHC#des_{re.escape(pid)}_[^"]+">.*?</owl:NamedIndividual>',
        '',
        text,
        flags=re.DOTALL
    )
    text = re.sub(
        rf'\s*<owl:NamedIndividual\s+rdf:about="http://www\.stiima\.cnr\.it/Person-CommonBox#HC{re.escape(pid)}">.*?</owl:NamedIndividual>',
        '',
        text,
        flags=re.DOTALL
    )
    text = re.sub(
        rf'\s*(?:<!--\s*Person:\s*{re.escape(pid)}\s*-->\s*)?<owl:NamedIndividual\s+rdf:about="http://www\.stiima\.cnr\.it/Person-CommonBox#{re.escape(pid)}">.*?</owl:NamedIndividual>',
        '',
        text,
        flags=re.DOTALL
    )
    return text


def _get_existing_person_data(g: "Graph", pid: str) -> dict:
    """Extract a person's current data from the parsed ontology graph for comparison."""
    p_iri = URIRef(str(NS_PERSON) + pid)
    hc_iri = URIRef(str(NS_PERSON) + "HC" + pid)

    first_name = str(next(g.objects(p_iri, NS_FOAF.first_name), "") or "")
    surname = str(next(g.objects(p_iri, NS_FOAF.surname), "") or "")
    tin = str(next(g.objects(p_iri, NS_FOAF.TIN), "") or "")
    city = str(next(g.objects(p_iri, NS_FOAF.city), "") or "")
    country = str(next(g.objects(p_iri, NS_FOAF.country), "") or "")
    zip_code = str(next(g.objects(p_iri, NS_FOAF.ZIPcode), "") or "")
    birthday = str(next(g.objects(p_iri, NS_FOAF.birthday), "") or "")

    jobs = set()
    for _, _, j_iri in g.triples((p_iri, NS_RIEONT3.isEvaluatedForJob, None)):
        jobs.add(str(j_iri).split("#")[-1])

    icfs: dict[str, int] = {}
    for _, _, desc_iri in g.triples((hc_iri, NS_HC.isDescribedBy, None)):
        icf_iri = next(g.objects(desc_iri, NS_HC.involvesICFCode), None)
        if not icf_iri:
            continue
        icf_code = str(icf_iri).split("#")[-1]
        prefix = icf_code[0].lower() if icf_code else "b"
        qual_prop_name = QUALIFIER_MAP.get(prefix, "BFqual")
        qual_val = next(g.objects(desc_iri, getattr(NS_HC, qual_prop_name)), None)
        if qual_val is not None:
            try:
                icfs[icf_code] = int(str(qual_val))
            except Exception:
                pass

    return {
        "first_name": first_name,
        "surname": surname,
        "tin": tin,
        "city": city,
        "country": country,
        "zip_code": zip_code,
        "birthday": birthday,
        "jobs": jobs,
        "icfs": icfs,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def import_sql_dataset(
    sql_path: str,
    ontology_path: str,
    mapping_path: str,
) -> ImportResult:
    """
    Full import pipeline with strict pre-validation:
      1. Load SQL dataset into in-memory SQLite (safely catch syntax errors).
      2. Extract known ontology entities (ICF codes, jobs, existing persons).
      3. Run comprehensive validation across all criteria & parameters.
         --> If ANY validation errors are found, abort immediately WITHOUT modifying the ontology!
      4. Classify workers: new, identical (skip), or modified (overwrite/update).
      5. For modified workers, remove prior RDF/XML individual blocks.
      6. Create auxiliary VIEWs for R2RML and materialise triples with Morph-KGC.
      7. Inject XML blocks into the RDF file (in place, with .bak backup).

    Returns an ImportResult summary.
    """
    if not _DEPS_OK:
        return ImportResult(
            error="morph-kgc / rdflib not installed. Run: pip install morph-kgc rdflib"
        )

    result = ImportResult()

    try:
        # 1. Load SQL in in-memory SQLite
        try:
            conn = _load_sql(sql_path)
        except sqlite3.Error as sql_err:
            result.validation_errors = [
                ValidationErrorItem(
                    category="schema",
                    message=f"Syntax or execution error in SQL file: {sql_err}",
                    fix_hint="Check the SQL syntax (CREATE TABLE, INSERT INTO) in the file."
                ).to_dict()
            ]
            result.error = f"SQL syntax error in file: {sql_err}"
            return result

        # 2. Read ontology text and extract known entities
        rdf_text = Path(ontology_path).read_text(encoding="utf-8")
        known_icf  = _extract_known_icf(rdf_text)
        known_jobs = _extract_known_jobs(ontology_path)

        # 3. PRE-VALIDATION: Check all criteria
        errors = validate_sql_dataset(conn, rdf_text, known_icf, known_jobs)
        if errors:
            err_count = len(errors)
            result.validation_errors = [e.to_dict() for e in errors]
            result.error = f"Validation failed: found {err_count} issue(s) in the file. The import was blocked to prevent conflicts in the ontology."
            conn.close()
            return result

        # 4. Classify new, updated, and identical (skipped) persons
        g_existing = Graph()
        g_existing.parse(ontology_path, format="xml")

        new_ids: list[str] = []
        updated_ids: list[str] = []
        skipped_ids: list[str] = []

        all_persons_rows = conn.execute("SELECT * FROM person").fetchall()
        person_cols_set = {col.lower() for col in all_persons_rows[0].keys()} if all_persons_rows else set()

        has_job_eval = "job_evaluation" in {r[0].lower() for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

        for row in all_persons_rows:
            raw_pid = str(row["person_id"]).strip()
            pid = _sanitize_id(raw_pid)

            fname = (row["first_name"] or "").strip()
            sname = (row["surname"] or "").strip()
            tin = (row["TIN"] or "").strip() if "tin" in person_cols_set and row["TIN"] is not None else ""
            city = (row["city"] or "").strip() if "city" in person_cols_set and row["city"] is not None else ""
            country = (row["country"] or "").strip() if "country" in person_cols_set and row["country"] is not None else ""
            zip_code = str(row["zip_code"]).strip() if "zip_code" in person_cols_set and row["zip_code"] is not None else ""
            birthday = str(row["birthday"]).strip() if "birthday" in person_cols_set and row["birthday"] is not None else ""

            incoming_icfs = {
                r["icf_code"]: int(r["qualifier"])
                for r in conn.execute("SELECT icf_code, qualifier FROM hc_descriptor WHERE person_id = ?", (row["person_id"],)).fetchall()
            }
            incoming_jobs = set()
            if has_job_eval:
                incoming_jobs = {
                    r["job_id"]
                    for r in conn.execute("SELECT job_id FROM job_evaluation WHERE person_id = ?", (row["person_id"],)).fetchall()
                }

            if _person_exists(rdf_text, pid):
                existing = _get_existing_person_data(g_existing, pid)
                is_identical = (
                    fname == existing["first_name"] and
                    sname == existing["surname"] and
                    (not tin or tin == existing["tin"]) and
                    (not city or city == existing["city"]) and
                    (not country or country == existing["country"]) and
                    (not zip_code or zip_code == existing["zip_code"]) and
                    (not birthday or birthday == existing["birthday"]) and
                    incoming_icfs == existing["icfs"] and
                    incoming_jobs == existing["jobs"]
                )
                if is_identical:
                    skipped_ids.append(pid)
                else:
                    updated_ids.append(pid)
            else:
                new_ids.append(pid)

        result.new_person_ids  = new_ids
        result.updated_ids     = updated_ids
        result.skipped_ids     = skipped_ids
        result.persons_added   = len(new_ids)
        result.persons_updated = len(updated_ids)
        result.persons_skipped = len(skipped_ids)

        persons_to_process = set(new_ids + updated_ids)

        if not persons_to_process:
            conn.close()
            return result

        # 5. For updated persons, remove existing RDF/XML blocks before injection
        for u_pid in updated_ids:
            rdf_text = _remove_person_from_rdf(rdf_text, u_pid)

        # 6. Create auxiliary views
        v_icf_ok, v_icf_skip, v_job_ok, v_job_skip = _create_views(
            conn, known_icf, known_jobs
        )
        result.icf_valid    = v_icf_ok
        result.icf_skipped  = v_icf_skip
        result.jobs_valid   = v_job_ok
        result.jobs_skipped = v_job_skip

        # Materialise via R2RML
        db_file = _export_db_to_file(conn)
        try:
            new_graph = _run_r2rml(mapping_path, db_file)
        finally:
            Path(db_file).unlink(missing_ok=True)

        # 7. Convert triples → RDF/XML blocks only for persons_to_process
        blocks = _triples_to_rdfxml_blocks(new_graph, persons_to_process)

        # 8. Inject into the RDF file
        if CLOSING_TAG not in rdf_text:
            return ImportResult(error="</rdf:RDF> closing tag not found in ontology file.")

        backup = ontology_path + ".bak"
        shutil.copy2(ontology_path, backup)
        result.backup_path = backup

        injection = (
            "\n\n\n    <!-- ===== PERSONE IMPORTATE / AGGIORNATE (RDB2RDF via R2RML) ===== -->\n\n"
            + "\n\n".join(blocks) + "\n\n"
        )
        updated = rdf_text.replace(CLOSING_TAG, injection + CLOSING_TAG, 1)
        Path(ontology_path).write_text(updated, encoding="utf-8")

        # 9. Extract detailed mapping info for each imported person before closing DB conn
        details = []
        for pid in sorted(list(persons_to_process)):
            try:
                row = conn.execute("SELECT first_name, surname FROM person WHERE person_id = ?", (pid,)).fetchone()
                fullname = f"{row['first_name']} {row['surname']}" if row else pid
            except Exception:
                fullname = pid

            icfs = []
            try:
                icf_rows = conn.execute("""
                    SELECT h.icf_code 
                    FROM hc_descriptor h
                    JOIN _known_icf k ON k.icf_code = h.icf_code
                    WHERE h.person_id = ?
                """, (pid,)).fetchall()
                icfs = [r["icf_code"] for r in icf_rows]
            except Exception as e:
                logger.warning("[importer] Error querying imported ICFs for %s: %s", pid, e)

            jobs = []
            try:
                job_rows = conn.execute("""
                    SELECT j.job_id 
                    FROM job_evaluation j
                    JOIN _known_jobs k ON k.job_id = j.job_id
                    WHERE j.person_id = ?
                """, (pid,)).fetchall()
                jobs = [r["job_id"] for r in job_rows]
            except Exception as e:
                logger.warning("[importer] Error querying imported jobs for %s: %s", pid, e)

            details.append({
                "person_id": pid,
                "fullname": fullname,
                "is_updated": pid in updated_ids,
                "icfs": icfs,
                "jobs": jobs
            })
        result.details = details
        conn.close()

    except Exception as exc:
        logger.exception("[importer] Import failed")
        result.error = str(exc)

    return result
