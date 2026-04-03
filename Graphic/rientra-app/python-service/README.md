# Rientr@ — Python Semantic Microservice

FastAPI REST service that exposes the Rientr@ ontology reasoning results
(loaded via owlready2 + Pellet) as structured JSON endpoints.

---

## Requirements

- Python 3.11+
- Java 11+ in `PATH` (required by Pellet via owlready2)
- The RDF ontology file (`.rdf` / `.owl` / `.ttl` / `.n3`)

Verify Java:
```bash
java -version   # must be 11 or higher
```

---

## Setup

```bash
# 1 — Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

# 2 — Install dependencies
pip install -r requirements.txt
```

---

## Running the service

### Option A — Auto-detect RDF file
Place the `.rdf` file in `python-service/` (or its parent folder) and run:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Option B — Explicit path via environment variable
```bash
ONTOLOGY_PATH=/path/to/your/ontology.rdf \
  uvicorn main:app --host 0.0.0.0 --port 8000
```

> **Note:** Pellet reasoning takes **30–120 seconds** on first startup.  
> The server is available immediately and returns `HTTP 503` until reasoning is complete.  
> Poll `GET /status` to check readiness.

---

## Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| `GET` | `/status` | Service health & readiness |
| `GET` | `/workers` | List all Person individuals |
| `GET` | `/workers/{worker_id}` | Single worker details |
| `GET` | `/jobs` | List all Job individuals |
| `GET` | `/jobs/{job_id}/importance` | Skill importance per job (Q4) |
| `GET` | `/match` | GCS%/AISA% for all selected workers (Q1+Q2) |
| `GET` | `/match/{worker_id}` | GCS%/AISA% for a specific worker |
| `POST` | `/match/detail` | Skill/Ability breakdown for one (worker, job) pair (Q3) |
| `GET` | `/health-conditions/{worker_id}` | ICF health conditions for a worker |

Interactive API docs (Swagger UI): **http://localhost:8000/docs**  
Alternative (ReDoc): **http://localhost:8000/redoc**

---

## Quick test (after `/status` returns `"ready"`)

```bash
# Service health
curl http://localhost:8000/status

# All workers
curl http://localhost:8000/workers

# All jobs
curl http://localhost:8000/jobs

# Health conditions for a worker
curl http://localhost:8000/health-conditions/Patient1

# Match results for all selected workers
curl http://localhost:8000/match

# Match results for one worker
curl http://localhost:8000/match/Patient1

# Skill detail for a specific (worker, job) pair
curl -X POST http://localhost:8000/match/detail \
     -H "Content-Type: application/json" \
     -d '{"worker_id": "Patient1", "job_id": "Job_AssemblyWorker"}'
```

---

## Integration with Spring Boot

From Spring Boot, call this service at `http://localhost:8000`.  
Example (RestTemplate):
```java
String workers = restTemplate.getForObject(
    "http://localhost:8000/workers", String.class);
```

CORS is pre-configured for:
- `http://localhost:5173` (React / Vite dev server)
- `http://localhost:3000` (alternative React port)
- `http://localhost:8080` (Spring Boot)

---

## Architecture notes

```
react-frontend (Vite :5173)
       │
       ▼
spring-boot-backend (:8080)
       │  REST calls
       ▼
python-semantic-service (:8000)   ← this service
       │
       ▼  owlready2 + Pellet (JVM)
   ontology.rdf
```

- The RDF ontology is loaded **once** at startup into the owlready2 `default_world`.
- Pellet runs **once** in a background thread — reasoning results are cached in memory.  
- Subsequent requests are served in milliseconds from the in-memory world.
- No authentication is implemented here; Spring Boot handles auth.
