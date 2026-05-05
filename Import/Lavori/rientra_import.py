"""
rientra_import.py  —  Rientr@ Import Tool
==========================================
Legge dataset SQL (2 tabelle: person + hc_descriptor) e inietta
nuovi pazienti nell'ontologia Rientra.rdf senza ri-serializzarla.

isSelected viene impostato automaticamente a false dallo script.
isEvaluatedForJob non viene gestito in questa versione.

Uso:
  python rientra_import.py --ontology Rientra.rdf --dataset dataset_import.sql
  python rientra_import.py --ontology Rientra.rdf --dataset dataset_import.sql --output Rientra_v2.rdf
"""

import argparse
import re
import sqlite3
import sys
import shutil
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

NS_FOAF   = "http://www.stiima.cnr.it/FOAF-excerpt#"
NS_HC     = "http://www.stiima.cnr.it/RientraHC#"
NS_ICF    = "http://www.stiima.cnr.it/ICF-exc-coreset#"
NS_PERSON = "http://www.stiima.cnr.it/Person-CommonBox#"
XSD       = "http://www.w3.org/2001/XMLSchema#"
CLOSING_TAG = "</rdf:RDF>"

QUALIFIER_MAP = {"b": "BFqual", "d": "AP1qual", "s": "BS1qual"}

FOAF_DATATYPES = {
    "first_name": "string",
    "surname":    "string",
    "TIN":        "string",
    "city":       "string",
    "country":    "string",
    "birthday":   "dateTime",
    "ZIPcode":    "int",
}


def load_dataset(sql_path):
    sql = Path(sql_path).read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(sql)
    except sqlite3.Error as e:
        print(f"ERRORE SQL: {e}"); sys.exit(1)
    return conn


def sanitize_id(name):
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name)


def person_exists(rdf_text, person_id):
    return f"{NS_PERSON}{person_id}" in rdf_text


def iri_exists(rdf_text, fragment):
    return fragment in rdf_text


def normalize_birthday(val):
    if val and "T" not in str(val):
        return str(val).strip() + "T00:00:00"
    return val


def foaf_prop_xml(prop_name, raw_value):
    dtype = FOAF_DATATYPES.get(prop_name, "string")
    if prop_name == "birthday":
        raw_value = normalize_birthday(raw_value)
    if prop_name == "ZIPcode":
        try:
            raw_value = str(int(raw_value))
        except (ValueError, TypeError):
            pass
    return (
        f'        <FOAF-excerpt:{prop_name} rdf:datatype="{XSD}{dtype}">'
        f'{xml_escape(str(raw_value))}</FOAF-excerpt:{prop_name}>'
    )


def build_descriptor_xml(desc_id, icf_code, qualifier):
    qual_prop = QUALIFIER_MAP.get(icf_code[0].lower(), "BFqual")
    return (
        f'    <owl:NamedIndividual rdf:about="{NS_HC}{desc_id}">\n'
        f'        <rdf:type rdf:resource="{NS_HC}HC_Descriptor"/>\n'
        f'        <RientraHC:involvesICFCode rdf:resource="{NS_ICF}{icf_code}"/>\n'
        f'        <RientraHC:{qual_prop} rdf:datatype="{XSD}integer">'
        f'{qualifier}</RientraHC:{qual_prop}>\n'
        f'    </owl:NamedIndividual>'
    )


def build_hc_xml(hc_id, descriptor_iris):
    desc_lines = "\n".join(
        f'        <RientraHC:isDescribedBy rdf:resource="{iri}"/>'
        for iri in descriptor_iris
    )
    return (
        f'    <owl:NamedIndividual rdf:about="{NS_PERSON}{hc_id}">\n'
        f'        <rdf:type rdf:resource="{NS_HC}Health_Condition"/>\n'
        f'{desc_lines}\n'
        f'    </owl:NamedIndividual>'
    )


def build_person_xml(person, hc_id, person_id):
    cols = person.keys()
    fields = [
        ("first_name", person["first_name"]),
        ("surname",    person["surname"]),
        ("TIN",        person["TIN"]      if "TIN"      in cols else None),
        ("birthday",   person["birthday"] if "birthday" in cols else None),
        ("city",       person["city"]     if "city"     in cols else None),
        ("country",    person["country"]  if "country"  in cols else None),
        ("ZIPcode",    person["zip_code"] if "zip_code" in cols else None),
    ]
    data_props = "\n".join(
        foaf_prop_xml(prop, val)
        for prop, val in fields if val is not None and str(val).strip()
    )
    # isSelected sempre false — impostato automaticamente, non viene dal dataset
    is_selected_xml = (
        f'        <rie:isSelected rdf:datatype="{XSD}boolean">false</rie:isSelected>'
    )
    return (
        f'    <!-- Person: {person_id} -->\n'
        f'    <owl:NamedIndividual rdf:about="{NS_PERSON}{person_id}">\n'
        f'        <rdf:type rdf:resource="{NS_FOAF}Person"/>\n'
        f'        <RientraHC:isInHealthCondition rdf:resource="{NS_PERSON}{hc_id}"/>\n'
        f'{data_props}\n'
        f'{is_selected_xml}\n'
        f'    </owl:NamedIndividual>'
    )


