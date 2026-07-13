-- ============================================================
--  Rientr@ — 3 nuovi pazienti da importare nell'ontologia
--  File: tre_nuovi_pazienti.sql
--
--  Strategia di scoring per ottenere "With Precautions" / "Not Suitable":
--
--  Formule (dal paper):
--    GCS%  = Σ(qualifier × anchor) / (n_skab × 12) × 100
--    AISA% = n_skab_impaired / n_total_skab × 100
--    Soglie:
--      NOT SUITABLE          → GCS > -0.5·AISA + 21
--      SUITABLE WITH PRECAUTIONS → GCS ≥ -0.5·AISA + 15.5
--      SUITABLE              → GCS < -0.5·AISA + 15.5
--
--  Anchor (da O*NET score):  ≥75→3 | ≥50→2 | ≥26→1 | else 0
--
--  PAZIENTE 1 — MarcoBianchi
--    Profilo: deficit motori MODERATI agli arti superiori + schiena
--    Attesi: Carpenter/Landscaping → NOT SUITABLE
--             FileClerk/Receptionist → WITH PRECAUTIONS
--
--  PAZIENTE 2 — SofiaRomano
--    Profilo: deficit COGNITIVI e di comunicazione MODERATI
--    Attesi: Travel_guide → NOT SUITABLE (richiede molte skill comunicative)
--             FileClerk → WITH PRECAUTIONS (scrittura/attenzione)
--             Insurance_claims_clerks → WITH PRECAUTIONS (ufficio)
--
--  PAZIENTE 3 — PaoloEsposito
--    Profilo: deficit SENSORIALI (udito/vista) + equilibrio MODERATI
--    Attesi: Travel_guide → NOT SUITABLE (dipende da comunicazione uditiva)
--             GemWorker → WITH PRECAUTIONS (precisione visiva, non perfetta)
--             WordProcessors → WITH PRECAUTIONS (lettura/scrittura rallentata)
-- ============================================================


-- ──────────────────────────────────────────────────────────────
--  TABELLA 1: Dati anagrafici
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS person (
    person_id   TEXT    PRIMARY KEY,
    first_name  TEXT    NOT NULL,
    surname     TEXT    NOT NULL,
    TIN         TEXT,
    birthday    TEXT,
    city        TEXT,
    country     TEXT,
    zip_code    INTEGER
);

INSERT OR IGNORE INTO person VALUES (
    'MarcoBianchi', 'Marco', 'Bianchi', 'BNCMRC85T10F205Y',
    '1985-12-10T00:00:00', 'Firenze', 'Italy', 50100
);

INSERT OR IGNORE INTO person VALUES (
    'SofiaRomano', 'Sofia', 'Romano', 'RMNSFO92A41H501P',
    '1992-01-01T00:00:00', 'Roma', 'Italy', 00185
);

INSERT OR IGNORE INTO person VALUES (
    'PaoloEsposito', 'Paolo', 'Esposito', 'SPTPLA78E12F839X',
    '1978-05-12T00:00:00', 'Napoli', 'Italy', 80121
);


-- ──────────────────────────────────────────────────────────────
--  TABELLA 2: Condizioni di salute ICF (HC_Descriptor)
--  qualifier: 0=nessuno | 1=lieve | 2=moderato | 3=grave | 4=completo
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS hc_descriptor (
    person_id   TEXT    NOT NULL REFERENCES person(person_id),
    icf_code    TEXT    NOT NULL,
    qualifier   INTEGER NOT NULL CHECK (qualifier BETWEEN 0 AND 4),
    PRIMARY KEY (person_id, icf_code)
);

-- ══════════════════════════════════════════════════════════════
--  PAZIENTE 1: MarcoBianchi
--  Deficit motori/muscoloscheletrici moderati — arto superiore + rachide
--  → Lavori fisici pesanti: NOT SUITABLE
--  → Lavori sedentari di ufficio: SUITABLE WITH PRECAUTIONS
-- ══════════════════════════════════════════════════════════════

