"""
rdb2rdf_step2.py
================
Step 2 del progetto Rientra@: RDB2RDF con matching verso l'ontologia principale.

Dataset in ingresso:
  - Tabella PostgreSQL  : ext_job  (ext01…ext09)
    → creare con: psql -U postgres -d rientra_db -f rientra_ext_jobs.sql
  - Ontologia           : Rientra.rdf  (namespace http://www.stiima.cnr.it/JobList#)

Fasi eseguite:
  1. Lettura di ext_job da PostgreSQL
  2. Estrazione dinamica del vocabolario professioni dall'ontologia via rdflib
  3. Strategia 1 — String Matching  (Jaccard + Overlap + Levenshtein)
  4. Strategia 2 — NLP Similarity
       - Preferenziale: sentence-transformers (all-MiniLM-L6-v2)
       - Fallback:      scikit-learn TF-IDF + cosine similarity
  5. Arricchimento del grafo RDF con i risultati del matching
  6. Serializzazione in Turtle e RDF/XML

Requisiti minimi:
    pip install psycopg2-binary rdflib scikit-learn rich

Requisiti per NLP ottimale:
    pip install sentence-transformers

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

S1_THRESHOLD = 0.12
S2_THRESHOLD = 0.50   # alzata: sotto questa soglia il match non è affidabile
S2_TFIDF_THR = 0.05


# ─────────────────────────────────────────────────────────────
# HELPERS VISIVI
# ─────────────────────────────────────────────────────────────

def score_color(score: float) -> str:
    if score >= 0.70: return "bold green"
    if score >= 0.40: return "yellow"
    if score >= 0.20: return "orange3"
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
            "uri":        str(s),
            "local_name": local,
            "label":      display,
            "titles":     titles,
            "description": desc,
        })

    jobs.sort(key=lambda x: x["label"])
    return jobs


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
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("  Calcolo string matching...", total=len(db_jobs))
        for r in db_jobs:
            results.append({
                "id":       r["id"],
                "title":    r["title"],
                "match_s1": s1_match_one(r["title"], onto_jobs),
            })
            progress.advance(task)
    return results


# ═════════════════════════════════════════════════════════════
# STRATEGIA 2 — NLP
# ═════════════════════════════════════════════════════════════

def _build_onto_text(j: dict) -> str:
    parts = [j["label"]]
    if j["titles"]:
        parts.append(j["titles"])
    if j["description"]:
        parts.append(j["description"])
    return " ".join(parts)

def run_nlp_matching(db_jobs: list[dict], onto_jobs: list[dict]) -> tuple[list[dict], str]:
    onto_texts = [_build_onto_text(j) for j in onto_jobs]
    db_texts   = [f"{r['title']}. {r.get('description','')}" for r in db_jobs]

    # ── Tenta sentence-transformers ───────────────────────────
    try:
        from sentence_transformers import SentenceTransformer

        with console.status("  Caricamento modello sentence-transformers...", spinner="dots"):
            model = SentenceTransformer("all-MiniLM-L6-v2")
        console.print("  [bold green]✓[/] Modello: [cyan]sentence-transformers/all-MiniLM-L6-v2[/]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True,
        ) as progress:
            t1 = progress.add_task("  Encoding ontologia...", total=1)
            onto_embs = model.encode(onto_texts, convert_to_numpy=True)
            progress.advance(t1)

            results = []
            t2 = progress.add_task("  Calcolo similarità...", total=len(db_jobs))
            for i, row in enumerate(db_jobs):
                q_emb = model.encode(db_texts[i], convert_to_numpy=True)
                norms = np.linalg.norm(onto_embs, axis=1) * np.linalg.norm(q_emb)
                sims  = onto_embs.dot(q_emb) / np.where(norms == 0, 1, norms)
                idx   = int(np.argmax(sims))
                sc    = float(sims[idx])
                m = {"job": onto_jobs[idx], "score": sc} if sc >= S2_THRESHOLD else None
                results.append({
                    "id":        row["id"],
                    "title":     row["title"],
                    "match_s2":  m,
                    "score_raw": sc,
                })
                progress.advance(t2)

        return results, "sentence-transformers"

    except Exception:
        pass

    # ── Fallback: TF-IDF ─────────────────────────────────────
    console.print("  [yellow]⚠[/] sentence-transformers non disponibile → [yellow]fallback TF-IDF[/]")
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    all_texts = onto_texts + db_texts
    vec   = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    tfidf = vec.fit_transform(all_texts)
    sims  = cosine_similarity(tfidf[len(onto_texts):], tfidf[:len(onto_texts)])

    results = []
    for i, row in enumerate(db_jobs):
        idx = int(sims[i].argmax())
        sc  = float(sims[i][idx])
        m = {"job": onto_jobs[idx], "score": sc} if sc >= S2_TFIDF_THR else None
        results.append({
            "id":        row["id"],
            "title":     row["title"],
            "match_s2":  m,
            "score_raw": sc,
        })
    return results, "TF-IDF (fallback)"


# ═════════════════════════════════════════════════════════════
# OUTPUT RICH
# ═════════════════════════════════════════════════════════════

def print_ontology_table(onto_jobs: list[dict]):
    t = Table(
        title="Professioni O*NET nell'ontologia",
        box=box.ROUNDED,
        header_style="bold cyan",
        title_style="bold white",
        show_lines=False,
    )
    t.add_column("#",              style="dim",        width=3,  justify="right")
    t.add_column("URI locale",     style="cyan",        width=46)
    t.add_column("Label O*NET",    style="bold white",  width=38)
    t.add_column("Desc.",          justify="center",    width=6)

    for i, j in enumerate(onto_jobs, 1):
        has_desc = "[green]✓[/]" if j["description"] else "[red]✗[/]"
        t.add_row(str(i), j["local_name"], j["label"], has_desc)

    console.print(t)


def print_db_table(db_jobs: list[dict]):
    t = Table(
        title="Lavori nel DB esterno (ext_job)",
        box=box.ROUNDED,
        header_style="bold magenta",
        title_style="bold white",
        show_lines=False,
    )
    t.add_column("ID",                style="bold magenta", width=6)
    t.add_column("Titolo",                                  width=30)
    t.add_column("Descrizione (estratto)",                  width=62)

    for r in db_jobs:
        desc_short = (r.get("description") or "")[:60] + "…"
        t.add_row(r["id"], r["title"], f"[dim]{desc_short}[/]")

    console.print(t)


def print_matching_detail(s1_res: list[dict], s2_res: list[dict], method: str):
    s2_idx = {r["id"]: r for r in s2_res}

    t = Table(
        title=f"Confronto S1 (String Matching) vs S2 (NLP · {method})",
        box=box.SIMPLE_HEAD,
        show_lines=True,
        header_style="bold white on dark_blue",
        title_style="bold white",
        expand=True,
    )
    t.add_column("ID",         style="bold",     width=6,  justify="center")
    t.add_column("Titolo DB",                    width=28)
    t.add_column("S1 — Match",                   width=30)
    t.add_column("Score S1",   justify="center", width=16)
    t.add_column("S2 — Match",                   width=30)
    t.add_column("Score S2",   justify="center", width=16)
    t.add_column("Esito",      justify="center", width=8)

    for r in s1_res:
        rid     = r["id"]
        m1      = r.get("match_s1")
        r2      = s2_idx.get(rid, {})
        m2      = r2.get("match_s2")
        sc2_raw = r2.get("score_raw", 0.0)

        # ── S1 ───────────────────────────────────────────────
        if m1:
            s1_cell = Text()
            s1_cell.append(m1["job"]["label"] + "\n")
            s1_cell.append(f"via: {m1['via'][:28]}", style="dim")
            s1_score = Text()
            s1_score.append(f"{m1['score']:.3f}\n", style=score_color(m1["score"]))
            s1_score.append(score_bar(m1["score"]),  style=score_color(m1["score"]))
        else:
            s1_cell  = Text("— nessun match —", style="dim")
            s1_score = Text("—", style="dim")

        # ── S2 ───────────────────────────────────────────────
        if m2:
            s2_label = m2["job"]["label"]
            s2_score = Text()
            s2_score.append(f"{m2['score']:.3f}\n", style=score_color(m2["score"]))
            s2_score.append(score_bar(m2["score"]),  style=score_color(m2["score"]))
        else:
            s2_label = Text()
            s2_label.append("— sotto soglia —\n", style="dim")
            s2_label.append(f"(raw: {sc2_raw:.3f})", style="dim red")
            s2_score = Text()
            s2_score.append(f"{sc2_raw:.3f}\n", style="dim red")
            s2_score.append(score_bar(sc2_raw),  style="dim red")

        # ── Esito ─────────────────────────────────────────────
        if m1 and m2 and m1["job"]["uri"] == m2["job"]["uri"]:
            esito = Text("✓ acc.", style="bold green")
        elif m1 and m2:
            esito = Text("~ div.", style="yellow")
        elif m2 and not m1:
            esito = Text("S2 only", style="cyan")
        elif m1 and not m2:
            esito = Text("S1 only", style="magenta")
        else:
            esito = Text("✗ no", style="bold red")

        t.add_row(rid, r["title"], s1_cell, s1_score, s2_label, s2_score, esito)

    console.print(t)
    console.print(
        "  [bold green]✓ acc.[/] concordano  "
        "[yellow]~ div.[/] risultati diversi  "
        "[cyan]S2 only[/] solo NLP  "
        "[magenta]S1 only[/] solo String  "
        "[bold red]✗ no[/] nessun match affidabile\n"
    )


def print_summary(s1_res: list[dict], s2_res: list[dict]):
    s2_idx  = {r["id"]: r for r in s2_res}
    total   = len(s1_res)
    n_s1    = sum(1 for r in s1_res if r.get("match_s1"))
    n_s2    = sum(1 for r in s2_res if r.get("match_s2"))
    n_both  = sum(1 for r in s1_res
                  if r.get("match_s1") and s2_idx.get(r["id"], {}).get("match_s2"))
    n_agree = sum(
        1 for r in s1_res
        if r.get("match_s1")
        and s2_idx.get(r["id"], {}).get("match_s2")
        and r["match_s1"]["job"]["uri"] == s2_idx[r["id"]]["match_s2"]["job"]["uri"]
    )

    lines = [
        f"  Job totali nel DB              : [bold]{total}[/]",
        f"  Match trovati da S1            : [bold {'green' if n_s1 else 'red'}]{n_s1}/{total}[/]",
        f"  Match trovati da S2 (≥ {S2_THRESHOLD}) : [bold {'green' if n_s2 else 'red'}]{n_s2}/{total}[/]",
        f"  Match in entrambe le strategie : [bold]{n_both}/{total}[/]",
    ]
    if n_both:
        lines.append(
            f"  Accordo S1 = S2                : [bold green]{n_agree}/{n_both}[/]"
        )
    lines += [
        "",
        f"  [dim]Soglia S1: {S1_THRESHOLD}  |  Soglia S2: {S2_THRESHOLD}[/]",
        f"  [dim]Score S2 sotto soglia: registrato come score_raw, non inserito nel grafo come triple di matching[/]",
    ]

    console.print(Panel(
        "\n".join(lines),
        title="[bold white]Riepilogo",
        border_style="cyan",
        padding=(1, 2),
    ))


# ═════════════════════════════════════════════════════════════
# ARRICCHIMENTO GRAFO RDF
# ═════════════════════════════════════════════════════════════

def build_enriched_graph(onto_graph, db_jobs, s1_res, s2_res):
    g = Graph()
    g.bind("rientra", RIENTRA)
    g.bind("joblist", JOBLIST)
    g.bind("rdfs",    RDFS)
    g.bind("xsd",     XSD)
    g.bind("owl",     OWL)

    for triple in onto_graph:
        g.add(triple)

    s2_idx = {r["id"]: r for r in s2_res}

    for row in db_jobs:
        rid  = row["id"]
        subj = RIENTRA[f"ExtJob_{rid}"]

        g.add((subj, RDF.type,               RIENTRA.Job))
        g.add((subj, RIENTRA.hasJobNameInDB, Literal(row["title"],  datatype=XSD.string)))
        g.add((subj, RIENTRA.hasExternalID,  Literal(rid,           datatype=XSD.string)))
        if row.get("description"):
            g.add((subj, RIENTRA.hasDescription,
                   Literal(row["description"], datatype=XSD.string)))

        m1 = next((r.get("match_s1") for r in s1_res if r["id"] == rid), None)
        if m1:
            g.add((subj, RIENTRA.matchedToONETJob_S1, URIRef(m1["job"]["uri"])))
            g.add((subj, RIENTRA.matchingScore_S1,
                   Literal(round(m1["score"], 4), datatype=XSD.decimal)))
            g.add((subj, RIENTRA.matchedViaLabel_S1,
                   Literal(m1["via"], datatype=XSD.string)))

        m2 = s2_idx.get(rid, {}).get("match_s2")
        if m2:
            g.add((subj, RIENTRA.matchedToONETJob_S2, URIRef(m2["job"]["uri"])))
            g.add((subj, RIENTRA.matchingScore_S2,
                   Literal(round(m2["score"], 4), datatype=XSD.decimal)))

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
    t.add_row("Turtle",       ttl, f"{os.path.getsize(ttl):,} bytes")
    t.add_row("RDF/XML",      rdf, f"{os.path.getsize(rdf):,} bytes")
    t.add_row("Triple totali", "",  str(len(g)))
    console.print(t)


# ═════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════

def main():
    console.print()
    console.print(Panel(
        f"[bold white]Rientra@[/] — Step 2: RDB2RDF + String Matching + NLP\n"
        f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]",
        border_style="blue",
        padding=(0, 2),
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
    console.print(f"  [bold green]✓[/] Ontologia: [bold]{len(onto_graph)}[/] triple caricate")

    onto_jobs = extract_ontology_jobs(onto_graph)
    console.print(f"  [bold green]✓[/] Professioni O*NET estratte: [bold]{len(onto_jobs)}[/]")
    console.print()
    print_ontology_table(onto_jobs)
    console.print()

    # ── [1] Lettura DB ────────────────────────────────────────
    console.print(Rule("[bold magenta]1 · Lettura DB esterno[/]", style="magenta"))
    console.print()
    db_jobs = fetch_all("SELECT id, title, description FROM ext_job ORDER BY id")
    console.print(f"  [bold green]✓[/] [bold]{len(db_jobs)}[/] lavori dalla tabella [cyan]ext_job[/]")
    console.print()
    print_db_table(db_jobs)
    console.print()

    # ── [2] Strategia 1 ───────────────────────────────────────
    console.print(Rule("[bold yellow]2 · Strategia 1 — String Matching[/]", style="yellow"))
    console.print("  [dim]Metriche: Jaccard (peso 0.5) + Overlap (0.3) + Levenshtein (0.2)[/]")
    console.print()
    s1_res = run_string_matching(db_jobs, onto_jobs)
    console.print(f"  [bold green]✓[/] Completato\n")

    # ── [3] Strategia 2 ───────────────────────────────────────
    console.print(Rule("[bold green]3 · Strategia 2 — NLP Similarity[/]", style="green"))
    console.print("  [dim]Modello: sentence-transformers/all-MiniLM-L6-v2  |  fallback: TF-IDF[/]")
    console.print()
    s2_res, method = run_nlp_matching(db_jobs, onto_jobs)
    console.print(f"  [bold green]✓[/] Completato con: [cyan]{method}[/]\n")

    # ── [4] Confronto ─────────────────────────────────────────
    console.print(Rule("[bold white]4 · Confronto S1 vs S2[/]", style="white"))
    console.print()
    print_matching_detail(s1_res, s2_res, method)
    print_summary(s1_res, s2_res)
    console.print()

    # ── [5] Grafo RDF ─────────────────────────────────────────
    console.print(Rule("[bold blue]5 · Costruzione e serializzazione grafo RDF[/]", style="blue"))
    console.print()
    with console.status("  Costruzione grafo A-Box...", spinner="dots"):
        g_final = build_enriched_graph(onto_graph, db_jobs, s1_res, s2_res)
    console.print(f"  [bold green]✓[/] {len(db_jobs)} ExtJob individuali aggiunti al grafo\n")

    with console.status("  Serializzazione...", spinner="dots"):
        save_graph(g_final, "rientra_ext_jobs")
    console.print()

    # ── Fine ──────────────────────────────────────────────────
    console.print(Panel(
        f"[bold green]Step 2 completato.[/]\n\n"
        f"Output → [cyan]{os.path.abspath(OUTPUT_DIR)}/[/]\n\n"
        f"[dim]Prossimo step: Strategia 3 — ESCO come ponte ontologico[/]",
        border_style="green",
        padding=(0, 2),
    ))
    console.print()


if __name__ == "__main__":
    main()