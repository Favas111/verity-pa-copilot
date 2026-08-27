-- =====================================================================
-- VERITY — 06_semantic.sql
-- Member 360 semantic view: the natural-language layer over structured data.
--
-- Run with: python3 scripts/run_sql.py sql/06_semantic.sql
--
-- ---------------------------------------------------------------------
-- What this is for, and what it is NOT for
-- ---------------------------------------------------------------------
-- This powers ad-hoc population questions — "how many members have an
-- HbA1c above 9?", "which plans have the most pending requests?" — asked
-- in English by a non-SQL user via Cortex Analyst.
--
-- It does NOT decide prior authorizations. A determination is a
-- deterministic rollup of the Criteria Ledger (05_rollup.sql), because a
-- coverage decision must be reproducible and individually cited. Text-to-
-- SQL is the right tool for exploration and the wrong tool for
-- adjudication, and keeping that line clean is the point.
--
-- ---------------------------------------------------------------------
-- Syntax notes (both cost time to discover)
-- ---------------------------------------------------------------------
--   * Comments and synonyms use the EQUALS form:
--       COMMENT = '...'          not   COMMENT '...'
--       WITH SYNONYMS = (...)    not   WITH SYNONYMS (...)
--   * Every dimension/metric is namespaced to its logical table (m.age),
--     and relationships are declared separately from the table list.
--   * Clause ORDER is fixed and enforced:
--       TABLES -> RELATIONSHIPS -> FACTS -> DIMENSIONS -> METRICS
--     Putting FACTS after DIMENSIONS fails with "unexpected 'FACTS'".
--
-- Synonyms are not decoration: they are how a nurse asking about
-- "patients" reaches a table called MEMBER. Cortex Analyst reads the
-- comments to choose joins, so vague comments produce vague SQL.
-- =====================================================================

USE DATABASE VERITY;
USE SCHEMA SEMANTIC;

