-- =====================================================================
-- VERITY — 01_policy_model.sql
-- Policy registry + Criteria Ledger (the machine-checkable criteria tree)
--
-- Run with:  snow sql -c hackathon -q "<contents>"
-- (snow sql -f is blocked in the agent harness; see CLAUDE.md)
-- =====================================================================

USE DATABASE VERITY;
USE SCHEMA POLICY;

-- ---------------------------------------------------------------------
-- Policy registry — EFFECTIVE-DATED.
--
-- This is the "moat" table. A determination must be evaluated against the
-- policy version in force on the DATE OF SERVICE, not the version in force
-- on the date of review. Effective dating makes that a join predicate
-- rather than a wish.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS POLICY_REGISTRY (
    policy_id           STRING        NOT NULL,
    policy_version      STRING        NOT NULL,
    title               STRING,
    payer               STRING,
    lob                 STRING,
    effective_date      DATE          NOT NULL,
    end_date            DATE,             -- NULL = currently in force
    supersedes_version  STRING,
    source_file         STRING,
    loaded_at           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_policy_registry PRIMARY KEY (policy_id, policy_version)
)
COMMENT = 'Effective-dated medical policy versions. Synthetic, fictional payer.';

-- ---------------------------------------------------------------------
-- Criteria Ledger
--
-- A criterion tree per policy version. Every node is GROUP or LEAF:
--
--   GROUP.combinator  ALL_OF  -> all children must be MET
--                     ANY_OF  -> at least one child MET
--                     NONE_OF -> no child may be MET (exclusions)
--
--   LEAF.evidence_type STRUCTURED   -> resolved by SQL over the semantic view
--                      UNSTRUCTURED -> resolved by Cortex Search over notes
--
-- Leaves are single-source on purpose. A policy criterion offering two
-- routes ("adequate trial ... OR documented intolerance") becomes an
-- ANY_OF group over one STRUCTURED and one UNSTRUCTURED leaf, so the
-- console can show the structured check failing and the unstructured
-- check carrying it.
--
-- The determination is a deterministic rollup of this tree. The LLM
-- resolves individual leaves and explains results; it never renders
-- the verdict.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS POLICY_CRITERIA (
    policy_id       STRING  NOT NULL,
    policy_version  STRING  NOT NULL,
    node_id         STRING  NOT NULL,
    parent_id       STRING,               -- NULL only for ROOT
    node_type       STRING  NOT NULL,     -- GROUP | LEAF
    combinator      STRING,               -- GROUP only: ALL_OF | ANY_OF | NONE_OF
    section_ref     STRING  NOT NULL,     -- e.g. '4.1' — drives the citation
    label           STRING  NOT NULL,
    evidence_type   STRING,               -- LEAF only: STRUCTURED | UNSTRUCTURED
    test_expr       STRING,               -- LEAF only: contract for the resolver
    sort_order      INT,
    source          STRING  DEFAULT 'GROUND_TRUTH',  -- GROUND_TRUTH | AI_EXTRACTED
    loaded_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_policy_criteria PRIMARY KEY (policy_id, policy_version, node_id, source)
)
COMMENT = 'Criteria Ledger: machine-checkable criterion tree per policy version.';

-- Landing table for the NDJSON produced by load_criteria.py.
CREATE TABLE IF NOT EXISTS _CRITERIA_STAGE (v VARIANT)
COMMENT = 'Transient landing zone for criteria tree loads.';

CREATE STAGE IF NOT EXISTS CRITERIA_LOAD
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = 'Internal stage for criteria tree NDJSON payloads.';
