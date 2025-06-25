-- Migration manuelle pour ajouter le champ public_csv_include_headers à la table lists
ALTER TABLE lists ADD COLUMN public_csv_include_headers BOOLEAN DEFAULT TRUE;

-- Pour compatibilité SQLite (si utilisé)
-- ALTER TABLE lists ADD COLUMN public_csv_include_headers INTEGER DEFAULT 1;

-- Pour PostgreSQL
-- ALTER TABLE lists ADD COLUMN public_csv_include_headers BOOLEAN DEFAULT TRUE;

-- Pour MySQL
-- ALTER TABLE lists ADD COLUMN public_csv_include_headers TINYINT(1) DEFAULT 1;
