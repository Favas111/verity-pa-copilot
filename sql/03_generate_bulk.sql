-- =====================================================================
-- VERITY — 03_generate_bulk.sql
-- Tier 1 synthetic population: 5,000 members and their claims history.
--
-- Determinism: every value derives from ABS(HASH(key,'salt')) % n rather
-- than RANDOM(seed). Re-running reproduces byte-identical data, which
-- matters because judges may clone and re-run this repo.
--
-- Realism notes (both were deliberate corrections during the build):
--   * HbA1c is drawn right-skewed, not uniform. A flat A1c distribution
--     averages ~9.0 and reads as obviously synthetic to any clinician.
--   * Rx fills carry per-member non-adherence, so therapy runs fragment.
--     Perfectly consecutive fills yielded 94% adequate trials, which is
--     both implausible and never exercises the NOT_MET path.
--
-- ALL DATA SYNTHETIC. Fictional payer, fictional members, fake NPIs/NDCs.
-- =====================================================================

USE DATABASE VERITY;
USE SCHEMA CORE;

-- ---------------------------------------------------------------------
-- Members — 5,000, ages ~18-78
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE MEMBER AS
WITH n AS (SELECT SEQ4() AS i FROM TABLE(GENERATOR(ROWCOUNT=>5000))),
fn AS (SELECT ARRAY_CONSTRUCT('James','Maria','Robert','Linda','David','Susan','Michael','Karen',
       'William','Nancy','Daniel','Lisa','Joseph','Betty','Thomas','Sandra','Charles','Ashley',
       'Anthony','Emily','Marcus','Priya','Chen','Aisha','Diego','Fatima','Ravi','Elena') AS a),
ln AS (SELECT ARRAY_CONSTRUCT('Alvarez','Bennett','Carter','Dawson','Ellery','Fairbanks','Grayson',
       'Holloway','Ibarra','Jennings','Kowalski','Lindqvist','Marchetti','Nakamura','Okafor',
       'Pemberton','Quintero','Rasmussen','Sandoval','Thorne','Ueda','Vasquez','Whitfield',
       'Ximenes','Yardley','Zelaya') AS a)
SELECT
 'M'||LPAD(i::STRING,8,'0') AS member_id,
 GET(fn.a, ABS(HASH(i,'fn'))%ARRAY_SIZE(fn.a))::STRING AS first_name,
 GET(ln.a, ABS(HASH(i,'ln'))%ARRAY_SIZE(ln.a))::STRING AS last_name,
 DATEADD(day, -(ABS(HASH(i,'dob'))%21900+6570), '2026-08-26'::DATE) AS date_of_birth,
 CASE WHEN ABS(HASH(i,'sex'))%2=0 THEN 'F' ELSE 'M' END AS sex,
 GET(ARRAY_CONSTRUCT('MN','TX','FL','CA','NY','OH','PA','IL','NC','GA'), ABS(HASH(i,'st'))%10)::STRING AS state,
 LPAD((ABS(HASH(i,'z'))%900+100)::STRING,3,'0') AS zip3,
 FALSE AS is_golden
FROM n, fn, ln;

-- ---------------------------------------------------------------------
-- Providers — ~14% out of network. Network status matters: out-of-network
-- encounters are exactly the ones whose narrative never reaches structured
-- claims, which is what the hero scenario turns on.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE PROVIDER AS
WITH n AS (SELECT SEQ4() AS i FROM TABLE(GENERATOR(ROWCOUNT=>200))),
sp AS (SELECT ARRAY_CONSTRUCT('Family Medicine','Internal Medicine','Endocrinology','Cardiology',
       'Nephrology','Obstetrics and Gynecology','Emergency Medicine') AS a),
nm AS (SELECT ARRAY_CONSTRUCT('Northgate','Lakeside','Cedar Ridge','Harbor Point','Summit',
       'Fairview','Riverbend','Stonebrook','Westmoor','Elmhurst') AS a)
