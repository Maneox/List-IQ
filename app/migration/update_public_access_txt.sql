-- Migration SQL pour l’export TXT public dans List-IQ
ALTER TABLE lists
    ADD COLUMN public_txt_enabled BOOLEAN DEFAULT FALSE,
    ADD COLUMN public_txt_column VARCHAR(255),
    ADD COLUMN public_txt_include_headers BOOLEAN DEFAULT TRUE;
