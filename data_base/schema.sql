-- ================================================================
-- SIH26189 — AI-Powered Criminal Network Analysis System
-- PostgreSQL Schema — Full + Corrected (re-runnable)
-- ================================================================


-- ================================================================
-- 1. FIR / POLICE REPORTS
-- ================================================================

CREATE TABLE IF NOT EXISTS fir_records (
    fir_id                  BIGSERIAL PRIMARY KEY,
    case_id                 VARCHAR(100) NOT NULL,
    fir_number              VARCHAR(100),
    police_station          VARCHAR(255),
    district                VARCHAR(255),
    state                   VARCHAR(255),
    registration_date       TIMESTAMP,
    incident_date           TIMESTAMP,
    incident_location       TEXT,
    description             TEXT NOT NULL,

    -- extracted mentions stored directly on FIR
    persons_mentioned       JSONB DEFAULT '[]'::jsonb,
    vehicles_mentioned      JSONB DEFAULT '[]'::jsonb,
    phones_mentioned        JSONB DEFAULT '[]'::jsonb,
    organizations_mentioned JSONB DEFAULT '[]'::jsonb,
    locations_mentioned     JSONB DEFAULT '[]'::jsonb,

    status                  VARCHAR(50) DEFAULT 'Open',

    -- blockchain provenance
    source_file             VARCHAR(500),
    source_hash             VARCHAR(64),

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE fir_records
    ADD COLUMN IF NOT EXISTS locations_mentioned JSONB DEFAULT '[]'::jsonb;


-- ================================================================
-- 2. CONTACT / CDR RECORDS
-- ================================================================

CREATE TABLE IF NOT EXISTS contact_records (
    contact_id              BIGSERIAL PRIMARY KEY,

    caller_name             VARCHAR(255),
    caller_phone            VARCHAR(20) NOT NULL,
    caller_location         VARCHAR(255),

    receiver_name           VARCHAR(255),
    receiver_phone          VARCHAR(20) NOT NULL,
    receiver_location       VARCHAR(255),

    call_timestamp          TIMESTAMP NOT NULL,
    duration_seconds        INTEGER DEFAULT 0,
    call_type               VARCHAR(30),    -- incoming / outgoing / missed

    -- blockchain provenance
    source_file             VARCHAR(500),
    source_hash             VARCHAR(64),

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CHECK (duration_seconds >= 0)
);

ALTER TABLE contact_records
    ADD COLUMN IF NOT EXISTS source_file VARCHAR(500);
ALTER TABLE contact_records
    ADD COLUMN IF NOT EXISTS source_hash VARCHAR(64);


-- ================================================================
-- 3. BANK / FINANCIAL RECORDS
-- ================================================================

CREATE TABLE IF NOT EXISTS bank_records (
    bank_record_id                  BIGSERIAL PRIMARY KEY,

    -- sender
    sender_account_number           VARCHAR(50)  NOT NULL,
    sender_account_holder_name      VARCHAR(255) NOT NULL,
    sender_bank_name                VARCHAR(255),
    sender_branch_name              VARCHAR(255),
    sender_ifsc                     VARCHAR(20),
    sender_location                 VARCHAR(255),

    -- receiver
    receiver_account_number         VARCHAR(50)  NOT NULL,
    receiver_account_holder_name    VARCHAR(255) NOT NULL,
    receiver_bank_name              VARCHAR(255),
    receiver_branch_name            VARCHAR(255),
    receiver_ifsc                   VARCHAR(20),
    receiver_location               VARCHAR(255),

    -- transaction
    transaction_id                  VARCHAR(100),
    transaction_type                VARCHAR(50),   -- debit / credit / transfer
    transaction_amount              DECIMAL(15, 2) NOT NULL,
    transaction_date                TIMESTAMP,
    currency                        VARCHAR(10) DEFAULT 'INR',

    -- blockchain provenance
    source_file                     VARCHAR(500),
    source_hash                     VARCHAR(64),

    created_at                      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CHECK (transaction_amount >= 0)
);


-- ================================================================
-- 4. SOCIAL MEDIA RECORDS
-- ================================================================

CREATE TABLE IF NOT EXISTS social_media_records (
    social_media_record_id  BIGSERIAL PRIMARY KEY,

    platform                VARCHAR(50)  NOT NULL,   -- Facebook / Twitter / Instagram
    user_id                 VARCHAR(100) NOT NULL,
    username                VARCHAR(100),

    post_id                 VARCHAR(100),
    post_content            TEXT,
    post_timestamp          TIMESTAMP,

    likes_count             INTEGER DEFAULT 0,
    comments_count          INTEGER DEFAULT 0,
    shares_count            INTEGER DEFAULT 0,

    mentioned_users         JSONB DEFAULT '[]'::jsonb,
    hashtags                JSONB DEFAULT '[]'::jsonb,
    phone_numbers           JSONB DEFAULT '[]'::jsonb,
    external_links          JSONB DEFAULT '[]'::jsonb,

    -- blockchain provenance
    source_file             VARCHAR(500),
    source_hash             VARCHAR(64),

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ================================================================
-- 5. PREVIOUS CRIME / CRIMINAL HISTORY RECORDS
-- ================================================================

CREATE TABLE IF NOT EXISTS previous_crime_records (
    history_id              BIGSERIAL PRIMARY KEY,

    person_name             VARCHAR(255) NOT NULL,
    person_identifier       VARCHAR(255),            -- Aadhaar / passport / any ID

    case_id                 VARCHAR(100),
    fir_number              VARCHAR(100),

    offense                 VARCHAR(255),
    offense_category        VARCHAR(255),            -- violent / financial / cyber etc.

    case_date               TIMESTAMP,
    case_status             VARCHAR(100),            -- convicted / acquitted / pending

    police_station          VARCHAR(255),
    district                VARCHAR(255),
    state                   VARCHAR(255),

    description             TEXT,

    -- blockchain provenance
    source_file             VARCHAR(500),
    source_hash             VARCHAR(64),

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ================================================================
-- 6. SURVEILLANCE / LOCATION HISTORY RECORDS
-- ================================================================

CREATE TABLE IF NOT EXISTS surveillance_records (
    surveillance_id         BIGSERIAL PRIMARY KEY,

    -- who/what was observed
    entity_name             VARCHAR(255),            -- person name or vehicle number
    entity_type             VARCHAR(50),             -- PERSON / VEHICLE / PHONE

    camera_id               VARCHAR(100),
    source_type             VARCHAR(100),            -- CCTV / drone / manual report
    source_reference        VARCHAR(255),

    location                VARCHAR(255) NOT NULL,
    location_name           VARCHAR(255),
    latitude                NUMERIC(10, 7),
    longitude               NUMERIC(10, 7),

    observed_at             TIMESTAMP,               -- when they were spotted
    event_description       TEXT,

    -- blockchain provenance
    source_file             VARCHAR(500),
    source_hash             VARCHAR(64),

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ================================================================
-- 7. EXTRACTED ENTITIES
--    Bridge table: NER output → cross-DB lookup → Neo4j graph
--    Every entity extracted from any source lands here first
-- ================================================================

CREATE TABLE IF NOT EXISTS extracted_entities (
    entity_id               BIGSERIAL PRIMARY KEY,

    fir_id                  BIGINT REFERENCES fir_records(fir_id) ON DELETE CASCADE,

    entity_type             VARCHAR(50)  NOT NULL,   -- PERSON / PHONE / VEHICLE / LOCATION / ORGANIZATION / ACCOUNT
    entity_value            VARCHAR(255) NOT NULL,   -- actual value e.g. "Rahul Kumar", "9876543210"

    confidence              FLOAT DEFAULT 1.0,       -- NER confidence score
    extraction_source       VARCHAR(100),            -- which model extracted it

    -- cross-DB lookup result
    db_hit_count            INTEGER DEFAULT 0,       -- how many source tables returned data
    entity_score            FLOAT   DEFAULT 0.0,     -- computed score after cross-DB lookup

    -- which source record this came from
    source_table            VARCHAR(100),
    source_record_id        BIGINT,

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_extracted_entities_fir_type_value
    ON extracted_entities (fir_id, entity_type, entity_value);


-- ================================================================
-- 8. LLM REASONING RESULTS
--    Stores what the LLM returned for each FIR analysis run
-- ================================================================

CREATE TABLE IF NOT EXISTS llm_reasoning_results (
    reasoning_id            BIGSERIAL PRIMARY KEY,

    fir_id                  BIGINT REFERENCES fir_records(fir_id) ON DELETE CASCADE,

    -- raw LLM output
    raw_response            TEXT,

    -- parsed relations (array of relation objects)
    relations               JSONB DEFAULT '[]'::jsonb,

    -- suspicious flags the LLM raised
    suspicious_flags        JSONB DEFAULT '[]'::jsonb,

    model_used              VARCHAR(100),
    prompt_tokens           INTEGER,
    completion_tokens       INTEGER,

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ================================================================
-- 9. BLOCKCHAIN AUDIT LEDGER
--    Tamper-evident log of every important system event
-- ================================================================

CREATE TABLE IF NOT EXISTS audit_ledger (
    ledger_id               BIGSERIAL PRIMARY KEY,

    event_type              VARCHAR(100) NOT NULL,
    -- DATA_INGESTED / ENTITY_EXTRACTED / RELATION_CREATED /
    -- ANALYSIS_EXECUTED / REPORT_GENERATED / ACCESS_RECORD /
    -- TAMPER_DETECTED

    actor_id                BIGINT,                  -- which user triggered it (NULL = system)
    actor_role              VARCHAR(50),             -- their role at time of event

    target_table            VARCHAR(100),
    target_record_id        BIGINT,

    -- the hash of the record at time of event
    record_hash             VARCHAR(64) NOT NULL,

    -- previous ledger entry hash — creates the chain
    previous_hash           VARCHAR(64),

    -- full chain hash (SHA-256 of record_hash + previous_hash)
    chain_hash              VARCHAR(64) NOT NULL,

    metadata                JSONB DEFAULT '{}'::jsonb,

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ================================================================
-- 10. USERS & RBAC
-- ================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id                 BIGSERIAL PRIMARY KEY,
    username                VARCHAR(100) UNIQUE NOT NULL,
    email                   VARCHAR(255) UNIQUE NOT NULL,
    password_hash           VARCHAR(255) NOT NULL,
    full_name               VARCHAR(255),
    role                    VARCHAR(50) NOT NULL DEFAULT 'viewer',
    -- roles: admin / investigator / viewer
    is_active               BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login              TIMESTAMP
);

CREATE TABLE IF NOT EXISTS role_permissions (
    permission_id           BIGSERIAL PRIMARY KEY,
    role                    VARCHAR(50) NOT NULL,
    resource                VARCHAR(100) NOT NULL,   -- fir_records / graph / reports etc.
    can_read                BOOLEAN DEFAULT FALSE,
    can_write               BOOLEAN DEFAULT FALSE,
    can_delete              BOOLEAN DEFAULT FALSE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_role_permissions_role_resource
    ON role_permissions (role, resource);

-- seed default permissions (safe to re-run)
INSERT INTO role_permissions (role, resource, can_read, can_write, can_delete) VALUES
    ('admin',        'fir_records',          TRUE,  TRUE,  TRUE),
    ('admin',        'graph',                TRUE,  TRUE,  TRUE),
    ('admin',        'audit_ledger',         TRUE,  FALSE, FALSE),
    ('investigator', 'fir_records',          TRUE,  TRUE,  FALSE),
    ('investigator', 'graph',                TRUE,  TRUE,  FALSE),
    ('investigator', 'audit_ledger',         TRUE,  FALSE, FALSE),
    ('viewer',       'fir_records',          TRUE,  FALSE, FALSE),
    ('viewer',       'graph',                TRUE,  FALSE, FALSE),
    ('viewer',       'audit_ledger',         FALSE, FALSE, FALSE)
ON CONFLICT (role, resource) DO NOTHING;


-- ================================================================
-- INDEXES
-- ================================================================

-- fir_records
CREATE INDEX IF NOT EXISTS idx_fir_case_id           ON fir_records(case_id);
CREATE INDEX IF NOT EXISTS idx_fir_registration_date ON fir_records(registration_date);
CREATE INDEX IF NOT EXISTS idx_fir_source_hash       ON fir_records(source_hash);

-- contact_records
CREATE INDEX IF NOT EXISTS idx_contact_caller        ON contact_records(caller_phone);
CREATE INDEX IF NOT EXISTS idx_contact_receiver      ON contact_records(receiver_phone);
CREATE INDEX IF NOT EXISTS idx_contact_caller_name   ON contact_records(caller_name);
CREATE INDEX IF NOT EXISTS idx_contact_receiver_name ON contact_records(receiver_name);
CREATE INDEX IF NOT EXISTS idx_contact_timestamp     ON contact_records(call_timestamp);

-- bank_records
CREATE INDEX IF NOT EXISTS idx_bank_sender_account   ON bank_records(sender_account_number);
CREATE INDEX IF NOT EXISTS idx_bank_receiver_account ON bank_records(receiver_account_number);
CREATE INDEX IF NOT EXISTS idx_bank_sender_name      ON bank_records(sender_account_holder_name);
CREATE INDEX IF NOT EXISTS idx_bank_receiver_name    ON bank_records(receiver_account_holder_name);
CREATE INDEX IF NOT EXISTS idx_bank_transaction_date ON bank_records(transaction_date);

-- social_media_records
CREATE INDEX IF NOT EXISTS idx_social_username       ON social_media_records(username);
CREATE INDEX IF NOT EXISTS idx_social_user_id        ON social_media_records(user_id);
CREATE INDEX IF NOT EXISTS idx_social_timestamp      ON social_media_records(post_timestamp);

-- previous_crime_records
CREATE INDEX IF NOT EXISTS idx_crime_person_name     ON previous_crime_records(person_name);
CREATE INDEX IF NOT EXISTS idx_crime_identifier      ON previous_crime_records(person_identifier);
CREATE INDEX IF NOT EXISTS idx_crime_case_id         ON previous_crime_records(case_id);

-- surveillance_records
CREATE INDEX IF NOT EXISTS idx_surv_entity_name      ON surveillance_records(entity_name);
CREATE INDEX IF NOT EXISTS idx_surv_entity_type      ON surveillance_records(entity_type);
CREATE INDEX IF NOT EXISTS idx_surv_observed_at      ON surveillance_records(observed_at);
CREATE INDEX IF NOT EXISTS idx_surv_location         ON surveillance_records(location);

-- extracted_entities
CREATE INDEX IF NOT EXISTS idx_entity_fir_id         ON extracted_entities(fir_id);
CREATE INDEX IF NOT EXISTS idx_entity_type           ON extracted_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entity_value          ON extracted_entities(entity_value);
CREATE INDEX IF NOT EXISTS idx_entity_score          ON extracted_entities(entity_score DESC);

-- llm_reasoning_results
CREATE INDEX IF NOT EXISTS idx_llm_fir_id            ON llm_reasoning_results(fir_id);
CREATE INDEX IF NOT EXISTS idx_llm_created_at        ON llm_reasoning_results(created_at);

-- audit_ledger
CREATE INDEX IF NOT EXISTS idx_audit_event_type      ON audit_ledger(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_actor_id        ON audit_ledger(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at      ON audit_ledger(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_chain_hash      ON audit_ledger(chain_hash);

-- users
CREATE INDEX IF NOT EXISTS idx_users_username        ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role            ON users(role);