CREATE OR REPLACE SEMANTIC VIEW MEMBER_360

  TABLES (
    members AS VERITY.CORE.MEMBER
      PRIMARY KEY (member_id)
      WITH SYNONYMS = ('member', 'patient', 'enrollee', 'people', 'population')
      COMMENT = 'Health plan members. One row per member. All data is synthetic.',

    eligibility AS VERITY.CORE.ELIGIBILITY
      WITH SYNONYMS = ('coverage', 'enrollment', 'plan')
      COMMENT = 'Coverage spans. Which plan and line of business a member belongs to.',

    claims AS VERITY.CORE.CLAIM
      PRIMARY KEY (claim_id)
      WITH SYNONYMS = ('medical claims', 'encounters', 'visits')
      COMMENT = 'Medical claim headers with billed and allowed amounts.',

    diagnoses AS VERITY.CORE.CLAIM_DIAGNOSIS
      WITH SYNONYMS = ('icd codes', 'conditions', 'diagnosis codes')
      COMMENT = 'ICD-10 diagnosis codes on each claim. E11 codes are Type 2 Diabetes.',

    rx AS VERITY.CORE.RX_CLAIM
      PRIMARY KEY (rx_claim_id)
      WITH SYNONYMS = ('pharmacy claims', 'prescriptions', 'fills', 'medications')
      COMMENT = 'Pharmacy fills. days_supply drives continuous-therapy calculations.',

    drugs AS VERITY.CORE.DRUG_REFERENCE
      PRIMARY KEY (ndc)
      WITH SYNONYMS = ('drug reference', 'medication list', 'formulary')
      COMMENT = 'Drug reference mapping NDC to drug class and formulary tier.',

    labs AS VERITY.CORE.LAB_RESULT
      PRIMARY KEY (lab_id)
      WITH SYNONYMS = ('lab results', 'laboratory', 'test results')
      COMMENT = 'Laboratory results. LOINC 4548-4 is HbA1c, reported as a percentage.',

    providers AS VERITY.CORE.PROVIDER
      PRIMARY KEY (provider_id)
      WITH SYNONYMS = ('doctors', 'clinicians', 'practices')
      COMMENT = 'Rendering providers and whether they are in or out of network.',

    requests AS VERITY.CORE.PA_REQUEST
      PRIMARY KEY (pa_id)
      WITH SYNONYMS = ('prior authorizations', 'PA requests', 'auth requests')
      COMMENT = 'Prior authorization requests awaiting or holding a determination.'
  )

  RELATIONSHIPS (
    eligibility_to_member AS eligibility (member_id) REFERENCES members,
    claims_to_member      AS claims      (member_id) REFERENCES members,
    diagnoses_to_claim    AS diagnoses   (claim_id)  REFERENCES claims,
    rx_to_member          AS rx          (member_id) REFERENCES members,
    rx_to_drug            AS rx          (ndc)       REFERENCES drugs,
    labs_to_member        AS labs        (member_id) REFERENCES members,
    claims_to_provider    AS claims      (provider_id) REFERENCES providers,
    requests_to_member    AS requests    (member_id) REFERENCES members
  )

  FACTS (
    claims.billed_amount   AS billed_amount  COMMENT = 'Amount billed by the provider.',
    claims.allowed_amount  AS allowed_amount COMMENT = 'Amount allowed by the plan.',
    labs.value_num         AS value_num      COMMENT = 'Numeric lab result. For HbA1c this is a percentage.'
  )

  DIMENSIONS (
    members.member_id   AS member_id
      COMMENT = 'Unique member identifier.',
    members.age         AS FLOOR(DATEDIFF(day, date_of_birth, CURRENT_DATE()) / 365.25)
      WITH SYNONYMS = ('years old', 'member age')
      COMMENT = 'Member age in years as of today.',
    members.sex         AS sex
      COMMENT = 'Member sex, F or M.',
    members.state       AS state
      WITH SYNONYMS = ('residence', 'location')
      COMMENT = 'Two-letter state of residence.',
    members.is_golden   AS is_golden
      COMMENT = 'TRUE for the three hand-built demonstration members.',

    eligibility.plan_id AS plan_id COMMENT = 'Plan identifier.',
    eligibility.lob     AS lob
      WITH SYNONYMS = ('line of business', 'segment')
      COMMENT = 'Line of business, for example Commercial.',

    claims.service_date AS service_date
      WITH SYNONYMS = ('date of service', 'visit date')
      COMMENT = 'Date the service was rendered.',
    claims.claim_type   AS claim_type
      COMMENT = 'PROFESSIONAL or INSTITUTIONAL.',

    diagnoses.icd10     AS icd10
      WITH SYNONYMS = ('diagnosis code', 'condition code')
      COMMENT = 'ICD-10-CM code. Codes beginning E11 indicate Type 2 Diabetes Mellitus.',

    rx.fill_date        AS fill_date COMMENT = 'Date the prescription was dispensed.',
    rx.days_supply      AS days_supply
      COMMENT = 'Days of therapy dispensed. Needed to establish continuous therapy.',

    drugs.drug_name     AS drug_name COMMENT = 'Drug name and strength.',
    drugs.drug_class    AS drug_class
      WITH SYNONYMS = ('medication class', 'therapeutic class')
      COMMENT = 'Therapeutic class: BIGUANIDE (metformin), SGLT2_INHIBITOR, SULFONYLUREA, GLP1_RA, DPP4_INHIBITOR, INSULIN.',
    drugs.tier          AS tier COMMENT = 'Formulary tier, 1 through 4.',

    labs.collected_date AS collected_date COMMENT = 'Date the specimen was collected.',
    labs.loinc          AS loinc
      COMMENT = 'LOINC code. 4548-4 is Hemoglobin A1c.',
    labs.test_name      AS test_name COMMENT = 'Human-readable test name.',

    providers.specialty      AS specialty COMMENT = 'Provider specialty.',
    providers.network_status AS network_status
      WITH SYNONYMS = ('in network', 'out of network')
      COMMENT = 'IN_NETWORK or OUT_OF_NETWORK. Out-of-network encounters often carry clinical detail absent from structured claims.',

    requests.requested_drug AS requested_drug COMMENT = 'Drug requested on the prior authorization.',
    requests.status         AS status
      COMMENT = 'PENDING, APPROVED, or ROUTED_TO_CLINICIAN. The system never emits DENIED.',
    requests.request_date   AS request_date COMMENT = 'Date the request was submitted.'
  )


  METRICS (
    members.member_count      AS COUNT(members.member_id)
      WITH SYNONYMS = ('number of members', 'how many members', 'population size')
      COMMENT = 'Distinct members.',
    members.average_age       AS AVG(FLOOR(DATEDIFF(day, members.date_of_birth, CURRENT_DATE()) / 365.25))
      COMMENT = 'Mean member age in years.',

    claims.claim_count        AS COUNT(claims.claim_id)
      WITH SYNONYMS = ('number of claims', 'claim volume')
      COMMENT = 'Number of medical claims.',
    claims.total_billed       AS SUM(claims.billed_amount)
      COMMENT = 'Total billed amount across claims.',
    claims.total_allowed      AS SUM(claims.allowed_amount)
      COMMENT = 'Total allowed amount across claims.',

    rx.fill_count             AS COUNT(rx.rx_claim_id)
      WITH SYNONYMS = ('number of fills', 'prescription count')
      COMMENT = 'Number of pharmacy fills.',
    rx.total_days_supply      AS SUM(rx.days_supply)
      COMMENT = 'Total days of therapy dispensed.',

    labs.lab_count            AS COUNT(labs.lab_id)
      COMMENT = 'Number of laboratory results.',
    labs.average_a1c          AS AVG(labs.value_num)
      WITH SYNONYMS = ('mean HbA1c', 'average hemoglobin a1c')
      COMMENT = 'Average lab value. Filter to LOINC 4548-4 for HbA1c specifically.',
    labs.max_a1c              AS MAX(labs.value_num)
      COMMENT = 'Highest lab value. Filter to LOINC 4548-4 for HbA1c.',

    requests.request_count    AS COUNT(requests.pa_id)
      WITH SYNONYMS = ('number of prior authorizations', 'PA volume')
      COMMENT = 'Number of prior authorization requests.'
  )

  COMMENT = 'Member 360 for a health plan: members, coverage, claims, diagnoses, pharmacy fills, labs, providers and prior authorization requests. All data synthetic. Use for population questions; prior authorization determinations are computed by the Criteria Ledger, not by this view.';

-- Cleanup of the syntax probe.
DROP SEMANTIC VIEW IF EXISTS VERITY.SEMANTIC._SMOKE;
