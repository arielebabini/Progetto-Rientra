#!/usr/bin/env python3
"""
add_job_to_ontology.py
======================
Aggiunge uno o più lavori all'ontologia Rientra (formato RDF/OWL).

Ogni lavoro è descritto da quattro file con nomi fissi:
  - Skills_XX-XXXX-00_csv.xlsx   (colonne: Importance, Skill, Skill Description)
  - Abilities_XX-XXXX-00_csv.xlsx(colonne: Importance, Ability, Ability Description)
  - desc.txt                     (descrizione breve O*NET)
  - label.txt                    (titoli alternativi separati da virgola)

Il codice SOC viene estratto automaticamente dal nome del file xlsx
(es. Skills_33-9011-00_csv.xlsx  →  33-9011.00).
Il nome del Job nell'ontologia viene derivato dal nome della cartella.

─────────────────────────────────────────────────────────────────────
MODALITÀ 1 — Singolo job (file esplicitati)
─────────────────────────────────────────────────────────────────────
  python3 add_job_to_ontology.py \
      --rdf       Rientra.rdf \
      --skills    Skills_33-9011-00_csv.xlsx \
      --abilities Abilities_33-9011-00_csv.xlsx \
      --desc      desc.txt \
      --labels    label.txt \
      --soc       33-9011.00 \
      --job-name  Animal_control_workers \
      --output    Rientra_updated.rdf

─────────────────────────────────────────────────────────────────────
MODALITÀ 2 — Batch (una cartella per ogni job)
─────────────────────────────────────────────────────────────────────
  Struttura attesa:
      jobs/
      ├── Animal_control_workers/
      │   ├── Skills_33-9011-00_csv.xlsx
      │   ├── Abilities_33-9011-00_csv.xlsx
      │   ├── desc.txt
      │   └── label.txt
      ├── AltroJob/
      │   └── ...
      └── ...

  Comando:
      python3 add_job_to_ontology.py \
          --rdf       Rientra.rdf \
          --jobs-dir  jobs/ \
          --output    Rientra_updated.rdf

    Comando per controllo duplicati:
        python add_job_V2.py --rdf Rientra.rdf --deduplicate

    Comando per export JobList:
        python add_job_V2.py --rdf Rientra.rdf --export-jobs jobs_export.csv
        
  I job vengono aggiunti in ordine alfabetico di cartella.
  Il file di output viene aggiornato in-place dopo ogni job,
  così i jde si accumulano correttamente senza conflitti.

─────────────────────────────────────────────────────────────────────
Soglie di importanza (da SWRL rules / pattern ontologia)
─────────────────────────────────────────────────────────────────────
  score >= 70  → isVeryImportantFor
  50 ≤ score < 70  → isImportantFor
  25 ≤ score < 50  → isSomewhatImportantFor
  score < 25   → isLessImportantFor
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("Installa openpyxl: pip install openpyxl")

# ---------------------------------------------------------------------------
# Mappatura nome O*NET -> nome SkAb nell'ontologia
# (alcuni nomi hanno typo o formato diverso nell'ontologia originale)
# ---------------------------------------------------------------------------
ONET_TO_SKAB = {
    # Skills
    "Active Learning":                    "ActiveLearning",
    "Active Listening":                   "ActiveListening",
    "Complex Problem Solving":            "ComplexProblemSolving",
    "Coordination":                       "Coordination",
    "Critical Thinking":                  "CriticalThinking",
    "Equipment Maintenance":              "Equipment_Maintenance",
    "Equipment Selection":                "Equipment_Selection",
    "Installation":                       "Installation",
    "Instructing":                        "Instructing",
    "Judgment and Decision Making":       "JudgmentAndDecisionMaking",
    "Learning Strategies":                "LearningStrategies",
    "Management of Financial Resources":  "Management_of_Financial_Resources",
    "Management of Material Resources":   "Management_of_Material_Resources",
    "Management of Personnel Resources":  "Management_of_Personnel_Resources",
    "Mathematics":                        "Mathematics",
    "Monitoring":                         "Monitoring",
    "Negotiation":                        "Negotiation",
    "Operations Analysis":                "Operation_Analysis",
    "Operations Monitoring":              "Operation_Monitoring",
    "Operation and Control":              "Operation_and_Control",
    "Persuasion":                         "Persuasion",
    "Programming":                        "Programming",
    "Quality Control Analysis":           "Quality_Control_Analysis",
    "Reading Comprehension":              "ReadingComprehension",
    "Repairing":                          "Repairing",
    "Science":                            "Science",
    "Service Orientation":                "ServiceOrientation",
    "Social Perceptiveness":              "Social_Perceptiveness",
    "Speaking":                           "Speaking",
    "Systems Analysis":                   "SystemAnalysis",
    "Systems Evaluation":                 "SystemEvaluation",
    "Technology Design":                  "Technology_Design",
    "Time Management":                    "TimeManagement",
    "Troubleshooting":                    "Troubleshooting",
    "Writing":                            "Writing",
    # Abilities
    "Arm-Hand Steadiness":                "ArmHandSteadiness",
    "Auditory Attention":                 "AuditoryAttention",
    "Category Flexibility":               "CategoryFlexibility",
    "Control Precision":                  "ControlPrecision",
    "Deductive Reasoning":                "DeductiveReasoning",
    "Depth Perception":                   "DepthPerception",
    "Dynamic Flexibility":                "Dynamic_Flexibility",
    "Dynamic Strength":                   "DynamicStrenght",    # typo nell'ontologia
    "Explosive Strength":                 "ExplosiveStrenght",  # typo nell'ontologia
    "Extent Flexibility":                 "ExtentFlexibility",
    "Far Vision":                         "FarVision",
    "Finger Dexterity":                   "FingerDexterity",
    "Flexibility of Closure":             "FlexibilityOfClosure",
    "Fluency of Ideas":                   "FluencyOfIdeas",
    "Glare Sensitivity":                  "GlareSensitivity",
    "Gross Body Coordination":            "GrossBodyCoordination",
    "Gross Body Equilibrium":             "GrossBodyEquilibrium",
    "Hearing Sensitivity":                "HearingSensitivity",
    "Inductive Reasoning":                "InductiveReasoning",
    "Information Ordering":               "InformationOrdering",
    "Manual Dexterity":                   "ManualDexterity",
    "Mathematical Reasoning":             "MathematicalReasoning",
    "Memorization":                       "Memorization",
    "Multilimb Coordination":             "MultilimbCoordination",
    "Near Vision":                        "NearVision",
    "Night Vision":                       "NightVision",
    "Number Facility":                    "NumberFacility",
    "Oral Comprehension":                 "OralComprehension",
    "Oral Expression":                    "OralExpression",
    "Originality":                        "Originality",
    "Perceptual Speed":                   "PerceptualSpeed",
    "Peripheral Vision":                  "PeripheralVision",
    "Problem Sensitivity":                "ProblemSensitivity",
    "Rate Control":                       "RateControl",
    "Reaction Time":                      "ReactionTime",
    "Response Orientation":               "ResponseOrientation",
    "Selective Attention":                "SelectiveAttention",
    "Sound Localization":                 "SoundLocalization",
    "Spatial Orientation":                "SpatialOrientation",
    "Speech Clarity":                     "SpeechClarity",
    "Speech Recognition":                 "SpeechRecognition",
    "Speed of Closure":                   "SpeedOfClosure",
    "Speed of Limb Movement":             "SpeedOfLimbMovement",
    "Stamina":                            "Stamina",
    "Static Strength":                    "StaticStrenght",     # typo nell'ontologia
    "Time Sharing":                       "TimeSharing",
    "Trunk Strength":                     "TrunkStrenght",      # typo nell'ontologia
    "Visual Color Discrimination":        "VisualColorDiscrimination",
    "Visualization":                      "Visualization",
    "Written Comprehension":              "WrittenComprehension",
    "Written Expression":                 "WrittenExpression",
    "Wrist-Finger Speed":                 "WristFingerSpeed",
}

# Namespace URIs
NS_JL   = "http://www.stiima.cnr.it/JobList#"
NS_JD   = "http://www.stiima.cnr.it/JobDescription#"
NS_SKAB = "http://www.stiima.cnr.it/SkAb#"
NS_OWL  = "http://www.w3.org/2002/07/owl#"
NS_RDF  = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
NS_XSD  = "http://www.w3.org/2001/XMLSchema#"


def score_to_importance(score: int) -> str:
    """Converte uno score O*NET nel nome della proprietà di importanza."""
    if score >= 70:
        return "isVeryImportantFor"
    elif score >= 50:
        return "isImportantFor"
    elif score >= 25:
        return "isSomewhatImportantFor"
    else:
        return "isLessImportantFor"


def read_xlsx_scores(path: str) -> list[tuple[int, str]]:
    """
    Legge un file .xlsx O*NET (Skills o Abilities) e restituisce
    una lista di (score, nome_onet) ordinata per score decrescente.
    Cerca la riga di intestazione (Importance, Skill/Ability, ...) 
    e poi legge i dati.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    entries = []
    header_found = False
    imp_col = None
    name_col = None

    for row in ws.iter_rows(values_only=True):
        if not header_found:
            # Cerca la riga header
            for i, cell in enumerate(row):
                if isinstance(cell, str):
                    if cell.strip().lower() == "importance":
                        imp_col = i
                    elif cell.strip().lower() in ("skill", "ability"):
                        name_col = i
            if imp_col is not None and name_col is not None:
                header_found = True
            continue

        if row[imp_col] is None:
            continue
        try:
            score = int(row[imp_col])
        except (ValueError, TypeError):
            continue
        name = str(row[name_col]).strip() if row[name_col] else None
        if name:
            entries.append((score, name))

    wb.close()
    return sorted(entries, key=lambda x: -x[0])


