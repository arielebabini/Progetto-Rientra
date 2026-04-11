"""
rdb2rdf_step2.py
================
Step 2 del progetto Rientra@: RDB2RDF con matching verso l'ontologia principale.

Dataset in ingresso:
  - Tabella PostgreSQL  : ext_job  (ext01…ext09)
    → creare con: psql -U postgres -d rientra_db -f rientra_ext_jobs.sql
  - Ontologia           : Rientra.rdf  (namespace http://www.stiima.cnr.it/JobList#)

Strategie di matching:
  S1 — String Matching   : Jaccard + Overlap + Levenshtein (baseline lessicale)
  S2 — BERT base         : bert-base-uncased, embedding [CLS], cosine similarity
  S3 — BioBERT           : dmis-lab/biobert-base-cased-v1.2, embedding [CLS], cosine similarity
  S4 — MiniLM            : all-MiniLM-L6-v2 via sentence-transformers (riferimento)

Nota sui modelli BERT "raw":
  BERT base e BioBERT non sono modelli sentence-level nativi come MiniLM.
  Per ricavare un embedding di frase si usa il token [CLS] dell'ultimo hidden
  state — tecnica standard per task di classificazione e similarità con BERT.
  BioBERT è BERT fine-tuned su letteratura biomedica (PubMed + PMC): non è
  il dominio ideale per job matching, ma è incluso per confronto metodologico.

Requisiti:
    pip install psycopg2-binary rdflib rich transformers torch scikit-learn
    pip install sentence-transformers   # per S4 (MiniLM)

Uso:
    python rdb2rdf_step2.py
"""

import os
import sys
import numpy as np
from datetime import datetime

import psycopg2
import psycopg2.extras
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, XSD, OWL

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich import box
from rich.text import Text
from rich.rule import Rule

console = Console()

# ─────────────────────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "rientra_db",
    "user":     "postgres",
    "password": "postgres",
}

ONTOLOGY_FILE = "Rientra.rdf"
OUTPUT_DIR    = "output"

JOBLIST = Namespace("http://www.stiima.cnr.it/JobList#")
RIENTRA = Namespace("https://www.stiima.cnr.it/rientra#")

# Soglie cosine similarity per i modelli NLP
# (i modelli BERT raw tendono a score più bassi di MiniLM per sentence similarity)
S1_THRESHOLD    = 0.12
BERT_THRESHOLD  = 0.70   # BERT base e BioBERT: soglia più alta perché [CLS] è meno discriminante
MINILM_THRESHOLD = 0.50  # MiniLM: fine-tuned per sentence similarity, score più affidabili

# Modelli da usare
MODELS = {
    "S2_BERT":    "bert-base-uncased",
    "S3_BioBERT": "dmis-lab/biobert-base-cased-v1.2",
    "S4_MiniLM":  "all-MiniLM-L6-v2",   # via sentence-transformers
}


# ─────────────────────────────────────────────────────────────
# HELPERS VISIVI
# ─────────────────────────────────────────────────────────────

def score_color(score: float) -> str:
    if score >= 0.85: return "bold green"
    if score >= 0.70: return "green"
    if score >= 0.50: return "yellow"
    if score >= 0.30: return "orange3"
    return "red"

def score_bar(score: float, width: int = 8) -> str:
    filled = round(score * width)
    return "█" * filled + "░" * (width - filled)


# ═════════════════════════════════════════════════════════════
# UTILITÀ DB
# ═════════════════════════════════════════════════════════════

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def fetch_all(sql: str, params=None) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

def test_connection() -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                v = cur.fetchone()[0]
        console.print(f"  [bold green]✓[/] PostgreSQL [dim]{v[:60]}...[/]")
        return True
    except Exception as e:
        console.print(f"  [bold red]✗[/] Errore connessione: [red]{e}[/]")
        return False


# ═════════════════════════════════════════════════════════════
# ESTRAZIONE VOCABOLARIO DALL'ONTOLOGIA
# ═════════════════════════════════════════════════════════════

