-- =====================================================================
-- VERITY — 04_resolvers.sql
-- Two-stage resolution of UNSTRUCTURED criteria leaves.
--
-- Run with: python3 scripts/run_sql.py sql/04_resolvers.sql
--
-- ---------------------------------------------------------------------
-- Why two stages
-- ---------------------------------------------------------------------
-- Retrieval alone is UNSAFE for criterion evaluation. Semantic search
-- matches on topic, not polarity. Observed during the build:
--
--   query : "family history of medullary thyroid carcinoma or MEN2"
--   M09000003 -> "Mother was diagnosed with medullary thyroid carcinoma"
--   M09000002 -> "No personal or family history of thyroid malignancy"
--
-- Both are strong topical matches. Treating "retrieval returned a hit" as
-- "criterion met" would have fired an exclusion against a member whose
-- record explicitly DENIES that history — wrongly blocking their care.
--
-- Reranker scores did separate the two (-1.55 vs -7.22), but a score
-- threshold is arbitrary and would drift with corpus and phrasing.
--
-- So: Cortex Search NARROWS to candidate passages; AI_FILTER DECIDES
-- whether the passage affirmatively asserts the condition. Retrieval
-- proposes, adjudication disposes.
--
-- ---------------------------------------------------------------------
-- Why a loop rather than a set-based join
-- ---------------------------------------------------------------------
-- SEARCH_PREVIEW requires its second argument to be a compile-time
-- constant, so the query payload cannot come from a joined column. The
-- procedure therefore iterates the resolver config and issues one
-- dynamic statement per leaf.
-- =====================================================================

USE DATABASE VERITY;
USE SCHEMA POLICY;

-- Landing table for a single resolution run.
CREATE OR REPLACE TABLE LEAF_EVIDENCE (
    run_id      STRING,
    member_id   STRING,
    policy_id   STRING,
    node_id     STRING,
    chunk_text  STRING,
    citation    STRING,
    affirms     BOOLEAN,
    rerank      FLOAT,          -- retrieval relevance; higher is better
    resolved_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Per-leaf retrieved evidence with its adjudication verdict. Feeds both the rollup and the audit trail.';

-- rerank exists so the console can show the STRONGEST affirming passage.
-- Several chunks often affirm the same criterion, and picking arbitrarily
-- (e.g. MAX over the text) surfaces filler: for the sulfonylurea leaf that
-- meant showing "Patient reports adherence to diet" instead of "Glipizide
-- discontinued after recurrent symptomatic hypoglycemia". The verdict was
-- right either way; the citation a reviewer reads was not.


CREATE OR REPLACE PROCEDURE RESOLVE_UNSTRUCTURED(p_member_id STRING, p_policy_id STRING)
RETURNS TABLE (node_id STRING, verdict STRING, citation STRING, evidence STRING)
LANGUAGE SQL
COMMENT = 'Stage 1: member-scoped Cortex Search per unstructured leaf. Stage 2: AI_FILTER adjudicates whether retrieved text AFFIRMS the condition. Writes evidence to LEAF_EVIDENCE and returns per-leaf verdicts.'
AS
$$
DECLARE
    run_id  STRING;
    payload STRING;
    stmt    STRING;
    v_node  STRING;
    v_query STRING;
    v_assert STRING;
    v_topk  INT;
    res     RESULTSET;
    cur CURSOR FOR
        SELECT node_id, search_query, assertion, top_k
        FROM VERITY.POLICY.LEAF_RESOLVER
        WHERE policy_id = ?;
BEGIN
    run_id := UUID_STRING();

    OPEN cur USING (p_policy_id);
    FOR rec IN cur DO
        -- Cursor fields are not visible inside a nested SELECT, so copy
        -- them into locals before building the payload.
        v_node   := rec.node_id;
        v_query  := rec.search_query;
        v_assert := rec.assertion;
        v_topk   := rec.top_k;

        -- Member filter is applied INSIDE the search request, so a
        -- retrieval can never surface another member's record.
        payload := (SELECT TO_JSON(OBJECT_CONSTRUCT(
            'query',   :v_query,
            'columns', ARRAY_CONSTRUCT('chunk_text', 'citation', 'member_id'),
            'filter',  OBJECT_CONSTRUCT('@eq', OBJECT_CONSTRUCT('member_id', :p_member_id)),
            'limit',   :v_topk
        )));

        stmt := 'INSERT INTO VERITY.POLICY.LEAF_EVIDENCE '
             || '(run_id, member_id, policy_id, node_id, chunk_text, citation, affirms, rerank) '
             || 'SELECT ''' || :run_id || ''', ''' || :p_member_id || ''', '''
             || :p_policy_id || ''', ''' || :v_node || ''', '
             || 'f.value:chunk_text::STRING, f.value:citation::STRING, '
             || 'AI_FILTER(PROMPT(''' || REPLACE(:v_assert, '''', '''''')
             || ' Text: {0}'', f.value:chunk_text::STRING)), '
             || 'f.value:"@scores":reranker_score::FLOAT '
             || 'FROM TABLE(FLATTEN(input => PARSE_JSON('
             || 'SNOWFLAKE.CORTEX.SEARCH_PREVIEW(''VERITY.DOCS.CLINICAL_SEARCH'', '''
             || :payload || ''')):results)) f';

        EXECUTE IMMEDIATE :stmt;
    END FOR;
    CLOSE cur;

    -- A leaf is MET if ANY retrieved passage affirmatively asserts it.
    -- Leaves with no retrieved evidence at all are absent from
    -- LEAF_EVIDENCE, so the outer join in the rollup treats them as
    -- NOT_MET rather than silently dropping them.
    -- Show the STRONGEST affirming passage, not an arbitrary one.
    res := (
        WITH ranked AS (
            SELECT node_id, citation, chunk_text, affirms,
                   ROW_NUMBER() OVER (PARTITION BY node_id
                                      ORDER BY affirms DESC, rerank DESC NULLS LAST) AS rn
            FROM VERITY.POLICY.LEAF_EVIDENCE
            WHERE run_id = :run_id)
        SELECT node_id,
               IFF(MAX(affirms), 'MET', 'NOT_MET')                        AS verdict,
               MAX(IFF(rn = 1 AND affirms, citation, NULL))               AS citation,
               MAX(IFF(rn = 1 AND affirms, LEFT(chunk_text, 320), NULL))  AS evidence
        FROM ranked
        GROUP BY node_id
        ORDER BY node_id);

    RETURN TABLE(res);
END;
$$;