SELECT
 'P'||LPAD(i::STRING,6,'0') AS provider_id,
 '99'||LPAD((ABS(HASH(i,'npi'))%100000000)::STRING,8,'0') AS npi,
 GET(nm.a, ABS(HASH(i,'n1'))%ARRAY_SIZE(nm.a))::STRING || ' ' ||
   GET(ARRAY_CONSTRUCT('Clinic','Medical Group','Health Partners','Family Practice','Specialty Care'),
       ABS(HASH(i,'n2'))%5)::STRING AS provider_name,
 GET(sp.a, ABS(HASH(i,'sp'))%ARRAY_SIZE(sp.a))::STRING AS specialty,
 CASE WHEN ABS(HASH(i,'net'))%100 < 18 THEN 'OUT_OF_NETWORK' ELSE 'IN_NETWORK' END AS network_status
FROM n, sp, nm;

CREATE OR REPLACE TABLE ELIGIBILITY AS
SELECT member_id,
 'PLAN-'||LPAD((ABS(HASH(member_id,'pl'))%6+1)::STRING,3,'0') AS plan_id,
 'Commercial' AS lob,
 DATEADD(year,-(ABS(HASH(member_id,'cs'))%4+1),'2026-01-01'::DATE) AS coverage_start,
 NULL::DATE AS coverage_end
FROM MEMBER;

-- ---------------------------------------------------------------------
-- Claims — diabetic cohort (~28%) gets a heavier utilisation profile.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE CLAIM AS
WITH m AS (
  SELECT member_id,
         CASE WHEN (ABS(HASH(member_id,'dm'))%100) < 28
              THEN 16 + ABS(HASH(member_id,'cc'))%17
              ELSE  5 + ABS(HASH(member_id,'cc'))%12 END AS n_claims
  FROM MEMBER),
k AS (SELECT SEQ4() AS j FROM TABLE(GENERATOR(ROWCOUNT=>33)))
SELECT
  'C'||LPAD((ABS(HASH(m.member_id,k.j,'cid'))%999999999)::STRING,10,'0')||'-'||k.j::STRING AS claim_id,
  m.member_id,
  'P'||LPAD((ABS(HASH(m.member_id,k.j,'pv'))%200)::STRING,6,'0') AS provider_id,
  DATEADD(day, -(ABS(HASH(m.member_id,k.j,'sd'))%1095), '2026-08-26'::DATE) AS service_date,
  CASE WHEN ABS(HASH(m.member_id,k.j,'ct'))%100 < 82 THEN 'PROFESSIONAL' ELSE 'INSTITUTIONAL' END AS claim_type,
  ROUND(40 + ABS(HASH(m.member_id,k.j,'ba'))%2400 + (ABS(HASH(m.member_id,k.j,'bc'))%100)/100.0, 2) AS billed_amount,
  NULL AS allowed_amount
FROM m JOIN k ON k.j < m.n_claims;

UPDATE CLAIM SET allowed_amount = ROUND(billed_amount * (0.38 + (ABS(HASH(claim_id,'al'))%38)/100.0), 2);

CREATE OR REPLACE TABLE CLAIM_DIAGNOSIS AS
WITH c AS (
  SELECT cl.claim_id, (ABS(HASH(cl.member_id,'dm'))%100) < 28 AS is_dm FROM CLAIM cl),
k AS (SELECT SEQ4() AS s FROM TABLE(GENERATOR(ROWCOUNT=>3))),
dm AS (SELECT ARRAY_CONSTRUCT('E11.9','E11.65','E11.40','E11.22','E11.21','E11.59') AS a),
ot AS (SELECT ARRAY_CONSTRUCT('I10','E78.5','Z00.00','M54.50','J06.9','E66.9','N18.30','K21.9','F41.9','M79.18') AS a)
SELECT c.claim_id, k.s + 1 AS seq,
  CASE WHEN c.is_dm AND k.s = 0 AND ABS(HASH(c.claim_id,'p'))%100 < 72
       THEN GET(dm.a, ABS(HASH(c.claim_id,'dx'))%ARRAY_SIZE(dm.a))::STRING
       ELSE GET(ot.a, ABS(HASH(c.claim_id,k.s,'ox'))%ARRAY_SIZE(ot.a))::STRING END AS icd10