def extract_ontology_jobs(onto_graph: Graph) -> list[dict]:
    jobs = []
    for s, _, _ in onto_graph.triples((None, RDF.type, OWL.Class)):
        if not str(s).startswith(str(JOBLIST)):
            continue
        local = str(s).split("#")[1]
        if local in ("Job", "Job_Descriptor"):
            continue

        label = str(onto_graph.value(s, RDFS.label) or "").strip()
        titles, desc = "", ""
        for pred, obj in onto_graph.predicate_objects(s):
            ps = str(pred)
            if "Net_job_titles" in ps or "job_titles" in ps:
                titles = str(obj)
            if "Net_short_description" in ps or "short_description" in ps:
                desc = str(obj)

        if titles and ":" in titles:
            titles = titles.split(":", 1)[1].strip()

        display = label or local.replace("_", " ")
        jobs.append({
            "uri":         str(s),
            "local_name":  local,
            "label":       display,
            "titles":      titles,
            "description": desc,
        })

    jobs.sort(key=lambda x: x["label"])
    return jobs

def _build_onto_text(j: dict) -> str:
    """Testo composito per l'ontologia: label + titoli alternativi + descrizione."""
    parts = [j["label"]]
    if j["titles"]:
        parts.append(j["titles"])
    if j["description"]:
        parts.append(j["description"])
    return " ".join(parts)


# ═════════════════════════════════════════════════════════════
# STRATEGIA 1 — STRING MATCHING
# ═════════════════════════════════════════════════════════════

def _norm(s: str) -> str:
    return s.lower().strip()

def _jaccard(a: str, b: str) -> float:
    a, b = set(_norm(a).split()), set(_norm(b).split())
    return len(a & b) / len(a | b) if (a | b) else 1.0

def _overlap(a: str, b: str) -> float:
    a, b = set(_norm(a).split()), set(_norm(b).split())
    return len(a & b) / min(len(a), len(b)) if (a and b) else 0.0

def _levenshtein(s1: str, s2: str) -> float:
    s1, s2 = _norm(s1), _norm(s2)
    m, n = len(s1), len(s2)
    if not m and not n:
        return 1.0
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[:], i
        for j in range(1, n + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            dp[j] = min(prev[j] + 1, dp[j-1] + 1, prev[j-1] + cost)
    return 1.0 - dp[n] / max(m, n)

def _combined(a: str, b: str) -> float:
    return 0.5 * _jaccard(a, b) + 0.3 * _overlap(a, b) + 0.2 * _levenshtein(a, b)

def s1_match_one(title: str, onto_jobs: list[dict]) -> dict | None:
    best, bj, bv = 0.0, None, None
    for j in onto_jobs:
        cands = [j["label"]]
        if j["titles"]:
            cands += [t.strip() for t in j["titles"].split(",") if t.strip()]
        for c in cands:
            sc = _combined(title, c)
            if sc > best:
                best, bj, bv = sc, j, c
    if best >= S1_THRESHOLD:
        return {"job": bj, "score": best, "via": bv}
    return None

def run_string_matching(db_jobs: list[dict], onto_jobs: list[dict]) -> list[dict]:
    results = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  BarColumn(), TaskProgressColumn(),
                  console=console, transient=True) as p:
        task = p.add_task("  Calcolo...", total=len(db_jobs))
        for r in db_jobs:
            results.append({"id": r["id"], "title": r["title"],
                            "match_s1": s1_match_one(r["title"], onto_jobs)})
            p.advance(task)
    return results


# ═════════════════════════════════════════════════════════════
# COSINE SIMILARITY — funzione centrale condivisa da S2 e S3
# ═════════════════════════════════════════════════════════════

def cosine_similarity_matrix(query_emb: np.ndarray,
                              corpus_embs: np.ndarray) -> np.ndarray:
    """
    Calcola la cosine similarity tra un vettore query e una matrice di vettori corpus.

    Formula:
        cos(θ) = (A · B) / (‖A‖ · ‖B‖)

    dove A è il vettore del job nel DB e B è il vettore di una professione O*NET.

    Il risultato è compreso tra -1 e 1:
      1.0  → testi identici nel significato
      0.0  → testi ortogonali (nessuna relazione semantica)
     -1.0  → testi opposti (raro con embedding linguistici)

    Per embedding BERT non negativi il range effettivo è [0, 1].
    """
    query_norm  = query_emb / (np.linalg.norm(query_emb) + 1e-9)
    corpus_norm = corpus_embs / (np.linalg.norm(corpus_embs, axis=1, keepdims=True) + 1e-9)
    return corpus_norm.dot(query_norm)


