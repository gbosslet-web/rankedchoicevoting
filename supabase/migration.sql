CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS elections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    seats_available INT NOT NULL DEFAULT 1,
    status TEXT CHECK (status IN ('draft', 'active', 'completed')) DEFAULT 'draft',
    results_visible BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    election_id UUID REFERENCES elections(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    bio TEXT
);

CREATE TABLE IF NOT EXISTS voters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    election_id UUID REFERENCES elections(id) ON DELETE CASCADE,
    -- Stores either an email address or a voter display name/label.
    email TEXT NOT NULL,
    token UUID UNIQUE DEFAULT gen_random_uuid(),
    has_voted BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS ballots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    election_id UUID REFERENCES elections(id) ON DELETE CASCADE,
    ranking JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS candidates_election_id_idx ON candidates(election_id);
CREATE INDEX IF NOT EXISTS voters_election_id_idx ON voters(election_id);
CREATE INDEX IF NOT EXISTS voters_token_idx ON voters(token);
CREATE INDEX IF NOT EXISTS ballots_election_id_idx ON ballots(election_id);

CREATE OR REPLACE FUNCTION submit_ballot(
    p_voter_id UUID,
    p_election_id UUID,
    p_ranking JSONB
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    voter_record voters%ROWTYPE;
BEGIN
    SELECT *
    INTO voter_record
    FROM voters
    WHERE id = p_voter_id
      AND election_id = p_election_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid voter';
    END IF;

    IF voter_record.has_voted THEN
        RAISE EXCEPTION 'Voting link has already been used';
    END IF;

    INSERT INTO ballots (election_id, ranking)
    VALUES (p_election_id, p_ranking);

    UPDATE voters
    SET has_voted = TRUE
    WHERE id = p_voter_id;
END;
$$;
