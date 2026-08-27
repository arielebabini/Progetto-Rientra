-- ==============================================================================
-- Dataset SQL di Esempio per RIENTR@ (Importazione Lavoratori)
-- Include: Lucia e Gioele con condizioni ICF e mansioni valutate conformi
-- ==============================================================================

-- 1. Tabella PERSON (Anagrafica Lavoratori)
CREATE TABLE IF NOT EXISTS person (
    person_id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    surname TEXT NOT NULL,
    TIN TEXT,
    city TEXT,
    country TEXT,
    zip_code INT,
    birthday TEXT
);

-- 2. Tabella HC_DESCRIPTOR (Condizioni di Salute e Funzionamento ICF)
-- Qualificatori ammessi: 0 (Nessun problema), 1 (Lieve), 2 (Moderato), 3 (Grave), 4 (Completo)
CREATE TABLE IF NOT EXISTS hc_descriptor (
    person_id TEXT NOT NULL,
    icf_code TEXT NOT NULL,
    qualifier INT NOT NULL
);

-- 3. Tabella JOB_EVALUATION (Mansioni Assegnate / Valutate)
CREATE TABLE IF NOT EXISTS job_evaluation (
    person_id TEXT NOT NULL,
    job_id TEXT NOT NULL
);

-- ------------------------------------------------------------------------------
-- INSERIMENTO DATI: Lucia e Gioele
-- ------------------------------------------------------------------------------

-- Inserimento Lavoratori
INSERT INTO person (person_id, first_name, surname, TIN, city, country, zip_code, birthday)
VALUES 
    ('LuciaVerdi', 'Lucia', 'Verdi', 'VRDLCU92A41H501U', 'Milano', 'Italy', 20121, '1992-01-15T00:00:00'),
    ('GioeleBianchi', 'Gioele', 'Bianchi', 'BNCGLI88C12F205W', 'Roma', 'Italy', 00185, '1988-03-12T00:00:00');

-- Descrittori ICF per Lucia
-- b130: Funzioni energetiche e delle pulsioni (qualifier: 1 = Lieve)
-- b280: Sensazione di dolore (qualifier: 2 = Moderato)
-- d430: Sollevare e trasportare oggetti (qualifier: 2 = Moderato)
-- d710: Interazioni interpersonali semplici (qualifier: 0 = Nessun problema)
-- s730: Struttura degli arti superiori (qualifier: 1 = Lieve)
INSERT INTO hc_descriptor (person_id, icf_code, qualifier)
VALUES 
    ('LuciaVerdi', 'b130', 1),
    ('LuciaVerdi', 'b280', 2),
    ('LuciaVerdi', 'd430', 2),
    ('LuciaVerdi', 'd710', 0),
    ('LuciaVerdi', 's730', 1);

-- Descrittori ICF per Gioele
-- b110: Funzioni della coscienza (qualifier: 0 = Nessun problema)
-- b140: Funzioni dell'attenzione (qualifier: 1 = Lieve)
-- d410: Cambiare la posizione corporea di base (qualifier: 1 = Lieve)
-- d450: Camminare (qualifier: 2 = Moderato)
-- s750: Struttura degli arti inferiori (qualifier: 2 = Moderato)
INSERT INTO hc_descriptor (person_id, icf_code, qualifier)
VALUES 
    ('GioeleBianchi', 'b110', 0),
    ('GioeleBianchi', 'b140', 1),
    ('GioeleBianchi', 'd410', 1),
    ('GioeleBianchi', 'd450', 2),
    ('GioeleBianchi', 's750', 2);

-- Valutazioni Mansioni (Job Evaluation)
-- Lucia viene valutata per Graphic_Designers e Programmers
-- Gioele viene valutato per Data_Entry_Keyers e Receptionist
INSERT INTO job_evaluation (person_id, job_id)
VALUES 
    ('LuciaVerdi', 'Graphic_Designers'),
    ('LuciaVerdi', 'Programmers'),
    ('GioeleBianchi', 'Data_Entry_Keyers'),
    ('GioeleBianchi', 'Receptionist');