# ═════════════════════════════════════════════════════════════
# EMBEDDING CON BERT RAW (BERT base e BioBERT)
# ═════════════════════════════════════════════════════════════

def get_bert_embedding(text: str, tokenizer, model,
                       max_length: int = 512) -> np.ndarray:
    """
    Calcola l'embedding di una frase con un modello BERT raw.

    Strategia: estrae il vettore del token [CLS] dall'ultimo hidden state.
    Il token [CLS] (Classification) è il primo token di ogni sequenza BERT
    ed è stato progettato per catturare una rappresentazione aggregata
    dell'intera sequenza — per questo è la scelta standard per embedding
    di frasi con BERT non fine-tuned su sentence similarity.

    Alternativa possibile: mean pooling su tutti i token non-padding,
    che spesso produce embedding leggermente più stabili ma richiede
    la gestione della attention mask.
    """
    import torch
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
        padding=True,
    )
    with torch.no_grad():
        outputs = model(**inputs)
    # outputs.last_hidden_state: shape [batch, seq_len, hidden_size]
    # [:, 0, :] → token [CLS], primo token della sequenza
    cls_embedding = outputs.last_hidden_state[:, 0, :].squeeze().numpy()
    return cls_embedding


def run_bert_matching(db_jobs: list[dict],
                      onto_jobs: list[dict],
                      model_name: str,
                      strategy_key: str,
                      threshold: float) -> tuple[list[dict], str]:
    """
    Esegue il matching con un modello BERT raw (bert-base o biobert).
    Restituisce (risultati, nome_modello) oppure (None, None) se il modello
    non è disponibile.
    """
    try:
        from transformers import AutoTokenizer, AutoModel

        with console.status(f"  Caricamento [cyan]{model_name}[/]...", spinner="dots"):
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model     = AutoModel.from_pretrained(model_name)
            model.eval()
        console.print(f"  [bold green]✓[/] Modello caricato: [cyan]{model_name}[/]")

        onto_texts = [_build_onto_text(j) for j in onto_jobs]
        db_texts   = [f"{r['title']}. {r.get('description', '')}" for r in db_jobs]

        # Pre-calcola embedding O*NET (una volta sola)
        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      BarColumn(), TaskProgressColumn(),
                      console=console, transient=True) as p:
            t1 = p.add_task("  Encoding O*NET...", total=len(onto_texts))
            onto_embs = []
            for txt in onto_texts:
                onto_embs.append(get_bert_embedding(txt, tokenizer, model))
                p.advance(t1)
        onto_embs = np.vstack(onto_embs)   # shape: [n_onto, hidden_size]

        # Calcola embedding per ogni job del DB e cosine similarity
        results = []
        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      BarColumn(), TaskProgressColumn(),
                      console=console, transient=True) as p:
            t2 = p.add_task("  Cosine similarity...", total=len(db_jobs))
            for i, row in enumerate(db_jobs):
                q_emb = get_bert_embedding(db_texts[i], tokenizer, model)
                sims  = cosine_similarity_matrix(q_emb, onto_embs)
                idx   = int(np.argmax(sims))
                sc    = float(sims[idx])
                m = {"job": onto_jobs[idx], "score": sc} if sc >= threshold else None
                results.append({
                    "id":        row["id"],
                    "title":     row["title"],
                    "match":     m,
                    "score_raw": sc,
                    "strategy":  strategy_key,
                })
                p.advance(t2)

        return results, model_name

    except Exception as e:
        console.print(f"  [yellow]⚠[/] {model_name} non disponibile: [dim]{e}[/]")
        return None, None


# ═════════════════════════════════════════════════════════════
# EMBEDDING CON SENTENCE-TRANSFORMERS (MiniLM — S4)
# ═════════════════════════════════════════════════════════════

