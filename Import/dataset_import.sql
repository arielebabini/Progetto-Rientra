-- ============================================================
--  Rientr@ - Dataset di import pazienti  (Opzione A: 2 tabelle)
--  Uso: letto da rientra_import.py per popolare l'ontologia
-- ============================================================

-- TABELLA 1: Anagrafica della persona
-- person_id → nome dell'individual OWL in Person-CommonBox (niente spazi)
-- is_selected viene impostato automaticamente a false dallo script, non va qui
CREATE TABLE IF NOT EXISTS person (
    person_id   TEXT    PRIMARY KEY,
    first_name  TEXT    NOT NULL,
    surname     TEXT    NOT NULL,
    TIN         TEXT,
    birthday    TEXT,       -- formato: YYYY-MM-DDTHH:MM:SS  oppure YYYY-MM-DD
    city        TEXT,
    country     TEXT,
    zip_code    INTEGER     -- xsd:int nell'ontologia
);

-- TABELLA 2: Condizione di salute - una riga per (persona, codice ICF)
-- Codici s* e e* vengono ignorati.
-- qualifier: scala ICF 0-4
CREATE TABLE IF NOT EXISTS hc_descriptor (
    person_id   TEXT    NOT NULL REFERENCES person(person_id),
    icf_code    TEXT    NOT NULL,
    qualifier   INTEGER NOT NULL CHECK (qualifier BETWEEN 0 AND 4),
    PRIMARY KEY (person_id, icf_code)
);

-- ============================================================
--  ESEMPIO DI POPOLAMENTO
-- ============================================================

INSERT OR IGNORE INTO person VALUES
    ('MarioBianchi', 'Mario', 'Bianchi', 'BNSMRA75C12H501Z',
     '1975-03-12T00:00:00', 'Milano', 'Italy', 20100);

INSERT OR IGNORE INTO hc_descriptor VALUES
    ('MarioBianchi', 'b110',   2),
    ('MarioBianchi', 'b1144',  1),
    ('MarioBianchi', 'b130',   3),
    ('MarioBianchi', 'b134',   1),
    ('MarioBianchi', 'b140',   2),
    ('MarioBianchi', 'b144',   1),
    ('MarioBianchi', 'b152',   2),
    ('MarioBianchi', 'b164',   1),
    ('MarioBianchi', 'b1646',  3),
    ('MarioBianchi', 'b176',   2),
    ('MarioBianchi', 'b4550',  1),
    ('MarioBianchi', 'd172',   2),
    ('MarioBianchi', 'd175',   1),
    ('MarioBianchi', 'd310',   0),
    ('MarioBianchi', 'd440',   1),
    ('MarioBianchi', 'd475',   2),
    ('MarioBianchi', 'd570',   0),
    ('MarioBianchi', 'd710',   1);