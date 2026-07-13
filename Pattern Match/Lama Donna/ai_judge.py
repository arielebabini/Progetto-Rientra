"""
ai_judge.py
===========
Modulo AI Judge per il progetto Rientra@.

Usa un LLM locale via Ollama per validare semanticamente i match proposti
da S2 (all-mpnet-base-v2) e S4 (all-MiniLM-L6-v2) verso le professioni O*NET.

Il judge emette un verdetto strutturato in JSON:
  {
    "verdict":         "CONFIRMED" | "PARTIAL" | "REJECTED" | "UNCERTAIN",
    "confidence":      0.0 – 1.0,
    "reasoning":       "spiegazione in inglese",
    "suggested_label": "eventuale professione O*NET alternativa (o null)"
  }

Requisiti:
    pip install ollama
    ollama pull gemma3:4b   (o altro modello compatibile M1 16 GB)

Modelli consigliati per MacBook Pro M1 16 GB:
    gemma3:4b    ~3 GB RAM  – veloce, buona qualità (DEFAULT)
    qwen2.5:7b   ~5 GB RAM  – top reasoning
    llama3.1:8b  ~6 GB RAM  – bilanciato
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich import box
from rich.rule import Rule

console = Console()

# ─────────────────────────────────────────────────────────────
# PROMPT TEMPLATES
# ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an expert occupational taxonomy judge specializing in O*NET job classifications.

Your task is to evaluate whether a proposed O*NET occupation is the correct semantic match for a given job posting.

Rules:
- Be strict: only mark as CONFIRMED if the match is clearly correct
- Use PARTIAL when there is significant overlap but the match is imperfect
- Use REJECTED when the proposed O*NET occupation is semantically wrong
- Use UNCERTAIN when the evidence is insufficient to decide

ALWAYS respond with valid JSON only. No explanation outside the JSON.
Output format:
{
  "verdict": "CONFIRMED" | "PARTIAL" | "REJECTED" | "UNCERTAIN",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<one or two sentences explaining your decision in English>",
  "suggested_label": "<alternative O*NET occupation if verdict is REJECTED, otherwise null>"
}"""

_USER_PROMPT_TEMPLATE = """Evaluate this O*NET match:

JOB TITLE: "{title}"
JOB DESCRIPTION: "{description}"

PROPOSED O*NET MATCH: "{onto_label}"
O*NET DESCRIPTION: "{onto_desc}"

EMBEDDING SCORES:
  - S2 (all-mpnet-base-v2):  {s2_score}
  - S4 (all-MiniLM-L6-v2):  {s4_score}
  - Score agreement:         {agreement}

Is "{onto_label}" the correct O*NET occupation for "{title}"?
Reply with JSON only."""


# ─────────────────────────────────────────────────────────────
# OLLAMA INTERFACE
# ─────────────────────────────────────────────────────────────

def check_ollama_available(model: str) -> bool:
    """
    Verifica che:
      1. Il pacchetto `ollama` sia installato
      2. Il server Ollama sia raggiungibile (localhost:11434)
      3. Il modello richiesto sia disponibile localmente

    Ritorna True se tutto è OK, False altrimenti.
    """
    try:
        import ollama  # type: ignore
        models_resp = ollama.list()
        available = [m.model for m in models_resp.models]
        # Controlla sia nome esatto sia prefisso (es. "gemma3:4b" vs "gemma3:4b-it-qat")
        for m in available:
            if m == model or m.startswith(model.split(":")[0]):
                return True
        console.print(
            f"  [yellow]⚠[/] Modello [cyan]{model}[/] non trovato in Ollama.\n"
            f"  [dim]Modelli disponibili: {', '.join(available) or 'nessuno'}[/]\n"
            f"  [dim]Esegui: [cyan]ollama pull {model}[/][/]"
        )
        return False
    except ImportError:
        console.print(
            "  [yellow]⚠[/] Pacchetto [cyan]ollama[/] non installato.\n"
            "  [dim]Esegui: [cyan]pip install ollama[/][/]"
        )
        return False
    except Exception as e:
        console.print(
            f"  [yellow]⚠[/] Ollama non raggiungibile: [dim]{e}[/]\n"
            f"  [dim]Assicurati che Ollama sia in esecuzione (ollama serve)[/]"
        )
        return False