FROM c JOIN k ON k.s < (1 + ABS(HASH(c.claim_id,'nd'))%3)
CROSS JOIN dm CROSS JOIN ot;

-- ---------------------------------------------------------------------
-- Pharmacy claims, WITH non-adherence gaps (see header note).
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE RX_CLAIM AS
WITH dmm AS (SELECT member_id FROM MEMBER WHERE (ABS(HASH(member_id,'dm'))%100) < 28),
met AS (
  SELECT member_id, 2 + ABS(HASH(member_id,'mn'))%16 AS n_fills,
         ABS(HASH(member_id,'ms'))%900 + 120 AS start_back,
         5 + ABS(HASH(member_id,'adh'))%40 AS gap_pct
  FROM dmm WHERE ABS(HASH(member_id,'mf'))%100 < 78),
sec AS (
  SELECT member_id, 2 + ABS(HASH(member_id,'sn'))%14 AS n_fills,
         ABS(HASH(member_id,'ss'))%600 + 90 AS start_back,
         5 + ABS(HASH(member_id,'adh2'))%40 AS gap_pct,
         CASE WHEN ABS(HASH(member_id,'sc'))%2=0 THEN 'SGLT2_INHIBITOR' ELSE 'SULFONYLUREA' END AS cls
  FROM dmm WHERE ABS(HASH(member_id,'sf'))%100 < 46),
k AS (SELECT SEQ4() AS j FROM TABLE(GENERATOR(ROWCOUNT=>18))),
dref AS (SELECT drug_class, ndc, drug_name,
                ROW_NUMBER() OVER (PARTITION BY drug_class ORDER BY ndc)-1 AS rn,
                COUNT(*) OVER (PARTITION BY drug_class) AS cnt
         FROM DRUG_REFERENCE)
SELECT 'RX'||LPAD((ABS(HASH(m.member_id,k.j,'met'))%999999999)::STRING,10,'0') AS rx_claim_id,
       m.member_id, d.ndc,
       DATEADD(day, -(m.start_back - k.j*30), '2026-08-26'::DATE) AS fill_date,
       30 AS days_supply, 30 AS quantity, d.drug_name AS dose_text,
       'P'||LPAD((ABS(HASH(m.member_id,'pr'))%200)::STRING,6,'0') AS prescriber_id
FROM met m JOIN k ON k.j < m.n_fills
JOIN dref d ON d.drug_class='BIGUANIDE' AND d.rn = ABS(HASH(m.member_id,'md'))%d.cnt
WHERE ABS(HASH(m.member_id,k.j,'skip'))%100 >= m.gap_pct
UNION ALL
SELECT 'RX'||LPAD((ABS(HASH(s.member_id,k.j,'sec'))%999999999)::STRING,10,'0'),
       s.member_id, d.ndc,
       DATEADD(day, -(s.start_back - k.j*30), '2026-08-26'::DATE),
       30, 30, d.drug_name,
       'P'||LPAD((ABS(HASH(s.member_id,'pr2'))%200)::STRING,6,'0')
FROM sec s JOIN k ON k.j < s.n_fills
JOIN dref d ON d.drug_class = s.cls AND d.rn = ABS(HASH(s.member_id,'sd'))%d.cnt
WHERE ABS(HASH(s.member_id,k.j,'skip2'))%100 >= s.gap_pct;