INSERT OR IGNORE INTO hc_descriptor VALUES
    -- Funzioni muscoloscheletriche (qualifier 2 = moderato)
    ('MarcoBianchi', 'b710',   2),   -- Mobilità delle articolazioni
    ('MarcoBianchi', 'b715',   2),   -- Stabilità delle articolazioni
    ('MarcoBianchi', 'b730',   2),   -- Forza muscolare
    ('MarcoBianchi', 'b735',   2),   -- Tono muscolare
    ('MarcoBianchi', 'b740',   2),   -- Resistenza muscolare
    ('MarcoBianchi', 'b760',   2),   -- Controllo dei movimenti volontari

    -- Attività di mobilità (qualifier 2-3 = moderato/grave)
    ('MarcoBianchi', 'd410',   2),   -- Cambiare la posizione corporea di base
    ('MarcoBianchi', 'd415',   2),   -- Mantenere la posizione corporea
    ('MarcoBianchi', 'd430',   3),   -- Sollevare e trasportare oggetti
    ('MarcoBianchi', 'd440',   2),   -- Uso fine della mano
    ('MarcoBianchi', 'd445',   3),   -- Uso della mano e del braccio
    ('MarcoBianchi', 'd450',   1),   -- Camminare (lieve)
    ('MarcoBianchi', 'd465',   2),   -- Spostarsi usando attrezzature

    -- Strutture correlate al movimento (qualifier 2-3)
    ('MarcoBianchi', 's720',   3),   -- Struttura della spalla
    ('MarcoBianchi', 's730',   2),   -- Struttura dell'arto superiore
    ('MarcoBianchi', 's760',   2);   -- Struttura del tronco


-- ══════════════════════════════════════════════════════════════
--  PAZIENTE 2: SofiaRomano
--  Deficit cognitivi e comunicativi moderati-gravi
--  → Lavori ad alta richiesta comunicativa: NOT SUITABLE
--  → Lavori d'ufficio strutturati: SUITABLE WITH PRECAUTIONS
-- ══════════════════════════════════════════════════════════════

INSERT OR IGNORE INTO hc_descriptor VALUES
    -- Funzioni mentali (qualifier 2-3)
    ('SofiaRomano', 'b110',   2),   -- Funzioni della coscienza
    ('SofiaRomano', 'b140',   3),   -- Funzioni dell'attenzione (grave)
    ('SofiaRomano', 'b1400',  3),   -- Mantenimento dell'attenzione
    ('SofiaRomano', 'b1401',  2),   -- Spostamento dell'attenzione
    ('SofiaRomano', 'b144',   3),   -- Funzioni della memoria
    ('SofiaRomano', 'b1440',  3),   -- Memoria a breve termine
    ('SofiaRomano', 'b152',   2),   -- Funzioni emozionali
    ('SofiaRomano', 'b164',   3),   -- Funzioni cognitive superiori (grave)
    ('SofiaRomano', 'b167',   2),   -- Funzioni del linguaggio (moderato)

    -- Funzioni della voce e del parlato (qualifier 2-3)
    ('SofiaRomano', 'b320',   3),   -- Funzioni di articolazione (grave)
    ('SofiaRomano', 'b330',   2),   -- Fluenza e ritmo del parlato

    -- Attività cognitive e comunicative (qualifier 2-3)
    ('SofiaRomano', 'd160',   2),   -- Focalizzare l'attenzione
    ('SofiaRomano', 'd163',   2),   -- Pensiero
    ('SofiaRomano', 'd166',   2),   -- Lettura
    ('SofiaRomano', 'd170',   2),   -- Scrivere
    ('SofiaRomano', 'd175',   3),   -- Risoluzione di problemi
    ('SofiaRomano', 'd210',   2),   -- Intraprendere un compito singolo
    ('SofiaRomano', 'd220',   3),   -- Intraprendere compiti molteplici (grave)
    ('SofiaRomano', 'd310',   2),   -- Comunicare con messaggi verbali ricevuti
    ('SofiaRomano', 'd315',   2),   -- Comunicare con messaggi non verbali ricevuti
    ('SofiaRomano', 'd330',   3),   -- Parlare (grave)
    ('SofiaRomano', 'd335',   2),   -- Produrre messaggi non verbali
    ('SofiaRomano', 'd710',   2),   -- Interazioni interpersonali di base
    ('SofiaRomano', 'd720',   3);   -- Interazioni interpersonali complesse (grave)


-- ══════════════════════════════════════════════════════════════
--  PAZIENTE 3: PaoloEsposito
--  Deficit sensoriali (udito, vista) + equilibrio moderati
--  → Lavori con forte dipendenza uditiva/visiva: NOT SUITABLE
--  → Lavori a bassa richiesta sensoriale: SUITABLE WITH PRECAUTIONS
-- ══════════════════════════════════════════════════════════════

