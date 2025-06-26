-- Migration manuelle pour ajouter le champ public_csv_include_headers à la table lists
ALTER TABLE lists ADD COLUMN public_csv_include_headers TINYINT(1) DEFAULT 1;