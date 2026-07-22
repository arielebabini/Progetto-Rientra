-- ============================================================
-- rientra_ext_jobs.sql
-- Database esterno con i lavori del dataset di esempio
-- Chiave primaria: ext01, ext02, ...
-- Import: psql -U postgres -d rientra_db -f rientra_ext_jobs.sql
-- ============================================================

DROP TABLE IF EXISTS ext_job;

CREATE TABLE ext_job (
    id          VARCHAR(6)   PRIMARY KEY,   -- ext01, ext02, ...
    title       TEXT         NOT NULL,
    description TEXT
);

INSERT INTO ext_job (id, title, description) VALUES
('ext01', 'Accounting clerk',
 'Perform routine accounting, bookkeeping, and payroll duties. Compute, classify, and record numerical data to keep financial records complete and accurate. Check figures, postings, and documents for correctness, and operate calculators, computers, or accounting software to process business transactions.'),

('ext02', 'Content manager web',
 'Plan, create, manage, and update digital content for websites and online platforms. Coordinate the development of text, images, and multimedia materials to ensure consistency with organizational goals. Monitor content performance, maintain site structure, and collaborate with designers, editors, and marketing staff.'),

('ext03', 'Data analyst',
 'Collect, process, and analyze data to identify trends, patterns, and relationships. Prepare reports, charts, and visualizations to support decision-making. Ensure data accuracy and integrity, and use statistical or analytical tools to interpret quantitative information.'),

('ext04', 'Data entry',
 'Enter numerical and text data into computer systems or databases using keyboards, data recorders, or scanners. Verify accuracy of data, correct errors, and maintain confidentiality of information. May compile, sort, and organize source documents.'),

('ext05', 'Data entry employee',
 'Input, update, and maintain data in electronic systems following established procedures. Review source documents for completeness, check data for errors, and make corrections as needed. Perform basic clerical tasks related to data management.'),

('ext06', 'Data scientist',
 'Develop and apply statistical, mathematical, and computational techniques to analyze large and complex data sets. Build models to extract insights, make predictions, and support strategic decisions. Communicate analytical results through reports, visualizations, and presentations.'),

('ext07', 'Digital public relations specialist',
 'Plan and execute online public relations strategies to build and maintain a positive digital presence. Manage communication through websites, social media, blogs, and online publications. Monitor public perception, respond to inquiries, and coordinate digital campaigns to enhance organizational image.'),

('ext08', 'Switchboard operator',
 'Operate telephone switchboard systems to route incoming, outgoing, and interoffice calls. Provide information to callers, take messages, and announce visitors. May handle answering services and perform related administrative tasks.'),

('ext09', 'Supermarket cashier',
 'Receive payments and process transactions at checkout counters in supermarkets. Scan items, handle cash or electronic payments, issue receipts, and assist customers. Maintain accurate records of transactions and ensure proper handling of money.');

-- Verifica
SELECT id, title FROM ext_job ORDER BY id;
