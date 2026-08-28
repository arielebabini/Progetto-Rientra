-- ==============================================================================
-- Dataset SQL di Esempio per RIENTR@ (Importazione Lavoratori)
-- Include: Lucia, Gioele ed Elena con condizioni ICF e mansioni valutate
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
-- INSERIMENTO DATI: Lucia, Gioele ed Elena
-- ------------------------------------------------------------------------------

-- Inserimento Lavoratori
INSERT INTO person (person_id, first_name, surname, TIN, city, country, zip_code, birthday)
VALUES 
    ('LuciaVerdi', 'Lucia', 'Verdi', 'VRDLCU92A41H501U', 'Milano', 'Italy', 20121, '1992-01-15T00:00:00'),
    ('GioeleBianchi', 'Gioele', 'Bianchi', 'BNCGLI88C12F205W', 'Roma', 'Italy', 00185, '1988-03-12T00:00:00'),
    ('ElenaRinaldi', 'Elena', 'Rinaldi', 'RNLLNE89M52F205K', 'Bologna', 'Italy', 40121, '1989-08-12T00:00:00');

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

-- Descrittori ICF per Elena
-- Valutazione clinica completa (108 abilità valutate tra funzioni b e attività d):
-- menomazioni concentrate su mobilità/sforzi pesanti e piena funzionalità (0) per abilità cognitive/d'ufficio
INSERT INTO hc_descriptor (person_id, icf_code, qualifier)
VALUES 
    ('ElenaRinaldi', 'b1143', 0),
    ('ElenaRinaldi', 'b1144', 0),
    ('ElenaRinaldi', 'b122', 0),
    ('ElenaRinaldi', 'b1261', 0),
    ('ElenaRinaldi', 'b130', 1),
    ('ElenaRinaldi', 'b1400', 0),
    ('ElenaRinaldi', 'b1401', 2),
    ('ElenaRinaldi', 'b1408-AuditoryAttention', 2),
    ('ElenaRinaldi', 'b1440', 2),
    ('ElenaRinaldi', 'b1441', 2),
    ('ElenaRinaldi', 'b1442', 1),
    ('ElenaRinaldi', 'b1478-ReactionTime', 1),
    ('ElenaRinaldi', 'b1560', 0),
    ('ElenaRinaldi', 'b1565', 0),
    ('ElenaRinaldi', 'b1568-FlexibilityOfClosure', 1),
    ('ElenaRinaldi', 'b1568-PerceptualSpeed', 1),
    ('ElenaRinaldi', 'b1600', 1),
    ('ElenaRinaldi', 'b1601', 0),
    ('ElenaRinaldi', 'b1640', 0),
    ('ElenaRinaldi', 'b1641', 0),
    ('ElenaRinaldi', 'b1642', 0),
    ('ElenaRinaldi', 'b1643', 0),
    ('ElenaRinaldi', 'b1645', 0),
    ('ElenaRinaldi', 'b1646', 0),
    ('ElenaRinaldi', 'b1648-FluencyOfIdeas', 0),
    ('ElenaRinaldi', 'b1648-Monitoring', 0),
    ('ElenaRinaldi', 'b1648-Originality', 0),
    ('ElenaRinaldi', 'b1648-ProblemSensitivity', 0),
    ('ElenaRinaldi', 'b16700', 0),
    ('ElenaRinaldi', 'b1720', 0),
    ('ElenaRinaldi', 'b1721', 0),
    ('ElenaRinaldi', 'b176', 0),
    ('ElenaRinaldi', 'b189-DeductiveReasoning', 0),
    ('ElenaRinaldi', 'b189-InductiveReasoning', 0),
    ('ElenaRinaldi', 'b21000', 0),
    ('ElenaRinaldi', 'b21001', 0),
    ('ElenaRinaldi', 'b21002', 0),
    ('ElenaRinaldi', 'b21003', 0),
    ('ElenaRinaldi', 'b2101', 0),
    ('ElenaRinaldi', 'b21021', 0),
    ('ElenaRinaldi', 'b21022', 0),
    ('ElenaRinaldi', 'b21028-GlareSensitivity', 0),
    ('ElenaRinaldi', 'b21028-NightVision', 0),
    ('ElenaRinaldi', 'b2301', 0),
    ('ElenaRinaldi', 'b2302', 0),
    ('ElenaRinaldi', 'b2303', 0),
    ('ElenaRinaldi', 'b2304', 0),
    ('ElenaRinaldi', 'b2351', 0),
    ('ElenaRinaldi', 'b265', 1),
    ('ElenaRinaldi', 'b28010', 1),
    ('ElenaRinaldi', 'b28014', 1),
    ('ElenaRinaldi', 'b320', 0),
    ('ElenaRinaldi', 'b330', 0),
    ('ElenaRinaldi', 'b4550', 2),
    ('ElenaRinaldi', 'b710', 2),
    ('ElenaRinaldi', 'b730', 2),
    ('ElenaRinaldi', 'b7305', 1),
    ('ElenaRinaldi', 'b7306', 0),
    ('ElenaRinaldi', 'b7308-ExplosiveStrength', 2),
    ('ElenaRinaldi', 'b735', 1),
    ('ElenaRinaldi', 'b740', 1),
    ('ElenaRinaldi', 'b7401', 1),
    ('ElenaRinaldi', 'b755', 0),
    ('ElenaRinaldi', 'b760', 1),
    ('ElenaRinaldi', 'b7602', 1),
    ('ElenaRinaldi', 'b7603', 2),
    ('ElenaRinaldi', 'b7608-RateControl', 0),
    ('ElenaRinaldi', 'b7608-ResponseOrientation', 1),
    ('ElenaRinaldi', 'b7608-SpeedOfLimbMovement', 2),
    ('ElenaRinaldi', 'b770', 4),
    ('ElenaRinaldi', 'b789-DynamicFlexibility', 2),
    ('ElenaRinaldi', 'd160', 1),
    ('ElenaRinaldi', 'd166', 1),
    ('ElenaRinaldi', 'd170', 1),
    ('ElenaRinaldi', 'd172', 1),
    ('ElenaRinaldi', 'd1751', 1),
    ('ElenaRinaldi', 'd177', 1),
    ('ElenaRinaldi', 'd198-ActiveLearning', 1),
    ('ElenaRinaldi', 'd198-LearningStrategies', 1),
    ('ElenaRinaldi', 'd2400', 0),
    ('ElenaRinaldi', 'd310', 0),
    ('ElenaRinaldi', 'd325', 0),
    ('ElenaRinaldi', 'd329-ActiveListening', 1),
    ('ElenaRinaldi', 'd330', 0),
    ('ElenaRinaldi', 'd3300', 0),
    ('ElenaRinaldi', 'd3301', 0),
    ('ElenaRinaldi', 'd3302', 0),
    ('ElenaRinaldi', 'd345', 0),
    ('ElenaRinaldi', 'd3558-Negotiation', 0),
    ('ElenaRinaldi', 'd3558-Persuasion', 0),
    ('ElenaRinaldi', 'd398-Instructing', 0),
    ('ElenaRinaldi', 'd4100', 3),
    ('ElenaRinaldi', 'd4102', 4),
    ('ElenaRinaldi', 'd4104', 4),
    ('ElenaRinaldi', 'd4105', 4),
    ('ElenaRinaldi', 'd4106', 3),
    ('ElenaRinaldi', 'd4402', 0),
    ('ElenaRinaldi', 'd4408-WristFingerSpeed', 0),
    ('ElenaRinaldi', 'd445', 0),
    ('ElenaRinaldi', 'd4500', 4),
    ('ElenaRinaldi', 'd4501', 4),
    ('ElenaRinaldi', 'd4502', 4),
    ('ElenaRinaldi', 'd4503', 4),
    ('ElenaRinaldi', 'd455', 4),
    ('ElenaRinaldi', 'd720', 0),
    ('ElenaRinaldi', 'd859-ManagementOfMaterialResources', 0),
    ('ElenaRinaldi', 'd859-ManagementOfPersonnelResources', 0),
    ('ElenaRinaldi', 'd865', 0);

-- Valutazioni Mansioni (Job Evaluation)
-- Lucia viene valutata per Graphic_Designers e Programmers
-- Gioele viene valutato per Data_Entry_Keyers e Receptionist
-- Elena viene valutata per 7 mansioni con esito bilanciato:
--   - 3 Suitable (FileClerk, Receptionist, WordProcessors)
--   - 2 With precautions (GemWorker, Travel_guide)
--   - 2 Not suitable (Carpenter, Construction_laborer)
INSERT INTO job_evaluation (person_id, job_id)
VALUES 
    ('LuciaVerdi', 'Graphic_Designers'),
    ('LuciaVerdi', 'Programmers'),
    ('GioeleBianchi', 'Data_Entry_Keyers'),
    ('GioeleBianchi', 'Receptionist'),
    ('ElenaRinaldi', 'Carpenter'),
    ('ElenaRinaldi', 'Construction_laborer'),
    ('ElenaRinaldi', 'FileClerk'),
    ('ElenaRinaldi', 'GemWorker'),
    ('ElenaRinaldi', 'Receptionist'),
    ('ElenaRinaldi', 'Travel_guide'),
    ('ElenaRinaldi', 'WordProcessors');
