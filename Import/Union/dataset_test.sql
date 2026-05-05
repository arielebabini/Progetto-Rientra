-- ============================================================
--  Rientr@ - Dataset di test  (3 pazienti)
--  Tutti i codici ICF sono presenti nell'ontologia Rientra.rdf
--  Uso: python rientra_import.py --ontology Rientra.rdf --dataset dataset_test.sql
-- ============================================================

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

CREATE TABLE IF NOT EXISTS hc_descriptor (
    person_id   TEXT    NOT NULL REFERENCES person(person_id),
    icf_code    TEXT    NOT NULL,
    qualifier   INTEGER NOT NULL CHECK (qualifier BETWEEN 0 AND 4),
    PRIMARY KEY (person_id, icf_code)
);

-- ============================================================
--  PAZIENTE 1 — LucaMartini
--  Profilo: deficit cognitivi e attenzione, difficoltà di apprendimento
--  Codici: b (funzioni mentali) + d (attività cognitive)
-- ============================================================
INSERT OR IGNORE INTO person VALUES (
    'LucaMartini', 'Luca', 'Martini', 'MRTLCU82E20F205X',
    '1982-05-20T00:00:00', 'Torino', 'Italy', 10100
);

INSERT OR IGNORE INTO hc_descriptor VALUES
    ('LucaMartini', 'b110',   3),   -- Funzioni della coscienza
    ('LucaMartini', 'b114',   2),   -- Funzioni di orientamento
    ('LucaMartini', 'b140',   3),   -- Funzioni dell attenzione
    ('LucaMartini', 'b1400',  2),   -- Mantenimento dell attenzione
    ('LucaMartini', 'b1401',  3),   -- Spostamento dell attenzione
    ('LucaMartini', 'b144',   2),   -- Funzioni della memoria
    ('LucaMartini', 'b1440',  1),   -- Memoria a breve termine
    ('LucaMartini', 'b1441',  2),   -- Memoria a lungo termine
    ('LucaMartini', 'b152',   1),   -- Funzioni emozionali
    ('LucaMartini', 'b164',   2),   -- Funzioni cognitive superiori
    ('LucaMartini', 'd160',   2),   -- Focalizzare l attenzione
    ('LucaMartini', 'd163',   3),   -- Pensiero
    ('LucaMartini', 'd166',   2),   -- Lettura
    ('LucaMartini', 'd172',   3),   -- Calcolo
    ('LucaMartini', 'd175',   2),   -- Risoluzione di problemi
    ('LucaMartini', 'd210',   1),   -- Intraprendere un compito singolo
    ('LucaMartini', 'd220',   2),   -- Intraprendere compiti molteplici
    ('LucaMartini', 'd310',   1);   -- Comunicare con messaggi verbali

-- ============================================================
--  PAZIENTE 2 — ElenaConti
--  Profilo: deficit motori e strutturali agli arti superiori
--  Codici: b (funzioni neuromuscolari) + d (mobilità/cura) + s (strutture)
-- ============================================================
INSERT OR IGNORE INTO person VALUES (
    'ElenaConti', 'Elena', 'Conti', 'CNTLNE90D52H501W',
    '1990-04-12T00:00:00', 'Roma', 'Italy', 00185
);

INSERT OR IGNORE INTO hc_descriptor VALUES
    ('ElenaConti', 'b710',   2),   -- Mobilità delle articolazioni
    ('ElenaConti', 'b730',   3),   -- Forza muscolare
    ('ElenaConti', 'b740',   2),   -- Resistenza muscolare
    ('ElenaConti', 'b760',   2),   -- Controllo dei movimenti volontari
    ('ElenaConti', 'b765',   1),   -- Movimenti involontari
    ('ElenaConti', 'b810',   1),   -- Funzioni protettive della cute
    ('ElenaConti', 'd410',   3),   -- Cambiare la posizione corporea di base
    ('ElenaConti', 'd415',   2),   -- Mantenere la posizione corporea
    ('ElenaConti', 'd430',   3),   -- Sollevare e trasportare oggetti
    ('ElenaConti', 'd440',   2),   -- Uso fine della mano
    ('ElenaConti', 'd445',   3),   -- Uso della mano e del braccio
    ('ElenaConti', 'd450',   1),   -- Camminare
    ('ElenaConti', 'd465',   2),   -- Spostarsi usando attrezzature
    ('ElenaConti', 'd510',   2),   -- Lavarsi
    ('ElenaConti', 'd540',   3),   -- Vestirsi
    ('ElenaConti', 's710',   2),   -- Struttura della testa e del collo
    ('ElenaConti', 's720',   3),   -- Struttura della spalla
    ('ElenaConti', 's730',   2),   -- Struttura dell arto superiore
    ('ElenaConti', 's7300',  3),   -- Struttura del braccio
    ('ElenaConti', 's7301',  2);   -- Struttura dell avambraccio