def run_minilm_matching(db_jobs: list[dict],
                        onto_jobs: list[dict],
                        threshold: float) -> tuple[list[dict], str]:
    """
    Esegue il matching con sentence-transformers/all-MiniLM-L6-v2.
    A differenza di BERT raw, MiniLM è fine-tuned per sentence similarity:
    il suo .encode() produce già embedding ottimizzati per cosine similarity,
    senza bisogno di estrarre manualmente il token [CLS].
    La cosine similarity viene comunque calcolata esplicitamente con la
    nostra funzione cosine_similarity_matrix per uniformità metodologica.
    """
    try:
        from sentence_transformers import SentenceTransformer

        model_name = MODELS["S4_MiniLM"]
        with console.status(f"  Caricamento [cyan]{model_name}[/]...", spinner="dots"):
            model = SentenceTransformer(model_name)
        console.print(f"  [bold green]✓[/] Modello caricato: [cyan]{model_name}[/]")

        onto_texts = [_build_onto_text(j) for j in onto_jobs]
        db_texts   = [f"{r['title']}. {r.get('description', '')}" for r in db_jobs]

        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      BarColumn(), TaskProgressColumn(),
                      console=console, transient=True) as p:
            t1 = p.add_task("  Encoding O*NET...", total=1)
            onto_embs = model.encode(onto_texts, convert_to_numpy=True)
            p.advance(t1)

            results = []
            t2 = p.add_task("  Cosine similarity...", total=len(db_jobs))
            for i, row in enumerate(db_jobs):
                q_emb = model.encode(db_texts[i], convert_to_numpy=True)
                # Cosine similarity calcolata esplicitamente (stessa formula di S2/S3)
                sims  = cosine_similarity_matrix(q_emb, onto_embs)
                idx   = int(np.argmax(sims))
                sc    = float(sims[idx])
                m = {"job": onto_jobs[idx], "score": sc} if sc >= threshold else None
                results.append({
                    "id":        row["id"],
                    "title":     row["title"],
                    "match":     m,
                    "score_raw": sc,
                    "strategy":  "S4_MiniLM",
                })
                p.advance(t2)

        return results, model_name

    except Exception as e:
        console.print(f"  [yellow]⚠[/] MiniLM non disponibile: [dim]{e}[/]")
        return None, None


# ═════════════════════════════════════════════════════════════
# OUTPUT RICH
# ═════════════════════════════════════════════════════════════

def print_ontology_table(onto_jobs: list[dict]):
    t = Table(title="Professioni O*NET nell'ontologia",
              box=box.ROUNDED, header_style="bold cyan",
              title_style="bold white", show_lines=False)
    t.add_column("#",           style="dim",       width=3,  justify="right")
    t.add_column("URI locale",  style="cyan",       width=46)
    t.add_column("Label O*NET", style="bold white", width=38)
    t.add_column("Desc.",       justify="center",   width=6)
    for i, j in enumerate(onto_jobs, 1):
        t.add_row(str(i), j["local_name"], j["label"],
                  "[green]✓[/]" if j["description"] else "[red]✗[/]")
    console.print(t)


def print_db_table(db_jobs: list[dict]):
    t = Table(title="Lavori nel DB esterno (ext_job)",
              box=box.ROUNDED, header_style="bold magenta",
              title_style="bold white", show_lines=False)
    t.add_column("ID",    style="bold magenta", width=6)
    t.add_column("Titolo",                      width=30)
    t.add_column("Descrizione (estratto)",      width=62)
    for r in db_jobs:
        desc = (r.get("description") or "")[:60] + "…"
        t.add_row(r["id"], r["title"], f"[dim]{desc}[/]")
    console.print(t)


def _score_cell(score: float | None, raw: float = 0.0) -> tuple[Text, Text]:
    """Restituisce (cella_label_aggiuntiva, cella_score) per la tabella."""
    if score is not None:
        bar = Text()
        bar.append(f"{score:.3f}\n", style=score_color(score))
        bar.append(score_bar(score),  style=score_color(score))
        return Text(""), bar
    else:
        lbl = Text(f"(raw: {raw:.3f})", style="dim red")
        bar = Text()
        bar.append(f"{raw:.3f}\n", style="dim red")
        bar.append(score_bar(raw),  style="dim red")
        return lbl, bar


