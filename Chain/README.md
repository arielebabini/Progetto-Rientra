# Rientra@ Step 1 — Guida rapida

## Struttura del progetto

```
rientra_step1/
├── ontology/
│   └── rientra_mini.ttl        ← ontologia minimale (apribile in Protégé)
├── sql/
│   └── setup.sql               ← schema PostgreSQL + dati di esempio
├── python/
│   └── rdb2rdf_step1.py        ← script principale
└── output/                     ← creata automaticamente dallo script
    ├── direct_mapping.ttl/.rdf
    ├── r2rml_mapping.ttl/.rdf
    └── rientra_final.ttl/.rdf
```

---

## Setup (una volta sola)

### 1. Crea il database PostgreSQL

Con l'installer ufficiale il superuser si chiama `postgres`.
Apri il terminale e lancia:

```bash
# Crea il DB
/Library/PostgreSQL/16/bin/createdb -U postgres rientra_db

# Ti chiede la password → inserisci quella scelta durante l'installazione

# Carica schema e dati
/Library/PostgreSQL/16/bin/psql -U postgres -d rientra_db -f rientra_step1/sql/setup.sql
```

> **Nota**: sostituisci `16` con la tua versione di PostgreSQL
> (controlla in `/Library/PostgreSQL/`).

Oppure, se hai aggiunto PostgreSQL al PATH (si vede se `psql` funziona senza percorso):

```bash
createdb -U postgres rientra_db
psql -U postgres -d rientra_db -f rientra_step1/sql/setup.sql
```

### 2. Installa le dipendenze Python

```bash
cd rientra_step1
pip install psycopg2-binary rdflib
```

### 3. Configura la connessione

Apri `python/rdb2rdf_step1.py` e modifica `DB_CONFIG`:

```python
DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "rientra_db",
    "user":     "postgres",     # utente PostgreSQL
    "password": "postgres"      # la tua password
}
```

---

## Esecuzione

```bash
cd rientra_step1
python python/rdb2rdf_step1.py
```

Output atteso:

```
============================================================
  Rientra@ — Step 1: RDB2RDF + String Matching
============================================================

[0] Test connessione PostgreSQL
  ✓ PostgreSQL OK: PostgreSQL 16.x ...

[0] Caricamento ontologia: ontology/rientra_mini.ttl
  ✓ 87 triple caricate dall'ontologia

[1] DIRECT MAPPING
    wheelchair_user                4 righe  →  ...
    icf_code                      23 righe  →  ...
    ...

[2] R2RML-STYLE MAPPING
    wheelchair_user       →  4 individui rientra:Wheelchair_user
    icf_code              →  23 individui rientra:ICF_Code
    ...

[3] STRING MATCHING — Soluzione 1
    ✓ [1] Manager of the digital archive
         Atteso:  Archivists
         Trovato: Archivists  (score=0.400)
         Via:     Digital Archivist
    ...

[4] ARRICCHIMENTO GRAFO
    9 triple aggiunte al grafo (matching)

Step 1 completato.
```

---

## Cosa fa lo script (fasi)

| Fase | Cosa succede |
|------|-------------|
| **Direct Mapping** | Ogni tabella SQL → Classe RDF generica (`ex:wheelchair_user`). Nessuna configurazione, output grezzo. |
| **R2RML Mapping** | Ogni tabella → Classe Rientra@ (`rientra:Wheelchair_user`). Le FK diventano object properties. |
| **String Matching** | Il nome del job nel DB (`"Manager of the digital archive"`) viene confrontato con i nomi O*NET e le loro label alternative usando Jaccard + Overlap. |
| **Arricchimento** | Il grafo R2RML viene completato con triple `rientra:matchedToONETJob`, `rientra:matchingScore`, `rientra:matchedViaLabel`. |

---

## Aprire l'ontologia in Protégé

1. Apri Protégé
2. `File → Open` → seleziona `ontology/rientra_mini.ttl`
3. Vai in `Entities → Classes` per vedere la gerarchia
4. Dopo aver eseguito lo script, apri anche `output/rientra_final.ttl`
   per vedere gli individui generati

---

## Troubleshooting

**Errore `role "arielebabini" does not exist`**
```bash
/Library/PostgreSQL/16/bin/psql -U postgres -c \
  "CREATE ROLE arielebabini WITH SUPERUSER LOGIN PASSWORD 'password';"
```

**Errore `could not connect to server`**
PostgreSQL non è avviato. Aprilo dall'app `pgAdmin` oppure:
```bash
/Library/PostgreSQL/16/bin/pg_ctl start \
  -D /Library/PostgreSQL/16/data
```

**`psql: command not found`**
Aggiungi PostgreSQL al PATH:
```bash
export PATH="/Library/PostgreSQL/16/bin:$PATH"
# Aggiungilo anche a ~/.zshrc per renderlo permanente
```
