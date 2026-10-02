-- Apply after 20261002_pending_requests.sql, before deploying email registration.
ALTER TABLE pending_registration ADD COLUMN IF NOT EXISTS email varchar(254);
ALTER TABLE pending_registration ALTER COLUMN member_id DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_pending_registration_email_unique ON pending_registration (email);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'pending_registration'::regclass
          AND conname = 'pending_registration_one_identifier'
    ) THEN
        ALTER TABLE pending_registration
            ADD CONSTRAINT pending_registration_one_identifier
            CHECK ((member_id IS NOT NULL) <> (email IS NOT NULL));
    END IF;
END $$;
