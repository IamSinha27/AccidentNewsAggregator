CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,                  -- article's published date, not occurrence date
    title TEXT NOT NULL,
    link TEXT UNIQUE NOT NULL,            -- the RESOLVED publisher URL, not the Google redirect
    source TEXT,                          -- outlet name
    severity TEXT NOT NULL CHECK (severity IN ('fatal', 'non-fatal')),  -- non-fatal also covers "the article doesn't say"
    deaths INT NOT NULL DEFAULT 0,        -- 0 on a fatal row means the toll wasn't stated; always 0 on non-fatal
    injured INT NOT NULL DEFAULT 0,       -- 0 means nobody hurt or no number stated
    vehicles TEXT[] NOT NULL DEFAULT '{}'  -- types involved, sorted, each once; empty = unknown. Same list as extract.VEHICLE_TYPES
        CHECK (vehicles <@ ARRAY['Auto-rickshaw', 'Bus', 'Car', 'Tractor', 'Truck', 'Two-wheeler', 'Van']),
    state TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CHECK (deaths >= 0 AND injured >= 0),
    CHECK (deaths = 0 OR severity = 'fatal')
);

-- One-time upgrade of a table created before severity/deaths/injured existed,
-- when the outcome was a single free-text `fatality` column ("Yes (3 dead)",
-- "No (injuries only)", "Unknown"). Does nothing once that column is gone.
-- injured can't be recovered from the old column; backfill_injured.py fills it.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'articles' AND column_name = 'fatality'
    ) THEN
        ALTER TABLE articles
            ADD COLUMN severity TEXT,
            ADD COLUMN deaths INT NOT NULL DEFAULT 0,
            ADD COLUMN injured INT NOT NULL DEFAULT 0;
        UPDATE articles SET
            severity = CASE WHEN fatality ILIKE 'yes%' THEN 'fatal' ELSE 'non-fatal' END,
            deaths = CASE WHEN fatality ILIKE 'yes%' THEN COALESCE(substring(fatality FROM '\d+')::int, 0) ELSE 0 END;
        ALTER TABLE articles
            ALTER COLUMN severity SET NOT NULL,
            ADD CHECK (severity IN ('fatal', 'non-fatal')),
            ADD CHECK (deaths >= 0 AND injured >= 0),
            ADD CHECK (deaths = 0 OR severity = 'fatal'),
            DROP COLUMN fatality;
    END IF;
END $$;

-- Upgrade of a table created when the vehicles were one free-text
-- `vehicle_type` column ("Truck / Car"). The old column is left in place here:
-- turning its text into categories needs the LLM, so backfill_vehicles.py
-- does that and then drops it.
ALTER TABLE articles ADD COLUMN IF NOT EXISTS vehicles TEXT[] NOT NULL DEFAULT '{}'
    CHECK (vehicles <@ ARRAY['Auto-rickshaw', 'Bus', 'Car', 'Tractor', 'Truck', 'Two-wheeler', 'Van']);
DROP INDEX IF EXISTS idx_articles_date_state_vehicle;

CREATE INDEX IF NOT EXISTS idx_articles_date ON articles (date);
CREATE INDEX IF NOT EXISTS idx_articles_date_state ON articles (date, state);  -- for the dedup lookup
CREATE INDEX IF NOT EXISTS idx_articles_state_date ON articles (state, date);  -- for one state's article list

-- Links the pipeline has already looked at and turned down (not an India
-- traffic accident, not recent, or an accident that's already stored). Lets a
-- rerun skip the scrape and the LLM call for them, and stops a borderline
-- article getting a second verdict. Pruned by the pipeline after a few days:
-- the feed only reaches back one day, so older links never come back.
CREATE TABLE IF NOT EXISTS seen_links (
    link TEXT PRIMARY KEY,
    outcome TEXT NOT NULL,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seen_links_seen_at ON seen_links (seen_at);  -- for the prune