def process_person(rdf_text, person, descriptors, stats):
    person_id = sanitize_id(person["person_id"])

    if person_exists(rdf_text, person_id):
        print(f"  [SKIP] {person_id} già presente.")
        stats["skipped"] += 1
        return []

    hc_id = "HC" + person_id
    blocks = []
    descriptor_iris = []
    skipped_icf = []

    for row in descriptors:
        icf_code  = row["icf_code"]
        qualifier = int(row["qualifier"])
        prefix    = icf_code[0].lower() if icf_code else ""

        if prefix == "e":
            skipped_icf.append(f"{icf_code}(E-factor)")
            stats["icf_skipped"] += 1
            continue
        if not iri_exists(rdf_text, icf_code):
            skipped_icf.append(icf_code)
            stats["icf_skipped"] += 1
            continue

        desc_id = f"des_{person_id}_{sanitize_id(icf_code)}"
        descriptor_iris.append(NS_HC + desc_id)
        blocks.append(build_descriptor_xml(desc_id, icf_code, qualifier))
        stats["descriptors"] += 1

    if skipped_icf:
        print(f"  [WARN] {person_id}: {len(skipped_icf)} codici ICF ignorati: {skipped_icf}")

    blocks.append(build_hc_xml(hc_id, descriptor_iris))
    blocks.append(build_person_xml(person, hc_id, person_id))
    stats["persons"] += 1
    print(f"  [OK]   {person_id} → {len(descriptor_iris)} descrittori inseriti.")
    return blocks


def main():
    parser = argparse.ArgumentParser(description="Rientr@ Import Tool")
    parser.add_argument("--ontology", required=True)
    parser.add_argument("--dataset",  required=True)
    parser.add_argument("--output",   default=None)
    args = parser.parse_args()

    out_path = args.output or args.ontology

    print(f"\n{'='*60}")
    print(f"  Rientr@ Import Tool")
    print(f"  Ontologia : {args.ontology}")
    print(f"  Dataset   : {args.dataset}")
    print(f"  Output    : {out_path}")
    print(f"{'='*60}\n")

    print("[1/4] Caricamento dataset SQL...")
    conn = load_dataset(args.dataset)
    persons = conn.execute("SELECT * FROM person").fetchall()
    print(f"      {len(persons)} persona/e trovata/e.\n")

    print("[2/4] Lettura ontologia RDF (testo grezzo)...")
    rdf_text = Path(args.ontology).read_text(encoding="utf-8")
    print(f"      {len(rdf_text.splitlines())} righe.\n")

    backup = out_path + ".bak"
    shutil.copy2(args.ontology, backup)
    print(f"[3/4] Backup salvato: {backup}\n")

    print("[4/4] Import persone...")
    stats = {"persons": 0, "descriptors": 0, "skipped": 0,
             "errors": 0, "icf_skipped": 0}
    all_blocks = []

    for person in persons:
        print(f"\n  → {person['person_id']}")
        descriptors = conn.execute(
            "SELECT icf_code, qualifier FROM hc_descriptor WHERE person_id = ?",
            (person["person_id"],)
        ).fetchall()
        blocks = process_person(rdf_text, person, descriptors, stats)
        all_blocks.extend(blocks)

    if all_blocks:
        injection = "\n\n\n    <!-- ===== PAZIENTI IMPORTATI ===== -->\n\n"
        injection += "\n\n".join(all_blocks)
        injection += "\n\n"
        if CLOSING_TAG not in rdf_text:
            print("ERRORE: </rdf:RDF> non trovato."); sys.exit(1)
        updated = rdf_text.replace(CLOSING_TAG, injection + CLOSING_TAG, 1)
        Path(out_path).write_text(updated, encoding="utf-8")
    else:
        print("\n  Nessuna persona nuova da inserire.")
        if out_path != args.ontology:
            shutil.copy2(args.ontology, out_path)

    print(f"\n{'='*60}")
    print(f"  Salvato: {out_path}")
    print(f"{'='*60}")
    print(f"""
  RIEPILOGO
  ─────────────────────────────────
  Persone inserite     : {stats['persons']}
  Persone già presenti : {stats['skipped']}
  Errori               : {stats['errors']}
  Descrittori ICF      : {stats['descriptors']}
  Codici ICF ignorati  : {stats['icf_skipped']}
  Backup               : {backup}
  ─────────────────────────────────
""")
    conn.close()


if __name__ == "__main__":
    main()