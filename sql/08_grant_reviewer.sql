-- =====================================================================
-- VERITY — 08_grant_reviewer.sql
-- Provision a read-only clinical reviewer so a teammate can open the
-- console and the agent without ACCOUNTADMIN.
--
-- Run with: python3 scripts/run_sql.py sql/08_grant_reviewer.sql
--
-- No password is set here on purpose. Set it in Snowsight
-- (Admin -> Users -> PRIYANKA -> Reset password) so the credential is
-- never written into a file, a shell history, or a git repo.
--
-- Read-only by design: this role can read every table and run the app,
-- and cannot write, drop, or adjudicate. A reviewer looking at evidence
-- has no reason to be able to mutate it.
-- =====================================================================

USE ROLE ACCOUNTADMIN;

CREATE USER IF NOT EXISTS PRIYANKA
    LOGIN_NAME    = 'PRIYANKA'
    DISPLAY_NAME  = 'Priyanka Karmakar'
    DEFAULT_ROLE  = 'VERITY_CLINICAL_REVIEWER'
    DEFAULT_WAREHOUSE = 'COMPUTE_WH'
    MUST_CHANGE_PASSWORD = TRUE
    COMMENT = 'Team Alpha — clinical reviewer, read-only access to VERITY.';

GRANT ROLE VERITY_CLINICAL_REVIEWER TO USER PRIYANKA;

-- ---------------------------------------------------------------------
-- Compute
-- ---------------------------------------------------------------------
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE VERITY_CLINICAL_REVIEWER;

-- ---------------------------------------------------------------------
-- Read access across the whole project.
-- FUTURE grants included so objects created later stay visible without
-- another round of grants.
-- ---------------------------------------------------------------------
GRANT USAGE ON DATABASE VERITY TO ROLE VERITY_CLINICAL_REVIEWER;
GRANT USAGE ON ALL SCHEMAS IN DATABASE VERITY TO ROLE VERITY_CLINICAL_REVIEWER;
GRANT USAGE ON FUTURE SCHEMAS IN DATABASE VERITY TO ROLE VERITY_CLINICAL_REVIEWER;

GRANT SELECT ON ALL TABLES IN DATABASE VERITY TO ROLE VERITY_CLINICAL_REVIEWER;
GRANT SELECT ON FUTURE TABLES IN DATABASE VERITY TO ROLE VERITY_CLINICAL_REVIEWER;
GRANT SELECT ON ALL VIEWS IN DATABASE VERITY TO ROLE VERITY_CLINICAL_REVIEWER;
GRANT SELECT ON FUTURE VIEWS IN DATABASE VERITY TO ROLE VERITY_CLINICAL_REVIEWER;

-- Semantic view (Cortex Analyst) and the two Cortex Search services.
GRANT SELECT ON ALL SEMANTIC VIEWS IN DATABASE VERITY TO ROLE VERITY_CLINICAL_REVIEWER;
GRANT USAGE ON CORTEX SEARCH SERVICE VERITY.DOCS.POLICY_SEARCH
    TO ROLE VERITY_CLINICAL_REVIEWER;
GRANT USAGE ON CORTEX SEARCH SERVICE VERITY.DOCS.CLINICAL_SEARCH
    TO ROLE VERITY_CLINICAL_REVIEWER;

-- The reviewer console.
GRANT USAGE ON STREAMLIT VERITY.APP.VERITY_CONSOLE TO ROLE VERITY_CLINICAL_REVIEWER;

-- The agent.
GRANT USAGE ON AGENT VERITY.AGENT.VERITY_AGENT TO ROLE VERITY_CLINICAL_REVIEWER;

-- Cortex functions the resolvers and agent rely on.
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE VERITY_CLINICAL_REVIEWER;

SHOW GRANTS TO ROLE VERITY_CLINICAL_REVIEWER;
