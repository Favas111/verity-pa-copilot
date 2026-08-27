-- =====================================================================
-- VERITY — 03b_chunks_search.sql
-- Section-aware policy chunks, clinical note chunks, and the two
-- Cortex Search services.
--
-- Run with: python3 scripts/run_sql.py sql/03b_chunks_search.sql
--
-- Must run through run_sql.py, not inline `snow sql -q`: the citation
-- string contains a section sign, and shell escaping mangles it. That is
-- exactly how citations shipped reading "MHP-PA-0142 $4.1" instead of
-- "MHP-PA-0142 §4.1" — the agent dutifully quoted the corrupted string.
--
-- ---------------------------------------------------------------------
-- Why two services and not one
-- ---------------------------------------------------------------------
-- POLICY_SEARCH holds rules; CLINICAL_SEARCH holds patient records. Kept
-- separate so a citation can never conflate "what the plan requires" with
-- "what this member's chart says", and so member_id filtering applies to
-- the clinical corpus only.
--
-- Policy chunks are split on HEADING boundaries rather than a fixed
-- character window, because the section reference IS the citation. A
-- reviewer needs "section 4.1", not "chunk 37".
-- =====================================================================

USE DATABASE VERITY;
USE SCHEMA DOCS;

-- ---------------------------------------------------------------------
-- Policy chunks — one row per policy section
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE POLICY_CHUNK AS
WITH lines AS (
  SELECT p.policy_id, f.index AS ln, f.value::STRING AS txt
  FROM POLICY_PARSED p,
  LATERAL FLATTEN(input => SPLIT(p.parsed:content::STRING, CHAR(10))) f),
marked AS (
  SELECT policy_id, ln, txt,
    -- Anchored at the start so the document title ("Medical Policy
    -- MHP-PA-0142") does not yield a bogus section number from its id.
    CASE WHEN TRIM(txt) LIKE '#%'
         THEN NULLIF(REGEXP_SUBSTR(TRIM(REGEXP_REPLACE(txt,'^#+[ ]*','')),
                                   '^[0-9]+([.][0-9]+)?'), '')
    END AS sec,
    CASE WHEN TRIM(txt) LIKE '#%'
         THEN TRIM(REGEXP_REPLACE(txt,'^#+[ ]*',''))
    END AS hd
  FROM lines),
filled AS (
  SELECT policy_id, ln, txt,
    LAST_VALUE(sec IGNORE NULLS) OVER (PARTITION BY policy_id ORDER BY ln
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS section_ref,
    LAST_VALUE(hd  IGNORE NULLS) OVER (PARTITION BY policy_id ORDER BY ln
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS section_heading
  FROM marked)
SELECT
  policy_id, section_ref, section_heading,
  policy_id || ' §' || section_ref AS citation,
  TRIM(LISTAGG(txt, '\n') WITHIN GROUP (ORDER BY ln)) AS chunk_text
FROM filled
WHERE section_ref IS NOT NULL
GROUP BY policy_id, section_ref, section_heading
HAVING LENGTH(TRIM(LISTAGG(txt, '\n') WITHIN GROUP (ORDER BY ln))) > 40;

-- ---------------------------------------------------------------------
-- Clinical note chunks — 600 chars with 100 overlap, so a specific
-- assertion ("discontinued due to recurrent urinary tract infections")
-- lands in a focused passage rather than a wall of note.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE NOTE_CHUNK AS
SELECT
  n.note_id, n.member_id, n.provider_id, n.note_type, n.note_date,
  n.source_system, n.network_status,
  c.index AS chunk_no,
  n.note_id || '#' || c.index::STRING AS chunk_id,
  n.note_type || ' ' || n.note_date::STRING || ' (' || n.source_system || ')' AS citation,
  c.value::STRING AS chunk_text
FROM CLINICAL_NOTE n,
LATERAL FLATTEN(input => SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER(
  n.note_text, 'none', 600, 100)) c;

-- ---------------------------------------------------------------------
-- Search services.
--
-- ATTRIBUTES are what make member scoping enforceable: the clinical
-- service filters on member_id inside the request, so a retrieval
-- cannot surface another member's record.
--
-- A live service bills continuously. Drop unused ones on a trial account.
-- ---------------------------------------------------------------------
CREATE OR REPLACE CORTEX SEARCH SERVICE POLICY_SEARCH
  ON chunk_text
  ATTRIBUTES policy_id, section_ref, citation
  WAREHOUSE = COMPUTE_WH
  TARGET_LAG = '1 hour'
  AS SELECT policy_id, section_ref, section_heading, citation, chunk_text
     FROM POLICY_CHUNK;

CREATE OR REPLACE CORTEX SEARCH SERVICE CLINICAL_SEARCH
  ON chunk_text
  ATTRIBUTES member_id, note_id, note_type, network_status, citation
  WAREHOUSE = COMPUTE_WH
  TARGET_LAG = '1 hour'
  AS SELECT chunk_id, member_id, note_id, note_type, note_date, source_system,
            network_status, citation, chunk_text
     FROM NOTE_CHUNK;

SELECT citation, section_heading FROM POLICY_CHUNK
ORDER BY SPLIT_PART(section_ref,'.',1)::INT,
         COALESCE(NULLIF(SPLIT_PART(section_ref,'.',2),''),'0')::INT
LIMIT 5;