def _parse_json_response(raw: str) -> dict:
    """
    Estrae e parsa il JSON dalla risposta del LLM.
    Gestisce il caso in cui il modello aggiunga testo prima/dopo il JSON.
    """
    # Prova direttamente
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Cerca blocco JSON delimitato da ```json ... ``` o ``` ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Cerca qualsiasi blocco { ... } nel testo
    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: risposta non parsabile
    return {
        "verdict": "UNCERTAIN",
        "confidence": 0.0,
        "reasoning": f"Could not parse LLM response: {raw[:120]}",
        "suggested_label": None,
    }


def _validate_verdict(result: dict) -> dict:
    """Normalizza e valida i campi del verdetto JSON."""
    valid_verdicts = {"CONFIRMED", "PARTIAL", "REJECTED", "UNCERTAIN"}

    verdict = str(result.get("verdict", "UNCERTAIN")).upper()
    if verdict not in valid_verdicts:
        verdict = "UNCERTAIN"

    try:
        confidence = float(result.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5

    reasoning = str(result.get("reasoning", "No reasoning provided."))[:500]
    suggested = result.get("suggested_label")
    if suggested and not isinstance(suggested, str):
        suggested = None

    return {
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": reasoning,
        "suggested_label": suggested,
    }


def judge_single_match(
    job_id: str,
    job_title: str,
    job_description: str,
    onto_label: str,
    onto_desc: str,
    s2_score: Optional[float],
    s4_score: Optional[float],
    model: str,
    temperature: float = 0.1,
) -> dict:
    """
    Invia un singolo match al LLM judge e ritorna il verdetto strutturato.

    Parametri:
        job_id          : ID del job nel DB (es. "ext01")
        job_title       : titolo del job nel DB
        job_description : descrizione del job (troncata a 400 chars se lunga)
        onto_label      : label O*NET proposta dal matching
        onto_desc       : descrizione O*NET (troncata)
        s2_score        : score cosine S2 (None se sotto soglia)
        s4_score        : score cosine S4 (None se sotto soglia)
        model           : nome modello Ollama
        temperature     : temperatura LLM (bassa per output deterministici)

    Ritorna dict con: job_id, verdict, confidence, reasoning, suggested_label,
                      latency_ms, error (se qualcosa va storto)
    """
    import ollama  # type: ignore

    # Prepara valori per il prompt
    desc_short  = (job_description or "N/A")[:400]
    onto_short  = (onto_desc or "N/A")[:400]
    s2_str      = f"{s2_score:.3f}" if s2_score is not None else "below threshold"
    s4_str      = f"{s4_score:.3f}" if s4_score is not None else "below threshold"

    if s2_score is not None and s4_score is not None:
        diff = abs(s2_score - s4_score)
        agreement = f"Δ={diff:.3f} ({'high' if diff < 0.05 else 'moderate' if diff < 0.10 else 'low'} agreement)"
    elif s2_score is not None or s4_score is not None:
        agreement = "only one model has a match above threshold"
    else:
        agreement = "both models below threshold — match is uncertain"

    prompt = _USER_PROMPT_TEMPLATE.format(
        title=job_title,
        description=desc_short,
        onto_label=onto_label,
        onto_desc=onto_short,
        s2_score=s2_str,
        s4_score=s4_str,
        agreement=agreement,
    )

    t0 = time.time()
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            options={"temperature": temperature},
        )
        raw = response["message"]["content"]
        latency_ms = int((time.time() - t0) * 1000)
        parsed = _parse_json_response(raw)
        validated = _validate_verdict(parsed)
        return {
            "job_id": job_id,
            "error": None,
            "latency_ms": latency_ms,
            **validated,
        }

    except Exception as e:
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "job_id": job_id,
            "verdict": "UNCERTAIN",
            "confidence": 0.0,
            "reasoning": f"Judge error: {str(e)[:200]}",
            "suggested_label": None,
            "latency_ms": latency_ms,
            "error": str(e),
        }


# ─────────────────────────────────────────────────────────────
# BATCH RUNNER
# ─────────────────────────────────────────────────────────────

def run_ai_judge(
    db_jobs: list[dict],
    nlp_results: dict[str, list[dict]],
    onto_jobs: list[dict],
    model: str,
) -> list[dict]:
    """
    Esegue il judge su tutti i job del DB per cui esiste almeno un match NLP.

    Per ogni job:
      - recupera il match migliore da S2 e/o S4
      - usa il match con score più alto come "proposta principale"
      - invia al LLM la coppia (job, onto_match) con entrambi gli score

    Ritorna una lista di dict con i risultati del judge per ogni job.
    """
    # Indici rapidi per lookup
    s2_idx = {r["id"]: r for r in (nlp_results.get("S2_MPNET") or [])}
    s4_idx = {r["id"]: r for r in (nlp_results.get("S4_MiniLM") or [])}

    # Mappa URI → descrizione O*NET per il prompt
    onto_desc_map = {j["uri"]: j["description"] for j in onto_jobs}
    onto_label_map = {j["uri"]: j["label"] for j in onto_jobs}

    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as p:
        task = p.add_task(f"  Judge [{model}]...", total=len(db_jobs))

        for row in db_jobs:
            rid   = row["id"]
            title = row["title"]
            desc  = row.get("description", "") or ""

            r2 = s2_idx.get(rid, {})
            r4 = s4_idx.get(rid, {})

            m2 = r2.get("match")   # match S2 (None se sotto soglia)
            m4 = r4.get("match")   # match S4 (None se sotto soglia)

            s2_score = m2["score"] if m2 else None
            s4_score = m4["score"] if m4 else None

            # Scegli il match principale: prefer S2 (più potente), fallback S4
            if m2:
                primary_uri   = m2["job"]["uri"]
                primary_label = m2["job"]["label"]
            elif m4:
                primary_uri   = m4["job"]["uri"]
                primary_label = m4["job"]["label"]
            else:
                # Nessun match NLP: skip judge (o usa score raw)
                raw_s2 = r2.get("score_raw", 0.0)
                raw_s4 = r4.get("score_raw", 0.0)
                # Usa il candidato con score raw più alto
                if raw_s2 >= raw_s4:
                    primary_uri   = (r2.get("match") or {}).get("job", {}).get("uri", "")
                    primary_label = (r2.get("match") or {}).get("job", {}).get("label", "N/A")
                    s2_score = raw_s2 if raw_s2 > 0 else None
                else:
                    primary_uri   = (r4.get("match") or {}).get("job", {}).get("uri", "")
                    primary_label = (r4.get("match") or {}).get("job", {}).get("label", "N/A")
                    s4_score = raw_s4 if raw_s4 > 0 else None

                if not primary_label or primary_label == "N/A":
                    results.append({
                        "job_id": rid,
                        "job_title": title,
                        "s2_match": None,
                        "s2_score": None,
                        "s4_match": None,
                        "s4_score": None,
                        "primary_label": "— nessun match —",
                        "verdict": "UNCERTAIN",
                        "confidence": 0.0,
                        "reasoning": "No NLP match found above or below threshold.",
                        "suggested_label": None,
                        "latency_ms": 0,
                        "error": None,
                    })
                    p.advance(task)
                    continue

            onto_desc = onto_desc_map.get(primary_uri, "")

            verdict = judge_single_match(
                job_id=rid,
                job_title=title,
                job_description=desc,
                onto_label=primary_label,
                onto_desc=onto_desc,
                s2_score=s2_score,
                s4_score=s4_score,
                model=model,
            )

            results.append({
                "job_id":        rid,
                "job_title":     title,
                "s2_match":      m2["job"]["label"] if m2 else None,
                "s2_score":      s2_score,
                "s4_match":      m4["job"]["label"] if m4 else None,
                "s4_score":      s4_score,
                "primary_label": primary_label,
                **{k: verdict[k] for k in
                   ["verdict","confidence","reasoning","suggested_label","latency_ms","error"]},
            })
            p.advance(task)

    return results


# ─────────────────────────────────────────────────────────────
# OUTPUT RICH
# ─────────────────────────────────────────────────────────────

_VERDICT_STYLE = {
    "CONFIRMED": ("✓ CONFIRMED", "bold green"),
    "PARTIAL":   ("~ PARTIAL",   "yellow"),
    "REJECTED":  ("✗ REJECTED",  "bold red"),
    "UNCERTAIN": ("? UNCERTAIN", "dim"),
}


def _confidence_bar(conf: float, width: int = 8) -> str:
    filled = round(conf * width)
    return "█" * filled + "░" * (width - filled)


def print_judge_table(judge_results: list[dict], model: str = ""):
    """Stampa la tabella Rich dei risultati del AI Judge."""
    if not judge_results:
        console.print("  [dim]Nessun risultato dal judge.[/]")
        return

    t = Table(
        title=f"AI Judge — validazione locale{'  ·  ' + model if model else ''}",
        box=box.SIMPLE_HEAD,
        show_lines=True,
        header_style="bold white on dark_magenta",
        title_style="bold white",
        expand=True,
    )
    t.add_column("ID",         style="bold", width=6,  justify="center")
    t.add_column("Titolo DB",               width=22)
    t.add_column("Match S2",                width=24)
    t.add_column("Match S4",                width=24)
    t.add_column("Proposta principale",     width=24)
    t.add_column("Verdetto",   justify="center", width=14)
    t.add_column("Confidence", justify="center", width=12)
    t.add_column("Reasoning",               width=40)

    for r in judge_results:
        verdict  = r.get("verdict", "UNCERTAIN")
        v_label, v_style = _VERDICT_STYLE.get(verdict, ("? UNCERTAIN", "dim"))

        conf     = r.get("confidence", 0.0)
        conf_txt = Text()
        conf_txt.append(f"{conf:.2f}\n", style=v_style)
        conf_txt.append(_confidence_bar(conf), style=v_style)

        reasoning = (r.get("reasoning") or "")[:120]
        if len(r.get("reasoning") or "") > 120:
            reasoning += "…"

        s2_lbl = r.get("s2_match") or Text("—", style="dim")
        s4_lbl = r.get("s4_match") or Text("—", style="dim")

        t.add_row(
            r["job_id"],
            r["job_title"],
            str(s2_lbl),
            str(s4_lbl),
            r.get("primary_label", "—"),
            Text(v_label, style=v_style),
            conf_txt,
            Text(reasoning, style="dim" if verdict == "UNCERTAIN" else ""),
        )

    console.print(t)

    # Legenda + statistiche
    totals = {v: sum(1 for r in judge_results if r.get("verdict") == v)
              for v in _VERDICT_STYLE}
    avg_conf = (sum(r.get("confidence", 0.0) for r in judge_results) /
                len(judge_results)) if judge_results else 0.0
    avg_lat  = (sum(r.get("latency_ms", 0) for r in judge_results) /
                len(judge_results)) if judge_results else 0.0

    console.print(
        f"  [bold green]✓ {totals['CONFIRMED']} CONFIRMED[/]  "
        f"[yellow]~ {totals['PARTIAL']} PARTIAL[/]  "
        f"[bold red]✗ {totals['REJECTED']} REJECTED[/]  "
        f"[dim]? {totals['UNCERTAIN']} UNCERTAIN[/]  "
        f"  [dim]avg confidence: {avg_conf:.2f}  ·  avg latency: {avg_lat:.0f} ms[/]\n"
    )

    # Warning se ci sono errori
    errors = [r for r in judge_results if r.get("error")]
    if errors:
        console.print(
            f"  [yellow]⚠[/] {len(errors)} chiamat{'a' if len(errors)==1 else 'e'} "
            f"al judge ha{'nno' if len(errors)>1 else ''} prodotto errori "
            f"(verdetto UNCERTAIN assegnato automaticamente)\n"
        )