def find_max_jde(rdf_content: str) -> int:
    """Trova il numero più alto di jde già presente nell'RDF."""
    nums = [int(m) for m in re.findall(r'JobList#jde(\d+)', rdf_content)]
    return max(nums) if nums else 0


def xml_escape(text: str) -> str:
    """Escape dei caratteri speciali XML."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


def find_and_remove_duplicate_jobs(rdf_content: str) -> tuple[str, list[str]]:
    """
    Individua i blocchi owl:Class duplicati nel namespace NS_JL
    (stesso rdf:about) e rimuove tutte le occorrenze successive alla prima.

    Restituisce (rdf_content_pulito, lista_uri_duplicati_rimossi).
    """
    # Regex che cattura l'intero blocco: apertura + corpo + </owl:Class>
    block_re = re.compile(
        r'(<owl:Class\s+rdf:about="(' + re.escape(NS_JL) + r'[^"]+)">' 
        r'.*?</owl:Class>)',
        re.DOTALL
    )

    seen_uris: set[str] = set()
    removed: list[str] = []

    def _remove_if_duplicate(m: re.Match) -> str:
        uri = m.group(2)   # URI completo
        if uri in seen_uris:
            removed.append(uri)
            # Rimuove anche l'eventuale riga di commento immediatamente prima
            return ""      # sostituisce il blocco con stringa vuota
        seen_uris.add(uri)
        return m.group(0)  # mantieni invariato

    cleaned = block_re.sub(_remove_if_duplicate, rdf_content)

    # Elimina righe vuote multiple consecutive lasciate dalla rimozione
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned, removed


def export_jobs_from_rdf(rdf_content: str, output_csv: str) -> None:
    """
    Legge il contenuto RDF, estrae tutti i job definiti nel namespace
    http://www.stiima.cnr.it/JobList# e salva nome + descrizione in un CSV.

    Un 'job reale' è un owl:Class con rdf:about che inizia per NS_JL
    e NON è 'Job' o 'Job_Descriptor' (le classi base dell'ontologia).
    La descrizione viene letta dalla proprietà JobL:ONet_short_description.
    """
    # ── Rimozione duplicati prima dell'estrazione ────────────────────────────
    rdf_content, dupes = find_and_remove_duplicate_jobs(rdf_content)
    if dupes:
        print(f"[INFO] Rimossi {len(dupes)} blocchi duplicati dal namespace NS_JL:")
        for uri in dupes:
            print(f"       - {uri}")

    # Trova tutti i blocchi owl:Class appartenenti a NS_JL
    # Pattern: cattura rdf:about e tutto il contenuto del blocco
    block_pattern = re.compile(
        r'<owl:Class\s+rdf:about="(' + re.escape(NS_JL) + r'([^"]+))">(.*?)</owl:Class>',
        re.DOTALL
    )

    # Pattern per la descrizione breve
    desc_pattern = re.compile(
        r'<JobL:ONet_short_description[^>]*>([^<]*)</JobL:ONet_short_description>',
        re.DOTALL
    )

    BASE_CLASSES = {"Job", "Job_Descriptor"}
    rows = []

    for m in block_pattern.finditer(rdf_content):
        full_uri  = m.group(1)   # URI completo
        local     = m.group(2)   # parte dopo il #
        block_body = m.group(3)

        # Salta le classi base dell'ontologia
        if local in BASE_CLASSES:
            continue

        # Cerca la descrizione all'interno del blocco
        desc_match = desc_pattern.search(block_body)
        description = desc_match.group(1).strip() if desc_match else ""

        # Converte underscore -> spazi per un nome leggibile
        job_label = local.replace("_", " ")

        rows.append({
            "Job Name":    job_label,
            "URI":         full_uri,
            "Description": description,
        })

    if not rows:
        print("[WARN] Nessun job trovato nel namespace NS_JL dell'ontologia.")
        return

    # Ordine alfabetico per nome
    rows.sort(key=lambda r: r["Job Name"].lower())

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Job Name", "URI", "Description"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] {len(rows)} job esportati in '{output_csv}'")
    for r in rows:
        preview = r['Description'][:80] + ('...' if len(r['Description']) > 80 else '')
        print(f"     • {r['Job Name']}")
        if preview:
            print(f"       {preview}")


def sanitize_job_name(name: str) -> str:
    """
    Converte qualsiasi stringa in un nome valido per un URI RDF.
    Sostituisce spazi e caratteri speciali con underscore.
    Es: "Animal Control Workers"  → "Animal_Control_Workers"
        "Tailors, Dressmakers"    → "Tailors_Dressmakers"
    """
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)   # collassa _ multipli
    return sanitized.strip("_")


def build_job_rdf(
    job_name: str,
    soc_code: str,
    label: str,
    onet_titles: str,
    onet_description: str,
    entries: list[tuple[int, str]],   # (score, onet_name)
    jde_start: int,
) -> tuple[str, str, dict[str, str]]:
    """
    Costruisce i blocchi RDF da inserire nell'ontologia:
      1. Il blocco owl:Class per il Job
      2. I blocchi owl:NamedIndividual per i Job_Descriptor (jde)
      3. Un dizionario {skab_uri: importance_property} per aggiornare le classi SkAb

    Restituisce: (job_class_block, jde_blocks, skab_importance_dict)
    """
    jde_counter = jde_start
    jde_refs = []
    jde_blocks = []
    skab_importance = {}  # skab_name -> importance_property

    for score, onet_name in entries:
        skab_name = ONET_TO_SKAB.get(onet_name)
        if skab_name is None:
            # Fallback: camelCase automatico
            skab_name = "".join(
                w.capitalize()
                for w in re.sub(r"[-/]", " ", onet_name).split()
            )
            print(f"  [WARN] Nessuna mappatura per '{onet_name}', uso '{skab_name}'")

        jde_id = f"jde{jde_counter}"
        jde_counter += 1
        jde_refs.append(jde_id)

        skab_uri = NS_SKAB + skab_name
        importance = score_to_importance(score)
        skab_importance[skab_name] = importance

        jde_block = (
            f'<owl:NamedIndividual rdf:about="{NS_JL}{jde_id}">\n'
            f'  <rdf:type rdf:resource="{NS_JL}Job_Descriptor"/>\n'
            f'  <JobL:concerns rdf:resource="{skab_uri}"/>\n'
            f'  <JobL:hasScore rdf:datatype="{NS_XSD}int">{score}</JobL:hasScore>\n'
            f'</owl:NamedIndividual>'
        )
        jde_blocks.append(jde_block)

    # Blocco del Job
    job_uri = NS_JL + job_name
    requires_lines = "\n".join(
        f'  <JobL:requires rdf:resource="{NS_JL}{jde_id}"/>'
        for jde_id in jde_refs
    )

    # Struttura identica ai job originali dell'ontologia:
    #   1. rdfs:subClassOf Job
    #   2. rdf:type owl:NamedIndividual
    #   3. JobL:requires (uno per jde)
    #   4. rdf:type JobL:Job   ← obbligatorio DOPO i requires, è quello che fa
    #                             riconoscere il job come JobL: in Protégé
    #   5. JobL:SOC_Code / ONet_job_titles / ONet_short_description / rdfs:label
    # NON si include la tripla autoreferenziale <rdf:type rdf:resource="...#JobName"/>
    job_class_block = (
        f'<owl:Class rdf:about="{job_uri}">\n'
        f'  <rdfs:subClassOf rdf:resource="{NS_JL}Job"/>\n'
        f'  <rdf:type rdf:resource="{NS_OWL}NamedIndividual"/>\n'
        f'{requires_lines}\n'
        f'  <rdf:type rdf:resource="{NS_JL}Job"/>\n'
        f'  <JobL:SOC_Code rdf:datatype="{NS_XSD}string">{xml_escape(soc_code)}</JobL:SOC_Code>\n'
        f'  <JobL:ONet_job_titles rdf:datatype="{NS_XSD}string">{xml_escape(onet_titles)}</JobL:ONet_job_titles>\n'
        f'  <JobL:ONet_short_description rdf:datatype="{NS_XSD}string">{xml_escape(onet_description)}</JobL:ONet_short_description>\n'
        f'</owl:Class>'
    )

    return job_class_block, "\n\n".join(jde_blocks), skab_importance


def inject_importance_into_skab(rdf_content: str, job_name: str,
                                  skab_importance: dict[str, str]) -> str:
    """
    Per ogni SkAb nell'ontologia, aggiunge la tripla
      <JobD:isXxxFor rdf:resource="...JobList#<job_name>"/>
    all'interno del blocco owl:Class corrispondente, subito prima del tag </owl:Class>.
    """
    job_uri = NS_JL + job_name

    for skab_name, importance_prop in skab_importance.items():
        # Cerca il blocco della classe SkAb
        pattern = rf'(<owl:Class rdf:about="{re.escape(NS_SKAB + skab_name)}"[^>]*>)'
        match = re.search(pattern, rdf_content)
        if not match:
            print(f"  [WARN] Classe SkAb non trovata nell'ontologia: {skab_name}")
            continue

        # Trovata la classe, inserisci la tripla di importanza prima di </owl:Class>
        # Troviamo la fine del blocco: il prossimo </owl:Class>
        start = match.start()
        end = rdf_content.find("</owl:Class>", start)
        if end == -1:
            print(f"  [WARN] Fine blocco non trovata per: {skab_name}")
            continue

        new_triple = (
            f'  <JobD:{importance_prop} rdf:resource="{job_uri}"/>\n'
        )
        rdf_content = rdf_content[:end] + new_triple + rdf_content[end:]

    return rdf_content


def soc_from_filename(filename: str) -> str:
    """
    Estrae il codice SOC dal nome del file xlsx.
    Es: 'Skills_33-9011-00_csv.xlsx'  →  '33-9011.00'
        'Abilities_47-2061-00_csv.xlsx' →  '47-2061.00'
    """
    m = re.search(r'(\d{2}-\d{4}-\d{2})', filename)
    if m:
        raw = m.group(1)          # es. '33-9011-00'
        parts = raw.rsplit("-", 1)  # ['33-9011', '00']
        return f"{parts[0]}.{parts[1]}"
    return None


def collect_job_folders(jobs_dir: str) -> list[dict]:
    """
    Scandisce `jobs_dir` e restituisce una lista di dizionari, uno per cartella,
    con i percorsi ai 4 file richiesti e il nome del job.
    Le cartelle vengono elaborate in ordine alfabetico.
    Cartelle con file mancanti vengono saltate con un avviso.
    """
    jobs_dir = Path(jobs_dir)
    if not jobs_dir.is_dir():
        sys.exit(f"[ERRORE] La cartella '{jobs_dir}' non esiste.")

    jobs = []
    for folder in sorted(jobs_dir.iterdir()):
        if not folder.is_dir():
            continue

        # Cerca i file xlsx (nomi fissi ma con SOC variabile)
        skills_files    = list(folder.glob("Skills_*.xlsx"))
        abilities_files = list(folder.glob("Abilities_*.xlsx"))
        desc_file       = folder / "desc.txt"
        labels_file     = folder / "label.txt"

        missing = []
        if not skills_files:    missing.append("Skills_*.xlsx")
        if not abilities_files: missing.append("Abilities_*.xlsx")
        if not desc_file.exists():   missing.append("desc.txt")
        if not labels_file.exists(): missing.append("label.txt")

        if missing:
            print(f"[WARN] Cartella '{folder.name}' saltata — file mancanti: {', '.join(missing)}")
            continue

        skills_path    = skills_files[0]
        abilities_path = abilities_files[0]

        # SOC dal nome del file Skills
        soc = soc_from_filename(skills_path.name)
        if soc is None:
            print(f"[WARN] Cartella '{folder.name}' saltata — impossibile estrarre SOC da '{skills_path.name}'")
            continue

        jobs.append({
            "job_name":   sanitize_job_name(folder.name),  # sanitizzato per URI valido
            "soc":        soc,
            "skills":     str(skills_path),
            "abilities":  str(abilities_path),
            "desc":       str(desc_file),
            "labels":     str(labels_file),
        })

    return jobs


def process_single_job(rdf_content: str, job_name: str, soc: str,
                        skills_path: str, abilities_path: str,
                        desc_path: str, labels_path: str) -> tuple[str, int, int]:
    """
    Elabora un singolo job e restituisce (rdf_content_aggiornato, jde_start, jde_end).
    """
    skill_entries   = read_xlsx_scores(skills_path)
    ability_entries = read_xlsx_scores(abilities_path)
    print(f"         Skills: {len(skill_entries)},  Abilities: {len(ability_entries)}")

    with open(desc_path, "r", encoding="utf-8") as f:
        onet_description = f.read().strip()

    with open(labels_path, "r", encoding="utf-8") as f:
        raw_labels = f.read().strip()
    titles_list = [t.strip() for t in raw_labels.split(",") if t.strip()]
    label       = titles_list[0] if titles_list else job_name.replace("_", " ")
    onet_titles = "Sample of reported job titles: " + ", ".join(titles_list)

    all_entries = sorted(skill_entries + ability_entries, key=lambda x: -x[0])

    max_jde   = find_max_jde(rdf_content)
    jde_start = max_jde + 1
    print(f"         jde di partenza: jde{jde_start}")

    job_block, jde_blocks_str, skab_importance = build_job_rdf(
        job_name=job_name,
        soc_code=soc,
        label=label,
        onet_titles=onet_titles,
        onet_description=onet_description,
        entries=all_entries,
        jde_start=jde_start,
    )

    comment = (
        f"\n<!-- Job aggiunto da add_job_to_ontology.py | SOC: {soc} | Nome: {job_name} -->\n"
    )

    # ── Inserimento 1: owl:Class del Job ─────────────────────────────────────
    # Va inserito subito DOPO l'ultimo </owl:Class> del blocco JobList#,
    # cioè prima della prima classe di un altro namespace (es. RientraOnt3Merged).
    # Strategia: troviamo l'ultima occorrenza di un JobList owl:Class nel file,
    # poi inseriamo subito dopo il suo </owl:Class> di chiusura.
    last_joblist_class = NS_JL.rstrip("#")   # "http://www.stiima.cnr.it/JobList"
    # Trova l'ultima owl:Class rdf:about che inizia con JobList#
    # (escludendo Job e Job_Descriptor che sono le classi base)
    pattern_job_class = r'<owl:Class rdf:about="' + re.escape(NS_JL)
    matches = list(re.finditer(pattern_job_class, rdf_content))
    # Filtra solo i job reali (non Job o Job_Descriptor)
    real_job_matches = [
        m for m in matches
        if not re.match(
            r'<owl:Class rdf:about="' + re.escape(NS_JL) + r'(Job|Job_Descriptor)"',
            rdf_content[m.start():m.start()+80]
        )
    ]

    if real_job_matches:
        # Posizione dell'ultimo JobList job class nel file
        last_match_start = real_job_matches[-1].start()
        # Trovare il </owl:Class> che chiude quel blocco
        close_tag = "</owl:Class>"
        close_pos = rdf_content.find(close_tag, last_match_start)
        insert_after = close_pos + len(close_tag)
        rdf_content = (
            rdf_content[:insert_after]
            + comment
            + job_block
            + "\n"
            + rdf_content[insert_after:]
        )
    else:
        # Fallback: prima del tag di chiusura del documento
        print("  [WARN] Nessun job JobList trovato come ancora — inserimento in fondo al file.")
        rdf_content = rdf_content.replace("</rdf:RDF>", comment + job_block + "\n\n</rdf:RDF>")

    # ── Inserimento 2: owl:NamedIndividual jde ────────────────────────────────
    # I jde vanno inseriti insieme agli altri jde esistenti,
    # cioè prima del PRIMO owl:NamedIndividual jde già presente.
    first_jde_pattern = r'<owl:NamedIndividual rdf:about="' + re.escape(NS_JL) + r'jde\d+">'
    first_jde_match = re.search(first_jde_pattern, rdf_content)

    if first_jde_match:
        insert_before_jde = first_jde_match.start()
        rdf_content = (
            rdf_content[:insert_before_jde]
            + jde_blocks_str
            + "\n\n"
            + rdf_content[insert_before_jde:]
        )
    else:
        # Fallback: in fondo, prima di </rdf:RDF>
        print("  [WARN] Nessun jde esistente trovato come ancora — inserimento jde in fondo.")
        rdf_content = rdf_content.replace("</rdf:RDF>", jde_blocks_str + "\n\n</rdf:RDF>")

    # ── Aggiornamento classi SkAb con proprietà di importanza ────────────────
    rdf_content = inject_importance_into_skab(rdf_content, job_name, skab_importance)

    jde_end = jde_start + len(all_entries) - 1
    return rdf_content, jde_start, jde_end


def main():
    parser = argparse.ArgumentParser(
        description="Aggiunge uno o più Job all'ontologia Rientra RDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Modalità singolo job:\n"
            "  %(prog)s --rdf Rientra.rdf --skills Skills_33-9011-00_csv.xlsx\n"
            "           --abilities Abilities_33-9011-00_csv.xlsx\n"
            "           --desc desc.txt --labels label.txt --soc 33-9011.00\n"
            "           --job-name Animal_control_workers --output out.rdf\n\n"
            "Modalità batch (cartella con sottocartelle):\n"
            "  %(prog)s --rdf Rientra.rdf --jobs-dir jobs/ --output out.rdf\n"
        )
    )
    parser.add_argument("--rdf",       required=True, help="File RDF/OWL di input")

    # --- Modalità esportazione job ---
    parser.add_argument("--export-jobs", default=None, metavar="OUTPUT.csv",
                        help="Esporta nome e descrizione di tutti i job (namespace NS_JL) in un CSV. "
                             "Non modifica l'ontologia.")
    parser.add_argument("--deduplicate", action="store_true", default=False,
                        help="Controlla e rimuove eventuali owl:Class duplicate nel namespace NS_JL. "
                             "Salva il risultato in --output (default: <rdf>_dedup.rdf).")
    parser.add_argument("--output",    default=None,  help="File RDF di output")

    # --- Modalità batch ---
    parser.add_argument("--jobs-dir",  default=None,
                        help="Cartella contenente una sottocartella per ogni job")

    # --- Modalità singolo job ---
    parser.add_argument("--skills",    default=None, help="File XLSX Skills O*NET")
    parser.add_argument("--abilities", default=None, help="File XLSX Abilities O*NET")
    parser.add_argument("--desc",      default=None, help="File TXT descrizione")
    parser.add_argument("--labels",    default=None, help="File TXT titoli alternativi")
    parser.add_argument("--soc",       default=None, help="Codice SOC (es. 33-9011.00)")
    parser.add_argument("--job-name",  default=None, help="Nome Job nell'ontologia")

    args = parser.parse_args()

    # --- Determina la modalità ---
    batch_mode  = args.jobs_dir is not None
    single_mode = args.skills is not None
    export_mode = args.export_jobs is not None
    dedup_mode  = args.deduplicate

    if not export_mode and not dedup_mode:
        if batch_mode and single_mode:
            sys.exit("[ERRORE] Usa --jobs-dir OPPURE i parametri singoli (--skills, --abilities...), non entrambi.")
        if not batch_mode and not single_mode:
            sys.exit("[ERRORE] Specifica --jobs-dir per la modalità batch, oppure --skills/--abilities/--desc/--labels/--soc per il singolo job.")

    # --- Output path ---
    if args.output is None:
        p = Path(args.rdf)
        args.output = str(p.with_name(p.stem + "_updated" + p.suffix))

    # --- Legge l'ontologia ---
    print(f"[INFO] Lettura ontologia: {args.rdf}")
    with open(args.rdf, "r", encoding="utf-8", errors="replace") as f:
        rdf_content = f.read()

    # ================================================================
    # MODALITÀ EXPORT JOBS
    # ================================================================
    if export_mode:
        export_jobs_from_rdf(rdf_content, args.export_jobs)
        sys.exit(0)

    # ================================================================
    # MODALITÀ DEDUPLICA
    # ================================================================
    if dedup_mode:
        dedup_output = args.output
        if dedup_output is None:
            p = Path(args.rdf)
            dedup_output = str(p.with_name(p.stem + "_dedup" + p.suffix))
        cleaned, dupes = find_and_remove_duplicate_jobs(rdf_content)
        if dupes:
            print(f"[INFO] Trovati e rimossi {len(dupes)} blocchi duplicati nel namespace NS_JL:")
            for uri in dupes:
                print(f"       - {uri}")
            with open(dedup_output, "w", encoding="utf-8") as f:
                f.write(cleaned)
            print(f"[OK] Ontologia deduplicata salvata in: {dedup_output}")
        else:
            print("[OK] Nessun duplicato trovato nel namespace NS_JL.")
        sys.exit(0)

    # ── Rimozione duplicati prima di aggiungere nuovi job ────────────────────
    rdf_content, dupes = find_and_remove_duplicate_jobs(rdf_content)
    if dupes:
        print(f"[WARN] Rimossi {len(dupes)} job duplicati dall'ontologia prima dell'elaborazione:")
        for uri in dupes:
            print(f"       - {uri}")

    # ================================================================
    # MODALITÀ BATCH
    # ================================================================
    if batch_mode:
        jobs = collect_job_folders(args.jobs_dir)
        if not jobs:
            sys.exit("[ERRORE] Nessuna cartella valida trovata in --jobs-dir.")

        print(f"\n[INFO] {len(jobs)} job trovati in '{args.jobs_dir}':")
        for j in jobs:
            print(f"       - {j['job_name']}  (SOC: {j['soc']})")
        print()

        summary = []
        for i, job in enumerate(jobs, 1):
            print(f"[{i}/{len(jobs)}] Elaborazione: {job['job_name']}  (SOC: {job['soc']})")
            rdf_content, jde_start, jde_end = process_single_job(
                rdf_content=rdf_content,
                job_name=job["job_name"],
                soc=job["soc"],
                skills_path=job["skills"],
                abilities_path=job["abilities"],
                desc_path=job["desc"],
                labels_path=job["labels"],
            )
            summary.append((job["job_name"], job["soc"], jde_start, jde_end))
            print(f"         ✓ jde{jde_start}..jde{jde_end}  ({jde_end - jde_start + 1} descrittori)")

        print(f"\n[INFO] Scrittura output: {args.output}")
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rdf_content)

        print(f"\n{'='*60}")
        print(f"  RIEPILOGO — {len(summary)} job aggiunti")
        print(f"{'='*60}")
        for job_name, soc, s, e in summary:
            print(f"  {job_name:45s}  SOC:{soc}  jde{s}..jde{e}")
        print(f"{'='*60}")
        print(f"  Output: {args.output}")

    # ================================================================
    # MODALITÀ SINGOLO JOB
    # ================================================================
    else:
        # Validazione argomenti obbligatori
        missing = [a for a, v in [("--abilities", args.abilities),
                                   ("--desc", args.desc),
                                   ("--labels", args.labels),
                                   ("--soc", args.soc)] if v is None]
        if missing:
            sys.exit(f"[ERRORE] Argomenti mancanti per la modalità singolo job: {', '.join(missing)}")

        # Deriva il nome del Job se non fornito
        if args.job_name is None:
            args.job_name = "Job_" + re.sub(r"[^A-Za-z0-9]", "_", args.soc)
            print(f"[INFO] --job-name non fornito, uso: {args.job_name}")

        # Sanitizza sempre il job_name per garantire un URI valido
        original_name = args.job_name
        args.job_name = sanitize_job_name(args.job_name)
        if args.job_name != original_name:
            print(f"[INFO] --job-name sanitizzato: '{original_name}' → '{args.job_name}'"
                  f"  (spazi/caratteri speciali rimpiazzati con _)")

        print(f"[INFO] Job: {args.job_name}  (SOC: {args.soc})")
        rdf_content, jde_start, jde_end = process_single_job(
            rdf_content=rdf_content,
            job_name=args.job_name,
            soc=args.soc,
            skills_path=args.skills,
            abilities_path=args.abilities,
            desc_path=args.desc,
            labels_path=args.labels,
        )

        print(f"[INFO] Scrittura output: {args.output}")
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rdf_content)

        print(f"\n[OK] Fatto!")
        print(f"     Job '{args.job_name}' aggiunto con {jde_end - jde_start + 1} Job_Descriptor (jde{jde_start}..jde{jde_end})")
        print(f"     Output salvato in: {args.output}")


if __name__ == "__main__":
    main()