def print_full_comparison(s1_res: list[dict],
                          nlp_results: dict[str, list[dict]],
                          model_names: dict[str, str]):
    """
    Tabella unica con S1 + tutti i modelli NLP disponibili, una colonna per modello.
    nlp_results: { "S2_BERT": [...], "S3_BioBERT": [...], "S4_MiniLM": [...] }
    model_names: { "S2_BERT": "bert-base-uncased", ... }
    """
    # Indici per lookup rapido per ogni strategia
    idx = {key: {r["id"]: r for r in res}
           for key, res in nlp_results.items() if res}

    available_strategies = [k for k in ["S2_BERT", "S3_BioBERT", "S4_MiniLM"]
                            if k in idx]

    # Costruisce header dinamico
    title_parts = ["S1 String"] + [
        model_names.get(k, k).split("/")[-1][:18]
        for k in available_strategies
    ]
    t = Table(
        title="Confronto strategie di matching · cosine similarity",
        box=box.SIMPLE_HEAD,
        show_lines=True,
        header_style="bold white on dark_blue",
        title_style="bold white",
        expand=True,
    )
    t.add_column("ID",       style="bold", width=6,  justify="center")
    t.add_column("Titolo DB",              width=26)
    t.add_column("S1 — Match",             width=28)
    t.add_column("Score S1", justify="center", width=14)

    for k in available_strategies:
        short = model_names.get(k, k).split("/")[-1][:20]
        t.add_column(f"{k[:2]} — {short}", width=28)
        t.add_column(f"Score {k[:2]}", justify="center", width=14)

    t.add_column("Verdetto", justify="center", width=10)

    for r in s1_res:
        rid = r["id"]
        m1  = r.get("match_s1")

        # S1
        if m1:
            s1_cell = Text()
            s1_cell.append(m1["job"]["label"] + "\n")
            s1_cell.append(f"via: {m1['via'][:24]}", style="dim")
            s1_sc = Text()
            s1_sc.append(f"{m1['score']:.3f}\n", style=score_color(m1["score"]))
            s1_sc.append(score_bar(m1["score"]),  style=score_color(m1["score"]))
        else:
            s1_cell = Text("— nessun match —", style="dim")
            s1_sc   = Text("—", style="dim")

        row_cells = [rid, r["title"], s1_cell, s1_sc]

        # NLP strategies
        nlp_matches = []
        for k in available_strategies:
            r2   = idx[k].get(rid, {})
            m2   = r2.get("match")
            raw  = r2.get("score_raw", 0.0)
            if m2:
                cell = Text(m2["job"]["label"])
                sc   = Text()
                sc.append(f"{m2['score']:.3f}\n", style=score_color(m2["score"]))
                sc.append(score_bar(m2["score"]),  style=score_color(m2["score"]))
                nlp_matches.append(m2["job"]["uri"])
            else:
                cell = Text()
                cell.append("— sotto soglia —\n", style="dim")
                cell.append(f"(raw: {raw:.3f})", style="dim red")
                sc   = Text()
                sc.append(f"{raw:.3f}\n", style="dim red")
                sc.append(score_bar(raw),  style="dim red")
                nlp_matches.append(None)
            row_cells += [cell, sc]

        # Verdetto: consensus tra i modelli che hanno trovato un match
        valid = [u for u in nlp_matches if u]
        if not valid and not m1:
            verdetto = Text("✗ no", style="bold red")
        elif len(set(valid)) == 1 and len(valid) == len(available_strategies):
            verdetto = Text("✓ tutti", style="bold green")
        elif len(set(valid)) == 1 and valid:
            verdetto = Text("~ parz.", style="yellow")
        elif valid:
            verdetto = Text("≠ div.", style="orange3")
        else:
            verdetto = Text("S1 only", style="magenta")

        row_cells.append(verdetto)
        t.add_row(*row_cells)

    console.print(t)
    console.print(
        "  [bold green]✓ tutti[/] tutti i modelli NLP concordano  "
        "[yellow]~ parz.[/] accordo parziale  "
        "[orange3]≠ div.[/] modelli divergono  "
        "[magenta]S1 only[/] solo string match  "
        "[bold red]✗ no[/] nessun match\n"
    )


