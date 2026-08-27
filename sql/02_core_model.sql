-- =====================================================================
-- VERITY — 02_core_model.sql
-- CORE (Member 360 foundation) + DOCS.CLINICAL_NOTE
--
-- Every column here exists to serve a specific criterion in the Criteria
-- Ledger. Schema was derived FROM the criteria tree, not the other way
-- round — see CLAUDE.md. Columns carrying that weight are commented with
-- the section reference they serve.
--
-- ALL DATA IS SYNTHETIC. Fictional payer (Meridian Health Plan),
-- fictional members, fake NDC labeler code (99999).
-- =====================================================================

USE DATABASE VERITY;
USE SCHEMA CORE;

-- ---------------------------------------------------------------------
-- Members
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS MEMBER (
    member_id       STRING NOT NULL,
    first_name      STRING,
    last_name       STRING,
    date_of_birth   DATE,                 -- §3.1 age on date of service
    sex             STRING,
    state           STRING,
    zip3            STRING,               -- 3-digit only: de-identification convention
    is_golden       BOOLEAN DEFAULT FALSE, -- demo cohort flag
    CONSTRAINT pk_member PRIMARY KEY (member_id)
) COMMENT = 'Synthetic members. No real persons.';

-- ---------------------------------------------------------------------
-- Member linkage across coverage periods.
--
-- §2.3 of MHP-PA-0142: a trial completed under a prior member identifier
-- or prior carrier SHALL count toward step therapy. Without this table
-- the hero scenario cannot be evaluated — a step-therapy query scoped to
-- the current member_id would miss a qualifying metformin trial.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS MEMBER_LINK (
    member_id        STRING NOT NULL,     -- current identity
    prior_member_id  STRING NOT NULL,     -- historical identity
    prior_carrier    STRING,              -- NULL = prior Meridian product
    link_type        STRING,              -- PLAN_CHANGE | CARRIER_CHANGE | ID_REISSUE
    coverage_start   DATE,
    coverage_end     DATE,
    CONSTRAINT pk_member_link PRIMARY KEY (member_id, prior_member_id)
) COMMENT = 'Prior-coverage identity linkage. Required by policy section 2.3.';

CREATE TABLE IF NOT EXISTS ELIGIBILITY (
    member_id       STRING NOT NULL,
    plan_id         STRING,
    lob             STRING,               -- Commercial | Medicare | Medicaid
    coverage_start  DATE,
    coverage_end    DATE
) COMMENT = 'Coverage spans by member.';

-- ---------------------------------------------------------------------
-- Providers — network_status matters: the hero note originates from an
-- out-of-network provider, which is precisely why it never made it into
-- structured claims data.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PROVIDER (
    provider_id     STRING NOT NULL,
    npi             STRING,
    provider_name   STRING,
    specialty       STRING,
    network_status  STRING,               -- IN_NETWORK | OUT_OF_NETWORK
    CONSTRAINT pk_provider PRIMARY KEY (provider_id)
) COMMENT = 'Synthetic providers. NPIs are fake.';

-- ---------------------------------------------------------------------
-- Medical claims
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS CLAIM (
    claim_id        STRING NOT NULL,
    member_id       STRING NOT NULL,
    provider_id     STRING,
    service_date    DATE,                 -- §3.2a 12-month diagnosis lookback
    claim_type      STRING,               -- PROFESSIONAL | INSTITUTIONAL
    billed_amount   NUMBER(12,2),
    allowed_amount  NUMBER(12,2),
    CONSTRAINT pk_claim PRIMARY KEY (claim_id)
) COMMENT = 'Synthetic medical claim headers.';

CREATE TABLE IF NOT EXISTS CLAIM_DIAGNOSIS (
    claim_id        STRING NOT NULL,
    seq             INT,
    icd10           STRING                -- §3.2a E11.* = Type 2 Diabetes Mellitus
) COMMENT = 'Diagnosis codes per claim.';

