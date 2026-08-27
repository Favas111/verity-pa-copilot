-- =====================================================================
-- VERITY — 05_rollup.sql
-- Structured leaf resolution + the deterministic rollup engine.
--
-- Run with: python3 scripts/run_sql.py sql/05_rollup.sql
--
-- ---------------------------------------------------------------------
-- Where the "AI cannot deny" guarantee actually lives
-- ---------------------------------------------------------------------
-- The determination is arithmetic over cited leaves, not a model call.
-- An LLM resolves individual unstructured leaves and explains results;
-- it never renders the verdict. ROOT rolls up to exactly two outcomes:
--
--     ROOT = MET  ->  APPROVE
--     otherwise   ->  ROUTE_TO_CLINICIAN
--
-- There is no code path that emits DENY. That is a structural property
-- of this file, not an instruction to a model that could be ignored.
--
-- ---------------------------------------------------------------------
-- Three verdict states, not two
-- ---------------------------------------------------------------------
--   MET                   satisfied, with a citation
--   NOT_MET               evidence exists and fails the criterion
--   INSUFFICIENT_EVIDENCE no evidence was found either way
--
-- The third state is what makes "here is exactly what is missing"
-- honest. Member B has no HbA1c inside the 90-day window: that is
-- INSUFFICIENT_EVIDENCE ("we need a recent HbA1c"), not NOT_MET ("the
-- HbA1c is too low"). Collapsing them would tell a clinician something
-- untrue about their patient.
-- =====================================================================

USE DATABASE VERITY;
USE SCHEMA CORE;

-- ---------------------------------------------------------------------
-- Structured leaf verdicts — one row per (pa_id, node_id).
-- Every branch carries its own citation: a reviewer must see WHY a
-- criterion passed, not merely that it did.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW V_STRUCTURED_VERDICT AS
WITH pa AS (
    SELECT p.pa_id, p.member_id, p.policy_id, p.date_of_service, m.date_of_birth
    FROM PA_REQUEST p JOIN MEMBER m ON m.member_id = p.member_id),

dx AS (
    SELECT pa.pa_id, COUNT(*) AS n,
           MAX(c.claim_id) AS claim_id, MAX(d.icd10) AS icd10,
           MAX(c.service_date) AS svc_date
    FROM pa
    JOIN CLAIM c           ON c.member_id = pa.member_id
    JOIN CLAIM_DIAGNOSIS d ON d.claim_id  = c.claim_id
    WHERE d.icd10 LIKE 'E11%'
      AND c.service_date BETWEEN DATEADD(month,-12,pa.date_of_service) AND pa.date_of_service
    GROUP BY pa.pa_id),

a1c AS (
    SELECT pa.pa_id, COUNT(*) AS n, MAX(l.value_num) AS best,
           MAX(l.collected_date) AS collected, MAX(l.lab_id) AS lab_id
    FROM pa
    JOIN LAB_RESULT l ON l.member_id = pa.member_id
    WHERE l.loinc = '4548-4'
      AND l.collected_date BETWEEN DATEADD(day,-90,pa.date_of_service) AND pa.date_of_service
    GROUP BY pa.pa_id),

-- Step therapy via the identity-linked trial view. V_DRUG_TRIAL already
-- spans prior member ids per policy section 2.3, so a trial completed
-- under a previous carrier counts here with no special-casing.
trial AS (
    SELECT pa.pa_id, t.drug_class,
           MAX(t.trial_days)   AS best_days,
           MAX(t.trial_months) AS best_months,
           MAX(t.trial_start)  AS t_start,
           MAX(t.trial_end)    AS t_end,
           MAX(t.fill_count)   AS fills,
           MAX(ARRAY_TO_STRING(t.evidence_sources, ', ')) AS sources
    FROM pa JOIN V_DRUG_TRIAL t ON t.member_id = pa.member_id
    GROUP BY pa.pa_id, t.drug_class),

steps AS (
    SELECT 'C4.1a' AS node_id, 'BIGUANIDE'       AS drug_class UNION ALL
    SELECT 'C4.2a',            'SGLT2_INHIBITOR'             UNION ALL
    SELECT 'C4.2b',            'SULFONYLUREA')

-- §3.1 age
SELECT pa_id, 'C3.1' AS node_id,
       IFF(FLOOR(DATEDIFF(day,date_of_birth,date_of_service)/365.25) >= 18,'MET','NOT_MET') AS verdict,
       'CORE.MEMBER date_of_birth' AS citation,
       'Age ' || FLOOR(DATEDIFF(day,date_of_birth,date_of_service)/365.25)::STRING
              || ' years on date of service' AS evidence
FROM pa

UNION ALL
-- §3.2a diagnosis
SELECT p.pa_id, 'C3.2a',
       IFF(COALESCE(d.n,0) > 0,'MET','INSUFFICIENT_EVIDENCE'),
       COALESCE('Claim ' || d.claim_id,'CORE.CLAIM'),
       COALESCE('ICD-10 ' || d.icd10 || ' on claim dated ' || d.svc_date::STRING,
                'No E11.* diagnosis on any claim in the preceding 12 months')
FROM pa p LEFT JOIN dx d ON d.pa_id = p.pa_id

UNION ALL
-- §3.3 glycemic control
SELECT p.pa_id, 'C3.3',
       CASE WHEN COALESCE(a.n,0) = 0 THEN 'INSUFFICIENT_EVIDENCE'
            WHEN a.best >= 7.0       THEN 'MET'
            ELSE 'NOT_MET' END,
       COALESCE('Lab ' || a.lab_id,'CORE.LAB_RESULT'),
       COALESCE('HbA1c ' || a.best::STRING || '% collected ' || a.collected::STRING,
                'No HbA1c result within 90 days of the date of service')
FROM pa p LEFT JOIN a1c a ON a.pa_id = p.pa_id

UNION ALL
-- §4.1a / §4.2a / §4.2b step therapy
SELECT p.pa_id, s.node_id,
       CASE WHEN t.best_days IS NULL     THEN 'INSUFFICIENT_EVIDENCE'
            WHEN t.best_days >= 90       THEN 'MET'
            ELSE 'NOT_MET' END,
       COALESCE('CORE.RX_CLAIM (' || t.fills::STRING || ' fills)','CORE.RX_CLAIM'),
       CASE WHEN t.best_days IS NULL
            THEN 'No ' || LOWER(REPLACE(s.drug_class,'_',' ')) || ' fills on record'
            ELSE t.best_months::STRING || ' months continuous '
                 || LOWER(REPLACE(s.drug_class,'_',' '))
                 || ' (' || t.t_start::STRING || ' to ' || t.t_end::STRING || ')'
                 || ', source: ' || t.sources
       END
FROM pa p
CROSS JOIN steps s
LEFT JOIN trial t ON t.pa_id = p.pa_id AND t.drug_class = s.drug_class;


-- =====================================================================
-- Determination store — the audit trail.
-- =====================================================================
USE SCHEMA AUDIT;

CREATE TABLE IF NOT EXISTS DETERMINATION (
    determination_id STRING,
    pa_id            STRING,
    member_id        STRING,
    policy_id        STRING,
    policy_version   STRING,
    outcome          STRING,        -- APPROVE | ROUTE_TO_CLINICIAN
    root_verdict     STRING,
    blocking_reasons STRING,
    decided_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'One row per adjudication. Outcome is never DENY by construction.';

CREATE TABLE IF NOT EXISTS DETERMINATION_NODE (
    determination_id STRING,
    node_id          STRING,
    parent_id        STRING,
    node_type        STRING,
    combinator       STRING,
    section_ref      STRING,
    label            STRING,
    evidence_type    STRING,
    verdict          STRING,
    citation         STRING,
    evidence         STRING,
    depth            INT,
    sort_order       INT
) COMMENT = 'Full per-node verdict trail for one determination — the evidence packet a reviewer reads.';


-- =====================================================================
-- ADJUDICATE — the deterministic rollup.
--
-- Snowflake recursive CTEs walk top-down; rollup is inherently
-- bottom-up, so the procedure computes node depth once and then folds
-- one level at a time from the deepest upward. The tree is shallow
-- (depth 4 here) and this stays correct for any depth.
-- =====================================================================
USE SCHEMA POLICY;

CREATE OR REPLACE PROCEDURE ADJUDICATE(p_pa_id STRING)
RETURNS TABLE (outcome STRING, root_verdict STRING, blocking_reasons STRING, determination_id STRING)
LANGUAGE SQL
COMMENT = 'Deterministic rollup of the Criteria Ledger for one PA request. Emits APPROVE or ROUTE_TO_CLINICIAN only.'
AS
$$
DECLARE
    det_id     STRING;
    v_member   STRING;
    v_policy   STRING;
    v_version  STRING;
    v_dos      DATE;
    max_depth  INT;
    d          INT;
    root_v     STRING;
    outcome    STRING;
    blockers   STRING;
    res        RESULTSET;
BEGIN
    det_id := UUID_STRING();

    SELECT member_id, policy_id, date_of_service
      INTO :v_member, :v_policy, :v_dos
      FROM VERITY.CORE.PA_REQUEST WHERE pa_id = :p_pa_id;

    -- Effective-dated policy selection: the version in force on the DATE
    -- OF SERVICE, not the version in force today. Policies change; a
    -- determination made against the wrong version is indefensible.
    SELECT policy_version INTO :v_version
      FROM VERITY.POLICY.POLICY_REGISTRY
     WHERE policy_id = :v_policy
       AND :v_dos >= effective_date
       AND (end_date IS NULL OR :v_dos < end_date)
     LIMIT 1;

    -- Resolve unstructured leaves for this member (retrieve + adjudicate).
    CALL VERITY.POLICY.RESOLVE_UNSTRUCTURED(:v_member, :v_policy);

    -- Seed every node with its leaf verdict, or NULL for groups.
    CREATE OR REPLACE TEMPORARY TABLE _roll AS
    WITH RECURSIVE depths AS (
        SELECT node_id, parent_id, 0 AS depth
        FROM VERITY.POLICY.POLICY_CRITERIA
        WHERE policy_id = :v_policy AND policy_version = :v_version
          AND source = 'GROUND_TRUTH' AND parent_id IS NULL
        UNION ALL
        SELECT c.node_id, c.parent_id, d.depth + 1
        FROM VERITY.POLICY.POLICY_CRITERIA c
        JOIN depths d ON c.parent_id = d.node_id
        WHERE c.policy_id = :v_policy AND c.policy_version = :v_version
          AND c.source = 'GROUND_TRUTH'),
    -- Rank affirming passages so the console cites the STRONGEST one.
    -- Picking arbitrarily surfaced filler ("Patient reports adherence to
    -- diet") over the passage that actually establishes the criterion
    -- ("Glipizide discontinued after recurrent symptomatic hypoglycemia").
    ranked AS (
        SELECT node_id, citation, chunk_text, affirms,
               ROW_NUMBER() OVER (PARTITION BY node_id
                                  ORDER BY affirms DESC, rerank DESC NULLS LAST) AS rn
        FROM VERITY.POLICY.LEAF_EVIDENCE
        WHERE member_id = :v_member AND policy_id = :v_policy
          AND run_id = (SELECT run_id FROM VERITY.POLICY.LEAF_EVIDENCE
                        WHERE member_id = :v_member AND policy_id = :v_policy
                        ORDER BY resolved_at DESC LIMIT 1)),
    unstruct AS (
        SELECT node_id,
               IFF(MAX(affirms),'MET','NOT_MET')            AS verdict,
               MAX(IFF(rn = 1 AND affirms, citation, NULL)) AS citation,
               -- Trim on a word boundary; a mid-word cut ("PLAN: Endocrinology h")
               -- reads as a rendering fault to anyone looking at the citation panel.
               MAX(IFF(rn = 1 AND affirms,
                       REGEXP_REPLACE(LEFT(chunk_text, 340), '\\\\s+\\\\S*$', '') ||
                       IFF(LENGTH(chunk_text) > 340, ' …', ''),
                       NULL))                               AS evidence
        FROM ranked
        GROUP BY node_id)
    SELECT c.node_id, c.parent_id, c.node_type, c.combinator, c.section_ref,
           c.label, c.evidence_type, dp.depth, c.sort_order,
           CASE
             WHEN c.node_type = 'GROUP'              THEN NULL
             WHEN c.evidence_type = 'STRUCTURED'     THEN sv.verdict
             WHEN us.node_id IS NOT NULL             THEN us.verdict
             ELSE 'INSUFFICIENT_EVIDENCE'
           END AS verdict,
           CASE WHEN c.evidence_type = 'STRUCTURED' THEN sv.citation ELSE us.citation END AS citation,
           CASE WHEN c.evidence_type = 'STRUCTURED' THEN sv.evidence ELSE us.evidence END AS evidence
    FROM VERITY.POLICY.POLICY_CRITERIA c
    JOIN depths dp ON dp.node_id = c.node_id
    LEFT JOIN VERITY.CORE.V_STRUCTURED_VERDICT sv
           ON sv.node_id = c.node_id AND sv.pa_id = :p_pa_id
    LEFT JOIN unstruct us ON us.node_id = c.node_id
    WHERE c.policy_id = :v_policy AND c.policy_version = :v_version
      AND c.source = 'GROUND_TRUTH';

    SELECT MAX(depth) INTO :max_depth FROM _roll;

    -- Fold upward, one level at a time.
    --   ALL_OF  : any NOT_MET -> NOT_MET; else any INSUFFICIENT -> INSUFFICIENT; else MET
    --   ANY_OF  : any MET -> MET; else any INSUFFICIENT -> INSUFFICIENT; else NOT_MET
    --   NONE_OF : any MET -> NOT_MET (an exclusion fired);
    --             else any INSUFFICIENT -> INSUFFICIENT; else MET
    d := :max_depth - 1;
    WHILE (d >= 0) DO
        UPDATE _roll g
           SET verdict = k.rolled
          FROM (
            SELECT p.node_id,
                   CASE p.combinator
                     WHEN 'ALL_OF' THEN
                       CASE WHEN SUM(IFF(ch.verdict='NOT_MET',1,0)) > 0 THEN 'NOT_MET'
                            WHEN SUM(IFF(ch.verdict='INSUFFICIENT_EVIDENCE',1,0)) > 0 THEN 'INSUFFICIENT_EVIDENCE'
                            ELSE 'MET' END
                     WHEN 'ANY_OF' THEN
                       CASE WHEN SUM(IFF(ch.verdict='MET',1,0)) > 0 THEN 'MET'
                            WHEN SUM(IFF(ch.verdict='INSUFFICIENT_EVIDENCE',1,0)) > 0 THEN 'INSUFFICIENT_EVIDENCE'
                            ELSE 'NOT_MET' END
                     WHEN 'NONE_OF' THEN
                       CASE WHEN SUM(IFF(ch.verdict='MET',1,0)) > 0 THEN 'NOT_MET'
                            WHEN SUM(IFF(ch.verdict='INSUFFICIENT_EVIDENCE',1,0)) > 0 THEN 'INSUFFICIENT_EVIDENCE'
                            ELSE 'MET' END
                   END AS rolled
            FROM _roll p JOIN _roll ch ON ch.parent_id = p.node_id
            WHERE p.node_type = 'GROUP' AND p.depth = :d
            GROUP BY p.node_id, p.combinator) k
         WHERE g.node_id = k.node_id;
        d := d - 1;
    END WHILE;

    SELECT verdict INTO :root_v FROM _roll WHERE parent_id IS NULL;

    -- The only two outcomes this system can produce.
    outcome := IFF(:root_v = 'MET', 'APPROVE', 'ROUTE_TO_CLINICIAN');

    -- What a reviewer needs to act on: the leaves actually RESPONSIBLE for the
    -- outcome. This is a downward descent from ROOT, not a flat filter.
    --
    -- "Not MET under a group that is not MET" is the wrong test twice over:
    --   * it blames leaves under a failed sub-group whose parent ANY_OF was
    --     satisfied by a sibling route — those leaves changed nothing;
    --   * for exclusions it blames the wrong leaves entirely, since under
    --     NONE_OF a MET child is the exclusion that fired, and NOT_MET
    --     children are exactly the exclusions that did NOT apply.
    --
    -- Responsibility by combinator:
    --   ALL_OF  -> children that are not MET
    --   ANY_OF  -> every child (no route succeeded)
    --   NONE_OF -> children that ARE MET (the exclusions that fired)
    CREATE OR REPLACE TEMPORARY TABLE _blame AS
    WITH RECURSIVE resp AS (
        SELECT node_id, parent_id, node_type, combinator, verdict,
               section_ref, label, sort_order
        FROM _roll
        WHERE parent_id IS NULL AND verdict <> 'MET'
        UNION ALL
        SELECT c.node_id, c.parent_id, c.node_type, c.combinator, c.verdict,
               c.section_ref, c.label, c.sort_order
        FROM _roll c
        JOIN resp p ON c.parent_id = p.node_id
        WHERE p.node_type = 'GROUP'
          AND CASE p.combinator
                WHEN 'ALL_OF'  THEN c.verdict <> 'MET'
                WHEN 'ANY_OF'  THEN TRUE
                WHEN 'NONE_OF' THEN c.verdict = 'MET'
                ELSE FALSE
              END)
    SELECT r.node_id, r.section_ref, r.label, r.verdict, r.sort_order,
           -- An exclusion that fired reads as an exclusion, not a shortfall.
           IFF(pg.combinator = 'NONE_OF' AND r.verdict = 'MET',
               'EXCLUSION APPLIES', r.verdict) AS reason
    FROM resp r
    LEFT JOIN _roll pg ON pg.node_id = r.parent_id
    WHERE r.node_type = 'LEAF';

    SELECT LISTAGG('§' || section_ref || ' ' || label || ' [' || reason || ']', ' | ')
             WITHIN GROUP (ORDER BY sort_order)
      INTO :blockers
      FROM _blame;

    INSERT INTO VERITY.AUDIT.DETERMINATION
      (determination_id, pa_id, member_id, policy_id, policy_version,
       outcome, root_verdict, blocking_reasons)
    SELECT :det_id, :p_pa_id, :v_member, :v_policy, :v_version,
           :outcome, :root_v, :blockers;

    INSERT INTO VERITY.AUDIT.DETERMINATION_NODE
      (determination_id, node_id, parent_id, node_type, combinator, section_ref,
       label, evidence_type, verdict, citation, evidence, depth, sort_order)
    SELECT :det_id, node_id, parent_id, node_type, combinator, section_ref,
           label, evidence_type, verdict, citation, evidence, depth, sort_order
    FROM _roll;

    -- Carry the outcome back to the request itself. Without this the
    -- request stays PENDING forever and anything reading PA_REQUEST -
    -- the agent included - reports that no determination has been run,
    -- while AUDIT.DETERMINATION says otherwise. Two sources of truth
    -- disagreeing about whether a decision exists is worse than either
    -- being wrong.
    UPDATE VERITY.CORE.PA_REQUEST
       SET status = :outcome,
           decision_date = CURRENT_DATE()
     WHERE pa_id = :p_pa_id;

    res := (SELECT :outcome AS outcome, :root_v AS root_verdict,
                   :blockers AS blocking_reasons, :det_id AS determination_id);
    RETURN TABLE(res);
END;
$$;
