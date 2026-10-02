-- Apply before deploying card payment and BAC1 requests.
ALTER TABLE pending_registration ADD COLUMN IF NOT EXISTS free_card_requested boolean NOT NULL DEFAULT false;
ALTER TABLE pending_registration ADD COLUMN IF NOT EXISTS card_year integer;
ALTER TABLE pending_card_request ADD COLUMN IF NOT EXISTS free_card boolean NOT NULL DEFAULT false;
CREATE TABLE IF NOT EXISTS card_payment_settings (
    id integer PRIMARY KEY,
    beneficiary varchar(70) NOT NULL DEFAULT '',
    iban varchar(34) NOT NULL DEFAULT '',
    bic varchar(11) NOT NULL DEFAULT '',
    amount numeric(10, 2),
    communication_prefix varchar(60) NOT NULL DEFAULT 'Carte Fédé'
);