def print_cosine_detail(nlp_results: dict[str, list[dict]],
                        model_names: dict[str, str],
                        onto_jobs: list[dict]):
    """
    Tabella dettaglio cosine similarity: per ogni job DB mostra lo score
    con TUTTE le professioni O*NET, per ogni modello disponibile.
    Utile per capire la distribuzione degli score e validare le soglie.
    """
    console.print(Rule("[dim]Dettaglio score cosine per tutti i candidati O*NET[/]", style="dim"))
    console.print("[dim]  (i valori in verde sono quelli scelti come match migliore)[/]\n")

    available = [k for k in ["S2_BERT", "S3_BioBERT", "S4_MiniLM"]
                 if k in nlp_results and nlp_results[k]]

    for strategy_key in available:
        res_list = nlp_results[strategy_key]
        mname    = model_names.get(strategy_key, strategy_key)
        console.print(f"  [bold cyan]{strategy_key}[/] · [dim]{mname}[/]")

        t = Table(box=box.MINIMAL, show_header=True,
                  header_style="dim", show_lines=False)
        t.add_column("Professione O*NET", width=38)
        for r in res_list:
            t.add_column(r["title"][:14], justify="right", width=10)

        # Nota: il dettaglio per O*NET richiede gli score completi
        # che non sono salvati nella struttura corrente.
        # Mostriamo solo il best match per job.
        idx_map = {r["id"]: r for r in res_list}
        for j in onto_jobs:
            row_vals = [j["label"][:37]]
            for r in res_list:
                m   = r.get("match")
                raw = r.get("score_raw", 0.0)
                if m and m["job"]["uri"] == j["uri"]:
                    row_vals.append(f"[bold green]{m['score']:.3f}[/]")
                elif not m and r.get("score_raw", 0) > 0:
                    # Se questo è il candidato con score più alto (anche sotto soglia)
                    row_vals.append(f"[dim]{raw:.3f}[/]")
                else:
                    row_vals.append("[dim]—[/]")
            t.add_row(*row_vals)

        console.print(t)
        console.print()


def print_summary_multi(s1_res: list[dict],
                        nlp_results: dict[str, list[dict]],
                        model_names: dict[str, str]):
    n_total = len(s1_res)
    n_s1    = sum(1 for r in s1_res if r.get("match_s1"))

    lines = [f"  Job totali nel DB  : [bold]{n_total}[/]",
             f"  Match da S1        : [bold {'green' if n_s1 else 'red'}]{n_s1}/{n_total}[/]  [dim](soglia {S1_THRESHOLD})[/]"]

    for key in ["S2_BERT", "S3_BioBERT", "S4_MiniLM"]:
        res = nlp_results.get(key)
        if not res:
            lines.append(f"  Match da {key[:2]}         : [dim]— modello non disponibile —[/]")
            continue
        thr = BERT_THRESHOLD if key in ("S2_BERT", "S3_BioBERT") else MINILM_THRESHOLD
        n   = sum(1 for r in res if r.get("match"))
        mname = model_names.get(key, key).split("/")[-1]
        lines.append(
            f"  Match da {key[:2]}         : [bold {'green' if n else 'red'}]{n}/{n_total}[/]"
            f"  [dim](soglia {thr} · {mname})[/]"
        )

    lines += [
        "",
        "  [dim]Nota: BERT base e BioBERT usano embedding [CLS] — non fine-tuned per sentence",
        "  similarity. Score tendenzialmente più bassi di MiniLM ma confrontabili tra loro.[/]",
    ]

    console.print(Panel("\n".join(lines),
                        title="[bold white]Riepilogo",
                        border_style="cyan", padding=(1, 2)))


# ═════════════════════════════════════════════════════════════
# ARRICCHIMENTO GRAFO RDF
# ═════════════════════════════════════════════════════════════