-- ============================================================
--  PAZIENTE 3 — GiuseppeFerrari
--  Profilo: difficoltà comunicative e relazionali, funzioni sensoriali
--  Codici: b (funzioni sensoriali/voce) + d (comunicazione/relazioni)
--  Include 2 codici e* → devono essere ignorati dallo script
-- ============================================================
INSERT OR IGNORE INTO person VALUES (
    'GiuseppeFerrari', 'Giuseppe', 'Ferrari', 'FRRGPP55M10L219K',
    '1955-08-10T00:00:00', 'Napoli', 'Italy', 80100
);

INSERT OR IGNORE INTO hc_descriptor VALUES
    ('GiuseppeFerrari', 'b230',   2),   -- Funzioni uditive
    ('GiuseppeFerrari', 'b240',   1),   -- Sensazioni associate all udito
    ('GiuseppeFerrari', 'b310',   3),   -- Funzioni della voce
    ('GiuseppeFerrari', 'b320',   2),   -- Funzioni di articolazione
    ('GiuseppeFerrari', 'b330',   3),   -- Fluenza e ritmo del parlato
    ('GiuseppeFerrari', 'b122',   1),   -- Funzioni psicosociali globali
    ('GiuseppeFerrari', 'b126',   2),   -- Funzioni del temperamento
    ('GiuseppeFerrari', 'b130',   2),   -- Funzioni dell energia
    ('GiuseppeFerrari', 'd310',   2),   -- Comunicare con messaggi verbali ricevuti
    ('GiuseppeFerrari', 'd315',   3),   -- Comunicare con messaggi non verbali ricevuti
    ('GiuseppeFerrari', 'd325',   2),   -- Comunicare con messaggi scritti ricevuti
    ('GiuseppeFerrari', 'd330',   3),   -- Parlare
    ('GiuseppeFerrari', 'd335',   2),   -- Produrre messaggi non verbali
    ('GiuseppeFerrari', 'd345',   2),   -- Scrivere messaggi
    ('GiuseppeFerrari', 'd710',   1),   -- Interazioni interpersonali di base
    ('GiuseppeFerrari', 'd720',   2),   -- Interazioni interpersonali complesse
    ('GiuseppeFerrari', 'd740',   1),   -- Relazioni formali
    ('GiuseppeFerrari', 'e310',   1),   -- [IGNORATO] Famiglia ristretta — fattore ambientale
    ('GiuseppeFerrari', 'e580',   2);   -- [IGNORATO] Servizi sanitari — fattore ambientale

-- ============================================================
--  TABELLA 3: Job evaluation — job già presenti nell'ontologia
--  job_id deve corrispondere esattamente all'IRI JobList#<job_id>
-- ============================================================
CREATE TABLE IF NOT EXISTS job_evaluation (
    person_id   TEXT    NOT NULL REFERENCES person(person_id),
    job_id      TEXT    NOT NULL,
    PRIMARY KEY (person_id, job_id)
);

-- LucaMartini — lavori cognitivi leggeri
INSERT OR IGNORE INTO job_evaluation VALUES
    ('LucaMartini', 'FileClerk'),
    ('LucaMartini', 'Receptionist'),
    ('LucaMartini', 'WordProcessors');

-- ElenaConti — lavori manuali/motori
INSERT OR IGNORE INTO job_evaluation VALUES
    ('ElenaConti', 'Carpenter'),
    ('ElenaConti', 'GemWorker'),
    ('ElenaConti', 'Landscaping_and_Groundskeeping_Workers');

-- GiuseppeFerrari — lavori comunicativi/d'ufficio
INSERT OR IGNORE INTO job_evaluation VALUES
    ('GiuseppeFerrari', 'Travel_guide'),
    ('GiuseppeFerrari', 'Insurance_claims_clerks'),
    ('GiuseppeFerrari', 'job_inesistente');   -- deve essere ignorato
