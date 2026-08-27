-- =====================================================================
-- VERITY — Prior Authorization Evidence Copilot
-- Snowflake CoCo CLI Hackathon (GCC Edition) — Challenge 4 (HCLS)
--
-- 00_setup.sql — account/warehouse guardrails, database, schemas, roles
-- Idempotent: safe to re-run.
--
-- ALL DATA IN THIS PROJECT IS FULLY SYNTHETIC. No real PHI is ever used.
-- The payer ("Meridian Health Plan") is fictional.
-- =====================================================================

USE ROLE ACCOUNTADMIN;

-- ---------------------------------------------------------------------
-- Cost guardrails (trial account: $400 / 30 days)
-- ---------------------------------------------------------------------
ALTER WAREHOUSE COMPUTE_WH SET
    AUTO_SUSPEND = 60          -- was 300; idle compute is the #1 trial credit leak
    AUTO_RESUME  = TRUE;

-- Cortex cross-region inference: required in AWS_AP_SOUTHEAST_7 (Jakarta),
-- where most Cortex models are not hosted locally.
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- ---------------------------------------------------------------------
-- Database + schemas
-- ---------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS VERITY
    COMMENT = 'Prior Authorization Evidence Copilot — synthetic data only';

USE DATABASE VERITY;

CREATE SCHEMA IF NOT EXISTS RAW
    COMMENT = 'Landing zone: generated synthetic source data, pre-conformance';
CREATE SCHEMA IF NOT EXISTS CORE
    COMMENT = 'Conformed member/claims/clinical model (Member 360 foundation)';
CREATE SCHEMA IF NOT EXISTS DOCS
    COMMENT = 'Unstructured: stages, AI_PARSE_DOCUMENT output, chunks, search services';
CREATE SCHEMA IF NOT EXISTS POLICY
    COMMENT = 'Medical policy registry + machine-checkable criteria tree (Criteria Ledger)';
CREATE SCHEMA IF NOT EXISTS SEMANTIC
    COMMENT = 'Semantic views powering Cortex Analyst';
CREATE SCHEMA IF NOT EXISTS AGENT
    COMMENT = 'Cortex Agent definitions and tool wiring';
CREATE SCHEMA IF NOT EXISTS AUDIT
    COMMENT = 'Immutable decision + evidence audit trail (CMS-0057-F style traceability)';
CREATE SCHEMA IF NOT EXISTS APP
    COMMENT = 'Streamlit in Snowflake — care coordinator / UM nurse console';

-- ---------------------------------------------------------------------
-- Stages for unstructured source documents
-- ---------------------------------------------------------------------
USE SCHEMA DOCS;

-- SNOWFLAKE_SSE encryption is REQUIRED for AI_PARSE_DOCUMENT to read the file.
CREATE STAGE IF NOT EXISTS POLICY_DOCS
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = 'Synthetic medical policy PDFs (Meridian Health Plan — fictional)';

CREATE STAGE IF NOT EXISTS CLINICAL_DOCS
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = 'Synthetic clinical notes, discharge summaries, referral faxes';

-- ---------------------------------------------------------------------
-- Roles: used to demo dynamic PHI masking (clinical vs non-clinical)
-- ---------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS VERITY_CLINICAL_REVIEWER
    COMMENT = 'UM nurse / medical director — may see PHI';
CREATE ROLE IF NOT EXISTS VERITY_ANALYST
    COMMENT = 'Non-clinical operations analyst — PHI is masked';

GRANT USAGE ON DATABASE VERITY TO ROLE VERITY_CLINICAL_REVIEWER;
GRANT USAGE ON DATABASE VERITY TO ROLE VERITY_ANALYST;
GRANT USAGE ON ALL SCHEMAS IN DATABASE VERITY TO ROLE VERITY_CLINICAL_REVIEWER;
GRANT USAGE ON ALL SCHEMAS IN DATABASE VERITY TO ROLE VERITY_ANALYST;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE VERITY_CLINICAL_REVIEWER;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE VERITY_ANALYST;

GRANT ROLE VERITY_CLINICAL_REVIEWER TO ROLE ACCOUNTADMIN;
GRANT ROLE VERITY_ANALYST TO ROLE ACCOUNTADMIN;

SELECT 'VERITY setup complete' AS status, CURRENT_REGION() AS region;