def build_enriched_graph(onto_graph, db_jobs, s1_res,
                         nlp_results: dict) -> Graph:
    g = Graph()
    g.bind("rientra", RIENTRA)
    g.bind("joblist", JOBLIST)
    g.bind("rdfs",    RDFS)
    g.bind("xsd",     XSD)
    g.bind("owl",     OWL)

    for triple in onto_graph:
        g.add(triple)

    # Indici per lookup
    nlp_idx = {key: {r["id"]: r for r in res}
               for key, res in nlp_results.items() if res}

    # Mapping chiave → nome proprietà RDF
    prop_map = {
        "S2_BERT":    ("matchedToONETJob_BERT",    "matchingScore_BERT"),
        "S3_BioBERT": ("matchedToONETJob_BioBERT", "matchingScore_BioBERT"),
        "S4_MiniLM":  ("matchedToONETJob_MiniLM",  "matchingScore_MiniLM"),
    }

    for row in db_jobs:
        rid  = row["id"]
        subj = RIENTRA[f"ExtJob_{rid}"]

        g.add((subj, RDF.type,               RIENTRA.Job))
        g.add((subj, RIENTRA.hasJobNameInDB, Literal(row["title"],  datatype=XSD.string)))
        g.add((subj, RIENTRA.hasExternalID,  Literal(rid,           datatype=XSD.string)))
        if row.get("description"):
            g.add((subj, RIENTRA.hasDescription,
                   Literal(row["description"], datatype=XSD.string)))

        # S1 — String Matching
        m1 = next((r.get("match_s1") for r in s1_res if r["id"] == rid), None)
        if m1:
            g.add((subj, RIENTRA.matchedToONETJob_S1, URIRef(m1["job"]["uri"])))
            g.add((subj, RIENTRA.matchingScore_S1,
                   Literal(round(m1["score"], 4), datatype=XSD.decimal)))
            g.add((subj, RIENTRA.matchedViaLabel_S1,
                   Literal(m1["via"], datatype=XSD.string)))

        # S2 / S3 / S4 — NLP
        for key, (prop_match, prop_score) in prop_map.items():
            r2 = nlp_idx.get(key, {}).get(rid, {})
            m  = r2.get("match")
            if m:
                g.add((subj, RIENTRA[prop_match], URIRef(m["job"]["uri"])))
                g.add((subj, RIENTRA[prop_score],
                       Literal(round(m["score"], 4), datatype=XSD.decimal)))

    return g