-- ---------------------------------------------------------------------
-- Drug reference — makes step-therapy class logic data-driven rather
-- than hardcoded. §4.1 keys on BIGUANIDE; §4.2 on SGLT2_INHIBITOR or
-- SULFONYLUREA.
--
-- NDC labeler code 99999 is deliberately invalid: these are not real
-- product codes.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS DRUG_REFERENCE (
    ndc             STRING NOT NULL,
    drug_name       STRING,
    drug_class      STRING,               -- BIGUANIDE | SGLT2_INHIBITOR | SULFONYLUREA | GLP1_RA | DPP4_INHIBITOR | INSULIN
    generic_flag    BOOLEAN,
    tier            INT,
    CONSTRAINT pk_drug_reference PRIMARY KEY (ndc)
) COMMENT = 'Synthetic drug reference. NDC labeler 99999 is intentionally fake.';

-- ---------------------------------------------------------------------
-- Pharmacy claims.
--
-- days_supply is load-bearing: §2.3 defines an adequate trial as three
-- CONSECUTIVE months, so proving it requires fill-to-fill gap analysis.
-- Fill dates alone are insufficient.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS RX_CLAIM (
    rx_claim_id     STRING NOT NULL,
    member_id       STRING NOT NULL,      -- may be a PRIOR id; join via MEMBER_LINK
    ndc             STRING,
    fill_date       DATE,                 -- §4.1a / §4.2 consecutive-fill logic
    days_supply     INT,                  -- §2.3 adequate trial duration
    quantity        NUMBER(10,2),
    dose_text       STRING,               -- §2.1 maximum tolerated dose evidence
    prescriber_id   STRING,
    CONSTRAINT pk_rx_claim PRIMARY KEY (rx_claim_id)
) COMMENT = 'Synthetic pharmacy claims.';

-- ---------------------------------------------------------------------
-- Labs — §3.3 requires HbA1c >= 7.0% within 90 days. LOINC 4548-4.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS LAB_RESULT (
    lab_id          STRING NOT NULL,
    member_id       STRING NOT NULL,
    loinc           STRING,               -- 4548-4 = Hemoglobin A1c
    test_name       STRING,
    value_num       NUMBER(10,3),
    unit            STRING,
    collected_date  DATE,                 -- §3.3 90-day window
    abnormal_flag   STRING,
    CONSTRAINT pk_lab_result PRIMARY KEY (lab_id)
) COMMENT = 'Synthetic laboratory results.';

-- ---------------------------------------------------------------------
-- Prior authorization requests.
--
-- Historical determinations are represented as additional rows with a
-- terminal status — no separate history table is needed, and the AUDIT
-- schema holds the evidence trail for each determination.
--
-- date_of_service drives the effective-dated policy join: the request is
-- adjudicated against the policy version in force on that date.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PA_REQUEST (
    pa_id           STRING NOT NULL,
    member_id       STRING NOT NULL,
    policy_id       STRING,
    requested_ndc   STRING,
    requested_drug  STRING,
    request_date    DATE,
    date_of_service DATE,                 -- selects the policy version in force
    prescriber_id   STRING,
    status          STRING,               -- PENDING | APPROVED | ROUTED_TO_CLINICIAN
    decision_date   DATE,
    CONSTRAINT pk_pa_request PRIMARY KEY (pa_id)
) COMMENT = 'Prior authorization requests. Status is never DENIED by the system.';

-- ---------------------------------------------------------------------
-- Clinical notes — the source for every UNSTRUCTURED leaf.
-- Chunked and indexed into Cortex Search downstream.
-- ---------------------------------------------------------------------
USE SCHEMA DOCS;

CREATE TABLE IF NOT EXISTS CLINICAL_NOTE (
    note_id         STRING NOT NULL,
    member_id       STRING NOT NULL,
    provider_id     STRING,
    note_type       STRING,               -- PROGRESS_NOTE | DISCHARGE_SUMMARY | CONSULT_NOTE | REFERRAL_FAX
    note_date       DATE,
    source_system   STRING,               -- provenance shown in the citation panel
    network_status  STRING,               -- OUT_OF_NETWORK notes are the ones structured data misses
    note_text       STRING,
    CONSTRAINT pk_clinical_note PRIMARY KEY (note_id)
) COMMENT = 'Synthetic clinical notes. No real PHI.';