INSERT OR IGNORE INTO hc_descriptor VALUES
    -- Funzioni sensoriali (qualifier 2-3)
    ('PaoloEsposito', 'b210',   3),   -- Funzioni della vista (grave)
    ('PaoloEsposito', 'b2102',  2),   -- Qualità della vista
    ('PaoloEsposito', 'b215',   2),   -- Funzioni delle strutture adiacenti all'occhio
    ('PaoloEsposito', 'b230',   3),   -- Funzioni uditive (grave)
    ('PaoloEsposito', 'b235',   2),   -- Funzioni vestibolari
    ('PaoloEsposito', 'b240',   2),   -- Sensazioni associate all'udito/equilibrio

    -- Funzioni di movimento/equilibrio (qualifier 1-2)
    ('PaoloEsposito', 'b755',   2),   -- Funzioni dei riflessi del movimento involontario
    ('PaoloEsposito', 'b770',   2),   -- Funzioni del pattern del cammino

    -- Funzioni mentali correlate (qualifier 1-2)
    ('PaoloEsposito', 'b156',   2),   -- Funzioni percettive
    ('PaoloEsposito', 'b160',   1),   -- Funzioni del pensiero (lieve)
    ('PaoloEsposito', 'b164',   2),   -- Funzioni cognitive superiori

    -- Attività e comunicazione (qualifier 1-2)
    ('PaoloEsposito', 'd115',   2),   -- Ascoltare
    ('PaoloEsposito', 'd160',   1),   -- Focalizzare l'attenzione (lieve)
    ('PaoloEsposito', 'd166',   2),   -- Lettura
    ('PaoloEsposito', 'd310',   2),   -- Comunicare con messaggi verbali ricevuti
    ('PaoloEsposito', 'd315',   2),   -- Comunicare con messaggi non verbali ricevuti
    ('PaoloEsposito', 'd330',   2),   -- Parlare
    ('PaoloEsposito', 'd450',   2),   -- Camminare
    ('PaoloEsposito', 'd455',   1);   -- Spostarsi (lieve)


-- ──────────────────────────────────────────────────────────────
--  TABELLA 3: Valutazione lavorativa
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS job_evaluation (
    person_id   TEXT    NOT NULL REFERENCES person(person_id),
    job_id      TEXT    NOT NULL,
    PRIMARY KEY (person_id, job_id)
);

-- ── MarcoBianchi (deficit motori) ─────────────────────────────
-- Atteso NOT SUITABLE: Carpenter, Landscaping (lavori fisici pesanti con
--   alta richiesta di forza/movimento → qualifiers 3 matchano skill critiche)
-- Atteso WITH PRECAUTIONS: FileClerk, Receptionist (sedentari ma richiedono
--   ancora uso delle mani → qualifiers 2 portano GCS nella zona gialla)
INSERT OR IGNORE INTO job_evaluation VALUES
    ('MarcoBianchi', 'Carpenter'),
    ('MarcoBianchi', 'Landscaping_and_Groundskeeping_Workers'),
    ('MarcoBianchi', 'FileClerk'),
    ('MarcoBianchi', 'Receptionist');

-- ── SofiaRomano (deficit cognitivi/comunicativi) ───────────────
-- Atteso NOT SUITABLE: Travel_guide (alta richiesta di parlato,
--   interazione, problem solving → qualifiers 3 su d330/d720/b164)
-- Atteso WITH PRECAUTIONS: FileClerk, Insurance_claims_clerks
--   (strutturato, meno parlato spontaneo → GCS nella zona gialla)
INSERT OR IGNORE INTO job_evaluation VALUES
    ('SofiaRomano', 'Travel_guide'),
    ('SofiaRomano', 'FileClerk'),
    ('SofiaRomano', 'Insurance_claims_clerks');

-- ── PaoloEsposito (deficit sensoriali/uditivi) ─────────────────
-- Atteso NOT SUITABLE: Travel_guide (forte dipendenza da udito
--   e parlato in ambienti rumorosi → qualifiers 3 su b230/d310/d330)
-- Atteso WITH PRECAUTIONS: GemWorker (precisione visiva ma fine
--   motor ancora possibile), WordProcessors (lettura/scrittura rallentata
--   ma non azzerata → qualifiers 2 → zona gialla)
INSERT OR IGNORE INTO job_evaluation VALUES
    ('PaoloEsposito', 'Travel_guide'),
    ('PaoloEsposito', 'GemWorker'),
    ('PaoloEsposito', 'WordProcessors');