def save_graph(g: Graph, name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ttl = os.path.join(OUTPUT_DIR, f"{name}.ttl")
    rdf = os.path.join(OUTPUT_DIR, f"{name}.rdf")
    g.serialize(ttl, format="turtle")
    g.serialize(rdf, format="xml")

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column(style="dim")
    t.add_column(style="cyan")
    t.add_column(style="dim", justify="right")
    t.add_row("Turtle",        ttl, f"{os.path.getsize(ttl):,} bytes")
    t.add_row("RDF/XML",       rdf, f"{os.path.getsize(rdf):,} bytes")
    t.add_row("Triple totali", "",  str(len(g)))
    console.print(t)


# ═════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════

def main():
    console.print()
    console.print(Panel(
        f"[bold white]Rientra@[/] — Step 2: RDB2RDF + String Matching + NLP\n"
        f"[dim]Modelli: BERT base · BioBERT · MiniLM  |  Metrica: cosine similarity[/]\n"
        f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]",
        border_style="blue", padding=(0, 2),
    ))
    console.print()

    # ── [0] Setup ─────────────────────────────────────────────
    console.print(Rule("[bold cyan]0 · Setup[/]", style="cyan"))
    console.print()

    if not test_connection():
        sys.exit(1)

    with console.status(f"  Caricamento ontologia [cyan]{ONTOLOGY_FILE}[/]...", spinner="dots"):
        onto_graph = Graph()
        onto_graph.parse(ONTOLOGY_FILE, format="xml")
    console.print(f"  [bold green]✓[/] Ontologia: [bold]{len(onto_graph)}[/] triple")

    onto_jobs = extract_ontology_jobs(onto_graph)
    console.print(f"  [bold green]✓[/] Professioni O*NET estratte: [bold]{len(onto_jobs)}[/]")
    console.print()
    print_ontology_table(onto_jobs)
    console.print()

    # ── [1] Lettura DB ────────────────────────────────────────
    console.print(Rule("[bold magenta]1 · Lettura DB esterno[/]", style="magenta"))
    console.print()
    db_jobs = fetch_all("SELECT id, title, description FROM ext_job ORDER BY id")
    console.print(f"  [bold green]✓[/] [bold]{len(db_jobs)}[/] lavori da [cyan]ext_job[/]")
    console.print()
    print_db_table(db_jobs)
    console.print()

    # ── [2] Strategia 1 — String Matching ─────────────────────
    console.print(Rule("[bold yellow]2 · Strategia 1 — String Matching[/]", style="yellow"))
    console.print("  [dim]Jaccard (0.5) + Overlap (0.3) + Levenshtein (0.2)[/]")
    console.print()
    s1_res = run_string_matching(db_jobs, onto_jobs)
    console.print(f"  [bold green]✓[/] Completato\n")

    # ── [3] Strategia 2 — BERT base ───────────────────────────
    console.print(Rule("[bold blue]3 · Strategia 2 — BERT base · cosine similarity[/]", style="blue"))
    console.print(f"  [dim]Modello: {MODELS['S2_BERT']}  |  Embedding: token [CLS]  |  Soglia: {BERT_THRESHOLD}[/]")
    console.print()
    s2_res, s2_name = run_bert_matching(
        db_jobs, onto_jobs,
        model_name=MODELS["S2_BERT"],
        strategy_key="S2_BERT",
        threshold=BERT_THRESHOLD,
    )
    if s2_res:
        console.print(f"  [bold green]✓[/] Completato\n")
    else:
        console.print(f"  [yellow]⚠[/] Saltato — installa [cyan]transformers torch[/]\n")

    # ── [4] Strategia 3 — BioBERT ─────────────────────────────
    console.print(Rule("[bold magenta]4 · Strategia 3 — BioBERT · cosine similarity[/]", style="magenta"))
    console.print(f"  [dim]Modello: {MODELS['S3_BioBERT']}  |  Embedding: token [CLS]  |  Soglia: {BERT_THRESHOLD}[/]")
    console.print(f"  [dim]Fine-tuned su: PubMed abstracts + PMC full-text articles (dominio biomedico)[/]")
    console.print()
    s3_res, s3_name = run_bert_matching(
        db_jobs, onto_jobs,
        model_name=MODELS["S3_BioBERT"],
        strategy_key="S3_BioBERT",
        threshold=BERT_THRESHOLD,
    )
    if s3_res:
        console.print(f"  [bold green]✓[/] Completato\n")
    else:
        console.print(f"  [yellow]⚠[/] Saltato\n")

    # ── [5] Strategia 4 — MiniLM ──────────────────────────────
    console.print(Rule("[bold green]5 · Strategia 4 — MiniLM · cosine similarity[/]", style="green"))
    console.print(f"  [dim]Modello: {MODELS['S4_MiniLM']}  |  Fine-tuned per sentence similarity  |  Soglia: {MINILM_THRESHOLD}[/]")
    console.print()
    s4_res, s4_name = run_minilm_matching(db_jobs, onto_jobs, threshold=MINILM_THRESHOLD)
    if s4_res:
        console.print(f"  [bold green]✓[/] Completato\n")
    else:
        console.print(f"  [yellow]⚠[/] Saltato — installa [cyan]sentence-transformers[/]\n")

    # Raccoglie tutti i risultati disponibili
    nlp_results  = {}
    model_names  = {}
    if s2_res: nlp_results["S2_BERT"]    = s2_res;  model_names["S2_BERT"]    = s2_name
    if s3_res: nlp_results["S3_BioBERT"] = s3_res;  model_names["S3_BioBERT"] = s3_name
    if s4_res: nlp_results["S4_MiniLM"]  = s4_res;  model_names["S4_MiniLM"]  = s4_name

    # ── [6] Confronto ─────────────────────────────────────────
    console.print(Rule("[bold white]6 · Confronto strategie[/]", style="white"))
    console.print()
    if nlp_results:
        print_full_comparison(s1_res, nlp_results, model_names)
        print_summary_multi(s1_res, nlp_results, model_names)
    else:
        console.print("  [yellow]Nessun modello NLP disponibile — solo S1 (string matching)[/]")
    console.print()

    # ── [7] Grafo RDF ─────────────────────────────────────────
    console.print(Rule("[bold blue]7 · Costruzione e serializzazione grafo RDF[/]", style="blue"))
    console.print()
    with console.status("  Costruzione grafo A-Box...", spinner="dots"):
        g_final = build_enriched_graph(onto_graph, db_jobs, s1_res, nlp_results)
    console.print(f"  [bold green]✓[/] {len(db_jobs)} ExtJob aggiunti al grafo\n")

    with console.status("  Serializzazione...", spinner="dots"):
        save_graph(g_final, "rientra_ext_jobs")
    console.print()

    # ── Fine ──────────────────────────────────────────────────
    console.print(Panel(
        f"[bold green]Step 2 completato.[/]\n\n"
        f"Output → [cyan]{os.path.abspath(OUTPUT_DIR)}/[/]\n\n"
        f"[dim]Modelli usati: {', '.join(model_names.values()) or 'solo S1'}[/]\n"
        f"[dim]Prossimo step: Strategia 3 — ESCO come ponte ontologico[/]",
        border_style="green", padding=(0, 2),
    ))
    console.print()


if __name__ == "__main__":
    main()