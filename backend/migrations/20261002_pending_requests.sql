-- Apply once to existing PostgreSQL databases before deploying this feature.
CREATE TABLE IF NOT EXISTS pending_registration (
    id varchar PRIMARY KEY,
    nom varchar(100) NOT NULL,
    prenom varchar(100) NOT NULL,
    member_id varchar(6) NOT NULL UNIQUE,
    password_hash varchar NOT NULL,
    created_at timestamp NOT NULL,
    expires_at timestamp NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pending_registration_expires_at ON pending_registration (expires_at);

CREATE TABLE IF NOT EXISTS pending_card_request (
    id varchar PRIMARY KEY,
    user_id varchar NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    annee integer NOT NULL,
    created_at timestamp NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'pending',
    CONSTRAINT uq_pending_card_user_year UNIQUE (user_id, annee)
);