-- ---------------------------------------------------------------------
-- HbA1c labs — right-skewed (see header note). LOINC 4548-4.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE LAB_RESULT AS
WITH dmm AS (SELECT member_id FROM MEMBER WHERE (ABS(HASH(member_id,'dm'))%100) < 28),
k AS (SELECT SEQ4() AS j FROM TABLE(GENERATOR(ROWCOUNT=>7))),
r AS (
  SELECT m.member_id, k.j,
         ROUND(6.1 + POWER((ABS(HASH(m.member_id,k.j,'v'))%1000)/1000.0, 2.5) * 5.5, 1) AS a1c
  FROM dmm m JOIN k ON k.j < (2 + ABS(HASH(m.member_id,'ln'))%5))
SELECT
 'L'||LPAD((ABS(HASH(member_id,j,'lab'))%999999999)::STRING,10,'0') AS lab_id,
 member_id, '4548-4' AS loinc, 'Hemoglobin A1c' AS test_name,
 a1c AS value_num, '%' AS unit,
 DATEADD(day, -(ABS(HASH(member_id,'lb'))%70 + j*182), '2026-08-26'::DATE) AS collected_date,
 CASE WHEN a1c >= 7.0 THEN 'H' ELSE 'N' END AS abnormal_flag
FROM r;

-- =====================================================================
-- Resolver views — these are what the Criteria Ledger leaves evaluate.
-- =====================================================================

-- Every identity a member has held. Policy section 2.3 requires step
-- therapy to be evaluated across all of them, not just the current id.
CREATE OR REPLACE VIEW V_MEMBER_IDENTITY AS
SELECT member_id, member_id AS any_member_id, 'CURRENT' AS id_source FROM MEMBER
UNION ALL
SELECT member_id, prior_member_id, COALESCE(prior_carrier,'PRIOR_MERIDIAN_PLAN') FROM MEMBER_LINK;

-- Continuous-therapy runs via fill-to-fill gap analysis. A run continues
-- while the next fill starts within 15 days of the previous fill's
-- exhaustion (fill_date + days_supply). days_supply is load-bearing here:
-- fill dates alone cannot establish the CONSECUTIVE months that section
-- 2.3 requires.
CREATE OR REPLACE VIEW V_DRUG_TRIAL AS
WITH fills AS (
  SELECT i.member_id, d.drug_class, r.fill_date, r.days_supply, r.ndc, r.rx_claim_id,
         i.any_member_id, i.id_source
  FROM V_MEMBER_IDENTITY i
  JOIN RX_CLAIM r       ON r.member_id = i.any_member_id
  JOIN DRUG_REFERENCE d ON d.ndc = r.ndc),
seq AS (
  SELECT *, LAG(DATEADD(day, days_supply, fill_date))
              OVER (PARTITION BY member_id, drug_class ORDER BY fill_date) AS prev_end
  FROM fills),
marked AS (
  SELECT *, CASE WHEN prev_end IS NULL OR fill_date > DATEADD(day, 15, prev_end)
                 THEN 1 ELSE 0 END AS starts_run
  FROM seq),
runs AS (
  SELECT *, SUM(starts_run) OVER (PARTITION BY member_id, drug_class ORDER BY fill_date
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS run_no
  FROM marked)
SELECT member_id, drug_class, run_no,
       MIN(fill_date) AS trial_start,
       MAX(DATEADD(day, days_supply, fill_date)) AS trial_end,
       DATEDIFF(day, MIN(fill_date), MAX(DATEADD(day, days_supply, fill_date))) AS trial_days,
       ROUND(DATEDIFF(day, MIN(fill_date), MAX(DATEADD(day, days_supply, fill_date)))/30.44, 1) AS trial_months,
       COUNT(*) AS fill_count,
       ARRAY_AGG(DISTINCT id_source) AS evidence_sources,
       ARRAY_AGG(rx_claim_id) WITHIN GROUP (ORDER BY fill_date) AS rx_claim_ids
FROM runs
GROUP BY member_id, drug_class, run_no;
